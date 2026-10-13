from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.complaints.models import NotCoveredReason, Priority, Status, Visit
from apps.complaints.phones import MOBILE_ERROR, MOBILE_OR_LANDLINE_ERROR
from apps.complaints.services import (
    ComplaintError,
    change_status,
    close_not_covered,
    file_complaint,
    record_visit,
    reopen,
    save_site,
    save_technician,
    set_active,
    undo_visit_parts,
    visit_next_options,
)
from apps.defectives.models import DefectivePiece, PieceStatus, Source
from apps.inventory.models import Company, EntryKind, ServiceSubtype, StockBalance, StockEntry
from apps.inventory.services import StockError, balance_drift, undo_entry
from tests.factories import give_stock, loc, make_complaint, make_item, make_site, make_tech, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def qty(item, place):
    row = StockBalance.objects.filter(item=item, location=place).first()
    return row.qty if row else 0


def moves(c):
    return [(e.from_status, e.to_status) for e in c.events.order_by("at", "id")]


@pytest.fixture
def stocked(office_user):
    drv = make_item("LG78-150-700")
    give_stock(drv, 5, office_user)
    return drv


def visit(c, user, **extra):
    """A visit to `c` with the usual defaults (no parts, no pieces, leaves it Attended)."""
    args = {
        "visit_date": TODAY,
        "technicians": [make_tech()],
        "work_done": "Checked the fittings",
        "next_status": Status.ATTENDED,
        **extra,
    }
    return record_visit(complaint=c, user=user, **args)


# ---------------------------------------------------------------- sites and technicians


def test_save_site_tidies_and_checks():
    s = save_site(
        data={
            "name": " Andhra  University ",
            "city": "Visakhapatnam",
            "contact_name": "Estate office",
            "phone": "98488 12345",
        }
    )
    assert (s.name, s.contact_name, s.phone) == ("Andhra University", "Estate office", "9848812345")
    with pytest.raises(
        ComplaintError, match="Andhra University, Visakhapatnam already exists. Pick it from the list."
    ):
        save_site(data={"name": "andhra university", "city": "visakhapatnam"})
    assert save_site(data={"name": "Andhra University", "city": "Guntur"}).pk != s.pk
    for data, message in [
        ({"name": "", "city": "X"}, "Enter the site name."),
        ({"name": "X", "city": " "}, "Enter the city."),
        ({"name": "X", "city": "Y", "phone": "12345"}, MOBILE_OR_LANDLINE_ERROR),
        ({"name": "X" * 121, "city": "Y"}, "Keep the site name to 120 characters or less."),
        ({"name": "X", "city": "Y" * 61}, "Keep the city to 60 characters or less."),
        ({"name": "X", "city": "Y", "contact_name": "Z" * 81}, "Keep the contact person to 80 characters"),
    ]:
        with pytest.raises(ComplaintError, match=message):
            save_site(data=data)


def test_a_site_takes_a_landline():
    s = save_site(data={"name": "Port Trust", "city": "Visakhapatnam", "phone": "0891-2345678"})
    assert s.phone == "08912345678"


def test_edit_site_keeps_its_own_name():
    s = make_site("BARC", "Visakhapatnam")
    data = {"name": "BARC", "city": "Visakhapatnam", "contact_name": "Chenna Keshavulu"}
    assert save_site(site=s, data=data).contact_name == "Chenna Keshavulu"


def test_save_technician_and_hide():
    t = save_technician(name="  Suresh ", phone="+91 98765 43210")
    assert (t.name, t.phone) == ("Suresh", "9876543210")
    with pytest.raises(ComplaintError, match="Suresh is already in the list."):
        save_technician(name="suresh")
    with pytest.raises(ComplaintError, match="Enter the name of the technician."):
        save_technician(name=" ")
    with pytest.raises(ComplaintError, match=MOBILE_ERROR):
        save_technician(name="Ravi", phone="0891-2345678")  # technicians: mobile only
    set_active(t, active=False)
    t.refresh_from_db()
    assert not t.is_active
    assert save_technician(name="Suresh K", technician=t).name == "Suresh K"


