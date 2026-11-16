"""All reads for the defectives screens. Views call these; no queries in templates."""

from collections import defaultdict
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Q

from apps.inventory.models import Item
from apps.inventory.normalise import normalise_code

from .models import BatchLine, BatchStatus, DefectivePiece, Outcome, PieceStatus, ReturnBatch, Source
from .services import normalise_tag

# What a piece row shows, including the complaint and site of the visit that collected it.
PIECE_RELATED = ["item", "company", "return_batch", "visit__complaint__site"]


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
        if f.waiting_over is not None and (waiting is None or waiting <= f.waiting_over):
            continue
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
    """[complaint no., company complaint no.] for the dispatch list ('Found in stock' for pieces from stock).
    Expects a piece from pieces_qs() or a batch line's piece, so its visit and complaint are loaded."""
    if piece.visit_id:
        return [piece.visit.complaint.number, piece.visit.complaint.company_ref]
    return ["Found in stock" if piece.source == Source.FOUND_IN_STOCK else "", ""]


def piece_search_q(text):
    """The pieces search box: a tag typed loosely (def-42), batch code, fault, return batch no., item code or
    the number of the complaint whose visit collected the piece."""
    return (
        Q(tag__icontains=normalise_tag(text))
        | Q(batch_code__icontains=text)
        | Q(fault__icontains=text)
        | Q(return_batch__number__icontains=text)
        | Q(item__code__icontains=normalise_code(text))
        | Q(visit__complaint__number__icontains=text)
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
    if f.answered:
        # Same rule as the dashboard's outcome counts: the answers on the batch lines, not the piece's latest.
        answers = {"batch_lines__outcome": f.answered}
        if f.since:
            answers["batch_lines__settled_on__gt"] = f.since
        pieces = pieces.filter(**answers).distinct()
    if f.q:
        pieces = pieces.filter(piece_search_q(f.q))
    return list(pieces)


def piece_items():
    """Items that have ever had a defective piece (the item filter on the pieces list)."""
    return Item.objects.filter(defective_pieces__isnull=False).distinct().order_by("code")


def piece_counts():
    """Pieces in store, in draft batches and sent, in one query: {"in_store", "in_batch", "sent"}.
    Task 16's main-dashboard `service_stats` must import this, so both dashboards always agree."""
    counts = dict(DefectivePiece.objects.values_list("status").annotate(n=Count("id")))
    return {
        "in_store": counts.get(PieceStatus.IN_STORE, 0),
        "in_batch": counts.get(PieceStatus.IN_BATCH, 0),
        "sent": counts.get(PieceStatus.SENT, 0),
    }


OVERDUE_DAYS = 30  # a batch still waiting on the company after this many days needs a chase


def dashboard(today, counts=None):
    """Figures for the defectives dashboard. Answers come from BatchLine: a piece's own outcome is empty while
    it sits in a draft or sent batch, and a piece rejected and replaced later has two answers.
    `counts` is piece_counts() when the caller already has it (the request's menu badges do)."""
    in_store, in_batch = Q(status=PieceStatus.IN_STORE), Q(status=PieceStatus.IN_BATCH)
    store_rows = list(
        DefectivePiece.objects.filter(in_store | in_batch)
        .values("company_id", "company__name")
        .annotate(store=Count("id", filter=in_store), batch=Count("id", filter=in_batch))
        .order_by("-store", "company__name")
    )
    sent_batches = defaultdict(list)  # company id -> its batches with pieces still out, oldest first
    out = ReturnBatch.objects.filter(pieces__status=PieceStatus.SENT).distinct()
    for b in out.order_by("dispatched_on", "id"):
        sent_batches[b.company_id].append(b)
    sent_rows = []
    sent = DefectivePiece.objects.filter(status=PieceStatus.SENT)
    for row in sent.values("company_id", "company__name").annotate(n=Count("id")).order_by("company__name"):
        batches = sent_batches[row["company_id"]]
        oldest = batches[0]
        sent_rows.append(
            {**row, "batches": batches, "oldest": oldest, "waiting": (today - oldest.dispatched_on).days}
        )
    sent_rows.sort(key=lambda r: -r["waiting"])
    # Batches the companies have kept longer than OVERDUE_DAYS: exactly the rows of /batches/?waiting_over=30.
    overdue = sum(
        1
        for batches in sent_batches.values()
        for b in batches
        if (today - b.dispatched_on).days > OVERDUE_DAYS
    )
    # One row per company: what is in the store, in a draft batch and out with the company.
    companies = {
        r["company_id"]: {
            "company_id": r["company_id"],
            "name": r["company__name"],
            "store": r["store"],
            "batch": r["batch"],
            "sent": 0,
            "batches": [],
            "waiting": None,
        }
        for r in store_rows
    }
    for r in sent_rows:
        row = companies.setdefault(
            r["company_id"],
            {"company_id": r["company_id"], "name": r["company__name"], "store": 0, "batch": 0},
        )
        row.update(sent=r["n"], batches=r["batches"], waiting=r["waiting"])
    company_rows = list(companies.values())
    for row in company_rows:
        row.setdefault("sent", 0), row.setdefault("batches", []), row.setdefault("waiting", None)
    since = today - timedelta(days=90)  # answers dated after this day: exactly the last 90 days
    answered = BatchLine.objects.exclude(outcome="").filter(settled_on__gt=since)
    by_outcome = dict(answered.values_list("outcome").annotate(n=Count("id")))
    longest = pieces_qs().filter(status=PieceStatus.IN_STORE).order_by("collected_on", "tag")[:6]
    return {
        **(counts or piece_counts()),
        "since": since,
        "overdue": overdue,
        "company_rows": company_rows,
        "drafts": ReturnBatch.objects.filter(status=BatchStatus.DRAFT).count(),
        "answered": sum(by_outcome.values()),
        "store_rows": store_rows,
        "sent_rows": sent_rows,
        "outcomes": [(value, label, by_outcome.get(value, 0)) for value, label in Outcome.choices],
        "oldest": [{"piece": p, "days": (today - p.collected_on).days} for p in longest],
    }


def defective_list_rows():
    """Pieces physically in the Defective store (in store + in draft batches), grouped by company, item, batch
    code and PKD: [company, item code, description, batch code, PKD, qty, of which in a draft batch, tags]."""
    groups = defaultdict(list)
    for p in pieces_qs().filter(status__in=[PieceStatus.IN_STORE, PieceStatus.IN_BATCH]).order_by("tag"):
        groups[(p.company.name, p.item.code, p.batch_code, p.pkd)].append(p)
    ordered = sorted(groups.items(), key=lambda kv: (*kv[0][:3], kv[0][3] or date.min))
    return [
        [
            company,
            code,
            ps[0].item.description,
            batch,
            f"{pkd:%m-%Y}" if pkd else "",
            len(ps),
            sum(p.status == PieceStatus.IN_BATCH for p in ps),
            ", ".join(p.tag for p in ps),
        ]
        for (company, code, batch, pkd), ps in ordered
    ]
