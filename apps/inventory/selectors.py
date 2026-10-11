"""All reads for the stock screens. Views call these; no queries in templates."""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Exists, F, OuterRef, Q, Sum
from django.db.models.functions import Coalesce

from .models import EntryKind, Item, Location, StockBalance, StockEntry, StockLine
from .services import item_search_q


def balance_map():
    """{(item_id, location_id): qty} for every non-zero balance."""
    return {
        (b["item_id"], b["location_id"]): b["qty"]
        for b in StockBalance.objects.exclude(qty=0).values("item_id", "location_id", "qty")
    }


def item_totals():
    return {
        r["item_id"]: r["total"] for r in StockBalance.objects.values("item_id").annotate(total=Sum("qty"))
    }


def is_low(item, total):
    return item.reorder_level > 0 and total <= item.reorder_level


def low_stock_items():
    totals = item_totals()
    return [
        i
        for i in Item.objects.filter(is_active=True).select_related("spare_type", "company")
        if is_low(i, totals.get(i.pk, 0))
    ]


def low_stock_count():
    """Number of active items at or below their reorder level, in one query."""
    return (
        Item.objects.filter(is_active=True, reorder_level__gt=0)
        .annotate(t=Coalesce(Sum("balances__qty"), 0))
        .filter(t__lte=F("reorder_level"))
        .count()
    )


def location_unit_totals():
    """[(location, {unit: qty})] for the 'Stock by location' card."""
    totals = defaultdict(lambda: defaultdict(int))
    for row in StockBalance.objects.exclude(qty=0).values("location_id", "item__unit").annotate(q=Sum("qty")):
        totals[row["location_id"]][row["item__unit"]] += row["q"]
    return [(place, dict(totals[place.pk])) for place in Location.objects.filter(is_active=True)]


def dashboard_stats(today):
    nos = StockBalance.objects.filter(item__unit="NOS").aggregate(t=Sum("qty"))["t"] or 0
    return {
        "active_items": Item.objects.filter(is_active=True).count(),
        "nos_in_stock": nos,
        "low_count": low_stock_count(),
        "entries_week": StockEntry.objects.filter(entry_date__gt=today - timedelta(days=7)).count(),
        "entries_today": StockEntry.objects.filter(entry_date=today).count(),
    }


def weekly_in_out(today, weeks=5):
    """NOS quantity received and issued per 7-day window, oldest first; undone entries excluded."""
    windows = [
        (today - timedelta(days=7 * w + 6), today - timedelta(days=7 * w)) for w in range(weeks - 1, -1, -1)
    ]
    lines = StockLine.objects.filter(
        entry__kind__in=[EntryKind.IN, EntryKind.OUT],
        item__unit="NOS",
        entry__entry_date__gte=windows[0][0],
        entry__entry_date__lte=today,
        entry__reversed_by__isnull=True,
    ).values_list("entry__entry_date", "qty")
    out = [
        {"start": s, "end": e, "label": f"{s:%d-%m}–{e:%d-%m}", "qty_in": 0, "qty_out": 0} for s, e in windows
    ]
    for day, qty in lines:
        for week in out:
            if week["start"] <= day <= week["end"]:
                week["qty_in" if qty > 0 else "qty_out"] += abs(qty)
    return out


def entries_with_lines(queryset):
    undone = StockEntry.objects.filter(reverses=OuterRef("pk"))
    return (
        queryset.annotate(undone_flag=Exists(undone))
        .select_related("reverses", "created_by")
        .prefetch_related("lines__item", "lines__location")
    )


def recent_entries(limit=8):
    return list(entries_with_lines(StockEntry.objects.order_by("-entry_date", "-id"))[:limit])


def _filtered_items(f):
    items = Item.objects.select_related("spare_type", "company", "fitting_type")
    if getattr(f, "spare_type", None):
        items = items.filter(spare_type=f.spare_type)
    if getattr(f, "company", None):
        items = items.filter(company=f.company)
    match = item_search_q(getattr(f, "q", ""))
    if match is not None:
        items = items.filter(match).distinct()
    return items


def current_stock_rows(f):
    """(rows, locations). Row: {item, per_loc: {location_id: qty}, total, low}. Hides items with no stock."""
    locations = [f.location] if f.location else list(Location.objects.filter(is_active=True))
    bal = balance_map()
    rows = []
    for item in _filtered_items(f).filter(is_active=True):
        per_loc = {place.pk: bal.get((item.pk, place.pk), 0) for place in Location.objects.all()}
        total = sum(per_loc.values())
        low = is_low(item, total)
        shown = per_loc.get(f.location.pk, 0) != 0 if f.location else (total != 0 or f.low)
        if shown and (low or not f.low):
            rows.append({"item": item, "per_loc": per_loc, "total": total, "low": low})
    return rows, locations


def low_stock_rows():
    rows, _ = current_stock_rows(
        type("F", (), {"location": None, "spare_type": None, "company": None, "q": "", "low": True})()
    )
    for row in rows:
        row["short_by"] = max(0, row["item"].reorder_level - row["total"])
    return rows


def movement_rows(f):
    """One row per ledger line in the date range: {entry, line, undone}. Newest first."""
    undone = StockEntry.objects.filter(reverses=OuterRef("entry_id"))
    lines = (
        StockLine.objects.filter(entry__entry_date__gte=f.date_from, entry__entry_date__lte=f.date_to)
        .select_related(
            "entry", "entry__created_by", "entry__reverses", "entry__reversed_by", "item", "location"
        )
        .annotate(undone=Exists(undone))
        .order_by("-entry__entry_date", "-entry_id", "id")
    )
    if f.kind:
        lines = lines.filter(entry__kind=f.kind)
    if f.location:
        lines = lines.filter(location=f.location)
    if f.item:
        lines = lines.filter(item=f.item)
    if f.q:
        lines = lines.filter(
            Q(item__code__icontains=f.q)
            | Q(entry__party__icontains=f.q)
            | Q(entry__ref__icontains=f.q)
            | Q(entry__number__icontains=f.q)
        )
    return [
        {"entry": line.entry, "line": line, "undone": line.undone, "n": n} for n, line in enumerate(lines)
    ]
