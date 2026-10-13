"""All writes for defective pieces and return batches. Views and commands call these; nothing else changes a
piece. Every stock effect goes through inventory's post_entry (append-only ledger, row locks, never negative).

Lock order. Every service here, and every caller that combines them, takes row locks in this order:

    ReturnBatch row, then pieces in tag order, then post_entry, then next_number(s)

- ReturnBatch row: `_lock_batch` (Task 5), one batch per call.
- Pieces: `_lock`, always in tag order.
- post_entry: StockBalance rows in (item, location) order, then the EntryCounter row for the entry kind.
- next_number / next_numbers: the core Counter row (DEF tags last of all).

So a service posts its ledger entry first and only then allocates piece tags. Two transactions that both
follow this order can never wait on each other in a cycle. The Counter rows are the most contended, so taking
them last also keeps them locked for the shortest time.
"""

import re
from collections import Counter

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.core.numbers import next_numbers
from apps.inventory.models import AdjustReason, EntryKind, Location, ServiceSubtype, StockLine
from apps.inventory.services import Line, post_entry

from .models import TRANSITIONS, DefectiveEvent, DefectivePiece, PieceStatus, ScrapReason, Source

TAG = re.compile(r"^DEF-?(\d{1,6})$")
MAX_PIECES_PER_LINE = 200  # one form line can't tag more pieces than this
FAULT_MAX, BATCH_CODE_MAX, NOTE_MAX = 200, 40, 300  # the model field lengths


class DefectiveError(ValidationError):
    """A defectives rule was broken. The message is safe to show to staff as-is."""


def normalise_tag(text):
    """'def-42' or 'DEF0042' -> 'DEF-0042' (what staff type or scan). Anything else comes back upper-cased."""
    raw = (text or "").strip().upper()
    match = TAG.match(raw)
    return f"DEF-{int(match.group(1)):04d}" if match else raw


# ---------------------------------------------------------------- shared checks


def _line_message(text, line=None):
    """'Line 2: quantity must…' for a numbered form line, 'Quantity must…' otherwise."""
    return f"Line {line}: {text}" if line else text[0].upper() + text[1:]


def _check_qty(qty, line=None):
    """A whole number of pieces, 1 to MAX_PIECES_PER_LINE. Checked before any arithmetic on qty."""
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        raise DefectiveError(_line_message("quantity must be 1 or more.", line))
    if qty > MAX_PIECES_PER_LINE:
        raise DefectiveError(_line_message(f"quantity must be between 1 and {MAX_PIECES_PER_LINE}.", line))


def _check_length(text, limit, what, line=None):
    """Refuse text longer than its field instead of silently cutting it."""
    if len(text) > limit:
        raise DefectiveError(_line_message(f"keep the {what} to {limit} characters or less.", line))


def _check_date(day, what="The date", missing="Choose the date."):
    if day is None:
        raise DefectiveError(missing)
    if day > timezone.localdate():
        raise DefectiveError(f"{what} can't be in the future.")


def _check_after_history(pieces, day, what="came into the store"):
    """Refuse a move dated before a piece's latest event, so each piece's history stays in date order.

    One query for all the pieces. Task 5 uses it for add / dispatch / settle as well, with its own `what`
    (e.g. "was added to the batch").
    """
    latest = dict(
        DefectiveEvent.objects.filter(piece__in=pieces)
        .order_by()
        .values("piece")
        .annotate(last=Max("at"))
        .values_list("piece", "last")
    )
    for p in pieces:
        last = latest.get(p.pk)
        if last and last > day:
            raise DefectiveError(f"{p.tag} only {what} on {last:%d-%m-%Y}.")


# ---------------------------------------------------------------- locking and status moves


def _lock(pieces):
    """The same pieces re-read and row-locked in tag order, so two people can't move one piece twice.
    Refuses unknown or repeated pieces (a stale page, a double tick)."""
    pks = [p.pk for p in pieces]
    locked = list(
        DefectivePiece.objects.select_for_update(of=("self",))
        .filter(pk__in=pks)
        .select_related("item", "company", "return_batch")
        .order_by("tag")
    )
    if len(locked) != len(pks):
        raise DefectiveError("Some pieces could not be found; refresh and try again.")
    return locked


