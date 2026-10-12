import pytest
from django.urls import get_resolver

pytestmark = pytest.mark.django_db
PUBLIC = {"login", "logout", "healthz"}
ADMIN_ONLY = {"masters", "masters_toggle"}
EXPECTED_STOCK_ROUTES = {
    "dashboard", "current_stock", "low_stock", "movements", "items", "item_new", "item_detail", "item_edit",
    "stock_in", "stock_out", "transfer", "adjust", "entry_detail", "entry_undo", "item_quick_create",
    "item_check_code", "global_search", "masters", "masters_toggle", "items_xlsx", "current_stock_xlsx",
}  # fmt: skip


def named_routes():
    for name, patterns in get_resolver().reverse_dict.items():
        if isinstance(name, str) and not name.startswith("admin") and name not in PUBLIC:
            result, params = patterns[0][
                0
            ]  # (possibilities, pattern, defaults, converters)[0] -> first possibility
            yield name, result % {k: 1 for k in params}


def test_sweep_finds_the_routes():
    names = {n for n, _ in named_routes()}
    assert names >= EXPECTED_STOCK_ROUTES


@pytest.mark.parametrize("name,path", sorted(named_routes()))
def test_anonymous_is_sent_to_login(client, name, path):
    r = client.get("/" + path)
    assert r.status_code == 302 and r.url.startswith("/login/"), name


@pytest.mark.parametrize("name,path", sorted(n for n in named_routes() if n[0] in ADMIN_ONLY))
def test_office_blocked_from_admin_pages(office_client, name, path):
    assert office_client.get("/" + path).status_code == 403


@pytest.mark.parametrize("name,path", sorted(n for n in named_routes() if n[0] not in ADMIN_ONLY))
def test_office_is_never_forbidden_on_stock_pages(office_client, name, path):
    # 404 (placeholder ids) and 405 (POST-only views) are fine; 403 would mean a stock page is locked
    assert office_client.get("/" + path).status_code != 403, name


def test_office_cannot_post_to_masters(office_client):
    assert office_client.post("/masters/", {"kind": "location", "name": "Sneaky"}).status_code == 403
