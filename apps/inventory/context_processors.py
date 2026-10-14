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
    (
        "Complaints",
        [  # entries whose page isn't built yet render disabled (their URL name doesn't resolve)
            ("complaints_dashboard", "Dashboard", "message-report", "", False),
            ("complaints", "All complaints", "list-details", "", False),
            ("complaint_new", "New complaint", "plus", "", False),
            ("sites", "Sites", "building", "", False),
            ("technicians", "Technicians", "users", "", False),
        ],
    ),
    (
        "Defectives",
        [  # entries whose page isn't built yet render disabled (their URL name doesn't resolve)
            ("defectives_dashboard", "Dashboard", "recycle", "", False),
            ("defective_pieces", "Pieces", "tags", "", False),
            ("mark_defective", "Mark defective", "alert-octagon", "", False),
            ("return_batches", "Return batches", "truck-return", "", False),
        ],
    ),
    ("Setup", [("items", "Items", "box", "", False), ("masters", "Masters", "settings", "", True)]),
]
EXTRA_URLS = ["global_search"]
# Menu entries that open on a filtered list, so the badge beside them counts exactly the rows shown.
NAV_QUERY = {"defective_pieces": "?status=IN_STORE"}
# URL names that should highlight a menu entry other than their own.
ACTIVE_ALIASES = {
    "item_new": "items",
    "item_edit": "items",
    "item_detail": "items",
    "entry_detail": "movements",
    "batch_new": "return_batches",
    "batch_detail": "return_batches",
    "piece_detail": "defective_pieces",
    "complaint_detail": "complaints",
    "visit_new": "complaints",
    "site_detail": "sites",
    "site_edit": "sites",
    "technician_edit": "technicians",
}


def _url(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def _open_complaints():
    """Open complaints (the "All complaints" list opens on the Open tab), from the shared status counts."""
    from apps.complaints.models import OPEN_STATUSES  # imported here: complaints depends on inventory
    from apps.complaints.selectors import status_counts

    counts = status_counts()
    return sum(counts[s] for s in OPEN_STATUSES)


def _pieces_in_store():
    """Pieces In store (the "Pieces" menu entry opens on that filter), from the shared piece counts."""
    from apps.defectives.selectors import piece_counts

    return piece_counts()["in_store"]


def nav(request):
    """Sidebar sections, URLs by name (None until built), active entry, and the menu badges' counts.

    Each badge is lazy: its one counting query runs only if the template shows it."""
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
                    "url": urls[n] and urls[n] + NAV_QUERY.get(n, ""),
                    "active": n == active,
                }
                for n, label, ic, cls, admin in entries
            ],
        )
        for title, entries in NAV
    ]
    return {
        "nav_sections": sections,
        "nav_urls": urls,
        "nav_low_count": SimpleLazyObject(low_stock_count),
        "nav_open_complaints": SimpleLazyObject(_open_complaints),
        "nav_pieces_in_store": SimpleLazyObject(_pieces_in_store),
    }
