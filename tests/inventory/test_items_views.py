import pytest
from django.utils import timezone

from apps.inventory.models import Company, EntryKind, Item, Location, SpareType
from apps.inventory.services import Line, post_entry, undo_entry
from tests.factories import loc, make_item

pytestmark = pytest.mark.django_db


def form_data(**over):
    data = {
        "code": "MCB 32A DP",
        "spare_type": SpareType.objects.get(name="Accessory").pk,
        "company": Company.objects.get(name="Havells").pk,
        "description": "MCB 32A double pole",
        "cat_ref": "",
        "fitting_type": "",
        "wattage_w": "",
        "current_ma": "",
        "unit": "NOS",
        "reorder_level": "4",
        "aliases": "MCB-32A-DP",
        "is_active": "on",
    }
    data.update(over)
    return data


def qi_data(**over):
    """Quick-create posts prefixed keys and no is_active."""
    data = form_data(**over)
    data.pop("is_active")
    return {f"qi-{k}": v for k, v in data.items()}


def test_items_list_filters(office_client):
    make_item("EIO6006", spare_type="PCB / LED module")
    make_item("LENS", spare_type="Lens")
    html = office_client.get("/items/?q=eio").content.decode()
    assert "EIO6006" in html and "LENS" not in html


def test_create_item(office_client):
    response = office_client.post("/items/new/", form_data())
    item = Item.objects.get(code="MCB 32A DP")
    assert response.status_code == 302 and response.url == f"/items/{item.pk}/"
    assert list(item.aliases.values_list("alias", flat=True)) == ["MCB-32A-DP"]


def test_create_item_lookalike_refused(office_client):
    make_item("LG30-018-054-0300")
    html = office_client.post("/items/new/", form_data(code="lg30-018-054-300", aliases="")).content.decode()
    assert (
        "looks the same as LG30-018-054-0300" in html
        and not Item.objects.filter(code="LG30-018-054-300").exists()
    )


def test_edit_item(office_client):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    response = office_client.post(
        f"/items/{item.pk}/edit/", form_data(code="EIO6006", description="LED module 9W", aliases="")
    )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.description == "LED module 9W"


def test_item_detail_history_and_running_balance(office_client, office_user):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    today = timezone.localdate()
    post_entry(kind=EntryKind.IN, entry_date=today, lines=[Line(item, loc(), 9)], user=office_user)
    post_entry(
        kind=EntryKind.OUT,
        entry_date=today,
        lines=[Line(item, loc(), -2)],
        user=office_user,
        subtype="SITE",
        party="BARC",
    )
    html = office_client.get(f"/items/{item.pk}/").content.decode()
    assert "Movement history" in html and "IN-0001" in html and "OUT-0001" in html
    assert "<b>7</b>" in html  # balance after the OUT


def test_quick_create_json(office_client):
    ok = office_client.post("/items/quick-create/", qi_data(code="LG99-200-700X", aliases="")).json()
    assert ok["ok"] and ok["item"]["code"] == "LG99-200-700X" and ok["item"]["unit"] == "NOS"
    bad = office_client.post("/items/quick-create/", qi_data(code="LG99-200-700X", aliases="")).json()
    assert not bad["ok"] and "already exists" in bad["error"]


def test_check_code_json(office_client):
    make_item("EIO8437", spare_type="PCB / LED module")
    assert office_client.get("/items/check-code/?code=ei08437").json()["status"] == "clash"
    assert office_client.get("/items/check-code/?code=NEW-1").json()["status"] == "ok"


def test_item_detail_undone_row_and_swapped_dates(office_client, office_user):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    today = timezone.localdate()
    entry = post_entry(kind=EntryKind.IN, entry_date=today, lines=[Line(item, loc(), 9)], user=office_user)
    undo_entry(entry=entry, reason="wrong item", user=office_user)
    url = f"/items/{item.pk}/?date_from={today:%Y-%m-%d}&date_to=2020-01-01"
    html = office_client.get(url).content.decode()
    assert 'class="undone"' in html and "Undone" in html
    assert office_client.get(f"/items/{item.pk}/?date_from=junk&date_to=").status_code == 200