def _log_events(pieces, to, *, at, user, note="", entry=None, new=False):
    """One DefectiveEvent per piece, in one INSERT. `new=True` logs a piece's arrival (no from-status)."""
    DefectiveEvent.objects.bulk_create(
        DefectiveEvent(
            piece=p,
            from_status="" if new else p.status,
            to_status=to,
            at=at,
            by=user,
            note=note[:NOTE_MAX],
            entry=entry,
        )
        for p in pieces
    )


def _move_all(pieces, to, *, at, user, note="", entry=None):
    """Change the status of several pieces (each checked against TRANSITIONS) and log one event each, in one
    INSERT. The caller saves the pieces (bulk_update)."""
    for piece in pieces:
        if to not in TRANSITIONS[piece.status]:
            raise DefectiveError(
                f"{piece.tag} is {piece.get_status_display().lower()}, so it can't become "
                f"{PieceStatus(to).label.lower()}."
            )
    _log_events(pieces, to, at=at, user=user, note=note, entry=entry)
    for piece in pieces:
        piece.status = to


def _move(piece, to, *, at, user, note="", entry=None):
    """_move_all for one piece. The caller saves the piece."""
    _move_all([piece], to, at=at, user=user, note=note, entry=entry)


def _not_in_store(piece, action, hint=""):
    where = f" ({piece.return_batch.number})" if piece.return_batch_id else ""
    status = piece.get_status_display().lower()
    return f"{piece.tag} is {status}{where}. Only pieces in store can be {action}{hint}."


def _per_item(pieces):
    """[(item, count)] for a group of pieces, in item-code order (one ledger line per item)."""
    counts = Counter(p.item_id for p in pieces)
    items = {p.item_id: p.item for p in pieces}
    return sorted(((items[i], n) for i, n in counts.items()), key=lambda pair: pair[0].code)


# ---------------------------------------------------------------- services


@transaction.atomic
def collect_pieces(
    *, entry, item, qty, source, collected_on, user, batch_code="", pkd=None, fault="", note=""
):
    """`qty` tagged pieces of one item in the Defective store, all from `entry`: the ledger entry the caller
    has already posted that brought them there (a collection Stock IN or a mark-defective transfer).

    Checks that the entry really put that many of the item into the Defective store (counting pieces already
    tagged from it), then takes the tags in one counter update and saves pieces and events in one INSERT each.
    Returns the pieces in tag order.
    """
    if entry is None:
        raise DefectiveError("A piece needs the ledger entry that brought it into the Defective store.")
    _check_date(collected_on, "The collection date", "Choose the collection date.")
    if collected_on != entry.entry_date:
        raise DefectiveError(
            f"The collection date must be the date of {entry.number} ({entry.entry_date:%d-%m-%Y})."
        )
    if source not in Source.values:
        raise DefectiveError("Choose where the piece came from.")
    _check_qty(qty)
    batch_code, fault, note = ((value or "").strip() for value in (batch_code, fault, note))
    _check_length(fault, FAULT_MAX, "fault")
    _check_length(batch_code, BATCH_CODE_MAX, "batch code")
    _check_length(note, NOTE_MAX, "note")
    brought = (
        StockLine.objects.filter(
            entry=entry, item=item, location__is_defective_store=True, qty__gt=0
        ).aggregate(n=Sum("qty"))["n"]
        or 0
    )
    if not brought:
        raise DefectiveError(f"{entry.number} brought no {item.code} into the Defective store.")
    tagged = DefectiveEvent.objects.filter(entry=entry, from_status="", piece__item=item).count()
    if tagged + qty > brought:
        already = f" ({tagged} already tagged)" if tagged else ""
        raise DefectiveError(
            f"{entry.number} brought only {brought} {item.code} into the Defective store{already}."
        )
    pieces = DefectivePiece.objects.bulk_create(
        DefectivePiece(
            tag=tag,
            item=item,
            company=item.company,
            batch_code=batch_code,
            pkd=pkd,
            fault=fault,
            source=source,
            collected_on=collected_on,
            created_by=user,
        )
        for tag in next_numbers("DEF", qty)
    )
    _log_events(pieces, PieceStatus.IN_STORE, at=collected_on, user=user, note=note, entry=entry, new=True)
    return pieces


