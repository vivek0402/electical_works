"""Parse the complaints list's GET params once; the list, dashboard links and Excel exports share them."""

from dataclasses import dataclass
from datetime import date

from apps.inventory.filters import _date, _obj, _text
from apps.inventory.models import Company

from .models import OPEN_STATUSES, Status, Technician

TABS = ["open", *OPEN_STATUSES, Status.CLOSED, Status.NOT_COVERED, "all"]
TAB_LABELS = {"open": "Open", **{s: Status(s).label for s in Status.values}, "all": "All"}
# Link target for the dashboard's "Closed / not covered" tile: Closed and Not covered together. It is not a
# tab of its own (the tab row is TABS), so nothing is highlighted while it is on.
FINISHED = "finished"
# (key, label, from days, to days or None)
AGE_BUCKETS = [
    ("0-2", "0–2 days", 0, 2),
    ("3-7", "3–7 days", 3, 7),
    ("8-15", "8–15 days", 8, 15),
    ("15+", "Over 15 days", 16, None),
]


@dataclass
class ComplaintFilters:
    tab: str
    company: Company | None
    city: str
    technician: Technician | None
    age: str  # an AGE_BUCKETS key, or ""
    q: str
    closed_since: date | None = None  # closed or not covered after this day (the dashboard's 30-day tile)


def complaint_filters(params):
    tab, age = params.get("tab", "open"), params.get("age", "")
    return ComplaintFilters(
        tab if tab in [*TABS, FINISHED] else "open",
        _obj(Company, params.get("company")),
        _text(params.get("city")),
        _obj(Technician, params.get("technician")),
        age if age in {key for key, *_ in AGE_BUCKETS} else "",
        _text(params.get("q")),
        _date(params.get("closed_since"), None),
    )
