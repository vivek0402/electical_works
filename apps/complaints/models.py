"""Complaints from customer sites: who reported what, which company's product failed, who visited and what was
done. Statuses move only through services.py, which checks TRANSITIONS and logs a ComplaintEvent."""

import re

import pgtrigger
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.inventory.models import IMMUTABLE, Company, Location, StockEntry


class Status(models.TextChoices):
    NOT_ATTENDED = "NOT_ATTENDED", "Not attended"
    ATTENDED = "ATTENDED", "Attended"
    MATERIAL_CHECK = "MATERIAL_CHECK", "Material need to check"
    AWAITING_MATERIAL = "AWAITING_MATERIAL", "Awaiting material"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"
    NOT_COVERED = "NOT_COVERED", "Not covered"


OPEN_STATUSES = [
    Status.NOT_ATTENDED,
    Status.ATTENDED,
    Status.MATERIAL_CHECK,
    Status.AWAITING_MATERIAL,
    Status.RESOLVED,
]
FINISHED_STATUSES = [Status.CLOSED, Status.NOT_COVERED]  # these, and only these, have a closed_on date
# Where a visit can leave a complaint (a visit never closes it; that is a separate status change).
WORK_STATUSES = [Status.ATTENDED, Status.MATERIAL_CHECK, Status.AWAITING_MATERIAL, Status.RESOLVED]
# Moves allowed from each status, in the order they are offered. NOT_COVERED is its own action (it needs a
# reason). A CLOSED complaint can only be reopened by Admin (services.reopen), which moves it to ATTENDED.
TRANSITIONS = {
    Status.NOT_ATTENDED: [Status.ATTENDED, Status.NOT_COVERED],
    Status.ATTENDED: [Status.MATERIAL_CHECK, Status.AWAITING_MATERIAL, Status.RESOLVED, Status.NOT_COVERED],
    Status.MATERIAL_CHECK: [Status.ATTENDED, Status.AWAITING_MATERIAL, Status.RESOLVED, Status.NOT_COVERED],
    Status.AWAITING_MATERIAL: [Status.ATTENDED, Status.MATERIAL_CHECK, Status.RESOLVED, Status.NOT_COVERED],
    Status.RESOLVED: [Status.CLOSED, Status.ATTENDED, Status.NOT_COVERED],
    Status.CLOSED: [],
    Status.NOT_COVERED: [],
}


class Priority(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class NotCoveredReason(models.TextChoices):
    NOT_OURS = "NOT_OURS", "Not our product"
    OUT_OF_WARRANTY = "OUT_OF_WARRANTY", "Out of warranty"
    CANCELLED = "CANCELLED", "Customer cancelled"
    OTHER = "OTHER", "Other"


# A blank phone, or a 10-digit Indian mobile number with no spaces (services strip them before saving).
MOBILE_REGEX = r"^[6-9][0-9]{9}$"


def _phone_ok(name):
    return models.CheckConstraint(
        condition=Q(phone="") | Q(phone__regex=MOBILE_REGEX), name=f"{name}_phone_mobile"
    )


def _tidy(text):
    return re.sub(r"\s+", " ", text or "").strip()


class Site(models.Model):
    """A customer site. Picked from a searchable list when filing a complaint; keeps its complaint history.
    The same name can be in two cities ("Andhra University" in Visakhapatnam and in Guntur)."""

    name = models.CharField(max_length=120)
    city = models.CharField(max_length=60)
    contact_name = models.CharField("contact person", max_length=80, blank=True)
    phone = models.CharField(max_length=10, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "city"]
        constraints = [
            models.UniqueConstraint(Lower("name"), Lower("city"), name="site_name_city_ci_unique"),
            models.CheckConstraint(condition=~Q(name="") & ~Q(city=""), name="site_name_city_present"),
            _phone_ok("site"),
        ]

    def __str__(self):
        return f"{self.name}, {self.city}"

    def save(self, *args, **kwargs):
        self.name, self.city = _tidy(self.name), _tidy(self.city)
        super().save(*args, **kwargs)


class Technician(models.Model):
    """A technician who visits sites. Names only; technicians don't log in."""

    name = models.CharField(max_length=60)
    phone = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="technician_name_ci_unique"),
            models.CheckConstraint(condition=~Q(name=""), name="technician_name_present"),
            _phone_ok("technician"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = _tidy(self.name)
        super().save(*args, **kwargs)


class Complaint(models.Model):
    number = models.CharField(max_length=12, unique=True)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="complaints")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="complaints")  # whose product
    company_ref = models.CharField("company complaint no.", max_length=60, blank=True, db_index=True)
    fault = models.TextField()
    qty_affected = models.PositiveIntegerField(null=True, blank=True)
    reported_on = models.DateField()
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    technicians = models.ManyToManyField(
        Technician, blank=True, related_name="complaints", through="ComplaintTechnician"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_ATTENDED)
    contact_name = models.CharField("contact person", max_length=80, blank=True)  # copied from the site
    phone = models.CharField(max_length=10, blank=True)
    not_covered_reason = models.CharField(max_length=20, choices=NotCoveredReason.choices, blank=True)
    closed_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reported_on", "-id"]
        indexes = [models.Index(fields=["status", "reported_on"], name="complaint_status_reported_idx")]
        constraints = [
            models.CheckConstraint(condition=~Q(number=""), name="complaint_number_present"),
            models.CheckConstraint(condition=~Q(fault=""), name="complaint_fault_present"),
            models.CheckConstraint(
                condition=Q(closed_on__isnull=True) | Q(closed_on__gte=F("reported_on")),
                name="complaint_closed_after_reported",
            ),
            models.CheckConstraint(condition=Q(status__in=Status.values), name="complaint_status_valid"),
            models.CheckConstraint(
                condition=Q(priority__in=Priority.values), name="complaint_priority_valid"
            ),
            # Closed or Not covered exactly when it has a closed date (a reopened complaint loses it).
            models.CheckConstraint(
                condition=Q(status__in=FINISHED_STATUSES, closed_on__isnull=False)
                | (~Q(status__in=FINISHED_STATUSES) & Q(closed_on__isnull=True)),
                name="complaint_closed_on_matches_status",
            ),
            # Not covered always says why; no other status has a reason.
            models.CheckConstraint(
                condition=Q(status=Status.NOT_COVERED, not_covered_reason__in=NotCoveredReason.values)
                | (~Q(status=Status.NOT_COVERED) & Q(not_covered_reason="")),
                name="complaint_reason_matches_status",
            ),
            models.CheckConstraint(
                condition=Q(qty_affected__isnull=True) | Q(qty_affected__gte=1),
                name="complaint_qty_affected_positive",
            ),
            _phone_ok("complaint"),
        ]

    def __str__(self):
        return self.number

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES


