import datetime
import io
import threading

import pytest
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from apps.inventory.models import AdjustReason, EntryKind, StockBalance, StockEntry, StockLine
from apps.inventory.services import Line, StockError, adjust_counts, balance_drift, post_entry, undo_entry
from tests.factories import loc, make_item, make_user

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def user(db):
    return make_user("clerk", "OFFICE")


@pytest.fixture
def pcb(db):
    return make_item("EIO6006", spare_type="PCB / LED module")


def qty(item, name="Vizag Office"):
    row = StockBalance.objects.filter(item=item, location=loc(name)).first()
    return row.qty if row else 0


def post(kind, *lines, user, **kw):
    return post_entry(kind=kind, entry_date=TODAY, lines=list(lines), user=user, **kw)


def test_stock_in_and_numbering(pcb, user):
    first = post(EntryKind.IN, Line(pcb, loc(), 11), user=user, subtype="OPENING")
    second = post(EntryKind.IN, Line(pcb, loc(), 7), user=user, subtype="SUPPLIER")
    assert (first.number, second.number) == ("IN-0001", "IN-0002")
    assert qty(pcb) == 18


def test_out_cannot_go_negative_and_saves_nothing(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 7), user=user)
    with pytest.raises(StockError) as err:
        post(EntryKind.OUT, Line(pcb, loc(), -8), user=user)
    assert err.value.message == "Only 7 NOS of EIO6006 at Vizag Office."
    assert qty(pcb) == 7 and StockEntry.objects.count() == 1


def test_unit_appears_in_message(user):
    wire = make_item("WIRE 1.5 SQMM", unit="MTR", spare_type="Wire / cable")
    post(EntryKind.IN, Line(wire, loc(), 40), user=user)
    with pytest.raises(StockError, match="Only 40 MTR of WIRE 1.5 SQMM at Vizag Office."):
        post(EntryKind.OUT, Line(wire, loc(), -50), user=user)


@pytest.mark.parametrize(
    "kind, sign, message",
    [
        (EntryKind.IN, -1, "Stock IN can only add"),
        (EntryKind.OUT, 1, "Stock OUT can only remove"),
    ],
)
def test_sign_rules(pcb, user, kind, sign, message):
    with pytest.raises(StockError, match=message):
        post(kind, Line(pcb, loc(), 3 * sign), user=user)


def test_future_date_refused(pcb, user):
    with pytest.raises(StockError, match="future"):
        post_entry(
            kind=EntryKind.IN,
            entry_date=TODAY + datetime.timedelta(days=1),
            lines=[Line(pcb, loc(), 1)],
            user=user,
        )


def test_transfer_rules(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="exactly what it puts in"):
        post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 3), user=user)
    with pytest.raises(StockError, match="two different locations"):
        post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc(), 4), user=user)
    post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4), user=user)
    assert (qty(pcb), qty(pcb, "TV Shop")) == (6, 4)


def test_adjust_counts_needs_reason_and_note(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="reason"):
        adjust_counts(entry_date=TODAY, location=loc(), counts=[(pcb, 9)], reason="", note="x", user=user)
    with pytest.raises(StockError, match="note"):
        adjust_counts(
            entry_date=TODAY,
            location=loc(),
            counts=[(pcb, 9)],
            reason=AdjustReason.DAMAGED,
            note=" ",
            user=user,
        )
    with pytest.raises(StockError, match="match the system"):
        adjust_counts(
            entry_date=TODAY,
            location=loc(),
            counts=[(pcb, 10)],
            reason=AdjustReason.COUNT,
            note="ok",
            user=user,
        )
    entry = adjust_counts(
        entry_date=TODAY,
        location=loc(),
        counts=[(pcb, 9)],
        reason=AdjustReason.DAMAGED,
        note="1 cracked",
        user=user,
    )
    assert entry.number == "ADJ-0001" and qty(pcb) == 9 and entry.lines.get().qty == -1


def test_undo_rules(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    with pytest.raises(StockError, match="reason"):
        undo_entry(entry=receipt, reason=" ", user=user)
    rev = undo_entry(entry=receipt, reason="wrong item", user=user)
    assert rev.number == "REV-0001" and rev.reverses == receipt and qty(pcb) == 0
    assert receipt.reversed_by == rev
    with pytest.raises(StockError, match="already undone"):
        undo_entry(entry=receipt, reason="again", user=user)
    with pytest.raises(StockError, match="can't be undone"):
        undo_entry(entry=rev, reason="x", user=user)


def test_undo_refused_when_stock_already_used(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    post(EntryKind.OUT, Line(pcb, loc(), -3), user=user)
    with pytest.raises(StockError, match="already been used"):
        undo_entry(entry=receipt, reason="mistake", user=user)


def test_ledger_is_append_only(pcb, user):
    entry = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    line = entry.lines.get()
    for sql, pk in [
        (f"UPDATE {StockLine._meta.db_table} SET qty = 50 WHERE id = %s", line.pk),
        (f"DELETE FROM {StockLine._meta.db_table} WHERE id = %s", line.pk),
        (f"UPDATE {StockEntry._meta.db_table} SET ref = 'x' WHERE id = %s", entry.pk),
    ]:
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, [pk])


def test_balance_check_constraint(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 1), user=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        StockBalance.objects.filter(item=pcb).update(qty=-1)


def test_rebuild_matches_cache(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4), user=user)
    assert balance_drift() == []
    StockBalance.objects.filter(location=loc("TV Shop")).update(qty=99)
    assert len(balance_drift()) == 1
    out = io.StringIO()
    call_command("rebuild_stock_balances", "--fix", stdout=out)
    assert "Rebuilt" in out.getvalue() and balance_drift() == [] and qty(pcb, "TV Shop") == 4


@pytest.mark.django_db(transaction=True)
def test_two_people_cannot_oversell():
    clerk = make_user("clerk2", "OFFICE")
    item = make_item("EIO9326", spare_type="PCB / LED module")
    post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(item, loc(), 7)], user=clerk)
    barrier, results = threading.Barrier(2), []

    def issue():
        try:
            barrier.wait()
            post_entry(kind=EntryKind.OUT, entry_date=TODAY, lines=[Line(item, loc(), -5)], user=clerk)
            results.append("ok")
        except StockError:
            results.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=issue) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "refused"]
    assert StockBalance.objects.get(item=item).qty == 2
