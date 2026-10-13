import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.defectives import services
from apps.defectives.models import (
    DefectiveEvent,
    DefectivePiece,
    Outcome,
    PieceStatus,
    ReturnBatch,
    ScrapReason,
    Source,
)
from apps.defectives.services import (
    DefectiveError,
    collect_pieces,
    create_piece,
    mark_defective,
    normalise_tag,
    scrap,
)
from apps.inventory.models import EntryKind, Location, ServiceSubtype, StockBalance, StockEntry, StockLine
from apps.inventory.services import Line, NotEnoughStock, StockError, balance_drift, post_entry
from tests.factories import give_stock, loc, make_item, make_pieces, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def qty(item, place):
    row = StockBalance.objects.filter(item=item, location=place).first()
    return row.qty if row else 0


@pytest.fixture
def drv(db):
    return make_item("LG78-150-700")


def test_mark_defective_moves_stock_and_tags_each_piece(drv, office_user):
    give_stock(drv, 5, office_user)
    entry, pieces = mark_defective(
        location=loc(), lines=[(drv, 2, "Dead on arrival")], entry_date=TODAY, user=office_user
    )
    assert entry.kind == EntryKind.TRF and entry.subtype == ServiceSubtype.MARK_DEFECTIVE
    assert [p.tag for p in pieces] == ["DEF-0001", "DEF-0002"]
    assert qty(drv, loc()) == 3 and qty(drv, store()) == 2
    p = DefectivePiece.objects.get(tag="DEF-0001")
    assert (p.status, p.source, p.company.name, p.fault, p.collected_on) == (
        PieceStatus.IN_STORE,
        Source.FOUND_IN_STOCK,
        "Wipro Lighting",
        "Dead on arrival",
        TODAY,
    )
    ev = DefectiveEvent.objects.get(piece=p)
    assert (ev.from_status, ev.to_status, ev.entry) == ("", PieceStatus.IN_STORE, entry)
    assert balance_drift() == []


def test_piece_company_comes_from_the_item(office_user):
    mcb = make_item("MCB 16A SP", company="Havells", spare_type="Accessory")
    [p] = make_pieces(mcb, 1, office_user)
    assert p.company.name == "Havells"


def test_every_line_needs_a_fault(drv, office_user):
    give_stock(drv, 5, office_user)
    with pytest.raises(DefectiveError, match="Line 2: write what is wrong with the piece."):
        mark_defective(
            location=loc(), lines=[(drv, 1, "no output"), (drv, 1, " ")], entry_date=TODAY, user=office_user
        )


def test_over_marking_saves_nothing_and_uses_no_tag(drv, office_user):
    give_stock(drv, 1, office_user)
    with pytest.raises(NotEnoughStock):
        mark_defective(location=loc(), lines=[(drv, 2, "x")], entry_date=TODAY, user=office_user)
    assert not DefectivePiece.objects.exists()
    _, [p] = mark_defective(location=loc(), lines=[(drv, 1, "x")], entry_date=TODAY, user=office_user)
    assert p.tag == "DEF-0001"


def test_cannot_mark_from_the_store(drv, office_user):
    with pytest.raises(DefectiveError, match="good-stock location"):
        mark_defective(location=store(), lines=[(drv, 1, "x")], entry_date=TODAY, user=office_user)


def test_scrap_writes_off_pieces_in_store(drv, office_user):
    pieces = make_pieces(drv, 3, office_user)
    entry = scrap(pieces=pieces[:2], reason=ScrapReason.NOT_WORTH, user=office_user)
    assert (entry.kind, entry.subtype, entry.reason) == (
        EntryKind.ADJ,
        ServiceSubtype.SCRAP_DEFECTIVE,
        "DAMAGED",
    )
    assert "Scrapped DEF-0001, DEF-0002: Not worth returning" in entry.note and qty(drv, store()) == 1
    statuses = list(DefectivePiece.objects.order_by("tag").values_list("status", flat=True))
    assert statuses == [PieceStatus.SCRAPPED, PieceStatus.SCRAPPED, PieceStatus.IN_STORE]
    assert DefectiveEvent.objects.filter(entry=entry).count() == 2
    assert DefectivePiece.objects.get(tag="DEF-0001").settled_on == TODAY
    assert balance_drift() == []


