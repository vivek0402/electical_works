"""Helpers shared by the defectives views."""

from django.utils.http import url_has_allowed_host_and_scheme

from ..models import DefectivePiece
from ..services import DefectiveError, normalise_tag

SAVED_ALREADY = "This was already saved."


def back_url(request, fallback):
    """Where to go after a POST: the page's `next` (this site only, same scheme), else `fallback`."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


def pieces_by_tag(tags):
    """The pieces for typed or ticked tags, in the order given (repeats dropped). Refuses a tag that no piece
    has, so a stale page or a typo is never silently skipped. An empty list is left to the service."""
    wanted = list(dict.fromkeys(normalise_tag(t) for t in tags if (t or "").strip()))
    found = {p.tag: p for p in DefectivePiece.objects.filter(tag__in=wanted).select_related("company")}
    for tag in wanted:
        if tag not in found:
            raise DefectiveError(f"There is no piece tagged {tag}.")
    return [found[tag] for tag in wanted]
