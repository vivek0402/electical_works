"""All writes for defective pieces and return batches. Views and commands call these; nothing else changes a
piece. Every stock effect goes through inventory's post_entry (append-only ledger, row locks, never negative).

Lock order (every service here, and every caller that combines them, takes row locks in this order so two
transactions can never wait on each other in a cycle):

1. DefectivePiece / ReturnBatch rows (``_lock``: pieces in tag order);
2. post_entry: StockBalance rows (item, location order), then the EntryCounter row;
3. next_number: the core Counter row (DEF, RB, CMP, VIS), always taken after post_entry.

So a service posts its ledger entry first and allocates tags / document numbers afterwards. The counter
rows are the most contended, so taking them last also keeps them locked for the shortest time.
"""

import re
from collections import Counter

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.numbers import next_number
from apps.inventory.models import AdjustReason, EntryKind, Location, ServiceSubtype
from apps.inventory.services import Line, post_entry

from .models import TRANSITIONS, DefectiveEvent, DefectivePiece, PieceStatus, ScrapReason, Source

TAG = re.compile(r"^DEF-?(\d{1,6})$")


class DefectiveError(ValidationError):
    """A defectives rule was broken. The message is safe to show to staff as-is."""


def normalise_tag(text):
    """'def-42' or 'DEF0042' -> 'DEF-0042' (what staff type or scan). Anything else comes back upper-cased."""
    raw = (text or "").strip().upper()
    match = TAG.match(raw)
    return f"DEF-{int(match.group(1)):04d}" if match else raw


def _lock(pieces):
    """The same pieces re-read and row-locked in tag order, so two people can't move one piece twice."""
    return list(
        DefectivePiece.objects.select_for_update(of=("self",))
        .filter(pk__in=[p.pk for p in pieces])
        .select_related("item", "company", "return_batch")
        .order_by("tag")
    )


def _move(piece, to, *, at, user, note="", entry=None):
    """Change a piece's status (checked against TRANSITIONS) and log it. The caller saves the piece."""
    if to not in TRANSITIONS[piece.status]:
        raise DefectiveError(
            f"{piece.tag} is {piece.get_status_display().lower()}, so it can't become "
            f"{PieceStatus(to).label.lower()}."
        )
    DefectiveEvent.objects.create(
        piece=piece, from_status=piece.status, to_status=to, at=at, by=user, note=note[:300], entry=entry
    )
    piece.status = to


def _not_in_store(piece, action, hint=""):
    where = f" ({piece.return_batch.number})" if piece.return_batch_id else ""
    status = piece.get_status_display().lower()
    return f"{piece.tag} is {status}{where}. Only pieces in store can be {action}{hint}."


def _check_date(day, what="The date", missing="Choose the date."):
    if day is None:
        raise DefectiveError(missing)
    if day > timezone.localdate():
        raise DefectiveError(f"{what} can't be in the future.")


def _per_item(pieces):
    """[(item, count)] for a group of pieces, in item-code order (one ledger line per item)."""
    counts = Counter(p.item_id for p in pieces)
    items = {p.item_id: p.item for p in pieces}
    return sorted(((items[i], n) for i, n in counts.items()), key=lambda pair: pair[0].code)


@transaction.atomic
def create_piece(*, item, source, collected_on, user, entry, batch_code="", pkd=None, fault="", note=""):
    """One tagged piece in the Defective store. The caller has already posted `entry`, the ledger entry that
    brought it there (a collection Stock IN or a mark-defective transfer), as the lock order requires."""
    piece = DefectivePiece.objects.create(
        tag=next_number("DEF"),
        item=item,
        company=item.company,
        batch_code=(batch_code or "").strip()[:40],
        pkd=pkd,
        fault=(fault or "").strip()[:200],
        source=source,
        collected_on=collected_on,
        created_by=user,
    )
    DefectiveEvent.objects.create(
        piece=piece, to_status=PieceStatus.IN_STORE, at=collected_on, by=user, note=note[:300], entry=entry
    )
    return piece


@transaction.atomic
def mark_defective(*, location, lines, entry_date, user):
    """Move faulty pieces from good stock into the Defective store and tag each one.

    lines: [(item, qty, fault)]. Posts one Transfer (MARK_DEFECTIVE) and creates `qty` pieces per line.
    Returns (entry, pieces). Raises DefectiveError or StockError and saves nothing.
    """
    if location.is_defective_store:
        raise DefectiveError("Choose the good-stock location where the faulty pieces were found.")
    if not lines:
        raise DefectiveError("Add at least one item.")
    for n, (_, _, fault) in enumerate(lines, start=1):
        if not (fault or "").strip():
            raise DefectiveError(f"Line {n}: write what is wrong with the piece.")
    _check_date(entry_date)
    store = Location.defective_store()
    moves = [ln for item, qty, _ in lines for ln in (Line(item, location, -qty), Line(item, store, qty))]
    # Lock order: post_entry (balances, entry counter) before next_number (piece tags).
    entry = post_entry(
        kind=EntryKind.TRF,
        entry_date=entry_date,
        lines=moves,
        user=user,
        subtype=ServiceSubtype.MARK_DEFECTIVE,
        party=store.name,
        note="Marked defective",
    )
    pieces = [
        create_piece(
            item=item,
            source=Source.FOUND_IN_STOCK,
            collected_on=entry_date,
            user=user,
            entry=entry,
            fault=fault,
            note="Marked defective from stock",
        )
        for item, qty, fault in lines
        for _ in range(qty)
    ]
    return entry, pieces


@transaction.atomic
def scrap(*, pieces, reason, user, note="", entry_date=None):
    """Write off pieces in store that are not worth returning: one Adjustment (Damaged) at the Defective
    store, -1 per piece. Returns the entry.

    The scrap date is kept in `settled_on`. Any `outcome` left over from an earlier batch (a piece rejected
    and sent back) is cleared: the scrap itself is recorded by the status and the event, and each batch's
    answer stays on its BatchLine.
    """
    entry_date = entry_date or timezone.localdate()
    pieces = _lock(pieces)
    if not pieces:
        raise DefectiveError("Tick at least one piece.")
    if reason not in ScrapReason.values:
        raise DefectiveError("Choose why the pieces are scrapped.")
    note = (note or "").strip()
    if reason == ScrapReason.OTHER and not note:
        raise DefectiveError("Write a note when the reason is Other.")
    for p in pieces:
        if p.status != PieceStatus.IN_STORE:
            hint = "; remove it from the batch first" if p.status == PieceStatus.IN_BATCH else ""
            raise DefectiveError(_not_in_store(p, "scrapped", hint))
    store = Location.defective_store()
    label = ScrapReason(reason).label
    why = label + (f" · {note}" if note else "")
    entry = post_entry(
        kind=EntryKind.ADJ,
        entry_date=entry_date,
        lines=[Line(item, store, -n) for item, n in _per_item(pieces)],
        user=user,
        subtype=ServiceSubtype.SCRAP_DEFECTIVE,
        reason=AdjustReason.DAMAGED,
        note=f"Scrapped {', '.join(p.tag for p in pieces)}: {why}",
    )
    for p in pieces:
        _move(p, PieceStatus.SCRAPPED, at=entry_date, user=user, note=why, entry=entry)
        p.outcome = ""
        p.settled_on = entry_date
        p.save(update_fields=["status", "outcome", "settled_on"])
    return entry
