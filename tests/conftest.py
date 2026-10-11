import pytest

from apps.accounts.roles import ADMIN, OFFICE, TECHNICIAN

from .factories import UserFactory


@pytest.fixture
def admin_user(db):
    return UserFactory(username="admin_t", role=ADMIN, is_staff=True, is_superuser=True)


@pytest.fixture
def office_user(db):
    return UserFactory(username="office_t", role=OFFICE)


@pytest.fixture
def tech_user(db):
    return UserFactory(username="tech_t", role=TECHNICIAN)
