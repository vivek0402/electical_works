import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db


def test_global_search_items_and_entries(office_client, office_user):
    a = make_item("EIO8437", spare_type="PCB / LED module")
    post_entry(
        kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(a, loc(), 1)], user=office_user
    )
    data = office_client.get("/search/?q=ei08437").json()
    assert data["items"][0]["code"] == "EIO8437" and data["items"][0]["url"] == f"/items/{a.pk}/"
    data = office_client.get("/search/?q=in-0001").json()
    assert data["entries"][0] == {"number": "IN-0001", "url": "/entries/IN-0001/", "label": "Stock IN"}


def test_short_query_returns_nothing(office_client):
    assert office_client.get("/search/?q=e").json() == {"items": [], "entries": []}
    assert office_client.get("/search/?q=ab").json() == {"items": [], "entries": []}
    assert office_client.get("/search/?q=a%00b").json() == {"items": [], "entries": []}


def test_nul_bytes_do_not_crash(office_client):
    assert office_client.get("/search/?q=EIO%00840").status_code == 200


def test_exact_match_first_and_aliases_included(office_client):
    make_item("EIO8437")
    make_item("EIO84370")
    items = office_client.get("/search/?q=EIO8437").json()["items"]
    assert items[0]["code"] == "EIO8437" and "aliases" in items[0]


def test_search_uses_one_query_plus_prefetch(office_client):
    for n in range(5):
        make_item(f"ZZ10{n}")
    with CaptureQueriesContext(connection) as ctx:
        office_client.get("/search/?q=ZZ10")
    search_sql = [
        q["sql"] for q in ctx.captured_queries if "inventory_item" in q["sql"] or "itemalias" in q["sql"]
    ]
    assert len(search_sql) <= 3, search_sql  # items, aliases prefetch (plus session/user queries excluded)


def test_search_requires_login(client):
    assert client.get("/search/?q=abc").status_code == 302
