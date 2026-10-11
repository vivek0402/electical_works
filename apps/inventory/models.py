from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Upper


class Master(models.Model):
    """Simple named list managed by admins. Deactivate, never delete, once used."""

    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


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
    search_key = models.CharField(max_length=80, db_index=True)
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
        ]

    def __str__(self):
        return self.code


class ItemAlias(models.Model):
    """Another spelling of an item's code (e.g. EI08437 for EIO8437)."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=80, unique=True)
    search_key = models.CharField(max_length=80, db_index=True)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "item aliases"

    def __str__(self):
        return self.alias
