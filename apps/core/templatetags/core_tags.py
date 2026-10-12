from django import template
from django.urls import reverse
from django.utils.html import format_html, format_html_join
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


@register.inclusion_tag("core/_sort_th.html", takes_context=True)
def sort_th(context, key, label, num=False):
    """Column header that sorts by `key`; clicking again flips the direction."""
    table = context["table"]
    active = table["sort"] == key
    new_dir = "desc" if active and table["dir"] == "asc" else "asc"
    return {
        "href": url_with(context, sort=key, dir=new_dir, page=None),
        "label": label,
        "num": num,
        "cls": table["dir"] if active else "",
    }


@register.simple_tag(takes_context=True)
def hidden_params(context, exclude=""):
    """Hidden inputs for the current GET params (minus `exclude`), so a small form keeps the other filters."""
    skip = set(exclude.split(","))
    return format_html_join(
        "",
        '<input type="hidden" name="{}" value="{}">',
        ((k, v) for k, v in context["request"].GET.items() if k not in skip),
    )


@register.simple_tag(takes_context=True)
def export_url(context, name, *args):
    """reverse(name) + the current GET params (minus paging/sorting), so the download matches the screen."""
    params = context["request"].GET.copy()
    for key in ("page", "size", "sort", "dir"):
        params.pop(key, None)
    query = params.urlencode()
    return reverse(name, args=args) + (f"?{query}" if query else "")
