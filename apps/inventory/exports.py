"""Excel downloads. Each reuses its list screen's filters, so it exports what is shown (all pages)."""

from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.excel import Column, workbook_response

from . import selectors
from .filters import history_filters, item_filters, movement_filters, stock_filters
from .models import EntryKind, Item


def _describe(*parts):
    return " · ".join(p for p in parts if p) or "None"


def _who(request):
    return request.user.first_name or request.user.username


def _pkd(line):
    return f"{line.pkd:%m-%Y}" if line.pkd else ""


@role_required(OFFICE)
def current_stock_xlsx(request):
    f = stock_filters(request.GET)
    rows, locations = selectors.current_stock_rows(f)
    rows.sort(key=lambda r: r["item"].code)
    cols = [
        Column("Item code", "code"),
        Column("Spare type"),
        Column("Description", width=30),
        Column("Used in fitting (cat ref)", "code"),
        Column("Fitting type"),
        Column("Company"),
    ]
    cols += [Column(p.name, "int") for p in locations]
    cols += [Column("Total", "int"), Column("Unit"), Column("Reorder level", "int"), Column("Status")]
    data = [
        [
            r["item"].code,
            r["item"].spare_type.name,
            r["item"].description,
            r["item"].cat_ref if r["item"].cat_ref != r["item"].code else "",
            r["item"].fitting_type.name if r["item"].fitting_type else "",
            r["item"].company.name,
        ]
        + [r["per_loc"].get(p.pk, 0) for p in locations]
        + [r["total"], r["item"].unit, r["item"].reorder_level, "LOW" if r["low"] else "OK"]
        for r in rows
    ]
    filters = _describe(
        f.location.name if f.location else "All locations",
        f.spare_type.name if f.spare_type else "all types",
        f.company.name if f.company else "all companies",
        f'search "{f.q}"' if f.q else "",
        "only low stock" if f.low else "",
    )
    low = {n for n, r in enumerate(rows) if r["low"]}
    return workbook_response(
        "Current_Stock", "Current Stock", filters, _who(request), cols, data, low, len(cols) - 1
    )


@role_required(OFFICE)
def movements_xlsx(request):
    f = movement_filters(request.GET, timezone.localdate())
    rows = selectors.movement_rows(f)
    cols = [
        Column("Date", "date"),
        Column("Entry no.", "code"),
        Column("Type"),
        Column("Details"),
        Column("Item code", "code"),
        Column("Description", width=28),
        Column("Location"),
        Column("Qty in", "int"),
        Column("Qty out", "int"),
        Column("Unit"),
        Column("Supplier / issued to", width=26),
        Column("DC / ref no."),
        Column("Batch code"),
        Column("PKD"),
        Column("Entered by"),
        Column("Note", width=28),
    ]
    data = []
    for r in rows:
        e, line = r["entry"], r["line"]
        note = f"Undone by {e.reversed_by.number}" if r["undone"] else e.note
        data.append(
            [
                e.entry_date,
                e.number,
                e.get_kind_display(),
                e.details,
                line.item.code,
                line.item.description,
                line.location.name,
                line.qty if line.qty > 0 else None,
                -line.qty if line.qty < 0 else None,
                line.item.unit,
                e.party,
                e.ref,
                line.batch_code,
                _pkd(line),
                e.created_by.first_name or e.created_by.username,
                note,
            ]
        )
    filters = _describe(
        f"{f.date_from:%d-%m-%Y} to {f.date_to:%d-%m-%Y}",
        EntryKind(f.kind).label if f.kind else "all types",
        f.location.name if f.location else "all locations",
        f.item.code if f.item else "",
        f'search "{f.q}"' if f.q else "",
    )
    return workbook_response("Stock_Movements", "Stock Movements", filters, _who(request), cols, data)


