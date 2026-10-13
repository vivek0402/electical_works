import pytest
from django.utils import timezone

from apps.defectives.models import BatchStatus, DefectivePiece, Outcome, PieceStatus, ReturnBatch
from apps.defectives.services import create_batch, dispatch, settle
from apps.inventory.models import Company, StockBalance
from tests.factories import loc, make_item, make_pieces, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def wipro():
    return Company.objects.get(name="Wipro Lighting")


def token(client, url):
    """Open `url` (which issues a one-time token) and return that token."""
    client.get(url)
    return client.session["entry_tokens"][-1]


def post(client, page, action, data, follow=True):
    """Post `data` to `action` with a fresh token from `page`, as the browser would."""
    return client.post(action, {**data, "entry_token": token(client, page)}, follow=follow)


@pytest.fixture
def pieces(office_user):
    """DEF-0001..0003 (Wipro), after IN-0001 (stock) and TRF-0001 (marked defective)."""
    return make_pieces(make_item("LG78-150-700", description="LED driver 150W"), 3, office_user)


# ---------------------------------------------------------------- new batch


def test_new_batch_offers_only_that_companys_pieces(office_client, office_user, pieces):
    make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user)
    html = office_client.get(f"/defectives/batches/new/?company={wipro().pk}").content.decode()
    assert "DEF-0001" in html and "DEF-0004" not in html
    assert ">Havells</option>" in html and ">Wipro Lighting</option>" in html


def test_new_batch_preticks_a_piece_from_the_piece_card(office_client, pieces):
    html = office_client.get(f"/defectives/batches/new/?company={wipro().pk}&tag=DEF-0002").content.decode()
    assert 'value="DEF-0002" data-tick aria-label="Tick DEF-0002" checked' in html


def test_create_batch_from_the_form(office_client, pieces):
    url = "/defectives/batches/new/"
    r = post(
        office_client,
        url,
        url,
        {"company": wipro().pk, "tag": ["DEF-0001", "DEF-0002"], "note": "Bank sites"},
        False,
    )
    assert r.status_code == 302 and r.url == "/defectives/batches/RB-0001/"
    b = ReturnBatch.objects.get()
    assert b.note == "Bank sites" and b.lines.count() == 2


def test_create_batch_twice_with_one_token_saves_once(office_client, pieces):
    url = "/defectives/batches/new/"
    data = {"company": wipro().pk, "tag": ["DEF-0001"], "entry_token": token(office_client, url)}
    office_client.post(url, data)
    r = office_client.post(url, data, follow=True)
    assert "This was already saved." in r.content.decode() and ReturnBatch.objects.count() == 1


def test_create_batch_without_a_token_saves_nothing(office_client, pieces):
    html = office_client.post("/defectives/batches/new/", {"company": wipro().pk}).content.decode()
    assert "This form had expired" in html and not ReturnBatch.objects.exists()


def test_new_batch_needs_a_company(office_client, pieces):
    url = "/defectives/batches/new/"
    html = post(office_client, url, url, {"tag": ["DEF-0001"]}).content.decode()
    assert "Choose the company the pieces go back to." in html and not ReturnBatch.objects.exists()


def test_new_batch_note_too_long_is_refused(office_client, pieces):
    url = "/defectives/batches/new/"
    html = post(office_client, url, url, {"company": wipro().pk, "note": "x" * 201}).content.decode()
    assert "200 characters" in html and not ReturnBatch.objects.exists()


# ---------------------------------------------------------------- draft batch


