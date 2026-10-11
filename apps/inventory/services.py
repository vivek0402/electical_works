"""Every stock write goes through here.

Views, forms and commands never touch the ledger directly.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from functools import reduce
from operator import or_

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q, Sum

from .models import (
    Bucket,
    DocType,
    Item,
    ItemAlias,
    ItemType,
    Location,
    StockBalance,
    StockDocument,
    StockMovement,
)
from .normalise import normalise_code


class StockError(ValidationError):
    """A stock rule was broken. The message is safe to show to staff as-is."""


@dataclass(frozen=True)
class Line:
    item: Item
    location: Location
    bucket: str
    qty: int  # signed: + into the bucket, − out of it
    batch_code: str = ""
    pkd_date: date | None = None


# Which bucket(s) and sign each document type may move. None = any bucket.
SIGN_RULES = {
    DocType.OPENING: (None, +1),
    DocType.RECEIVED_FROM_WIPRO: (Bucket.FRESH, +1),
    DocType.ISSUED_TO_COMPLAINT: (Bucket.FRESH, -1),
    DocType.DEFECTIVE_COLLECTED: (Bucket.DEFECTIVE, +1),
    DocType.RETURNED_TO_WIPRO: (Bucket.DEFECTIVE, -1),
    DocType.SCRAPPED: (None, -1),
    DocType.TRANSFER: (None, 0),  # any sign, but must net to zero per item+bucket
    DocType.ADJUSTMENT: (None, 0),
}
REASON_REQUIRED = {DocType.ADJUSTMENT, DocType.SCRAPPED}


def _validate(doc_type, lines, reason, is_reversal):
    if not lines:
        raise StockError("Add at least one item line.")
    for line in lines:
        if not isinstance(line.qty, int) or line.qty == 0:
            raise StockError(f"Quantity for {line.item.code} must be a whole number, not zero.")
        if line.bucket not in Bucket.values:
            raise StockError(f"Unknown bucket {line.bucket!r}.")
    if doc_type in REASON_REQUIRED and not reason.strip():
        raise StockError(f"A reason is required for {DocType(doc_type).label.lower()}.")
    if is_reversal:
        return  # a reversal mirrors an already-valid document with signs flipped
    bucket_rule, sign = SIGN_RULES[doc_type]
    label = DocType(doc_type).label
    for line in lines:
        if bucket_rule and line.bucket != bucket_rule:
            raise StockError(f"{label} can only move {Bucket(bucket_rule).label} stock.")
        if sign and (line.qty > 0) != (sign > 0):
            direction = "add" if sign > 0 else "remove"
            raise StockError(f"{label} can only {direction} stock ({line.item.code}).")
    if doc_type == DocType.TRANSFER:
        net = defaultdict(int)
        for line in lines:
            net[(line.item.pk, line.bucket)] += line.qty
        if any(net.values()):
            raise StockError("A transfer must take out exactly what it puts in.")
        if len({line.location.pk for line in lines}) < 2:
            raise StockError("A transfer needs two different locations.")


def _lock_balances(keys):
    """Ensure balance rows exist, then lock them in a fixed order (prevents deadlocks)."""
    StockBalance.objects.bulk_create(
        [StockBalance(item_id=i, location_id=loc, bucket=b, qty=0) for i, loc, b in keys],
        ignore_conflicts=True,
    )
    match = reduce(or_, (Q(item_id=i, location_id=loc, bucket=b) for i, loc, b in keys))
    rows = (
        StockBalance.objects.select_for_update()
        .filter(match)
        .order_by("item_id", "location_id", "bucket")
    )
    return {(r.item_id, r.location_id, r.bucket): r for r in rows}


@transaction.atomic
def post_document(
    *, doc_type, doc_date, lines, user=None, ref_no="", reason="", reverses=None
) -> StockDocument:
    """Post a stock document atomically. Raises StockError (nothing saved) if any bucket would
    go negative or a rule is broken."""
    _validate(doc_type, lines, reason, is_reversal=reverses is not None)

    deltas = defaultdict(int)
    for line in lines:
        deltas[(line.item.pk, line.location.pk, line.bucket)] += line.qty
    keys = sorted(deltas)
    balances = _lock_balances(keys)

    names = {line.item.pk: line.item.code for line in lines}
    places = {line.location.pk: line.location.name for line in lines}
    for key in keys:
        new_qty = balances[key].qty + deltas[key]
        if new_qty < 0:
            item_id, location_id, bucket = key
            raise StockError(
                f"Only {balances[key].qty} NOS of {names[item_id]} ({Bucket(bucket).label}) "
                f"at {places[location_id]}."
            )
        balances[key].qty = new_qty

    document = StockDocument.objects.create(
        doc_type=doc_type,
        doc_date=doc_date,
        ref_no=ref_no.strip(),
        reason=reason.strip(),
        reverses=reverses,
        created_by=user,
    )
    StockMovement.objects.bulk_create(
        StockMovement(
            document=document,
            item=line.item,
            location=line.location,
            bucket=line.bucket,
            qty=line.qty,
            batch_code=line.batch_code,
            pkd_date=line.pkd_date,
        )
        for line in lines
    )
    StockBalance.objects.bulk_update([balances[k] for k in keys], ["qty", "updated_at"])
    return document


@transaction.atomic
def reverse_document(*, document, user=None, reason, doc_date=None) -> StockDocument:
    """Cancel a document by posting its mirror image. The original stays visible."""
    document = StockDocument.objects.select_for_update().get(pk=document.pk)
    if document.reverses_id:
        raise StockError("A reversal cannot itself be reversed. Post a new document instead.")
    if StockDocument.objects.filter(reverses=document).exists():
        raise StockError("This document has already been reversed.")
    if not reason.strip():
        raise StockError("Please give a reason for the reversal.")
    lines = [
        Line(m.item, m.location, m.bucket, -m.qty, m.batch_code, m.pkd_date)
        for m in document.lines.select_related("item", "location")
    ]
    return post_document(
        doc_type=document.doc_type,
        doc_date=doc_date or date.today(),
        lines=lines,
        user=user,
        ref_no=document.ref_no if document.doc_type != DocType.OPENING else "",
        reason=reason,
        reverses=document,
    )


@transaction.atomic
def rebuild_balances() -> int:
    """Recompute the StockBalance cache from the ledger. Returns the number of balance rows."""
    with connection.cursor() as cursor:
        cursor.execute(f"LOCK TABLE {StockBalance._meta.db_table} IN EXCLUSIVE MODE")
    StockBalance.objects.all().delete()
    totals = StockMovement.objects.values("item_id", "location_id", "bucket").annotate(
        total=Sum("qty")
    )
    StockBalance.objects.bulk_create(
        StockBalance(
            item_id=t["item_id"], location_id=t["location_id"], bucket=t["bucket"], qty=t["total"]
        )
        for t in totals
    )
    return len(totals)


def balance_drift():
    """(item_id, location_id, bucket, cached, ledger) for every key where cache != ledger."""
    ledger = {
        (t["item_id"], t["location_id"], t["bucket"]): t["total"]
        for t in StockMovement.objects.values("item_id", "location_id", "bucket").annotate(
            total=Sum("qty")
        )
    }
    cached = {(b.item_id, b.location_id, b.bucket): b.qty for b in StockBalance.objects.all()}
    return [
        (*key, cached.get(key, 0), ledger.get(key, 0))
        for key in sorted(set(ledger) | set(cached))
        if cached.get(key, 0) != ledger.get(key, 0)
    ]


@transaction.atomic
def create_item(*, code, item_type=ItemType.OTHER, **fields) -> Item:
    """Create an item with a normalised code. Refuses codes already used as a code or alias."""
    code = normalise_code(code)
    if not code:
        raise ValidationError("Item code cannot be blank.")
    if Item.objects.filter(code=code).exists():
        raise ValidationError(f"Item {code} already exists.")
    alias = ItemAlias.objects.filter(alias=code).select_related("item").first()
    if alias:
        raise ValidationError(f"{code} is already an alias of {alias.item.code}.")
    return Item.objects.create(code=code, item_type=item_type, **fields)


@transaction.atomic
def add_alias(*, item, alias) -> ItemAlias:
    """Map another spelling to `item`. Refuses spellings that are already a code or alias."""
    alias = normalise_code(alias)
    if not alias or alias == item.code:
        raise ValidationError("Alias must differ from the item code.")
    if Item.objects.filter(code=alias).exists():
        raise ValidationError(f"{alias} is already an item code; merge the items instead.")
    existing = ItemAlias.objects.filter(alias=alias).select_related("item").first()
    if existing:
        if existing.item_id == item.pk:
            return existing
        raise ValidationError(f"{alias} is already an alias of {existing.item.code}.")
    return ItemAlias.objects.create(item=item, alias=alias)
