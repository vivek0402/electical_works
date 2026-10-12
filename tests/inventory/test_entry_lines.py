import pytest
from django.http import QueryDict

from apps.inventory.entry_lines import parse_lines, raw_lines
from apps.inventory.services import StockError
from tests.factories import make_item

pytestmark = pytest.mark.django_db


def post(*rows):
    q = QueryDict(mutable=True)
    for item, qty, batch, pkd in rows:
        q.appendlist("line_item", str(item))
        q.appendlist("line_qty", str(qty))
        q.appendlist("line_batch", batch)
        q.appendlist("line_pkd", pkd)
    return raw_lines(q)


def test_parses_lines_and_skips_blank_rows():
    a = make_item("EIO6006")
    parsed = parse_lines(post((a.pk, 3, "B1", "2026-05"), ("", "", "", "")), "in")
    assert len(parsed) == 1
    line = parsed[0]
    assert (line.item, line.qty, line.batch, line.pkd.isoformat(), line.n) == (a, 3, "B1", "2026-05-01", 1)


@pytest.mark.parametrize(
    "rows,mode,msg",
    [
        ([], "in", "Add at least one item."),
        ([("", 3, "", "")], "out", "Line 1: choose an item."),
        ([("ITEM", "2.5", "", "")], "out", "Line 1: enter a whole-number quantity of 1 or more."),
        ([("ITEM", 0, "", "")], "trf", "Line 1: enter a whole-number quantity of 1 or more."),
        ([("ITEM", -1, "", "")], "adj", r"Line 1: enter a whole-number counted quantity \(0 or more\)."),
        (
            [("ITEM", 1, "", ""), ("ITEM", 2, "", "")],
            "out",
            "The same item is on two lines. Combine them into one line.",
        ),
        ([("ITEM", 1, "", "13-2026")], "in", "Line 1: PKD must be a month like 2026-05."),
        ([("ITEM", 1, "", "2026-13")], "in", "Line 1: PKD must be a month like 2026-05."),
    ],
)
def test_line_errors(rows, mode, msg):
    a = make_item("EIO6006")
    rows = [(a.pk if r[0] == "ITEM" else r[0], *r[1:]) for r in rows]
    with pytest.raises(StockError, match=msg):
        parse_lines(post(*rows), mode)


def test_adjust_allows_zero_and_inactive_items_are_refused():
    a = make_item("EIO6006")
    assert parse_lines(post((a.pk, 0, "", "")), "adj")[0][1] == 0
    b = make_item("OLD-1", is_active=False)
    with pytest.raises(StockError, match="Line 1: this item is no longer active."):
        parse_lines(post((b.pk, 1, "", "")), "in")


def test_line_numbers_count_blank_rows():
    a = make_item("EIO6006")
    with pytest.raises(StockError, match="Line 2: enter a whole-number quantity of 1 or more."):
        parse_lines(post(("", "", "", ""), (a.pk, "x", "", "")), "out")
    parsed = parse_lines(post(("", "", "", ""), (a.pk, 2, "", "")), "out")
    assert [p.n for p in parsed] == [2]


def test_quantity_limits():
    a = make_item("EIO6006")
    assert parse_lines(post((a.pk, 1_000_000, "", "")), "in")[0].qty == 1_000_000
    with pytest.raises(StockError, match="Line 1: 1,000,001 is too large. The most per line is 1,000,000."):
        parse_lines(post((a.pk, 1_000_001, "", "")), "in")
    with pytest.raises(
        StockError, match="Line 1: That quantity is too large. The most per line is 1,000,000."
    ):
        parse_lines(post((a.pk, "9" * 5000, "", "")), "out")
    with pytest.raises(StockError, match="Line 1: choose an item."):
        parse_lines(post(("1" * 5000, 1, "", "")), "out")


def test_unknown_item_and_batch_only_row():
    with pytest.raises(StockError, match="Line 1: choose an item."):
        parse_lines(post((999999, 1, "", "")), "in")
    with pytest.raises(StockError, match="Line 1: choose an item."):
        parse_lines(post(("", "", "B1", "")), "in")


def test_adjust_expected_is_read():
    a = make_item("EIO6006")
    q = QueryDict(mutable=True)
    for name, value in [("item", a.pk), ("qty", 2), ("batch", ""), ("pkd", ""), ("expected", 5)]:
        q.appendlist(f"line_{name}", str(value))
    assert parse_lines(raw_lines(q), "adj")[0].expected == 5
    assert parse_lines(raw_lines(q), "out")[0].expected is None
