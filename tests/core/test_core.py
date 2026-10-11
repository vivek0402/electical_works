import datetime

import pytest
from django.template import Context, Template

pytestmark = pytest.mark.django_db


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dates_render_dd_mm_yyyy():
    out = Template("{{ d|date }}|{{ d|date:'SHORT_DATE_FORMAT' }}").render(
        Context({"d": datetime.date(2026, 5, 25)})
    )
    assert out == "25-05-2026|25-05-2026"
