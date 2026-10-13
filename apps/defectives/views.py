from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tables import sort_and_page
from apps.core.tokens import EXPIRED, already_saved, is_issued, new_token, spend_token
from apps.inventory import selectors as stock
from apps.inventory.entry_lines import parse_lines, raw_lines
from apps.inventory.filters import _obj
from apps.inventory.models import Company, Location
from apps.inventory.services import StockError

from . import selectors, services
from .filters import batch_filters
from .forms import DispatchForm, MarkDefectiveForm, SettleForm
from .models import BATCH_LABELS, BatchStatus, DefectivePiece, Outcome, PieceStatus, ReturnBatch
from .services import MAX_PIECES_PER_LINE, DefectiveError, normalise_tag
from .templatetags.defective_tags import OUTCOME_STYLE

SAVED_ALREADY = "This was already saved."


def _mark_lines(rows):
    """[(item, qty, fault)] for mark_defective. The piece limit is checked here too, so the error names the
    line number the user sees (the service counts only the non-blank lines)."""
    parsed = parse_lines(rows, "mark")
    for p in parsed:
        if p.qty > MAX_PIECES_PER_LINE:
            raise StockError(f"Line {p.n}: quantity must be between 1 and {MAX_PIECES_PER_LINE}.")
    return [(p.item, p.qty, p.fault) for p in parsed]


@role_required(OFFICE)
def mark_defective(request):
    """Faulty pieces found in good stock: a transfer into the Defective store, one tag per piece."""
    initial = {"entry_date": timezone.localdate(), "location": stock.default_location()}
    form = MarkDefectiveForm(request.POST or None, initial=initial)
    error, lines, token = None, [], ""
    if request.method == "POST":
        lines = raw_lines(request.POST)
        token = request.POST.get("entry_token", "")
        done = already_saved(request.session, token)
        if done:
            messages.warning(request, SAVED_ALREADY)
            return redirect("entry_detail", number=done)
        if not is_issued(request.session, token):
            token, error = "", EXPIRED
        elif form.is_valid():
            try:
                entry, pieces = services.mark_defective(
                    location=form.cleaned_data["location"],
                    lines=_mark_lines(lines),
                    entry_date=form.cleaned_data["entry_date"],
                    user=request.user,
                )
            except (StockError, DefectiveError) as exc:
                error = f"{exc.message} Nothing was saved."
            else:
                spend_token(request.session, token, entry.number)
                tags = ", ".join(p.tag for p in pieces)
                plural = "s" if len(pieces) > 1 else ""
                messages.success(request, f"{entry.number} saved. New defective tag{plural}: {tags}.")
                return redirect("entry_detail", number=entry.number)
        else:
            error = form.first_error()
    elif request.GET.get("item", "").isdecimal():
        lines = [{"item": request.GET["item"], "qty": "", "fault": ""}]
    items, balances = stock.picker_data()
    return render(
        request,
        "defectives/mark.html",
        {
            "form": form,
            "error": error,
            "token": token or new_token(request.session),
            "items_data": items,
            "balances_data": balances,
            "initial_lines": lines,
            "store_name": Location.defective_store().name,
            "max_pieces": MAX_PIECES_PER_LINE,
        },
    )


# ---------------------------------------------------------------- return batches and the piece card


def _back(request, fallback):
    """Where to go after a POST: the page's `next` (this site only), else `fallback`."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def _replayed(request):
    """A redirect to what this POST's one-time token already saved (a double submit or Back + resubmit)."""
    done = already_saved(request.session, request.POST.get("entry_token", ""))
    if done:
        messages.warning(request, SAVED_ALREADY)
        return redirect(done)
    return None


@role_required(OFFICE)
def piece_detail(request, tag):
    """The piece card: details, every batch it went into (each with that batch's answer) and its timeline."""
    piece = get_object_or_404(selectors.pieces_qs().select_related("item__spare_type"), tag=tag)
    events = list(piece.events.select_related("by", "entry").order_by("-at", "-id"))
    entries = list(dict.fromkeys(ev.entry for ev in reversed(events) if ev.entry_id))
    drafts = []
    if piece.status == PieceStatus.IN_STORE:
        drafts = ReturnBatch.objects.filter(status=BatchStatus.DRAFT, company=piece.company).order_by("-id")
    return render(
        request,
        "defectives/piece_detail.html",
        {
            "piece": piece,
            "events": events,
            "entries": entries,
            "lines": selectors.piece_batch_lines(piece),
            "drafts": drafts,
            "token": new_token(request.session),
        },
    )


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


