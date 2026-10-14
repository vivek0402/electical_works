import io
import re
from datetime import timedelta

import openpyxl
import pytest
from django.http import QueryDict
from django.utils import timezone

from apps.complaints import selectors
from apps.complaints.filters import complaint_filters
from apps.complaints.models import NotCoveredReason, Status
from apps.complaints.services import change_status, close_not_covered
from apps.inventory.models import Company
from tests.factories import make_complaint, make_site, make_tech

pytestmark = pytest.mark.django_db
LIST = "/complaints/list/"
MAX_DASHBOARD, MAX_LIST, MAX_EXPORT = 12, 13, 7  # measured + 1; pages +2 for the two menu badges
LINK = r'href="/complaints/(CMP-\d{4})/"'


def today():
    return timezone.localdate()


def ago(days):
    return today() - timedelta(days=days)


def sheet(response):
    assert response.status_code == 200
    return openpyxl.load_workbook(io.BytesIO(response.content)).active


@pytest.fixture
def several(office_user):
    """CMP-0001 Wipro at BARC (20 days old), CMP-0002 Havells at Dr Reddys with Ramu (1 day),
    CMP-0003 Wipro at IISER Tirupati, closed as Not covered."""
    make_complaint(office_user, reported_on=ago(20), company_ref="WL/AP/24990")
    make_complaint(
        office_user,
        reported_on=ago(1),
        site=make_site("Dr Reddys", "Visakhapatnam"),
        company="Havells",
        technicians=[make_tech("Ramu")],
    )
    c = make_complaint(office_user, reported_on=ago(5), site=make_site("IISER", "Tirupati"))
    close_not_covered(complaint=c, reason=NotCoveredReason.NOT_OURS, user=office_user)


def numbers(client, query=""):
    return re.findall(LINK, client.get(LIST + query).content.decode())


def finish(c, user, to, *days):
    """Walk a complaint to Resolved and then `to`, on the given days ago (attended, resolved, final)."""
    for status, d in zip((Status.ATTENDED, Status.RESOLVED, to), days, strict=True):
        change_status(complaint=c, to=status, user=user, at=ago(d))


def test_age_and_days_awaiting_material(office_user):
    c = make_complaint(office_user, reported_on=ago(20))
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=ago(18))
    change_status(complaint=c, to=Status.AWAITING_MATERIAL, user=office_user, at=ago(15))
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=ago(10))  # 5 days waiting
    change_status(complaint=c, to=Status.AWAITING_MATERIAL, user=office_user, at=ago(4))  # still waiting: +4
    found = selectors.complaint_qs().get(pk=c.pk)
    assert (selectors.age_days(found, today()), selectors.awaiting_days(found, today())) == (20, 9)
    change_status(complaint=c, to=Status.RESOLVED, user=office_user, at=ago(2))  # +2, then the clock stops
    change_status(complaint=c, to=Status.CLOSED, user=office_user, at=ago(2))
    found = selectors.complaint_qs().get(pk=c.pk)
    assert (selectors.age_days(found, today()), selectors.awaiting_days(found, today())) == (18, 7)


@pytest.mark.parametrize(
    "days, bucket", [(0, "0-2"), (2, "0-2"), (3, "3-7"), (8, "8-15"), (15, "8-15"), (16, "15+")]
)
def test_age_buckets(days, bucket):
    assert selectors.age_bucket(days) == bucket


def test_list_defaults_to_open_newest_first(office_client, several):
    assert numbers(office_client) == ["CMP-0002", "CMP-0001"]


def test_tabs_and_filters(office_client, several):
    havells = Company.objects.get(name="Havells")
    assert numbers(office_client, "?tab=NOT_COVERED") == ["CMP-0003"]
    assert numbers(office_client, "?tab=all") == ["CMP-0002", "CMP-0003", "CMP-0001"]
    assert numbers(office_client, f"?company={havells.pk}") == ["CMP-0002"]
    assert numbers(office_client, "?city=visakhapatnam&tab=all") == ["CMP-0002", "CMP-0001"]
    assert numbers(office_client, f"?technician={make_tech('Ramu').pk}") == ["CMP-0002"]
    assert numbers(office_client, "?age=15%2B") == ["CMP-0001"]
    assert numbers(office_client, "?q=24990") == ["CMP-0001"]
    assert numbers(office_client, "?q=reddys") == ["CMP-0002"]
    assert numbers(office_client, "?sort=age&dir=desc") == ["CMP-0001", "CMP-0002"]
    assert numbers(office_client, "?sort=age&dir=asc") == ["CMP-0002", "CMP-0001"]


