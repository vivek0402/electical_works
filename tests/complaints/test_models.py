from datetime import timedelta

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.complaints.models import (
    TRANSITIONS,
    Complaint,
    ComplaintEvent,
    NotCoveredReason,
    Site,
    Status,
    Technician,
    Visit,
)
from apps.defectives import selectors as defective_selectors
from apps.defectives.models import DefectivePiece, Source
from apps.defectives.services import collect_pieces, create_piece
from apps.inventory.models import Company, EntryKind, ServiceSubtype, StockEntry
from apps.inventory.services import Line, StockError, post_entry, undo_entry
from tests.factories import give_stock, loc, make_item, make_pieces, make_site, make_tech, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()
PIECES = "/defectives/pieces/"


def complaint(user, number="CMP-0001", site=None, **extra):
    return Complaint.objects.create(
        number=number,
        site=site or make_site(),
        company=Company.objects.get(name="Wipro Lighting"),
        fault="Flood lights not glowing",
        reported_on=TODAY,
        created_by=user,
        **extra,
    )


def collect(user, c, item, qty=1, number="VIS-0001"):
    """A visit to complaint `c` that collected `qty` failed `item`s into the Defective store."""
    e = post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(item, store(), qty)],
        user=user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
        complaint=c,
    )
    v = Visit.objects.create(
        number=number,
        complaint=c,
        visit_date=TODAY,
        work_done="Removed drivers",
        next_status=Status.ATTENDED,
        collect_entry=e,
        created_by=user,
    )
    pieces = collect_pieces(
        entry=e, item=item, qty=qty, source=Source.SITE_VISIT, collected_on=TODAY, user=user, visit=v
    )
    return v, pieces


def refused(queryset, **change):
    with pytest.raises(IntegrityError), transaction.atomic():
        queryset.update(**change)


def test_site_is_unique_by_name_and_city_ignoring_case():
    make_site("BARC", "Visakhapatnam")
    make_site("BARC", "Mumbai")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_site("barc", "visakhapatnam")
    assert str(Site.objects.get(city="Mumbai")) == "BARC, Mumbai"


def test_site_name_spaces_are_tidied():
    assert make_site("  Laurus   Labs Unit-2 ", " Visakhapatnam ").name == "Laurus Labs Unit-2"


def test_technician_names_are_unique_ignoring_case():
    make_tech("Ramu")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_tech("RAMU")


def test_transitions_match_the_approved_flow():
    assert TRANSITIONS[Status.NOT_ATTENDED] == [Status.ATTENDED, Status.NOT_COVERED]
    assert TRANSITIONS[Status.RESOLVED] == [Status.CLOSED, Status.ATTENDED, Status.NOT_COVERED]
    assert TRANSITIONS[Status.CLOSED] == [] and TRANSITIONS[Status.NOT_COVERED] == []
    for status in (Status.ATTENDED, Status.MATERIAL_CHECK, Status.AWAITING_MATERIAL):
        assert Status.NOT_COVERED in TRANSITIONS[status]


def test_complaint_defaults(office_user):
    c = complaint(office_user)
    assert (c.status, c.priority, c.is_open, str(c)) == (Status.NOT_ATTENDED, "NORMAL", True, "CMP-0001")


def test_complaint_events_are_append_only(office_user):
    ev = ComplaintEvent.objects.create(
        complaint=complaint(office_user), to_status=Status.NOT_ATTENDED, at=TODAY, by=office_user
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        ComplaintEvent.objects.filter(pk=ev.pk).update(note="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        ComplaintEvent.objects.filter(pk=ev.pk).delete()


def test_entries_and_pieces_link_back_to_the_complaint(office_user):
    c = complaint(office_user, company_ref="WL/AP/24871")
    item = make_item("LG78-150-700")
    e = post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(item, store(), 1)],
        user=office_user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
        complaint=c,
    )
    v = Visit.objects.create(
        number="VIS-0001",
        complaint=c,
        visit_date=TODAY,
        work_done="Removed a driver",
        next_status=Status.ATTENDED,
        collect_entry=e,
        created_by=office_user,
    )
    p = create_piece(
        item=item, source=Source.SITE_VISIT, collected_on=TODAY, user=office_user, entry=e, visit=v
    )
    assert e.complaint == c and list(c.entries.all()) == [e] and p.visit == v
    found = defective_selectors.pieces_qs().get(pk=p.pk)
    assert defective_selectors.complaint_cells(found) == ["CMP-0001", "WL/AP/24871"]
    assert list(DefectivePiece.objects.filter(defective_selectors.piece_search_q("cmp-0001"))) == [p]


def test_complaint_cells_for_pieces_without_a_visit(office_user):
    [p] = make_pieces(make_item("LG78-150-700"), 1, office_user)
    assert defective_selectors.complaint_cells(p) == ["Found in stock", ""]


def test_collect_pieces_tags_every_piece_with_the_visit(office_user):
    v, pieces = collect(office_user, complaint(office_user), make_item("LG78-150-700"), qty=3)
    assert [p.visit for p in pieces] == [v, v, v] and list(v.pieces.order_by("tag")) == pieces


