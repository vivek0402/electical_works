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
    monkeypatch.setenv("SEED_PASSWORD", "Str0ng-seed-pass-1")
    call_command("seed_users")
    monkeypatch.setenv("SEED_PASSWORD", "Str0ng-seed-pass-2")
    call_command("seed_users")
    assert User.objects.count() == 2
    admin = User.objects.get(username="admin")
    assert admin.is_superuser and admin.check_password("Str0ng-seed-pass-1")
    assert User.objects.get(username="office").groups.filter(name="OFFICE").exists()


def test_login_page_and_flow(client, office_user):
    page = client.get("/login/")
    assert page.status_code == 200 and b"Sign in" in page.content
    bad = client.post("/login/", {"username": office_user.username, "password": "nope"})
    assert b"Wrong username or password" in bad.content
    good = client.post("/login/", {"username": office_user.username, "password": PASSWORD})
    assert good.status_code == 302 and good.url == "/"


def test_login_field_errors(client):
    page = client.post("/login/", {"username": "", "password": ""})
    assert b"This field is required." in page.content and b"is-invalid" in page.content


def test_login_next_offsite_ignored(client, office_user):
    r = client.post(
        "/login/?next=https://evil.example", {"username": office_user.username, "password": PASSWORD}
    )
    assert r.status_code == 302 and r.url == "/"


def test_logout_post_only(office_client):
    assert office_client.get("/logout/").status_code == 405
    r = office_client.post("/logout/")
    assert r.status_code == 302 and r.url == "/login/"
    assert "_auth_user_id" not in office_client.session


def test_admin_group_member_gets_staff_access(client):
    user = User.objects.create_user("plain", password=PASSWORD)
    client.force_login(user)
    assert client.get("/admin/").status_code == 302
    user.groups.add(Group.objects.get(name=ADMIN))
    assert client.get("/admin/").status_code == 200
    user.groups.remove(Group.objects.get(name=ADMIN))
    user.refresh_from_db()
    assert not user.is_staff


def test_role_required_needs_roles():
    with pytest.raises(ValueError):
        role_required()


def test_seed_users_rejects_weak_password(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "123")
    with pytest.raises(CommandError, match="too weak"):
        call_command("seed_users")


def test_admin_site_admin_only(admin_client, office_client):
    assert admin_client.get("/admin/").status_code == 200
    assert office_client.get("/admin/").status_code == 302