def test_nul_and_junk_params_are_harmless(office_client, several):
    assert numbers(office_client, "?q=%00abc") == []
    assert numbers(office_client, "?city=%00&company=x&technician=999&age=zz&tab=zz") == [
        "CMP-0002",
        "CMP-0001",
    ]


def test_tab_counts(several):
    _, tabs = selectors.complaint_rows(complaint_filters(QueryDict("")), today())
    counts = {key: n for key, _, n in tabs}
    assert (counts["open"], counts["NOT_ATTENDED"], counts["NOT_COVERED"], counts["all"]) == (2, 2, 1, 3)
    assert "finished" not in counts  # a link target from the dashboard, not a tab of its own


def test_an_old_open_complaint_shows_a_red_age(office_client, several):
    assert '<span class="badge st st-alert">20 d</span>' in office_client.get(LIST).content.decode()


def test_dashboard(office_client, several):
    d = selectors.dashboard(today())
    assert (d["counts"]["NOT_ATTENDED"], d["closed_30"], d["open"]) == (2, 1, 2)
    assert [(a["key"], a["n"]) for a in d["ages"]] == [("0-2", 1), ("3-7", 0), ("8-15", 0), ("15+", 1)]
    assert [r["c"].number for r in d["oldest"]] == ["CMP-0001", "CMP-0002"]
    assert {r["label"]: r["n"] for r in d["companies"]} == {"Wipro Lighting": 1, "Havells": 1}
    assert [(r["label"], r["n"]) for r in d["cities"]] == [("Visakhapatnam", 2)]
    html = office_client.get("/complaints/").content.decode()
    assert "Complaints dashboard" in html and "Oldest open complaints" in html
    assert f'href="{LIST}?tab=NOT_ATTENDED"' in html


def test_every_dashboard_link_lists_exactly_what_it_counts(office_client, office_user, several):
    old = make_complaint(office_user, reported_on=ago(60))
    finish(old, office_user, Status.CLOSED, 59, 58, 40)  # closed 40 days ago: outside the 30-day window
    new = make_complaint(office_user, reported_on=ago(10))
    finish(new, office_user, Status.CLOSED, 9, 8, 7)
    d = selectors.dashboard(today())
    assert d["closed_30"] == 2  # CMP-0003 (not covered) and the recent closed one, not the old one
    response = office_client.get("/complaints/")
    tiles = response.context["tiles"]
    assert len(tiles) == 6 and sum(1 for t in tiles if t["href"]) == 6
    for tile in tiles:
        found = re.findall(LINK, office_client.get(tile["href"]).content.decode())
        assert len(found) == tile["n"], tile["label"]
    for group in ("ages", "companies", "cities"):
        for row in response.context["d"][group]:
            found = re.findall(LINK, office_client.get(row["href"]).content.decode())
            assert len(found) == row["n"], row["label"]


def test_dashboard_cities_group_ignoring_case(office_client, office_user):
    make_complaint(office_user, site=make_site("A", "Vizag"))
    make_complaint(office_user, site=make_site("B", "vizag"))
    response = office_client.get("/complaints/")
    cities = response.context["d"]["cities"]
    assert [(r["label"], r["n"]) for r in cities] == [("Vizag", 2)]
    assert len(re.findall(LINK, office_client.get(cities[0]["href"]).content.decode())) == 2


def test_open_tab_link_from_the_finished_view_lists_open_complaints(office_client, several):
    since = (today() - timedelta(days=30)).isoformat()
    html = office_client.get(f"{LIST}?tab=finished&closed_since={since}").content.decode()
    assert re.findall(LINK, html) == ["CMP-0003"]
    assert "Closed or not covered after" in html
    open_href = re.search(r'href="([^"]+)" class="nav-link"[^>]*>Open ', html).group(1).replace("&amp;", "&")
    assert "closed_since" not in open_href
    assert numbers(office_client, open_href.removeprefix(LIST)) == ["CMP-0002", "CMP-0001"]
    # even a hand-made URL: closed_since never hides open complaints
    assert numbers(office_client, f"?tab=open&closed_since={since}") == ["CMP-0002", "CMP-0001"]


