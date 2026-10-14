import datetime
import io
import threading

import pytest
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from apps.inventory.models import AdjustReason, EntryKind, StockBalance, StockEntry, StockLine
from apps.inventory.services import (
    Line,
    StockError,
    adjust_counts,
    balance_drift,
    lock_balances,
    post_entry,
    undo_entry,
)
from tests.factories import loc, make_item, make_user

pytestmark = pytest.mark.django_db


def today():
    return timezone.localdate()


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
    return post_entry(kind=kind, entry_date=today(), lines=list(lines), user=user, **kw)


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


def test_refused_out_does_not_use_a_number(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 7), user=user)
    with pytest.raises(StockError):
        post(EntryKind.OUT, Line(pcb, loc(), -8), user=user)
    assert post(EntryKind.OUT, Line(pcb, loc(), -2), user=user).number == "OUT-0001"


def test_refused_undo_does_not_use_a_number(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    post(EntryKind.OUT, Line(pcb, loc(), -3), user=user)
    with pytest.raises(StockError, match="already been used"):
        undo_entry(entry=receipt, reason="mistake", user=user)
    second = post(EntryKind.IN, Line(pcb, loc(), 2), user=user)
    assert undo_entry(entry=second, reason="typo", user=user).number == "REV-0001"


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
            entry_date=today() + datetime.timedelta(days=1),
            lines=[Line(pcb, loc(), 1)],
            user=user,
        )


@pytest.mark.parametrize("bad", [True, 1.5, "3", 0])
def test_quantity_must_be_whole_nonzero(pcb, user, bad):
    with pytest.raises(StockError, match="whole number, not zero"):
        post(EntryKind.IN, Line(pcb, loc(), bad), user=user)


@pytest.mark.parametrize("kind", [EntryKind.IN, EntryKind.REV])
def test_empty_lines_refused(user, kind):
    receipt = None
    if kind == EntryKind.REV:
        item = make_item("EIO1111")
        receipt = post(EntryKind.IN, Line(item, loc(), 1), user=user)
    with pytest.raises(StockError, match="Add at least one item."):
        post(kind, user=user, reverses=receipt)


def test_reverses_only_with_rev(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    with pytest.raises(StockError):
        post(EntryKind.REV, Line(pcb, loc(), -5), user=user)
    with pytest.raises(StockError):
        post(EntryKind.OUT, Line(pcb, loc(), -5), user=user, reverses=receipt)
    assert StockEntry.objects.count() == 1


def test_rev_still_checks_date_and_qty(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    with pytest.raises(StockError, match="future"):
        post_entry(
            kind=EntryKind.REV,
            entry_date=today() + datetime.timedelta(days=1),
            lines=[Line(pcb, loc(), -5)],
            user=user,
            reverses=receipt,
        )
    with pytest.raises(StockError, match="whole number"):
        post(EntryKind.REV, Line(pcb, loc(), 0), user=user, reverses=receipt)


@pytest.mark.parametrize(
    "kind, qty_, kw",
    [
        ("XX", 1, {}),
        (EntryKind.IN, 1, {"subtype": "SITE"}),
        (EntryKind.OUT, -1, {"subtype": "SUPPLIER"}),
        (EntryKind.IN, 1, {"reason": AdjustReason.DAMAGED}),
        (EntryKind.ADJ, -1, {"reason": "BROKEN", "note": "x"}),
        (EntryKind.ADJ, -1, {"reason": AdjustReason.LOST, "note": "x", "subtype": "SITE"}),
    ],
)
def test_kind_subtype_and_reason_validated(pcb, user, kind, qty_, kw):
    post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    with pytest.raises(StockError):
        post(kind, Line(pcb, loc(), qty_), user=user, **kw)
    assert StockEntry.objects.count() == 1


def test_inactive_item_and_location_refused(pcb, user):
    pcb.is_active = False
    pcb.save()
    with pytest.raises(StockError, match="EIO6006 is inactive."):
        post(EntryKind.IN, Line(pcb, loc(), 1), user=user)
    other = make_item("EIO2222")
    shop = loc("TV Shop")
    shop.is_active = False
    shop.save()
    with pytest.raises(StockError, match="TV Shop is inactive."):
        post(EntryKind.IN, Line(other, shop, 1), user=user)


def test_undo_allowed_after_item_goes_inactive(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    pcb.is_active = False
    pcb.save()
    rev = undo_entry(entry=receipt, reason="wrong item", user=user)
    assert rev.number == "REV-0001" and qty(pcb) == 0


def test_transfer_rules(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="exactly what it puts in"):
        post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 3), user=user)
    with pytest.raises(StockError, match="two different locations"):
        post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc(), 4), user=user)
    post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4), user=user)
    assert (qty(pcb), qty(pcb, "TV Shop")) == (6, 4)