def test_draft_add_by_typed_tag_and_remove(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    url = f"/defectives/batches/{b.number}/"
    html = office_client.get(url).content.decode()
    assert "Draft" in html and "Dispatch" in html and "DEF-0002" in html
    html = post(office_client, url, url + "add/", {"tag_text": "def-2"}).content.decode()
    assert "DEF-0002 added to RB-0001." in html and b.lines.count() == 2
    html = post(office_client, url, url + "remove/", {"tag": "DEF-0001"}).content.decode()
    assert "DEF-0001 removed from RB-0001. It is back in store." in html
    assert DefectivePiece.objects.get(tag="DEF-0001").status == PieceStatus.IN_STORE
    html = post(office_client, url, url + "add/", {"tag_text": "DEF-0099"}).content.decode()
    assert "There is no piece tagged DEF-0099." in html


def test_add_ticked_pieces(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user)
    url = f"/defectives/batches/{b.number}/"
    post(office_client, url, url + "add/", {"tag": ["DEF-0002", "DEF-0003"]})
    assert sorted(b.lines.values_list("piece__tag", flat=True)) == ["DEF-0002", "DEF-0003"]


def test_add_nothing_ticked_is_shown_inline(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user)
    url = f"/defectives/batches/{b.number}/"
    html = post(office_client, url, url + "add/", {}).content.decode()
    assert "Type a tag (e.g. DEF-0042) or tick pieces to add." in html


def test_add_another_companys_piece_is_refused(office_client, office_user, pieces):
    make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user)
    b = create_batch(company=wipro(), user=office_user)
    url = f"/defectives/batches/{b.number}/"
    html = post(office_client, url, url + "add/", {"tag_text": "DEF-0004"}).content.decode()
    assert "A batch holds one company&#x27;s pieces only." in html and not b.lines.exists()


def test_remove_replayed_token_does_not_act_twice(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:2])
    url = f"/defectives/batches/{b.number}/"
    data = {"tag": "DEF-0001", "entry_token": token(office_client, url)}
    office_client.post(url + "remove/", data)
    html = office_client.post(url + "remove/", data, follow=True).content.decode()
    assert "This was already saved." in html and b.lines.count() == 1


# ---------------------------------------------------------------- dispatch and settle


def test_dispatch_and_settle_from_the_detail_page(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:2])
    url = f"/defectives/batches/{b.number}/"
    day = TODAY.isoformat()
    html = post(
        office_client,
        url,
        url + "dispatch/",
        {"dispatched_on": day, "courier": "DTDC", "docket_no": "D51243817"},
    ).content.decode()
    assert "RB-0001 dispatched. Stock OUT OUT-0001 posted from the Defective store." in html
    assert "Settle ticked pieces" in html and "D51243817" in html
    assert "Add ticked" not in html and "/remove/" not in html  # locked: no add or remove controls
    before = (
        StockBalance.objects.filter(item=pieces[0].item, location=loc()).values_list("qty", flat=True).first()
        or 0
    )
    html = post(
        office_client,
        url,
        url + "settle/",
        {"tag": ["DEF-0001"], "outcome": "REPLACED", "settled_on": day, "to_location": loc().pk},
    ).content.decode()
    assert "1 piece(s) settled as Replaced. Entries: IN-0002." in html and "Partly settled" in html
    assert 'href="/entries/IN-0002/"' in html
    assert StockBalance.objects.get(item=pieces[0].item, location=loc()).qty == before + 1
    html = post(
        office_client,
        url,
        url + "settle/",
        {"tag": ["DEF-0002"], "outcome": "REJECTED_RETURNED", "settled_on": day},
    ).content.decode()
    assert "settled as Rejected (returned)" in html and "All pieces are settled." in html
    assert ReturnBatch.objects.get().status == BatchStatus.DISPATCHED
    assert DefectivePiece.objects.get(tag="DEF-0002").status == PieceStatus.IN_STORE


