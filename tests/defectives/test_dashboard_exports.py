import io
from datetime import timedelta

import openpyxl
import pytest
from django.utils import timezone

from apps.defectives import selectors
from apps.defectives.filters import piece_filters
from apps.defectives.models import BatchLine, Outcome, ReturnBatch
from apps.defectives.services import create_batch, dispatch, settle
from apps.inventory.models import Company
from tests.factories import loc, make_item, make_pieces

pytestmark = pytest.mark.django_db


def today():
    return timezone.localdate()


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
    dispatch(batch=b, dispatched_on=today(), courier="DTDC", docket_no="D1", user=office_user)
    settle(
        batch=b,
        pieces=w[:1],
        outcome=Outcome.REPLACED,
        settled_on=today(),
        to_location=loc(),
        user=office_user,
    )
    create_batch(company=wipro(), user=office_user, pieces=w[2:3])
    return w


def test_dashboard_numbers(office_client, story):
    d = selectors.dashboard(today())
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
    dispatch(batch=b1, dispatched_on=today(), courier="DTDC", docket_no="D1", user=office_user)
    settle(batch=b1, pieces=[p], outcome=Outcome.REJECTED_RETURNED, settled_on=today(), user=office_user)
    p.refresh_from_db()
    b2 = create_batch(company=wipro(), user=office_user, pieces=[p])
    dispatch(batch=b2, dispatched_on=today(), courier="DTDC", docket_no="D2", user=office_user)
    settle(
        batch=b2,
        pieces=[p],
        outcome=Outcome.REPLACED,
        settled_on=today(),
        to_location=loc(),
        user=office_user,
    )
    d = selectors.dashboard(today())
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


def test_outcome_links_match_their_counts(office_client, office_user):
    """Rejected (returned) = 1 on the dashboard links to a list of exactly that one piece."""
    (p,) = make_pieces(make_item("DRV-9"), 1, office_user)
    b1 = create_batch(company=wipro(), user=office_user, pieces=[p])
    dispatch(batch=b1, dispatched_on=today(), courier="DTDC", docket_no="D1", user=office_user)
    settle(batch=b1, pieces=[p], outcome=Outcome.REJECTED_RETURNED, settled_on=today(), user=office_user)
    p.refresh_from_db()
    b2 = create_batch(company=wipro(), user=office_user, pieces=[p])
    dispatch(batch=b2, dispatched_on=today(), courier="DTDC", docket_no="D2", user=office_user)
    settle(
        batch=b2,
        pieces=[p],
        outcome=Outcome.REPLACED,
        settled_on=today(),
        to_location=loc(),
        user=office_user,
    )
    html = office_client.get("/defectives/").content.decode()
    since = f"{today() - timedelta(days=90):%Y-%m-%d}"
    link = f"/defectives/pieces/?answered=REJECTED_RETURNED&amp;since={since}"
    assert link in html
    page = office_client.get(f"/defectives/pieces/?answered=REJECTED_RETURNED&since={since}").content.decode()
    assert page.count("DEF-0001") >= 1
    f = piece_filters({"answered": "REJECTED_RETURNED", "since": since})
    assert [x.tag for x in selectors.piece_rows(f)] == ["DEF-0001"]
    # the piece's own (latest) outcome is Replaced, so the old outcome filter would find nothing
    assert selectors.piece_rows(piece_filters({"outcome": "REJECTED_RETURNED"})) == []


def _answer(user, settled_on, code):
    (p,) = make_pieces(make_item(code), 1, user)
    b = create_batch(company=wipro(), user=user, pieces=[p])
    dispatch(batch=b, dispatched_on=today(), courier="DTDC", docket_no="D", user=user)
    settle(batch=b, pieces=[p], outcome=Outcome.REPAIRED, settled_on=today(), to_location=loc(), user=user)
    BatchLine.objects.filter(batch=b).update(settled_on=settled_on)  # back-date the answer


