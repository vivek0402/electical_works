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
from apps.inventory.filters import movement_filters
from apps.inventory.models import Company, EntryKind
from apps.inventory.selectors import movement_rows
from apps.inventory.services import Line, post_entry
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
    assert 'title="Open complaints">1<span class="visually-hidden"> open</span></span>' in html
    assert (
        'title="Pieces in store, not yet in a batch">2'
        '<span class="visually-hidden"> in store, not yet in a batch</span></span>' in html
    )
    assert '<span class="brand-sub">Service</span>' in html
    # each badge sits on a menu link whose list shows exactly that many rows
    assert 'href="/complaints/list/"' in html and 'href="/defectives/pieces/?status=IN_STORE"' in html


def test_menu_badges_hidden_when_zero(office_client):
    html = office_client.get("/").content.decode()
    assert 'title="Open complaints"' not in html and 'title="Pieces in store, not yet in a batch"' not in html


# ---------------------------------------------------------------- main dashboard


def _blocks(html):
    """{title: (count, href)} for the dashboard's "needs attention" blocks."""
    found = re.findall(
        r'<a class="b-block attn[^"]*" href="([^"]+)" data-count="(\d+)">.*?<b>([^<]+)</b>', html, re.S
    )
    return {title: (int(n), href.replace("&amp;", "&")) for href, n, title in found}


def _flow(html, label):
    """(count, href) of the Defective pieces card's step with this label."""
    m = re.search(r'<a href="([^"]+)"[^>]*><b>(\d+)</b>' + re.escape(label), html)
    assert m, label
    return int(m.group(2)), m.group(1).replace("&amp;", "&")


def _link(html, text):
    """href of the link whose text starts with `text`."""
    m = re.search(r'<a href="([^"]+)">' + re.escape(text), html)
    assert m, text
    return m.group(1).replace("&amp;", "&")


def test_dashboard_shows_service_figures_and_each_link_lists_that_many(office_client, office_user, visited):
    # a complaint not attended yet, and a piece sent to a company
    make_complaint(office_user, site=make_site("BARC"))
    pieces = make_pieces(make_item("X1"), 1, office_user)
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user, pieces=pieces)
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    # CMP-0001 visited again today: still one complaint, two visits
    record_visit(
        complaint=visited,
        visit_date=TODAY,
        technicians=[make_tech()],
        work_done="Checked again",
        next_status=Status.ATTENDED,
        user=office_user,
    )
    # a visit exactly 7 days ago is on the window's edge and is left out (visit_date > today - 7)
    old = make_complaint(office_user, site=make_site("Old Site"), reported_on=TODAY - timedelta(days=10))
    record_visit(
        complaint=old,
        visit_date=TODAY - timedelta(days=7),
        technicians=[make_tech()],
        work_done="Looked at it",
        next_status=Status.ATTENDED,
        user=office_user,
    )
    html = office_client.get("/").content.decode()

    # the open count is the row count of the list its figure links to
    n = int(re.search(r'<a class="fig" href="/complaints/list/">(\d+)</a>', html).group(1))
    assert n == 3 and "1 not attended" in html
    rows, _ = complaint_rows(complaint_filters(QueryDict("")), TODAY)
    assert len(rows) == n

    # the attention blocks: not attended and pieces with companies, each the row count of its list
    blocks = _blocks(html)
    count, href = blocks["Complaints nobody has attended"]
    assert count == 1 and "Oldest: BARC" in html
    rows, _ = complaint_rows(complaint_filters(QueryDict(href.partition("?")[2])), TODAY)
    assert len(rows) == count
    count, href = blocks["Defective pieces waiting on a company"]
    path, _, query = href.partition("?")
    assert path == "/defectives/pieces/" and count == 1
    assert len(piece_rows(piece_filters(QueryDict(query)))) == count

    for label, expected in (("in store<span", 2), ("with companies", 1)):
        n, href = _flow(html, label)
        path, _, query = href.partition("?")
        assert path == "/defectives/pieces/" and n == expected
        assert len(piece_rows(piece_filters(QueryDict(query)))) == n

    href = _link(html, "1 visited in the last 7 days")
    path, _, query = href.partition("?")
    assert path == "/complaints/list/" and "(2 visits)" in html
    rows, _ = complaint_rows(complaint_filters(QueryDict(query)), TODAY)
    assert [r["c"].number for r in rows] == ["CMP-0001"]
    listed = office_client.get(href).content.decode()
    assert listed.count('<a class="code" href="/complaints/CMP-') == 1


