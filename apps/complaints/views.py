from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN, OFFICE, has_role
from apps.core.tables import sort_and_page
from apps.core.tokens import guarded_post, page_token
from apps.defectives.services import MAX_PIECES_PER_LINE, DefectiveError
from apps.inventory import selectors as stock
from apps.inventory.entry_lines import parse_lines, raw_lines
from apps.inventory.filters import _text
from apps.inventory.models import Company, StockEntry
from apps.inventory.services import StockError

from . import selectors, services
from .filters import AGE_BUCKETS, CLOSED_SINCE_TABS, FINISHED, complaint_filters
from .forms import ComplaintForm, SiteForm, TechnicianForm, VisitForm
from .models import TRANSITIONS, Complaint, NotCoveredReason, Priority, Site, Status, Technician, Visit
from .services import ComplaintError

SAVED_ALREADY = "This was already saved."


@never_cache
@role_required(OFFICE)
def complaint_new(request):
    """File a complaint. The site picker fills contact and phone from the site; a contact or phone left
    blank means "copy it from the site" (file_complaint gets None), a typed one is kept for this complaint
    only and doesn't change the site."""
    initial = {"reported_on": timezone.localdate()}
    if request.GET.get("site", "").isdecimal():
        initial["site"] = request.GET["site"]
    form = ComplaintForm(request.POST or None, initial=initial)
    error, token = None, ""
    if request.method == "POST":

        def run():
            if not form.is_valid():
                raise ComplaintError(form.first_error())
            data = form.cleaned_data
            c = services.file_complaint(
                site=data["site"],
                company=data["company"],
                fault=data["fault"],
                reported_on=data["reported_on"],
                user=request.user,
                company_ref=data["company_ref"],
                qty_affected=data["qty_affected"],
                priority=data["priority"],
                technicians=list(data["technicians"]),
                contact_name=data["contact_name"] or None,  # blank: use the site's
                phone=data["phone"] or None,
            )
            messages.success(request, f"Complaint {c.number} filed for {c.site.name}.")
            return reverse("complaint_detail", args=[c.number])

        result = guarded_post(request, run)
        if result.replayed:
            messages.warning(request, "This complaint was already saved.")
        if result.saved:
            return redirect(result.saved)
        error, token = result.error, result.token
    return render(
        request,
        "complaints/form.html",
        {
            "form": form,
            "error": error,
            "token": token or page_token(request.session, request.path),
            "site_form": SiteForm(prefix="ns"),
            "sites_data": selectors.site_options(),
            "cities": selectors.cities(),
        },
    )


@role_required(OFFICE)
@require_POST
def site_quick_create(request):
    """The New site modal: save a site and return it as JSON for the picker. Like item_quick_create (Stock IN)
    it carries no one-time token: saving the same site twice is refused as a duplicate."""
    form = SiteForm(request.POST, prefix="ns")
    if not form.is_valid():
        return JsonResponse({"ok": False, "error": form.first_error()})
    try:
        site = services.save_site(data=form.cleaned_data)
    except ComplaintError as exc:
        return JsonResponse({"ok": False, "error": exc.message})
    return JsonResponse({"ok": True, "site": selectors.site_option(site)})


def _dialogs(c, visits):
    """The keys of the dialogs the complaint page draws in its current state."""
    keys = {f"undo-{v.number}" for v in visits if v.out_entry_id and not _undone(v.out_entry)}
    if c.status != Status.NOT_COVERED:
        keys.add("status")
    if c.is_open:
        keys.add("nc")
    return keys


def _undone(entry):
    try:
        return entry.reversed_by is not None
    except StockEntry.reversed_by.RelatedObjectDoesNotExist:
        return False


