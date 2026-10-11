import datetime

import pytest
from django.template import Context, Template
from django.urls import reverse

from tests.factories import PASSWORD

pytestmark = pytest.mark.django_db


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_requires_login(client):
    response = client.get(reverse("home"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_login_logout_flow(client, office_user):
    response = client.post(
        reverse("login"), {"username": office_user.username, "password": PASSWORD}
    )
    assert response.status_code == 302
    assert response.url == reverse("home")

    home = client.get(reverse("home"))
    assert home.status_code == 200
    assert b"Office" in home.content
    assert b"/admin/" not in home.content  # admin link only for ADMIN

    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert client.get(reverse("home")).status_code == 302


def test_wrong_password_shows_friendly_error(client, office_user):
    response = client.post(reverse("login"), {"username": office_user.username, "password": "no"})
    assert response.status_code == 200
    assert b"Wrong username or password" in response.content


def test_admin_sees_admin_link_and_admin_site(client, admin_user):
    client.force_login(admin_user)
    assert b"/admin/" in client.get(reverse("home")).content
    assert client.get(reverse("admin:index")).status_code == 200


def test_technician_cannot_open_admin_site(client, tech_user):
    client.force_login(tech_user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert "/admin/login/" in response.url


def test_dates_render_dd_mm_yyyy():
    rendered = Template("{{ d|date }}|{{ d|date:'SHORT_DATE_FORMAT' }}").render(
        Context({"d": datetime.date(2026, 5, 25)})
    )
    assert rendered == "25-05-2026|25-05-2026"
