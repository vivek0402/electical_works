import pytest
from django.utils import timezone

from apps.complaints.models import NotCoveredReason, Status, Visit
from apps.complaints.services import change_status, close_not_covered, set_active
from apps.defectives.models import DefectivePiece
from apps.inventory.models import StockBalance
from tests.factories import give_stock, loc, make_complaint, make_item, make_site, make_tech, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def url(c):
    return f"/complaints/{c.number}/visit/"


def submit(client, c, data):
    """Open the page (which issues its one-time token), then post with that token."""
    client.get(url(c))
    return client.post(url(c), {**data, "entry_token": client.session["entry_tokens"][-1]})


def visit_data(tech, **extra):
    return {
        "visit_date": TODAY.isoformat(),
        "technicians": [tech.pk],
        "work_done": "Changed 1 driver, 2 taken for testing",
        "location": loc().pk,
        "next_status": "MATERIAL_CHECK",
        **extra,
    }


def full_visit(tech, drv):
    return visit_data(
        tech,
        part_item=[str(drv.pk)],
        part_qty=["1"],
        col_item=[str(drv.pk)],
        col_qty=["2"],
        col_batch=["B2405"],
        col_pkd=["2026-03"],
        col_fault=["no output"],
    )


@pytest.fixture
def setup(office_user):
    drv = make_item("LG78-150-700")
    give_stock(drv, 5, office_user)  # IN-0001
    return drv, make_tech("Ramu"), make_complaint(office_user)


def test_visit_page(office_client, setup):
    drv, tech, c = setup
    r = office_client.get(url(c))
    html = r.content.decode()
    assert 'data-lines="part"' in html and 'data-lines="col"' in html and 'data-mode="collect"' in html
    assert 'data-initial="initial-parts"' in html and 'data-initial="initial-collected"' in html
    assert "data-lines-form" in html and "data-form-error" in html
    assert "The first visit also logs" in html and "Material need to check" in html
    assert "Defective store</option>" not in html
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_visit_page_defaults_to_the_complaints_technicians(office_client, office_user):
    ramu, suresh = make_tech("Ramu"), make_tech("Suresh")
    c = make_complaint(office_user, technicians=[suresh])
    html = office_client.get(url(c)).content.decode()
    assert f'<option value="{suresh.pk}" selected>Suresh</option>' in html
    assert f'<option value="{ramu.pk}">Ramu</option>' in html


def test_visit_page_offers_only_active_technicians(office_client, setup):
    drv, tech, c = setup
    hidden = make_tech("Old hand")
    set_active(hidden, active=False)
    assert "Old hand" not in office_client.get(url(c)).content.decode()


def test_visit_page_shows_the_site_phone_formatted(office_client, office_user):
    site = make_site("Andhra University", phone="9876543210", contact_name="Mr Rao")
    c = make_complaint(office_user, site=site)
    html = office_client.get(url(c)).content.decode()
    assert "98765 43210" in html and "Mr Rao" in html


def test_record_a_visit_with_parts_and_two_failed_pieces(office_client, setup):
    drv, tech, c = setup
    r = submit(office_client, c, full_visit(tech, drv))
    assert r.status_code == 302 and r.url == f"/complaints/{c.number}/"
    html = office_client.get(r.url).content.decode()
    assert "Visit VIS-0001 saved. Parts given: OUT-0001. New defective tags: DEF-0001, DEF-0002." in html
    assert "Material need to check" in html and 'href="/defectives/pieces/DEF-0002/"' in html
    assert DefectivePiece.objects.filter(visit__complaint=c).count() == 2
    assert StockBalance.objects.get(item=drv, location=loc()).qty == 4
    assert sum(b.qty for b in StockBalance.objects.filter(item=drv, location=store())) == 2


def test_a_visit_with_no_parts(office_client, setup):
    drv, tech, c = setup
    r = submit(office_client, c, visit_data(tech, next_status="ATTENDED"))
    assert r.status_code == 302
    html = office_client.get(r.url).content.decode()
    assert "Visit VIS-0001 saved." in html and "Parts given:" not in html


def test_the_same_save_twice_saves_once(office_client, setup):
    drv, tech, c = setup
    office_client.get(url(c))
    data = {**full_visit(tech, drv), "entry_token": office_client.session["entry_tokens"][-1]}
    office_client.post(url(c), data)
    r = office_client.post(url(c), data)
    assert r.status_code == 302 and r.url == f"/complaints/{c.number}/"
    assert Visit.objects.count() == 1
    assert "This visit was already saved." in office_client.get(r.url).content.decode()


def test_over_issue_is_refused_and_keeps_the_lines(office_client, setup):
    drv, tech, c = setup
    data = visit_data(
        tech, part_item=[str(drv.pk)], part_qty=["9"], col_item=[str(drv.pk)], col_qty=["1"], col_batch=["B7"]
    )
    html = submit(office_client, c, data).content.decode()
    assert "Parts given: Only 5 NOS of LG78-150-700 at Vizag Office. Nothing was saved." in html
    assert f'"item": "{drv.pk}", "qty": "9"' in html and '"batch": "B7"' in html
    assert "Changed 1 driver, 2 taken for testing" in html  # the header is kept too
    assert not Visit.objects.exists()


def test_a_bad_collected_line_names_its_table(office_client, setup):
    drv, tech, c = setup
    data = visit_data(tech, col_item=[""], col_qty=["2"], col_batch=[""], col_pkd=[""], col_fault=["x"])
    html = submit(office_client, c, data).content.decode()
    assert "Failed parts collected: Line 1: choose an item. Nothing was saved." in html