def _detail(request, c, token="", errors=None):
    """Render the complaint page. After a refused POST, `errors` holds the message under the dialog's key
    (status / nc / undo-VIS-0001); that dialog opens again with the message and what was typed. When that
    dialog isn't drawn any more (another tab closed the complaint or undid the parts), the message is shown
    at the top of the page instead, so a refusal is never silent."""
    errors = dict(errors or {})
    today = timezone.localdate()
    page = reverse("complaint_detail", args=[c.number])
    visits = selectors.complaint_visits(c)
    drawn = _dialogs(c, visits)
    page_errors = [
        msg if "nothing was saved" in msg.lower() else f"{msg} Nothing was saved."
        for key, msg in errors.items()
        if key not in drawn
    ]
    errors = {key: msg for key, msg in errors.items() if key in drawn}
    return render(
        request,
        "complaints/detail.html",
        {
            "c": c,
            "age": selectors.age_days(c, today),
            "awaiting": selectors.awaiting_days(c, today),
            "events": list(reversed(c.events.all())),
            "visits": visits,
            "next_statuses": [s for s in TRANSITIONS[c.status] if s != Status.NOT_COVERED],
            "reasons": NotCoveredReason.choices,
            "can_reopen": c.status == Status.CLOSED and has_role(request.user, ADMIN),
            "errors": errors,
            "page_errors": page_errors,
            "posted": request.POST if errors else {},
            "token": token or page_token(request.session, page),
        },
    )


def _complaint(number):
    return get_object_or_404(selectors.complaint_qs(), number=number)


@never_cache
@role_required(OFFICE)
def complaint_detail(request, number):
    return _detail(request, _complaint(number))


def _complaint_post(request, number, key, run):
    """What every complaint-page POST shares. `run(complaint)` calls one service and returns the success
    message. Saved: back to the complaint page. The same action again: there too, with a warning. Refused:
    the page again, with the dialog `key` open and showing the message; nothing was saved."""
    c = _complaint(number)
    page = reverse("complaint_detail", args=[number])

    def save():
        messages.success(request, run(c))
        return page

    result = guarded_post(request, save)
    if result.replayed:
        messages.warning(request, SAVED_ALREADY)
    if result.saved:
        return redirect(result.saved)
    return _detail(request, _complaint(number), result.token, {key: result.error})


@role_required(OFFICE)
@require_POST
def complaint_status(request, number):
    """Change status (only TRANSITIONS moves), or for Admin reopen a Closed complaint (to Attended)."""

    def run(c):
        before = c.get_status_display()
        c = services.change_status(
            complaint=c, to=request.POST.get("to", ""), user=request.user, note=request.POST.get("note", "")
        )
        return f"{c.number}: {before} → {c.get_status_display()}."

    return _complaint_post(request, number, "status", run)


@role_required(OFFICE)
@require_POST
def complaint_not_covered(request, number):
    def run(c):
        c = services.close_not_covered(
            complaint=c,
            reason=request.POST.get("reason", ""),
            user=request.user,
            note=request.POST.get("note", ""),
        )
        return f"{c.number} closed as Not covered ({c.get_not_covered_reason_display()})."

    return _complaint_post(request, number, "nc", run)


@role_required(OFFICE)
@require_POST
def visit_undo_parts(request, number, visit):
    """Undo a visit's parts given: a REV entry linked to the complaint (not a status event)."""
    v = get_object_or_404(Visit, number=visit, complaint__number=number)

    def run(c):
        rev = services.undo_visit_parts(visit=v, reason=request.POST.get("reason", ""), user=request.user)
        return f"Parts given on {v.number} undone. {rev.number} posted. The parts are back in stock."

    return _complaint_post(request, number, f"undo-{v.number}", run)


def _visit_lines(raw_parts, raw_collected):
    """(parts, collected) in the shapes record_visit takes. A problem names its table and the line number the
    user sees ("Failed parts collected: Line 2: …"); the piece limit is checked here for that reason too (the
    service counts only the non-blank lines)."""
    try:
        parts = parse_lines(raw_parts, "out", allow_empty=True)
    except StockError as exc:
        raise ComplaintError(f"Parts given: {exc.message}") from exc
    try:
        collected = parse_lines(raw_collected, "collect", allow_empty=True)
        for p in collected:
            if p.qty > MAX_PIECES_PER_LINE:
                raise StockError(f"Line {p.n}: quantity must be between 1 and {MAX_PIECES_PER_LINE}.")
    except StockError as exc:
        raise ComplaintError(f"Failed parts collected: {exc.message}") from exc
    return [(p.item, p.qty) for p in parts], [(p.item, p.qty, p.batch, p.pkd, p.fault) for p in collected]


