from datetime import timedelta

import pytest
from django.utils import timezone

from apps.defectives.models import BatchLine, BatchStatus, DefectivePiece, Outcome, PieceStatus
from apps.defectives.services import (
    DefectiveError,
    add_pieces,
    create_batch,
    dispatch,
    mark_defective,
    remove_pieces,
    settle,
)
from apps.inventory.models import Company, EntryKind, ServiceSubtype, StockBalance
from apps.inventory.services import Line, balance_drift, post_entry
from tests.factories import loc, make_item, make_pieces, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def qty(item, place):
    row = StockBalance.objects.filter(item=item, location=place).first()
    return row.qty if row else 0


def wipro():
    return Company.objects.get(name="Wipro Lighting")


def fresh(piece):
    piece.refresh_from_db()
    return piece


@pytest.fixture
def wipro_pieces(office_user):
    return make_pieces(make_item("LG78-150-700"), 3, office_user)  # DEF-0001..0003


@pytest.fixture
def havells_piece(office_user):
    return make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user)[0]


@pytest.fixture
def old_pieces(office_user):
    """Two pieces collected 10 days ago (stocked and marked defective on that date)."""
    item = make_item("LG78-150-700")
    day = TODAY - timedelta(days=10)
    post_entry(
        kind=EntryKind.IN,
        entry_date=day,
        lines=[Line(item, loc(), 2)],
        user=office_user,
        subtype="SUPPLIER",
        party="Test supplier",
    )
    _, pieces = mark_defective(
        location=loc(), lines=[(item, 2, "no output")], entry_date=day, user=office_user
    )
    return pieces


def sent_batch(pieces, user):
    b = create_batch(company=wipro(), user=user, pieces=pieces)
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D51243817", user=user)
    b.refresh_from_db()
    return b


def test_create_batch_with_pieces(wipro_pieces, office_user):
    b = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:2], note=" Drivers ")
    assert (b.number, b.status, b.note, b.created_on) == ("RB-0001", BatchStatus.DRAFT, "Drivers", TODAY)
    assert [fresh(p).status for p in wipro_pieces] == [
        PieceStatus.IN_BATCH,
        PieceStatus.IN_BATCH,
        PieceStatus.IN_STORE,
    ]
    assert fresh(wipro_pieces[0]).return_batch == b and b.lines.count() == 2
    event = wipro_pieces[0].events.last()
    assert (event.from_status, event.to_status, event.note) == (
        PieceStatus.IN_STORE,
        PieceStatus.IN_BATCH,
        "Added to RB-0001",
    )


def test_company_is_required(office_user):
    with pytest.raises(DefectiveError, match="Choose the company the pieces go back to."):
        create_batch(company=None, user=office_user)


def test_create_date_cannot_be_in_the_future(office_user):
    with pytest.raises(DefectiveError, match="The batch date can't be in the future."):
        create_batch(company=wipro(), user=office_user, created_on=TODAY + timedelta(days=1))


def test_a_batch_holds_one_company(wipro_pieces, havells_piece, office_user):
    with pytest.raises(DefectiveError, match="DEF-0004 is a Havells piece. A batch holds one company"):
        create_batch(company=wipro(), user=office_user, pieces=[wipro_pieces[0], havells_piece])
    b = create_batch(company=wipro(), user=office_user)
    with pytest.raises(
        DefectiveError, match="RB-0001 is for Wipro Lighting, but DEF-0004 is a Havells piece"
    ):
        add_pieces(batch=b, pieces=[havells_piece], user=office_user)


def test_only_pieces_in_store_can_be_added(wipro_pieces, office_user):
    create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:1])
    b2 = create_batch(company=wipro(), user=office_user)
    with pytest.raises(
        DefectiveError, match=r"DEF-0001 is in draft batch \(RB-0001\)\. Only pieces in store"
    ):
        add_pieces(batch=b2, pieces=wipro_pieces[:1], user=office_user)
    with pytest.raises(DefectiveError, match="Tick at least one piece."):
        add_pieces(batch=b2, pieces=[], user=office_user)


def test_add_and_remove_keep_each_history_in_date_order(old_pieces, office_user):
    with pytest.raises(DefectiveError, match="DEF-0001 only came into the store on"):
        create_batch(
            company=wipro(), user=office_user, pieces=old_pieces, created_on=TODAY - timedelta(days=12)
        )
    b = create_batch(company=wipro(), user=office_user, created_on=TODAY - timedelta(days=8))
    with pytest.raises(DefectiveError, match="can't be before the batch was created"):
        add_pieces(batch=b, pieces=old_pieces, user=office_user, at=TODAY - timedelta(days=9))
    with pytest.raises(DefectiveError, match="The date can't be in the future."):
        add_pieces(batch=b, pieces=old_pieces, user=office_user, at=TODAY + timedelta(days=1))
    add_pieces(batch=b, pieces=old_pieces, user=office_user, at=TODAY - timedelta(days=5))
    with pytest.raises(DefectiveError, match="DEF-0001 only was added to the batch on"):
        remove_pieces(batch=b, pieces=old_pieces[:1], user=office_user, at=TODAY - timedelta(days=7))
    with pytest.raises(DefectiveError, match="DEF-0001 only was added to the batch on"):
        dispatch(
            batch=b, dispatched_on=TODAY - timedelta(days=6), courier="DTDC", docket_no="D1", user=office_user
        )


