"""Read the item lines the entry forms post as parallel arrays line_item, line_qty, line_batch, line_pkd."""

import re
from datetime import date

from .models import Item
from .services import StockError

FIELDS = ("item", "qty", "batch", "pkd")
MAX_QTY = 1_000_000  # far above any real line; keeps typos out of the 32-bit ledger column
WHOLE = re.compile(r"[0-9]+")


def raw_lines(post):
    """[{item, qty, batch, pkd}] exactly as typed (strings). Also sent back to the page when a POST fails."""
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


def _whole(text):
    """A plain non-negative whole number typed as ASCII digits, else None."""
    return int(text) if WHOLE.fullmatch(text) else None


def parse_lines(rows, mode):
    """[(item, qty, batch, pkd)] for mode in|out|trf|adj. Raises StockError with the first problem."""
    wanted = [r for r in rows if r["item"] or r["qty"]]
    ids = [_whole(r["item"]) for r in wanted]
    items = Item.objects.filter(is_active=True).in_bulk([i for i in ids if i is not None])
    minimum = 0 if mode == "adj" else 1
    parsed = []
    for n, (row, item_id) in enumerate(zip(wanted, ids, strict=True), start=1):
        item = items.get(item_id)
        if item is None:
            raise StockError(f"Line {n}: choose an item.")
        qty = _whole(row["qty"])
        if qty is None or qty < minimum or qty > MAX_QTY:
            what = "counted quantity (0 or more)" if mode == "adj" else "quantity of 1 or more"
            raise StockError(f"Line {n}: enter a whole-number {what}.")
        parsed.append((item, qty, row["batch"][:40], _month(row["pkd"], n)))
    if not parsed:
        raise StockError("Add at least one item.")
    if mode != "in" and len({item.pk for item, *_ in parsed}) != len(parsed):
        raise StockError("The same item is on two lines. Combine them into one line.")
    return parsed