# ---------------------------------------------------------------- database guards


def test_complaint_status_and_dates_must_agree(office_user):
    c = complaint(office_user)
    rows = Complaint.objects.filter(pk=c.pk)
    refused(rows, status="DANCING")
    refused(rows, priority="LOW")
    refused(rows, status=Status.CLOSED)  # closed with no closed_on
    refused(rows, closed_on=TODAY)  # open with a closed_on
    refused(rows, status=Status.NOT_COVERED, closed_on=TODAY)  # not covered with no reason
    refused(rows, not_covered_reason=NotCoveredReason.CANCELLED)  # a reason on an open complaint
    refused(rows, not_covered_reason="BORED")
    refused(rows, qty_affected=0)
    rows.update(status=Status.CLOSED, closed_on=TODAY)
    rows.update(status=Status.ATTENDED, closed_on=None)  # Admin reopen
    rows.update(status=Status.NOT_COVERED, closed_on=TODAY, not_covered_reason=NotCoveredReason.OTHER)


def test_phones_are_stored_clean(office_user):
    """Sites and complaints: mobile or STD landline. Technicians: mobile only."""
    site = make_site(phone="9908127999")
    tech = make_tech(phone="")
    c = complaint(office_user, phone="9908127999")
    for model, pk in ((Site, site.pk), (Complaint, c.pk)):
        rows = model.objects.filter(pk=pk)
        for bad in ("12345", "1234567890", "9876 54321", "0012345678"):
            refused(rows, phone=bad)
        for good in ("", "9876543210", "08912345678", "0891234567"):
            rows.update(phone=good)
    rows = Technician.objects.filter(pk=tech.pk)
    for bad in ("1234567890", "0891234567"):  # a landline is refused for a technician
        refused(rows, phone=bad)
    rows.update(phone="9876543210")


def test_names_cannot_be_blank():
    refused(Site.objects.filter(pk=make_site().pk), name="")
    refused(Site.objects.filter(pk=make_site().pk), city="")
    refused(Technician.objects.filter(pk=make_tech().pk), name="")


def test_event_rules(office_user):
    c = complaint(office_user)

    def bad_event(**fields):
        with pytest.raises(IntegrityError), transaction.atomic():
            ComplaintEvent.objects.create(complaint=c, at=TODAY, by=office_user, **fields)

    bad_event(from_status=Status.ATTENDED, to_status=Status.ATTENDED)  # not a move
    bad_event(from_status=Status.NOT_ATTENDED, to_status="DANCING")
    bad_event(from_status=Status.ATTENDED, to_status=Status.NOT_COVERED)  # no reason
    bad_event(from_status=Status.NOT_ATTENDED, to_status=Status.ATTENDED, reason=NotCoveredReason.OTHER)
    ComplaintEvent.objects.create(
        complaint=c,
        from_status=Status.ATTENDED,
        to_status=Status.NOT_COVERED,
        reason=NotCoveredReason.NOT_OURS,
        at=TODAY,
        by=office_user,
    )


def test_visit_rules(office_user):
    c = complaint(office_user)
    v = Visit.objects.create(
        number="VIS-0001",
        complaint=c,
        visit_date=TODAY,
        work_done="Checked",
        next_status=Status.ATTENDED,
        created_by=office_user,
    )
    rows = Visit.objects.filter(pk=v.pk)
    refused(rows, next_status=Status.CLOSED)  # a visit leaves the complaint in a working status
    refused(rows, next_status=Status.NOT_COVERED)
    refused(rows, location=loc())  # a location only with the parts-given OUT


# ---------------------------------------------------------------- screens


def test_pieces_from_a_visit_show_their_complaint(office_client, office_user):
    c = complaint(office_user, site=make_site("Andhra University", "Guntur"))
    _, [p] = collect(office_user, c, make_item("LG78-150-700"))
    html = office_client.get(PIECES).content.decode()
    assert "CMP-0001" in html and "Andhra University" in html
    html = office_client.get(PIECES + "?q=cmp-0001").content.decode()
    assert p.tag in html
    html = office_client.get(f"{PIECES}{p.tag}/").content.decode()
    assert "CMP-0001" in html


def test_pieces_list_queries_do_not_grow_with_complaints(office_client, office_user):
    item = make_item("LG78-150-700")
    collect(office_user, complaint(office_user), item)
    with CaptureQueriesContext(connection) as one:
        office_client.get(PIECES)
    for n in range(2, 8):
        site = make_site(f"Site {n}", "Visakhapatnam")
        c = complaint(office_user, number=f"CMP-{n:04d}", site=site)
        collect(office_user, c, item, number=f"VIS-{n:04d}")
    with CaptureQueriesContext(connection) as many:
        html = office_client.get(PIECES).content.decode()
    assert "CMP-0007" in html
    assert len(many) == len(one)