def test_remove_puts_the_piece_back_in_store(wipro_pieces, office_user):
    b = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:2])
    remove_pieces(batch=b, pieces=wipro_pieces[:1], user=office_user)
    p = fresh(wipro_pieces[0])
    assert p.status == PieceStatus.IN_STORE and p.return_batch is None
    assert list(b.lines.values_list("piece__tag", flat=True)) == ["DEF-0002"]
    with pytest.raises(DefectiveError, match="DEF-0001 is not in RB-0001."):
        remove_pieces(batch=b, pieces=wipro_pieces[:1], user=office_user)
    with pytest.raises(DefectiveError, match="Tick at least one piece."):
        remove_pieces(batch=b, pieces=[], user=office_user)


def test_dispatch_posts_one_out_and_locks_the_batch(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    b = sent_batch(wipro_pieces[:2], office_user)
    e = b.dispatch_entry
    assert (e.kind, e.subtype, e.return_batch, e.ref, e.party) == (
        EntryKind.OUT,
        ServiceSubtype.RETURN_TO_COMPANY,
        b,
        "D51243817",
        "Wipro Lighting",
    )
    assert [(ln.item, ln.location, ln.qty) for ln in e.lines.all()] == [(drv, store(), -2)]
    assert (b.status, b.courier, b.docket_no, b.dispatched_on) == (
        BatchStatus.DISPATCHED,
        "DTDC",
        "D51243817",
        TODAY,
    )
    assert fresh(wipro_pieces[0]).status == PieceStatus.SENT and qty(drv, store()) == 1
    assert wipro_pieces[0].events.last().entry == e
    with pytest.raises(
        DefectiveError, match="RB-0001 was dispatched on .*, so it is locked. Start a new batch."
    ):
        add_pieces(batch=b, pieces=wipro_pieces[2:], user=office_user)
    with pytest.raises(DefectiveError, match="RB-0001 is dispatched and locked."):
        remove_pieces(batch=b, pieces=wipro_pieces[:1], user=office_user)
    with pytest.raises(DefectiveError, match="RB-0001 was already dispatched."):
        dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="X", user=office_user)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"dispatched_on": None}, "Choose the dispatch date."),
        ({"dispatched_on": TODAY + timedelta(days=1)}, "The dispatch date can't be in the future."),
        ({"dispatched_on": TODAY - timedelta(days=1)}, "can't be before the batch was created"),
        ({"courier": " "}, "Choose the courier."),
        ({"docket_no": ""}, "Enter the docket / LR number."),
    ],
)
def test_dispatch_rules(wipro_pieces, office_user, change, message):
    b = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:1])
    args = {"dispatched_on": TODAY, "courier": "DTDC", "docket_no": "D1", **change}
    with pytest.raises(DefectiveError, match=message):
        dispatch(batch=b, user=office_user, **args)


def test_empty_batch_cannot_be_dispatched(office_user):
    b = create_batch(company=wipro(), user=office_user)
    with pytest.raises(DefectiveError, match="An empty batch can't be dispatched. Add pieces first."):
        dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)


