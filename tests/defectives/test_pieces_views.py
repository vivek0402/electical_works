import re

import pytest

from apps.defectives.models import DefectivePiece, PieceStatus, ReturnBatch
from apps.defectives.services import create_batch
from apps.inventory.models import Company, Location, StockBalance
from tests.factories import make_item, make_pieces

pytestmark = pytest.mark.django_db
LIST, BULK = "/defectives/pieces/", "/defectives/pieces/bulk/"


@pytest.fixture
def mixed(office_user):
    """DEF-0001, DEF-0002 (Wipro driver, 'no output') and DEF-0003 (Havells MCB, 'trips')."""
    make_pieces(make_item("LG78-150-700"), 2, office_user, fault="no output")
    make_pieces(
        make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user, fault="trips"
    )


def tags(client, query=""):
    html = client.get(LIST + query).content.decode()
    return re.findall(r'href="/defectives/pieces/(DEF-\d{4})/"', html)


def bulk(client, data, follow=False, page=LIST):
    """Post `data` to the bulk URL with the one-time token of `page`, as the browser would."""
    client.get(page)
    token = client.session["entry_tokens"][-1]
    return client.post(BULK, {**data, "entry_token": token}, follow=follow)


def test_list_newest_first_and_filters(office_client, mixed):
    assert tags(office_client) == ["DEF-0003", "DEF-0002", "DEF-0001"]
    havells = Company.objects.get(name="Havells")
    assert tags(office_client, f"?company={havells.pk}") == ["DEF-0003"]
    assert tags(office_client, "?q=def-1") == ["DEF-0001"]
    assert tags(office_client, "?q=trips") == ["DEF-0003"]
    assert tags(office_client, "?q=MCB") == ["DEF-0003"]
    assert tags(office_client, "?status=SENT") == []
    assert tags(office_client, "?source=SITE_VISIT") == []
    assert tags(office_client, "?status=IN_STORE&sort=tag&dir=asc") == ["DEF-0001", "DEF-0002", "DEF-0003"]
    assert tags(office_client, "?date_from=2999-01-01") == []
    assert tags(office_client, "?date_to=2000-01-01") == []


def test_only_pieces_in_store_can_be_ticked(office_client, office_user, mixed):
    create_batch(
        company=Company.objects.get(name="Wipro Lighting"),
        user=office_user,
        pieces=list(DefectivePiece.objects.filter(tag="DEF-0001")),
    )
    html = office_client.get(LIST).content.decode()
    assert 'value="DEF-0002" data-tick' in html and 'value="DEF-0001" data-tick' not in html


def test_bulk_add_to_a_new_batch(office_client, mixed):
    r = bulk(office_client, {"action": "batch", "batch": "new", "tag": ["DEF-0001", "DEF-0002"]})
    assert r.status_code == 302 and r.url == "/defectives/batches/RB-0001/"
    assert ReturnBatch.objects.get().company.name == "Wipro Lighting"


def test_bulk_add_refuses_mixed_companies(office_client, mixed):
    data = {"action": "batch", "batch": "new", "tag": ["DEF-0001", "DEF-0003"], "next": LIST}
    html = bulk(office_client, data, follow=True).content.decode()
    assert "belong to 2 companies (Havells, Wipro Lighting)" in html and not ReturnBatch.objects.exists()


def test_bulk_add_to_a_draft_of_another_company_shows_the_services_refusal(office_client, office_user, mixed):
    b = create_batch(company=Company.objects.get(name="Havells"), user=office_user)
    data = {"action": "batch", "batch": b.number, "tag": ["DEF-0002"], "next": LIST}
    html = bulk(office_client, data, follow=True).content.decode()
    assert "holds one company" in html and "only." in html
    assert not b.lines.exists()


def test_bulk_add_to_an_existing_draft(office_client, office_user, mixed):
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user)
    bulk(office_client, {"action": "batch", "batch": b.number, "tag": ["DEF-0002"]})
    assert list(b.lines.values_list("piece__tag", flat=True)) == ["DEF-0002"]


def test_list_offers_drafts_to_choose_from(office_client, office_user, mixed):
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user)
    assert f'value="{b.number}"' in office_client.get(LIST).content.decode()


def test_bulk_scrap(office_client, mixed):
    store = Location.defective_store()
    before = StockBalance.objects.get(location=store, item__code="LG78-150-700").qty
    next_url = LIST + "?status=IN_STORE"
    r = bulk(office_client, {"action": "scrap", "reason": "BURNT", "tag": ["DEF-0001"], "next": next_url})
    assert r.url == next_url
    assert DefectivePiece.objects.get(tag="DEF-0001").status == PieceStatus.SCRAPPED
    assert StockBalance.objects.get(location=store, item__code="LG78-150-700").qty == before - 1
    data = {"action": "scrap", "reason": "OTHER", "tag": ["DEF-0002"]}
    html = bulk(office_client, data, follow=True).content.decode()
    assert "Write a note when the reason is Other." in html


def test_unsafe_next_is_ignored(office_client, mixed):
    data = {"action": "scrap", "reason": "BURNT", "tag": ["DEF-0001"], "next": "https://evil.example/"}
    assert bulk(office_client, data).url == LIST


def test_nothing_ticked(office_client, mixed):
    html = bulk(office_client, {"action": "scrap", "reason": "BURNT"}, follow=True).content.decode()
    assert "Tick at least one piece." in html


def test_unknown_tag_is_refused(office_client, mixed):
    data = {"action": "scrap", "reason": "BURNT", "tag": ["DEF-0099"]}
    assert "There is no piece tagged DEF-0099." in bulk(office_client, data, follow=True).content.decode()


def test_same_bulk_action_twice_saves_once(office_client, mixed):
    office_client.get(LIST)
    data = {
        "action": "batch",
        "batch": "new",
        "tag": ["DEF-0001"],
        "entry_token": office_client.session["entry_tokens"][-1],
    }
    office_client.post(BULK, data)
    html = office_client.post(BULK, data, follow=True).content.decode()
    assert "This was already saved." in html and ReturnBatch.objects.count() == 1


def test_expired_token_saves_nothing(office_client, mixed):
    r = office_client.post(BULK, {"action": "scrap", "reason": "BURNT", "tag": ["DEF-0001"]}, follow=True)
    assert "expired" in r.content.decode()
    assert DefectivePiece.objects.get(tag="DEF-0001").status == PieceStatus.IN_STORE


def test_bulk_needs_post(office_client):
    assert office_client.get(BULK).status_code == 405


def test_piece_card_offers_scrap_and_scraps(office_client, mixed):
    card = LIST + "DEF-0001/"
    html = office_client.get(card).content.decode()
    assert "Scrap…" in html and f'action="{BULK}"' in html
    # data-once disables the submit button, so the action must not depend on the button's own name/value
    assert '<input type="hidden" name="action" value="scrap">' in html
    r = bulk(
        office_client, {"action": "scrap", "reason": "NOT_WORTH", "tag": "DEF-0001", "next": card}, page=card
    )
    assert r.url == card
    assert "Scrap…" not in office_client.get(card).content.decode()


def test_nav_links_pieces(office_client):
    assert f'href="{LIST}"' in office_client.get("/").content.decode()