def test_undo_transfer(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    move = post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4), user=user)
    undo_entry(entry=move, reason="wrong shop", user=user)
    assert (qty(pcb), qty(pcb, "TV Shop")) == (10, 0)


def test_undo_transfer_refused_when_used_at_destination(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    move = post(EntryKind.TRF, Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4), user=user)
    post(EntryKind.OUT, Line(pcb, loc("TV Shop"), -3), user=user)
    with pytest.raises(StockError, match="already been used"):
        undo_entry(entry=move, reason="wrong shop", user=user)
    assert (qty(pcb), qty(pcb, "TV Shop")) == (6, 1)


def test_adjust_counts_needs_reason_and_note(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="reason"):
        adjust_counts(entry_date=today(), location=loc(), counts=[(pcb, 9)], reason="", note="x", user=user)
    with pytest.raises(StockError, match="note"):
        adjust_counts(
            entry_date=today(),
            location=loc(),
            counts=[(pcb, 9)],
            reason=AdjustReason.DAMAGED,
            note=" ",
            user=user,
        )
    with pytest.raises(StockError, match="match the system"):
        adjust_counts(
            entry_date=today(),
            location=loc(),
            counts=[(pcb, 10)],
            reason=AdjustReason.COUNT,
            note="ok",
            user=user,
        )
    entry = adjust_counts(
        entry_date=today(),
        location=loc(),
        counts=[(pcb, 9)],
        reason=AdjustReason.DAMAGED,
        note="1 cracked",
        user=user,
    )
    assert entry.number == "ADJ-0001" and qty(pcb) == 9 and entry.lines.get().qty == -1


def test_adjust_counts_refuses_duplicate_item(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="EIO6006 is listed twice."):
        adjust_counts(
            entry_date=today(),
            location=loc(),
            counts=[(pcb, 9), (pcb, 8)],
            reason=AdjustReason.COUNT,
            note="recount",
            user=user,
        )
    assert qty(pcb) == 10


@pytest.mark.parametrize("bad", [-1, True, 2.5, "9"])
def test_adjust_counts_refuses_bad_count(pcb, user, bad):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="Counted quantity for EIO6006 must be a whole number, 0 or more."):
        adjust_counts(
            entry_date=today(),
            location=loc(),
            counts=[(pcb, bad)],
            reason=AdjustReason.COUNT,
            note="recount",
            user=user,
        )
    assert qty(pcb) == 10


def test_undo_rules(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user, company=pcb.company)
    with pytest.raises(StockError, match="reason"):
        undo_entry(entry=receipt, reason=" ", user=user)
    rev = undo_entry(entry=receipt, reason="wrong item", user=user)
    assert rev.number == "REV-0001" and rev.reverses == receipt and qty(pcb) == 0
    assert rev.company == receipt.company
    assert receipt.reversed_by == rev
    with pytest.raises(StockError, match="already undone"):
        undo_entry(entry=receipt, reason="again", user=user)
    with pytest.raises(StockError, match="can't be undone"):
        undo_entry(entry=rev, reason="x", user=user)