def test_closed_since_with_the_closed_and_all_tabs(office_client, office_user, several):
    old = make_complaint(office_user, reported_on=ago(60))
    finish(old, office_user, Status.CLOSED, 59, 58, 40)
    new = make_complaint(office_user, reported_on=ago(10))
    finish(new, office_user, Status.CLOSED, 9, 8, 7)
    since = (today() - timedelta(days=30)).isoformat()
    assert numbers(office_client, f"?tab=CLOSED&closed_since={since}") == ["CMP-0005"]
    assert numbers(office_client, "?tab=CLOSED") == ["CMP-0005", "CMP-0004"]
    assert sorted(numbers(office_client, f"?tab=finished&closed_since={since}")) == ["CMP-0003", "CMP-0005"]
    # "all" keeps open complaints out of the way only by the date: the open ones have no closed date
    assert numbers(office_client, f"?tab=all&closed_since={since}") == ["CMP-0003", "CMP-0005"]


def test_city_dropdown_and_dashboard_share_one_grouping(office_client, office_user):
    make_complaint(office_user, site=make_site("A", "Vizag"))
    make_complaint(office_user, site=make_site("B", "vizag"))
    assert selectors.cities() == ["Vizag"]
    html = office_client.get(LIST).content.decode()
    assert len(re.findall(r'<option value="[Vv]izag"', html)) == 1
    assert selectors.group_cities(["Vizag", "vizag", "Guntur"]) == [
        {"label": "Vizag", "n": 2},
        {"label": "Guntur", "n": 1},
    ]


def test_reopened_complaint_age_runs_to_today_and_awaiting_days_stay(office_client, office_user, admin_user):
    from apps.complaints.services import reopen

    c = make_complaint(office_user, reported_on=ago(20))
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=ago(19))
    change_status(complaint=c, to=Status.AWAITING_MATERIAL, user=office_user, at=ago(18))
    change_status(complaint=c, to=Status.RESOLVED, user=office_user, at=ago(12))  # 6 days waiting
    change_status(complaint=c, to=Status.CLOSED, user=office_user, at=ago(10))
    found = selectors.complaint_qs().get(pk=c.pk)
    assert (selectors.age_days(found, today()), selectors.awaiting_days(found, today())) == (10, 6)
    reopen(complaint=c, user=admin_user, note="Customer called again", at=ago(1))
    found = selectors.complaint_qs().get(pk=c.pk)
    assert (selectors.age_days(found, today()), selectors.awaiting_days(found, today())) == (20, 6)


def test_search_matches_contact_name_and_phone_digits(office_client, office_user):
    make_complaint(office_user, contact_name="Mr Subba Rao", phone="9848012345")
    make_complaint(office_user, contact_name="Other", phone="9000011111")
    assert numbers(office_client, "?q=subba") == ["CMP-0001"]
    assert numbers(office_client, "?q=98480") == ["CMP-0001"]
    assert numbers(office_client, "?q=98480%2012345") == ["CMP-0001"]
    assert numbers(office_client, "?q=0891") == []  # looks like a phone, matches none


def test_late_days_is_one_constant():
    from apps.complaints.filters import AGE_BUCKETS, LATE_DAYS

    assert LATE_DAYS == 15 and AGE_BUCKETS[-2][3] == LATE_DAYS and AGE_BUCKETS[-1][2] == LATE_DAYS + 1


def test_dashboard_open_rows_skip_the_events_query(office_user, several, django_assert_num_queries):
    # open complaints: one query for them, one for technicians; no events query
    with django_assert_num_queries(2):
        rows = selectors.open_rows(today())
    assert len(rows) == 2 and rows[0]["awaiting"] is None
    assert selectors.status_counts()["NOT_ATTENDED"] == 2
    assert [a["n"] for a in selectors.age_counts(rows)] == [1, 0, 0, 1]
    assert selectors.closed_since_count(today() - timedelta(days=30)) == 1


