"""Excel downloads for complaints, in the same layout as the stock exports."""

from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.excel import Column, workbook_response

from . import selectors
from .filters import AGE_BUCKETS, FINISHED, TAB_LABELS, complaint_filters
from .phones import format_phone

COLUMNS = [
    Column("Complaint no.", "code"),
    Column("Reported on", "date"),
    Column("Site", width=26),
    Column("City"),
    Column("Contact"),
    Column("Phone", "code"),
    Column("Company"),
    Column("Company complaint no.", "code"),
    Column("Fault", width=40),
    Column("Qty affected", "int"),
    Column("Technicians"),
    Column("Priority"),
    Column("Status"),
    Column("Age (days)", "int"),
    Column("Days awaiting material", "int"),
    Column("Last visit", "date"),
]
AGE_COLUMN = 13  # highlighted red when an open complaint is older than 15 days
LATE_DAYS = 15  # the same limit as the red age badge on the list


def _who(request):
    return request.user.first_name or request.user.username


def _describe(f, first, technicians="all technicians"):
    ages = {key: label for key, label, _, _ in AGE_BUCKETS}
    parts = [
        first,
        f.company.name if f.company else "all companies",
        f.city or "all cities",
        f.technician.name if f.technician else technicians,
        f"age {ages[f.age]}" if f.age else "",
        f"closed or not covered since {f.closed_since:%d-%m-%Y}" if f.closed_since else "",
        f'search "{f.q}"' if f.q else "",
    ]
    return " · ".join(p for p in parts if p)


def _cells(row):
    c = row["c"]
    return [
        c.number,
        c.reported_on,
        c.site.name,
        c.site.city,
        c.contact_name,
        format_phone(c.phone),
        c.company.name,
        c.company_ref,
        c.fault,
        c.qty_affected,
        row["techs"],
        c.get_priority_display(),
        c.get_status_display(),
        row["age"],
        row["awaiting"],
        c.last_visit,
    ]


@role_required(OFFICE)
def pending_complaints_xlsx(request):
    """Every open complaint (the list's other filters apply), oldest first; red age = open over 15 days."""
    f = complaint_filters(request.GET)
    f.tab, f.closed_since = "open", None  # "pending" means open, whatever tab the list was on
    rows, _ = selectors.complaint_rows(f, timezone.localdate())
    rows.sort(key=lambda r: (r["c"].reported_on, r["c"].number))
    filters = _describe(
        f,
        "Open complaints (Not attended, Attended, Material need to check, Awaiting material, Resolved)",
        technicians="",
    )
    late = {n for n, r in enumerate(rows) if r["age"] > LATE_DAYS}
    return workbook_response(
        "Pending_Complaints",
        "Pending Complaints",
        filters,
        _who(request),
        COLUMNS,
        [_cells(r) for r in rows],
        late,
        AGE_COLUMN,
    )


@role_required(OFFICE)
def complaints_xlsx(request):
    """The complaint list with its current filters (all pages), newest first."""
    f = complaint_filters(request.GET)
    rows, _ = selectors.complaint_rows(f, timezone.localdate())
    rows.sort(key=lambda r: (r["c"].reported_on, r["c"].number), reverse=True)
    cols = [*COLUMNS, Column("Closed on", "date"), Column("Not covered reason"), Column("Visits", "int")]
    data = [
        _cells(r) + [r["c"].closed_on, r["c"].get_not_covered_reason_display(), r["c"].n_visits] for r in rows
    ]
    label = {"all": "All statuses", FINISHED: "Closed and not covered"}.get(f.tab) or TAB_LABELS[f.tab]
    return workbook_response(
        "Complaint_List", "Complaint List", _describe(f, label), _who(request), cols, data
    )
