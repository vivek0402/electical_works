"""All reads for the defectives screens. Views call these; no queries in templates."""

from datetime import date

from django.conf import settings
from django.db.models import Count, Q

from apps.inventory.models import Item
from apps.inventory.normalise import normalise_code

from .models import DefectivePiece, ReturnBatch, Source
from .services import normalise_tag

# What a piece row shows. Task 10 adds the complaint and site of the visit that collected it.
PIECE_RELATED = ["item", "company", "return_batch"]


def pieces_qs():
    return DefectivePiece.objects.select_related(*PIECE_RELATED)


def batch_label(batch, lines, settled):
    """'Draft', 'Dispatched', 'Partly settled' or 'Settled' (worked out, never stored)."""
    if batch.is_draft:
        return "Draft"
    if settled == 0:
        return "Dispatched"
    return "Partly settled" if settled < lines else "Settled"


def batches_with_counts():
    return ReturnBatch.objects.select_related("company").annotate(
        n_lines=Count("lines", distinct=True),
        n_settled=Count("lines", filter=~Q(lines__outcome=""), distinct=True),
    )


def batch_rows(f, today):
    """Return-batch list rows: {batch, label, waiting (days since dispatch while not fully settled)}."""
    batches = batches_with_counts()
    if f.company:
        batches = batches.filter(company=f.company)
    rows = []
    for b in batches:
        label = batch_label(b, b.n_lines, b.n_settled)
        if f.status and label != f.status:
            continue
        waiting = (today - b.dispatched_on).days if b.dispatched_on and label != "Settled" else None
        rows.append({"batch": b, "label": label, "waiting": waiting})
    return rows


def batch_lines(batch):
    """The batch's lines with their pieces, in tag order. Each line holds this batch's answer."""
    related = [f"piece__{name}" for name in PIECE_RELATED]
    return list(batch.lines.select_related(*related, "to_location", "entry").order_by("piece__tag"))


def answer_groups(lines):
    """The answered lines grouped as they were recorded: one group per settle call.

    A settle call posts one entry for all its pieces, so lines group by entry. Rejected (scrapped) posts no
    entry, so those lines group by date. Returns [{outcome, settled_on, to_location, entry, tags}] by date.
    """
    groups = {}
    for line in lines:
        if not line.outcome:
            continue
        key = ("entry", line.entry_id) if line.entry_id else ("none", line.outcome, line.settled_on)
        group = groups.setdefault(
            key,
            {
                "outcome": line.outcome,
                "settled_on": line.settled_on,
                "to_location": line.to_location,
                "entry": line.entry,
                "tags": [],
            },
        )
        group["tags"].append(line.piece.tag)
    return sorted(
        groups.values(), key=lambda g: (g["settled_on"] or date.min, g["entry"].pk if g["entry"] else 0)
    )


def piece_batch_lines(piece):
    """Every batch the piece went into, newest first, each with that batch's answer from its BatchLine."""
    return list(
        piece.batch_lines.select_related("batch", "to_location", "entry").order_by(
            "-batch__created_on", "-batch_id"
        )
    )


def courier_suggestions():
    """Couriers to suggest when dispatching: the configured list, then any others used before."""
    used = ReturnBatch.objects.exclude(courier="").order_by("-id").values_list("courier", flat=True)[:200]
    return list(dict.fromkeys([*settings.COURIERS, *used]))


def complaint_cells(piece):
    """[complaint no., company complaint no.] for the dispatch list. Task 10 fills these from the visit."""
    return ["Found in stock" if piece.source == Source.FOUND_IN_STOCK else "", ""]


def piece_search_q(text):
    """The pieces search box: a tag typed loosely (def-42), batch code, fault, return batch no. or item code.
    Task 10 adds the complaint number."""
    return (
        Q(tag__icontains=normalise_tag(text))
        | Q(batch_code__icontains=text)
        | Q(fault__icontains=text)
        | Q(return_batch__number__icontains=text)
        | Q(item__code__icontains=normalise_code(text))
    )


def piece_rows(f):
    pieces = pieces_qs()
    for field, value in (
        ("company", f.company),
        ("item", f.item),
        ("status", f.status),
        ("source", f.source),
        ("outcome", f.outcome),
    ):
        if value:
            pieces = pieces.filter(**{field: value})
    if f.date_from:
        pieces = pieces.filter(collected_on__gte=f.date_from)
    if f.date_to:
        pieces = pieces.filter(collected_on__lte=f.date_to)
    if f.q:
        pieces = pieces.filter(piece_search_q(f.q))
    return list(pieces)


def piece_items():
    """Items that have ever had a defective piece (the item filter on the pieces list)."""
    return Item.objects.filter(defective_pieces__isnull=False).distinct().order_by("code")