def test_a_bad_parts_line_names_its_table(office_client, setup):
    drv, tech, c = setup
    data = visit_data(tech, part_item=["", str(drv.pk)], part_qty=["", "0"])
    html = submit(office_client, c, data).content.decode()
    assert "Parts given: Line 2: enter a whole-number quantity of 1 or more. Nothing was saved." in html


def test_too_many_collected_pieces_on_a_line_names_the_line(office_client, setup):
    drv, tech, c = setup
    data = visit_data(tech, col_item=["", str(drv.pk)], col_qty=["", "201"])
    html = submit(office_client, c, data).content.decode()
    assert "Failed parts collected: Line 2: quantity must be between 1 and 200. Nothing was saved." in html
    assert not Visit.objects.exists()


def test_a_visit_needs_a_technician(office_client, setup):
    drv, tech, c = setup
    html = submit(office_client, c, visit_data(tech, technicians=[])).content.decode()
    assert "Choose who attended." in html and not Visit.objects.exists()


def test_a_technician_hidden_after_the_page_opened_is_named(office_client, setup):
    drv, tech, c = setup
    office_client.get(url(c))
    token = office_client.session["entry_tokens"][-1]
    set_active(tech, active=False)
    html = office_client.post(url(c), {**visit_data(tech), "entry_token": token}).content.decode()
    assert "Ramu is hidden." in html and not Visit.objects.exists()


def test_a_status_not_offered_is_refused(office_client, setup):
    drv, tech, c = setup
    html = submit(office_client, c, visit_data(tech, next_status="CLOSED")).content.decode()
    assert "Status after this visit: Choose one of the statuses offered." in html
    assert (
        'role="radiogroup" aria-labelledby="next-status-label" aria-required="true" aria-invalid="true"'
        in html
    )
    assert not Visit.objects.exists()


def test_no_visit_page_for_a_finished_complaint(office_client, office_user, setup):
    drv, tech, c = setup
    close_not_covered(complaint=c, reason=NotCoveredReason.CANCELLED, user=office_user)
    r = office_client.get(url(c))
    assert r.status_code == 302 and r.url == f"/complaints/{c.number}/"
    assert url(c) not in office_client.get(r.url).content.decode()


def test_a_post_to_a_finished_complaint_saves_nothing(office_client, office_user, setup):
    drv, tech, c = setup
    office_client.get(url(c))
    token = office_client.session["entry_tokens"][-1]
    close_not_covered(complaint=c, reason=NotCoveredReason.CANCELLED, user=office_user)
    r = office_client.post(url(c), {**full_visit(tech, drv), "entry_token": token})
    assert r.status_code == 302 and not Visit.objects.exists()


def test_record_visit_button_while_open(office_client, setup):
    drv, tech, c = setup
    html = office_client.get(f"/complaints/{c.number}/").content.decode()
    assert html.count(f'href="{url(c)}"') == 1  # the page action only: the Visits card no longer repeats it


def test_visit_page_highlights_all_complaints_in_the_menu(office_client, setup):
    drv, tech, c = setup
    r = office_client.get(url(c))
    active = [link for _, links in r.context["nav_sections"] for link in links if link["active"]]
    assert [link["name"] for link in active] == ["complaints"]


def test_visit_page_is_office_only(client, setup):
    drv, tech, c = setup
    r = client.get(url(c))
    assert r.status_code in (302, 403)


def two_by_two(tech, drv, other):
    return visit_data(
        tech,
        part_item=[str(drv.pk), str(other.pk)],
        part_qty=["1", "1"],
        col_item=[str(drv.pk), str(other.pk)],
        col_qty=["1", "2"],
        col_batch=["B1", ""],
        col_pkd=["2026-03", ""],
        col_fault=["no output", ""],
    )


def test_visit_page_query_count(office_client, setup, django_assert_max_num_queries):
    drv, tech, c = setup
    with django_assert_max_num_queries(20):  # 16 today
        assert office_client.get(url(c)).status_code == 200


def test_saving_two_parts_and_two_collected_lines_query_count(
    office_client, office_user, setup, django_assert_max_num_queries
):
    drv, tech, c = setup
    other = make_item("LG76-150-700FH")
    give_stock(other, 5, office_user)
    office_client.get(url(c))
    data = {**two_by_two(tech, drv, other), "entry_token": office_client.session["entry_tokens"][-1]}
    with django_assert_max_num_queries(95):  # 83 today
        r = office_client.post(url(c), data)
    assert r.status_code == 302 and DefectivePiece.objects.filter(visit__complaint=c).count() == 3


def test_the_same_part_on_two_lines_is_refused(office_client, setup):
    drv, tech, c = setup
    data = visit_data(tech, part_item=[str(drv.pk), str(drv.pk)], part_qty=["1", "1"])
    html = submit(office_client, c, data).content.decode()
    assert (
        "Parts given: The same item is on two lines. Combine them into one line. Nothing was saved." in html
    )
    assert not Visit.objects.exists()


def test_the_defective_store_is_refused_as_the_parts_location(office_client, setup):
    drv, tech, c = setup
    data = visit_data(tech, location=store().pk, part_item=[str(drv.pk)], part_qty=["1"])
    html = submit(office_client, c, data).content.decode()
    assert "From location: Choose a good-stock location for the parts given." in html
    assert not Visit.objects.exists()


def test_a_later_visit_starts_on_the_current_status(office_client, office_user, setup):
    drv, tech, c = setup
    change_status(complaint=c, to=Status.ATTENDED, user=office_user)
    html = office_client.get(url(c)).content.decode()
    assert 'value="ATTENDED" class="form-selectgroup-input" checked' in html
    assert "The first visit also logs" not in html
