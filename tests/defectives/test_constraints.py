"""Database guards on the defectives tables: a bad row is refused even if it skips the services."""

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.defectives.models import (
    BatchLine,
    BatchStatus,
    DefectivePiece,
    Outcome,
    PieceStatus,
    ReturnBatch,
    Source,
)
from apps.inventory.models import EntryKind, ServiceSubtype
from apps.inventory.services import Line, post_entry
from tests.factories import make_item, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def make_batch(user, number="RB-0001"):
    item = make_item(f"B-{number}")
    return ReturnBatch.objects.create(number=number, company=item.company, created_on=TODAY, created_by=user)


def make_piece(user, tag="DEF-0001", **extra):
    item = make_item(f"P-{tag}")
    return DefectivePiece.objects.create(
        tag=tag,
        item=item,
        company=item.company,
        source=Source.FOUND_IN_STOCK,
        collected_on=TODAY,
        created_by=user,
        **extra,
    )


def refused(queryset, **change):
    with pytest.raises(IntegrityError), transaction.atomic():
        queryset.update(**change)


def collect_into_store(item, user, **extra):
    return post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(item, store(), 1)],
        user=user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
        **extra,
    )


# --- BatchLine ---------------------------------------------------------------------------------------


def test_a_piece_has_one_open_batch_line(office_user):
    p = make_piece(office_user)
    b1, b2 = make_batch(office_user), make_batch(office_user, "RB-0002")
    BatchLine.objects.create(batch=b1, piece=p)
    with pytest.raises(IntegrityError), transaction.atomic():
        BatchLine.objects.create(batch=b2, piece=p)
    BatchLine.objects.filter(batch=b1).update(outcome=Outcome.REJECTED_RETURNED, settled_on=TODAY)
    BatchLine.objects.create(batch=b2, piece=p)  # the first answer is in, so it can go out again


def test_batch_line_outcome_and_date_go_together(office_user):
    BatchLine.objects.create(batch=make_batch(office_user), piece=make_piece(office_user))
    lines = BatchLine.objects.all()
    refused(lines, outcome=Outcome.REPLACED)
    refused(lines, settled_on=TODAY)
    lines.update(outcome=Outcome.REPLACED, settled_on=TODAY)


# --- DefectivePiece ----------------------------------------------------------------------------------


def test_piece_in_a_batch_exactly_when_its_status_says_so(office_user):
    b = make_batch(office_user)
    pieces = DefectivePiece.objects.filter(pk=make_piece(office_user).pk)
    refused(pieces, return_batch=b)  # in store, but pointing at a batch
    refused(pieces, status=PieceStatus.IN_BATCH)  # in a batch, but no batch
    refused(pieces, status=PieceStatus.SCRAPPED, return_batch=b)
    pieces.update(status=PieceStatus.IN_BATCH, return_batch=b)
    pieces.update(status=PieceStatus.SENT)
    refused(pieces, return_batch=None)


def test_settled_piece_needs_outcome_and_date(office_user):
    b = make_batch(office_user)
    pieces = DefectivePiece.objects.filter(
        pk=make_piece(office_user, status=PieceStatus.SENT, return_batch=b).pk
    )
    refused(pieces, status=PieceStatus.SETTLED)
    refused(pieces, status=PieceStatus.SETTLED, outcome=Outcome.REPLACED)
    refused(pieces, status=PieceStatus.SETTLED, settled_on=TODAY)
    pieces.update(status=PieceStatus.SETTLED, outcome=Outcome.REPLACED, settled_on=TODAY)


def test_replacement_entry_only_with_a_good_outcome(office_user):
    p = make_piece(office_user)
    entry = collect_into_store(p.item, office_user)
    pieces = DefectivePiece.objects.filter(pk=p.pk)
    refused(pieces, replacement_entry=entry)
    refused(pieces, replacement_entry=entry, outcome=Outcome.REJECTED_RETURNED)
    pieces.update(replacement_entry=entry, outcome=Outcome.REPAIRED)


def test_piece_status_must_be_known(office_user):
    refused(DefectivePiece.objects.filter(pk=make_piece(office_user).pk), status="LOST")


# --- ReturnBatch -------------------------------------------------------------------------------------


def test_dispatched_batch_has_date_and_entry(office_user):
    b = make_batch(office_user)
    entry = collect_into_store(make_item("Z1"), office_user)
    batches = ReturnBatch.objects.filter(pk=b.pk)
    refused(batches, status=BatchStatus.DISPATCHED)
    refused(batches, status=BatchStatus.DISPATCHED, dispatched_on=TODAY)
    refused(batches, status=BatchStatus.DISPATCHED, dispatch_entry=entry)
    refused(batches, dispatched_on=TODAY, dispatch_entry=entry)  # still a draft
    batches.update(status=BatchStatus.DISPATCHED, dispatched_on=TODAY, dispatch_entry=entry)


def test_batch_used_by_a_ledger_entry_cannot_be_deleted(office_user):
    b = make_batch(office_user)
    collect_into_store(make_item("Z2"), office_user, return_batch=b)
    with pytest.raises(ProtectedError):
        b.delete()


def test_batch_holding_a_piece_cannot_be_deleted(office_user):
    b = make_batch(office_user)
    make_piece(office_user, status=PieceStatus.IN_BATCH, return_batch=b)
    with pytest.raises(ProtectedError):
        b.delete()
