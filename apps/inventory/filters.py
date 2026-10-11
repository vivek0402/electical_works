"""Parse list-screen GET params once; views and Excel exports share them."""

from dataclasses import dataclass
from datetime import date, timedelta

from .models import Company, EntryKind, FittingType, Item, Location, SpareType


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
    return StockFilters(
        _obj(Location, params.get("location")),
        _obj(SpareType, params.get("spare_type")),
        _obj(Company, params.get("company")),
        params.get("q", "").strip(),
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
    return MovementFilters(
        _date(params.get("date_from"), today - timedelta(days=30)),
        _date(params.get("date_to"), today),
        kind if kind in EntryKind.values else "",
        _obj(Location, params.get("location")),
        params.get("q", "").strip(),
        _obj(Item, params.get("item")),
    )


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
        params.get("q", "").strip(),
        _obj(SpareType, params.get("spare_type")),
        _obj(Company, params.get("company")),
        _obj(FittingType, params.get("fitting_type")),
        status if status in ("1", "0", "") else "1",
    )
