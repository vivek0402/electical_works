from datetime import timedelta

import pytest
from django.utils import timezone

from apps.complaints import selectors
from apps.complaints.models import Site, Status, Technician
from apps.complaints.services import close_not_covered, record_visit
from tests.factories import make_complaint, make_site, make_tech

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def post_from(client, page, action, data=None, **kw):
    """POST to `action` with the one-time token of the page `page` (as that page's forms do)."""
    client.get(page)
    token = client.session["entry_token_pages"][page]
    return client.post(action, {**(data or {}), "entry_token": token}, **kw)


def test_sites_list_and_search(office_client, office_user):
    make_complaint(office_user)  # at BARC, Visakhapatnam
    make_site("NSL Textiles", "Guntur", contact_name="Jagadeesh", phone="9849669594")
    html = office_client.get("/sites/").content.decode()
    assert "BARC" in html and "NSL Textiles" in html and 'id="site-modal"' in html
    assert 'href="tel:9849669594"' in html and "98496 69594" in html  # raw digits link, spaced text
    html = office_client.get("/sites/?q=jagadeesh").content.decode()
    assert "NSL Textiles" in html and "BARC" not in html
    assert "NSL Textiles" in office_client.get("/sites/?q=98496 69594").content.decode()
    assert "BARC" not in office_client.get("/sites/?city=guntur").content.decode()  # city matches any case


def test_site_rows_count_open_complaints(office_user):
    make_complaint(office_user)
    done = make_complaint(office_user, reported_on=TODAY - timedelta(days=3))
    close_not_covered(complaint=done, reason="CANCELLED", user=office_user)
    [row] = selectors.site_rows()
    assert (row.n_open, row.n_all, row.last) == (1, 2, TODAY)


def test_site_card_shows_its_complaint_history(office_client, office_user):
    c = make_complaint(office_user)
    other = make_complaint(office_user, site=make_site("Other Site", "Guntur"), fault="Different fault")
    html = office_client.get(f"/sites/{c.site.pk}/").content.decode()
    assert f'href="/complaints/{c.number}/"' in html and f'href="/complaints/new/?site={c.site.pk}"' in html
    assert other.number not in html
    assert "Hide" not in html  # Office has no Hide button


def test_edit_a_site_with_a_landline(office_client):
    site = make_site(phone="08912345678")
    html = office_client.get(f"/sites/{site.pk}/").content.decode()
    assert 'href="tel:08912345678"' in html and "0891-2345678" in html
    page = f"/sites/{site.pk}/edit/"
    data = {
        "name": "BARC",
        "city": "Visakhapatnam",
        "contact_name": "Chenna",
        "phone": "0891-2345678",
        "address": "",
    }
    r = post_from(office_client, page, page, data)
    assert r.url == f"/sites/{site.pk}/"
    site.refresh_from_db()
    assert (site.contact_name, site.phone) == ("Chenna", "08912345678")


def test_edit_site_refuses_a_bad_phone_and_a_duplicate(office_client):
    site = make_site()
    make_site("NSL Textiles", "Guntur")
    page = f"/sites/{site.pk}/edit/"
    data = {"name": "BARC", "city": "Visakhapatnam", "contact_name": "", "phone": "123", "address": ""}
    html = post_from(office_client, page, page, data).content.decode()
    assert "Phone must be a 10-digit mobile number or an STD landline like 0891-2345678." in html
    clash = {**data, "phone": "", "name": "nsl textiles", "city": "GUNTUR"}
    html = post_from(office_client, page, page, clash).content.decode()
    assert "already exists" in html
    site.refresh_from_db()
    assert site.name == "BARC" and Site.objects.count() == 2


def test_edit_without_the_token_saves_nothing(office_client):
    site = make_site()
    data = {"name": "Renamed", "city": "Visakhapatnam", "contact_name": "", "phone": "", "address": ""}
    html = office_client.post(f"/sites/{site.pk}/edit/", data).content.decode()
    assert "had expired" in html
    site.refresh_from_db()
    assert site.name == "BARC"


