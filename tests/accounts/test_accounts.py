import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import PermissionDenied
from django.core.management import CommandError, call_command
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN, OFFICE, has_role
from tests.factories import PASSWORD

pytestmark = pytest.mark.django_db


@role_required(ADMIN)
def admin_only(request):
    return HttpResponse("ok")


def call(view, user):
    request = RequestFactory().get("/x")
    request.user = user
    return view(request)


def test_role_groups_exist():
    assert set(Group.objects.values_list("name", flat=True)) >= {"ADMIN", "OFFICE"}


def test_has_role(admin_user, office_user):
    assert has_role(office_user, OFFICE)
    assert not has_role(office_user, ADMIN)
    assert has_role(admin_user, OFFICE)  # admin may do everything
    assert not has_role(AnonymousUser(), OFFICE)


def test_role_required(admin_user, office_user):
    assert call(admin_only, admin_user).status_code == 200
    with pytest.raises(PermissionDenied):
        call(admin_only, office_user)
    response = call(admin_only, AnonymousUser())
    assert response.status_code == 302 and "/login/" in response.url


def test_seed_users_requires_password(monkeypatch):
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="SEED_PASSWORD"):
        call_command("seed_users")


def test_seed_users_idempotent(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "first-pass")
    call_command("seed_users")
    monkeypatch.setenv("SEED_PASSWORD", "second-pass")
    call_command("seed_users")
    assert User.objects.count() == 2
    admin = User.objects.get(username="admin")
    assert admin.is_superuser and admin.check_password("first-pass")
    assert User.objects.get(username="office").groups.filter(name="OFFICE").exists()


def test_login_page_and_flow(client, office_user):
    page = client.get("/login/")
    assert page.status_code == 200 and b"Sign in" in page.content
    bad = client.post("/login/", {"username": office_user.username, "password": "nope"})
    assert b"Wrong username or password" in bad.content
    good = client.post("/login/", {"username": office_user.username, "password": PASSWORD})
    assert good.status_code == 302


def test_admin_site_admin_only(admin_client, office_client):
    assert admin_client.get("/admin/").status_code == 200
    assert office_client.get("/admin/").status_code == 302
