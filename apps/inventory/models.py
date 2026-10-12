import re

import pgtrigger
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Upper

from .normalise import normalise_code
from .normalise import search_key as make_search_key


class Master(models.Model):
    """Simple named list managed by admins. Deactivate, never delete, once used."""

    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="%(app_label)s_%(class)s_name_ci_unique"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = re.sub(r"\s+", " ", self.name or "").strip()
        super().save(*args, **kwargs)


class Location(Master):
    pass


class Company(Master):
    """Supplier / manufacturer / brand (Wipro Lighting, Finolex Cables, local traders...)."""

    class Meta(Master.Meta):
        verbose_name_plural = "companies"


class FittingType(Master):
    pass


class SpareType(Master):
    pass


class Unit(models.TextChoices):
    NOS = "NOS", "NOS"
    MTR = "MTR", "MTR"
    ROLL = "ROLL", "ROLL"
    BOX = "BOX", "BOX"
    PKT = "PKT", "PKT"


class Item(models.Model):
    """A spare (driver, PCB, lens, complete fitting, wire...) with its own code and parent fitting."""

    code = models.CharField(max_length=80, unique=True)
    search_key = models.CharField(max_length=80, db_index=True, editable=False)
    spare_type = models.ForeignKey(SpareType, on_delete=models.PROTECT)
    description = models.CharField(max_length=200, blank=True)
    cat_ref = models.CharField("used in fitting (product cat ref)", max_length=80, blank=True)
    fitting_type = models.ForeignKey(FittingType, on_delete=models.PROTECT, null=True, blank=True)
    wattage_w = models.PositiveSmallIntegerField(null=True, blank=True)
    current_ma = models.PositiveSmallIntegerField(null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    unit = models.CharField(max_length=4, choices=Unit.choices, default=Unit.NOS)
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
            models.CheckConstraint(condition=~Q(search_key=""), name="item_search_key_not_empty"),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = normalise_code(self.code)
        self.search_key = make_search_key(self.code)
        super().save(*args, **kwargs)


class ItemAlias(models.Model):
    """Another spelling of an item's code (e.g. EI08437 for EIO8437)."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=80, unique=True)
    search_key = models.CharField(max_length=80, db_index=True, editable=False)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "item aliases"
        constraints = [
            models.CheckConstraint(
                condition=Q(alias=Upper(F("alias"))) & ~Q(alias=""), name="alias_normalised"
            ),
            models.CheckConstraint(condition=~Q(search_key=""), name="alias_search_key_not_empty"),
        ]

    def __str__(self):
        return self.alias

    def save(self, *args, **kwargs):
        self.alias = normalise_code(self.alias)
        self.search_key = make_search_key(self.alias)
        super().save(*args, **kwargs)


class EntryKind(models.TextChoices):
    IN = "IN", "Stock IN"
    OUT = "OUT", "Stock OUT"
    TRF = "TRF", "Transfer"
    ADJ = "ADJ", "Adjustment"
    REV = "REV", "Undo"


class InSource(models.TextChoices):
    SUPPLIER = "SUPPLIER", "From supplier"
    RETURN = "RETURN", "Returned unused from site"
    OPENING = "OPENING", "Opening stock"


class OutTarget(models.TextChoices):
    SITE = "SITE", "Site / customer"
    TECH = "TECH", "Technician"
    OTHER = "OTHER", "Other"


class AdjustReason(models.TextChoices):
    COUNT = "COUNT", "Physical count"
    DAMAGED = "DAMAGED", "Damaged"
    LOST = "LOST", "Lost"
    FOUND = "FOUND", "Found"
    OTHER = "OTHER", "Other"


class EntryCounter(models.Model):
    """Last number used per entry kind (IN-0007 ...). Locked while posting."""

    kind = models.CharField(max_length=3, primary_key=True, choices=EntryKind.choices)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.kind}: {self.last}"


IMMUTABLE = pgtrigger.Protect(name="append_only", operation=pgtrigger.Update | pgtrigger.Delete)
# No TRUNCATE guard on purpose. A BEFORE TRUNCATE trigger (pgtrigger.Trigger, Statement level; Protect
# can't do TRUNCATE) works, but Django's flush between transaction=True tests (e.g. the concurrency test)
# uses TRUNCATE and then fails. TRUNCATE needs table-owner (or TRUNCATE) rights; keep those off the app role.


class StockEntry(models.Model):
    """One stock event (a receipt, an issue, a transfer, a count correction, an undo). Never edited."""

    number = models.CharField(max_length=12, unique=True)
    kind = models.CharField(max_length=3, choices=EntryKind.choices)
    subtype = models.CharField(max_length=10, blank=True)  # InSource for IN, OutTarget for OUT
    entry_date = models.DateField()
    party = models.CharField("supplier / issued to", max_length=120, blank=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, null=True, blank=True)
    ref = models.CharField("DC / ref no.", max_length=60, blank=True)
    reason = models.CharField(max_length=10, choices=AdjustReason.choices, blank=True)
    note = models.TextField(blank=True)
    reverses = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-id"]
        indexes = [models.Index(fields=["kind", "entry_date"], name="entry_kind_date_idx")]
        triggers = [IMMUTABLE]

    def __str__(self):
        return self.number

    @property
    def details(self):
        """Short human description.

        e.g. 'From supplier', 'To site / customer', 'Damaged', 'Undo of OUT-0003'.
        """
        if self.kind == EntryKind.IN:
            return InSource(self.subtype).label if self.subtype else ""
        if self.kind == EntryKind.OUT:
            return f"To {OutTarget(self.subtype).label.lower()}" if self.subtype else ""
        if self.kind == EntryKind.TRF:
            return "Between locations"
        if self.kind == EntryKind.ADJ:
            return self.get_reason_display()
        return f"Undo of {self.reverses.number}" if self.reverses_id else "Undo"

    @property
    def is_undone(self):
        """True if an Undo entry reverses this one (uses the `undone_flag` annotation when present)."""
        flag = getattr(self, "undone_flag", None)
        return StockEntry.objects.filter(reverses=self).exists() if flag is None else flag


class StockLine(models.Model):
    """Signed quantity of an item into (+) or out of (-) a location. Never edited."""

    entry = models.ForeignKey(StockEntry, on_delete=models.PROTECT, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="lines")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="lines")
    qty = models.IntegerField()
    batch_code = models.CharField(max_length=40, blank=True)
    pkd = models.DateField("packed (month)", null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=~Q(qty=0), name="line_qty_nonzero")]
        indexes = [models.Index(fields=["item", "location"], name="line_item_loc_idx")]
        triggers = [IMMUTABLE]

    def __str__(self):
        return f"{self.qty:+d} {self.item} @ {self.location}"


class StockBalance(models.Model):
    """Cached stock per item and location. Rebuildable from StockLine; can never go negative."""

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="balances")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="balances")
    qty = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "location"], name="one_balance_row"),
            models.CheckConstraint(condition=Q(qty__gte=0), name="balance_never_negative"),
        ]

    def __str__(self):
        return f"{self.item} @ {self.location}: {self.qty}"