def test_ninety_day_window_boundary(office_user):
    _answer(office_user, today() - timedelta(days=90), "OLD-1")  # exactly 90 days ago: outside
    _answer(office_user, today() - timedelta(days=89), "NEW-1")  # inside
    assert selectors.dashboard(today())["answered"] == 1


def test_waiting_uses_oldest_batch_still_out(office_user):
    w = make_pieces(make_item("LG78-150-700"), 3, office_user)
    old = create_batch(company=wipro(), user=office_user, pieces=w[:2])
    dispatch(batch=old, dispatched_on=today(), courier="A", docket_no="1", user=office_user)
    ReturnBatch.objects.filter(pk=old.pk).update(dispatched_on=today() - timedelta(days=40))
    newer = create_batch(company=wipro(), user=office_user, pieces=w[2:])
    dispatch(batch=newer, dispatched_on=today(), courier="A", docket_no="2", user=office_user)
    ReturnBatch.objects.filter(pk=newer.pk).update(dispatched_on=today() - timedelta(days=5))
    # the older batch is partly settled: one piece still out, so it still counts
    settle(
        batch=old,
        pieces=w[:1],
        outcome=Outcome.REPAIRED,
        settled_on=today(),
        to_location=loc(),
        user=office_user,
    )
    [row] = selectors.dashboard(today())["sent_rows"]
    assert (row["n"], row["waiting"], row["oldest"].number) == (2, 40, old.number)
    assert [b.number for b in row["batches"]] == [old.number, newer.number]
    # once the older batch is fully answered, the newer one sets the wait
    settle(
        batch=old,
        pieces=w[1:2],
        outcome=Outcome.REPAIRED,
        settled_on=today(),
        to_location=loc(),
        user=office_user,
    )
    [row] = selectors.dashboard(today())["sent_rows"]
    assert (row["waiting"], row["oldest"].number) == (5, newer.number)


def test_piece_counts_is_shared(story):
    assert selectors.piece_counts() == {"in_store": 2, "in_batch": 1, "sent": 1}


def test_empty_dashboard_renders(office_client):
    html = office_client.get("/defectives/").content.decode()
    assert "No answers in the last 90 days" in html and "def-chart-toggle" not in html
    assert "The Defective store is empty." in html and "Nothing is waiting on a company." in html


def test_chart_has_counts_in_its_label_and_a_fixed_toggle(office_client, story):
    html = office_client.get("/defectives/").content.decode()
    assert "Replaced 1, Repaired 0, Rejected (returned) 0, Rejected (scrapped) 0" in html
    assert "Table view" in html and "View as table" not in html


def test_store_row_link_has_no_status_filter(office_client, story):
    html = office_client.get("/defectives/").content.decode()
    assert "?company=" in html and "&amp;status=IN_STORE" not in html


def test_draft_dispatch_list_status_line(office_client, story):
    ws = sheet(office_client.get("/defectives/batches/RB-0002/export/"))
    assert ws["A3"].value == "Status: Draft (not dispatched yet) · 1 piece"
    ws = sheet(office_client.get("/defectives/batches/RB-0001/export/"))
    assert ws["A3"].value.startswith("Status: Dispatched") and ws["A3"].value.endswith("· 2 pieces")


def test_sheet_name_never_ends_in_an_apostrophe(office_client, office_user):
    from apps.core.excel import Column, workbook_response

    name = "Return Batch RB-0001 " + "x" * 9 + "'" + "y" * 5  # the 31st character is an apostrophe
    assert name[:31].endswith("'")
    ws = openpyxl.load_workbook(
        io.BytesIO(workbook_response("f", name, "all", "me", [Column("A")], [["1"]]).content)
    ).active
    assert not ws.title.endswith("'")


def test_query_counts_are_bounded(office_client, story, django_assert_max_num_queries):
    with django_assert_max_num_queries(13):
        assert office_client.get("/defectives/").status_code == 200
    with django_assert_max_num_queries(6):
        assert office_client.get("/defectives/export/").status_code == 200
    with django_assert_max_num_queries(7):
        assert office_client.get("/defectives/batches/RB-0001/export/").status_code == 200