def test_settle_offers_only_good_active_locations(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    html = office_client.get(f"/defectives/batches/{b.number}/").content.decode()
    assert f'<option value="{loc().pk}">Vizag Office</option>' in html
    assert f'<option value="{store().pk}"' not in html


def test_settle_into_the_store_is_refused_inline(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    url = f"/defectives/batches/{b.number}/"
    data = {
        "tag": ["DEF-0001"],
        "outcome": "REPLACED",
        "settled_on": TODAY.isoformat(),
        "to_location": store().pk,
    }
    r = post(office_client, url, url + "settle/", data, follow=False)
    assert r.status_code == 200 and "Goes into location:" in r.content.decode()
    data["to_location"] = ""
    html = post(office_client, url, url + "settle/", data).content.decode()
    assert "Choose the good-stock location the replacement pieces go into." in html
    assert 'value="DEF-0001" data-tick aria-label="Tick DEF-0001" checked' in html  # the ticks are kept
    assert DefectivePiece.objects.get(tag="DEF-0001").status == PieceStatus.SENT


def test_settle_rejected_ignores_a_location(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    url = f"/defectives/batches/{b.number}/"
    data = {
        "tag": ["DEF-0001"],
        "outcome": "REJECTED_SCRAPPED",
        "settled_on": TODAY.isoformat(),
        "to_location": loc().pk,
    }
    html = post(office_client, url, url + "settle/", data).content.decode()
    assert "1 piece(s) settled as Rejected (scrapped)." in html
    assert b.lines.get().to_location is None


def test_settle_needs_ticks(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    url = f"/defectives/batches/{b.number}/"
    html = post(
        office_client, url, url + "settle/", {"outcome": "REPLACED", "settled_on": TODAY.isoformat()}
    ).content.decode()
    assert "Tick the pieces the company has answered for." in html


def test_settled_lines_are_grouped_by_entry(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces)
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(
        batch=b,
        pieces=pieces[:2],
        outcome=Outcome.REPLACED,
        settled_on=TODAY,
        to_location=loc(),
        user=office_user,
    )
    html = office_client.get(f"/defectives/batches/{b.number}/").content.decode()
    assert "Answers recorded" in html and "DEF-0001, DEF-0002" in html


def test_dispatch_errors_are_shown(office_client, office_user):
    b = create_batch(company=wipro(), user=office_user)
    url = f"/defectives/batches/{b.number}/"
    html = post(
        office_client,
        url,
        url + "dispatch/",
        {"dispatched_on": TODAY.isoformat(), "courier": "DTDC", "docket_no": "D1"},
    ).content.decode()
    assert "An empty batch" in html and "data-show-on-load" in html


def test_dispatch_courier_over_60_characters_is_refused(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    url = f"/defectives/batches/{b.number}/"
    data = {"dispatched_on": TODAY.isoformat(), "courier": "C" * 61, "docket_no": "D1"}
    html = post(office_client, url, url + "dispatch/", data).content.decode()
    assert "Courier:" in html and ReturnBatch.objects.get().is_draft


def test_dispatch_suggests_couriers(office_client, office_user, pieces, settings):
    settings.COURIERS = ["DTDC", "By hand"]
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    html = office_client.get(f"/defectives/batches/{b.number}/").content.decode()
    assert 'list="couriers"' in html and '<option value="By hand">' in html and 'maxlength="60"' in html


# ---------------------------------------------------------------- list and piece card


def test_batches_list_shows_the_worked_out_status(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:2])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(
        batch=b,
        pieces=pieces[:1],
        outcome=Outcome.REPLACED,
        settled_on=TODAY,
        to_location=loc(),
        user=office_user,
    )
    create_batch(company=wipro(), user=office_user)  # RB-0002, a draft
    html = office_client.get("/defectives/batches/").content.decode()
    assert "Partly settled" in html and "1 / 2" in html and "RB-0002" in html
    html = office_client.get("/defectives/batches/?status=Partly+settled").content.decode()
    assert "RB-0001" in html and "RB-0002" not in html


def test_piece_card_shows_history_batches_and_entries(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(batch=b, pieces=pieces[:1], outcome=Outcome.REJECTED_RETURNED, settled_on=TODAY, user=office_user)
    b2 = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])  # sent out again
    html = office_client.get("/defectives/pieces/DEF-0001/").content.decode()
    assert "Marked defective from stock" in html and "Dispatched with RB-0001 (DTDC D1)" in html
    assert "Rejected (returned)" in html and "In draft batch" in html
    assert "TRF-0001" in html and "OUT-0001" in html and "IN-0002" in html
    assert b2.number in html and "Waiting" in html  # every batch it went into, each with its own answer


def test_piece_card_add_to_draft(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user)
    page = "/defectives/pieces/DEF-0003/"
    html = office_client.get(page).content.decode()
    assert f"/defectives/batches/{b.number}/add/" in html and "New batch for Wipro Lighting" in html
    r = post(
        office_client, page, f"/defectives/batches/{b.number}/add/", {"tag": "DEF-0003", "next": page}, False
    )
    assert r.url == page and b.lines.get().piece.tag == "DEF-0003"


def test_entry_page_links_its_return_batch(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    entry = dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    html = office_client.get(f"/entries/{entry.number}/").content.decode()
    assert f'href="/defectives/batches/{b.number}/"' in html


def test_nav_links_return_batches(office_client):
    assert 'href="/defectives/batches/"' in office_client.get("/").content.decode()
