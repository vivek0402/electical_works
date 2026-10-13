import io

import openpyxl
import pytest
from django.utils import timezone

from apps.defectives import selectors
from apps.defectives.models import Outcome
from apps.defectives.services import create_batch, dispatch, settle
from apps.inventory.models import Company
from tests.factories import loc, make_item, make_pieces

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def sheet(response):
    assert response.status_code == 200
    return openpyxl.load_workbook(io.BytesIO(response.content)).active


def wipro():
    return Company.objects.get(name="Wipro Lighting")


@pytest.fixture
def story(office_user):
    """Wipro DEF-0001..4, Havells DEF-0005. RB-0001 sent with 1+2, 1 replaced. RB-0002 draft with 3."""
    w = make_pieces(make_item("LG78-150-700", description="LED driver 150W"), 4, office_user)
    make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user)
    b = create_batch(company=wipro(), user=office_user, pieces=w[:2])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(
        batch=b, pieces=w[:1], outcome=Outcome.REPLACED, settled_on=TODAY, to_location=loc(), user=office_user
    )
    create_batch(company=wipro(), user=office_user, pieces=w[2:3])
    return w


def test_dashboard_numbers(office_client, story):
    d = selectors.dashboard(TODAY)
    assert (d["in_store"], d["in_batch"], d["sent"], d["drafts"], d["answered"]) == (2, 1, 1, 1, 1)
    assert [(r["company__name"], r["store"], r["batch"]) for r in d["store_rows"]] == [
        ("Havells", 1, 0),
        ("Wipro Lighting", 1, 1),
    ]
    [row] = d["sent_rows"]
    assert (row["company__name"], row["n"], row["waiting"], row["oldest"].number) == (
        "Wipro Lighting",
        1,
        0,
        "RB-0001",
    )
    assert {value: n for value, _, n in d["outcomes"]}["REPLACED"] == 1
    assert [r["piece"].tag for r in d["oldest"]] == ["DEF-0004", "DEF-0005"]
    html = office_client.get("/defectives/").content.decode()
    assert (
        "Pieces in store" in html and "Sent, awaiting settlement" in html and "Outcomes, last 90 days" in html
    )


def test_defective_list_export_groups_by_company(office_client, story):
    ws = sheet(office_client.get("/defectives/export/"))
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=7)]
    assert [(r[0], r[1], r[5], r[6], r[7]) for r in rows] == [
        ("Havells", "MCB 16A SP", 1, 0, "DEF-0005"),
        ("Wipro Lighting", "LG78-150-700", 2, 1, "DEF-0003, DEF-0004"),
    ]


def test_dispatch_list_export(office_client, story):
    ws = sheet(office_client.get("/defectives/batches/RB-0001/export/"))
    assert "Return Batch RB-0001 · Wipro Lighting" in ws["A2"].value and "DTDC D1" in ws["A3"].value
    assert [ws.cell(r, 1).value for r in (7, 8)] == ["DEF-0001", "DEF-0002"]
    assert ws.cell(7, 7).value == "Found in stock" and ws.cell(7, 10).value == "Replaced"


def test_export_buttons(office_client, story):
    assert 'href="/defectives/export/' in office_client.get("/defectives/pieces/").content.decode()
    assert (
        'href="/defectives/batches/RB-0001/export/"'
        in office_client.get("/defectives/batches/RB-0001/").content.decode()
    )


def test_nav_links_the_dashboard(office_client):
    assert 'href="/defectives/"' in office_client.get("/").content.decode()


def test_outcomes_count_batch_lines_so_a_replaced_rejection_counts_twice(office_user):
    """A piece rejected, sent back, re-batched and replaced has two answers; both count."""
    (p,) = make_pieces(make_item("DRV-9"), 1, office_user)
    b1 = create_batch(company=wipro(), user=office_user, pieces=[p])
    dispatch(batch=b1, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(batch=b1, pieces=[p], outcome=Outcome.REJECTED_RETURNED, settled_on=TODAY, user=office_user)
    p.refresh_from_db()
    b2 = create_batch(company=wipro(), user=office_user, pieces=[p])
    dispatch(batch=b2, dispatched_on=TODAY, courier="DTDC", docket_no="D2", user=office_user)
    settle(
        batch=b2, pieces=[p], outcome=Outcome.REPLACED, settled_on=TODAY, to_location=loc(), user=office_user
    )
    d = selectors.dashboard(TODAY)
    counts = {value: n for value, _, n in d["outcomes"]}
    assert counts["REJECTED_RETURNED"] == 1 and counts["REPLACED"] == 1 and d["answered"] == 2


def test_exports_are_plain_text_and_frozen(office_client, office_user):
    make_pieces(make_item("=CMD-1", description="=1+1"), 1, office_user)
    ws = sheet(office_client.get("/defectives/export/"))
    assert ws.freeze_panes == "B7"
    assert ws["C7"].value == "=1+1" and ws["C7"].data_type == "s"
    assert ws["A2"].value == "Defective List"


def test_dispatch_list_unknown_batch_is_404(office_client):
    assert office_client.get("/defectives/batches/RB-9999/export/").status_code == 404