def test_scrap_clears_a_leftover_outcome(drv, office_user):
    """A piece rejected and sent back earlier is in store again with the old answer; scrapping clears it."""
    [p] = make_pieces(drv, 1, office_user)
    DefectivePiece.objects.filter(pk=p.pk).update(outcome=Outcome.REJECTED_RETURNED, settled_on=TODAY)
    scrap(pieces=[p], reason=ScrapReason.REJECTED, user=office_user)
    p.refresh_from_db()
    assert (p.status, p.outcome, p.settled_on) == (PieceStatus.SCRAPPED, "", TODAY)


def test_scrap_rules(drv, office_user):
    pieces = make_pieces(drv, 2, office_user)
    with pytest.raises(DefectiveError, match="Tick at least one piece."):
        scrap(pieces=[], reason=ScrapReason.BURNT, user=office_user)
    with pytest.raises(DefectiveError, match="Choose why the pieces are scrapped."):
        scrap(pieces=pieces, reason="", user=office_user)
    with pytest.raises(DefectiveError, match="Write a note when the reason is Other."):
        scrap(pieces=pieces, reason=ScrapReason.OTHER, user=office_user)
    scrap(pieces=pieces[:1], reason=ScrapReason.OTHER, note="fell off the shelf", user=office_user)
    with pytest.raises(DefectiveError, match="DEF-0001 is scrapped. Only pieces in store can be scrapped."):
        scrap(pieces=pieces[:1], reason=ScrapReason.BURNT, user=office_user)


@pytest.mark.parametrize(
    "text, tag",
    [("def-42", "DEF-0042"), ("DEF0042", "DEF-0042"), (" DEF-0007 ", "DEF-0007"), ("rb-1", "RB-1")],
)
def test_normalise_tag(text, tag):
    assert normalise_tag(text) == tag


def days_ago(n):
    return TODAY - datetime.timedelta(days=n)


def collected(item, n, user, day=TODAY):
    """A site-visit style Stock IN of `n` failed pieces straight into the Defective store."""
    return post_entry(
        kind=EntryKind.IN,
        entry_date=day,
        lines=[Line(item, store(), n)],
        user=user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
    )


# ---------------------------------------------------------------- mark defective: line rules


@pytest.mark.parametrize("bad", [0, -2, "3", 1.5, True, None])
def test_quantity_must_be_a_whole_number_of_one_or_more(drv, office_user, bad):
    give_stock(drv, 5, office_user)
    with pytest.raises(DefectiveError, match="Line 1: quantity must be 1 or more."):
        mark_defective(location=loc(), lines=[(drv, bad, "x")], entry_date=TODAY, user=office_user)


def test_quantity_is_capped_at_200(drv, office_user):
    give_stock(drv, 201, office_user)
    with pytest.raises(DefectiveError, match="Line 1: quantity must be between 1 and 200."):
        mark_defective(location=loc(), lines=[(drv, 201, "x")], entry_date=TODAY, user=office_user)
    _, pieces = mark_defective(location=loc(), lines=[(drv, 200, "x")], entry_date=TODAY, user=office_user)
    assert len(pieces) == 200 and pieces[-1].tag == "DEF-0200"


def test_too_long_fault_is_refused_not_cut(drv, office_user):
    give_stock(drv, 2, office_user)
    other = make_item("EIO9326", spare_type="PCB / LED module")
    give_stock(other, 1, office_user)
    with pytest.raises(DefectiveError, match="Line 2: keep the fault to 200 characters or less."):
        mark_defective(
            location=loc(), lines=[(drv, 1, "x"), (other, 1, "y" * 201)], entry_date=TODAY, user=office_user
        )


def test_same_item_on_two_lines_is_refused(drv, office_user):
    give_stock(drv, 2, office_user)
    with pytest.raises(DefectiveError, match="LG78-150-700 is listed twice."):
        mark_defective(
            location=loc(), lines=[(drv, 1, "x"), (drv, 1, "y")], entry_date=TODAY, user=office_user
        )


def test_cannot_mark_at_an_inactive_location(drv, office_user):
    give_stock(drv, 1, office_user)
    Location.objects.filter(pk=loc().pk).update(is_active=False)
    with pytest.raises(StockError, match="Vizag Office is inactive."):
        mark_defective(location=loc(), lines=[(drv, 1, "x")], entry_date=TODAY, user=office_user)
    assert not DefectivePiece.objects.exists()


