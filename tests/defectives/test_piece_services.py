import pytest
from django.utils import timezone

from apps.defectives.models import DefectiveEvent, DefectivePiece, Outcome, PieceStatus, ScrapReason, Source
from apps.defectives.services import DefectiveError, mark_defective, normalise_tag, scrap
from apps.inventory.models import EntryKind, ServiceSubtype, StockBalance
from apps.inventory.services import NotEnoughStock, balance_drift
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