# ---------------------------------------------------------------- filing


def test_file_complaint_copies_the_site_contact(office_user):
    site = make_site(contact_name="Murthy", phone="9908127999")
    tech = make_tech()
    c = file_complaint(
        site=site,
        company=Company.objects.get(name="Havells"),
        fault=" Battens failed in canteen ",
        reported_on=TODAY,
        user=office_user,
        company_ref="HV-C-78020",
        qty_affected=4,
        priority=Priority.HIGH,
        technicians=[tech],
    )
    assert (c.number, c.status, c.fault, c.contact_name, c.phone, c.priority, c.company_ref) == (
        "CMP-0001",
        Status.NOT_ATTENDED,
        "Battens failed in canteen",
        "Murthy",
        "9908127999",
        Priority.HIGH,
        "HV-C-78020",
    )
    assert list(c.technicians.all()) == [tech] and moves(c) == [("", Status.NOT_ATTENDED)]
    filed = c.events.get()
    assert (filed.note, filed.at) == ("Complaint filed", TODAY)


def test_contact_can_be_changed_for_one_complaint(office_user):
    c = make_complaint(
        office_user, site=make_site(contact_name="Murthy"), contact_name="Bujji Babu", phone=""
    )
    assert (c.contact_name, c.phone) == ("Bujji Babu", "")
    c2 = make_complaint(office_user, phone="0891 2345678")
    assert c2.phone == "08912345678"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"site": None}, "Choose the site."),
        ({"company": None}, "Choose the company whose product failed."),
        ({"fault": " "}, "Describe the fault."),
        ({"reported_on": None}, "Choose the date the complaint was reported."),
        ({"reported_on": TODAY + timedelta(days=1)}, "The reported date can't be in the future."),
        ({"qty_affected": 0}, "Quantity affected must be a whole number of 1 or more."),
        ({"qty_affected": True}, "Quantity affected must be a whole number of 1 or more."),
        ({"phone": "123"}, MOBILE_OR_LANDLINE_ERROR),
        ({"priority": "LOW"}, "Choose the priority."),
        ({"company_ref": "R" * 61}, "Keep the company complaint no. to 60 characters or less."),
    ],
)
def test_file_complaint_rules(office_user, change, message):
    args = {
        "site": make_site(),
        "company": Company.objects.get(name="Wipro Lighting"),
        "fault": "x",
        "reported_on": TODAY,
        **change,
    }
    with pytest.raises(ComplaintError, match=message):
        file_complaint(user=office_user, **args)


# ---------------------------------------------------------------- status changes


def test_change_status_follows_the_transitions(office_user):
    c = make_complaint(office_user)
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, note="Called the site")
    change_status(complaint=c, to=Status.AWAITING_MATERIAL, user=office_user)
    c.refresh_from_db()
    assert c.status == Status.AWAITING_MATERIAL
    with pytest.raises(ComplaintError, match="This complaint is already Awaiting material."):
        change_status(complaint=c, to=Status.AWAITING_MATERIAL, user=office_user)
    with pytest.raises(
        ComplaintError,
        match="A complaint that is Awaiting material can't move to Closed. "
        "Allowed: Attended, Material need to check, Resolved, Not covered.",
    ):
        change_status(complaint=c, to=Status.CLOSED, user=office_user)
    with pytest.raises(ComplaintError, match="Choose the new status."):
        change_status(complaint=c, to="LOST", user=office_user)
    change_status(complaint=c, to=Status.RESOLVED, user=office_user)
    change_status(complaint=c, to=Status.CLOSED, user=office_user)
    c.refresh_from_db()
    assert c.closed_on == TODAY and not c.is_open
    assert moves(c)[-1] == (Status.RESOLVED, Status.CLOSED)