def test_cannot_mark_in_the_future(drv, office_user):
    give_stock(drv, 1, office_user)
    tomorrow = TODAY + datetime.timedelta(days=1)
    with pytest.raises(DefectiveError, match="The date can't be in the future."):
        mark_defective(location=loc(), lines=[(drv, 1, "x")], entry_date=tomorrow, user=office_user)


def test_a_failure_after_posting_saves_nothing(drv, office_user, monkeypatch):
    give_stock(drv, 2, office_user)
    entries = StockEntry.objects.count()

    def boom(prefix, n):
        raise RuntimeError("counter unavailable")

    monkeypatch.setattr(services, "next_numbers", boom)
    with pytest.raises(RuntimeError):
        mark_defective(location=loc(), lines=[(drv, 2, "x")], entry_date=TODAY, user=office_user)
    assert StockEntry.objects.count() == entries and not DefectivePiece.objects.exists()
    assert qty(drv, loc()) == 2 and qty(drv, store()) == 0


def test_marking_ten_pieces_costs_no_more_queries_than_one(office_user):
    one, ten, warm = make_item("ONE-1"), make_item("TEN-10"), make_item("WARM-0")
    for item, n in ((one, 1), (ten, 10), (warm, 1)):
        give_stock(item, n, office_user)
    # The first mark creates the DEF counter row and the store balance rows; measure after that.
    mark_defective(location=loc(), lines=[(warm, 1, "x")], entry_date=TODAY, user=office_user)
    mark_defective(location=loc(), lines=[(one, 1, "x")], entry_date=TODAY, user=office_user)
    give_stock(one, 1, office_user)
    with CaptureQueriesContext(connection) as q1:
        mark_defective(location=loc(), lines=[(one, 1, "x")], entry_date=TODAY, user=office_user)
    with CaptureQueriesContext(connection) as q10:
        _, pieces = mark_defective(location=loc(), lines=[(ten, 10, "x")], entry_date=TODAY, user=office_user)
    assert len(pieces) == 10 and all(p.pk for p in pieces)
    assert DefectiveEvent.objects.filter(piece__in=pieces).count() == 10
    assert len(q10) <= len(q1) + 1 and len(q10) <= 30  # +1: the ten-piece item's store balance row is new


# ---------------------------------------------------------------- collect_pieces / create_piece checks


def test_collect_pieces_tags_one_piece_per_unit(drv, office_user):
    e = collected(drv, 3, office_user)
    pieces = collect_pieces(
        entry=e,
        item=drv,
        qty=3,
        source=Source.SITE_VISIT,
        collected_on=TODAY,
        user=office_user,
        batch_code="B7",
        fault="no output",
    )
    assert [p.tag for p in pieces] == ["DEF-0001", "DEF-0002", "DEF-0003"]
    assert {(p.source, p.batch_code, p.fault) for p in pieces} == {(Source.SITE_VISIT, "B7", "no output")}
    assert DefectiveEvent.objects.filter(entry=e, from_status="", to_status=PieceStatus.IN_STORE).count() == 3


def test_create_piece_one_at_a_time_up_to_the_store_line(drv, office_user):
    e = collected(drv, 2, office_user)
    args = {"item": drv, "source": Source.SITE_VISIT, "collected_on": TODAY, "user": office_user, "entry": e}
    assert [create_piece(**args).tag, create_piece(**args).tag] == ["DEF-0001", "DEF-0002"]
    with pytest.raises(DefectiveError, match="brought only 2 LG78-150-700 into the Defective store"):
        create_piece(**args)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"entry": None}, "A piece needs the ledger entry that brought it into the Defective store."),
        ({"collected_on": None}, "Choose the collection date."),
        ({"collected_on": TODAY + datetime.timedelta(days=1)}, "The collection date can't be in the future."),
        ({"collected_on": TODAY - datetime.timedelta(days=1)}, "The collection date must be the date of IN-"),
        ({"source": "STOLEN"}, "Choose where the piece came from."),
        ({"qty": 0}, "Quantity must be 1 or more."),
        ({"qty": 201}, "Quantity must be between 1 and 200."),
        ({"qty": 3}, "brought only 2 LG78-150-700 into the Defective store."),
        ({"fault": "z" * 201}, "Keep the fault to 200 characters or less."),
        ({"batch_code": "b" * 41}, "Keep the batch code to 40 characters or less."),
    ],
)
def test_collect_pieces_refuses(drv, office_user, change, message):
    e = collected(drv, 2, office_user)
    args = {
        "entry": e,
        "item": drv,
        "qty": 2,
        "source": Source.SITE_VISIT,
        "collected_on": TODAY,
        "user": office_user,
    }
    with pytest.raises(DefectiveError, match=message):
        collect_pieces(**{**args, **change})
    assert not DefectivePiece.objects.exists()


