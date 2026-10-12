import io

import openpyxl
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.inventory.models import EntryKind
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db


def sheet(response):
    assert response.status_code == 200
    return openpyxl.load_workbook(io.BytesIO(response.content)).active


@pytest.fixture
def stock(office_user):
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module", description="LED module")
    b = make_item("LG78-150-700", reorder=2)
    post_entry(
        kind=EntryKind.IN,
        entry_date=timezone.localdate(),
        user=office_user,
        subtype="SUPPLIER",
        party="Wipro Lighting",
        lines=[Line(a, loc(), 8), Line(b, loc("TV Shop"), 20)],
    )
    return a, b


def test_current_stock_export_respects_filters(office_client, stock):
    ws = sheet(office_client.get(f"/stock/export/?location={loc('TV Shop').pk}"))
    codes = [ws.cell(r, 1).value for r in range(7, ws.max_row + 1)]
    assert codes == ["LG78-150-700"] and "TV Shop" in ws["A3"].value


def test_movements_export(office_client, stock):
    ws = sheet(office_client.get("/movements/export/"))
    headers = [c.value for c in ws[6]]
    assert headers[:3] == ["Date", "Entry no.", "Type"] and ws.max_row == 8  # 2 lines


def test_items_and_low_stock_exports(office_client, stock):
    assert sheet(office_client.get("/items/export/")).max_row == 8
    low = sheet(office_client.get("/low-stock/export/"))
    assert low.cell(7, 1).value == "EIO6006" and low.max_row == 7


def test_item_history_export(office_client, stock):
    a, _ = stock
    ws = sheet(office_client.get(f"/items/{a.pk}/export/"))
    assert "EIO6006" in ws["A2"].value and ws.cell(7, 2).value == "IN-0001"


def test_item_history_export_swaps_reversed_dates(office_client, stock):
    a, _ = stock
    today = timezone.localdate()
    ws = sheet(office_client.get(f"/items/{a.pk}/export/?date_from={today}&date_to=2000-01-01"))
    assert ws.cell(7, 2).value == "IN-0001"


def test_undone_note_and_flat_query_count(office_client, office_user, stock):
    a, _ = stock
    from apps.inventory.models import StockEntry
    from apps.inventory.services import undo_entry

    undo_entry(entry=StockEntry.objects.get(number="IN-0001"), user=office_user, reason="mistake")
    with CaptureQueriesContext(connection) as ctx:
        ws = sheet(office_client.get("/movements/export/"))
    notes = [ws.cell(r, 16).value for r in range(7, ws.max_row + 1)]
    assert any("Undone by REV-0001" in (n or "") for n in notes)
    assert len(ctx) < 20


@pytest.mark.parametrize(
    "url",
    ["/stock/export/", "/movements/export/", "/items/export/", "/low-stock/export/", "/items/1/export/"],
)
def test_anonymous_is_refused(client, stock, url):
    assert client.get(url).status_code in (302, 403)


def test_item_history_has_undone_note(office_client, office_user, stock):
    from apps.inventory.models import StockEntry
    from apps.inventory.services import undo_entry

    a, _ = stock
    undo_entry(entry=StockEntry.objects.get(number="IN-0001"), user=office_user, reason="mistake")
    ws = sheet(office_client.get(f"/items/{a.pk}/export/"))
    assert [c.value for c in ws[6]][-1] == "Note"
    notes = [ws.cell(r, 13).value for r in range(7, ws.max_row + 1)]
    assert "Undone by REV-0001" in notes


def test_low_stock_keeps_int_format_when_highlighted(office_client, stock):
    ws = sheet(office_client.get("/low-stock/export/"))
    headers = [c.value for c in ws[6]]
    cell = ws.cell(7, headers.index("Total") + 1)
    assert cell.number_format.startswith("#,##0") and cell.fill.fgColor.rgb.endswith("FDE2E2")


def test_blank_int_cell_and_format(office_client, stock):
    ws = sheet(office_client.get("/movements/export/"))
    headers = [c.value for c in ws[6]]
    qty_out = ws.cell(7, headers.index("Qty out") + 1)
    assert qty_out.value is None  # IN lines have no "out" quantity
    assert qty_out.number_format.startswith("#,##0")


def test_export_buttons_keep_filters(office_client, stock):
    html = office_client.get("/stock/?q=eio").content.decode()
    assert 'href="/stock/export/?q=eio"' in html
    a, _ = stock
    html = office_client.get(f"/items/{a.pk}/").content.decode()
    assert f'href="/items/{a.pk}/export/' in html
    assert "/movements/export/" in office_client.get("/movements/").content.decode()
    assert "/low-stock/export/" in office_client.get("/low-stock/").content.decode()
    assert "/items/export/" in office_client.get("/items/").content.decode()
