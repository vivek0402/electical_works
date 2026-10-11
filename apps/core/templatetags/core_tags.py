from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def url_with(context, **changes):
    """Current query string with some params replaced (None removes); keeps filters across sort/page links."""
    params = context["request"].GET.copy()
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return "?" + params.urlencode()


@register.filter
def qty(value):
    """Zero shows as a faint 0 so real numbers stand out."""
    return value if value else mark_safe('<span class="zero">0</span>')


@register.filter
def lines_summary(entry):
    """'EIO6006 × 3' for single-item entries, else 'N items'."""
    lines = list(entry.lines.all())
    codes = {line.item.code for line in lines}
    if len(codes) == 1:
        if entry.kind == "TRF":
            moved = sum(line.qty for line in lines if line.qty > 0)
        else:
            moved = sum(abs(line.qty) for line in lines)
        return format_html('<span class="code">{}</span> × {}', next(iter(codes)), moved)
    return f"{len(codes)} items"


@register.filter
def entry_locations(entry):
    seen = []
    for line in entry.lines.all():
        if line.location.name not in seen:
            seen.append(line.location.name)
    return " → ".join(seen)


@register.filter
def get_item(mapping, key):
    return mapping.get(key, 0) if mapping else 0