def _visit_saved_message(visit):
    text = f"Visit {visit.number} saved."
    if visit.out_entry:
        text += f" Parts given: {visit.out_entry.number}."
    tags = list(visit.pieces.order_by("tag").values_list("tag", flat=True))
    if tags:
        text += f" New defective tags: {', '.join(tags)}."
    return text


@never_cache
@role_required(OFFICE)
def visit_new(request, number):
    """Record a visit: work done, parts given (one Stock OUT), failed parts collected (tagged pieces in the
    Defective store) and the status after it, in one save. A refused save comes back here with what was typed
    (both line tables included) and the message; nothing was saved."""
    complaint = get_object_or_404(Complaint.objects.select_related("site", "company"), number=number)
    if not complaint.is_open:
        messages.warning(
            request, f"{complaint.number} is {complaint.get_status_display()}, so visits can't be added."
        )
        return redirect("complaint_detail", number=number)
    first = complaint.status == Status.NOT_ATTENDED
    initial = {
        "visit_date": timezone.localdate(),
        "location": stock.default_location(),
        "technicians": [t.pk for t in complaint.technicians.filter(is_active=True)],
        "next_status": Status.ATTENDED if first else complaint.status,
    }
    form = VisitForm(request.POST or None, initial=initial, complaint=complaint)
    error, token, raw_parts, raw_collected = None, "", [], []
    if request.method == "POST":
        raw_parts, raw_collected = raw_lines(request.POST, "part"), raw_lines(request.POST, "col")

        def run():
            if not form.is_valid():
                raise ComplaintError(form.first_error())
            data = form.cleaned_data
            try:
                parts, collected = _visit_lines(raw_parts, raw_collected)
                visit = services.record_visit(
                    complaint=complaint,
                    visit_date=data["visit_date"],
                    technicians=list(data["technicians"]),
                    work_done=data["work_done"],
                    next_status=data["next_status"],
                    user=request.user,
                    location=data["location"],
                    parts=parts,
                    collected=collected,
                )
            except (ComplaintError, StockError, DefectiveError) as exc:
                raise ComplaintError(f"{exc.message} Nothing was saved.") from exc
            messages.success(request, _visit_saved_message(visit))
            return reverse("complaint_detail", args=[number])

        result = guarded_post(request, run)
        if result.replayed:
            messages.warning(request, "This visit was already saved.")
        if result.saved:
            return redirect(result.saved)
        error, token = result.error, result.token
    items, balances = stock.picker_data()
    return render(
        request,
        "complaints/visit.html",
        {
            "c": complaint,
            "form": form,
            "first": first,
            "error": error,
            "token": token or page_token(request.session, request.path),
            "items_data": items,
            "balances_data": balances,
            "initial_parts": raw_parts,
            "initial_collected": raw_collected,
            "max_pieces": MAX_PIECES_PER_LINE,
        },
    )


