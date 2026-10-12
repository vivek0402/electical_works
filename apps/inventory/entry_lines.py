"""Read the item lines the entry forms post as parallel arrays line_item, line_qty, line_batch, line_pkd
(and line_expected on the adjust form: the system quantity the user saw when typing the count)."""

import re
from datetime import date
from typing import NamedTuple

from .models import Item
from .services import StockError

FIELDS = ("item", "qty", "batch", "pkd", "expected")
MAX_QTY = 1_000_000  # far above any real line; keeps typos out of the 32-bit ledger column
MAX_DIGITS = 9  # never int() an unbounded string
DIGITS = re.compile(r"[0-9]+")


class ParsedLine(NamedTuple):
    item: Item
    qty: int
    batch: str
    pkd: date | None
    expected: int | None  # adjust only; None when not sent
    n: int  # the line number the user sees (blank rows still count)


def raw_lines(post):
    """[{item, qty, batch, pkd, expected}] exactly as typed (strings); sent back to the page on errors."""
    columns = [post.getlist(f"line_{name}") for name in FIELDS]
    count = max((len(c) for c in columns), default=0)
    return [
        {name: (col[n].strip() if n < len(col) else "") for name, col in zip(FIELDS, columns, strict=True)}
        for n in range(count)
    ]


def _month(text, n):
    if not text:
        return None
    try:
        year, month = (int(part) for part in text.split("-"))
        return date(year, month, 1)
    except ValueError as exc:
        raise StockError(f"Line {n}: PKD must be a month like 2026-05.") from exc


def _digits(text):
    """True if text is a plain whole number typed as ASCII digits."""
    return bool(DIGITS.fullmatch(text))


def _small(text):
    """The number if text is 1-9 ASCII digits, else None."""
    return int(text) if _digits(text) and len(text) <= MAX_DIGITS else None


def _qty(text, n, mode):
    if _digits(text) and (len(text) > MAX_DIGITS or int(text) > MAX_QTY):
        shown = f"{int(text):,}" if len(text) <= MAX_DIGITS else "That quantity"
        raise StockError(f"Line {n}: {shown} is too large. The most per line is {MAX_QTY:,}.")
    qty = _small(text)
    minimum = 0 if mode == "adj" else 1
    if qty is None or qty < minimum:
        what = "counted quantity (0 or more)" if mode == "adj" else "quantity of 1 or more"
        raise StockError(f"Line {n}: enter a whole-number {what}.")
    return qty


def parse_lines(rows, mode):
    """[ParsedLine] for mode in|out|trf|adj. Raises StockError with the first problem.

    Blank rows are skipped but still counted, so "Line 2" is the second row on the screen.
    """
    ids = [_small(r["item"]) for r in rows]
    items = Item.objects.in_bulk([i for i in ids if i is not None])
    parsed = []
    for n, (row, item_id) in enumerate(zip(rows, ids, strict=True), start=1):
        if not any(row.get(name) for name in ("item", "qty", "batch", "pkd")):
            continue
        item = items.get(item_id)
        if item is None:
            raise StockError(f"Line {n}: choose an item.")
        if not item.is_active:
            raise StockError(f"Line {n}: this item is no longer active.")
        qty = _qty(row["qty"], n, mode)
        expected = _small(row.get("expected", "")) if mode == "adj" else None
        parsed.append(ParsedLine(item, qty, row["batch"][:40], _month(row["pkd"], n), expected, n))
    if not parsed:
        raise StockError("Add at least one item.")
    if mode != "in" and len({line.item.pk for line in parsed}) != len(parsed):
        raise StockError("The same item is on two lines. Combine them into one line.")
    return parsed
