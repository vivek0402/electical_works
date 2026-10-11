import pytest
from django.test import Client

from tests.factories import make_user


@pytest.fixture
def admin_user(db):
    return make_user("admin_t", "ADMIN", superuser=True)


@pytest.fixture
def office_user(db):
    return make_user("office_t", "OFFICE")


@pytest.fixture
def office_client(office_user):
    client = Client()
    client.force_login(office_user)
    return client


@pytest.fixture
def admin_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client
