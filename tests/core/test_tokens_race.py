"""A one-time form token must hold even when the same form is posted twice at the same instant.

Found in rigour testing (e2e/rigour/concurrency.py): the token was spent in the session only after the save,
so two requests that both read it as unspent both saved. The token is now also claimed in the database,
inside the saving transaction, so the second request waits for the first and is sent to what it saved.
"""

import threading

import pytest
from django.db import connection
from django.test import Client

from apps.core import tokens
from apps.inventory.models import StockEntry
from tests.factories import make_item
from tests.inventory.test_entry_views import stock_in_data


def _post_twice_together(client, url, data, monkeypatch):
    """Post `data` from two clients that share one session, both past the 'token unspent?' check before
    either has saved."""
    barrier, results, errors = threading.Barrier(2, timeout=15), [], []
    real = tokens.is_issued

    def check_then_wait(session, token):
        issued = real(session, token)
        barrier.wait()
        return issued

    monkeypatch.setattr(tokens, "is_issued", check_then_wait)

    def post():
        try:
            twin = Client()
            twin.cookies = client.cookies
            r = twin.post(url, data)
            results.append((r.status_code, r.get("Location", "")))
        except Exception as exc:  # recorded so a failure can be diagnosed
            errors.append(repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=post) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    return results


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_same_form_posted_at_the_same_instant_saves_once(office_user, monkeypatch):
    item = make_item("EIO6006")
    client = Client()
    client.force_login(office_user)
    client.get("/stock/in/")
    data = {**stock_in_data(item), "entry_token": client.session["entry_tokens"][-1]}

    results = _post_twice_together(client, "/stock/in/", data, monkeypatch)

    assert StockEntry.objects.count() == 1
    assert sorted(results) == [(302, "/entries/IN-0001/")] * 2  # both end on the one entry that was saved


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_refused_post_leaves_the_token_for_a_retry(office_user):
    """The database claim is rolled back with the refused save, so fixing the form and posting again works."""
    item = make_item("EIO6006")
    client = Client()
    client.force_login(office_user)
    client.get("/stock/in/")
    token = client.session["entry_tokens"][-1]
    bad = {**stock_in_data(item), "company": "", "entry_token": token}
    assert "Choose the supplier." in client.post("/stock/in/", bad).content.decode()
    assert client.post("/stock/in/", {**stock_in_data(item), "entry_token": token}).url == "/entries/IN-0001/"
    assert StockEntry.objects.count() == 1
