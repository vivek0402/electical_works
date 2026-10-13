"""All writes for defective pieces and return batches. Views and commands call these; nothing else changes a
piece. Every stock effect goes through inventory's post_entry (append-only ledger, row locks, never negative).

Lock order. Every service here, and every caller that combines them, takes row locks in this order:

    ReturnBatch row, then pieces in tag order, then post_entry, then next_number(s)

- ReturnBatch row: `_lock_batch`, one batch per call.
- Pieces: `_lock`, always in tag order.
- post_entry: StockBalance rows in (item, location) order, then the EntryCounter row for the entry kind.
  At most ONE post_entry per service call: a second one would lock balances while holding an EntryCounter
  row, the reverse of an ordinary stock entry (so settle posts one entry for all its pieces).
- next_number / next_numbers: the core Counter row (DEF tags last of all).

One exception: a service that creates a document may take that document's own new number first (create_batch
takes next_number("RB") before anything else). The new batch row is invisible to other transactions until
commit, so nobody else can be waiting on it, and no service takes an RB number after locking a batch or
pieces, so the RB Counter row never closes a cycle.

So a service posts its ledger entry first and only then allocates piece tags. Two transactions that both
follow this order can never wait on each other in a cycle. The Counter rows are the most contended, so taking
them last also keeps them locked for the shortest time.
"""

import re
from collections import Counter
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.core.numbers import next_number, next_numbers
from apps.inventory.models import AdjustReason, EntryKind, Location, ServiceSubtype, StockLine
from apps.inventory.services import Line, post_entry

from .models import (
    GOOD_OUTCOMES,
    TRANSITIONS,
    BatchLine,
    BatchStatus,
    DefectiveEvent,
    DefectivePiece,
    Outcome,
    PieceStatus,
    ReturnBatch,
    ScrapReason,
    Source,
)

TAG = re.compile(r"^DEF-?(\d{1,6})$")
MAX_PIECES_PER_LINE = 200  # one form line can't tag more pieces than this
FAULT_MAX, BATCH_CODE_MAX, NOTE_MAX = 200, 40, 300  # the model field lengths
BATCH_NOTE_MAX, COURIER_MAX, DOCKET_MAX = 200, 60, 40  # ReturnBatch field lengths
ENTRY_NOTE_TAGS = 20  # tags listed in a settlement entry's note before "+N more"


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

    One query for all the pieces. The batch services use it too, each with its own `what`
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


def _not_in_store(piece, action, hint=""):
    where = f" ({piece.return_batch.number})" if piece.return_batch_id else ""
    status = piece.get_status_display().lower()
    return f"{piece.tag} is {status}{where}. Only pieces in store can be {action}{hint}."


def _tag_list(pieces, limit=ENTRY_NOTE_TAGS):
    """'DEF-0001, DEF-0004' for an entry note; after `limit` tags, '… +N more'."""
    tags = [p.tag for p in pieces]
    shown = ", ".join(tags[:limit])
    return f"{shown} +{len(tags) - limit} more" if len(tags) > limit else shown


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

    lines: [(item, qty, fault)], qty 1 to MAX_PIECES_PER_LINE per line. The same item may be on several lines
    with different faults. Posts one Transfer (MARK_DEFECTIVE) with one pair of ledger lines per item (the qty
    summed over its lines), then tags `qty` pieces per form line with that line's fault.
    Returns (entry, pieces).
    Raises DefectiveError or StockError and saves nothing.
    """
    if location.is_defective_store:
        raise DefectiveError("Choose the good-stock location where the faulty pieces were found.")
    if not lines:
        raise DefectiveError("Add at least one item.")
    cleaned, per_item = [], {}  # per_item: {item_pk: [item, total qty]} in first-seen order
    for n, (item, qty, fault) in enumerate(lines, start=1):
        _check_qty(qty, n)
        fault = (fault or "").strip()
        if not fault:
            raise DefectiveError(f"Line {n}: write what is wrong with the piece.")
        _check_length(fault, FAULT_MAX, "fault", n)
        cleaned.append((item, qty, fault))
        per_item.setdefault(item.pk, [item, 0])[1] += qty
    _check_date(entry_date)
    store = Location.defective_store()
    # post_entry refuses an item twice at one location, so each item moves once with its lines' total.
    moves = [
        ln
        for item, total in per_item.values()
        for ln in (Line(item, location, -total), Line(item, store, total))
    ]
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
    # One collect_pieces call per form line, all against the item's one store line: its count check adds the
    # pieces earlier calls already tagged from this entry, so the lines together can't tag more than moved.
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


# ---------------------------------------------------------------- return batches


def _lock_batch(batch):
    """The batch re-read and row-locked (first in the lock order), so two people can't change it at once."""
    return ReturnBatch.objects.select_for_update(of=("self",)).select_related("company").get(pk=batch.pk)