@role_required(OFFICE)
def items_xlsx(request):
    f = item_filters(request.GET)
    rows = sorted(selectors.item_rows(f), key=lambda r: r["item"].code)
    cols = [
        Column("Item code", "code"),
        Column("Other spellings", "code"),
        Column("Spare type"),
        Column("Description", width=30),
        Column("Product cat ref", "code"),
        Column("Fitting type"),
        Column("Wattage (W)", "int"),
        Column("Current (mA)", "int"),
        Column("Company"),
        Column("Unit"),
        Column("Reorder level", "int"),
        Column("In stock", "int"),
        Column("Status"),
    ]
    data = [
        [
            i.code,
            ", ".join(a.alias for a in i.aliases.all()),
            i.spare_type.name,
            i.description,
            i.cat_ref,
            i.fitting_type.name if i.fitting_type else "",
            i.wattage_w,
            i.current_ma,
            i.company.name,
            i.unit,
            i.reorder_level,
            r["total"],
            "Active" if i.is_active else "Inactive",
        ]
        for r in rows
        for i in [r["item"]]
    ]
    status = {"1": "active", "0": "inactive", "": "active and inactive"}[f.status]
    filters = _describe(
        f'search "{f.q}"' if f.q else "",
        f.spare_type.name if f.spare_type else "all types",
        f.company.name if f.company else "all companies",
        f.fitting_type.name if f.fitting_type else "",
        status,
    )
    return workbook_response("Item_List", "Item List", filters, _who(request), cols, data)


@role_required(OFFICE)
def low_stock_xlsx(request):
    rows, locations = selectors.low_stock_rows()
    rows.sort(key=lambda r: -r["short_by"])
    cols = [
        Column("Item code", "code"),
        Column("Spare type"),
        Column("Description", width=30),
        Column("Company"),
    ]
    cols += [Column(p.name, "int") for p in locations]
    cols += [
        Column("Total", "int"),
        Column("Reorder level", "int"),
        Column("Short by", "int"),
        Column("Unit"),
    ]
    data = [
        [r["item"].code, r["item"].spare_type.name, r["item"].description, r["item"].company.name]
        + [r["per_loc"].get(p.pk, 0) for p in locations]
        + [r["total"], r["item"].reorder_level, r["short_by"], r["item"].unit]
        for r in rows
    ]
    total_col = 4 + len(locations)
    return workbook_response(
        "Low_Stock",
        "Low Stock",
        "Items at or below their reorder level (total across all locations)",
        _who(request),
        cols,
        data,
        set(range(len(data))),
        total_col,
    )


@role_required(OFFICE)
def item_history_xlsx(request, pk):
    item = get_object_or_404(Item, pk=pk)
    today = timezone.localdate()
    date_from, date_to, location = history_filters(request.GET, today)
    rows = selectors.item_history(item, date_from, date_to, location)
    cols = [
        Column("Date", "date"),
        Column("Entry no.", "code"),
        Column("Type"),
        Column("Location"),
        Column("Qty in", "int"),
        Column("Qty out", "int"),
        Column("Balance at location", "int"),
        Column("Supplier / issued to", width=26),
        Column("DC / ref no."),
        Column("Batch code"),
        Column("PKD"),
        Column("Entered by"),
    ]
    data = [
        [
            r["entry"].entry_date,
            r["entry"].number,
            r["entry"].get_kind_display(),
            r["line"].location.name,
            r["line"].qty if r["line"].qty > 0 else None,
            -r["line"].qty if r["line"].qty < 0 else None,
            r["after"],
            r["entry"].party,
            r["entry"].ref,
            r["line"].batch_code,
            _pkd(r["line"]),
            r["entry"].created_by.first_name or r["entry"].created_by.username,
        ]
        for r in rows
    ]
    filters = _describe(
        f"{date_from:%d-%m-%Y} to {date_to:%d-%m-%Y}", location.name if location else "all locations"
    )
    return workbook_response(
        f"Item_{item.pk}_History",
        f"Item history: {item.code} ({item.unit})",
        filters,
        _who(request),
        cols,
        data,
    )
