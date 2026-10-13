import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.inventory.models import AdjustReason, EntryKind, Location, ServiceSubtype, StockEntry
from apps.inventory.services import Line, StockError, post_entry, undo_entry
from tests.factories import loc, make_item, make_user, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def user(db):
    return make_user("clerk", "OFFICE")


@pytest.fixture
def drv(db):
    return make_item("LG78-150-700")


def post(kind, *lines, user, **kw):
    return post_entry(kind=kind, entry_date=TODAY, lines=list(lines), user=user, **kw)


def stock(item, qty, user):
    return post(EntryKind.IN, Line(item, loc(), qty), user=user, subtype="SUPPLIER")


def collect(item, qty, user):
    return post(EntryKind.IN, Line(item, store(), qty), user=user, subtype=ServiceSubtype.DEFECTIVE_COLLECTED)


def test_migration_creates_one_active_defective_store():
    s = Location.defective_store()
    assert s.name == "Defective store" and s.is_active
    assert list(Location.objects.filter(is_defective_store=True)) == [s]
    assert s not in Location.objects.good()
    assert set(Location.objects.good().values_list("name", flat=True)) == {
        "Vizag Office",
        "Svkml",
        "TV Shop",
        "Kartika Class",
    }


def test_only_one_defective_store():
    with pytest.raises(IntegrityError), transaction.atomic():
        Location.objects.create(name="Second store", is_defective_store=True)


def test_collection_and_dispatch_post_at_the_store(drv, user):
    e = collect(drv, 2, user)
    assert e.details == "Failed parts collected at site" and e.is_defective
    e.refresh_from_db()
    assert e.subtype == "DEFECTIVE_COLLECTED"  # 19 characters fit
    out = post(EntryKind.OUT, Line(drv, store(), -2), user=user, subtype=ServiceSubtype.RETURN_TO_COMPANY)
    assert out.details == "Defectives returned to company" and out.is_defective


def test_store_subtype_refused_at_a_good_location(drv, user):
    with pytest.raises(StockError, match="must be posted at the Defective store"):
        post(EntryKind.IN, Line(drv, loc(), 1), user=user, subtype=ServiceSubtype.DEFECTIVE_COLLECTED)


def test_ordinary_entries_cannot_touch_the_store(drv, user):
    with pytest.raises(StockError, match="managed from the Defectives screens"):
        post(EntryKind.IN, Line(drv, store(), 1), user=user, subtype="SUPPLIER")
    stock(drv, 3, user)
    with pytest.raises(StockError, match="managed from the Defectives screens"):
        post(EntryKind.TRF, Line(drv, loc(), -1), Line(drv, store(), 1), user=user)


def test_mark_defective_is_a_transfer_into_the_store(drv, user):
    stock(drv, 3, user)
    e = post(
        EntryKind.TRF,
        Line(drv, loc(), -1),
        Line(drv, store(), 1),
        user=user,
        subtype=ServiceSubtype.MARK_DEFECTIVE,
    )
    assert e.details == "Marked defective" and e.is_defective
    with pytest.raises(StockError, match="from a good location into the Defective store"):
        post(
            EntryKind.TRF,
            Line(drv, loc(), -1),
            Line(drv, loc("TV Shop"), 1),
            user=user,
            subtype=ServiceSubtype.MARK_DEFECTIVE,
        )


def test_service_subtype_must_match_the_kind(drv, user):
    with pytest.raises(StockError, match="Choose where the stock came from"):
        post(EntryKind.IN, Line(drv, loc(), 1), user=user, subtype=ServiceSubtype.COMPLAINT)
    with pytest.raises(StockError, match="don't take a type"):
        post(
            EntryKind.ADJ,
            Line(drv, loc(), 1),
            user=user,
            subtype=ServiceSubtype.MARK_DEFECTIVE,
            reason=AdjustReason.FOUND,
            note="x",
        )


def test_scrap_is_an_adjustment_at_the_store(drv, user):
    collect(drv, 1, user)
    e = post(
        EntryKind.ADJ,
        Line(drv, store(), -1),
        user=user,
        subtype=ServiceSubtype.SCRAP_DEFECTIVE,
        reason=AdjustReason.DAMAGED,
        note="Scrapped DEF-0001",
    )
    assert e.details == "Defective pieces scrapped" and e.is_defective


def test_complaint_out_is_ordinary_and_can_be_undone(drv, user):
    stock(drv, 3, user)
    e = post(
        EntryKind.OUT,
        Line(drv, loc(), -1),
        user=user,
        subtype=ServiceSubtype.COMPLAINT,
        party="BARC, Visakhapatnam",
    )
    assert e.details == "Parts given at complaint visit" and not e.is_defective
    assert undo_entry(entry=e, reason="typed twice", user=user).kind == EntryKind.REV


def test_replacement_in_goes_to_good_stock(drv, user):
    e = post(EntryKind.IN, Line(drv, loc(), 1), user=user, subtype=ServiceSubtype.REPLACEMENT)
    assert e.details == "Replacement / repaired piece from company" and e.is_defective


def test_defective_entries_cannot_be_undone(drv, user):
    e = collect(drv, 1, user)
    with pytest.raises(StockError, match="Use the Defectives screens instead of Undo"):
        undo_entry(entry=e, reason="oops", user=user)
    assert not StockEntry.objects.filter(kind=EntryKind.REV).exists()


def test_entry_page_hides_undo_for_defective_entries(office_client, office_user, drv):
    e = collect(drv, 1, office_user)
    html = office_client.get(f"/entries/{e.number}/").content.decode()
    assert "Undo this entry" not in html and "belongs to the defective pieces" in html
    assert office_client.post(f"/entries/{e.number}/undo/", {"reason": "x"}).status_code == 302
    assert not StockEntry.objects.filter(kind=EntryKind.REV).exists()
