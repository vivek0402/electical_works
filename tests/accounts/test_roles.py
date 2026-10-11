import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN, OFFICE, ROLES, TECHNICIAN, has_role, sync_role_groups
from apps.inventory.models import Location

pytestmark = pytest.mark.django_db


@role_required(OFFICE)
def office_only_view(request):
    return HttpResponse("ok")


def _call(user):
    request = RequestFactory().get("/x")
    request.user = user
    return office_only_view(request)


def test_role_groups_exist_after_migrate():
    assert set(Group.objects.filter(name__in=ROLES).values_list("name", flat=True)) == set(ROLES)


def test_admin_group_has_every_permission_and_office_has_location_view():
    admin = Group.objects.get(name=ADMIN)
    office = Group.objects.get(name=OFFICE)
    assert admin.permissions.filter(codename="delete_location").exists()
    assert office.permissions.filter(codename="view_location").exists()
    assert not office.permissions.filter(codename="delete_location").exists()


def test_sync_role_groups_is_idempotent():
    sync_role_groups()
    sync_role_groups()
    assert Group.objects.filter(name__in=ROLES).count() == 3


def test_locations_seeded():
    names = set(Location.objects.values_list("name", flat=True))
    assert names == {"Svkml", "Vizag Office", "TV Shop", "Kartika Class"}


def test_has_role(admin_user, office_user, tech_user):
    assert has_role(office_user, OFFICE)
    assert not has_role(tech_user, OFFICE)
    assert has_role(admin_user, OFFICE, TECHNICIAN)  # ADMIN may do everything
    assert not has_role(AnonymousUser(), OFFICE)


def test_role_required_allows_role_and_admin(office_user, admin_user):
    assert _call(office_user).status_code == 200
    assert _call(admin_user).status_code == 200


def test_role_required_denies_other_roles(tech_user):
    with pytest.raises(PermissionDenied):
        _call(tech_user)


def test_role_required_redirects_anonymous_to_login():
    response = _call(AnonymousUser())
    assert response.status_code == 302
    assert "/login/" in response.url
