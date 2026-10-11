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

from .models import (
    AdjustReason,
    EntryCounter,
    EntryKind,
    InSource,
    Item,
    ItemAlias,
    Location,
    OutTarget,
    StockBalance,
    StockEntry,
    StockLine,
)
from .normalise import normalise_code, search_key


class StockError(ValidationError):
    """A stock rule was broken. The message is safe to show to staff as-is."""


class NotEnoughStock(StockError):
    """Posting would take a balance below zero."""


@dataclass(frozen=True)
class Line:
    item: Item
    location: Location
    qty: int  # + into the location, - out of it
    batch_code: str = ""
    pkd: date | None = None


def _is_whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate(*, kind, entry_date, lines, subtype, reason, note, reverses):
    if kind not in EntryKind.values:
        raise StockError("Unknown entry kind.")
    if kind == EntryKind.REV and reverses is None:
        raise StockError("An undo must name the entry it cancels.")
    if kind != EntryKind.REV and reverses is not None:
        raise StockError("Only an undo can cancel another entry.")

    # Common checks, for every kind (including REV).
    if not lines:
        raise StockError("Add at least one item.")
    if entry_date > timezone.localdate():
        raise StockError("The date can't be in the future.")
    for line in lines:
        if not _is_whole(line.qty) or line.qty == 0:
            raise StockError(f"Quantity for {line.item.code} must be a whole number, not zero.")
    if kind == EntryKind.REV:
        return  # an undo mirrors an existing entry, so the rules below do not apply to it

    # Kind-specific checks for new entries.
    if kind == EntryKind.IN:
        if subtype and subtype not in InSource.values:
            raise StockError("Choose where the stock came from.")
    elif kind == EntryKind.OUT:
        if subtype and subtype not in OutTarget.values:
            raise StockError("Choose who the stock was issued to.")
    elif subtype:
        raise StockError(f"{EntryKind(kind).label} entries don't take a type.")
    if kind != EntryKind.ADJ and reason:
        raise StockError("Only an adjustment takes a reason.")

    inactive_item = Item.objects.filter(pk__in={line.item.pk for line in lines}, is_active=False).first()
    if inactive_item:
        raise StockError(f"{inactive_item.code} is inactive.")
    inactive_place = Location.objects.filter(
        pk__in={line.location.pk for line in lines}, is_active=False
    ).first()
    if inactive_place:
        raise StockError(f"{inactive_place.name} is inactive.")

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
        if reason not in AdjustReason.values:
            raise StockError("Choose a valid reason for the adjustment.")
        if not note.strip():
            raise StockError("Write a short note explaining the adjustment.")


def _lock_balances(keys):
    """Make sure balance rows exist, then lock them in a fixed order (avoids deadlocks)."""
    if not keys:
        return {}
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
    _validate(
        kind=kind,
        entry_date=entry_date,
        lines=lines,
        subtype=subtype,
        reason=reason,
        note=note,
        reverses=reverses,
    )
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
            raise NotEnoughStock(f"Only {balances[key].qty} {item.unit} of {item.code} at {place.name}.")
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
    if not counts:
        raise StockError("Add at least one item.")
    seen = set()
    for item, counted in counts:
        if item.pk in seen:
            raise StockError(f"{item.code} is listed twice.")
        seen.add(item.pk)
        if not _is_whole(counted) or counted < 0:
            raise StockError(f"Counted quantity for {item.code} must be a whole number, 0 or more.")
    keys = sorted((item.pk, location.pk) for item, _ in counts)
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
    entry_date = entry_date or timezone.localdate()
    if entry_date < entry.entry_date:
        raise StockError("The undo can't be dated before the entry it cancels.")
    lines = [
        Line(line.item, line.location, -line.qty, line.batch_code, line.pkd)
        for line in entry.lines.select_related("item", "location")
    ]
    try:
        return post_entry(
            kind=EntryKind.REV,
            entry_date=entry_date,
            lines=lines,
            user=user,
            party=entry.party,
            company=entry.company,
            ref=entry.ref,
            note=reason,
            reverses=entry,
        )
    except NotEnoughStock as exc:
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


class ItemError(ValidationError):
    """An item rule was broken. The message is safe to show to staff as-is."""


def find_item_by_code(text, exclude=None):
    """Exact code, then a stored other spelling, then a look-alike code (O/0, I/1, hyphens, leading zeros)."""
    code, key = normalise_code(text), search_key(text)
    if not code:
        return None
    items = Item.objects.exclude(pk=exclude.pk) if exclude else Item.objects.all()
    aliases = ItemAlias.objects.exclude(item=exclude) if exclude else ItemAlias.objects.all()
    hit = items.filter(code=code).first()
    if hit:
        return hit
    alias = aliases.filter(alias=code).select_related("item").first() or (
        aliases.filter(search_key=key).select_related("item").first() if key else None
    )
    if alias:
        return alias.item
    return items.filter(search_key=key).first() if key else None


@transaction.atomic
def save_item(*, data, item=None) -> Item:
    """Create (item=None) or update an item from cleaned form data. Raises ItemError (friendly message)."""
    code = normalise_code(data["code"])
    if not code:
        raise ItemError("Item code is required.")
    if not search_key(code):
        raise ItemError("Item code must contain at least one letter or number.")
    clash = find_item_by_code(code, exclude=item)
    if clash:
        raise ItemError(
            f"{code} already exists."
            if clash.code == code
            else f"{code} looks the same as {clash.code}. Use that item instead."
        )
    if item and item.code != code and item.lines.exists():
        raise ItemError(
            "This item already has stock entries, so its code can't be changed. "
            "Add the new spelling under 'Other spellings'."
        )
    aliases = []
    for raw in data.get("aliases", []):
        alias = normalise_code(raw)
        if not alias or alias == code or alias in aliases:
            continue
        if not search_key(alias):
            raise ItemError(f"Other spelling {alias} must contain at least one letter or number.")
        owner = find_item_by_code(alias, exclude=item)
        if owner and owner.code != code:
            raise ItemError(f"Other spelling {alias} belongs to {owner.code}.")
        aliases.append(alias)
    item = item or Item()
    item.code, item.search_key = code, search_key(code)
    item.spare_type, item.company = data["spare_type"], data["company"]
    item.description = (data.get("description") or "").strip()
    item.cat_ref = normalise_code(data.get("cat_ref"))
    item.fitting_type = data.get("fitting_type")
    item.wattage_w, item.current_ma = data.get("wattage_w"), data.get("current_ma")
    item.unit = data["unit"]
    item.reorder_level = data.get("reorder_level") or 0
    item.is_active = data.get("is_active", True)
    item.save()
    item.aliases.all().delete()
    ItemAlias.objects.bulk_create(ItemAlias(item=item, alias=a, search_key=search_key(a)) for a in aliases)
    return item


def search_items(text, limit=8, active_only=False):
    """Items matching any code, other spelling, description or fitting cat ref (typo-tolerant on codes)."""
    raw, code, key = (text or "").strip(), normalise_code(text), search_key(text)
    if len(raw) < 2:
        return []
    match = (
        Q(code__icontains=code)
        | Q(description__icontains=raw)
        | Q(cat_ref__icontains=code)
        | Q(aliases__alias__icontains=code)
    )
    if len(key) > 2:
        match |= Q(search_key__contains=key) | Q(aliases__search_key__contains=key)
    items = Item.objects.filter(match)
    if active_only:
        items = items.filter(is_active=True)
    return list(items.select_related("spare_type", "company").distinct().order_by("code")[:limit])