def test_change_status_dates(office_user):
    c = make_complaint(office_user, reported_on=TODAY - timedelta(days=5))
    with pytest.raises(ComplaintError, match="The date can't be in the future."):
        change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=TODAY + timedelta(days=1))
    with pytest.raises(
        ComplaintError,
        match=f"The date can't be before the complaint was reported \\({c.reported_on:%d-%m-%Y}\\).",
    ):
        change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=TODAY - timedelta(days=6))
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=TODAY - timedelta(days=3))
    day = TODAY - timedelta(days=3)
    with pytest.raises(
        ComplaintError, match=f"The date can't be before the complaint's last change \\({day:%d-%m-%Y}\\)."
    ):
        change_status(complaint=c, to=Status.RESOLVED, user=office_user, at=TODAY - timedelta(days=4))
    change_status(complaint=c, to=Status.RESOLVED, user=office_user, at=day)  # the same day is fine
    change_status(complaint=c, to=Status.CLOSED, user=office_user, at=TODAY - timedelta(days=1))
    c.refresh_from_db()
    assert c.closed_on == TODAY - timedelta(days=1)
    assert [e.at for e in c.events.all()] == [TODAY - timedelta(days=5), day, day, TODAY - timedelta(days=1)]


def test_not_covered_needs_a_reason(office_user):
    c = make_complaint(office_user)
    with pytest.raises(ComplaintError, match="Choose why the complaint is not covered."):
        close_not_covered(complaint=c, reason="", user=office_user)
    with pytest.raises(ComplaintError, match="Write a note when the reason is Other."):
        close_not_covered(complaint=c, reason=NotCoveredReason.OTHER, user=office_user)
    close_not_covered(complaint=c, reason=NotCoveredReason.NOT_OURS, user=office_user, note="Another brand")
    c.refresh_from_db()
    assert (c.status, c.not_covered_reason, c.closed_on) == (Status.NOT_COVERED, "NOT_OURS", TODAY)
    assert (c.events.last().reason, c.events.last().note) == ("NOT_OURS", "Another brand")
    with pytest.raises(ComplaintError, match="can't move to Attended"):
        change_status(complaint=c, to=Status.ATTENDED, user=office_user)


def test_a_long_note_is_refused(office_user):
    c = make_complaint(office_user)
    with pytest.raises(ComplaintError, match="Keep the note to 300 characters or less."):
        change_status(complaint=c, to=Status.ATTENDED, user=office_user, note="n" * 301)


def test_only_admin_reopens_a_closed_complaint(office_user, admin_user):
    c = make_complaint(office_user)
    with pytest.raises(ComplaintError, match="Only a closed complaint can be reopened."):
        reopen(complaint=c, user=admin_user, note="x")
    for to in (Status.ATTENDED, Status.RESOLVED, Status.CLOSED):
        change_status(complaint=c, to=to, user=office_user)
    with pytest.raises(
        ComplaintError, match="A closed complaint can't move to Attended. Only Admin can reopen it."
    ):
        change_status(complaint=c, to=Status.ATTENDED, user=office_user)
    with pytest.raises(ComplaintError, match="Only Admin can reopen it."):
        reopen(complaint=c, user=office_user, note="Lights failed again")
    with pytest.raises(ComplaintError, match="Write why the complaint is being reopened."):
        reopen(complaint=c, user=admin_user, note=" ")
    with pytest.raises(ComplaintError, match="The date can't be in the future."):
        reopen(complaint=c, user=admin_user, note="x", at=TODAY + timedelta(days=1))
    change_status(complaint=c, to=Status.ATTENDED, user=admin_user, note="Lights failed again")
    c.refresh_from_db()
    assert (c.status, c.closed_on) == (Status.ATTENDED, None)
    assert c.events.last().note == "Reopened: Lights failed again"
    assert moves(c)[-1] == (Status.CLOSED, Status.ATTENDED)


# ---------------------------------------------------------------- visits


def test_visit_next_options(office_user):
    c = make_complaint(office_user)
    assert visit_next_options(c) == [
        Status.ATTENDED,
        Status.MATERIAL_CHECK,
        Status.AWAITING_MATERIAL,
        Status.RESOLVED,
    ]
    change_status(complaint=c, to=Status.ATTENDED, user=office_user)
    change_status(complaint=c, to=Status.RESOLVED, user=office_user)
    c.refresh_from_db()
    assert visit_next_options(c) == [Status.ATTENDED, Status.RESOLVED]