class ComplaintEvent(models.Model):
    """Append-only history: every status change of a complaint, who made it, when, and why."""

    complaint = models.ForeignKey(Complaint, on_delete=models.PROTECT, related_name="events")
    from_status = models.CharField(max_length=20, choices=Status.choices, blank=True)  # blank: filed
    to_status = models.CharField(max_length=20, choices=Status.choices)
    at = models.DateField()
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    reason = models.CharField(max_length=20, choices=NotCoveredReason.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]
        triggers = [IMMUTABLE]
        constraints = [
            models.CheckConstraint(
                condition=Q(to_status__in=Status.values) & Q(from_status__in=["", *Status.values]),
                name="complaint_event_status_valid",
            ),
            models.CheckConstraint(
                condition=~Q(from_status=F("to_status")), name="complaint_event_is_a_move"
            ),
            # A move to Not covered always records why; no other move has a reason.
            models.CheckConstraint(
                condition=Q(to_status=Status.NOT_COVERED, reason__in=NotCoveredReason.values)
                | (~Q(to_status=Status.NOT_COVERED) & Q(reason="")),
                name="complaint_event_reason_only_not_covered",
            ),
        ]

    def __str__(self):
        return f"{self.complaint}: {self.from_status or '-'} -> {self.to_status}"


class Visit(models.Model):
    """A technicians' visit to the site: work done, parts given (one Stock OUT) and failed parts collected
    (one Stock IN at the Defective store, one tagged piece per unit)."""

    number = models.CharField(max_length=12, unique=True)
    complaint = models.ForeignKey(Complaint, on_delete=models.PROTECT, related_name="visits")
    visit_date = models.DateField()
    technicians = models.ManyToManyField(Technician, related_name="visits", through="VisitTechnician")
    work_done = models.TextField()
    next_status = models.CharField(max_length=20, choices=Status.choices)
    # The location the parts were given from: set exactly when there is a parts-given OUT.
    location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    out_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="visit_given"
    )
    collect_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="visit_collected"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visit_date", "-id"]
        # A visit posted stock and tagged pieces, so it is never deleted. Updates stay possible.
        triggers = [pgtrigger.Protect(name="visit_no_delete", operation=pgtrigger.Delete)]
        constraints = [
            models.CheckConstraint(condition=~Q(number=""), name="visit_number_present"),
            models.CheckConstraint(condition=~Q(work_done=""), name="visit_work_done_present"),
            models.CheckConstraint(
                condition=Q(next_status__in=WORK_STATUSES), name="visit_next_status_is_work"
            ),
            models.CheckConstraint(
                condition=Q(location__isnull=True, out_entry__isnull=True)
                | Q(location__isnull=False, out_entry__isnull=False),
                name="visit_location_with_parts",
            ),
        ]

    def __str__(self):
        return self.number


# The technician links. Their own models so that a technician with any history can't be deleted (PROTECT);
# hide them instead (is_active).
class ComplaintTechnician(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="+")
    technician = models.ForeignKey(Technician, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["complaint", "technician"], name="complaint_technician_once")
        ]

    def __str__(self):
        return f"{self.complaint_id} / {self.technician_id}"


class VisitTechnician(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name="+")
    technician = models.ForeignKey(Technician, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["visit", "technician"], name="visit_technician_once")]

    def __str__(self):
        return f"{self.visit_id} / {self.technician_id}"
