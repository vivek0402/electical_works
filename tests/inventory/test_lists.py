import datetime

import pytest
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.services import Line, post_entry, undo_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def stock(office_user):
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module")
    b = make_item("LG78-150-700", reorder=2)
    c = make_item("LENS", reorder=0, spare_type="Lens")
    post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY - datetime.timedelta(days=40),
        user=office_user,
        lines=[Line(a, loc(), 8), Line(b, loc(), 20), Line(c, loc("Svkml"), 5)],
    )
    out = post_entry(
        kind=EntryKind.OUT,
        entry_date=TODAY,
        user=office_user,
        subtype="SITE",
        party="Dr Reddys",
        lines=[Line(b, loc(), -3)],
    )
    undo_entry(entry=out, reason="wrong job", user=office_user)
    return a, b, c


def test_current_stock_all_locations(office_client, stock):
    html = office_client.get("/stock/").content.decode()
    for text in ["EIO6006", "LG78-150-700", "LENS", "Vizag Office", "Svkml", "Showing 1–3 of 3"]:
        assert text in html


def test_current_stock_filters(office_client, stock):
    svkml = loc("Svkml").pk
    html = office_client.get(f"/stock/?location={svkml}").content.decode()
    assert "LENS" in html and "EIO6006" not in html
    html = office_client.get("/stock/?low=1").content.decode()
    assert "EIO6006" in html and "LG78-150-700" not in html
    html = office_client.get("/stock/?q=ei06006").content.decode()  # look-alike spelling
    assert "EIO6006" in html and "LENS" not in html


def test_current_stock_sort_by_total_desc(office_client, stock):
    html = office_client.get("/stock/?sort=total&dir=desc").content.decode()
    assert html.index("LG78-150-700") < html.index("EIO6006") < html.index("LENS")


def test_movements_default_last_30_days_and_undone(office_client, stock):
    html = office_client.get("/movements/").content.decode()
    assert "OUT-0001" in html and "REV-0001" in html and "IN-0001" not in html  # IN was 40 days ago
    assert 'class="undone"' in html
    old = (TODAY - datetime.timedelta(days=60)).isoformat()
    assert "IN-0001" in office_client.get(f"/movements/?date_from={old}").content.decode()


def test_movements_filter_kind(office_client, stock):
    html = office_client.get("/movements/?kind=REV").content.decode()
    assert "REV-0001" in html and "OUT-0001" not in html


def test_low_stock(office_client, stock):
    html = office_client.get("/low-stock/").content.decode()
    assert "EIO6006" in html and "LG78-150-700" not in html and "Short by" in html
    a = stock[0]
    assert "<th>Unit</th>" in html
    assert f'href="/stock/in/?item={a.pk}" class="btn btn-sm btn-in"' in html


def test_movements_search_finds_other_spellings_and_descriptions(office_client, office_user):
    from apps.inventory.models import ItemAlias

    item = make_item("EIO8437", spare_type="PCB / LED module")
    item.description = "Round LED module"
    item.save()
    ItemAlias.objects.create(item=item, alias="EI08437", search_key="E108437")
    post_entry(kind=EntryKind.IN, entry_date=TODAY, user=office_user, lines=[Line(item, loc(), 3)])
    for q in ["EI08437", "round led", "EIO-8437"]:
        assert "IN-0001" in office_client.get(f"/movements/?q={q}").content.decode(), q
    assert "IN-0001" not in office_client.get("/movements/?q=nothing-like-it").content.decode()


@pytest.mark.parametrize("url", ["/stock/?q=ab%00", "/movements/?q=%00", "/stock/?q=%00%00x"])
def test_nul_in_search_is_safe(office_client, stock, url):
    assert office_client.get(url).status_code == 200


def _query_count(client, url):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        assert client.get(url).status_code == 200
    return len(ctx)


@pytest.mark.parametrize("url", ["/stock/", "/low-stock/", "/stock/?size=50"])
def test_list_queries_do_not_grow_with_items(office_client, office_user, url):
    def add(n, start):
        for i in range(start, start + n):
            it = make_item(f"BULK{i:03d}", reorder=100, spare_type="Lens")
            post_entry(kind=EntryKind.IN, entry_date=TODAY, user=office_user, lines=[Line(it, loc(), 5)])

    add(5, 0)
    few = _query_count(office_client, url)
    add(25, 5)
    assert _query_count(office_client, url) <= few


def test_inactive_location_with_stock_gets_a_column(office_client, office_user):
    item = make_item("OLDLOC", reorder=0)
    gone = loc("Svkml")
    post_entry(kind=EntryKind.IN, entry_date=TODAY, user=office_user, lines=[Line(item, gone, 7)])
    gone.is_active = False
    gone.save()
    html = office_client.get("/stock/").content.decode()
    assert "Svkml" in html and "OLDLOC" in html
    assert "<b>7</b>" in html


def test_inactive_empty_location_has_no_column(office_client, office_user):
    gone = loc("Svkml")
    gone.is_active = False
    gone.save()
    item = make_item("ONLYMAIN")
    post_entry(kind=EntryKind.IN, entry_date=TODAY, user=office_user, lines=[Line(item, loc(), 2)])
    assert "Svkml" not in office_client.get("/stock/").content.decode()


def test_movements_reversed_dates_are_swapped(office_client, stock):
    a = TODAY.isoformat()
    b = (TODAY - datetime.timedelta(days=60)).isoformat()
    assert "IN-0001" in office_client.get(f"/movements/?date_from={a}&date_to={b}").content.decode()