@transaction.atomic
def create_batch(*, company, user, pieces=(), note="", created_on=None):
    """A new draft return batch for one company, optionally filled with pieces in store.

    Takes the batch's own RB number first (the documented exception to the lock order), then add_pieces
    locks the new batch and the pieces and checks them (company, status, date). If add_pieces refuses, the
    whole call rolls back, so the RB number is given back.
    """
    if company is None:
        raise DefectiveError("Choose the company the pieces go back to.")
    created_on = created_on or timezone.localdate()
    _check_date(created_on, "The batch date", "Choose the batch date.")
    note = (note or "").strip()
    _check_length(note, BATCH_NOTE_MAX, "note")
    batch = ReturnBatch.objects.create(
        number=next_number("RB"),
        company=company,
        created_on=created_on,
        note=note,
        created_by=user,
    )
    if pieces:
        add_pieces(batch=batch, pieces=pieces, user=user, at=created_on)
    return batch


@transaction.atomic
def add_pieces(*, batch, pieces, user, at=None):
    """Put pieces in store into a draft batch of the same company.

    Clears any answer left from an earlier batch (a piece rejected and sent back): the piece is waiting on the
    company again, and that earlier answer stays on its BatchLine.
    """
    batch = _lock_batch(batch)
    if not batch.is_draft:
        raise DefectiveError(
            f"{batch.number} was dispatched on {batch.dispatched_on:%d-%m-%Y}, so it is locked. "
            "Start a new batch."
        )
    pieces = _lock(pieces)
    if not pieces:
        raise DefectiveError("Tick at least one piece.")
    for p in pieces:
        if p.company_id != batch.company_id:
            raise DefectiveError(
                f"{batch.number} is for {batch.company.name}, but {p.tag} is a {p.company.name} piece. "
                "A batch holds one company's pieces only."
            )
        if p.status != PieceStatus.IN_STORE:
            raise DefectiveError(_not_in_store(p, "added"))
    at = at or timezone.localdate()
    _check_date(at)
    if at < batch.created_on:
        raise DefectiveError(f"The date can't be before the batch was created ({batch.created_on:%d-%m-%Y}).")
    _check_after_history(pieces, at, what="came into the store")
    _move_all(pieces, PieceStatus.IN_BATCH, at=at, user=user, note=f"Added to {batch.number}")
    for p in pieces:
        p.return_batch = batch
        p.outcome, p.settled_on = "", None
    DefectivePiece.objects.bulk_update(pieces, ["status", "return_batch", "outcome", "settled_on"])
    BatchLine.objects.bulk_create(BatchLine(batch=batch, piece=p) for p in pieces)
    return batch