@role_required(OFFICE)
def complaints_dashboard(request):
    today = timezone.localdate()
    d = selectors.dashboard(today)
    base = reverse("complaints")
    for row in d["ages"]:
        row["href"] = f"{base}?{urlencode({'age': row['key']})}"
    for row in d["companies"]:
        row["href"] = f"{base}?{urlencode({'company': row['id']})}"
    for row in d["cities"]:
        row["href"] = f"{base}?{urlencode({'city': row['label']})}"
    n = d["counts"]

    def tile(status, label, icon, css, sub=""):
        return {
            "n": n[status],
            "label": label,
            "icon": icon,
            "sub": sub,
            "css": css,
            "href": f"{base}?{urlencode({'tab': status})}",
        }

    tiles = [
        tile(
            Status.NOT_ATTENDED,
            "Not attended",
            "alert-circle",
            "kpi-alert" if n[Status.NOT_ATTENDED] else "kpi-brand",
        ),
        tile(Status.ATTENDED, "Attended", "tool", "kpi-brand"),
        tile(Status.MATERIAL_CHECK, "Material need to check", "zoom-question", "kpi-brand"),
        tile(
            Status.AWAITING_MATERIAL,
            "Awaiting material",
            "hourglass",
            "kpi-wait" if n[Status.AWAITING_MATERIAL] else "kpi-brand",
        ),
        tile(Status.RESOLVED, "Resolved", "circle-check", "kpi-brand", "to be closed"),
        {
            "n": d["closed_30"],
            "label": "Closed / not covered",
            "icon": "lock",
            "sub": "last 30 days",
            "css": "kpi-brand",
            "href": f"{base}?{urlencode({'tab': FINISHED, 'closed_since': d['since'].isoformat()})}",
        },
    ]
    return render(request, "complaints/dashboard.html", {"d": d, "tiles": tiles})


@role_required(OFFICE)
def complaint_list(request):
    f = complaint_filters(request.GET)
    rows, tabs = selectors.complaint_rows(f, timezone.localdate())
    statuses, priorities = list(Status.values), list(Priority.values)
    sorters = {
        "no": lambda r: r["c"].number,
        "reported": lambda r: (r["c"].reported_on, r["c"].number),
        "site": lambda r: r["c"].site.name,
        "company": lambda r: r["c"].company.name,
        "techs": lambda r: r["techs"],
        "priority": lambda r: priorities.index(r["c"].priority),
        "status": lambda r: statuses.index(r["c"].status),
        "age": lambda r: r["age"],
    }
    table = sort_and_page(request, rows, sorters, "reported", "desc")
    return render(
        request,
        "complaints/list.html",
        {
            "f": f,
            "finished": f.tab == FINISHED,
            "since_active": bool(f.closed_since and f.tab in CLOSED_SINCE_TABS),
            "table": table,
            "tabs": tabs,
            "companies": Company.objects.filter(Q(is_active=True) | Q(complaints__isnull=False)).distinct(),
            "cities": selectors.cities(),
            "technicians": Technician.objects.all(),
            "ages": AGE_BUCKETS,
        },
    )


# ---------------------------------------------------------------- sites and technicians
# Office adds and edits both; only Admin hides or shows them (role_required on the toggle views, not just
# the template). Every write goes through guarded_post, like the rest of the module.

SITE_FIELDS = ("name", "city", "contact_name", "phone", "address")


@never_cache
@role_required(OFFICE)
def sites(request):
    q, city = _text(request.GET.get("q")), _text(request.GET.get("city"))
    rows = selectors.site_rows(q, city)
    sorters = {
        "name": lambda s: s.name.lower(),
        "city": lambda s: s.city.lower(),
        "contact": lambda s: s.contact_name.lower(),
        "open": lambda s: s.n_open,
        "total": lambda s: s.n_all,
        "last": lambda s: s.last,
    }
    table = sort_and_page(request, rows, sorters, "name")
    return render(
        request,
        "complaints/sites.html",
        {
            "table": table,
            "q": q,
            "city": city,
            "cities": selectors.cities(),
            "site_form": SiteForm(prefix="ns"),
        },
    )


def _site_page(request, site):
    """The site card: its details and every complaint filed for it (newest first)."""
    today = timezone.localdate()
    rows = [
        selectors.complaint_row(c, today, events=False)
        for c in selectors.complaint_qs(events=False).filter(site=site)
    ]
    rows.sort(key=lambda r: (r["c"].reported_on, r["c"].number), reverse=True)
    return render(
        request,
        "complaints/site_detail.html",
        {
            "site": site,
            "rows": rows,
            "n_open": sum(1 for r in rows if r["c"].is_open),
            "token": page_token(request.session, request.path),
        },
    )


@never_cache
@role_required(OFFICE)
def site_detail(request, pk):
    return _site_page(request, get_object_or_404(Site, pk=pk))