def test_visit_gives_parts_collects_pieces_and_moves_the_status(office_user, stocked):
    ramu, appa = make_tech("Ramu"), make_tech("Apparao")
    other = make_item("LG78-150-701")
    c = make_complaint(office_user, technicians=[ramu])
    v = record_visit(
        complaint=c,
        visit_date=TODAY,
        technicians=[ramu, appa],
        work_done="Changed 2 drivers",
        next_status=Status.MATERIAL_CHECK,
        user=office_user,
        location=loc(),
        parts=[(stocked, 2)],
        collected=[
            (stocked, 2, "B2405", date(2026, 3, 1), "no output"),
            (other, 1, "", None, "flickers"),
        ],
    )
    assert v.number == "VIS-0001" and v.location == loc()
    out, col = v.out_entry, v.collect_entry
    assert (out.kind, out.subtype, out.complaint, out.ref, out.party, out.note) == (
        EntryKind.OUT,
        ServiceSubtype.COMPLAINT,
        c,
        "CMP-0001",
        "BARC, Visakhapatnam",
        "Visit VIS-0001",
    )
    assert (col.kind, col.subtype, col.complaint) == (EntryKind.IN, ServiceSubtype.DEFECTIVE_COLLECTED, c)
    assert qty(stocked, loc()) == 3 and qty(stocked, store()) == 2 and qty(other, store()) == 1
    pieces = [
        (p.tag, p.item.code, p.source, p.visit, p.batch_code, p.pkd, p.fault)
        for p in DefectivePiece.objects.order_by("tag")
    ]
    assert pieces == [
        ("DEF-0001", "LG78-150-700", Source.SITE_VISIT, v, "B2405", date(2026, 3, 1), "no output"),
        ("DEF-0002", "LG78-150-700", Source.SITE_VISIT, v, "B2405", date(2026, 3, 1), "no output"),
        ("DEF-0003", "LG78-150-701", Source.SITE_VISIT, v, "", None, "flickers"),
    ]
    first = DefectivePiece.objects.get(tag="DEF-0001").events.get()
    assert (first.entry, first.note) == (col, "Collected at site (CMP-0001, VIS-0001)")
    c.refresh_from_db()
    assert c.status == Status.MATERIAL_CHECK
    assert moves(c)[1:] == [
        (Status.NOT_ATTENDED, Status.ATTENDED),
        (Status.ATTENDED, Status.MATERIAL_CHECK),
    ]
    assert set(c.technicians.all()) == {ramu, appa} and set(v.technicians.all()) == {ramu, appa}
    assert balance_drift() == []


def test_visit_without_parts_or_pieces(office_user):
    c = make_complaint(office_user)
    v = visit(c, office_user, work_done="Site checked, drivers needed")
    assert v.out_entry is None and v.collect_entry is None and v.location is None
    assert not StockEntry.objects.exists()
    assert moves(c)[-1] == (Status.NOT_ATTENDED, Status.ATTENDED)
    assert c.events.last().note == "Visit VIS-0001"


def test_a_visit_that_keeps_the_status_logs_no_event(office_user):
    c = make_complaint(office_user)
    change_status(complaint=c, to=Status.ATTENDED, user=office_user)
    visit(c, office_user, next_status=Status.ATTENDED)
    assert c.events.count() == 2


def test_over_issue_saves_nothing_at_all(office_user, stocked):
    c = make_complaint(office_user)
    with pytest.raises(ComplaintError, match="Parts given: Only 5 NOS of LG78-150-700 at Vizag Office."):
        visit(c, office_user, location=loc(), parts=[(stocked, 9)], collected=[(stocked, 1, "", None, "x")])
    assert not Visit.objects.exists() and not DefectivePiece.objects.exists()
    assert StockEntry.objects.count() == 1  # only the opening stock
    c.refresh_from_db()
    assert c.status == Status.NOT_ATTENDED and c.events.count() == 1
    assert visit(c, office_user).number == "VIS-0001"  # the refused visit used no number


