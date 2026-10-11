from django.urls import NoReverseMatch, reverse
from django.utils.functional import SimpleLazyObject

from .selectors import low_stock_count

# (section, [(url_name, label, tabler icon, icon css class, admin_only)])
NAV = [
    ("Overview", [("dashboard", "Dashboard", "layout-dashboard", "", False)]),
    (
        "Stock",
        [
            ("stock_in", "Stock IN", "package-import", "text-in", False),
            ("stock_out", "Stock OUT", "package-export", "text-out", False),
            ("transfer", "Transfer", "arrows-exchange", "", False),
            ("adjust", "Adjust count", "adjustments-horizontal", "", False),
        ],
    ),
    (
        "Reports",
        [
            ("current_stock", "Current stock", "building-warehouse", "", False),
            ("movements", "Movements", "history", "", False),
            ("low_stock", "Low stock", "alert-triangle", "", False),
        ],
    ),
    ("Setup", [("items", "Items", "box", "", False), ("masters", "Masters", "settings", "", True)]),
]
EXTRA_URLS = ["global_search"]
# URL names that should highlight a menu entry other than their own.
ACTIVE_ALIASES = {
    "item_new": "items",
    "item_edit": "items",
    "item_detail": "items",
    "entry_detail": "movements",
}


def _url(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def nav(request):
    """Sidebar sections, URLs by name (None until built), active entry, and the low-stock count."""
    if not request.user.is_authenticated:
        return {}
    urls = {name: _url(name) for _, entries in NAV for name, *_ in entries}
    urls.update({name: _url(name) for name in EXTRA_URLS})
    current = request.resolver_match.url_name if request.resolver_match else ""
    active = ACTIVE_ALIASES.get(current, current)
    sections = [
        (
            title,
            [
                {
                    "name": n,
                    "label": label,
                    "icon": ic,
                    "cls": cls,
                    "admin_only": admin,
                    "url": urls[n],
                    "active": n == active,
                }
                for n, label, ic, cls, admin in entries
            ],
        )
        for title, entries in NAV
    ]
    return {"nav_sections": sections, "nav_urls": urls, "nav_low_count": SimpleLazyObject(low_stock_count)}
