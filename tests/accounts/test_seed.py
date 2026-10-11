import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


def test_seed_requires_password_env(monkeypatch):
    monkeypatch.delenv("SEED_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="SEED_PASSWORD"):
        call_command("seed_demo")


def test_seed_creates_users_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "first-pass")
    call_command("seed_demo")
    monkeypatch.setenv("SEED_PASSWORD", "second-pass")
    call_command("seed_demo")

    assert User.objects.count() == 4
    admin = User.objects.get(username="admin")
    assert admin.is_superuser and admin.is_staff
    assert admin.check_password("first-pass")  # re-run keeps existing passwords

    ramu = User.objects.get(username="ramu")
    assert list(ramu.groups.values_list("name", flat=True)) == ["TECHNICIAN"]
    assert not ramu.is_staff
    assert hasattr(ramu, "profile")
    assert User.objects.get(username="apparao").groups.filter(name="TECHNICIAN").exists()
    assert User.objects.get(username="office").groups.filter(name="OFFICE").exists()
