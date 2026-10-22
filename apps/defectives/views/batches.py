from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tables import sort_and_page
from apps.core.tokens import guarded_post, page_token
from apps.inventory.filters import _obj
from apps.inventory.models import Company, Location
from apps.inventory.services import StockError

from .. import selectors, services
from ..filters import batch_filters
from ..forms import DispatchForm, SettleForm
from ..models import BATCH_LABELS, Outcome, PieceStatus, ReturnBatch
from ..services import DefectiveError
from ..templatetags.defective_tags import OUTCOME_STYLE
from .common import SAVED_ALREADY, back_url, pieces_by_tag


def _tags(pieces):
    """'DEF-0001, DEF-0002' for up to three pieces, else 'N pieces'."""
    return ", ".join(p.tag for p in pieces) if len(pieces) <= 3 else f"{len(pieces)} pieces"


@role_required(OFFICE)
def return_batches(request):
    f = batch_filters(request.GET)
    rows = selectors.batch_rows(f, timezone.localdate())
    sorters = {
        "no": lambda r: r["batch"].number,
        "company": lambda r: r["batch"].company.name,
        "created": lambda r: r["batch"].created_on,
        "status": lambda r: BATCH_LABELS.index(r["label"]),
        "pieces": lambda r: r["batch"].n_lines,
        "settled": lambda r: r["batch"].n_settled,
        "disp": lambda r: r["batch"].dispatched_on,
        "wait": lambda r: r["waiting"] if r["waiting"] is not None else -1,
    }
    table = sort_and_page(request, rows, sorters, "no", "desc")
    return render(
        request,
        "defectives/batches.html",
        {"f": f, "table": table, "companies": Company.objects.filter(is_active=True), "labels": BATCH_LABELS},
    )


@never_cache
@role_required(OFFICE)
def batch_new(request):
    """Pick a company, tick its pieces in store, create a draft batch."""
    source = request.POST if request.method == "POST" else request.GET
    company = _obj(Company, source.get("company"))
    ticked = set(source.getlist("tag"))
    error, token = None, ""
    if request.method == "POST":

        def run():
            try:
                chosen = pieces_by_tag(source.getlist("tag"))
                batch = services.create_batch(
                    company=company, user=request.user, pieces=chosen, note=request.POST.get("note", "")
                )
            except (DefectiveError, StockError) as exc:
                raise DefectiveError(f"{exc.message} Nothing was saved.") from exc
            made = f"Draft batch {batch.number} created for {batch.company.name}"
            messages.success(request, f"{made} with {batch.lines.count()} piece(s).")
            return reverse("batch_detail", args=[batch.number])

        result = guarded_post(request, run)
        if result.replayed:
            messages.warning(request, SAVED_ALREADY)
        if result.saved:
            return redirect(result.saved)
        error, token = result.error, result.token
    available = []
    if company:
        available = list(
            selectors.pieces_qs().filter(company=company, status=PieceStatus.IN_STORE).order_by("tag")
        )
    companies = list(
        Company.objects.filter(defective_pieces__status=PieceStatus.IN_STORE).distinct().order_by("name")
    )
    if company and company not in companies:
        companies.append(company)
    return render(
        request,
        "defectives/batch_new.html",
        {
            "companies": companies,
            "company": company,
            "ticked": ticked,
            "available": available,
            "note": source.get("note", ""),
            "error": error,
            "token": token or page_token(request.session, reverse("batch_new")),
        },
    )


def _batch(number):
    return get_object_or_404(ReturnBatch.objects.select_related("company", "dispatch_entry"), number=number)