def test_item_detail_shows_stock_at_inactive_location(office_client, office_user):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    place = Location.objects.create(name="Old Godown")
    post_entry(
        kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(item, place, 5)], user=office_user
    )
    place.is_active = False
    place.save()
    assert "Old Godown" in office_client.get(f"/items/{item.pk}/").content.decode()


def test_items_list_nul_in_query_is_safe(office_client):
    assert office_client.get("/items/?q=a%00b").status_code == 200


def test_field_errors_show_below_input_groups(office_client):
    html = office_client.post("/items/new/", form_data(wattage_w="-1")).content.decode()
    assert "Ensure this value is greater than or equal to 0." in html


def test_item_with_inactive_master_stays_editable(office_client):
    item = make_item("EIO6006", spare_type="PCB / LED module", company="Havells")
    Company.objects.filter(name="Havells").update(is_active=False)
    response = office_client.post(
        f"/items/{item.pk}/edit/", form_data(code="EIO6006", aliases="", company=item.company_id)
    )
    assert response.status_code == 302


def test_quick_create_is_always_active(office_client):
    ok = office_client.post("/items/quick-create/", qi_data(code="LG99-200-700X", aliases="")).json()
    assert ok["ok"] and Item.objects.get(code="LG99-200-700X").is_active


def test_quick_create_error_names_the_field(office_client):
    bad = office_client.post("/items/quick-create/", qi_data(code="", aliases="")).json()
    assert not bad["ok"] and bad["error"].startswith("Item code:") and "qi-code" not in bad["errors"]
    assert "code" in bad["errors"]


def test_new_item_form_defaults_to_default_company(office_client):
    html = office_client.get("/items/new/").content.decode()
    pk = Company.objects.get(name="Wipro Lighting").pk
    assert f'<option value="{pk}" selected>' in html


def test_cat_ref_datalist_ids_follow_prefix(office_client):
    html = office_client.get("/items/new/").content.decode()
    assert 'list="it-cat-refs"' in html and 'id="it-cat-refs"' in html and 'id="it-code-hint"' in html


@pytest.mark.parametrize(
    "url", ["/items/", "/items/new/", "/items/1/", "/items/1/edit/", "/items/check-code/"]
)
def test_roleless_user_gets_403(url):
    from django.test import Client

    from tests.factories import make_user

    client = Client()
    client.force_login(make_user("nobody"))
    assert client.get(url).status_code == 403


def test_roleless_user_cannot_quick_create():
    from django.test import Client

    from tests.factories import make_user

    client = Client()
    client.force_login(make_user("nobody"))
    assert client.post("/items/quick-create/", qi_data()).status_code == 403


def test_quick_create_get_is_405(office_client):
    assert office_client.get("/items/quick-create/").status_code == 405


def test_untick_active_deactivates(office_client):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    data = form_data(code="EIO6006", aliases="")
    data.pop("is_active")
    assert office_client.post(f"/items/{item.pk}/edit/", data).status_code == 302
    item.refresh_from_db()
    assert not item.is_active


def test_check_code_original_is_ok_for_own_code(office_client):
    make_item("EIO8437", spare_type="PCB / LED module")
    data = office_client.get("/items/check-code/?code=EIO8437&original=EIO8437").json()
    assert data["status"] == "ok"


def test_code_change_refused_when_item_has_lines(office_client, office_user):
    item = make_item("EIO6006", spare_type="PCB / LED module")
    post_entry(
        kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(item, loc(), 3)], user=office_user
    )
    html = office_client.post(
        f"/items/{item.pk}/edit/", form_data(code="EIO6099", aliases="")
    ).content.decode()
    assert "can&#x27;t be changed" in html or "can't be changed" in html
    item.refresh_from_db()
    assert item.code == "EIO6006"