@transaction.atomic
def remove_pieces(*, batch, pieces, user, at=None):
    """Take pieces out of a draft batch; they are back in store and their line in the batch is dropped."""
    batch = _lock_batch(batch)
    if not batch.is_draft:
        raise DefectiveError(f"{batch.number} is dispatched and locked.")
    pieces = _lock(pieces)
    if not pieces:
        raise DefectiveError("Tick at least one piece.")
    for p in pieces:
        if p.return_batch_id != batch.pk or p.status != PieceStatus.IN_BATCH:
            raise DefectiveError(f"{p.tag} is not in {batch.number}.")
    at = at or timezone.localdate()
    _check_date(at)
    _check_after_history(pieces, at, what="was added to the batch")
    _move_all(pieces, PieceStatus.IN_STORE, at=at, user=user, note=f"Removed from {batch.number}")
    for p in pieces:
        p.return_batch = None
    DefectivePiece.objects.bulk_update(pieces, ["status", "return_batch"])
    BatchLine.objects.filter(batch=batch, piece__in=pieces).delete()
    return batch


@transaction.atomic
def dispatch(*, batch, dispatched_on, courier, docket_no, user):
    """Send a draft batch: one Stock OUT (RETURN_TO_COMPANY) from the Defective store, then lock the batch.
    Returns the entry."""
    batch = _lock_batch(batch)
    if not batch.is_draft:
        raise DefectiveError(f"{batch.number} was already dispatched.")
    # The batch row is locked and every change to its lines locks it first, so this list can't go stale.
    piece_ids = list(batch.lines.values_list("piece_id", flat=True))
    if not piece_ids:
        raise DefectiveError("An empty batch can't be dispatched. Add pieces first.")
    _check_date(dispatched_on, "The dispatch date", "Choose the dispatch date.")
    if dispatched_on < batch.created_on:
        raise DefectiveError(
            f"The dispatch date can't be before the batch was created ({batch.created_on:%d-%m-%Y})."
        )
    courier, docket_no = (courier or "").strip(), (docket_no or "").strip()
    if not courier:
        raise DefectiveError("Choose the courier.")
    if not docket_no:
        raise DefectiveError("Enter the docket / LR number.")
    _check_length(courier, COURIER_MAX, "courier")
    _check_length(docket_no, DOCKET_MAX, "docket / LR number")
    pieces = _lock([DefectivePiece(pk=pk) for pk in piece_ids])
    _check_after_history(pieces, dispatched_on, what="was added to the batch")
    store = Location.defective_store()
    entry = post_entry(
        kind=EntryKind.OUT,
        entry_date=dispatched_on,
        lines=[Line(item, store, -n) for item, n in _per_item(pieces)],
        user=user,
        subtype=ServiceSubtype.RETURN_TO_COMPANY,
        party=batch.company.name,
        company=batch.company,
        ref=docket_no,
        note=f"{batch.number}: {courier} {docket_no}",
        return_batch=batch,
    )
    batch.status, batch.dispatched_on, batch.dispatch_entry = BatchStatus.DISPATCHED, dispatched_on, entry
    batch.courier, batch.docket_no = courier, docket_no
    batch.save(update_fields=["status", "dispatched_on", "dispatch_entry", "courier", "docket_no"])
    _move_all(
        pieces,
        PieceStatus.SENT,
        at=dispatched_on,
        user=user,
        note=f"Dispatched with {batch.number} ({courier} {docket_no})",
        entry=entry,
    )
    DefectivePiece.objects.bulk_update(pieces, ["status"])
    return entry


