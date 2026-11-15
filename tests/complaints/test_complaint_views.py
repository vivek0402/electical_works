import pytest
from django.utils import timezone

from apps.complaints.models import Complaint, Status
from apps.complaints.phones import format_phone
from apps.complaints.services import change_status, close_not_covered, record_visit, set_active
from apps.complaints.templatetags.complaint_tags import phone_display
from apps.inventory.models import Company, EntryKind, StockEntry
from tests.factories import give_stock, loc, make_complaint, make_item, make_site, make_tech

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()
NEW = "/complaints/new/"


def submit(client, data):
    client.get(NEW)
    return client.post(NEW, {**data, "entry_token": client.session["entry_tokens"][-1]})


def complaint_data(site, **extra):
    return {
        "site": site.pk,
        "contact_name": "",
        "phone": "",
        "company": Company.objects.get(name="Havells").pk,
        "company_ref": "HV-C-78020",
        "reported_on": TODAY.isoformat(),
        "qty_affected": "4",
        "fault": "LED battens failed in canteen",
        "priority": "HIGH",
        **extra,
    }


def detail_post(client, c, action, data):
    """POST from the complaint page, with the page's one-time token (as the page's modals do)."""
    page = f"/complaints/{c.number}/"
    client.get(page)
    token = client.session["entry_token_pages"][page]
    return client.post(f"{page}{action}/", {**data, "entry_token": token}, follow=True)


def test_new_complaint_page(office_client):
    make_site(contact_name="Murthy")
    make_tech("Ramu")
    make_tech("Hidden tech", is_active=False)
    html = office_client.get(NEW).content.decode()
    assert 'id="sites-data"' in html and "Murthy" in html and 'id="new-site-btn"' in html
    assert "selected>Wipro Lighting</option>" not in html  # no preselected company
    assert "Choose…" in html
    assert 'id="id_ns-phone"' in html and 'id="id_phone"' in html  # modal fields don't clash
    assert ">Ramu</option>" in html and "Hidden tech" not in html  # only active technicians offered


def test_file_a_complaint(office_client):
    site = make_site(contact_name="Murthy", phone="9908127999")
    r = submit(office_client, complaint_data(site, technicians=[make_tech().pk]))
    c = Complaint.objects.get()
    assert r.url == f"/complaints/{c.number}/"
    assert (c.contact_name, c.phone, c.priority, c.company.name) == (
        "Murthy",
        "9908127999",
        "HIGH",
        "Havells",
    )
    assert [t.name for t in c.technicians.all()] == ["Ramu"]
    html = office_client.get(r.url).content.decode()
    assert (
        "Complaint CMP-0001 filed for BARC." in html and "Not attended" in html and "Complaint filed" in html
    )


def test_contact_and_landline_override(office_client):
    site = make_site(contact_name="Murthy", phone="9908127999")
    submit(office_client, complaint_data(site, contact_name="Estate office", phone="0891-2345678"))
    c = Complaint.objects.get()
    assert (c.contact_name, c.phone) == ("Estate office", "08912345678")


def test_bad_phone_is_refused(office_client):
    html = submit(office_client, complaint_data(make_site(), phone="12345")).content.decode()
    assert "Phone: Phone must be a 10-digit mobile number or an STD landline" in html
    assert not Complaint.objects.exists()


def test_errors_keep_the_form(office_client):
    html = submit(office_client, complaint_data(make_site(), fault="")).content.decode()
    assert "Fault: Describe the fault." in html and not Complaint.objects.exists()
    assert 'value="HV-C-78020"' in html


def test_stale_page_with_a_hidden_site_shows_the_service_error(office_client):
    site = make_site()
    set_active(site, active=False)
    html = submit(office_client, complaint_data(site)).content.decode()
    assert "BARC, Visakhapatnam is hidden. Show it again in Sites, or choose another." in html
    tech = make_tech()
    set_active(tech, active=False)
    html = submit(office_client, complaint_data(make_site("NTPC"), technicians=[tech.pk])).content.decode()
    assert "Ramu is hidden. Show it again in Technicians, or choose another." in html
    assert not Complaint.objects.exists()


