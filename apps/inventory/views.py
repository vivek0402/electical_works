from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tables import sort_and_page
from apps.core.tokens import guarded_post, page_token

from . import selectors
from .context_processors import PIECES_STATUS_QUERY, service_counts
from .entry_lines import parse_lines, raw_lines
from .filters import _text, history_filters, item_filters, movement_filters, stock_filters
from .forms import AdjustForm, ItemForm, StockInForm, StockOutForm, TransferForm, UndoForm
from .models import (
    Company,
    EntryKind,
    FittingType,
    InSource,
    Item,
    Location,
    OutTarget,
    SpareType,
    StockBalance,
    StockEntry,
)
from .normalise import normalise_code
from .services import (
    ItemError,
    Line,
    StockError,
    adjust_counts,
    find_item_by_code,
    post_entry,
    save_item,
    search_items,
    undo_entry,
)


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
            "service": selectors.service_stats(today, *service_counts(request)),
            "pieces_urls": {
                status: reverse("defective_pieces") + PIECES_STATUS_QUERY.format(status)
                for status in ("IN_STORE", "SENT")
            },
            "today": today,
            "movements_from": selectors.movements_week_from(today),
        },
    )


def _masters():
    return {
        "all_locations": Location.objects.good().filter(is_active=True),
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
        "def": lambda r: r["defective"],
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
        {
            "f": f,
            "table": table,
            "kinds": EntryKind.choices,
            **_masters(),
            "all_locations": Location.objects.filter(is_active=True),  # the Defective store stays filterable
        },
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
    form = ItemForm(request.POST or None, initial=ItemForm.initial_from(item), item=item)
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
    held = dict(StockBalance.objects.filter(item=item).values_list("location_id", "qty"))
    store_id = selectors.defective_store_id()
    places = list(
        Location.objects.good().filter(Q(is_active=True) | Q(pk__in=[k for k, q in held.items() if q]))
    )
    per_loc = [(p, held.get(p.pk, 0)) for p in places]
    total = sum(q for _, q in per_loc)
    return render(
        request,
        "inventory/item_detail.html",
        {
            "item": item,
            "per_loc": per_loc,
            "total": total,
            "defective": held.get(store_id, 0),
            "low": selectors.is_low(item, total),
            "history": selectors.item_history(item, date_from, date_to, location),
            "date_from": date_from,
            "date_to": date_to,
            "location": location,
            "all_locations": places + list(Location.objects.filter(pk=store_id)),
        },
    )


@role_required(OFFICE)
@require_POST
def item_quick_create(request):
    """Create an item from the Stock IN form modal; returns JSON for the item picker."""
    form = ItemForm(request.POST, prefix="qi")
    if not form.is_valid():
        name, errs = next(iter(form.errors.items()))
        label = form.fields[name].label or name.replace("_", " ").capitalize()
        return JsonResponse(
            {"ok": False, "error": f"{label}: {errs[0]}", "errors": form.errors.get_json_data()}
        )
    try:
        item = save_item(data={**form.cleaned_data, "is_active": True})
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


ENTRY_PAGES = {
    # mode: (kind, form, title, subtitle, icon, save-button class)
    "in": (
        EntryKind.IN,
        StockInForm,
        "Stock IN",
        "Material received at a location",
        "package-import",
        "btn-in",
    ),
    "out": (
        EntryKind.OUT,
        StockOutForm,
        "Stock OUT",
        "Material given out from a location",
        "package-export",
        "btn-out",
    ),
    "trf": (
        EntryKind.TRF,
        TransferForm,
        "Transfer stock",
        "Move stock from one location to another",
        "arrows-exchange",
        "btn-primary",
    ),
    "adj": (
        EntryKind.ADJ,
        AdjustForm,
        "Adjust stock count",
        "Correct the system count after a physical check",
        "adjustments-horizontal",
        "btn-primary",
    ),
}
SUBTYPE_ICONS = {
    InSource.SUPPLIER: "truck-delivery",
    InSource.RETURN: "arrow-back-up",
    InSource.OPENING: "clipboard-list",
    OutTarget.SITE: "building-factory-2",
    OutTarget.TECH: "user-cog",
    OutTarget.OTHER: "user",
}


def _default_location():
    return selectors.default_location()


def _save_entry(mode, data, parsed, user):
    kind, place, note = ENTRY_PAGES[mode][0], data["location"], data.get("note", "")
    common = {"entry_date": data["entry_date"], "user": user, "note": note}
    if mode == "in":
        return post_entry(
            kind=kind,
            lines=[Line(p.item, place, p.qty, p.batch, p.pkd) for p in parsed],
            subtype=data["subtype"],
            party=data["party"],
            company=data["company"],
            ref=data["ref"],
            **common,
        )
    if mode == "out":
        return post_entry(
            kind=kind,
            lines=[Line(p.item, place, -p.qty) for p in parsed],
            subtype=data["subtype"],
            party=data["party"],
            ref=data["ref"],
            **common,
        )
    if mode == "trf":
        dest = data["to_location"]
        moves = [line for p in parsed for line in (Line(p.item, place, -p.qty), Line(p.item, dest, p.qty))]
        return post_entry(kind=kind, lines=moves, party=dest.name, **common)
    return adjust_counts(
        entry_date=data["entry_date"],
        location=place,
        counts=[(p.item, p.qty, p.expected) for p in parsed],
        line_numbers=[p.n for p in parsed],
        reason=data["reason"],
        note=note,
        user=user,
    )


def _entry_page(request, mode):
    kind, form_class, title, subtitle, icon, button = ENTRY_PAGES[mode]
    initial = {"entry_date": timezone.localdate(), "location": _default_location()}
    if mode == "trf":
        others = (
            Location.objects.good()
            .filter(is_active=True)
            .exclude(pk=getattr(initial["location"], "pk", None))
        )
        initial["to_location"] = others.filter(name="TV Shop").first() or others.first()
    form = form_class(request.POST or None, initial=initial)
    error, lines, token = None, [], ""
    if request.method == "POST":
        lines = raw_lines(request.POST)

        def run():
            if not form.is_valid():
                raise StockError(form.first_error())
            try:
                entry = _save_entry(mode, form.cleaned_data, parse_lines(lines, mode), request.user)
            except StockError as exc:
                raise StockError(f"{exc.message} Nothing was saved.") from exc
            count = entry.lines.values("item").distinct().count()
            messages.success(request, f"{entry.number} saved · {count} item(s). Stock updated.")
            return entry.number

        # A missing, expired or already-spent token saves nothing, keeps what was typed and asks again.
        result = guarded_post(request, run)
        if result.replayed:
            messages.warning(request, "This entry was already saved.")
        if result.saved:
            return redirect("entry_detail", number=result.saved)
        error, token = result.error, result.token
    elif request.GET.get("item", "").isdecimal():
        lines = [{"item": request.GET["item"], "qty": "", "batch": "", "pkd": "", "expected": ""}]
    items, balances = selectors.picker_data()
    subtypes = []
    if "subtype" in form.fields:
        subtypes = [(v, label, SUBTYPE_ICONS[v]) for v, label in form.fields["subtype"].choices]
    context = {
        "mode": mode,
        "form": form,
        "title": title,
        "subtitle": subtitle,
        "icon": icon,
        "button": button,
        "error": error,
        "token": token or page_token(request.session, request.path),
        "subtypes": subtypes,
        "items_data": items,
        "balances_data": balances,
        "initial_lines": lines,
        "parties": {v: selectors.recent_parties(v) for v, _, _ in subtypes},
    }
    if mode == "in":
        context["item_form"] = ItemForm(prefix="qi")
        context["cat_refs"] = Item.objects.exclude(cat_ref="").values_list("cat_ref", flat=True).distinct()
    return render(request, "inventory/entry_form.html", context)


@never_cache
@role_required(OFFICE)
def stock_in(request):
    return _entry_page(request, "in")


@never_cache
@role_required(OFFICE)
def stock_out(request):
    return _entry_page(request, "out")


@never_cache
@role_required(OFFICE)
def transfer(request):
    return _entry_page(request, "trf")


@never_cache
@role_required(OFFICE)
def adjust(request):
    return _entry_page(request, "adj")


@role_required(OFFICE)
def entry_detail(request, number):
    from apps.defectives.models import DefectivePiece  # imported here: defectives depends on inventory

    entry = get_object_or_404(selectors.entries_with_lines(StockEntry.objects.all()), number=number)
    undone_by = StockEntry.objects.filter(reverses=entry).first()
    # the pieces this entry moved (collected, marked, dispatched, settled or scrapped)
    pieces = (
        DefectivePiece.objects.filter(events__entry=entry).distinct().select_related("item").order_by("id")
    )
    return render(
        request,
        "inventory/entry_detail.html",
        {
            "entry": entry,
            "undone_by": undone_by,
            "can_undo": entry.kind != EntryKind.REV
            and undone_by is None
            and not entry.is_defective
            and not entry.is_complaint_visit,
            "pieces": pieces,
        },
    )


@role_required(OFFICE)
@require_POST
def entry_undo(request, number):
    entry = get_object_or_404(StockEntry, number=number)
    form = UndoForm(request.POST)
    if not form.is_valid():
        messages.error(request, f"Reason: {form.errors['reason'][0]}")
        return redirect("entry_detail", number=number)
    try:
        rev = undo_entry(entry=entry, reason=form.cleaned_data["reason"], user=request.user)
    except StockError as exc:
        messages.error(request, exc.message)
        return redirect("entry_detail", number=number)
    messages.success(request, f"{entry.number} undone by {rev.number}. Stock updated.")
    return redirect("entry_detail", number=rev.number)


SEARCH_EMPTY = {"items": [], "entries": [], "complaints": [], "sites": [], "pieces": []}


@role_required(OFFICE)
def global_search(request):
    """Top-bar search: items (code, other spelling, description, fitting), entry numbers, complaints (the
    complaints list's search: no., company's complaint no., site, fault, contact, phone), sites and
    defective pieces (the pieces list's search: tag typed loosely, batch code, RB no., ...).
    Each group is kept small."""
    from apps.complaints.models import Complaint, Site  # imported here: both apps depend on inventory
    from apps.complaints.selectors import complaint_search_q
    from apps.defectives.selectors import piece_search_q, pieces_qs

    q = _text(request.GET.get("q"))
    if len(q) <= 2:
        return JsonResponse(SEARCH_EMPTY)
    found = [
        {**selectors.picker_option(i), "url": reverse("item_detail", args=[i.pk])}
        for i in search_items(q, limit=8)
    ]
    entries = StockEntry.objects.filter(number__icontains=q).order_by("-id")[:5]
    complaints = (
        Complaint.objects.filter(complaint_search_q(q)).select_related("site", "company").order_by("-id")[:5]
    )
    sites = Site.objects.filter(
        Q(name__icontains=q) | Q(city__icontains=q) | Q(contact_name__icontains=q)
    ).order_by("-is_active", "name", "city")[:4]  # active sites first
    pieces = pieces_qs().filter(piece_search_q(q)).order_by("-id")[:5]
    return JsonResponse(
        {
            "items": found,
            "entries": [
                {
                    "number": e.number,
                    "url": reverse("entry_detail", args=[e.number]),
                    "label": e.get_kind_display(),
                }
                for e in entries
            ],
            "complaints": [
                {
                    "number": c.number,
                    "url": reverse("complaint_detail", args=[c.number]),
                    "label": f"{c.site.name}, {c.site.city} · {c.company.name}",
                    "ref": c.company_ref,
                    "status": c.get_status_display(),
                }
                for c in complaints
            ],
            "sites": [
                {
                    "name": s.name,
                    "url": reverse("site_detail", args=[s.pk]),
                    "label": s.city
                    + (f" · {s.contact_name}" if s.contact_name else "")
                    + ("" if s.is_active else " (hidden)"),
                }
                for s in sites
            ],
            "pieces": [
                {
                    "tag": p.tag,
                    "url": reverse("piece_detail", args=[p.tag]),
                    "label": f"{p.item.code} · {p.company.name}",
                    "status": p.get_status_display(),
                }
                for p in pieces
            ],
        }
    )
