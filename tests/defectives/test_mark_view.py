import pytest
from django.utils import timezone

from apps.defectives.models import DefectivePiece
from apps.inventory.models import StockEntry
from tests.factories import give_stock, loc, make_item, make_user, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate().isoformat()
URL = "/defectives/mark/"


def submit(client, data):
    """Open the page (which issues a one-time token), then post with that token."""
    client.get(URL)
    return client.post(URL, {**data, "entry_token": client.session["entry_tokens"][-1]})


def mark_data(item, qty, fault="Dead on arrival"):
    return {
        "entry_date": TODAY,
        "location": loc().pk,
        "line_item": [str(item.pk)],
        "line_qty": [str(qty)],
        "line_fault": [fault],
    }


@pytest.fixture
def drv(office_user):
    item = make_item("LG78-150-700")
    give_stock(item, 5, office_user)
    return item


def test_page_offers_good_locations_and_a_mark_editor(office_client, drv):
    html = office_client.get(URL).content.decode()
    assert "Mark defective from stock" in html and "Defective store</option>" not in html
    assert 'id="items-data"' in html and 'id="balances-data"' in html and 'id="initial-lines"' in html
    assert "data-lines-form" in html and "data-form-error" in html
    assert (
        'data-lines="line"' in html and 'data-mode="mark"' in html and 'data-initial="initial-lines"' in html
    )


def test_mark_saves_one_transfer_and_tags_pieces(office_client, drv):
    r = submit(office_client, mark_data(drv, 2))
    entry = StockEntry.objects.get(subtype="MARK_DEFECTIVE")
    assert r.status_code == 302 and r.url == f"/entries/{entry.number}/"
    assert list(DefectivePiece.objects.order_by("tag").values_list("tag", flat=True)) == [
        "DEF-0001",
        "DEF-0002",
    ]
    assert "New defective tags: DEF-0001, DEF-0002." in office_client.get(r.url).content.decode()


def test_mark_needs_a_fault(office_client, drv):
    html = submit(office_client, mark_data(drv, 1, fault="")).content.decode()
    assert "Line 1: write what is wrong with the piece. Nothing was saved." in html
    assert not DefectivePiece.objects.exists()


def test_mark_over_quantity_is_refused(office_client, drv):
    html = submit(office_client, mark_data(drv, 9)).content.decode()
    assert "Only 5 NOS of LG78-150-700 at Vizag Office. Nothing was saved." in html
    assert not StockEntry.objects.filter(subtype="MARK_DEFECTIVE").exists()


def test_mark_more_than_the_piece_limit_is_refused(office_client, drv):
    html = submit(office_client, mark_data(drv, 201)).content.decode()
    assert "Line 1: quantity must be between 1 and 200. Nothing was saved." in html


def test_the_defective_store_is_refused_as_the_from_location(office_client, drv):
    data = {**mark_data(drv, 1), "location": store().pk}
    html = submit(office_client, data).content.decode()
    assert "Found at location: Select a valid choice." in html
    assert not DefectivePiece.objects.exists()


def test_expired_token_saves_nothing(office_client, drv):
    office_client.get(URL)
    html = office_client.post(URL, {**mark_data(drv, 1), "entry_token": "bogus"}).content.decode()
    assert "This form had expired" in html and not DefectivePiece.objects.exists()


def test_resubmitting_does_not_mark_twice(office_client, drv):
    office_client.get(URL)
    data = {**mark_data(drv, 1), "entry_token": office_client.session["entry_tokens"][-1]}
    first = office_client.post(URL, data)
    again = office_client.post(URL, data)
    assert again.url == first.url and DefectivePiece.objects.count() == 1


def test_item_param_prefills_a_line(office_client, drv):
    html = office_client.get(f"{URL}?item={drv.pk}").content.decode()
    assert f'"item": "{drv.pk}"' in html


def test_nav_links_mark_defective(office_client):
    assert 'href="/defectives/mark/"' in office_client.get("/").content.decode()


def test_a_user_without_a_role_cannot_open_the_page(client):
    client.force_login(make_user("norole_t"))
    assert client.get(URL).status_code == 403


def test_same_item_on_two_lines_with_different_faults(office_client, drv):
    data = {**mark_data(drv, 2, "no output"), "line_item": [str(drv.pk)] * 2, "line_qty": ["2", "1"]}
    data["line_fault"] = ["no output", "burnt"]
    r = submit(office_client, data)
    assert r.status_code == 302
    entry = StockEntry.objects.get(subtype="MARK_DEFECTIVE")
    assert entry.lines.get(item=drv, location=store()).qty == 3
    assert list(DefectivePiece.objects.order_by("tag").values_list("fault", flat=True)) == [
        "no output",
        "no output",
        "burnt",
    ]


def blank_row_between(item, qty, fault):
    """Line 1 is fine, line 2 is left blank, line 3 is the one under test."""
    return {
        "entry_date": TODAY,
        "location": loc().pk,
        "line_item": [str(item.pk), "", str(item.pk)],
        "line_qty": ["1", "", str(qty)],
        "line_fault": ["burnt", "", fault],
    }


@pytest.mark.parametrize(
    "qty,fault,message",
    [
        (1, "", "Line 3: write what is wrong with the piece."),
        (201, "dead", "Line 3: quantity must be between 1 and 200."),
        (1, "x" * 201, "Line 3: keep the fault to 200 characters or less."),
    ],
)
def test_errors_name_the_line_on_screen_past_a_blank_row(office_client, drv, qty, fault, message):
    html = submit(office_client, blank_row_between(drv, qty, fault)).content.decode()
    assert f"{message} Nothing was saved." in html
    assert not DefectivePiece.objects.exists()


def test_mark_back_then_different_lines_with_a_spent_token_saves_nothing(office_client, drv):
    office_client.get(URL)
    t = office_client.session["entry_tokens"][-1]
    office_client.post(URL, {**mark_data(drv, 1), "entry_token": t})
    html = office_client.post(URL, {**mark_data(drv, 2), "entry_token": t}).content.decode()
    assert "This form had expired" in html and DefectivePiece.objects.count() == 1
