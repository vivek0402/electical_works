"""Defective pieces: every failed part tracked one physical piece at a time, from collection to the company's
answer. Statuses move only through services.py, which checks TRANSITIONS and logs a DefectiveEvent."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.inventory.models import IMMUTABLE, Company, Item, Location, StockEntry


class PieceStatus(models.TextChoices):
    IN_STORE = "IN_STORE", "In store"
    IN_BATCH = "IN_BATCH", "In draft batch"
    SENT = "SENT", "Sent to company"
    SETTLED = "SETTLED", "Settled"
    SCRAPPED = "SCRAPPED", "Scrapped"


# Moves a piece may make. SENT -> IN_STORE means "rejected, and the company sent it back".
TRANSITIONS = {
    PieceStatus.IN_STORE: {PieceStatus.IN_BATCH, PieceStatus.SCRAPPED},
    PieceStatus.IN_BATCH: {PieceStatus.IN_STORE, PieceStatus.SENT},
    PieceStatus.SENT: {PieceStatus.SETTLED, PieceStatus.IN_STORE},
    PieceStatus.SETTLED: set(),
    PieceStatus.SCRAPPED: set(),
}


class Outcome(models.TextChoices):
    REPLACED = "REPLACED", "Replaced"
    REPAIRED = "REPAIRED", "Repaired"
    REJECTED_RETURNED = "REJECTED_RETURNED", "Rejected (returned)"
    REJECTED_SCRAPPED = "REJECTED_SCRAPPED", "Rejected (scrapped)"


GOOD_OUTCOMES = {Outcome.REPLACED, Outcome.REPAIRED}  # a piece comes back into good stock
UNBATCHED = [PieceStatus.IN_STORE, PieceStatus.SCRAPPED]  # statuses where a piece is in no batch


class Source(models.TextChoices):
    SITE_VISIT = "SITE_VISIT", "Site visit"
    FOUND_IN_STOCK = "FOUND_IN_STOCK", "Found in stock"


class BatchStatus(models.TextChoices):
    """Stored status. 'Partly settled' and 'Settled' are worked out from the lines (selectors.batch_label)."""

    DRAFT = "DRAFT", "Draft"
    DISPATCHED = "DISPATCHED", "Dispatched"


class ScrapReason(models.TextChoices):
    NOT_WORTH = "NOT_WORTH", "Not worth returning"
    BURNT = "BURNT", "Burnt / physically damaged"
    REJECTED = "REJECTED", "Rejected by the company"
    OTHER = "OTHER", "Other"


class ReturnBatch(models.Model):
    """Pieces going back to one company together. Locked once dispatched."""

    number = models.CharField(max_length=12, unique=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="return_batches")
    created_on = models.DateField()
    status = models.CharField(max_length=10, choices=BatchStatus.choices, default=BatchStatus.DRAFT)
    dispatched_on = models.DateField(null=True, blank=True)
    docket_no = models.CharField("docket / LR no.", max_length=40, blank=True)
    courier = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=200, blank=True)
    dispatch_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="dispatched_batch"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "return batches"
        constraints = [
            # Dispatched exactly when it has a dispatch date and the Stock OUT that sent it.
            models.CheckConstraint(
                condition=Q(
                    status=BatchStatus.DISPATCHED, dispatched_on__isnull=False, dispatch_entry__isnull=False
                )
                | (
                    ~Q(status=BatchStatus.DISPATCHED)
                    & Q(dispatched_on__isnull=True, dispatch_entry__isnull=True)
                ),
                name="batch_dispatched_has_date_and_entry",
            ),
        ]

    def __str__(self):
        return self.number

    @property
    def is_draft(self):
        return self.status == BatchStatus.DRAFT


class DefectivePiece(models.Model):
    """One physical failed piece with its own tag. Its company is copied from the item when collected."""

    tag = models.CharField(max_length=12, unique=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="defective_pieces")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="defective_pieces")
    batch_code = models.CharField(max_length=40, blank=True)
    pkd = models.DateField("packed (month)", null=True, blank=True)
    fault = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    collected_on = models.DateField()
    status = models.CharField(max_length=10, choices=PieceStatus.choices, default=PieceStatus.IN_STORE)
    # The batch the piece is in (draft, sent or settled). Cleared when it is removed or sent back rejected.
    return_batch = models.ForeignKey(
        ReturnBatch, on_delete=models.PROTECT, null=True, blank=True, related_name="pieces"
    )
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)  # the latest answer
    settled_on = models.DateField(null=True, blank=True)
    replacement_entry = models.ForeignKey(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="replaced_pieces"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["status", "company"], name="piece_status_company_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=PieceStatus.values), name="piece_status_valid"),
            # In store or scrapped: no batch. In a draft batch, sent or settled: always a batch.
            models.CheckConstraint(
                condition=Q(status__in=UNBATCHED, return_batch__isnull=True)
                | (~Q(status__in=UNBATCHED) & Q(return_batch__isnull=False)),
                name="piece_batch_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(status=PieceStatus.SETTLED) | (~Q(outcome="") & Q(settled_on__isnull=False)),
                name="piece_settled_has_outcome",
            ),
            models.CheckConstraint(
                condition=Q(replacement_entry__isnull=True)
                | Q(outcome__in=[Outcome.REPLACED, Outcome.REPAIRED]),
                name="piece_replacement_needs_good_outcome",
            ),
        ]

    def __str__(self):
        return self.tag


class BatchLine(models.Model):
    """One piece in one return batch, with the company's answer for it. A piece that was rejected and sent
    back can go out again in a later batch, so its earlier answers stay on record here."""

    batch = models.ForeignKey(ReturnBatch, on_delete=models.PROTECT, related_name="lines")
    piece = models.ForeignKey(DefectivePiece, on_delete=models.PROTECT, related_name="batch_lines")
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    settled_on = models.DateField(null=True, blank=True)
    to_location = models.ForeignKey(
        Location, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    entry = models.ForeignKey(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="settled_lines"
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "piece"], name="piece_once_per_batch"),
            # A piece waits on at most one company answer at a time.
            models.UniqueConstraint(
                fields=["piece"], condition=Q(outcome=""), name="one_open_line_per_piece"
            ),
            # An answer always has its date, and a date always has its answer.
            models.CheckConstraint(
                condition=Q(outcome="", settled_on__isnull=True)
                | (~Q(outcome="") & Q(settled_on__isnull=False)),
                name="line_outcome_has_date",
            ),
        ]

    def __str__(self):
        return f"{self.batch} / {self.piece}"


class DefectiveEvent(models.Model):
    """Append-only history of a piece: every status change, with the ledger entry that moved it (if any)."""

    piece = models.ForeignKey(DefectivePiece, on_delete=models.PROTECT, related_name="events")
    from_status = models.CharField(max_length=10, choices=PieceStatus.choices, blank=True)
    to_status = models.CharField(max_length=10, choices=PieceStatus.choices)
    at = models.DateField()
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    entry = models.ForeignKey(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="defective_events"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]
        triggers = [IMMUTABLE]

    def __str__(self):
        return f"{self.piece}: {self.from_status or '-'} -> {self.to_status}"
