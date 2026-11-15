from django.urls import NoReverseMatch, reverse
from django.utils.functional import SimpleLazyObject

from apps.accounts.roles import ADMIN, has_role

from .selectors import low_stock_count

# The five top-bar sections. Each has a key, a label, the url name its pill opens, the sub-tabs shown under
# page title on list and overview pages (url_name, label, admin_only), and the hero actions shown on those
# same pages (url_name, label, tabler icon, css class). Form and detail pages show a back link instead.
SECTIONS = [
    {
        "key": "home",
        "label": "Home",
        "open": "dashboard",
        "tabs": [("dashboard", "Home", False)],
        "actions": [
            ("stock_in", "Stock IN", "arrow-down-left", "btn-in"),
            ("stock_out", "Stock OUT", "arrow-up-right", "btn-out"),
            ("complaint_new", "New complaint", "plus", "btn-main"),
            ("transfer", "Transfer", "arrows-exchange", "btn-quiet sep-before"),
            ("adjust", "Adjust count", "adjustments-horizontal", "btn-quiet"),
        ],
    },
    {
        "key": "stock",
        "label": "Stock",
        "open": "current_stock",
        "tabs": [
            ("current_stock", "Current stock", False),
            ("movements", "Movements", False),
            ("low_stock", "Low stock", False),
        ],
        "actions": [
            ("stock_in", "Stock IN", "arrow-down-left", "btn-in"),
            ("stock_out", "Stock OUT", "arrow-up-right", "btn-out"),
            ("transfer", "Transfer", "arrows-exchange", "btn-quiet"),
            ("adjust", "Adjust count", "adjustments-horizontal", "btn-quiet"),
        ],
    },
    {
        "key": "complaints",
        "label": "Complaints",
        "open": "complaints_dashboard",
        "tabs": [
            ("complaints_dashboard", "Overview", False),
            ("complaints", "All complaints", False),
            ("sites", "Sites", False),
            ("technicians", "Technicians", False),
        ],
        "actions": [("complaint_new", "New complaint", "plus", "btn-main")],
    },
    {
        "key": "defectives",
        "label": "Defectives",
        "open": "defectives_dashboard",
        "tabs": [
            ("defectives_dashboard", "Overview", False),
            ("defective_pieces", "Pieces", False),
            ("return_batches", "Return batches", False),
        ],
        "actions": [
            ("mark_defective", "Mark defective", "alert-octagon", "btn-quiet"),
            ("batch_new", "New return batch", "plus", "btn-main"),
        ],
    },
    {
        "key": "setup",
        "label": "Setup",
        "open": "items",
        "tabs": [("items", "Items", False), ("masters", "Masters", True)],
        "actions": [("item_new", "New item", "plus", "btn-main")],
    },
]
EXTRA_URLS = ["global_search"]
# "?status=..." for the pieces list: the menu entry and the dashboard's piece tiles all build on it.
PIECES_STATUS_QUERY = "?status={}"
# Menu entries that open on a filtered list, so the badge beside them counts exactly the rows shown.
NAV_QUERY = {"defective_pieces": PIECES_STATUS_QUERY.format("IN_STORE")}
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


# Form pages that highlight no menu entry of their own: the tab their back link returns to.
FORM_BACK = {
    "stock_in": "current_stock",
    "stock_out": "current_stock",
    "transfer": "current_stock",
    "adjust": "current_stock",
    "complaint_new": "complaints",
    "mark_defective": "defectives_dashboard",
}
# Menu entries are the sub-tabs of every section (plus Home), keyed by url name.
TAB_SECTION = {name: sec for sec in SECTIONS for name, *_ in sec["tabs"]}
URL_NAMES = [name for sec in SECTIONS for name, *_ in sec["tabs"] + sec["actions"]]


def _url(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def service_counts(request):
    """(complaint status counts, piece counts), counted once per request (one query each, only when asked)
    and shared by the menu badges and the main dashboard's service tiles."""
    from apps.complaints.selectors import status_counts  # imported here: both apps depend on inventory
    from apps.defectives.selectors import piece_counts

    cache = request.__dict__.setdefault("_service_counts", {})
    if "status" not in cache:
        cache["status"] = status_counts()
    if "pieces" not in cache:
        cache["pieces"] = piece_counts()
    return cache["status"], cache["pieces"]


def _open_complaints(request):
    """Open complaints (the "All complaints" list opens on the Open tab)."""
    from apps.complaints.models import OPEN_STATUSES

    counts, _ = service_counts(request)
    return sum(counts[s] for s in OPEN_STATUSES)


def _pieces_in_store(request):
    """Pieces In store (the "Pieces" menu entry opens on that filter)."""
    return service_counts(request)[1]["in_store"]


def nav(request):
    """Top-bar sections, the current section's sub-tabs, hero actions or back link, URLs by name (None until
    built), and the menu badges' counts.

    Each badge is lazy: its one counting query runs only if the template shows it."""
    if not request.user.is_authenticated:
        return {}
    urls = {name: _url(name) for name in URL_NAMES}
    urls.update({name: _url(name) for name in EXTRA_URLS})
    current = request.resolver_match.url_name if request.resolver_match else ""
    active = ACTIVE_ALIASES.get(current, current)
    is_admin = has_role(request.user, ADMIN)

    def entry(name, label, admin=False):
        return {
            "name": name,
            "label": label,
            "admin_only": admin,
            "url": urls[name] and urls[name] + NAV_QUERY.get(name, ""),
            "active": name == active,
        }

    sections = [
        (sec["label"], [entry(n, label, admin) for n, label, admin in sec["tabs"]]) for sec in SECTIONS
    ]
    # Where this page lives. A tab page (a list or overview) shows the section's tabs and actions; any other
    # page (a form or a detail page) shows a back link to the tab it came from.
    is_tab_page = current in TAB_SECTION
    back_name = None if is_tab_page else FORM_BACK.get(current) or ACTIVE_ALIASES.get(current)
    home_name = current if is_tab_page else back_name
    section = TAB_SECTION.get(home_name)
    top = []
    for sec in SECTIONS:
        top.append(
            {
                "key": sec["key"],
                "label": sec["label"],
                "url": urls[sec["open"]],
                "active": sec is section,
                "count_url": {
                    "complaints": urls["complaints"],
                    "defectives": urls["defective_pieces"]
                    and urls["defective_pieces"] + NAV_QUERY["defective_pieces"],
                }.get(sec["key"]),
            }
        )
    tabs, actions, back = [], [], None
    if section and is_tab_page:
        tabs = [
            e
            for e in (entry(n, label, admin) for n, label, admin in section["tabs"])
            if is_admin or not e["admin_only"]
        ]
        if section["key"] == "home":
            tabs = []  # Home has one page, so no tab strip
        actions = [
            {"name": n, "label": label, "icon": icon, "cls": cls, "url": urls[n]}
            for n, label, icon, cls in section["actions"]
        ]
    elif section and back_name:
        label = next(label for n, label, _ in section["tabs"] if n == back_name)
        back = {"url": urls[back_name] and urls[back_name] + NAV_QUERY.get(back_name, ""), "label": label}
    return {
        "nav_sections": sections,
        "nav_top": top,
        "nav_tabs": tabs,
        "nav_actions": actions,
        "nav_back": back,
        "nav_urls": urls,
        "nav_low_count": SimpleLazyObject(low_stock_count),
        "nav_open_complaints": SimpleLazyObject(lambda: _open_complaints(request)),
        "nav_pieces_in_store": SimpleLazyObject(lambda: _pieces_in_store(request)),
    }
