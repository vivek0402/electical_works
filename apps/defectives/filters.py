"""Parse the defectives list screens' GET params once; views and Excel exports share them."""

from dataclasses import dataclass
from datetime import date

from apps.inventory.filters import _date, _obj, _text
from apps.inventory.models import Company, Item

from .models import BATCH_LABELS, Outcome, PieceStatus, Source


@dataclass
class BatchFilters:
    company: Company | None
    status: str  # one of BATCH_LABELS, or "" for any
    waiting_over: int | None = None  # only batches still waiting on the company for more than this many days


def batch_filters(params):
    status = params.get("status", "")
    days = params.get("waiting_over", "")
    return BatchFilters(
        _obj(Company, params.get("company")),
        status if status in BATCH_LABELS else "",
        int(days) if days.isdigit() and len(days) < 5 else None,
    )


@dataclass
class PieceFilters:
    company: Company | None
    item: Item | None
    status: str
    source: str
    outcome: str
    date_from: date | None  # collected on or after
    date_to: date | None
    q: str
    answered: str = ""  # a company answer recorded on any of the piece's batch lines
    since: date | None = None  # ... with the answer dated after this day


def piece_filters(params):
    status, source, outcome = params.get("status", ""), params.get("source", ""), params.get("outcome", "")
    answered = params.get("answered", "")
    date_from, date_to = _date(params.get("date_from"), None), _date(params.get("date_to"), None)
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return PieceFilters(
        _obj(Company, params.get("company")),
        _obj(Item, params.get("item")),
        status if status in PieceStatus.values else "",
        source if source in Source.values else "",
        outcome if outcome in Outcome.values else "",
        date_from,
        date_to,
        _text(params.get("q")),
        answered if answered in Outcome.values else "",
        _date(params.get("since"), None),
    )