def test_only_admin_hides_and_shows_sites(office_client, admin_client):
    site = make_site()
    page = f"/sites/{site.pk}/"
    assert "Hide" not in office_client.get(page).content.decode()
    assert post_from(office_client, page, f"{page}toggle/", {"active": "0"}).status_code == 403
    site.refresh_from_db()
    assert site.is_active
    assert "Hide" in admin_client.get(page).content.decode()
    post_from(admin_client, page, f"{page}toggle/", {"active": "0"})
    site.refresh_from_db()
    assert not site.is_active
    assert "Show" in admin_client.get(page).content.decode()
    post_from(admin_client, page, f"{page}toggle/", {"active": "1"})
    site.refresh_from_db()
    assert site.is_active


def test_toggle_needs_post_and_a_token(admin_client):
    site = make_site()
    assert admin_client.get(f"/sites/{site.pk}/toggle/").status_code == 405
    admin_client.post(f"/sites/{site.pk}/toggle/")
    site.refresh_from_db()
    assert site.is_active  # no token, nothing saved


def test_only_admin_hides_technicians_and_hidden_are_not_offered(office_client, admin_client):
    site, tech = make_site(), make_tech()
    assert (
        post_from(
            office_client, "/technicians/", f"/technicians/{tech.pk}/toggle/", {"active": "0"}
        ).status_code
        == 403
    )
    tech.refresh_from_db()
    assert tech.is_active
    post_from(admin_client, "/technicians/", f"/technicians/{tech.pk}/toggle/", {"active": "0"})
    tech.refresh_from_db()
    assert not tech.is_active
    post_from(admin_client, f"/sites/{site.pk}/", f"/sites/{site.pk}/toggle/", {"active": "0"})
    html = office_client.get("/complaints/new/").content.decode()
    assert "BARC" not in html and "Ramu" not in html  # hidden ones are not offered


def test_technicians_page_hide_buttons_are_admin_only(office_client, admin_client):
    make_tech()
    assert "/toggle/" not in office_client.get("/technicians/").content.decode()
    assert "/toggle/" in admin_client.get("/technicians/").content.decode()


def test_add_and_edit_technicians(office_client):
    html = post_from(
        office_client,
        "/technicians/",
        "/technicians/",
        {"name": "Suresh", "phone": "98765 43210"},
        follow=True,
    ).content.decode()
    assert "Technician Suresh added." in html and "98765 43210" in html
    html = post_from(office_client, "/technicians/", "/technicians/", {"name": "suresh"}).content.decode()
    assert "Suresh is already in the list." in html
    t = Technician.objects.get(name="Suresh")
    assert t.phone == "9876543210"
    page = f"/technicians/{t.pk}/edit/"
    post_from(office_client, page, page, {"name": "Suresh K", "phone": ""})
    t.refresh_from_db()
    assert (t.name, t.phone) == ("Suresh K", "")


def test_technician_phone_is_mobile_only(office_client):
    html = post_from(
        office_client, "/technicians/", "/technicians/", {"name": "Landline", "phone": "0891-2345678"}
    ).content.decode()
    assert "Phone must be a 10-digit mobile number." in html
    assert not Technician.objects.filter(name="Landline").exists()


def test_technician_rows_and_links(office_client, office_user):
    ramu = make_tech("Ramu")
    a = make_complaint(office_user, reported_on=TODAY - timedelta(days=40), technicians=[ramu])
    b = make_complaint(office_user, reported_on=TODAY - timedelta(days=40), technicians=[ramu])
    for c, day in ((a, TODAY - timedelta(days=31)), (b, TODAY)):  # the 31-day-old visit is outside the window
        record_visit(
            complaint=c,
            visit_date=day,
            technicians=[ramu],
            work_done="Checked",
            next_status=Status.ATTENDED,
            user=office_user,
        )
    [row] = selectors.technician_rows(TODAY)
    assert (row.n_open, row.n_visits, row.last) == (2, 1, TODAY)
    assert (
        f'href="/complaints/list/?technician={ramu.pk}"'
        in office_client.get("/technicians/").content.decode()
    )