def test_resubmit_does_not_file_twice(office_client):
    office_client.get(NEW)
    data = {**complaint_data(make_site()), "entry_token": office_client.session["entry_tokens"][-1]}
    first, again = office_client.post(NEW, data), office_client.post(NEW, data)
    assert again.url == first.url and Complaint.objects.count() == 1


def test_post_without_a_token_saves_nothing(office_client):
    html = office_client.post(NEW, complaint_data(make_site())).content.decode()
    assert "This form had expired" in html and not Complaint.objects.exists()


def test_site_quick_create(office_client):
    data = {
        "ns-name": "Andhra University",
        "ns-city": "Visakhapatnam",
        "ns-contact_name": "Estate office",
        "ns-phone": "0891-2345678",
    }
    made = office_client.post("/sites/quick-create/", data).json()
    assert made["ok"] and (made["site"]["name"], made["site"]["contact"]) == (
        "Andhra University",
        "Estate office",
    )
    assert made["site"]["phone"] == "08912345678"
    dup = office_client.post("/sites/quick-create/", data).json()
    assert not dup["ok"] and "already exists" in dup["error"]
    bad = office_client.post("/sites/quick-create/", {"ns-name": "", "ns-city": "X"}).json()
    assert bad == {"ok": False, "error": "Site name: Enter the site name."}
    phone = office_client.post(
        "/sites/quick-create/", {"ns-name": "Y", "ns-city": "X", "ns-phone": "1"}
    ).json()
    assert not phone["ok"] and phone["error"].startswith("Phone: Phone must be")


def test_detail_shows_details_timeline_and_actions(office_client, office_user):
    c = make_complaint(office_user, company_ref="WL/AP/24871")
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, note="Called the site")
    html = office_client.get(f"/complaints/{c.number}/").content.decode()
    assert "WL/AP/24871" in html and "Not attended → Attended" in html and "Called the site" in html
    assert "Change status" in html and "Close as Not covered" in html
    assert "Awaiting material <b>0</b> days" in html
    assert "Record visit" in html  # Task 13 builds the page; until then the button is disabled
    # Only the allowed moves are offered (Not covered is its own action).
    for value in ("MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED"):
        assert f'name="to" value="{value}"' in html
    assert 'name="to" value="CLOSED"' not in html and 'name="to" value="NOT_COVERED"' not in html


def test_change_status_from_the_page(office_client, office_user):
    c = make_complaint(office_user)
    html = detail_post(office_client, c, "status", {"to": "ATTENDED", "note": "Called"}).content.decode()
    assert "CMP-0001: Not attended → Attended." in html
    html = detail_post(office_client, c, "status", {"to": "CLOSED"}).content.decode()
    assert "A complaint that is Attended" in html
    c.refresh_from_db()
    assert c.status == Status.ATTENDED


def test_status_post_needs_the_page_token(office_client, office_user):
    c = make_complaint(office_user)
    html = office_client.post(f"/complaints/{c.number}/status/", {"to": "ATTENDED"}, follow=True)
    assert "This form had expired" in html.content.decode()
    c.refresh_from_db()
    assert c.status == Status.NOT_ATTENDED


def test_not_covered_from_the_page(office_client, office_user):
    c = make_complaint(office_user)
    html = detail_post(office_client, c, "not-covered", {"reason": "OTHER", "note": ""}).content.decode()
    assert "Write a note when the reason is Other." in html
    html = detail_post(
        office_client, c, "not-covered", {"reason": "OUT_OF_WARRANTY", "note": ""}
    ).content.decode()
    assert "CMP-0001 closed as Not covered (Out of warranty)." in html
    c.refresh_from_db()
    assert c.status == Status.NOT_COVERED
    assert "Change status" not in html and "Not covered: <b>Out of warranty</b>" in html


