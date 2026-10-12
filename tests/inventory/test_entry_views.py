import datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.inventory.models import Company, EntryKind, StockEntry
from apps.inventory.selectors import picker_data, picker_option
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate().isoformat()


def lines(*rows):
    data = {"line_item": [], "line_qty": [], "line_batch": [], "line_pkd": []}
    for item, qty in rows:
        data["line_item"].append(str(item.pk))
        data["line_qty"].append(str(qty))
        data["line_batch"].append("")
        data["line_pkd"].append("")
    return data


def submit(client, url, data):
    """Open the form (which issues a one-time token), then post it with that token."""
    client.get(url)
    return client.post(url, {**data, "entry_token": client.session["entry_tokens"][-1]})


def stock(item, qty, user, place=None):
    return post_entry(
        kind=EntryKind.IN,
        entry_date=timezone.localdate(),
        lines=[Line(item, place or loc(), qty)],
        user=user,
        subtype="SUPPLIER",
        party="Wipro Lighting",
    )


def test_stock_in_from_supplier(office_client):
    a = make_item("EIO6006")
    wipro = Company.objects.get(name="Wipro Lighting")
    r = submit(
        office_client,
        "/stock/in/",
        {
            "entry_date": TODAY,
            "subtype": "SUPPLIER",
            "company": wipro.pk,
            "party": "",
            "location": loc().pk,
            "ref": "DC 1",
            "note": "",
            **lines((a, 5)),
        },
    )
    entry = StockEntry.objects.get()
    assert r.status_code == 302 and r.url == "/entries/IN-0001/"
    assert (entry.party, entry.company, entry.subtype) == ("Wipro Lighting", wipro, "SUPPLIER")


def test_stock_in_needs_supplier(office_client):
    a = make_item("EIO6006")
    html = submit(
        office_client,
        "/stock/in/",
        {
            "entry_date": TODAY,
            "subtype": "SUPPLIER",
            "company": "",
            "party": "",
            "location": loc().pk,
            **lines((a, 5)),
        },
    ).content.decode()
    assert "Choose the supplier." in html and not StockEntry.objects.exists()
    assert '"item": ' in html  # the typed lines come back to the page


def test_stock_in_return_from_site(office_client):
    a = make_item("EIO6006")
    r = submit(
        office_client,
        "/stock/in/",
        {"entry_date": TODAY, "subtype": "RETURN", "party": "BARC", "location": loc().pk, **lines((a, 2))},
    )
    assert r.url == "/entries/IN-0001/"
    entry = StockEntry.objects.get()
    assert (entry.party, entry.company, entry.subtype) == ("BARC", None, "RETURN")


def test_stock_in_page_defaults_and_quick_create_modal(office_client):
    wipro = Company.objects.get(name="Wipro Lighting")
    html = office_client.get("/stock/in/").content.decode()
    assert f'<option value="{wipro.pk}" selected>Wipro Lighting</option>' in html
    assert 'name="qi-code"' in html and 'id="qi-code-hint"' in html
    assert 'name="is_active"' not in html
    assert 'class="form-selectgroup-input"' in html


def test_stock_out_over_issue_refused(office_client, office_user):
    a = make_item("EIO6006")
    stock(a, 2, office_user)
    html = submit(
        office_client,
        "/stock/out/",
        {"entry_date": TODAY, "subtype": "SITE", "party": "BARC", "location": loc().pk, **lines((a, 5))},
    ).content.decode()
    assert "Only 2 NOS of EIO6006 at Vizag Office. Nothing was saved." in html
    assert StockEntry.objects.count() == 1


def test_stock_out_needs_name(office_client, office_user):
    a = make_item("EIO6006")
    stock(a, 2, office_user)
    html = submit(
        office_client,
        "/stock/out/",
        {"entry_date": TODAY, "subtype": "TECH", "party": " ", "location": loc().pk, **lines((a, 1))},
    ).content.decode()
    assert "Enter who it was issued to (technician)." in html
    assert StockEntry.objects.count() == 1


def test_transfer(office_client, office_user):
    a = make_item("EIO6006")
    stock(a, 4, office_user)
    r = submit(
        office_client,
        "/stock/transfer/",
        {"entry_date": TODAY, "location": loc().pk, "to_location": loc("TV Shop").pk, **lines((a, 3))},
    )
    assert r.url == "/entries/TRF-0001/"
    assert StockEntry.objects.get(number="TRF-0001").party == "TV Shop"


