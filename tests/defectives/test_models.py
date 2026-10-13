import pytest
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.defectives.models import (
    TRANSITIONS,
    BatchLine,
    DefectiveEvent,
    DefectivePiece,
    PieceStatus,
    ReturnBatch,
    Source,
)
from apps.inventory.models import Company, EntryKind, ServiceSubtype
from apps.inventory.services import Line, post_entry
from tests.factories import make_item, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def make_batch(user, number="RB-0001"):
    company = Company.objects.get(name="Wipro Lighting")
    return ReturnBatch.objects.create(number=number, company=company, created_on=TODAY, created_by=user)


def make_piece(user, item, tag="DEF-0001"):
    return DefectivePiece.objects.create(
        tag=tag,
        item=item,
        company=item.company,
        source=Source.FOUND_IN_STOCK,
        collected_on=TODAY,
        created_by=user,
    )


def test_piece_defaults(office_user):
    p = make_piece(office_user, make_item("LG78-150-700"))
    assert str(p) == "DEF-0001" and p.status == PieceStatus.IN_STORE and p.outcome == ""
    assert p.company.name == "Wipro Lighting" and p.return_batch is None


def test_transitions_end_at_settled_and_scrapped():
    assert TRANSITIONS[PieceStatus.SETTLED] == set() and TRANSITIONS[PieceStatus.SCRAPPED] == set()
    assert TRANSITIONS[PieceStatus.SENT] == {PieceStatus.SETTLED, PieceStatus.IN_STORE}


def test_a_piece_is_in_a_batch_only_once(office_user):
    b, p = make_batch(office_user), make_piece(office_user, make_item("X1"))
    BatchLine.objects.create(batch=b, piece=p)
    with pytest.raises(IntegrityError), transaction.atomic():
        BatchLine.objects.create(batch=b, piece=p)


def test_piece_events_are_append_only(office_user):
    p = make_piece(office_user, make_item("X2"))
    ev = DefectiveEvent.objects.create(piece=p, to_status=PieceStatus.IN_STORE, at=TODAY, by=office_user)
    with pytest.raises(DatabaseError), transaction.atomic():
        DefectiveEvent.objects.filter(pk=ev.pk).update(note="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        ev.delete()


def test_ledger_entry_links_to_its_return_batch(office_user):
    b, item = make_batch(office_user), make_item("X3")
    post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(item, store(), 1)],
        user=office_user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
    )
    e = post_entry(
        kind=EntryKind.OUT,
        entry_date=TODAY,
        lines=[Line(item, store(), -1)],
        user=office_user,
        subtype=ServiceSubtype.RETURN_TO_COMPANY,
        return_batch=b,
    )
    assert e.return_batch == b and list(b.entries.all()) == [e]
