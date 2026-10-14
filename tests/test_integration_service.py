"""Stock, complaints and defectives linked: menu badges, search, dashboard, movements, entry pages."""

import io
import re
from datetime import timedelta

import openpyxl
import pytest
from django.http import QueryDict
from django.utils import timezone

from apps.complaints.filters import complaint_filters
from apps.complaints.models import Status
from apps.complaints.selectors import complaint_rows
from apps.complaints.services import record_visit
from apps.defectives.filters import piece_filters
from apps.defectives.selectors import piece_rows
from apps.defectives.services import create_batch, dispatch
from apps.inventory.models import Company
from tests.factories import give_stock, loc, make_complaint, make_item, make_pieces, make_site, make_tech

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def visited(office_user):
    """IN-0001 stock; CMP-0001 at Laurus Labs Unit-2 (WL/AP/24871); a visit giving 1 part (OUT-0001) and
    collecting 2 failed pieces DEF-0001/0002 (IN-0002, batch code B2405)."""
    item = make_item("LG78-150-700")
    give_stock(item, 5, office_user)
    c = make_complaint(
        office_user, company_ref="WL/AP/24871", site=make_site("Laurus Labs Unit-2", "Visakhapatnam")
    )
    record_visit(
        complaint=c,
        visit_date=TODAY,
        technicians=[make_tech()],
        work_done="Changed 1 driver",
        next_status=Status.MATERIAL_CHECK,
        user=office_user,
        location=loc(),
        parts=[(item, 1)],
        collected=[(item, 2, "B2405", None, "no output")],
    )
    return c


# ---------------------------------------------------------------- global search


def test_global_search_finds_complaints_refs_sites_and_tags(office_client, visited):
    found = office_client.get("/search/?q=cmp-0001").json()["complaints"]
    assert found[0]["number"] == "CMP-0001" and found[0]["url"] == "/complaints/CMP-0001/"
    assert found[0]["ref"] == "WL/AP/24871" and found[0]["status"] == "Material need to check"
    assert office_client.get("/search/?q=24871").json()["complaints"][0]["number"] == "CMP-0001"
    sites = office_client.get("/search/?q=laurus").json()["sites"]
    assert sites[0]["name"] == "Laurus Labs Unit-2" and sites[0]["url"] == f"/sites/{visited.site_id}/"
    pieces = office_client.get("/search/?q=def-1").json()["pieces"]
    assert pieces[0] == {
        "tag": "DEF-0001",
        "url": "/defectives/pieces/DEF-0001/",
        "label": "LG78-150-700 · Wipro Lighting",
        "status": "In store",
    }
    assert office_client.get("/search/?q=b2405").json()["pieces"][0]["tag"] in {"DEF-0001", "DEF-0002"}


def test_global_search_still_finds_items_and_entries(office_client, visited):
    d = office_client.get("/search/?q=lg78").json()
    assert d["items"][0]["code"] == "LG78-150-700" and d["items"][0]["url"].startswith("/items/")
    assert office_client.get("/search/?q=out-0001").json()["entries"][0]["url"] == "/entries/OUT-0001/"


def test_global_search_groups_stay_small(office_client, office_user):
    item = make_item("ZZ1")
    make_pieces(item, 12, office_user)
    site = make_site("Zeta Works", "Vizag")
    for n in range(7):
        make_complaint(office_user, site=make_site(f"Zeta Works {n}", "Vizag") if n else site)
    d = office_client.get("/search/?q=zeta").json()
    assert len(d["complaints"]) <= 5 and len(d["sites"]) <= 4
    assert len(office_client.get("/search/?q=def-").json()["pieces"]) <= 5


# ---------------------------------------------------------------- menu


def test_menu_badges_and_brand(office_client, visited):
    html = office_client.get("/").content.decode()
    assert 'title="Open complaints">1</span>' in html
    assert 'title="Pieces in the Defective store">2</span>' in html
    assert '<span class="brand-sub">Service</span>' in html
    # each badge sits on a menu link whose list shows exactly that many rows
    assert 'href="/complaints/list/"' in html and 'href="/defectives/pieces/?status=IN_STORE"' in html


def test_menu_badges_hidden_when_zero(office_client):
    html = office_client.get("/").content.decode()
    assert 'title="Open complaints"' not in html and 'title="Pieces in the Defective store"' not in html


# ---------------------------------------------------------------- main dashboard


def _tile(html, label):
    """(count, href) of the dashboard tile with this label."""
    m = re.search(
        r'<a href="([^"]+)" class="card card-sm card-link[^>]*>(?:(?!</a>).)*?'
        r'<div class="fw-medium fs-3">(\d+)</div><div class="text-secondary">' + re.escape(label),
        html,
        re.S,
    )
    assert m, label
    return int(m.group(2)), m.group(1).replace("&amp;", "&")


