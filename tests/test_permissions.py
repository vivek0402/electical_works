import pytest
from django.urls import get_resolver

pytestmark = pytest.mark.django_db
PUBLIC = {"login", "logout", "healthz"}
ADMIN_ONLY = {"masters", "masters_toggle"}


def named_routes():
    for name, patterns in get_resolver().reverse_dict.items():
        if isinstance(name, str) and not name.startswith("admin") and name not in PUBLIC:
            result, params = patterns[0][
                0
            ]  # (possibilities, pattern, defaults, converters)[0] -> first possibility
            yield name, result % {k: 1 for k in params}


def test_sweep_finds_the_routes():
    names = {n for n, _ in named_routes()}
    assert {"dashboard", "entry_undo", "item_quick_create", "masters_toggle", "global_search"} <= names
    assert len(names) >= 24


@pytest.mark.parametrize("name,path", sorted(named_routes()))
def test_anonymous_is_sent_to_login(client, name, path):
    r = client.get("/" + path)
    assert r.status_code == 302 and r.url.startswith("/login/"), name


@pytest.mark.parametrize("name,path", sorted(n for n in named_routes() if n[0] in ADMIN_ONLY))
def test_office_blocked_from_admin_pages(office_client, name, path):
    assert office_client.get("/" + path).status_code == 403