@pytest.mark.parametrize(
    "change, message",
    [
        ({"visit_date": None}, "Choose the visit date."),
        ({"visit_date": TODAY + timedelta(days=1)}, "The visit date can't be in the future."),
        (
            {"visit_date": TODAY - timedelta(days=5)},
            "The visit date can't be before the complaint was reported",
        ),
        ({"technicians": []}, "Choose who attended."),
        ({"work_done": " "}, "Write what work was done."),
        ({"next_status": Status.CLOSED}, "A complaint that is Not attended can't move to Closed."),
        ({"next_status": "LOST"}, "Choose the status after the visit."),
        ({"location": None}, "Choose the location the parts were given from."),
        ({"parts": [(None, 1)]}, "Parts given, line 1: choose the item."),
        ({"parts": [("ITEM", 0)]}, "Parts given, line 1: quantity must be 1 or more."),
        (
            {"collected": [("ITEM", 201, "", None, "")]},
            "Failed parts, line 1: quantity must be between 1 and 200.",
        ),
        ({"collected": [("ITEM", 1, "B" * 41, None, "")]}, "Failed parts, line 1: keep the batch code to 40"),
        ({"collected": [("ITEM", 1, "", None, "F" * 201)]}, "Failed parts, line 1: keep the fault to 200"),
    ],
)
def test_visit_rules(office_user, stocked, change, message):
    c, change = make_complaint(office_user), dict(change)
    for key in ("parts", "collected"):  # "ITEM" stands for the stocked item
        if key in change:
            change[key] = [tuple(stocked if v == "ITEM" else v for v in line) for line in change[key]]
    args = {
        "visit_date": TODAY,
        "technicians": [make_tech()],
        "work_done": "x",
        "next_status": Status.ATTENDED,
        "location": loc(),
        "parts": [(stocked, 1)],
        **change,
    }
    with pytest.raises(ComplaintError, match=message):
        record_visit(complaint=c, user=office_user, **args)
    assert not Visit.objects.exists() and StockEntry.objects.count() == 1


def test_parts_cant_come_from_the_defective_store(office_user, stocked):
    c = make_complaint(office_user)
    with pytest.raises(ComplaintError, match="Choose a good-stock location for the parts given."):
        visit(c, office_user, location=store(), parts=[(stocked, 1)])


def test_a_backdated_visit_cant_change_the_status_before_the_last_change(office_user):
    c = make_complaint(office_user, reported_on=TODAY - timedelta(days=5))
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=TODAY - timedelta(days=1))
    with pytest.raises(ComplaintError, match="This complaint last changed status on"):
        visit(c, office_user, visit_date=TODAY - timedelta(days=3), next_status=Status.RESOLVED)
    # Recorded late without a status change: fine.
    v = visit(c, office_user, visit_date=TODAY - timedelta(days=3), next_status=Status.ATTENDED)
    assert v.visit_date == TODAY - timedelta(days=3) and c.events.count() == 2


def test_no_visits_on_a_finished_complaint(office_user):
    c = make_complaint(office_user)
    close_not_covered(complaint=c, reason=NotCoveredReason.CANCELLED, user=office_user)
    with pytest.raises(ComplaintError, match="This complaint is Not covered, so visits can't be added."):
        visit(c, office_user)


def test_visit_takes_every_balance_lock_before_any_entry_counter(office_user, stocked):
    """record_visit posts two entries. It locks all their balance rows in one sorted pass first, so it never
    holds an EntryCounter while waiting for a balance row (see the record_visit docstring)."""
    c = make_complaint(office_user)
    with CaptureQueriesContext(connection) as ctx:
        visit(
            c,
            office_user,
            location=loc(),
            parts=[(stocked, 1)],
            collected=[(stocked, 1, "", None, "x")],
        )
    sqls = [q["sql"] for q in ctx.captured_queries]
    balance_locks = [i for i, s in enumerate(sqls) if '"inventory_stockbalance"' in s and "FOR UPDATE" in s]
    counter_locks = [i for i, s in enumerate(sqls) if '"inventory_entrycounter"' in s and "FOR UPDATE" in s]
    assert len(counter_locks) == 2 and balance_locks[0] < counter_locks[0]
    first = sqls[balance_locks[0]]
    assert f'"location_id" = {loc().pk}' in first and f'"location_id" = {store().pk}' in first