def test_replaced_posts_stock_in_to_good_stock(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    good_before = qty(drv, loc())
    b = sent_batch(wipro_pieces[:2], office_user)
    [e] = settle(
        batch=b,
        pieces=wipro_pieces[:1],
        outcome=Outcome.REPLACED,
        settled_on=TODAY,
        to_location=loc(),
        user=office_user,
    )
    assert (e.kind, e.subtype, e.return_batch, e.ref) == (
        EntryKind.IN,
        ServiceSubtype.REPLACEMENT,
        b,
        "RB-0001",
    )
    assert qty(drv, loc()) == good_before + 1
    p = fresh(wipro_pieces[0])
    assert (p.status, p.outcome, p.settled_on, p.replacement_entry) == (
        PieceStatus.SETTLED,
        Outcome.REPLACED,
        TODAY,
        e,
    )
    line = BatchLine.objects.get(batch=b, piece=p)
    assert (line.outcome, line.to_location, line.entry, line.settled_on) == (
        Outcome.REPLACED,
        loc(),
        e,
        TODAY,
    )
    assert p.events.last().entry == e


def test_rejected_returned_goes_back_to_the_store_and_can_go_again(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    b = sent_batch(wipro_pieces[:1], office_user)
    [e] = settle(
        batch=b,
        pieces=wipro_pieces[:1],
        outcome=Outcome.REJECTED_RETURNED,
        settled_on=TODAY,
        user=office_user,
    )
    assert e.subtype == ServiceSubtype.DEFECTIVE_RETURNED and qty(drv, store()) == 3
    p = fresh(wipro_pieces[0])
    assert (p.status, p.outcome, p.return_batch) == (PieceStatus.IN_STORE, Outcome.REJECTED_RETURNED, None)
    b2 = create_batch(company=wipro(), user=office_user, pieces=[p])
    assert BatchLine.objects.get(batch=b, piece=p).outcome == Outcome.REJECTED_RETURNED
    assert BatchLine.objects.get(batch=b2, piece=p).outcome == ""


def test_adding_a_rejected_piece_clears_its_old_answer(wipro_pieces, office_user):
    b = sent_batch(wipro_pieces[:1], office_user)
    settle(
        batch=b,
        pieces=wipro_pieces[:1],
        outcome=Outcome.REJECTED_RETURNED,
        settled_on=TODAY,
        user=office_user,
    )
    b2 = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:1])
    p = fresh(wipro_pieces[0])
    assert (p.status, p.return_batch, p.outcome, p.settled_on) == (PieceStatus.IN_BATCH, b2, "", None)
    old = BatchLine.objects.get(batch=b, piece=p)
    assert (old.outcome, old.settled_on) == (Outcome.REJECTED_RETURNED, TODAY)


def test_rejected_scrapped_posts_nothing(wipro_pieces, office_user):
    b = sent_batch(wipro_pieces[:1], office_user)
    done = settle(
        batch=b,
        pieces=wipro_pieces[:1],
        outcome=Outcome.REJECTED_SCRAPPED,
        settled_on=TODAY,
        user=office_user,
    )
    assert done == [] and fresh(wipro_pieces[0]).status == PieceStatus.SETTLED


def test_settle_rules(wipro_pieces, office_user):
    draft = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[2:])  # RB-0001, DEF-0003
    with pytest.raises(DefectiveError, match="Only a dispatched batch can be settled."):
        settle(
            batch=draft,
            pieces=wipro_pieces[2:],
            outcome=Outcome.REPLACED,
            settled_on=TODAY,
            to_location=loc(),
            user=office_user,
        )
    b = sent_batch(wipro_pieces[:2], office_user)  # RB-0002
    cases = [
        ({"pieces": []}, "Tick the pieces the company has answered for."),
        ({"outcome": ""}, "Choose the outcome."),
        ({"settled_on": None}, "Choose the settlement date."),
        ({"settled_on": TODAY + timedelta(days=1)}, "The date can't be in the future."),
        ({"settled_on": TODAY - timedelta(days=1)}, "can't be before the batch was dispatched"),
        ({"to_location": None}, "Choose the good-stock location the replacement pieces go into."),
        ({"to_location": store()}, "Choose the good-stock location the replacement pieces go into."),
        ({"pieces": wipro_pieces[2:]}, "DEF-0003 is not in RB-0002."),
    ]
    for change, message in cases:
        args = {
            "pieces": wipro_pieces[:1],
            "outcome": Outcome.REPLACED,
            "settled_on": TODAY,
            "to_location": loc(),
            **change,
        }
        with pytest.raises(DefectiveError, match=message):
            settle(batch=b, user=office_user, **args)
    settle(
        batch=b,
        pieces=wipro_pieces[:1],
        outcome=Outcome.REPAIRED,
        settled_on=TODAY,
        to_location=loc(),
        user=office_user,
    )
    with pytest.raises(DefectiveError, match="DEF-0001 is not waiting on the company"):
        settle(
            batch=b,
            pieces=wipro_pieces[:1],
            outcome=Outcome.REPAIRED,
            settled_on=TODAY,
            to_location=loc(),
            user=office_user,
        )


def test_store_matches_the_pieces_after_a_full_cycle(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    b = sent_batch(wipro_pieces, office_user)
    settle(
        batch=b,
        pieces=wipro_pieces[:1],
        outcome=Outcome.REPLACED,
        settled_on=TODAY,
        to_location=loc(),
        user=office_user,
    )
    settle(
        batch=b,
        pieces=wipro_pieces[1:2],
        outcome=Outcome.REJECTED_RETURNED,
        settled_on=TODAY,
        user=office_user,
    )
    settle(
        batch=b,
        pieces=wipro_pieces[2:],
        outcome=Outcome.REJECTED_SCRAPPED,
        settled_on=TODAY,
        user=office_user,
    )
    in_store = DefectivePiece.objects.filter(status__in=[PieceStatus.IN_STORE, PieceStatus.IN_BATCH]).count()
    assert qty(drv, store()) == in_store == 1 and balance_drift() == []