def test_collect_pieces_needs_a_store_line_for_the_item(drv, office_user):
    other = make_item("EIO9326", spare_type="PCB / LED module")
    supplier_in = give_stock(drv, 2, office_user)  # good stock, not the Defective store
    with pytest.raises(
        DefectiveError, match=f"{supplier_in.number} brought no LG78-150-700 into the Defective"
    ):
        collect_pieces(
            entry=supplier_in, item=drv, qty=1, source=Source.SITE_VISIT, collected_on=TODAY, user=office_user
        )
    e = collected(drv, 1, office_user)
    with pytest.raises(DefectiveError, match="brought no EIO9326 into the Defective store."):
        collect_pieces(
            entry=e, item=other, qty=1, source=Source.SITE_VISIT, collected_on=TODAY, user=office_user
        )


# ---------------------------------------------------------------- scrap: more rules


def test_scrap_cannot_be_dated_before_the_piece_came_in(drv, office_user):
    post_entry(
        kind=EntryKind.IN,
        entry_date=days_ago(10),
        lines=[Line(drv, loc(), 2)],
        user=office_user,
        subtype="SUPPLIER",
    )
    _, pieces = mark_defective(
        location=loc(), lines=[(drv, 2, "x")], entry_date=days_ago(5), user=office_user
    )
    with pytest.raises(DefectiveError, match=f"DEF-0001 only came into the store on {days_ago(5):%d-%m-%Y}."):
        scrap(pieces=pieces, reason=ScrapReason.BURNT, user=office_user, entry_date=days_ago(7))
    entry = scrap(pieces=pieces, reason=ScrapReason.BURNT, user=office_user, entry_date=days_ago(5))
    assert entry.entry_date == days_ago(5)


def test_scrap_cannot_be_in_the_future(drv, office_user):
    pieces = make_pieces(drv, 1, office_user)
    tomorrow = TODAY + datetime.timedelta(days=1)
    with pytest.raises(DefectiveError, match="The scrap date can't be in the future."):
        scrap(pieces=pieces, reason=ScrapReason.BURNT, user=office_user, entry_date=tomorrow)


def test_scrap_refuses_unknown_or_repeated_pieces(drv, office_user):
    pieces = make_pieces(drv, 2, office_user)
    ghost = DefectivePiece(pk=999999, tag="DEF-9999")
    for chosen in ([pieces[0], ghost], [pieces[0], pieces[0]]):
        with pytest.raises(DefectiveError, match="Some pieces could not be found; refresh and try again."):
            scrap(pieces=chosen, reason=ScrapReason.BURNT, user=office_user)


def test_scrap_a_piece_in_a_draft_batch_gives_the_hint(drv, office_user):
    [p] = make_pieces(drv, 1, office_user)
    batch = ReturnBatch.objects.create(
        number="RB-0001", company=p.company, created_on=TODAY, created_by=office_user
    )
    DefectivePiece.objects.filter(pk=p.pk).update(status=PieceStatus.IN_BATCH, return_batch=batch)
    expected = (
        "DEF-0001 is in draft batch (RB-0001). Only pieces in store can be scrapped; "
        "remove it from the batch first."
    )
    with pytest.raises(DefectiveError) as err:
        scrap(pieces=[p], reason=ScrapReason.BURNT, user=office_user)
    assert err.value.message == expected


def test_scrap_across_two_items_posts_one_line_per_item(drv, office_user):
    pcb = make_item("EIO9326", spare_type="PCB / LED module")
    pieces = make_pieces(drv, 2, office_user) + make_pieces(pcb, 1, office_user)
    entry = scrap(pieces=pieces, reason=ScrapReason.NOT_WORTH, user=office_user)
    lines = sorted(StockLine.objects.filter(entry=entry).values_list("item__code", "location__name", "qty"))
    assert lines == [("EIO9326", store().name, -1), ("LG78-150-700", store().name, -2)]
    assert balance_drift() == []
