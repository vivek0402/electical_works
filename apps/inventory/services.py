"""All writes to items and stock. Views, forms and commands call these; nothing else touches the ledger."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from functools import reduce
from operator import or_

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import EntryCounter, EntryKind, Item, Location, StockBalance, StockEntry, StockLine


class StockError(ValidationError):
    """A stock rule was broken. The message is safe to show to staff as-is."""


@dataclass(frozen=True)
class Line:
    item: Item
    location: Location
    qty: int  # + into the location, - out of it
    batch_code: str = ""
    pkd: date | None = None


def _validate(kind, entry_date, lines, reason, note):
    if not lines:
        raise StockError("Add at least one item.")
    if entry_date > timezone.localdate():
        raise StockError("The date can't be in the future.")
    for line in lines:
        if not isinstance(line.qty, int) or line.qty == 0:
            raise StockError(f"Quantity for {line.item.code} must be a whole number, not zero.")
    label = EntryKind(kind).label
    if kind == EntryKind.IN and any(line.qty < 0 for line in lines):
        raise StockError(f"{label} can only add stock.")
    if kind == EntryKind.OUT and any(line.qty > 0 for line in lines):
        raise StockError(f"{label} can only remove stock.")
    if kind == EntryKind.TRF:
        net = defaultdict(int)
        for line in lines:
            net[line.item.pk] += line.qty
        if any(net.values()):
            raise StockError("A transfer must take out exactly what it puts in.")
        if len({line.location.pk for line in lines}) < 2:
            raise StockError("A transfer needs two different locations.")
    if kind == EntryKind.ADJ:
        if not reason:
            raise StockError("Choose the reason for the adjustment.")
        if not note.strip():
            raise StockError("Write a short note explaining the adjustment.")


def _lock_balances(keys):
    """Make sure balance rows exist, then lock them in a fixed order (avoids deadlocks)."""
    StockBalance.objects.bulk_create(
        [StockBalance(item_id=i, location_id=loc, qty=0) for i, loc in keys], ignore_conflicts=True
    )
    match = reduce(or_, (Q(item_id=i, location_id=loc) for i, loc in keys))
    rows = StockBalance.objects.select_for_update().filter(match).order_by("item_id", "location_id")
    return {(r.item_id, r.location_id): r for r in rows}


def _next_number(kind):
    counter = EntryCounter.objects.select_for_update().get(kind=kind)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"{kind}-{counter.last:04d}"


@transaction.atomic
def post_entry(
    *,
    kind,
    entry_date,
    lines,
    user,
    subtype="",
    party="",
    company=None,
    ref="",
    reason="",
    note="",
    reverses=None,
) -> StockEntry:
    """Post a stock entry.

    Raises StockError (and saves nothing) if a rule is broken or stock would go negative.
    """
    if kind != EntryKind.REV:
        _validate(kind, entry_date, lines, reason, note)
    deltas = defaultdict(int)
    for line in lines:
        deltas[(line.item.pk, line.location.pk)] += line.qty
    keys = sorted(deltas)
    balances = _lock_balances(keys)
    items = {line.item.pk: line.item for line in lines}
    places = {line.location.pk: line.location for line in lines}
    now = timezone.now()
    for key in keys:
        new_qty = balances[key].qty + deltas[key]
        if new_qty < 0:
            item, place = items[key[0]], places[key[1]]
            raise StockError(f"Only {balances[key].qty} {item.unit} of {item.code} at {place.name}.")
        balances[key].qty = new_qty
        balances[key].updated_at = now  # bulk_update does not apply auto_now
    entry = StockEntry.objects.create(
        number=_next_number(kind),
        kind=kind,
        subtype=subtype,
        entry_date=entry_date,
        party=party.strip(),
        company=company,
        ref=ref.strip(),
        reason=reason,
        note=note.strip(),
        reverses=reverses,
        created_by=user,
    )
    StockLine.objects.bulk_create(
        StockLine(
            entry=entry,
            item=line.item,
            location=line.location,
            qty=line.qty,
            batch_code=line.batch_code,
            pkd=line.pkd,
        )
        for line in lines
    )
    StockBalance.objects.bulk_update([balances[k] for k in keys], ["qty", "updated_at"])
    return entry


@transaction.atomic
def adjust_counts(*, entry_date, location, counts, reason, note, user) -> StockEntry:
    """Set the counted quantity for each (item, counted) at one location; posts only the differences."""
    if not reason:
        raise StockError("Choose the reason for the adjustment.")
    if not note.strip():
        raise StockError("Write a short note explaining the adjustment.")
    keys = sorted({(item.pk, location.pk) for item, _ in counts})
    if not keys:
        raise StockError("Add at least one item.")
    balances = _lock_balances(keys)
    lines = [Line(item, location, counted - balances[(item.pk, location.pk)].qty) for item, counted in counts]
    lines = [line for line in lines if line.qty]
    if not lines:
        raise StockError("The counted quantities match the system. Nothing to adjust.")
    return post_entry(
        kind=EntryKind.ADJ, entry_date=entry_date, lines=lines, user=user, reason=reason, note=note
    )


@transaction.atomic
def undo_entry(*, entry, reason, user, entry_date=None) -> StockEntry:
    """Cancel an entry by posting its exact opposite. Both stay on record."""
    entry = StockEntry.objects.select_for_update().get(pk=entry.pk)
    if entry.kind == EntryKind.REV:
        raise StockError("An undo can't be undone. Make a new entry instead.")
    if StockEntry.objects.filter(reverses=entry).exists():
        raise StockError("This entry was already undone.")
    if not reason.strip():
        raise StockError("Please give a reason.")
    lines = [
        Line(line.item, line.location, -line.qty, line.batch_code, line.pkd)
        for line in entry.lines.select_related("item", "location")
    ]
    try:
        return post_entry(
            kind=EntryKind.REV,
            entry_date=entry_date or timezone.localdate(),
            lines=lines,
            user=user,
            party=entry.party,
            ref=entry.ref,
            note=reason,
            reverses=entry,
        )
    except StockError as exc:
        raise StockError(
            f"{exc.message} That stock has already been used, so this entry can't be undone."
        ) from exc


@transaction.atomic
def rebuild_balances() -> int:
    """Recompute the StockBalance cache from the ledger. Returns the number of rows."""
    with connection.cursor() as cursor:
        cursor.execute(f"LOCK TABLE {StockBalance._meta.db_table} IN EXCLUSIVE MODE")
    StockBalance.objects.all().delete()
    totals = list(StockLine.objects.values("item_id", "location_id").annotate(total=Sum("qty")))
    StockBalance.objects.bulk_create(
        StockBalance(item_id=t["item_id"], location_id=t["location_id"], qty=t["total"]) for t in totals
    )
    return len(totals)


def balance_drift():
    """[(item_id, location_id, cached, ledger)] where the cache disagrees with the ledger."""
    ledger = {
        (t["item_id"], t["location_id"]): t["total"]
        for t in StockLine.objects.values("item_id", "location_id").annotate(total=Sum("qty"))
    }
    cached = {(b.item_id, b.location_id): b.qty for b in StockBalance.objects.all()}
    return [
        (*key, cached.get(key, 0), ledger.get(key, 0))
        for key in sorted(set(ledger) | set(cached))
        if cached.get(key, 0) != ledger.get(key, 0)
    ]