@role_required(OFFICE)
def batch_new(request):
    """Pick a company, tick its pieces in store, create a draft batch."""
    source = request.POST if request.method == "POST" else request.GET
    company = _obj(Company, source.get("company"))
    ticked = set(source.getlist("tag"))
    error, token = None, ""
    if request.method == "POST":
        replay = _replayed(request)
        if replay:
            return replay
        token = request.POST.get("entry_token", "")
        if not is_issued(request.session, token):
            token, error = "", EXPIRED
        else:
            chosen = list(DefectivePiece.objects.filter(tag__in=ticked))
            try:
                batch = services.create_batch(
                    company=company, user=request.user, pieces=chosen, note=request.POST.get("note", "")
                )
            except (DefectiveError, StockError) as exc:
                error = f"{exc.message} Nothing was saved."
            else:
                url = reverse("batch_detail", args=[batch.number])
                spend_token(request.session, token, url)
                made = f"Draft batch {batch.number} created for {batch.company.name}"
                messages.success(request, f"{made} with {len(chosen)} piece(s).")
                return redirect(url)
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
            "token": token or new_token(request.session),
        },
    )


def _detail(request, batch, token="", errors=None):
    """Render the batch page. After a refused POST, `errors` holds the message under the form's key
    (add / remove / dispatch / settle) and that form shows what was posted, so nothing is typed twice."""
    errors = errors or {}
    posted = request.POST if errors else {}
    lines = selectors.batch_lines(batch)
    settled = sum(1 for line in lines if line.outcome)
    today = timezone.localdate()
    available = []
    if batch.is_draft:
        available = list(
            selectors.pieces_qs().filter(company=batch.company, status=PieceStatus.IN_STORE).order_by("tag")
        )
    return render(
        request,
        "defectives/batch_detail.html",
        {
            "batch": batch,
            "lines": lines,
            "settled": settled,
            "groups": selectors.answer_groups(lines),
            "label": selectors.batch_label(batch, len(lines), settled),
            "sent": [ln for ln in lines if not ln.outcome and ln.piece.status == PieceStatus.SENT],
            "waiting": (today - batch.dispatched_on).days if batch.dispatched_on else 0,
            "today": today,
            "available": available,
            "locations": Location.objects.good().filter(is_active=True),
            "couriers": selectors.courier_suggestions(),
            "outcome_choices": [(v, label, OUTCOME_STYLE[v][1]) for v, label in Outcome.choices],
            "errors": errors,
            "posted": posted,
            "ticked": set(posted.getlist("tag")) if "settle" in errors else set(),
            "token": token or new_token(request.session),
        },
    )


def _batch(number):
    return get_object_or_404(ReturnBatch.objects.select_related("company", "dispatch_entry"), number=number)


@role_required(OFFICE)
def batch_detail(request, number):
    return _detail(request, _batch(number))


def _batch_post(request, number, form_key, run):
    """What every batch-page POST shares.

    A replayed token goes to what it saved; a token the page never issued saves nothing. `run(batch)` calls
    one service and returns the success message. A DefectiveError or StockError it raises is shown inline on
    the batch page, by the form that was sent (or, for a POST from another page with `next`, as a message
    there).
    """
    batch = _batch(number)
    back = _back(request, reverse("batch_detail", args=[number]))
    replay = _replayed(request)
    if replay:
        return replay
    token = request.POST.get("entry_token", "")
    if not is_issued(request.session, token):
        token, error = "", EXPIRED
    else:
        try:
            text = run(batch)
        except (DefectiveError, StockError) as exc:
            error = exc.message
        else:
            spend_token(request.session, token, back)
            messages.success(request, text)
            return redirect(back)
    if request.POST.get("next"):
        messages.error(request, error)
        return redirect(back)
    return _detail(request, _batch(number), token, {form_key: error})


@role_required(OFFICE)
@require_POST
def batch_add(request, number):
    def run(batch):
        typed = normalise_tag(request.POST.get("tag_text", ""))
        tags = [typed] if typed else request.POST.getlist("tag")
        if typed and not DefectivePiece.objects.filter(tag=typed).exists():
            raise DefectiveError(f"There is no piece tagged {typed}.")
        if not tags:
            raise DefectiveError("Type a tag (e.g. DEF-0042) or tick pieces to add.")
        chosen = list(DefectivePiece.objects.filter(tag__in=tags))
        services.add_pieces(batch=batch, pieces=chosen, user=request.user)
        added = ", ".join(sorted(tags)) if len(tags) <= 3 else f"{len(tags)} pieces"
        return f"{added} added to {batch.number}."

    return _batch_post(request, number, "add", run)


@role_required(OFFICE)
@require_POST
def batch_remove(request, number):
    def run(batch):
        tag = request.POST.get("tag", "")
        chosen = list(DefectivePiece.objects.filter(tag=tag))
        services.remove_pieces(batch=batch, pieces=chosen, user=request.user)
        return f"{tag} removed from {batch.number}. It is back in store."

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
        chosen = list(DefectivePiece.objects.filter(tag__in=request.POST.getlist("tag")))
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
