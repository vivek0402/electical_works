from django import template
from django.utils.html import format_html

from apps.core.templatetags.core_tags import st_badge

from ..models import Outcome, PieceStatus

register = template.Library()

# (css class, Tabler icon) per value.
# Red = needs attention, amber = waiting, green = done well, slate = neutral.
PIECE_STYLE = {
    PieceStatus.IN_STORE: ("st-neutral", "building-warehouse"),
    PieceStatus.IN_BATCH: ("st-neutral", "packages"),
    PieceStatus.SENT: ("st-wait", "truck"),
    PieceStatus.SETTLED: ("st-ok", "circle-check"),
    PieceStatus.SCRAPPED: ("st-done", "trash"),
}
OUTCOME_STYLE = {
    Outcome.REPLACED: ("st-ok", "replace"),
    Outcome.REPAIRED: ("st-ok", "tool"),
    Outcome.REJECTED_RETURNED: ("st-alert", "arrow-back"),
    Outcome.REJECTED_SCRAPPED: ("st-alert", "trash"),
}
BATCH_STYLE = {
    "Draft": ("st-neutral", "pencil"),
    "Dispatched": ("st-wait", "truck"),
    "Partly settled": ("st-wait", "progress-check"),
    "Settled": ("st-ok", "circle-check"),
}


@register.filter
def piece_badge(status):
    css, icon = PIECE_STYLE[status]
    return st_badge(css, icon, PieceStatus(status).label)


@register.filter
def piece_css(status):
    return PIECE_STYLE[status][0]


@register.filter
def piece_icon(status):
    return PIECE_STYLE[status][1]


@register.filter
def outcome_badge(outcome):
    if not outcome:
        return ""
    css, icon = OUTCOME_STYLE[outcome]
    return st_badge(css, icon, Outcome(outcome).label)


@register.filter
def batch_badge(label):
    css, icon = BATCH_STYLE[label]
    return st_badge(css, icon, label)


@register.filter
def pkd_month(value):
    return f"{value:%m-%Y}" if value else ""


@register.filter
def waiting_badge(days):
    """'12 days', or a red badge after 30 days. Empty when nothing is waiting."""
    if days is None:
        return ""
    if days > 30:
        return format_html(
            '<span class="badge st st-alert"><i class="ti ti-alert-triangle"></i>{} days</span>', days
        )
    return f"{days} days"