def test_a_visit_piece_must_come_from_that_visits_collection(office_user):
    from apps.defectives.services import DefectiveError

    item = make_item("LG78-150-700")
    v, _ = collect(office_user, complaint(office_user), item)
    other = post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(item, store(), 1)],
        user=office_user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
    )
    args = {"item": item, "collected_on": TODAY, "user": office_user, "visit": v}
    with pytest.raises(DefectiveError, match="is not the collection entry of visit VIS-0001"):
        create_piece(entry=other, source=Source.SITE_VISIT, **args)
    with pytest.raises(DefectiveError, match="Only pieces collected at a site visit belong to a visit."):
        create_piece(entry=v.collect_entry, source=Source.FOUND_IN_STOCK, **args)


def test_only_site_visit_pieces_name_a_visit(office_user):
    v, [p] = collect(office_user, complaint(office_user), make_item("LG78-150-700"))
    refused(DefectivePiece.objects.filter(pk=p.pk), source=Source.FOUND_IN_STOCK)
    [found] = make_pieces(make_item("LG78-150-701"), 1, office_user)
    refused(DefectivePiece.objects.filter(pk=found.pk), visit=v)


# ---------------------------------------------------------------- history is kept


def test_a_technician_with_history_cannot_be_deleted(office_user):
    from django.db.models import ProtectedError

    ramu, appa, new = make_tech("Ramu"), make_tech("Apparao"), make_tech("Suresh")
    c = complaint(office_user)
    c.technicians.add(ramu)
    v = Visit.objects.create(
        number="VIS-0001",
        complaint=c,
        visit_date=TODAY,
        work_done="Checked",
        next_status=Status.ATTENDED,
        created_by=office_user,
    )
    v.technicians.set([appa])
    for tech in (ramu, appa):
        with pytest.raises(ProtectedError), transaction.atomic():
            tech.delete()
    new.delete()  # never used: fine
    assert list(c.technicians.all()) == [ramu] and list(v.technicians.all()) == [appa]


def test_visits_cannot_be_deleted_but_can_be_updated(office_user):
    v = Visit.objects.create(
        number="VIS-0001",
        complaint=complaint(office_user),
        visit_date=TODAY,
        work_done="Checked",
        next_status=Status.ATTENDED,
        created_by=office_user,
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        Visit.objects.filter(pk=v.pk).delete()
    Visit.objects.filter(pk=v.pk).update(work_done="Checked all fittings")
    assert Visit.objects.get(pk=v.pk).work_done == "Checked all fittings"


def test_numbers_fault_and_work_done_cannot_be_blank(office_user):
    c = complaint(office_user)
    refused(Complaint.objects.filter(pk=c.pk), number="")
    refused(Complaint.objects.filter(pk=c.pk), fault="")
    v = Visit.objects.create(
        number="VIS-0001",
        complaint=c,
        visit_date=TODAY,
        work_done="Checked",
        next_status=Status.ATTENDED,
        created_by=office_user,
    )
    refused(Visit.objects.filter(pk=v.pk), number="")
    refused(Visit.objects.filter(pk=v.pk), work_done="")


def test_a_complaint_cannot_close_before_it_was_reported(office_user):
    rows = Complaint.objects.filter(pk=complaint(office_user).pk)
    refused(rows, status=Status.CLOSED, closed_on=TODAY - timedelta(days=1))
    rows.update(status=Status.CLOSED, closed_on=TODAY)  # the same day is fine


# ---------------------------------------------------------------- a visit's ledger entries


def test_only_visit_subtypes_can_name_a_complaint(office_user):
    item = make_item("LG78-150-700")
    with pytest.raises(IntegrityError), transaction.atomic():
        post_entry(
            kind=EntryKind.IN,
            entry_date=TODAY,
            lines=[Line(item, loc(), 1)],
            user=office_user,
            subtype="SUPPLIER",
            complaint=complaint(office_user),
        )


def test_a_visits_entries_cannot_be_undone(office_client, office_user):
    item = make_item("LG78-150-700")
    give_stock(item, 3, office_user)
    c = complaint(office_user)
    given = post_entry(
        kind=EntryKind.OUT,
        entry_date=TODAY,
        lines=[Line(item, loc(), -1)],
        user=office_user,
        subtype=ServiceSubtype.COMPLAINT,
        complaint=c,
    )
    v, _ = collect(office_user, c, item, number="VIS-0002")
    message = "This entry belongs to a complaint visit. Correct it from the complaint."
    for e in (given, v.collect_entry):
        with pytest.raises(StockError, match=message):
            undo_entry(entry=e, reason="typed twice", user=office_user)
        html = office_client.get(f"/entries/{e.number}/").content.decode()
        assert "Undo this entry" not in html
        assert "belongs to a visit on complaint" in html and "CMP-0001" in html
        assert "belongs to the defective pieces" not in html
        r = office_client.post(f"/entries/{e.number}/undo/", {"reason": "x"}, follow=True)
        assert message in r.content.decode()
    assert not StockEntry.objects.filter(kind=EntryKind.REV).exists()
