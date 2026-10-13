from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tables import sort_and_page
from apps.core.tokens import guarded_post, page_token
from apps.inventory.filters import _text
from apps.inventory.models import Company
from apps.inventory.services import StockError

from .. import selectors, services
from ..filters import piece_filters
from ..models import (
    GOOD_OUTCOMES,
    BatchStatus,
    Outcome,
    PieceStatus,
    ReturnBatch,
    ScrapReason,
    Source,
)
from ..services import DefectiveError, normalise_tag
from .common import SAVED_ALREADY, back_url, pieces_by_tag

WENT_INTO = {Outcome.REPLACED: "Replacement went into", Outcome.REPAIRED: "Repaired piece went into"}


@never_cache
@role_required(OFFICE)
def piece_detail(request, tag):
    """The piece card: details, every batch it went into (each with that batch's answer) and its timeline."""
    canonical = normalise_tag(tag)
    if canonical != tag:
        return redirect("piece_detail", tag=canonical)
    piece = get_object_or_404(selectors.pieces_qs().select_related("item__spare_type"), tag=tag)
    events = list(piece.events.select_related("by", "entry").order_by("-at", "-id"))
    entries = list(dict.fromkeys(ev.entry for ev in reversed(events) if ev.entry_id))
    lines = selectors.piece_batch_lines(piece)  # newest batch first
    answer = next((line for line in lines if line.outcome), None)  # the newest answered line
    drafts = []
    if piece.status == PieceStatus.IN_STORE:
        drafts = list(
            ReturnBatch.objects.filter(status=BatchStatus.DRAFT, company=piece.company).order_by("-id")
        )
    return render(
        request,
        "defectives/piece_detail.html",
        {
            "piece": piece,
            "events": events,
            "entries": entries,
            "lines": lines,
            "went_into": answer if answer and answer.outcome in GOOD_OUTCOMES else None,
            "went_into_label": WENT_INTO.get(answer.outcome, "") if answer else "",
            "drafts": drafts,
            "scrap_reasons": ScrapReason.choices,
            "token": page_token(request.session, request.path),
        },
    )


@never_cache
@role_required(OFFICE)
def defective_pieces(request):
    f = piece_filters(request.GET)
    rows = selectors.piece_rows(f)
    order = list(PieceStatus.values)
    sorters = {
        "tag": lambda p: (len(p.tag), p.tag),  # DEF-10000 after DEF-9999
        "code": lambda p: p.item.code,
        "company": lambda p: p.company.name,
        "source": lambda p: p.source,
        "collected": lambda p: (p.collected_on, p.tag),
        "bpkd": lambda p: p.batch_code,
        "status": lambda p: order.index(p.status),
        "rb": lambda p: p.return_batch.number if p.return_batch_id else "",
    }
    table = sort_and_page(request, rows, sorters, "tag", "desc")
    return render(
        request,
        "defectives/pieces.html",
        {
            "f": f,
            "table": table,
            "companies": Company.objects.filter(
                Q(is_active=True) | Q(pk=f.company.pk if f.company else None)
            ),
            "items": selectors.piece_items(),
            "statuses": PieceStatus.choices,
            "sources": Source.choices,
            "drafts": ReturnBatch.objects.filter(status=BatchStatus.DRAFT)
            .select_related("company")
            .annotate(n=Count("lines"))
            .order_by("-id"),
            "scrap_reasons": ScrapReason.choices,
            "token": page_token(request.session, request.path),
        },
    )


def _add_to_batch(request, chosen):
    """Add the ticked pieces to the chosen draft batch, or to a new batch for their company."""
    names = sorted({p.company.name for p in chosen})
    if len(names) > 1:
        raise DefectiveError(
            f"The ticked pieces belong to {len(names)} companies ({', '.join(names)}). A return batch holds "
            "one company's pieces only. Filter the list by company, or untick the others."
        )
    target = _text(request.POST.get("batch", "new"))
    if target == "new":
        return services.create_batch(company=chosen[0].company, user=request.user, pieces=chosen)
    batch = ReturnBatch.objects.filter(number=target).first()
    if batch is None:
        raise DefectiveError("Choose a draft batch.")
    services.add_pieces(batch=batch, pieces=chosen, user=request.user)
    return batch


@role_required(OFFICE)
@require_POST
def pieces_bulk(request):
    """Bulk actions from the pieces list and the piece card: add ticked pieces to a batch, or scrap them.

    A refusal comes back to the page the form was on (`next`) as a red message and nothing is saved.
    """
    back = back_url(request, reverse("defective_pieces"))

    def run():
        try:
            chosen = pieces_by_tag(request.POST.getlist("tag"))
            if not chosen:
                raise DefectiveError("Tick at least one piece.")
            action = request.POST.get("action", "")
            if action == "batch":
                batch = _add_to_batch(request, chosen)
                messages.success(request, f"{len(chosen)} piece(s) added to {batch.number}.")
                return reverse("batch_detail", args=[batch.number])
            if action == "scrap":
                services.scrap(
                    pieces=chosen,
                    reason=request.POST.get("reason", ""),
                    note=request.POST.get("note", ""),
                    user=request.user,
                )
                tags = ", ".join(p.tag for p in chosen)
                messages.success(request, f"{len(chosen)} piece(s) scrapped: {tags}.")
                return back
            raise DefectiveError("Choose what to do with the ticked pieces.")
        except StockError as exc:
            raise DefectiveError(exc.message) from exc

    result = guarded_post(request, run)
    if result.replayed:
        messages.warning(request, SAVED_ALREADY)
    if result.saved:
        return redirect(result.saved)
    messages.error(request, result.error)
    return redirect(back)
