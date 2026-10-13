"""Read the item lines a form posts as parallel arrays <prefix>_item, <prefix>_qty, <prefix>_batch,
<prefix>_pkd and <prefix>_fault (prefix "line" on the stock forms and Mark defective), plus line_expected on
the adjust form (the system quantity the user saw when typing the count). The visit page will use other
prefixes: "part" (parts given) and "col" (failed parts collected)."""

import re
from datetime import date
from typing import NamedTuple

from .models import Item
from .services import StockError

FIELDS = ("item", "qty", "batch", "pkd", "expected", "fault")
TYPED = ("item", "qty", "batch", "pkd", "fault")  # a row with none of these filled in is blank and skipped
# Modes where the same item may be on several lines: stock coming in (one line per batch) and pieces marked
# defective (one line per fault; mark_defective groups them into one ledger line per item).
REPEATS_OK = ("in", "collect", "mark")
FAULT_MAX = 200  # DefectivePiece.fault
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
    fault: str = ""  # mark defective / failed parts collected


def raw_lines(post, prefix="line"):
    """[{item, qty, batch, pkd, expected, fault}] exactly as typed (strings).

    They are sent back to the page on errors."""
    columns = [post.getlist(f"{prefix}_{name}") for name in FIELDS]
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


def _fault(text, n, mode):
    if mode == "mark" and not text:
        raise StockError(f"Line {n}: write what is wrong with the piece.")
    if len(text) > FAULT_MAX:  # refused, never cut: the user sees what is wrong
        raise StockError(f"Line {n}: keep the fault to {FAULT_MAX} characters or less.")
    return text


def parse_lines(rows, mode, allow_empty=False):
    """[ParsedLine] for mode in|out|trf|adj (stock forms) or collect|mark (service forms).

    Raises StockError with the first problem. Blank rows are skipped but still counted, so "Line 2" is the
    second row on the screen. A fault is required on mark lines. allow_empty returns [] instead of
    "Add at least one item." (a visit may give no parts).
    """
    ids = [_small(r["item"]) for r in rows]
    items = Item.objects.in_bulk([i for i in ids if i is not None])
    parsed = []
    for n, (row, item_id) in enumerate(zip(rows, ids, strict=True), start=1):
        if not any(row.get(name) for name in TYPED):
            continue
        item = items.get(item_id)
        if item is None:
            raise StockError(f"Line {n}: choose an item.")
        if not item.is_active:
            raise StockError(f"Line {n}: this item is no longer active.")
        qty = _qty(row["qty"], n, mode)
        expected = _small(row.get("expected", "")) if mode == "adj" else None
        batch, pkd = row.get("batch", "")[:40], _month(row.get("pkd", ""), n)
        fault = _fault(row.get("fault", ""), n, mode)
        parsed.append(ParsedLine(item, qty, batch, pkd, expected, n, fault))
    if not parsed:
        if allow_empty:
            return []
        raise StockError("Add at least one item.")
    if mode not in REPEATS_OK and len({line.item.pk for line in parsed}) != len(parsed):
        raise StockError("The same item is on two lines. Combine them into one line.")
    return parsed
