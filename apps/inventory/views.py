from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tables import sort_and_page

from . import selectors
from .filters import _text, history_filters, item_filters, movement_filters, stock_filters
from .forms import ItemForm
from .models import Company, EntryKind, FittingType, Item, Location, SpareType
from .normalise import normalise_code
from .services import ItemError, find_item_by_code, save_item


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


def _item_form_context(form, item=None):
    cat_refs = Item.objects.exclude(cat_ref="").values_list("cat_ref", flat=True).distinct()
    return {"form": form, "item": item, "cat_refs": cat_refs}


@role_required(OFFICE)
def items(request):
    f = item_filters(request.GET)
    rows = selectors.item_rows(f)
    sorters = {
        "code": lambda r: r["item"].code,
        "type": lambda r: r["item"].spare_type.name,
        "desc": lambda r: r["item"].description,
        "cat": lambda r: r["item"].cat_ref,
        "watt": lambda r: r["item"].wattage_w or 0,
        "company": lambda r: r["item"].company.name,
        "unit": lambda r: r["item"].unit,
        "reorder": lambda r: r["item"].reorder_level,
        "stock": lambda r: r["total"],
    }
    table = sort_and_page(request, rows, sorters, "code")
    return render(
        request,
        "inventory/items.html",
        {
            "f": f,
            "table": table,
            "fitting_types": FittingType.objects.filter(is_active=True),
            **_masters(),
        },
    )


@role_required(OFFICE)
def item_new(request):
    form = ItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            item = save_item(data=form.cleaned_data)
        except ItemError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, f"Item {item.code} saved.")
            return redirect("item_detail", pk=item.pk)
    return render(request, "inventory/item_form.html", _item_form_context(form))


@role_required(OFFICE)
def item_edit(request, pk):
    item = get_object_or_404(Item, pk=pk)
    form = ItemForm(request.POST or None, initial=ItemForm.initial_from(item))
    if request.method == "POST" and form.is_valid():
        try:
            item = save_item(item=item, data=form.cleaned_data)
        except ItemError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, f"Item {item.code} saved.")
            return redirect("item_detail", pk=item.pk)
    return render(request, "inventory/item_form.html", _item_form_context(form, item))


@role_required(OFFICE)
def item_detail(request, pk):
    item = get_object_or_404(Item.objects.select_related("spare_type", "company", "fitting_type"), pk=pk)
    date_from, date_to, location = history_filters(request.GET, timezone.localdate())
    bal = selectors.balance_map()
    places = selectors.stock_locations(bal)
    per_loc = [(p, bal.get((item.pk, p.pk), 0)) for p in places]
    total = sum(q for _, q in per_loc)
    return render(
        request,
        "inventory/item_detail.html",
        {
            "item": item,
            "per_loc": per_loc,
            "total": total,
            "low": selectors.is_low(item, total),
            "history": selectors.item_history(item, date_from, date_to, location),
            "date_from": date_from,
            "date_to": date_to,
            "location": location,
            "all_locations": places,
        },
    )


@role_required(OFFICE)
@require_POST
def item_quick_create(request):
    """Create an item from the Stock IN form modal; returns JSON for the item picker."""
    form = ItemForm(request.POST)
    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        return JsonResponse({"ok": False, "error": first})
    try:
        item = save_item(data=form.cleaned_data)
    except ItemError as exc:
        return JsonResponse({"ok": False, "error": exc.message})
    return JsonResponse({"ok": True, "item": selectors.picker_option(item)})


@role_required(OFFICE)
def item_check_code(request):
    """Live hint while typing a code: ok / clash (exact or look-alike)."""
    code, original = _text(request.GET.get("code")), _text(request.GET.get("original"))
    if not normalise_code(code):
        return JsonResponse({"status": "empty", "message": ""})
    hit = find_item_by_code(code)
    if hit and hit.code != normalise_code(original):
        if hit.code == normalise_code(code):
            msg = f"{hit.code} already exists."
        else:
            msg = f"Looks like existing item {hit.code}. Use that instead?"
        return JsonResponse({"status": "clash", "message": msg})
    return JsonResponse({"status": "ok", "message": f"Will be saved as {normalise_code(code)}"})
