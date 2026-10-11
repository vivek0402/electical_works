import io
import threading
from datetime import date

import pytest
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.inventory.models import (
    Bucket,
    DocType,
    Item,
    Location,
    StockBalance,
    StockDocument,
    StockMovement,
)
from apps.inventory.services import (
    Line,
    StockError,
    balance_drift,
    post_document,
    rebuild_balances,
    reverse_document,
)

FRESH, DEFECTIVE = Bucket.FRESH, Bucket.DEFECTIVE
TODAY = date(2026, 5, 25)


@pytest.fixture
def office(db):
    return Location.objects.get(name="Vizag Office")


@pytest.fixture
def shop(db):
    return Location.objects.get(name="TV Shop")


@pytest.fixture
def pcb(db):
    return Item.objects.create(code="EIO6006", item_type="PCB")


def qty(item, location, bucket):
    row = StockBalance.objects.filter(item=item, location=location, bucket=bucket).first()
    return row.qty if row else 0


def post(doc_type, *lines, **kwargs):
    return post_document(doc_type=doc_type, doc_date=TODAY, lines=list(lines), **kwargs)


def test_opening_fills_each_bucket_separately(pcb, office):
    post(DocType.OPENING, Line(pcb, office, FRESH, 11), Line(pcb, office, DEFECTIVE, 7))
    assert qty(pcb, office, FRESH) == 11
    assert qty(pcb, office, DEFECTIVE) == 7


def test_lines_for_same_key_are_summed(pcb, office):
    # The fresh sample sheet lists EIO6006 twice (11 + 7).
    post(DocType.OPENING, Line(pcb, office, FRESH, 11), Line(pcb, office, FRESH, 7))
    assert qty(pcb, office, FRESH) == 18
    assert StockMovement.objects.count() == 2


def test_cannot_go_negative_with_friendly_message(pcb, office):
    post(DocType.OPENING, Line(pcb, office, FRESH, 7))
    with pytest.raises(StockError) as err:
        post(DocType.ISSUED_TO_COMPLAINT, Line(pcb, office, FRESH, -8))
    assert err.value.message == "Only 7 NOS of EIO6006 (Fresh) at Vizag Office."
    assert qty(pcb, office, FRESH) == 7
    assert StockDocument.objects.count() == 1  # nothing half-saved


def test_fresh_and_defective_do_not_mix(pcb, office):
    post(DocType.OPENING, Line(pcb, office, DEFECTIVE, 5))
    with pytest.raises(StockError, match="Only 0 NOS of EIO6006 \\(Fresh\\)"):
        post(DocType.ISSUED_TO_COMPLAINT, Line(pcb, office, FRESH, -1))


@pytest.mark.parametrize(
    "doc_type, bucket, sign, message",
    [
        (DocType.RECEIVED_FROM_WIPRO, DEFECTIVE, 1, "can only move Fresh"),
        (DocType.RECEIVED_FROM_WIPRO, FRESH, -1, "can only add"),
        (DocType.ISSUED_TO_COMPLAINT, FRESH, 1, "can only remove"),
        (DocType.DEFECTIVE_COLLECTED, FRESH, 1, "can only move Defective"),
        (DocType.RETURNED_TO_WIPRO, DEFECTIVE, 1, "can only remove"),
        (DocType.OPENING, FRESH, -1, "can only add"),
    ],
)
def test_sign_and_bucket_rules(pcb, office, doc_type, bucket, sign, message):
    with pytest.raises(StockError, match=message):
        post(doc_type, Line(pcb, office, bucket, 3 * sign), reason="x")


def test_each_movement_type_happy_path(pcb, office):
    post(DocType.OPENING, Line(pcb, office, FRESH, 10))
    post(DocType.RECEIVED_FROM_WIPRO, Line(pcb, office, FRESH, 5), ref_no="DC-77")
    post(DocType.ISSUED_TO_COMPLAINT, Line(pcb, office, FRESH, -4))
    post(DocType.DEFECTIVE_COLLECTED, Line(pcb, office, DEFECTIVE, 4))
    post(DocType.RETURNED_TO_WIPRO, Line(pcb, office, DEFECTIVE, -3))
    post(DocType.SCRAPPED, Line(pcb, office, DEFECTIVE, -1), reason="burnt")
    post(DocType.ADJUSTMENT, Line(pcb, office, FRESH, -1), reason="count correction")
    assert qty(pcb, office, FRESH) == 10
    assert qty(pcb, office, DEFECTIVE) == 0


def test_reason_required_for_adjustment_and_scrap(pcb, office):
    post(DocType.OPENING, Line(pcb, office, FRESH, 3))
    for doc_type in (DocType.ADJUSTMENT, DocType.SCRAPPED):
        with pytest.raises(StockError, match="reason is required"):
            post(doc_type, Line(pcb, office, FRESH, -1), reason="  ")


def test_transfer_moves_between_locations(pcb, office, shop):
    post(DocType.OPENING, Line(pcb, office, FRESH, 10))
    post(DocType.TRANSFER, Line(pcb, office, FRESH, -4), Line(pcb, shop, FRESH, 4))
    assert qty(pcb, office, FRESH) == 6
    assert qty(pcb, shop, FRESH) == 4


