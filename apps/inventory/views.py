from django.shortcuts import render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tables import sort_and_page

from . import selectors
from .filters import movement_filters, stock_filters
from .models import Company, EntryKind, Location, SpareType


@role_required(OFFICE)
def dashboard(request):
    today = timezone.localdate()
    weeks = selectors.weekly_in_out(today)
    return render(
        request,
        "inventory/dashboard.html",
        {
            "stats": selectors.dashboard_stats(today),
            "weeks": weeks,
            "weeks_chart": [{"label": w["label"], "in": w["qty_in"], "out": w["qty_out"]} for w in weeks],
            "locations": selectors.location_unit_totals(),
            "recent": selectors.recent_entries(),
            "today": today,
        },
    )


def _masters():
    return {
        "all_locations": Location.objects.filter(is_active=True),
        "spare_types": SpareType.objects.filter(is_active=True),
        "companies": Company.objects.filter(is_active=True),
    }


@role_required(OFFICE)
def current_stock(request):
    f = stock_filters(request.GET)
    rows, locations = selectors.current_stock_rows(f)
    sorters = {
        "code": lambda r: r["item"].code,
        "type": lambda r: r["item"].spare_type.name,
        "desc": lambda r: r["item"].description,
        "company": lambda r: r["item"].company.name,
        "total": lambda r: r["total"],
        "unit": lambda r: r["item"].unit,
    }
    for p in locations:
        p.sort_key = f"L{p.pk}"
        sorters[p.sort_key] = lambda r, pk=p.pk: r["per_loc"].get(pk, 0)
    table = sort_and_page(request, rows, sorters, "code")
    return render(
        request,
        "inventory/current_stock.html",
        {"f": f, "table": table, "locations": locations, **_masters()},
    )


@role_required(OFFICE)
def low_stock(request):
    rows, locations = selectors.low_stock_rows()
    sorters = {
        "code": lambda r: r["item"].code,
        "type": lambda r: r["item"].spare_type.name,
        "total": lambda r: r["total"],
        "short": lambda r: r["short_by"],
        "reorder": lambda r: r["item"].reorder_level,
    }
    table = sort_and_page(request, rows, sorters, "short", "desc")
    return render(
        request,
        "inventory/low_stock.html",
        {"table": table, "locations": locations},
    )


@role_required(OFFICE)
def movements(request):
    f = movement_filters(request.GET, timezone.localdate())
    rows = selectors.movement_rows(f)
    sorters = {
        "date": lambda r: -r["n"],
        "no": lambda r: r["entry"].number,
        "kind": lambda r: r["entry"].kind,
        "code": lambda r: r["line"].item.code,
        "loc": lambda r: r["line"].location.name,
        "in": lambda r: r["line"].qty,
        "out": lambda r: -r["line"].qty,
        "party": lambda r: r["entry"].party,
        "by": lambda r: r["entry"].created_by.username,
    }
    table = sort_and_page(request, rows, sorters, "date", "desc")
    return render(
        request,
        "inventory/movements.html",
        {"f": f, "table": table, "kinds": EntryKind.choices, **_masters()},
    )
