from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tokens import EXPIRED, already_saved, is_issued, new_token, spend_token
from apps.inventory import selectors as stock
from apps.inventory.entry_lines import parse_lines, raw_lines
from apps.inventory.models import Location
from apps.inventory.services import StockError

from . import services
from .forms import MarkDefectiveForm
from .services import MAX_PIECES_PER_LINE, DefectiveError


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
            messages.warning(request, "This was already saved.")
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