@transaction.atomic
def settle(*, batch, pieces, outcome, settled_on, user, to_location=None):
    """Record the company's answer for sent pieces of one dispatched batch, with ONE ledger entry per call:

    REPLACED / REPAIRED: one Stock IN (REPLACEMENT) into `to_location`, a good-stock location, one line per
    item. Every piece's `replacement_entry` is that same entry.
    REJECTED_RETURNED: one Stock IN (DEFECTIVE_RETURNED) back into the Defective store, one line per
    (item, batch code, pkd); the pieces are in store again.
    REJECTED_SCRAPPED: nothing to post, the pieces already left with the dispatch OUT.

    The answer is saved on each piece (its latest) and on its BatchLine (this batch's), both pointing at the
    entry. Returns [entry], or [] when nothing was posted.

    A single post_entry keeps the lock order: it locks every balance row in sorted order and only then the
    EntryCounter. Posting once per piece would hold EntryCounter(IN) while locking more balances, the reverse
    of an ordinary Stock IN, and could deadlock with it.
    """
    batch = _lock_batch(batch)
    if batch.is_draft:
        raise DefectiveError("Only a dispatched batch can be settled.")
    pieces = _lock(pieces)
    if not pieces:
        raise DefectiveError("Tick the pieces the company has answered for.")
    if outcome not in Outcome.values:
        raise DefectiveError("Choose the outcome.")
    _check_date(settled_on, "The date", "Choose the settlement date.")
    if settled_on < batch.dispatched_on:
        raise DefectiveError(
            f"The date can't be before the batch was dispatched ({batch.dispatched_on:%d-%m-%Y})."
        )
    good = outcome in GOOD_OUTCOMES
    if good and (to_location is None or to_location.is_defective_store or not to_location.is_active):
        raise DefectiveError("Choose the good-stock location the replacement pieces go into.")
    for p in pieces:
        if p.return_batch_id != batch.pk:
            raise DefectiveError(f"{p.tag} is not in {batch.number}.")
        if p.status != PieceStatus.SENT:
            raise DefectiveError(
                f"{p.tag} is not waiting on the company (it is {p.get_status_display().lower()}). "
                "Only sent pieces can be settled."
            )
    open_lines = {
        line.piece_id: line for line in BatchLine.objects.filter(batch=batch, piece__in=pieces, outcome="")
    }
    for p in pieces:
        if p.pk not in open_lines:
            raise DefectiveError(f"{p.tag}'s line in {batch.number} is already settled; refresh.")
    _check_after_history(pieces, settled_on, what="was dispatched")
    label = Outcome(outcome).label
    entry = None
    if good:
        entry_lines = [Line(item, to_location, n) for item, n in _per_item(pieces)]
        subtype = ServiceSubtype.REPLACEMENT
    elif outcome == Outcome.REJECTED_RETURNED:
        store = Location.defective_store()
        groups = Counter((p.item, p.batch_code, p.pkd) for p in pieces)
        entry_lines = [
            Line(item, store, n, code, pkd)
            for (item, code, pkd), n in sorted(
                groups.items(), key=lambda kv: (kv[0][0].code, kv[0][1], kv[0][2] or date.min)
            )
        ]
        subtype = ServiceSubtype.DEFECTIVE_RETURNED
    if good or outcome == Outcome.REJECTED_RETURNED:
        entry = post_entry(
            kind=EntryKind.IN,
            entry_date=settled_on,
            lines=entry_lines,
            user=user,
            subtype=subtype,
            party=batch.company.name,
            company=batch.company,
            ref=batch.number,
            note=f"{batch.number} {label}: {_tag_list(pieces)}",
            return_batch=batch,
        )
    to = PieceStatus.IN_STORE if outcome == Outcome.REJECTED_RETURNED else PieceStatus.SETTLED
    where = f" → {to_location.name}" if good else ""
    _move_all(pieces, to, at=settled_on, user=user, note=f"{batch.number}: {label}{where}", entry=entry)
    for p in pieces:
        p.outcome, p.settled_on = outcome, settled_on
        if good:
            p.replacement_entry = entry
        if to == PieceStatus.IN_STORE:
            p.return_batch = None
        line = open_lines[p.pk]
        line.outcome, line.settled_on, line.entry = outcome, settled_on, entry
        line.to_location = to_location if good else None
    DefectivePiece.objects.bulk_update(
        pieces, ["status", "outcome", "settled_on", "replacement_entry", "return_batch"]
    )
    BatchLine.objects.bulk_update(
        list(open_lines.values()), ["outcome", "settled_on", "entry", "to_location"]
    )
    return [entry] if entry else []