@never_cache
@role_required(OFFICE)
def site_edit(request, pk):
    site = get_object_or_404(Site, pk=pk)
    initial = {f: getattr(site, f) for f in SITE_FIELDS}
    form = SiteForm(request.POST or None, initial=initial)
    error, token = None, ""
    if request.method == "POST":

        def run():
            if not form.is_valid():
                raise ComplaintError(form.first_error())
            services.save_site(site=site, data=form.cleaned_data)
            messages.success(request, f"Site {site.name} saved.")
            return reverse("site_detail", args=[site.pk])

        result = guarded_post(request, run)
        if result.replayed:
            messages.warning(request, SAVED_ALREADY)
        if result.saved:
            return redirect(result.saved)
        error, token = result.error, result.token
    return render(
        request,
        "complaints/site_form.html",
        {
            "site": Site.objects.get(pk=pk),  # the saved name, not a half-edited one, in the title
            "form": form,
            "error": error,
            "token": token or page_token(request.session, request.path),
            "cities": selectors.cities(),
        },
    )


def _toggle(request, obj, page, noun):
    """Hide or show a site or technician (Admin only; the decorators check it). Back to `page`."""

    def run():
        services.set_active(obj, active=not obj.is_active)
        if obj.is_active:
            messages.success(request, f"{obj.name} is shown again.")
        else:
            messages.success(request, f"{obj.name} is hidden from the {noun} lists.")
        return page

    result = guarded_post(request, run)
    if result.replayed:
        messages.warning(request, SAVED_ALREADY)
    elif result.error:
        messages.error(request, result.error)
    return redirect(page)


@role_required(ADMIN)
@require_POST
def site_toggle(request, pk):
    site = get_object_or_404(Site, pk=pk)
    return _toggle(request, site, reverse("site_detail", args=[pk]), "site")


def _technicians_page(request, form, error=None, token=""):
    rows = sorted(
        selectors.technician_rows(timezone.localdate()), key=lambda t: (not t.is_active, t.name.lower())
    )
    return render(
        request,
        "complaints/technicians.html",
        {
            "rows": rows,
            "form": form,
            "error": error,
            "token": token or page_token(request.session, request.path),
        },
    )


@never_cache
@role_required(OFFICE)
def technicians(request):
    form = TechnicianForm(request.POST or None)
    if request.method != "POST":
        return _technicians_page(request, form)

    def run():
        if not form.is_valid():
            raise ComplaintError(form.first_error())
        tech = services.save_technician(**form.cleaned_data)
        messages.success(request, f"Technician {tech.name} added.")
        return reverse("technicians")

    result = guarded_post(request, run)
    if result.replayed:
        messages.warning(request, SAVED_ALREADY)
    if result.saved:
        return redirect(result.saved)
    return _technicians_page(request, form, result.error, result.token)


@never_cache
@role_required(OFFICE)
def technician_edit(request, pk):
    tech = get_object_or_404(Technician, pk=pk)
    form = TechnicianForm(request.POST or None, initial={"name": tech.name, "phone": tech.phone})
    error, token = None, ""
    if request.method == "POST":

        def run():
            if not form.is_valid():
                raise ComplaintError(form.first_error())
            saved = services.save_technician(technician=tech, **form.cleaned_data)
            messages.success(request, f"Technician {saved.name} saved.")
            return reverse("technicians")

        result = guarded_post(request, run)
        if result.replayed:
            messages.warning(request, SAVED_ALREADY)
        if result.saved:
            return redirect(result.saved)
        error, token = result.error, result.token
    return render(
        request,
        "complaints/technician_form.html",
        {
            "tech": Technician.objects.get(pk=pk),
            "form": form,
            "error": error,
            "token": token or page_token(request.session, request.path),
        },
    )


@role_required(ADMIN)
@require_POST
def technician_toggle(request, pk):
    tech = get_object_or_404(Technician, pk=pk)
    return _toggle(request, tech, reverse("technicians"), "technician")