def test_transfer_same_location_refused(office_client):
    a = make_item("EIO6006")
    html = submit(
        office_client,
        "/stock/transfer/",
        {"entry_date": TODAY, "location": loc().pk, "to_location": loc().pk, **lines((a, 3))},
    ).content.decode()
    assert "From and To locations must be different." in html


def test_adjust_posts_difference(office_client, office_user):
    a = make_item("EIO6006")
    stock(a, 4, office_user)
    r = submit(
        office_client,
        "/stock/adjust/",
        {
            "entry_date": TODAY,
            "location": loc().pk,
            "reason": "DAMAGED",
            "note": "2 cracked",
            **lines((a, 2)),
        },
    )
    assert r.url == "/entries/ADJ-0001/"
    assert StockEntry.objects.get(number="ADJ-0001").lines.get().qty == -2


def test_adjust_needs_reason(office_client):
    a = make_item("EIO6006")
    html = submit(
        office_client,
        "/stock/adjust/",
        {"entry_date": TODAY, "location": loc().pk, "reason": "", "note": "x", **lines((a, 2))},
    ).content.decode()
    assert "Choose the reason for the adjustment." in html
    assert not StockEntry.objects.exists()


def test_future_date_refused(office_client):
    a = make_item("EIO6006")
    future = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
    html = submit(
        office_client,
        "/stock/out/",
        {"entry_date": future, "subtype": "SITE", "party": "X", "location": loc().pk, **lines((a, 1))},
    ).content.decode()
    assert "The date can&#x27;t be in the future." in html


def test_entry_detail_and_undo(office_client, office_user):
    a = make_item("EIO6006")
    entry = stock(a, 4, office_user)
    html = office_client.get(f"/entries/{entry.number}/").content.decode()
    assert "IN-0001" in html and "EIO6006" in html and "Undo this entry" in html
    r = office_client.post(f"/entries/{entry.number}/undo/", {"reason": "typed wrong qty"})
    assert r.url == "/entries/REV-0001/"
    html = office_client.get(f"/entries/{entry.number}/").content.decode()
    assert "Undone by" in html and "Undo this entry" not in html and "Undone</span>" in html
    rev = office_client.get("/entries/REV-0001/").content.decode()
    assert "This entry cancels" in rev and "Undo this entry" not in rev


def test_undo_needs_reason(office_client, office_user):
    a = make_item("EIO6006")
    entry = stock(a, 4, office_user)
    r = office_client.post(f"/entries/{entry.number}/undo/", {"reason": " "}, follow=True)
    assert "Please give a reason." in r.content.decode()


def test_undo_refused_when_stock_used(office_client, office_user):
    a = make_item("EIO6006")
    entry = stock(a, 4, office_user)
    post_entry(
        kind=EntryKind.OUT,
        entry_date=timezone.localdate(),
        lines=[Line(a, loc(), -3)],
        user=office_user,
        subtype="SITE",
        party="BARC",
    )
    r = office_client.post(f"/entries/{entry.number}/undo/", {"reason": "oops"}, follow=True)
    assert "That stock has already been used" in r.content.decode()
    assert not StockEntry.objects.filter(kind=EntryKind.REV).exists()


def test_undo_get_not_allowed(office_client, office_user):
    a = make_item("EIO6006")
    entry = stock(a, 4, office_user)
    assert office_client.get(f"/entries/{entry.number}/undo/").status_code == 405


def test_prefill_item_from_query(office_client):
    a = make_item("EIO6006")
    html = office_client.get(f"/stock/out/?item={a.pk}").content.decode()
    assert f'"item": "{a.pk}"' in html


def test_entry_numbers_link_to_detail(office_client, office_user):
    a = make_item("EIO6006")
    stock(a, 4, office_user)
    for url in ["/", "/movements/", f"/items/{a.pk}/"]:
        assert 'href="/entries/IN-0001/"' in office_client.get(url).content.decode(), url