def test_reopen_is_admin_only(office_client, admin_client, office_user):
    c = make_complaint(office_user)
    for to in (Status.ATTENDED, Status.RESOLVED, Status.CLOSED):
        change_status(complaint=c, to=to, user=office_user)
    detail = f"/complaints/{c.number}/"
    html = office_client.get(detail).content.decode()
    assert "Only Admin can reopen it" in html and "Reopen (move to Attended)" not in html
    html = detail_post(office_client, c, "status", {"to": "ATTENDED", "note": "x"}).content.decode()
    assert "Only Admin can reopen it." in html
    assert "Reopen (move to Attended)" in admin_client.get(detail).content.decode()
    html = detail_post(admin_client, c, "status", {"to": "ATTENDED", "note": ""}).content.decode()
    assert "Write why the complaint is being reopened." in html
    detail_post(admin_client, c, "status", {"to": "ATTENDED", "note": "Failed again"})
    c.refresh_from_db()
    assert c.status == Status.ATTENDED and c.events.last().note == "Reopened: Failed again"


def visit_with_parts(user, c):
    item = make_item("LG78-150-700")
    give_stock(item, 5, user)
    return record_visit(
        complaint=c,
        visit_date=TODAY,
        technicians=[make_tech()],
        work_done="Replaced a driver",
        next_status=Status.ATTENDED,
        user=user,
        location=loc(),
        parts=[(item, 2)],
    )


def test_undo_parts_given(office_client, office_user):
    c = make_complaint(office_user)
    v = visit_with_parts(office_user, c)
    page = f"/complaints/{c.number}/"
    html = office_client.get(page).content.decode()
    assert "Undo parts given" in html and f'href="/entries/{v.out_entry.number}/"' in html
    html = detail_post(office_client, c, f"visits/{v.number}/undo-parts", {"reason": ""}).content.decode()
    assert "Write why the parts given are being undone." in html
    html = detail_post(
        office_client, c, f"visits/{v.number}/undo-parts", {"reason": "Wrong driver"}
    ).content.decode()
    rev = StockEntry.objects.get(kind=EntryKind.REV)
    assert f"Parts given on {v.number} undone. {rev.number} posted." in html
    assert f'href="/entries/{rev.number}/"' in html and "Undo parts given" not in html
    assert c.events.count() == 2  # filed + attended: the undo is a REV entry, not a status event
    entry_html = office_client.get(f"/entries/{rev.number}/").content.decode()
    assert f'Undo of the parts given on <span class="code">{v.number}</span>' in entry_html
    assert f'href="/complaints/{c.number}/"' in entry_html


def test_no_undo_for_a_visit_without_parts(office_client, office_user):
    c = make_complaint(office_user)
    record_visit(
        complaint=c,
        visit_date=TODAY,
        technicians=[make_tech()],
        work_done="Checked wiring",
        next_status=Status.ATTENDED,
        user=office_user,
    )
    html = office_client.get(f"/complaints/{c.number}/").content.decode()
    assert "Checked wiring" in html and "Undo parts given" not in html


def test_entry_page_links_its_complaint(office_client, office_user):
    c = make_complaint(office_user)
    v = visit_with_parts(office_user, c)
    html = office_client.get(f"/entries/{v.out_entry.number}/").content.decode()
    assert "belongs to a visit on complaint" in html and f'href="/complaints/{c.number}/"' in html


def test_piece_source_links_its_complaint(office_client, office_user):
    item, c = make_item("LG78-150-700"), make_complaint(office_user)
    record_visit(
        complaint=c,
        visit_date=TODAY,
        technicians=[make_tech()],
        work_done="Removed a driver",
        next_status=Status.ATTENDED,
        user=office_user,
        collected=[(item, 1, "", None, "no output")],
    )
    html = office_client.get("/defectives/pieces/DEF-0001/").content.decode()
    assert f'href="/complaints/{c.number}/"' in html and "BARC" in html
    assert (
        'href="/defectives/pieces/DEF-0001/"'
        in office_client.get(f"/complaints/{c.number}/").content.decode()
    )


def test_menu_links_new_complaint(office_client):
    # the Home hero and the Complaints section hero both offer it
    assert 'href="/complaints/new/"' in office_client.get("/").content.decode()
    assert 'href="/complaints/new/"' in office_client.get("/complaints/").content.decode()


def test_unknown_complaint_is_404(office_client):
    assert office_client.get("/complaints/CMP-9999/").status_code == 404


