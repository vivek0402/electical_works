import datetime

import pytest

from apps.inventory.filters import item_filters, movement_filters, stock_filters
from tests.factories import loc

pytestmark = pytest.mark.django_db
TODAY = datetime.date(2026, 10, 12)


def test_stock_filters_bad_ids_and_nul():
    f = stock_filters({"location": "abc", "spare_type": "99999", "company": "", "q": " a\x00b ", "low": "1"})
    assert f.location is None and f.spare_type is None and f.company is None
    assert f.q == "ab" and f.low is True
    assert stock_filters({"location": str(loc().pk), "low": "0"}).low is False


def test_movement_filters_defaults_and_bad_values():
    f = movement_filters({"date_from": "nope", "date_to": "2026-13-45", "kind": "XYZ", "item": "zz"}, TODAY)
    assert f.date_from == TODAY - datetime.timedelta(days=30) and f.date_to == TODAY
    assert f.kind == "" and f.item is None and f.location is None


def test_movement_filters_valid_kind_and_swapped_dates():
    f = movement_filters({"date_from": "2026-10-10", "date_to": "2026-09-01", "kind": "REV"}, TODAY)
    assert f.kind == "REV"
    assert f.date_from == datetime.date(2026, 9, 1) and f.date_to == datetime.date(2026, 10, 10)


@pytest.mark.parametrize("raw,expected", [("1", "1"), ("0", "0"), ("", ""), ("junk", "1")])
def test_item_filters_status(raw, expected):
    assert item_filters({"status": raw}).status == expected


def test_item_filters_default_status_and_bad_ids():
    f = item_filters({"spare_type": "x", "company": "0", "fitting_type": "-1", "q": "\x00"})
    assert f.status == "1" and f.q == ""
    assert f.spare_type is None and f.company is None and f.fitting_type is None
