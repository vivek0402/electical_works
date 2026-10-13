from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tokens import page_token

from .. import selectors
from ..models import GOOD_OUTCOMES, BatchStatus, Outcome, PieceStatus, ReturnBatch
from ..services import normalise_tag

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
            "token": page_token(request.session, request.path),
        },
    )