def _detail(request, batch, token="", errors=None):
    """Render the batch page. After a refused POST, `errors` holds the message under the form's key
    (add / remove / dispatch / settle) and that form shows what was posted, so nothing is typed twice."""
    errors = dict(errors or {})
    posted = request.POST if errors else {}
    lines = selectors.batch_lines(batch)
    settled = sum(1 for line in lines if line.outcome)
    sent = [ln for ln in lines if not ln.outcome and ln.piece.status == PieceStatus.SENT]
    # A refusal is never silent: when the form that was posted isn't drawn any more (another tab dispatched
    # or settled the batch), its message shows at the top of the page, like the complaint page does.
    drawn = {"add", "remove", "dispatch"} if batch.is_draft else ({"settle"} if sent else set())
    for key in [k for k in errors if k not in drawn]:
        messages.error(request, errors.pop(key))
    today = timezone.localdate()
    available = []
    if batch.is_draft:
        available = list(
            selectors.pieces_qs().filter(company=batch.company, status=PieceStatus.IN_STORE).order_by("tag")
        )
    page = reverse("batch_detail", args=[batch.number])
    return render(
        request,
        "defectives/batch_detail.html",
        {
            "batch": batch,
            "lines": lines,
            "settled": settled,
            "groups": selectors.answer_groups(lines),
            "label": selectors.batch_label(batch, len(lines), settled),
            "sent": sent,
            "waiting": (today - batch.dispatched_on).days if batch.dispatched_on else 0,
            "today": today,
            "available": available,
            "locations": list(Location.objects.good().filter(is_active=True)),
            "couriers": selectors.courier_suggestions(),
            "outcome_choices": [(v, label, OUTCOME_STYLE[v][1]) for v, label in Outcome.choices],
            "errors": errors,
            "posted": posted,
            "ticked": set(posted.getlist("tag")) if {"settle", "add"} & errors.keys() else set(),
            # An add error shows by the tag box, unless the pieces were ticked in the list below it.
            "add_error_typed": "add" in errors and (posted.get("tag_text") or not posted.getlist("tag")),
            "token": token or page_token(request.session, page),
        },
    )


@never_cache
@role_required(OFFICE)
def batch_detail(request, number):
    return _detail(request, _batch(number))


def _batch_post(request, number, form_key, run):
    """What every batch-page POST shares.

    `run(batch)` calls one service and returns the success message. guarded_post runs it once per token and
    action: the same action again goes to where the first one went; another action with a spent token (Back,
    then act on a different row) saves nothing and shows the expired message. A refusal is shown inline on
    the batch page, by the form that was sent (or, for a POST from another page with `next`, as a message
    there).
    """
    batch = _batch(number)
    back = back_url(request, reverse("batch_detail", args=[number]))

    def save():
        messages.success(request, run(batch))
        return back

    result = guarded_post(request, save)
    if result.replayed:
        messages.warning(request, SAVED_ALREADY)
    if result.saved:
        return redirect(result.saved)
    if request.POST.get("next"):
        messages.error(request, result.error)
        return redirect(back)
    return _detail(request, _batch(number), result.token, {form_key: result.error})


@role_required(OFFICE)
@require_POST
def batch_add(request, number):
    def run(batch):
        typed = request.POST.get("tag_text", "").strip()
        tags = [typed] if typed else request.POST.getlist("tag")
        if not tags:
            raise DefectiveError("Type a tag (e.g. DEF-0042) or tick pieces to add.")
        chosen = pieces_by_tag(tags)
        services.add_pieces(batch=batch, pieces=chosen, user=request.user)
        return f"{_tags(chosen)} added to {batch.number}."

    return _batch_post(request, number, "add", run)


@role_required(OFFICE)
@require_POST
def batch_remove(request, number):
    def run(batch):
        chosen = pieces_by_tag([request.POST.get("tag", "")])
        services.remove_pieces(batch=batch, pieces=chosen, user=request.user)
        return f"{_tags(chosen)} removed from {batch.number}. It is back in store."

    return _batch_post(request, number, "remove", run)


@role_required(OFFICE)
@require_POST
def batch_dispatch(request, number):
    def run(batch):
        form = DispatchForm(request.POST)
        if not form.is_valid():
            raise DefectiveError(form.first_error())
        entry = services.dispatch(batch=batch, user=request.user, **form.cleaned_data)
        return f"{batch.number} dispatched. Stock OUT {entry.number} posted from the Defective store."

    return _batch_post(request, number, "dispatch", run)


@role_required(OFFICE)
@require_POST
def batch_settle(request, number):
    """One outcome per submit: settle posts one entry per call."""

    def run(batch):
        form = SettleForm(request.POST)
        if not form.is_valid():
            raise DefectiveError(form.first_error())
        data = form.cleaned_data
        chosen = pieces_by_tag(request.POST.getlist("tag"))
        entries = services.settle(
            batch=batch,
            pieces=chosen,
            outcome=data["outcome"],
            settled_on=data["settled_on"],
            to_location=data["to_location"],
            user=request.user,
        )
        made = f" Entries: {', '.join(e.number for e in entries)}." if entries else ""
        return f"{len(chosen)} piece(s) settled as {Outcome(data['outcome']).label}.{made}"

    return _batch_post(request, number, "settle", run)
