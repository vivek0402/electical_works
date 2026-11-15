from datetime import timedelta

import pytest
from django.utils import timezone

from apps.defectives.services import create_batch, dispatch
from apps.inventory.models import Company, EntryKind
from apps.inventory.selectors import dashboard_stats, weekly_in_out
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item, make_pieces

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def stocked(office_user):
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module")
    wire = make_item("WIRE 1.5 SQMM", unit="MTR", reorder=0, spare_type="Wire / cable")
    post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(a, loc(), 8), Line(wire, loc(), 90)],
        user=office_user,
    )
    post_entry(
        kind=EntryKind.OUT,
        entry_date=TODAY,
        lines=[Line(a, loc(), -2)],
        user=office_user,
        subtype="SITE",
        party="Dr Reddys",
    )
    return a, wire


def test_dashboard_stats(stocked):
    stats = dashboard_stats(TODAY)
    assert stats["active_items"] == 2
    assert stats["nos_in_stock"] == 6  # MTR items are not added to NOS
    assert stats["low_count"] == 1  # 6 <= reorder 10
    assert stats["movements_week"] == 3  # ledger lines, not entries


def test_weekly_in_out_counts_nos_only(stocked):
    weeks = weekly_in_out(TODAY)
    assert len(weeks) == 5
    assert weeks[-1]["qty_in"] == 8 and weeks[-1]["qty_out"] == 2


def test_dashboard_page(office_client, stocked):
    page = office_client.get("/")
    assert page.status_code == 200
    html = page.content.decode()
    for text in [
        f"{TODAY:%A}, {TODAY.day} {TODAY:%B}",  # the hero title is today's date in words
        "Stock IN",
        "Stock OUT",
        "Stock IN this week",
        "Stock OUT this week",
        "Recent entries",
        "OUT-0001",
        "Vizag Office",
    ]:
        assert text in html
    assert "apexcharts" not in html and "chart-weekly" not in html  # the charts are server-rendered bars


def test_dashboard_requires_login(client):
    assert client.get("/").status_code == 302


# --- low-stock count, weekly boundaries, undone label ---------------------------------------------

from apps.inventory.selectors import low_stock_count, low_stock_rows  # noqa: E402
from apps.inventory.services import undo_entry  # noqa: E402


def test_low_stock_count_matches_list(office_user):
    low = make_item("LOW1", reorder=5)
    fine = make_item("FINE1", reorder=5)
    make_item("NOBAL", reorder=3)  # no balance row: 0 <= 3, low
    make_item("NOREORDER", reorder=0)  # reorder 0: never low
    gone = make_item("GONE", reorder=9)
    gone.is_active = False
    gone.save()
    post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        user=office_user,
        lines=[Line(low, loc(), 5), Line(fine, loc(), 6)],
    )
    assert low_stock_count() == len(low_stock_rows()[0]) == 2


def test_weekly_in_out_excludes_undone_and_respects_boundaries(office_user):
    a = make_item("WK1")
    e_new = post_entry(
        kind=EntryKind.IN, entry_date=TODAY - timedelta(days=6), lines=[Line(a, loc(), 4)], user=office_user
    )
    post_entry(
        kind=EntryKind.IN, entry_date=TODAY - timedelta(days=7), lines=[Line(a, loc(), 3)], user=office_user
    )
    undone = post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(a, loc(), 50)], user=office_user)
    undo_entry(entry=undone, reason="mistake", user=office_user)
    weeks = weekly_in_out(TODAY)
    assert weeks[-1]["qty_in"] == 4  # day -6 is in the current window, undone 50 excluded
    assert weeks[-2]["qty_in"] == 3  # day -7 is in the previous window
    assert e_new.pk


def test_undone_badge_in_table(office_client, office_user):
    a = make_item("UND1")
    e = post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(a, loc(), 4)], user=office_user)
    undo_entry(entry=e, reason="oops", user=office_user)
    html = office_client.get("/").content.decode()
    assert "Undone" in html and 'class="undone"' in html


def test_dashboard_query_count(office_client, office_user, django_assert_max_num_queries):
    a, b = make_item("Q1"), make_item("Q2")
    for _ in range(20):
        post_entry(
            kind=EntryKind.IN,
            entry_date=TODAY,
            lines=[Line(a, loc(), 2), Line(b, loc(), 1)],
            user=office_user,
        )
    # a piece with a company, so the oldest-sent-batch line is drawn too (the worst case)
    pieces = make_pieces(make_item("QP"), 1, office_user)
    batch = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user, pieces=pieces)
    dispatch(batch=batch, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    # measured 21 (was 19 with the tiles): the stock figures; the service figures (status and piece counts are
    # shared with the menu badges); +2 the open complaints (rows and technicians) behind the age bars and the
    # "oldest" lines; +1 the answered count; +1 the oldest sent batch (only when pieces are with companies);
    # -1 the "movements today" count the old tile needed
    with django_assert_max_num_queries(21):
        assert office_client.get("/").status_code == 200


def test_dashboard_stock_card_shows_this_and_last_week_and_each_bar_is_readable(office_client, office_user):
    a = make_item("WKCARD")
    for days, qty in ((0, 8), (3, 4), (8, 5)):
        post_entry(
            kind=EntryKind.IN,
            entry_date=TODAY - timedelta(days=days),
            lines=[Line(a, loc(), qty)],
            user=office_user,
        )
    html = office_client.get("/").content.decode()
    assert '<div class="fig">12 <small>NOS</small></div>' in html  # this week: 8 + 4
    assert "5 the week before" in html
    # five bars per strip, each with its week and quantity as text for screen readers
    assert html.count('title="') >= 10 and "Stock IN in NOS, last five weeks:" in html


def test_dashboard_links_to_lists_and_locations(office_client, stocked):
    html = office_client.get("/").content.decode()
    week = f"date_from={TODAY - timedelta(days=6):%Y-%m-%d}&amp;date_to={TODAY:%Y-%m-%d}"
    for url in ["/stock/", f"/movements/?{week}", f"/movements/?kind=IN&amp;{week}", "/low-stock/"]:
        assert f'href="{url}"' in html
    assert f'href="/stock/?location={loc().pk}"' in html