def page_token_for(client, c):
    page = f"/complaints/{c.number}/"
    client.get(page)
    return client.session["entry_token_pages"][page]


def test_stale_page_refusal_is_visible(office_client, office_user):
    """Another tab closed the complaint, so the status dialog isn't drawn any more: the refusal shows at the
    top of the page instead of inside a dialog that isn't there."""
    c = make_complaint(office_user)
    token = page_token_for(office_client, c)
    close_not_covered(complaint=c, reason="CANCELLED", user=office_user)  # the other tab
    r = office_client.post(f"/complaints/{c.number}/status/", {"to": "ATTENDED", "entry_token": token})
    html = r.content.decode()
    assert 'id="status-modal"' not in html
    assert "A complaint that is Not covered can&#x27;t move to Attended. Nothing was saved." in html
    assert c.events.count() == 2


def test_undo_url_refuses_a_visit_of_another_complaint(office_client, office_user):
    c = make_complaint(office_user)
    v = visit_with_parts(office_user, c)
    other = make_complaint(office_user, site=make_site("NTPC"))
    token = page_token_for(office_client, other)
    r = office_client.post(
        f"/complaints/{other.number}/visits/{v.number}/undo-parts/", {"reason": "x", "entry_token": token}
    )
    assert r.status_code == 404 and not StockEntry.objects.filter(kind=EntryKind.REV).exists()


def test_double_submitted_status_change_logs_once(office_client, office_user):
    c = make_complaint(office_user)
    data = {"to": "ATTENDED", "note": "Called", "entry_token": page_token_for(office_client, c)}
    url = f"/complaints/{c.number}/status/"
    office_client.post(url, data)
    html = office_client.post(url, data, follow=True).content.decode()
    assert "This was already saved." in html
    assert c.events.filter(to_status=Status.ATTENDED).count() == 1


def test_refused_post_reopens_its_own_dialog_with_the_note(office_client, office_user):
    c = make_complaint(office_user)
    change_status(complaint=c, to=Status.ATTENDED, user=office_user)
    html = detail_post(office_client, c, "status", {"to": "CLOSED", "note": "Typed note 42"}).content.decode()
    status = html[html.index('id="status-modal"') : html.index('id="nc-modal"')]
    nc = html[html.index('id="nc-modal"') :]
    assert "data-show-on-load" in status and "Typed note 42</textarea>" in status
    assert "data-show-on-load" not in nc and "Typed note 42" not in nc
    html = detail_post(office_client, c, "not-covered", {"reason": "OTHER", "note": ""}).content.decode()
    nc = html[html.index('id="nc-modal"') :]
    assert "data-show-on-load" in nc and 'value="OTHER" selected' in nc
    assert "data-show-on-load" not in html[html.index('id="status-modal"') : html.index('id="nc-modal"')]


def test_visits_show_as_cards_on_phones(office_client, office_user):
    c = make_complaint(office_user)
    v = visit_with_parts(office_user, c)
    html = office_client.get(f"/complaints/{c.number}/").content.decode()
    assert (
        'class="table-responsive d-none d-md-block"' in html and 'class="list-group-item visit-card"' in html
    )
    assert html.count(f'data-bs-target="#undo-{v.number}"') == 2  # the table row and the phone card
    assert "LG78-150-700</span> × 2" in html  # the OUT line's quantity without its minus sign


def test_phone_display():
    assert format_phone("9876543210") == "98765 43210"
    assert format_phone("08912345678") == "0891-2345678"
    assert format_phone("01123456789") == "011-23456789"
    assert format_phone("04023456789") == "040-23456789"
    assert format_phone("") == "" and format_phone("12") == "12"
    assert phone_display("08912345678") == "0891-2345678"


def test_phones_are_shown_formatted(office_client, office_user):
    c = make_complaint(office_user, site=make_site(phone="9876543210"))
    html = office_client.get(f"/complaints/{c.number}/").content.decode()
    assert '<a href="tel:9876543210">98765 43210</a>' in html
    made = office_client.post(
        "/sites/quick-create/", {"ns-name": "AU", "ns-city": "Vizag", "ns-phone": "08912345678"}
    )
    assert made.json()["site"]["phone_display"] == "0891-2345678"