def create_piece(*, item, source, collected_on, user, entry, batch_code="", pkd=None, fault="", note=""):
    """One tagged piece from `entry` (collect_pieces with qty=1). Prefer collect_pieces for several."""
    [piece] = collect_pieces(
        entry=entry,
        item=item,
        qty=1,
        source=source,
        collected_on=collected_on,
        user=user,
        batch_code=batch_code,
        pkd=pkd,
        fault=fault,
        note=note,
    )
    return piece


@transaction.atomic
def mark_defective(*, location, lines, entry_date, user):
    """Move faulty pieces from good stock into the Defective store and tag each one.

    lines: [(item, qty, fault)], each item once, qty 1 to MAX_PIECES_PER_LINE. Posts one Transfer
    (MARK_DEFECTIVE), then tags `qty` pieces per line. Returns (entry, pieces).
    Raises DefectiveError or StockError and saves nothing.
    """
    if location.is_defective_store:
        raise DefectiveError("Choose the good-stock location where the faulty pieces were found.")
    if not lines:
        raise DefectiveError("Add at least one item.")
    seen, cleaned = set(), []
    for n, (item, qty, fault) in enumerate(lines, start=1):
        _check_qty(qty, n)
        fault = (fault or "").strip()
        if not fault:
            raise DefectiveError(f"Line {n}: write what is wrong with the piece.")
        _check_length(fault, FAULT_MAX, "fault", n)
        if item.pk in seen:
            raise DefectiveError(f"{item.code} is listed twice.")
        seen.add(item.pk)
        cleaned.append((item, qty, fault))
    _check_date(entry_date)
    store = Location.defective_store()
    moves = [ln for item, qty, _ in cleaned for ln in (Line(item, location, -qty), Line(item, store, qty))]
    # Lock order: post_entry (balances, entry counter) before next_numbers (piece tags).
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
        piece
        for item, qty, fault in cleaned
        for piece in collect_pieces(
            entry=entry,
            item=item,
            qty=qty,
            source=Source.FOUND_IN_STOCK,
            collected_on=entry_date,
            user=user,
            fault=fault,
            note="Marked defective from stock",
        )
    ]
    return entry, pieces


@transaction.atomic
def scrap(*, pieces, reason, user, note="", entry_date=None):
    """Write off pieces in store that are not worth returning: one Adjustment (Damaged) at the Defective
    store, one line per item. Returns the entry.

    The scrap date is kept in `settled_on`. Any `outcome` left over from an earlier batch (a piece rejected
    and sent back) is cleared: the scrap itself is recorded by the status and the event, and each batch's
    answer stays on its BatchLine.
    """
    entry_date = entry_date or timezone.localdate()
    _check_date(entry_date, "The scrap date", "Choose the scrap date.")
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
    _check_after_history(pieces, entry_date)
    store = Location.defective_store()
    why = ScrapReason(reason).label + (f" · {note}" if note else "")
    entry = post_entry(
        kind=EntryKind.ADJ,
        entry_date=entry_date,
        lines=[Line(item, store, -n) for item, n in _per_item(pieces)],
        user=user,
        subtype=ServiceSubtype.SCRAP_DEFECTIVE,
        reason=AdjustReason.DAMAGED,
        note=f"Scrapped {', '.join(p.tag for p in pieces)}: {why}",
    )
    _move_all(pieces, PieceStatus.SCRAPPED, at=entry_date, user=user, note=why, entry=entry)
    for p in pieces:
        p.outcome = ""
        p.settled_on = entry_date
    DefectivePiece.objects.bulk_update(pieces, ["status", "outcome", "settled_on"])
    return entry