def test_dashboard_empty_state(office_client):
    html = office_client.get("/complaints/").content.decode()
    assert html.count("Nothing open.") == 3 and "0 open" in html


def test_list_empty_state(office_client):
    assert "No complaints match these filters." in office_client.get(LIST).content.decode()


def test_pending_export_lists_open_complaints_oldest_first(office_client, several):
    ws = sheet(office_client.get("/complaints/pending/export/"))
    assert [ws.cell(r, 1).value for r in range(7, ws.max_row + 1)] == ["CMP-0001", "CMP-0002"]
    headers = [c.value for c in ws[6]]
    age = ws.cell(7, headers.index("Age (days)") + 1)
    assert age.value == 20 and age.fill.fgColor.rgb.endswith("FDE2E2")
    assert ws.cell(7, headers.index("Company complaint no.") + 1).value == "WL/AP/24990"
    assert not ws.cell(8, headers.index("Age (days)") + 1).fill.fgColor.rgb.endswith("FDE2E2")


def test_exports_show_phones_spaced(office_client, office_user):
    make_complaint(office_user, phone="9848012345")
    ws = sheet(office_client.get("/complaints/pending/export/"))
    headers = [c.value for c in ws[6]]
    assert ws.cell(7, headers.index("Phone") + 1).value == "98480 12345"


def test_pending_export_applies_the_list_filters_but_always_open(office_client, several):
    havells = Company.objects.get(name="Havells")
    ws = sheet(office_client.get(f"/complaints/pending/export/?company={havells.pk}&tab=CLOSED"))
    assert [ws.cell(r, 1).value for r in range(7, ws.max_row + 1)] == ["CMP-0002"]
    assert "Havells" in ws["A3"].value


def test_complaint_list_export_uses_the_filters(office_client, several):
    ws = sheet(office_client.get("/complaints/export/?tab=all"))
    headers = [c.value for c in ws[6]]
    assert headers[-3:] == ["Closed on", "Not covered reason", "Visits"]
    reasons = {ws.cell(r, 1).value: ws.cell(r, len(headers) - 1).value for r in range(7, ws.max_row + 1)}
    assert set(reasons) == {"CMP-0001", "CMP-0002", "CMP-0003"} and reasons["CMP-0003"] == "Not our product"
    ws = sheet(office_client.get("/complaints/export/?tab=NOT_COVERED"))
    assert [ws.cell(r, 1).value for r in range(7, ws.max_row + 1)] == ["CMP-0003"]


def test_exports_never_write_formulas(office_client, office_user):
    make_complaint(office_user, fault='=HYPERLINK("http://x")', company_ref="=1+1")
    for url in ("/complaints/export/", "/complaints/pending/export/"):
        ws = sheet(office_client.get(url))
        assert all(c.data_type != "f" for row in ws.iter_rows() for c in row)
        assert any(c.value == "=1+1" for row in ws.iter_rows() for c in row)


def test_export_buttons_keep_the_filters(office_client, several):
    assert 'href="/complaints/export/?tab=all"' in office_client.get(LIST + "?tab=all").content.decode()
    assert 'href="/complaints/pending/export/"' in office_client.get("/complaints/").content.decode()


def test_nav_links_complaints(office_client):
    html = office_client.get("/").content.decode()
    assert 'href="/complaints/"' in html and f'href="{LIST}"' in html


def test_query_counts_are_bounded(office_client, office_user, several, django_assert_max_num_queries):
    for n in range(12):  # more rows must not mean more queries
        make_complaint(office_user, reported_on=ago(n), technicians=[make_tech(f"Tech {n}")])
    with django_assert_max_num_queries(MAX_DASHBOARD):
        assert office_client.get("/complaints/").status_code == 200
    with django_assert_max_num_queries(MAX_LIST):
        assert office_client.get(LIST + "?tab=all&sort=age").status_code == 200
    with django_assert_max_num_queries(MAX_EXPORT):
        assert office_client.get("/complaints/export/?tab=all").status_code == 200
    with django_assert_max_num_queries(MAX_EXPORT):
        assert office_client.get("/complaints/pending/export/").status_code == 200


def test_screens_are_for_signed_in_staff_only(client):
    for url in ("/complaints/", LIST, "/complaints/export/", "/complaints/pending/export/"):
        assert client.get(url).status_code == 302