def test_dashboard_late_complaints_block_lists_what_it_counts(office_client, office_user):
    make_complaint(office_user, site=make_site("Fresh Site"), reported_on=TODAY - timedelta(days=15))
    make_complaint(office_user, site=make_site("Late Site"), reported_on=TODAY - timedelta(days=16))
    make_complaint(office_user, site=make_site("Later Site"), reported_on=TODAY - timedelta(days=40))
    html = office_client.get("/").content.decode()
    count, href = _blocks(html)["Complaints open for more than 15 days"]
    assert count == 2 and "Oldest: Later Site, 40 days" in html  # day 15 is not late, day 16 is
    rows, _ = complaint_rows(complaint_filters(QueryDict(href.partition("?")[2])), TODAY)
    assert sorted(r["age"] for r in rows) == [16, 40]
    listed = office_client.get(href).content.decode()
    assert listed.count('<a class="code" href="/complaints/CMP-') == count


def test_dashboard_low_stock_block_lists_what_it_counts(office_client, office_user):
    low = make_item("LOWDASH", reorder=5)
    post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(low, loc(), 2)], user=office_user)
    html = office_client.get("/").content.decode()
    count, href = _blocks(html)["Items low on stock"]
    assert count == 1 and href == "/low-stock/"
    assert office_client.get(href).content.decode().count('<a class="code" href="/items/') == count


def test_dashboard_has_no_attention_blocks_when_nothing_needs_it(office_client):
    html = office_client.get("/").content.decode()
    assert 'class="b-block attn' not in html and "Nothing needs attention today." in html


def test_dashboard_counts_the_things_that_need_attention(office_client, office_user):
    make_complaint(office_user, site=make_site("BARC"), reported_on=TODAY - timedelta(days=20))
    html = office_client.get("/").content.decode()
    assert len(_blocks(html)) == 2 and "2 things need attention today." in html  # not attended and late


def test_movements_caption_counts_the_lines_its_list_shows(office_client, office_user, visited):
    # visited: IN-0001 (1 line), OUT-0001 (1 line), IN-0002 (1 line), all today; plus a 2-line IN 6 days ago
    # (inside the window) and one 7 days ago (outside it, though the Movements default range would list it)
    a, b = make_item("W1"), make_item("W2")
    for days in (6, 7):
        post_entry(
            kind=EntryKind.IN,
            entry_date=TODAY - timedelta(days=days),
            lines=[Line(a, loc(), 1), Line(b, loc(), 1)],
            user=office_user,
        )
    html = office_client.get("/").content.decode()
    m = re.search(r'<a href="(/movements/\?[^"]+)">(\d+) movements in the last 7 days</a>', html)
    assert m
    n, href = int(m.group(2)), m.group(1).replace("&amp;", "&")
    assert n == 5
    path, _, query = href.partition("?")
    assert len(movement_rows(movement_filters(QueryDict(query), TODAY))) == n
    listed = office_client.get(href).content.decode()
    assert listed.count('<a class="code" href="/entries/') == n


def test_global_search_lists_active_sites_first_and_marks_hidden_ones(office_client):
    make_site("Zeta Alpha", "Vizag", is_active=False)
    make_site("Zeta Beta", "Vizag")
    sites = office_client.get("/search/?q=zeta").json()["sites"]
    assert [(s["name"], s["label"]) for s in sites] == [
        ("Zeta Beta", "Vizag"),
        ("Zeta Alpha", "Vizag (hidden)"),
    ]


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
