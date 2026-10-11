import pgtrigger
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Func, Q, Value
from django.db.models.functions import Upper

from .normalise import LEADING_ZEROS, NON_ALNUM


def search_key_expression(field):
    """SQL twin of `normalise.search_key` (stored generated column, so admin edits stay correct)."""
    translated = Func(Upper(F(field)), Value("OI"), Value("01"), function="translate")
    no_zeros = Func(
        translated, Value(LEADING_ZEROS), Value(r"\1\2"), Value("g"), function="regexp_replace"
    )
    return Func(
        no_zeros,
        Value(NON_ALNUM),
        Value(""),
        Value("g"),
        function="regexp_replace",
        output_field=models.CharField(),
    )


class Location(models.Model):
    """A place that holds stock (store, office, shop…).

    Deactivate, never delete, once it has history.
    """

    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ItemType(models.TextChoices):
    FITTING = "FITTING", "Fitting"
    DRIVER = "DRIVER", "Driver"
    PCB = "PCB", "PCB / LED module"
    LENS = "LENS", "Lens"
    CONTROLLER = "CONTROLLER", "Controller"
    SWITCH = "SWITCH", "Switch"
    ACCESSORY = "ACCESSORY", "Accessory"
    OTHER = "OTHER", "Other"


class Unit(models.TextChoices):
    NOS = "NOS", "NOS"


class Item(models.Model):
    """A spare part or fitting, identified by one normalised code."""

    code = models.CharField(max_length=80, unique=True, help_text="Stored upper-case, trimmed.")
    search_key = models.GeneratedField(
        expression=search_key_expression("code"),
        output_field=models.CharField(max_length=80),
        db_persist=True,
    )
    item_type = models.CharField(max_length=12, choices=ItemType.choices, default=ItemType.OTHER)
    description = models.CharField(max_length=200, blank=True)
    fitting_type = models.CharField(max_length=80, blank=True)
    wattage_w = models.PositiveSmallIntegerField("wattage (W)", null=True, blank=True)
    current_ma = models.PositiveSmallIntegerField("current (mA)", null=True, blank=True)
    brand = models.CharField(max_length=40, default="Wipro")
    unit = models.CharField(max_length=8, choices=Unit.choices, default=Unit.NOS)
    reorder_level = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(code=Upper(F("code"))) & ~Q(code=""), name="item_code_normalised"
            ),
        ]
        indexes = [
            models.Index(fields=["search_key"], name="item_search_key_idx"),
            GinIndex(fields=["code"], opclasses=["gin_trgm_ops"], name="item_code_trgm"),
            GinIndex(fields=["search_key"], opclasses=["gin_trgm_ops"], name="item_key_trgm"),
            models.Index(fields=["item_type"], name="item_type_idx"),
        ]

    def __str__(self):
        return self.code


class ItemAlias(models.Model):
    """Another spelling that maps to an item (e.g. EI08437 -> EIO8437)."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "item aliases"
        constraints = [
            models.CheckConstraint(
                condition=Q(alias=Upper(F("alias"))) & ~Q(alias=""), name="alias_normalised"
            ),
        ]
        indexes = [
            GinIndex(fields=["alias"], opclasses=["gin_trgm_ops"], name="alias_trgm"),
        ]

    def __str__(self):
        return f"{self.alias} → {self.item.code}"


class Bucket(models.TextChoices):
    FRESH = "FRESH", "Fresh"
    DEFECTIVE = "DEFECTIVE", "Defective"


class DocType(models.TextChoices):
    OPENING = "OPENING", "Opening stock"
    RECEIVED_FROM_WIPRO = "RECEIVED_FROM_WIPRO", "Received from Wipro"
    ISSUED_TO_COMPLAINT = "ISSUED_TO_COMPLAINT", "Issued to complaint"
    DEFECTIVE_COLLECTED = "DEFECTIVE_COLLECTED", "Defective collected"
    RETURNED_TO_WIPRO = "RETURNED_TO_WIPRO", "Returned to Wipro"
    TRANSFER = "TRANSFER", "Transfer"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    SCRAPPED = "SCRAPPED", "Scrapped"


IMMUTABLE = pgtrigger.Protect(name="append_only", operation=pgtrigger.Update | pgtrigger.Delete)


class StockDocument(models.Model):
    """Header of one stock event (a receipt, a transfer, an opening count…). Append-only."""

    doc_type = models.CharField(max_length=24, choices=DocType.choices)
    doc_date = models.DateField()
    ref_no = models.CharField("ref / DC no.", max_length=60, blank=True)
    reason = models.TextField(blank=True)
    reverses = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversed_by",
        help_text="Set when this document cancels an earlier one.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-doc_date", "-id"]
        constraints = [
            # Re-running an import must not post the same opening twice.
            models.UniqueConstraint(
                fields=["doc_type", "ref_no"],
                condition=Q(doc_type="OPENING") & ~Q(ref_no=""),
                name="unique_opening_ref",
            ),
        ]
        indexes = [models.Index(fields=["doc_type", "doc_date"], name="doc_type_date_idx")]
        triggers = [IMMUTABLE]

    def __str__(self):
        return f"{self.get_doc_type_display()} #{self.pk} ({self.doc_date:%d-%m-%Y})"


class StockMovement(models.Model):
    """One ledger line: signed qty of an item into (+) or out of (−) a location bucket."""

    document = models.ForeignKey(StockDocument, on_delete=models.PROTECT, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movements")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="movements")
    bucket = models.CharField(max_length=10, choices=Bucket.choices)
    qty = models.IntegerField()
    batch_code = models.CharField(max_length=40, blank=True)
    pkd_date = models.DateField("PKD", null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=~Q(qty=0), name="movement_qty_nonzero"),
            models.CheckConstraint(
                condition=Q(bucket__in=Bucket.values), name="movement_bucket_valid"
            ),
        ]
        indexes = [models.Index(fields=["item", "location", "bucket"], name="move_stock_key_idx")]
        triggers = [IMMUTABLE]

    def __str__(self):
        return f"{self.qty:+d} {self.item} {self.bucket} @ {self.location}"


class StockBalance(models.Model):
    """Cached current stock per item/location/bucket. Rebuildable from StockMovement."""

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="balances")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="balances")
    bucket = models.CharField(max_length=10, choices=Bucket.choices)
    qty = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "location", "bucket"], name="one_balance_row"),
            models.CheckConstraint(condition=Q(qty__gte=0), name="balance_never_negative"),
            models.CheckConstraint(
                condition=Q(bucket__in=Bucket.values), name="balance_bucket_valid"
            ),
        ]
        indexes = [models.Index(fields=["location", "bucket"], name="balance_loc_bucket_idx")]

    def __str__(self):
        return f"{self.item} {self.bucket} @ {self.location}: {self.qty}"