def test_complaint_pages_link_the_site(office_client, office_user):
    c = make_complaint(office_user)
    assert f'href="/sites/{c.site.pk}/"' in office_client.get(f"/complaints/{c.number}/").content.decode()
    assert f'href="/sites/{c.site.pk}/"' in office_client.get("/complaints/list/").content.decode()
    assert f'href="/sites/{c.site.pk}/"' in office_client.get("/complaints/").content.decode()


def test_nav_links_sites_and_technicians(office_client):
    html = office_client.get("/").content.decode()
    assert 'href="/sites/"' in html and 'href="/technicians/"' in html


def test_toggle_states_the_target_so_a_stale_page_cannot_flip_it_back(admin_client):
    site = make_site()
    page = f"/sites/{site.pk}/"
    post_from(admin_client, page, f"{page}toggle/", {"active": "0"})
    site.refresh_from_db()
    assert not site.is_active
    post_from(admin_client, page, f"{page}toggle/", {"active": "0"})  # a stale Hide page posts Hide again
    site.refresh_from_db()
    assert not site.is_active
    post_from(admin_client, page, f"{page}toggle/", {"active": "1"})
    site.refresh_from_db()
    assert site.is_active
    post_from(admin_client, page, f"{page}toggle/", {})  # no target state: nothing changes
    post_from(admin_client, page, f"{page}toggle/", {"active": "maybe"})
    site.refresh_from_db()
    assert site.is_active
    assert 'name="active" value="0"' in admin_client.get(page).content.decode()


def test_a_site_with_open_complaints_cannot_be_hidden(admin_client, office_user):
    c = make_complaint(office_user)
    page = f"/sites/{c.site.pk}/"
    html = post_from(admin_client, page, f"{page}toggle/", {"active": "0"}, follow=True).content.decode()
    assert "BARC, Visakhapatnam has 1 open complaint(s). Close them before hiding the site." in html
    c.site.refresh_from_db()
    assert c.site.is_active
    close_not_covered(complaint=c, reason="CANCELLED", user=office_user)
    post_from(admin_client, page, f"{page}toggle/", {"active": "0"})
    c.site.refresh_from_db()
    assert not c.site.is_active


def test_service_refuses_hiding_a_site_with_open_complaints(office_user):
    from apps.complaints.services import ComplaintError, set_active

    c = make_complaint(office_user)
    with pytest.raises(
        ComplaintError, match=r"has 1 open complaint\(s\)\. Close them before hiding the site"
    ):
        set_active(c.site, active=False)


def test_a_technician_can_be_hidden_with_a_note_about_open_complaints(admin_client, office_user):
    ramu = make_tech("Ramu")
    make_complaint(office_user, technicians=[ramu])
    html = post_from(
        admin_client, "/technicians/", f"/technicians/{ramu.pk}/toggle/", {"active": "0"}, follow=True
    ).content.decode()
    assert "Ramu is hidden. Still assigned to 1 open complaint(s)." in html
    ramu.refresh_from_db()
    assert not ramu.is_active


def test_hidden_site_card_has_no_new_complaint_button(admin_client):
    site = make_site(is_active=False)
    html = admin_client.get(f"/sites/{site.pk}/").content.decode()
    assert "New complaint for this site" not in html and "Show" in html


def test_technicians_page_accessibility(admin_client):
    t = make_tech("Ramu")
    html = admin_client.get("/technicians/").content.decode()
    assert 'aria-label="Edit Ramu"' in html and 'aria-label="Hide Ramu"' in html
    assert 'avatar avatar-xs bg-secondary-lt me-2" aria-hidden="true"' in html
    assert "order-first" in html and t.pk
    err = post_from(admin_client, "/technicians/", "/technicians/", {"name": ""}).content.decode()
    assert 'id="form-error" tabindex="-1"' in err
