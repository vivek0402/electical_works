import io

import openpyxl
import pytest
from django.utils import timezone

from apps.inventory import selectors
from apps.inventory.filters import ItemFilters
from apps.inventory.models import EntryKind, Location, ServiceSubtype
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def stocked(office_user):
    """EIO6006: 6 good at Vizag Office (reorder 10) and 4 failed pieces in the Defective store."""
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module")
    post_entry(
        kind=EntryKind.IN, entry_date=TODAY, lines=[Line(a, loc(), 6)], user=office_user, subtype="SUPPLIER"
    )
    post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(a, store(), 4)],
        user=office_user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
    )
    return a


def test_totals_and_low_stock_ignore_the_store(stocked):
    assert selectors.item_totals()[stocked.pk] == 6
    assert selectors.low_stock_count() == 1  # 6 <= 10; the 4 failed pieces don't help
    assert selectors.dashboard_stats(TODAY)["nos_in_stock"] == 6
    shown = {p.name for p, _ in selectors.location_unit_totals()}
    assert "Defective store" not in shown and "Vizag Office" in shown


def test_current_stock_has_a_separate_defective_column(office_client, stocked):
    rows, locations = selectors.current_stock_rows(selectors.StockFilters(None, None, None, "", False))
    assert [r["total"] for r in rows] == [6] and rows[0]["defective"] == 4
    assert all(not p.is_defective_store for p in locations)
    html = office_client.get("/stock/").content.decode()
    # the header says it (grouped "Not counted" over the shaded Defective store column), the total is 6 not 10
    assert ">Not counted<" in html and "Defective store" in html and "Good stock, by location" in html
    assert '6 <span class="cap">NOS</span>' in html and '10 <span class="cap">NOS</span>' not in html


def test_item_with_only_failed_pieces_is_still_listed(office_user):
    b = make_item("LENS")
    post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(b, store(), 2)],
        user=office_user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
    )
    rows, _ = selectors.current_stock_rows(selectors.StockFilters(None, None, None, "", False))
    assert [(r["item"].code, r["total"], r["defective"]) for r in rows] == [("LENS", 0, 2)]


def test_store_is_not_a_current_stock_filter(office_client, stocked):
    html = office_client.get(f"/stock/?location={store().pk}").content.decode()
    assert "EIO6006" in html  # the bad filter is ignored, not applied


def test_entry_forms_never_offer_the_store(office_client):
    for url in ("/stock/in/", "/stock/out/", "/stock/transfer/", "/stock/adjust/"):
        # not as a location option (the menu badge added in Task 16 may name the store elsewhere on the page)
        assert ">Defective store</option>" not in office_client.get(url).content.decode(), url


def test_entry_form_refuses_the_store_if_posted(office_client, stocked):
    office_client.get("/stock/out/")
    token = office_client.session["entry_tokens"][-1]
    html = office_client.post(
        "/stock/out/",
        {
            "entry_date": TODAY.isoformat(),
            "subtype": "SITE",
            "party": "BARC",
            "location": store().pk,
            "line_item": [str(stocked.pk)],
            "line_qty": ["1"],
            "line_batch": [""],
            "line_pkd": [""],
            "entry_token": token,
        },
    ).content.decode()
    assert "Select a valid choice" in html


def test_movements_can_still_filter_by_the_store(office_client, stocked):
    html = office_client.get(f"/movements/?location={store().pk}").content.decode()
    assert f'<option value="{store().pk}" selected>' in html
    assert "IN-0002" in html and "IN-0001" not in html


def test_item_card_shows_the_store_separately(office_client, stocked):
    html = office_client.get(f"/items/{stocked.pk}/").content.decode()
    assert "Total (good stock)" in html and "Defective store: <b>4</b>" in html


def test_store_cannot_be_hidden(admin_client):
    s = store()
    html = admin_client.post(
        "/masters/toggle/", {"kind": "location", "pk": s.pk}, follow=True
    ).content.decode()
    s.refresh_from_db()
    assert s.is_active and "holds the defective pieces" in html


def test_last_good_location_rule_ignores_the_store(admin_client):
    Location.objects.good().exclude(name="TV Shop").update(is_active=False)
    place = loc("TV Shop")
    html = admin_client.post(
        "/masters/toggle/", {"kind": "location", "pk": place.pk}, follow=True
    ).content.decode()
    place.refresh_from_db()
    assert place.is_active and "At least one location must stay active" in html


def test_current_stock_export_lists_the_store_separately(office_client, stocked):
    ws = openpyxl.load_workbook(io.BytesIO(office_client.get("/stock/export/").content)).active
    headers = [c.value for c in ws[6]]
    assert headers[-1] == "Defective store (not counted)" and "Defective store" not in headers[:-1]
    assert ws.cell(7, headers.index("Total") + 1).value == 6 and ws.cell(7, len(headers)).value == 4


def test_default_location_is_never_the_store():
    Location.objects.good().update(is_active=False)
    Location.objects.filter(name="TV Shop").update(is_active=True)
    assert selectors.default_location().name == "TV Shop"
    Location.objects.good().update(is_active=False)
    assert selectors.default_location() is None  # nothing good is active: never fall back to the store


def test_forms_start_on_a_good_location(office_client):
    Location.objects.filter(name="Vizag Office").update(is_active=False)
    for url in ("/stock/in/", "/stock/transfer/"):
        html = office_client.get(url).content.decode()
        assert ">Defective store</option>" not in html, url
        assert f'value="{store().pk}" selected' not in html, url


def test_low_stock_page_and_export_have_no_store_column(office_client, stocked):
    html = office_client.get("/low-stock/").content.decode()
    assert "EIO6006" in html and ">Defective store<" not in html
    ws = openpyxl.load_workbook(io.BytesIO(office_client.get("/low-stock/export/").content)).active
    assert "Defective store" not in [c.value for c in ws[6]]


def test_item_list_in_stock_excludes_the_store(stocked):
    rows = selectors.item_rows(ItemFilters("", None, None, None, "1"))
    assert [r["total"] for r in rows if r["item"] == stocked] == [6]


def test_weekly_in_out_ignores_store_lines(stocked):
    week = selectors.weekly_in_out(TODAY)[-1]
    assert (week["qty_in"], week["qty_out"]) == (6, 0)  # the 4 collected pieces are not counted


def test_export_low_highlight_stays_on_the_status_column(office_client, stocked):
    ws = openpyxl.load_workbook(io.BytesIO(office_client.get("/stock/export/").content)).active
    headers = [c.value for c in ws[6]]
    assert ws.cell(7, headers.index("Status") + 1).value == "LOW"


def test_current_stock_query_count_is_bounded(office_client, stocked, django_assert_max_num_queries):
    for n in range(5):
        make_item(f"BULK{n}")
    with django_assert_max_num_queries(25):
        office_client.get("/stock/")


def test_spare_type_is_in_the_item_cell_not_a_column(office_client, stocked):
    html = office_client.get("/stock/").content.decode()
    assert ">Spare type</a>" not in html.split("<tbody>")[0].split("<thead>")[-1]
    assert "PCB / LED module" in html.split("<tbody>")[1]