def test_transfer_must_balance_and_span_locations(pcb, office, shop):
    post(DocType.OPENING, Line(pcb, office, FRESH, 10))
    with pytest.raises(StockError, match="exactly what it puts in"):
        post(DocType.TRANSFER, Line(pcb, office, FRESH, -4), Line(pcb, shop, FRESH, 3))
    with pytest.raises(StockError, match="two different locations"):
        post(DocType.TRANSFER, Line(pcb, office, FRESH, -4), Line(pcb, office, FRESH, 4))


def test_transfer_cannot_overdraw_source(pcb, office, shop):
    post(DocType.OPENING, Line(pcb, office, FRESH, 2))
    with pytest.raises(StockError, match="Only 2 NOS"):
        post(DocType.TRANSFER, Line(pcb, office, FRESH, -3), Line(pcb, shop, FRESH, 3))
    assert qty(pcb, shop, FRESH) == 0


def test_zero_and_empty_lines_rejected(pcb, office):
    with pytest.raises(StockError, match="not zero"):
        post(DocType.OPENING, Line(pcb, office, FRESH, 0))
    with pytest.raises(StockError, match="at least one"):
        post(DocType.OPENING)


def test_reversal_restores_stock_and_keeps_both_documents(pcb, office):
    post(DocType.OPENING, Line(pcb, office, FRESH, 10))
    receipt = post(DocType.RECEIVED_FROM_WIPRO, Line(pcb, office, FRESH, 5), ref_no="DC-1")
    reversal = reverse_document(document=receipt, reason="wrong DC entered")
    assert qty(pcb, office, FRESH) == 10
    assert reversal.reverses == receipt
    assert reversal.doc_type == DocType.RECEIVED_FROM_WIPRO
    assert StockDocument.objects.count() == 3
    assert [m.qty for m in reversal.lines.all()] == [-5]


def test_reversal_rules(pcb, office):
    opening = post(DocType.OPENING, Line(pcb, office, FRESH, 10), ref_no="LEGACY-1")
    with pytest.raises(StockError, match="give a reason"):
        reverse_document(document=opening, reason="")
    reversal = reverse_document(document=opening, reason="re-import")
    with pytest.raises(StockError, match="already been reversed"):
        reverse_document(document=opening, reason="again")
    with pytest.raises(StockError, match="cannot itself be reversed"):
        reverse_document(document=reversal, reason="undo")


def test_reversal_cannot_drive_stock_negative(pcb, office):
    opening = post(DocType.OPENING, Line(pcb, office, FRESH, 5))
    post(DocType.ISSUED_TO_COMPLAINT, Line(pcb, office, FRESH, -3))
    with pytest.raises(StockError, match="Only 2 NOS"):
        reverse_document(document=opening, reason="mistake")


def test_opening_ref_is_unique(pcb, office):
    post(DocType.OPENING, Line(pcb, office, FRESH, 1), ref_no="LEGACY-2026-05-25")
    with pytest.raises(IntegrityError), transaction.atomic():
        post(DocType.OPENING, Line(pcb, office, FRESH, 1), ref_no="LEGACY-2026-05-25")


def test_rebuild_matches_cache_and_detects_drift(pcb, office, shop):
    post(DocType.OPENING, Line(pcb, office, FRESH, 10), Line(pcb, office, DEFECTIVE, 3))
    post(DocType.TRANSFER, Line(pcb, office, FRESH, -4), Line(pcb, shop, FRESH, 4))
    assert balance_drift() == []
    before = {(b.item_id, b.location_id, b.bucket): b.qty for b in StockBalance.objects.all()}

    StockBalance.objects.filter(location=shop).update(qty=99)  # simulate a corrupted cache
    assert len(balance_drift()) == 1
    out = io.StringIO()
    call_command("rebuild_stock_balances", "--fix", stdout=out)
    assert "Rebuilt 3 balance rows" in out.getvalue()
    after = {(b.item_id, b.location_id, b.bucket): b.qty for b in StockBalance.objects.all()}
    assert after == before
    assert rebuild_balances() == 3


def test_ledger_is_append_only_in_the_database(pcb, office):
    doc = post(DocType.OPENING, Line(pcb, office, FRESH, 5))
    move = doc.lines.get()
    for sql in (
        f"UPDATE {StockMovement._meta.db_table} SET qty = 50 WHERE id = %s",
        f"DELETE FROM {StockMovement._meta.db_table} WHERE id = %s",
    ):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, [move.pk])
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
        cur.execute(f"UPDATE {StockDocument._meta.db_table} SET ref_no='x' WHERE id = %s", [doc.pk])
    move.refresh_from_db()
    assert move.qty == 5


def test_balance_check_constraint_is_final_guard(pcb, office):
    post(DocType.OPENING, Line(pcb, office, FRESH, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        StockBalance.objects.filter(item=pcb).update(qty=-1)


@pytest.mark.django_db(transaction=True)
def test_concurrent_issues_cannot_oversell():
    item = Item.objects.create(code="EIO9326", item_type="PCB")
    office = Location.objects.get(name="Vizag Office")
    post(DocType.OPENING, Line(item, office, FRESH, 7))

    barrier = threading.Barrier(2)
    results = []

    def issue():
        try:
            barrier.wait()
            post(DocType.ISSUED_TO_COMPLAINT, Line(item, office, FRESH, -5))
            results.append("ok")
        except StockError:
            results.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=issue) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["ok", "refused"]
    assert qty(item, office, FRESH) == 2