def test_dashboard_shows_service_figures_and_each_link_lists_that_many(office_client, office_user, visited):
    # a second complaint (not attended), a piece sent to a company, and an old visit outside the 7-day window
    make_complaint(office_user, site=make_site("BARC"))
    pieces = make_pieces(make_item("X1"), 1, office_user)
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user, pieces=pieces)
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    html = office_client.get("/").content.decode()

    n, href = _tile(html, "Open complaints")
    assert n == 2 and "1 not attended yet" in html
    path, _, query = href.partition("?")
    assert path == "/complaints/list/"
    rows, _ = complaint_rows(complaint_filters(QueryDict(query)), TODAY)
    assert len(rows) == n

    for label, expected in (("Defective pieces in store", 2), ("Pieces with companies", 1)):
        n, href = _tile(html, label)
        path, _, query = href.partition("?")
        assert path == "/defectives/pieces/" and n == expected
        assert len(piece_rows(piece_filters(QueryDict(query)))) == n

    n, href = _tile(html, "Complaints visited")
    path, _, query = href.partition("?")
    assert path == "/complaints/list/" and n == 1 and "1 visit recorded" in html
    rows, _ = complaint_rows(complaint_filters(QueryDict(query)), TODAY)
    assert [r["c"].number for r in rows] == ["CMP-0001"]


def test_visited_since_filter_uses_the_window(office_client, office_user, visited):
    since = TODAY - timedelta(days=7)
    html = office_client.get(f"/complaints/list/?tab=all&visited_since={since:%Y-%m-%d}").content.decode()
    assert 'href="/complaints/CMP-0001/"' in html and "Visited after" in html
    later = office_client.get(f"/complaints/list/?tab=all&visited_since={TODAY:%Y-%m-%d}").content.decode()
    assert 'href="/complaints/CMP-0001/"' not in later  # __gt: a visit today is not after today


# ---------------------------------------------------------------- movements and entry pages


def test_movements_label_and_link_service_entries(office_client, visited):
    html = office_client.get("/movements/").content.decode()
    assert "Parts given at complaint visit" in html and "Failed parts collected at site" in html
    assert 'href="/complaints/CMP-0001/"' in html
    html = office_client.get("/movements/?q=cmp-0001").content.decode()
    assert 'href="/entries/OUT-0001/"' in html and 'href="/entries/IN-0001/"' not in html


def test_store_location_is_marked_in_movements(office_client, visited):
    html = office_client.get("/movements/").content.decode()
    assert '<i class="ti ti-recycle" aria-hidden="true"></i> Defective store' in html


def test_movements_link_return_batches(office_client, office_user):
    pieces = make_pieces(make_item("X1"), 1, office_user)
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user, pieces=pieces)
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    html = office_client.get("/movements/").content.decode()
    assert "Defectives returned to company" in html and f'href="/defectives/batches/{b.number}/"' in html
    assert 'href="/entries/' in office_client.get(f"/movements/?q={b.number.lower()}").content.decode()


def test_entry_pages_link_back_and_list_pieces(office_client, office_user, visited):
    html = office_client.get("/entries/IN-0002/").content.decode()
    assert 'href="/complaints/CMP-0001/"' in html and 'href="/defectives/pieces/DEF-0002/"' in html
    assert "Undo this entry" not in html
    out = office_client.get("/entries/OUT-0001/").content.decode()
    # the parts given are undone from the complaint page (undo_visit_parts), never from the entry page
    assert "Undo this entry" not in out and "Correct it from the complaint" in out
    assert "Complaint CMP-0001" in out
    pieces = make_pieces(make_item("X1"), 1, office_user)
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user, pieces=pieces)
    entry = dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    html = office_client.get(f"/entries/{entry.number}/").content.decode()
    assert f'href="/defectives/batches/{b.number}/"' in html and "Docket / ref no." in html
    assert f'href="/defectives/pieces/{pieces[0].tag}/"' in html


def test_movements_export_has_complaint_and_batch_columns(office_client, visited):
    response = office_client.get("/movements/export/")
    ws = openpyxl.load_workbook(io.BytesIO(response.content)).active
    headers = [c.value for c in ws[6]]
    assert headers[-2:] == ["Complaint", "Return batch"]
    complaint_of = {ws.cell(r, 2).value: ws.cell(r, len(headers) - 1).value for r in range(7, ws.max_row + 1)}
    assert complaint_of["OUT-0001"] == "CMP-0001" and complaint_of["IN-0001"] in (None, "")
