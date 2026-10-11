import datetime
from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.template import Context, Template


@pytest.mark.django_db
def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_503_when_db_down(client):
    with patch("apps.core.views.connection.cursor", side_effect=OperationalError("down")):
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unreachable"}


def test_dates_render_dd_mm_yyyy():
    out = Template("{{ d|date }}|{{ d|date:'SHORT_DATE_FORMAT' }}").render(
        Context({"d": datetime.date(2026, 5, 25)})
    )
    assert out == "25-05-2026|25-05-2026"
