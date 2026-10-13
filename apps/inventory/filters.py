"""Parse list-screen GET params once; views and Excel exports share them."""

from dataclasses import dataclass
from datetime import date, timedelta

from .models import Company, EntryKind, FittingType, Item, Location, SpareType


def _text(value):
    """Strip NUL bytes (Postgres rejects them) and surrounding spaces."""
    return (value or "").replace(chr(0), "").strip()


def _obj(model, value):
    try:
        return model.objects.get(pk=int(value)) if value else None
    except (ValueError, model.DoesNotExist):
        return None


def _date(value, default):
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


@dataclass
class StockFilters:
    location: Location | None
    spare_type: SpareType | None
    company: Company | None
    q: str
    low: bool


def stock_filters(params):
    place = _obj(Location, params.get("location"))
    if place is not None and place.is_defective_store:
        place = None  # the Defective store has its own column, it is not a location filter here
    return StockFilters(
        place,
        _obj(SpareType, params.get("spare_type")),
        _obj(Company, params.get("company")),
        _text(params.get("q")),
        params.get("low") == "1",
    )


@dataclass
class MovementFilters:
    date_from: date
    date_to: date
    kind: str
    location: Location | None
    q: str
    item: Item | None


def movement_filters(params, today):
    kind = params.get("kind", "")
    date_from = _date(params.get("date_from"), today - timedelta(days=30))
    date_to = _date(params.get("date_to"), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return MovementFilters(
        date_from,
        date_to,
        kind if kind in EntryKind.values else "",
        _obj(Location, params.get("location")),
        _text(params.get("q")),
        _obj(Item, params.get("item")),
    )


def history_filters(params, today):
    """(date_from, date_to, location) for an item card's history; bad dates fall back, reversed dates swap."""
    date_from = _date(params.get("date_from"), today - timedelta(days=30))
    date_to = _date(params.get("date_to"), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to, _obj(Location, params.get("location"))


@dataclass
class ItemFilters:
    q: str
    spare_type: SpareType | None
    company: Company | None
    fitting_type: FittingType | None
    status: str  # "1" active, "0" inactive, "" all


def item_filters(params):
    status = params.get("status", "1")
    return ItemFilters(
        _text(params.get("q")),
        _obj(SpareType, params.get("spare_type")),
        _obj(Company, params.get("company")),
        _obj(FittingType, params.get("fitting_type")),
        status if status in ("1", "0", "") else "1",
    )
