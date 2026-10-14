from django import template
from django.utils.html import format_html

from apps.core.templatetags.core_tags import st_badge

from ..models import Priority, Status

register = template.Library()

# Red = needs attention, amber = waiting on someone, green = done well, slate = neutral / finished.
STATUS_STYLE = {
    Status.NOT_ATTENDED: ("st-alert", "alert-circle"),
    Status.ATTENDED: ("st-neutral", "tool"),
    Status.MATERIAL_CHECK: ("st-neutral", "zoom-question"),
    Status.AWAITING_MATERIAL: ("st-wait", "hourglass"),
    Status.RESOLVED: ("st-ok", "circle-check"),
    Status.CLOSED: ("st-done", "lock"),
    Status.NOT_COVERED: ("st-done", "ban"),
}


@register.filter
def status_badge(status):
    css, icon = STATUS_STYLE[status]
    return st_badge(css, icon, Status(status).label)


@register.filter
def status_css(status):
    return STATUS_STYLE[status][0]


@register.filter
def status_icon(status):
    return STATUS_STYLE[status][1]


@register.filter
def priority_badge(priority):
    if priority == Priority.URGENT:
        return st_badge("st-alert", "urgent", "Urgent")
    if priority == Priority.HIGH:
        return st_badge("st-wait", "arrow-up", "High")
    return format_html('<span class="text-secondary">{}</span>', "Normal")


@register.simple_tag
def age_badge(days, is_open):
    """'12 d', or a red badge when an open complaint is older than 15 days."""
    if is_open and days > 15:
        return format_html('<span class="badge st st-alert">{} d</span>', days)
    return f"{days} d"
