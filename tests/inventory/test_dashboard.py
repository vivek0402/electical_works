import pytest
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.selectors import dashboard_stats, weekly_in_out
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

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
    assert stats["entries_week"] == 2 and stats["entries_today"] == 2


def test_weekly_in_out_counts_nos_only(stocked):
    weeks = weekly_in_out(TODAY)
    assert len(weeks) == 5
    assert weeks[-1]["qty_in"] == 8 and weeks[-1]["qty_out"] == 2


def test_dashboard_page(office_client, stocked):
    page = office_client.get("/")
    assert page.status_code == 200
    html = page.content.decode()
    for text in [
        "Stock dashboard",
        "Stock IN",
        "Stock OUT",
        "Recent entries",
        "OUT-0001",
        "Vizag Office",
        "chart-weekly",
    ]:
        assert text in html


def test_dashboard_requires_login(client):
    assert client.get("/").status_code == 302
