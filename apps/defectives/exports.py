"""Excel downloads for the defectives module, in the same layout as the stock exports."""

from django.shortcuts import get_object_or_404

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.excel import Column, workbook_response

from . import selectors
from .models import ReturnBatch


def _who(request):
    return request.user.first_name or request.user.username


@role_required(OFFICE)
def defective_list_xlsx(request):
    cols = [
        Column("Company"),
        Column("Item code", "code"),
        Column("Description", width=28),
        Column("Batch code", "code"),
        Column("PKD"),
        Column("Qty in store", "int"),
        Column("Of which in a draft batch", "int"),
        Column("Tags", "code", width=40),
    ]
    return workbook_response(
        "Defective_List",
        "Defective List",
        "Pieces in the Defective store (in store + in draft batches) · grouped by company",
        _who(request),
        cols,
        selectors.defective_list_rows(),
    )


@role_required(OFFICE)
def batch_xlsx(request, number):
    """The dispatch list that goes with the shipment: one row per piece, with this batch's answer."""
    batch = get_object_or_404(ReturnBatch.objects.select_related("company"), number=number)
    lines = selectors.batch_lines(batch)
    if batch.is_draft:
        status = "Draft (not dispatched yet)"
    else:
        status = f"Dispatched {batch.dispatched_on:%d-%m-%Y} · {batch.courier} {batch.docket_no}"
    cols = [
        Column("Tag", "code"),
        Column("Item code", "code"),
        Column("Description", width=28),
        Column("Batch code", "code"),
        Column("PKD"),
        Column("Fault", width=30),
        Column("Complaint", "code"),
        Column("Company complaint no.", "code"),
        Column("Collected on", "date"),
        Column("Outcome"),
    ]
    data = [
        [
            ln.piece.tag,
            ln.piece.item.code,
            ln.piece.item.description,
            ln.piece.batch_code,
            f"{ln.piece.pkd:%m-%Y}" if ln.piece.pkd else "",
            ln.piece.fault,
            *selectors.complaint_cells(ln.piece),
            ln.piece.collected_on,
            ln.get_outcome_display(),
        ]
        for ln in lines
    ]
    note = f" · {batch.note}" if batch.note else ""
    return workbook_response(
        f"Return_Batch_{batch.number}",
        f"Return Batch {batch.number} · {batch.company.name}",
        f"{status} · {len(lines)} pieces{note}",
        _who(request),
        cols,
        data,
    )