def test_undo_cannot_be_dated_before_entry(pcb, user):
    receipt = post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    with pytest.raises(StockError, match="The undo can't be dated before the entry it cancels."):
        undo_entry(entry=receipt, reason="x", user=user, entry_date=today() - datetime.timedelta(days=1))


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
        (f"DELETE FROM {StockEntry._meta.db_table} WHERE id = %s", entry.pk),
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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_people_cannot_oversell():
    clerk = make_user("clerk2", "OFFICE")
    item = make_item("EIO9326", spare_type="PCB / LED module")
    post_entry(kind=EntryKind.IN, entry_date=today(), lines=[Line(item, loc(), 7)], user=clerk)
    barrier, results = threading.Barrier(2), []

    def issue():
        try:
            barrier.wait()
            post_entry(kind=EntryKind.OUT, entry_date=today(), lines=[Line(item, loc(), -5)], user=clerk)
            results.append("ok")
        except StockError:
            results.append("refused")
        except Exception as exc:  # recorded so a failure can be diagnosed
            results.append(repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=issue) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "refused"]
    assert StockBalance.objects.get(item=item).qty == 2


def days_ago(n):
    return today() - datetime.timedelta(days=n)


def test_backdated_out_before_stock_arrived_refused(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError) as err:
        post_entry(kind=EntryKind.OUT, entry_date=days_ago(20), lines=[Line(pcb, loc(), -6)], user=user)
    assert err.value.message == f"Only 0 NOS of EIO6006 at Vizag Office on {days_ago(20):%d-%m-%Y}."
    assert qty(pcb) == 10 and StockEntry.objects.count() == 1


def test_backdated_out_after_stock_arrived_allowed(pcb, user):
    post_entry(kind=EntryKind.IN, entry_date=days_ago(20), lines=[Line(pcb, loc(), 10)], user=user)
    post_entry(kind=EntryKind.OUT, entry_date=days_ago(10), lines=[Line(pcb, loc(), -6)], user=user)
    assert qty(pcb) == 4


def test_backdated_out_that_breaks_a_later_point_refused(pcb, user):
    # 10 in on day -20, 8 out on day -5, 5 in today: today's balance is 7.
    post_entry(kind=EntryKind.IN, entry_date=days_ago(20), lines=[Line(pcb, loc(), 10)], user=user)
    post_entry(kind=EntryKind.OUT, entry_date=days_ago(5), lines=[Line(pcb, loc(), -8)], user=user)
    post(EntryKind.IN, Line(pcb, loc(), 5), user=user)
    # 6 out on day -10 fits then (10 on hand) and today (7), but day -5 would drop to -4.
    with pytest.raises(StockError) as err:
        post_entry(kind=EntryKind.OUT, entry_date=days_ago(10), lines=[Line(pcb, loc(), -6)], user=user)
    assert err.value.message == f"Only 2 NOS of EIO6006 at Vizag Office on {days_ago(5):%d-%m-%Y}."
    assert qty(pcb) == 7
    # 2 out on day -10 keeps every point at 0 or more.
    post_entry(kind=EntryKind.OUT, entry_date=days_ago(10), lines=[Line(pcb, loc(), -2)], user=user)
    assert qty(pcb) == 5


def test_backdated_transfer_checks_the_source_history(pcb, user):
    post(EntryKind.IN, Line(pcb, loc(), 10), user=user)
    with pytest.raises(StockError, match="on "):
        post_entry(
            kind=EntryKind.TRF,
            entry_date=days_ago(3),
            lines=[Line(pcb, loc(), -4), Line(pcb, loc("TV Shop"), 4)],
            user=user,
        )


def test_post_entry_with_locked_balances_must_cover_every_row(pcb, user):
    """locked= (from lock_balances) skips re-locking, so it must name every balance row the entry touches."""
    with transaction.atomic():
        locked = lock_balances([Line(pcb, loc(), 4)])
        post(EntryKind.IN, Line(pcb, loc(), 4), user=user, subtype="SUPPLIER", locked=locked)
        assert qty(pcb) == 4
        with pytest.raises(ValueError, match="must cover every balance row"):
            post(EntryKind.IN, Line(pcb, loc("TV Shop"), 1), user=user, subtype="SUPPLIER", locked=locked)
        with pytest.raises(ValueError, match="must cover every balance row"):
            post(
                EntryKind.IN, Line(pcb, loc(), 1), user=user, subtype="SUPPLIER", locked={(pcb.pk, loc().pk)}
            )
    assert balance_drift() == []
