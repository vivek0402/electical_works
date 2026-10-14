from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN, OFFICE, has_role
from apps.core.tokens import guarded_post, page_token

from . import selectors, services
from .forms import ComplaintForm, SiteForm
from .models import TRANSITIONS, NotCoveredReason, Status, Visit
from .services import ComplaintError

SAVED_ALREADY = "This was already saved."


@never_cache
@role_required(OFFICE)
def complaint_new(request):
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


def _detail(request, c, token="", errors=None):
    """Render the complaint page. After a refused POST, `errors` holds the message under the dialog's key
    (status / nc / undo-VIS-0001); that dialog opens again with the message and what was typed."""
    errors = errors or {}
    today = timezone.localdate()
    page = reverse("complaint_detail", args=[c.number])
    return render(
        request,
        "complaints/detail.html",
        {
            "c": c,
            "age": selectors.age_days(c, today),
            "awaiting": selectors.awaiting_days(c, today),
            "events": list(reversed(c.events.all())),
            "visits": selectors.complaint_visits(c),
            "next_statuses": [s for s in TRANSITIONS[c.status] if s != Status.NOT_COVERED],
            "reasons": NotCoveredReason.choices,
            "can_reopen": c.status == Status.CLOSED and has_role(request.user, ADMIN),
            "errors": errors,
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
