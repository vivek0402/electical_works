import pytest
from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import resolve
from django.utils import timezone

from apps.core.templatetags.core_tags import get_item, lines_summary, qty
from apps.inventory.context_processors import nav
from apps.inventory.models import EntryKind
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def render_url_with(query, **kw):
    request = RequestFactory().get("/" + query)
    args = " ".join(f"{k}={v!r}" for k, v in kw.items())
    return Template("{% load core_tags %}{% url_with " + args + " %}").render(Context({"request": request}))


def test_url_with_replace_remove_int():
    assert render_url_with("?a=1&page=2", page=3) == "?a=1&amp;page=3"
    assert render_url_with("?a=1&page=2", page=None) == "?a=1"
    assert "page=7" in render_url_with("?a=1", page=7)


def test_qty_and_get_item():
    assert 'class="zero"' in qty(0)
    assert qty(5) == 5
    assert get_item({"a": 2}, "a") == 2
    assert get_item({"a": 2}, "x") == 0
    assert get_item(None, "x") == 0


def test_lines_summary(office_user):
    a, b = make_item("S1"), make_item("S2")
    one = post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(a, loc(), 3)], user=office_user)
    two = post_entry(
        kind=EntryKind.IN, entry_date=TODAY, lines=[Line(a, loc(), 3), Line(b, loc(), 1)], user=office_user
    )
    trf = post_entry(
        kind=EntryKind.TRF,
        entry_date=TODAY,
        lines=[Line(a, loc(), -2), Line(a, loc("Svkml"), 2)],
        user=office_user,
    )
    assert "S1" in lines_summary(one) and "× 3" in lines_summary(one)
    assert lines_summary(two) == "2 items"
    assert "× 2" in lines_summary(trf)


def request_for(path, user):
    request = RequestFactory().get(path)
    request.user = user
    request.resolver_match = resolve(path)
    return request


def test_nav_anonymous_empty():
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    assert nav(request) == {}


# Menu entries whose screens later tasks build; they render disabled until their URL name resolves.
# Remove a name here when its screen is built.
UNBUILT: set[str] = set()


def test_only_unbuilt_screens_are_disabled_in_the_menu(office_user):
    from apps.inventory import context_processors as cp

    ctx = cp.nav(request_for("/", office_user))
    disabled = {e["name"] for _, entries in ctx["nav_sections"] for e in entries if not e["url"]}
    assert disabled == UNBUILT


def test_nav_masters_hidden_and_stock_screens_live(office_client):
    html = office_client.get("/").content.decode()
    assert "Masters" not in html
    for url in ["/stock/in/", "/stock/out/", "/stock/transfer/", "/stock/adjust/"]:
        assert f'href="{url}"' in html
    assert html.count('aria-disabled="true"') == len(UNBUILT)  # only the service screens still to come


def test_nav_masters_live_for_admin_only(admin_client, office_client):
    admin_html = admin_client.get("/items/").content.decode()
    assert 'href="/masters/"' in admin_html
    assert admin_html.count('aria-disabled="true"') == len(UNBUILT)
    assert 'href="/masters/"' not in office_client.get("/items/").content.decode()


def test_nav_masters_visible_to_admin(admin_client):
    assert "Masters" in admin_client.get("/items/").content.decode()


def test_nav_active_alias(office_user, monkeypatch):
    from apps.inventory import context_processors as cp

    request = request_for("/", office_user)
    request.resolver_match.url_name = "item_detail"
    ctx = cp.nav(request)
    items = next(e for title, entries in ctx["nav_sections"] for e in entries if e["name"] == "items")
    dash = next(e for title, entries in ctx["nav_sections"] for e in entries if e["name"] == "dashboard")
    assert items["active"] and not dash["active"]


def test_tab_pages_show_section_tabs_and_actions_form_pages_show_a_back_link(office_client):
    stock = office_client.get("/stock/").context
    assert [t["name"] for t in stock["nav_tabs"]] == ["current_stock", "movements", "low_stock"]
    assert [a["name"] for a in stock["nav_actions"]] == ["stock_in", "stock_out", "transfer", "adjust"]
    assert stock["nav_back"] is None
    form = office_client.get("/stock/in/").context
    assert form["nav_tabs"] == [] and form["nav_actions"] == []
    assert form["nav_back"]["url"] == "/stock/" and form["nav_back"]["label"] == "Current stock"
    top = {p["key"]: p["active"] for p in form["nav_top"]}
    assert top == {"home": False, "stock": True, "complaints": False, "defectives": False, "setup": False}


def test_masters_tab_is_admin_only_and_home_has_no_tab_strip(office_client, admin_client):
    assert office_client.get("/").context["nav_tabs"] == []
    assert [t["name"] for t in office_client.get("/items/").context["nav_tabs"]] == ["items"]
    assert [t["name"] for t in admin_client.get("/items/").context["nav_tabs"]] == ["items", "masters"]