# ---------------------------------------------------------------- undo a visit's parts given


def given(office_user, stocked, n=2):
    c = make_complaint(office_user)
    v = visit(
        c,
        office_user,
        location=loc(),
        parts=[(stocked, n)],
        collected=[(stocked, 1, "", None, "no output")],
    )
    return c, v


def test_undo_visit_parts_puts_the_stock_back(office_user, stocked):
    c, v = given(office_user, stocked)
    assert qty(stocked, loc()) == 3
    rev = undo_visit_parts(visit=v, reason=" Typed 2, gave 1 ", user=office_user)
    assert qty(stocked, loc()) == 5 and balance_drift() == []
    assert (rev.kind, rev.reverses, rev.complaint, rev.entry_date, rev.ref, rev.party) == (
        EntryKind.REV,
        v.out_entry,
        c,
        TODAY,
        "CMP-0001",
        "BARC, Visakhapatnam",
    )
    assert rev.note == "Parts given on VIS-0001 undone: Typed 2, gave 1"
    assert list(c.entries.order_by("id")) == [v.out_entry, v.collect_entry, rev]
    # The collected pieces are not touched (they are corrected from the Defectives screens).
    assert qty(stocked, store()) == 1
    assert list(DefectivePiece.objects.values_list("status", flat=True)) == [PieceStatus.IN_STORE]
    # The status is not touched either.
    c.refresh_from_db()
    assert c.status == Status.ATTENDED and c.events.count() == 2
    # The reversal is an undo, so it can't be undone in turn.
    with pytest.raises(StockError, match="An undo can't be undone."):
        undo_entry(entry=rev, reason="x", user=office_user)


def test_undo_visit_parts_only_once(office_user, stocked):
    _, v = given(office_user, stocked)
    rev = undo_visit_parts(visit=v, reason="wrong item", user=office_user)
    with pytest.raises(
        ComplaintError, match=f"The parts given on VIS-0001 were already undone \\({rev.number}\\)."
    ):
        undo_visit_parts(visit=v, reason="again", user=office_user)
    assert StockEntry.objects.filter(kind=EntryKind.REV).count() == 1 and qty(stocked, loc()) == 5


def test_undo_visit_parts_needs_parts(office_user):
    c = make_complaint(office_user)
    v = visit(c, office_user)
    with pytest.raises(ComplaintError, match="Visit VIS-0001 gave no parts, so there is nothing to undo."):
        undo_visit_parts(visit=v, reason="x", user=office_user)
    assert not StockEntry.objects.exists()


def test_undo_visit_parts_rules(office_user, stocked):
    _, v = given(office_user, stocked)
    with pytest.raises(ComplaintError, match="Write why the parts given are being undone."):
        undo_visit_parts(visit=v, reason=" ", user=office_user)
    with pytest.raises(ComplaintError, match="The date can't be in the future."):
        undo_visit_parts(visit=v, reason="x", user=office_user, at=TODAY + timedelta(days=1))
    with pytest.raises(
        ComplaintError, match=f"The undo can't be dated before the visit \\({TODAY:%d-%m-%Y}\\)."
    ):
        undo_visit_parts(visit=v, reason="x", user=office_user, at=TODAY - timedelta(days=1))
    assert not StockEntry.objects.filter(kind=EntryKind.REV).exists()


def test_undo_visit_parts_on_a_closed_complaint(office_user, stocked):
    """Correcting the stock is still allowed once the complaint is closed."""
    c, v = given(office_user, stocked)
    for to in (Status.RESOLVED, Status.CLOSED):
        change_status(complaint=c, to=to, user=office_user)
    undo_visit_parts(visit=v, reason="gave none in the end", user=office_user)
    assert qty(stocked, loc()) == 5


def test_general_undo_still_refuses_a_visits_entries(office_user, stocked):
    _, v = given(office_user, stocked)
    for e in (v.out_entry, v.collect_entry):
        with pytest.raises(
            StockError, match="This entry belongs to a complaint visit. Correct it from the complaint."
        ):
            undo_entry(entry=e, reason="x", user=office_user)