def test_picker_option_keys_and_picker_data(office_user):
    a = make_item("EIO6006", cat_ref="LF40")
    a.aliases.create(alias="EI-06006")
    make_item("OLD-1", is_active=False)
    stock(a, 4, office_user)
    option = picker_option(a)
    assert option["aliases"] == ["EI-06006"]
    assert option["keys"].split() == ["E106006", "E16006", "LF40"]
    items, balances = picker_data()
    assert [i["code"] for i in items] == ["EIO6006"]
    assert balances == {f"{a.pk}-{loc().pk}": 4}


def test_entry_pages_need_login(client):
    for url in ["/stock/in/", "/stock/out/", "/stock/transfer/", "/stock/adjust/"]:
        assert client.get(url).status_code == 302


def stock_in_data(item, qty=5):
    wipro = Company.objects.get(name="Wipro Lighting")
    return {
        "entry_date": TODAY,
        "subtype": "SUPPLIER",
        "company": wipro.pk,
        "location": loc().pk,
        **lines((item, qty)),
    }


def test_same_form_posted_twice_saves_once(office_client):
    a = make_item("EIO6006")
    office_client.get("/stock/in/")
    data = {**stock_in_data(a), "entry_token": office_client.session["entry_tokens"][-1]}
    assert office_client.post("/stock/in/", data).url == "/entries/IN-0001/"
    r = office_client.post("/stock/in/", data, follow=True)
    assert StockEntry.objects.count() == 1
    assert r.redirect_chain[-1][0] == "/entries/IN-0001/"
    assert "This entry was already saved." in r.content.decode()


def test_post_without_token_saves_nothing_and_keeps_lines(office_client):
    a = make_item("EIO6006")
    html = office_client.post("/stock/in/", stock_in_data(a)).content.decode()
    assert "nothing was saved" in html and f'"item": "{a.pk}"' in html
    assert not StockEntry.objects.exists()
    assert office_client.session["entry_tokens"]  # a fresh token for the retry


def test_token_survives_a_failed_post(office_client):
    a = make_item("EIO6006")
    office_client.get("/stock/in/")
    token = office_client.session["entry_tokens"][-1]
    bad = {**stock_in_data(a), "company": "", "entry_token": token}
    assert "Choose the supplier." in office_client.post("/stock/in/", bad).content.decode()
    assert (
        office_client.post("/stock/in/", {**stock_in_data(a), "entry_token": token}).url
        == "/entries/IN-0001/"
    )


def test_stock_in_opening(office_client):
    a = make_item("EIO6006")
    r = submit(
        office_client,
        "/stock/in/",
        {"entry_date": TODAY, "subtype": "OPENING", "location": loc().pk, **lines((a, 7))},
    )
    entry = StockEntry.objects.get()
    assert r.url == "/entries/IN-0001/"
    assert (entry.subtype, entry.party, entry.company) == ("OPENING", "Opening stock (first count)", None)


def test_transfer_from_empty_location_refused(office_client):
    a = make_item("EIO6006")
    html = submit(
        office_client,
        "/stock/transfer/",
        {"entry_date": TODAY, "location": loc().pk, "to_location": loc("TV Shop").pk, **lines((a, 1))},
    ).content.decode()
    assert "Only 0 NOS of EIO6006 at Vizag Office. Nothing was saved." in html
    assert not StockEntry.objects.exists()


def test_adjust_refused_when_stock_changed_since_page_opened(office_client, office_user):
    a = make_item("EIO6006")
    stock(a, 4, office_user)
    data = {"entry_date": TODAY, "location": loc().pk, "reason": "DAMAGED", "note": "x", **lines((a, 2))}
    html = submit(office_client, "/stock/adjust/", {**data, "line_expected": ["3"]}).content.decode()
    assert (
        "Line 1: stock of EIO6006 at Vizag Office changed since you opened this page (was 3, now 4). "
        "Check the count and save again." in html
    )
    assert StockEntry.objects.count() == 1
    assert (
        submit(office_client, "/stock/adjust/", {**data, "line_expected": ["4"]}).url == "/entries/ADJ-0001/"
    )


def test_entry_form_has_token_and_qty_limit(office_client):
    html = office_client.get("/stock/out/").content.decode()
    token = office_client.session["entry_tokens"][-1]
    assert f'name="entry_token" value="{token}"' in html
    script = (Path(settings.BASE_DIR) / "static" / "js" / "entry-form.js").read_text(encoding="utf-8")
    assert 'max="1000000"' in script
