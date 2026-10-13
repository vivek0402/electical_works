"""All writes to items and stock. Views, forms and commands call these; nothing else touches the ledger."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from functools import reduce
from operator import or_

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Case, DateField, F, IntegerField, Min, Q, Sum, Value, When
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import (
    SERVICE_SUBTYPES,
    STORE_SUBTYPES,
    AdjustReason,
    EntryCounter,
    EntryKind,
    InSource,
    Item,
    ItemAlias,
    Location,
    OutTarget,
    ServiceSubtype,
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
    service = SERVICE_SUBTYPES.get(kind, set())
    if kind == EntryKind.IN:
        if subtype and subtype not in InSource.values and subtype not in service:
            raise StockError("Choose where the stock came from.")
    elif kind == EntryKind.OUT:
        if subtype and subtype not in OutTarget.values and subtype not in service:
            raise StockError("Choose who the stock was issued to.")
    elif subtype and subtype not in service:
        raise StockError(f"{EntryKind(kind).label} entries don't take a type.")
    if kind != EntryKind.ADJ and reason:
        raise StockError("Only an adjustment takes a reason.")

    inactive_item = Item.objects.filter(pk__in={line.item.pk for line in lines}, is_active=False).first()
    if inactive_item:
        raise StockError(f"{inactive_item.code} is inactive.")
    # One query for the places: active flag and Defective store flag, read from the database (never
    # from the caller's possibly stale Location objects).
    places = {
        pk: (name, is_active, is_store)
        for pk, name, is_active, is_store in Location.objects.filter(
            pk__in={line.location.pk for line in lines}
        ).values_list("pk", "name", "is_active", "is_defective_store")
    }
    inactive_place = next((name for name, active, _ in places.values() if not active), None)
    if inactive_place:
        raise StockError(f"{inactive_place} is inactive.")

    # Only the defectives services post to the Defective store, and their entries only post there.
    at_store = [places[line.location.pk][2] for line in lines]
    if subtype in STORE_SUBTYPES and not all(at_store):
        raise StockError(f"{ServiceSubtype(subtype).label} must be posted at the Defective store.")
    if subtype == ServiceSubtype.MARK_DEFECTIVE and (
        all(at_store)
        or not any(at_store)
        or any((line.qty > 0) != is_store for line, is_store in zip(lines, at_store, strict=True))
    ):
        # Every store line adds (qty > 0) and every good line removes (qty < 0).
        raise StockError("Marking defective moves stock from a good location into the Defective store.")
    if subtype == ServiceSubtype.SCRAP_DEFECTIVE and any(line.qty > 0 for line in lines):
        raise StockError("Scrapping can only remove pieces from the Defective store.")
    if any(at_store) and subtype not in STORE_SUBTYPES and subtype != ServiceSubtype.MARK_DEFECTIVE:
        raise StockError("The Defective store is managed from the Defectives screens.")

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


def _check_history(*, entry_date, deltas, items, places):
    """Refuse a backdated removal that would take stock below zero on its date or any later date.

    Call after the balance rows are locked, so concurrent posts are serialised. One query per key:
    lines dated before entry_date are folded into the entry_date bucket.
    """
    if entry_date >= timezone.localdate():
        return  # dated today: the current balance check covers it
    for (item_id, location_id), delta in deltas.items():
        if delta >= 0:
            continue
        day = Greatest(F("entry__entry_date"), Value(entry_date, output_field=DateField()))
        rows = (
            StockLine.objects.filter(item_id=item_id, location_id=location_id)
            .annotate(day=day)
            .values("day")
            .annotate(total=Sum("qty"))
            .order_by("day")
        )
        running, lowest, lowest_day = 0, None, entry_date
        for row in rows:
            if lowest is None and row["day"] != entry_date:
                lowest = 0  # nothing on or before entry_date: the balance there was 0
            running += row["total"]
            if lowest is None or running < lowest:
                lowest, lowest_day = running, row["day"]
        if lowest is None:
            lowest = 0
        if lowest + delta < 0:
            item, place = items[item_id], places[location_id]
            raise NotEnoughStock(
                f"Only {lowest} {item.unit} of {item.code} at {place.name} on {lowest_day:%d-%m-%Y}."
            )


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
    return_batch=None,
    complaint=None,
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
    _check_history(entry_date=entry_date, deltas=deltas, items=items, places=places)
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
        return_batch=return_batch,
        complaint=complaint,
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
def adjust_counts(*, entry_date, location, counts, reason, note, user, line_numbers=None) -> StockEntry:
    """Set the counted quantity for each (item, counted[, expected]) at one location; posts the differences.

    `expected` is the system quantity the user saw while counting. If the locked balance differs, someone
    moved that stock meanwhile and the count is refused. `line_numbers` (same order as counts) are the
    line numbers to name in that message; by default 1, 2, 3...
    """
    if not reason:
        raise StockError("Choose the reason for the adjustment.")
    if not note.strip():
        raise StockError("Write a short note explaining the adjustment.")
    if not counts:
        raise StockError("Add at least one item.")
    counts = [(c[0], c[1], c[2] if len(c) > 2 else None) for c in counts]
    numbers = list(line_numbers) if line_numbers else list(range(1, len(counts) + 1))
    seen = set()
    for item, counted, _ in counts:
        if item.pk in seen:
            raise StockError(f"{item.code} is listed twice.")
        seen.add(item.pk)
        if not _is_whole(counted) or counted < 0:
            raise StockError(f"Counted quantity for {item.code} must be a whole number, 0 or more.")
    keys = sorted((item.pk, location.pk) for item, _, _ in counts)
    balances = _lock_balances(keys)
    for n, (item, _, expected) in zip(numbers, counts, strict=True):
        now = balances[(item.pk, location.pk)].qty
        if expected is not None and expected != now:
            raise StockError(
                f"Line {n}: stock of {item.code} at {location.name} changed since you opened this page "
                f"(was {expected}, now {now}). Check the count and save again."
            )
    lines = [
        Line(item, location, counted - balances[(item.pk, location.pk)].qty) for item, counted, _ in counts
    ]
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
    if entry.is_complaint_visit:  # checked first: a visit's collection IN is also a defectives entry
        raise StockError("This entry belongs to a complaint visit. Correct it from the complaint.")
    if entry.is_defective:
        raise StockError(
            "This entry belongs to the defective pieces. Use the Defectives screens instead of Undo."
        )
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


ITEM_WRITE_LOCK = 724_018_001  # arbitrary fixed bigint: serialises all item writes
MAX_CODE_LENGTH = 80


def find_item_by_code(text, exclude=None):
    """Exact code, a stored other spelling, then a look-alike code (O/0, I/1, hyphens, leading zeros)."""
    code, key = normalise_code(text), search_key(text)
    if not code:
        return None
    items = Item.objects.exclude(pk=exclude.pk) if exclude else Item.objects.all()
    aliases = ItemAlias.objects.exclude(item=exclude) if exclude else ItemAlias.objects.all()
    hit = items.filter(code=code).first()
    if hit:
        return hit
    alias = aliases.filter(alias=code).select_related("item").first()
    if alias:
        return alias.item
    if not key:
        return None
    hit = items.filter(search_key=key).first()
    if hit:
        return hit
    alias = aliases.filter(search_key=key).select_related("item").first()
    return alias.item if alias else None


@transaction.atomic
def save_item(*, data, item=None) -> Item:
    """Create (item=None) or replace an item's fields from cleaned form data. Raises ItemError.

    `data` is a full replace: every key is required (code, spare_type, company, description, cat_ref,
    fitting_type, wattage_w, current_ma, unit, reorder_level, aliases, is_active). A missing key raises
    KeyError on purpose, so a partial dict can never silently reset fields or drop aliases.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ITEM_WRITE_LOCK])
    code = normalise_code(data["code"])
    if not code:
        raise ItemError("Item code is required.")
    if len(code) > MAX_CODE_LENGTH:
        raise ItemError(f"Item code is too long (max {MAX_CODE_LENGTH} characters).")
    if not search_key(code):
        raise ItemError("Item code must contain at least one letter or number.")
    clash = find_item_by_code(code, exclude=item)
    if clash:
        if clash.code == code:
            raise ItemError(f"{code} already exists.")
        msg = f"{code} looks the same as {clash.code}. Use that item instead."
        if not clash.is_active:
            msg += " (It is inactive; reactivate it.)"
        raise ItemError(msg)
    if item and item.code != code and item.lines.exists():
        raise ItemError(
            "This item already has stock entries, so its code can't be changed. "
            "Add the new spelling under 'Other spellings'."
        )
    if item and item.unit != data["unit"] and item.lines.exists():
        raise ItemError(f"The unit can't be changed because {item.code} already has stock entries.")
    if item and not data["is_active"] and item.balances.exclude(qty=0).exists():
        raise ItemError(f"{item.code} still holds stock. Issue or adjust it to zero first.")
    aliases = []
    for raw in data["aliases"]:
        alias = normalise_code(raw)
        if not alias or alias == code or alias in aliases:
            continue
        if len(alias) > MAX_CODE_LENGTH:
            raise ItemError(f"Other spelling {alias} is too long (max {MAX_CODE_LENGTH} characters).")
        if not search_key(alias):
            raise ItemError(f"Other spelling {alias} must contain at least one letter or number.")
        owner = find_item_by_code(alias, exclude=item)
        if owner:
            raise ItemError(f"Other spelling {alias} belongs to {owner.code}.")
        aliases.append(alias)
    item = item or Item()
    item.code, item.search_key = code, search_key(code)
    item.spare_type, item.company = data["spare_type"], data["company"]
    item.description = (data["description"] or "").strip()
    item.cat_ref = normalise_code(data["cat_ref"])
    item.fitting_type = data["fitting_type"]
    item.wattage_w, item.current_ma = data["wattage_w"], data["current_ma"]
    item.unit = data["unit"]
    item.reorder_level = data["reorder_level"] or 0
    item.is_active = data["is_active"]
    try:
        with transaction.atomic():
            item.save()
            item.aliases.all().delete()
            ItemAlias.objects.bulk_create(
                ItemAlias(item=item, alias=a, search_key=search_key(a)) for a in aliases
            )
    except IntegrityError as exc:
        raise ItemError(f"{code} already exists.") from exc
    return item


def item_search_q(text):
    """Q matching a code, other spelling, description or cat ref. None if text is too short."""
    raw, code, key = (text or "").strip(), normalise_code(text), search_key(text)
    if len(raw) < 2:
        return None
    match = (
        Q(code__icontains=code)
        | Q(description__icontains=raw)
        | Q(cat_ref__icontains=code)
        | Q(aliases__alias__icontains=code)
    )
    if len(key) > 2:
        match |= Q(search_key__contains=key) | Q(aliases__search_key__contains=key)
    return match


def search_items(text, limit=8, active_only=False):
    """Items matching a code, other spelling, description or cat ref (typo-tolerant on codes).

    Best matches first: exact code or spelling, then codes starting with the text, then the rest.
    """
    code = normalise_code(text)
    match = item_search_q(text)
    if match is None:
        return []
    items = Item.objects.filter(match)
    if active_only:
        items = items.filter(is_active=True)
    rank = Min(
        Case(
            When(code=code, then=Value(0)),
            When(aliases__alias=code, then=Value(0)),
            When(code__startswith=code, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    )
    return list(
        items.select_related("spare_type", "company")
        .prefetch_related("aliases")
        .annotate(rank=rank)
        .order_by("rank", "code")[:limit]
    )
