"""All writes for complaints, sites and technicians. Views and commands call these; nothing else changes a
complaint. A visit's stock effects go through inventory's post_entry and defectives' collect_pieces, all in
one transaction, so a visit that would over-issue stock saves nothing at all.

Lock order (see also the docstring of apps/defectives/services.py):

    Complaint row, then the visit's own VIS number, then every StockBalance row (one sorted pass), then the
    EntryCounter rows (OUT, then IN), then DEF piece tags

Only these services lock a Complaint row, and each locks one complaint, first. record_visit is the one
service that posts two ledger entries in one transaction; its docstring explains why that can't deadlock.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.roles import ADMIN, has_role
from apps.core.numbers import next_number
from apps.core.text import clean_text
from apps.defectives.models import Source
from apps.defectives.services import (
    BATCH_CODE_MAX,
    FAULT_MAX,
    MAX_PIECES_PER_LINE,
    DefectiveError,
    collect_pieces,
)
from apps.inventory.models import EntryKind, Location, ServiceSubtype, StockEntry

# _reverse_entry is private to inventory on purpose; this cross-app import is intentional and used only by
# undo_visit_parts (the general Undo refuses a visit's entries).
from apps.inventory.services import Line, StockError, _reverse_entry, lock_balances, post_entry

from .models import (
    OPEN_STATUSES,
    TRANSITIONS,
    WORK_STATUSES,
    Complaint,
    ComplaintEvent,
    NotCoveredReason,
    Priority,
    Site,
    Status,
    Technician,
    Visit,
)
from .phones import normalise_phone

# Field lengths (the model's), refused rather than cut.
SITE_NAME_MAX, CITY_MAX, CONTACT_MAX, COMPANY_REF_MAX, TECH_NAME_MAX, NOTE_MAX = 120, 60, 80, 60, 60, 300
REOPENED = "Reopened: "
PARTY_MAX = StockEntry._meta.get_field("party").max_length  # a visit's entries name the site, cut to fit


class ComplaintError(ValidationError):
    """A complaints rule was broken. The message is safe to show to staff as-is."""


def _tidy(text):
    """Typed text on one line: NUL bytes dropped (Postgres rejects them), runs of spaces made one."""
    return " ".join((text or "").replace(chr(0), "").split())


def _limit(text, limit, what):
    if len(text) > limit:
        raise ComplaintError(f"Keep the {what} to {limit} characters or less.")
    return text


def _phone(text, *, allow_landline):
    try:
        return normalise_phone(text, allow_landline=allow_landline)
    except ValueError as exc:
        raise ComplaintError(str(exc)) from exc


def _label(status):
    return Status(status).label


def _check_shown(*, site=None, technicians=()):
    """Refuse a hidden site or technician (read from the database, not the caller's possibly stale copy)."""
    if site is not None and not Site.objects.filter(pk=site.pk, is_active=True).exists():
        raise ComplaintError(f"{site} is hidden. Show it again in Sites, or choose another.")
    pks = [t.pk for t in technicians]
    hidden = Technician.objects.filter(pk__in=pks, is_active=False).order_by("name").first()
    if hidden:
        raise ComplaintError(f"{hidden.name} is hidden. Show it again in Technicians, or choose another.")


def _check_day(complaint, day, *, what, last_change=True):
    """`day` (a status change, reopen or visit) is not in the future, not before the complaint was reported
    and, when it logs an event (`last_change`), not before the complaint's last event, so the history stays in
    date order (age and days awaiting material are worked out from it)."""
    if day > timezone.localdate():
        raise ComplaintError(f"{what} can't be in the future.")
    if day < complaint.reported_on:
        raise ComplaintError(
            f"{what} can't be before the complaint was reported ({complaint.reported_on:%d-%m-%Y})."
        )
    if last_change:
        last = complaint.events.aggregate(last=Max("at"))["last"]
        if last and day < last:
            raise ComplaintError(f"{what} can't be before the complaint's last change ({last:%d-%m-%Y}).")


# ---------------------------------------------------------------- sites and technicians


@transaction.atomic
def save_site(*, data, site=None):
    """Create (site=None) or update a site. data keys: name, city, contact_name, phone, address.
    The phone may be a mobile or an STD landline."""
    name = _limit(_tidy(data.get("name")), SITE_NAME_MAX, "site name")
    city = _limit(_tidy(data.get("city")), CITY_MAX, "city")
    if not name:
        raise ComplaintError("Enter the site name.")
    if not city:
        raise ComplaintError("Enter the city.")
    clash = (
        Site.objects.filter(name__iexact=name, city__iexact=city)
        .exclude(pk=getattr(site, "pk", None))
        .first()
    )
    if clash:  # name the saved site as it is spelled, not as it was typed
        raise ComplaintError(f"{clash} already exists. Pick it from the list.")
    site = site or Site()
    site.name, site.city = name, city
    site.contact_name = _limit(_tidy(data.get("contact_name")), CONTACT_MAX, "contact person")
    site.phone = _phone(data.get("phone"), allow_landline=True)
    site.address = (data.get("address") or "").replace(chr(0), "").strip()
    try:
        with transaction.atomic():
            site.save()
    except IntegrityError as exc:  # someone saved the same site a moment ago
        raise ComplaintError(f"{name}, {city} already exists. Pick it from the list.") from exc
    return site


@transaction.atomic
def save_technician(*, name, phone="", technician=None):
    """Create (technician=None) or update a technician. The phone is a mobile only."""
    name = _limit(_tidy(name), TECH_NAME_MAX, "name")
    if not name:
        raise ComplaintError("Enter the name of the technician.")
    clash = Technician.objects.filter(name__iexact=name).exclude(pk=getattr(technician, "pk", None)).first()
    if clash:  # name the saved technician as spelled ("Suresh"), not as typed ("suresh")
        raise ComplaintError(f"{clash.name} is already in the list.")
    technician = technician or Technician()
    technician.name, technician.phone = name, _phone(phone, allow_landline=False)
    try:
        with transaction.atomic():
            technician.save()
    except IntegrityError as exc:
        raise ComplaintError(f"{name} is already in the list.") from exc
    return technician


def set_active(obj, *, active):
    """Show or hide a site or technician in the dropdowns (Admin only; the view checks the role).
    A site with open complaints can't be hidden: record_visit refuses hidden sites, so those complaints
    would be stuck. A technician can be hidden while assigned (the view says how many are still open)."""
    if not active and isinstance(obj, Site):
        n = obj.complaints.filter(status__in=OPEN_STATUSES).count()
        if n:
            raise ComplaintError(f"{obj} has {n} open complaint(s). Close them before hiding the site.")
    obj.is_active = active
    obj.save(update_fields=["is_active"])
    return obj


# ---------------------------------------------------------------- complaints


def _log(complaint, to, *, at, user, note="", reason=""):
    """Record a status change (append-only event) and apply it to the locked complaint."""
    ComplaintEvent.objects.create(
        complaint=complaint,
        from_status=complaint.status,
        to_status=to,
        at=at,
        by=user,
        note=note,
        reason=reason,
    )
    complaint.status = to
    complaint.closed_on = at if to in (Status.CLOSED, Status.NOT_COVERED) else None  # reopened: open again
    complaint.not_covered_reason = reason  # only a move to Not covered has one
    complaint.save(update_fields=["status", "closed_on", "not_covered_reason"])


@transaction.atomic
def file_complaint(
    *,
    site,
    company,
    fault,
    reported_on,
    user,
    company_ref="",
    qty_affected=None,
    priority=Priority.NORMAL,
    technicians=(),
    contact_name=None,
    phone=None,
):
    """A new complaint, Not attended, with its 'Complaint filed' event dated `reported_on`.
    Contact and phone default to the site's; pass them to override (the phone may be a landline)."""
    if site is None:
        raise ComplaintError("Choose the site.")
    if company is None:
        raise ComplaintError("Choose the company whose product failed.")
    _check_shown(site=site, technicians=technicians)
    fault = clean_text(fault)
    if not fault:
        raise ComplaintError("Describe the fault.")
    if reported_on is None:
        raise ComplaintError("Choose the date the complaint was reported.")
    if reported_on > timezone.localdate():
        raise ComplaintError("The reported date can't be in the future.")
    if qty_affected is not None and (
        not isinstance(qty_affected, int) or isinstance(qty_affected, bool) or qty_affected < 1
    ):
        raise ComplaintError("Quantity affected must be a whole number of 1 or more.")
    if priority not in Priority.values:
        raise ComplaintError("Choose the priority.")
    company_ref = _limit(_tidy(company_ref), COMPANY_REF_MAX, "company complaint no.")
    contact_name = _limit(
        _tidy(site.contact_name if contact_name is None else contact_name), CONTACT_MAX, "contact person"
    )
    phone = _phone(site.phone if phone is None else phone, allow_landline=True)
    complaint = Complaint.objects.create(
        number=next_number("CMP"),
        site=site,
        company=company,
        company_ref=company_ref,
        fault=fault,
        qty_affected=qty_affected,
        reported_on=reported_on,
        priority=priority,
        contact_name=contact_name,
        phone=phone,
        created_by=user,
    )
    complaint.technicians.set(technicians)  # ComplaintTechnician rows (no extra fields, so set() works)
    ComplaintEvent.objects.create(
        complaint=complaint, to_status=Status.NOT_ATTENDED, at=reported_on, by=user, note="Complaint filed"
    )
    return complaint


def _locked(complaint):
    return Complaint.objects.select_for_update().get(pk=complaint.pk)


@transaction.atomic
def reopen(*, complaint, user, note, at=None):
    """Admin only: a Closed complaint goes back to Attended. The reason is logged ('Reopened: …')."""
    complaint = _locked(complaint)
    if complaint.status != Status.CLOSED:
        raise ComplaintError("Only a closed complaint can be reopened.")
    if not has_role(user, ADMIN):
        raise ComplaintError("A closed complaint can't move to Attended. Only Admin can reopen it.")
    note = clean_text(note)
    if not note:
        raise ComplaintError("Write why the complaint is being reopened.")
    _limit(note, NOTE_MAX - len(REOPENED), "note")
    at = at or timezone.localdate()
    _check_day(complaint, at, what="The date")
    _log(complaint, Status.ATTENDED, at=at, user=user, note=REOPENED + note)
    return complaint


@transaction.atomic
def change_status(*, complaint, to, user, note="", reason="", at=None):
    """Move a complaint to `to`, checked against TRANSITIONS, and log it. `at` defaults to today; it can't be
    in the future, before the complaint was reported, or before its last change. Closed -> Attended is a
    reopen (Admin only, needs a note). Not covered needs a reason (and a note when the reason is Other)."""
    complaint = _locked(complaint)
    if complaint.status == Status.CLOSED and to == Status.ATTENDED:
        return reopen(complaint=complaint, user=user, note=note, at=at)
    if to not in Status.values:
        raise ComplaintError("Choose the new status.")
    if complaint.status == to:
        raise ComplaintError(f"This complaint is already {_label(to)}.")
    allowed = TRANSITIONS[complaint.status]
    if to not in allowed:
        message = f"A complaint that is {_label(complaint.status)} can't move to {_label(to)}."
        if allowed:
            message += f" Allowed: {', '.join(_label(s) for s in allowed)}."
        raise ComplaintError(message)
    note = _limit(clean_text(note), NOTE_MAX, "note")
    if to == Status.NOT_COVERED:
        if reason not in NotCoveredReason.values:
            raise ComplaintError("Choose why the complaint is not covered.")
        if reason == NotCoveredReason.OTHER and not note:
            raise ComplaintError("Write a note when the reason is Other.")
    else:
        reason = ""
    at = at or timezone.localdate()
    _check_day(complaint, at, what="The date")
    _log(complaint, to, at=at, user=user, note=note, reason=reason)
    return complaint


def close_not_covered(*, complaint, reason, user, note="", at=None):
    """Close a complaint that isn't ours to do (any open status), with a reason."""
    return change_status(
        complaint=complaint, to=Status.NOT_COVERED, user=user, note=note, reason=reason, at=at
    )


# ---------------------------------------------------------------- visits


def visit_next_options(complaint):
    """Statuses a visit can leave this complaint in (a visit never closes it)."""
    if complaint.status == Status.NOT_ATTENDED:
        return list(WORK_STATUSES)  # a first visit logs Not attended -> Attended, then moves on from there
    allowed = TRANSITIONS[complaint.status]
    return [s for s in WORK_STATUSES if s == complaint.status or s in allowed]


def _qty_ok(qty, top=None):
    return isinstance(qty, int) and not isinstance(qty, bool) and qty >= 1 and (top is None or qty <= top)


def _clean_parts(parts):
    """[(item, qty)] checked: an item and a whole quantity of 1 or more on each line."""
    for n, (item, qty) in enumerate(parts, start=1):
        if item is None:
            raise ComplaintError(f"Parts given, line {n}: choose the item.")
        if not _qty_ok(qty):
            raise ComplaintError(f"Parts given, line {n}: quantity must be 1 or more.")
    return list(parts)


def _clean_collected(collected):
    """[(item, qty, batch_code, pkd, fault)] checked and tidied before anything is posted (a batch code too
    long for the ledger line would otherwise fail in the database, not with a message)."""
    cleaned = []
    for n, (item, qty, batch_code, pkd, fault) in enumerate(collected, start=1):
        where = f"Failed parts, line {n}"
        if item is None:
            raise ComplaintError(f"{where}: choose the item.")
        if not _qty_ok(qty, MAX_PIECES_PER_LINE):
            raise ComplaintError(f"{where}: quantity must be between 1 and {MAX_PIECES_PER_LINE}.")
        batch_code, fault = _tidy(batch_code), clean_text(fault)
        if len(batch_code) > BATCH_CODE_MAX:
            raise ComplaintError(f"{where}: keep the batch code to {BATCH_CODE_MAX} characters or less.")
        if len(fault) > FAULT_MAX:
            raise ComplaintError(f"{where}: keep the fault to {FAULT_MAX} characters or less.")
        cleaned.append((item, qty, batch_code, pkd, fault))
    return cleaned


@transaction.atomic
def record_visit(
    *, complaint, visit_date, technicians, work_done, next_status, user, location=None, parts=(), collected=()
):
    """One visit, all or nothing: the parts given (one Stock OUT, subtype COMPLAINT, from `location`), the
    failed parts collected (one Stock IN at the Defective store, subtype DEFECTIVE_COLLECTED, then one
    collect_pieces call per line: one tagged piece per unit) and the status change. Both entries name the
    complaint. Returns the Visit.

    parts: [(item, qty)]. collected: [(item, qty, batch_code, pkd, fault)], qty 1 to 200 per line.
    Raises ComplaintError and saves nothing (not even a visit number) if any rule is broken.

    Why two post_entry calls here can't deadlock. The defectives services post at most one entry per call:
    post_entry locks its balance rows and then its EntryCounter, so a second post_entry would lock more
    balance rows while holding an EntryCounter, the reverse of every other entry. Posted naively, this visit
    holds EntryCounter(OUT) while it waits for Defective-store balance rows, and `dispatch` (store balances,
    then EntryCounter(OUT)) or `mark_defective` (good and store balances in one sorted pass) can be holding
    exactly those rows while waiting for ours: a cycle. So this service first locks EVERY balance row both
    entries need, good locations and the Defective store together, in one sorted pass (lock_balances), and
    only then posts. The two post_entry calls get `locked=` and re-lock only rows this transaction already
    holds (no waiting), so the only new locks after the balances are EntryCounter(OUT), then EntryCounter(IN),
    then the DEF counter.
    The order is then: Complaint row, VIS counter, all balances (sorted), EntryCounter OUT, EntryCounter IN,
    DEF counter. Checked against every other writer:
    - Stock IN / OUT / Transfer / Adjust / Undo, mark_defective, scrap, dispatch, settle, undo_visit_parts:
      each locks its balances in one sorted pass and then one EntryCounter, with nothing balance-related
      after it, so they take balances before counters just as this service does.
    - Nothing else takes two EntryCounters, so OUT-before-IN here can't meet IN-before-OUT anywhere.
    - The VIS counter is taken only here; the Complaint row only by these complaint services, first.
    - The DEF counter is last everywhere (mark_defective and this service).
    """
    complaint = Complaint.objects.select_for_update(of=("self",)).select_related("site").get(pk=complaint.pk)
    if not complaint.is_open:
        raise ComplaintError(f"This complaint is {_label(complaint.status)}, so visits can't be added.")
    if visit_date is None:
        raise ComplaintError("Choose the visit date.")
    _check_day(complaint, visit_date, what="The visit date", last_change=False)
    if not technicians:
        raise ComplaintError("Choose who attended.")
    _check_shown(site=complaint.site, technicians=technicians)
    work_done = clean_text(work_done)
    if not work_done:
        raise ComplaintError("Write what work was done.")
    if next_status not in Status.values:
        raise ComplaintError("Choose the status after the visit.")
    options = visit_next_options(complaint)
    if next_status not in options:
        raise ComplaintError(
            f"A complaint that is {_label(complaint.status)} can't move to {_label(next_status)}. "
            f"After a visit it can be: {', '.join(_label(s) for s in options)}."
        )
    if (
        next_status != complaint.status
    ):  # the visit logs a status change, so it must keep the history in order
        last = complaint.events.aggregate(last=Max("at"))["last"]
        if last and visit_date < last:
            raise ComplaintError(
                f"This complaint last changed status on {last:%d-%m-%Y}. A visit dated before that can't "
                f"change the status; leave it {_label(complaint.status)}."
            )
    parts, collected = _clean_parts(parts), _clean_collected(collected)
    if parts and location is None:
        raise ComplaintError("Choose the location the parts were given from.")
    if parts and location.is_defective_store:
        raise ComplaintError("Choose a good-stock location for the parts given.")

    number = next_number("VIS")  # the visit's own new number first: the documented exception
    store = Location.defective_store() if collected else None
    out_lines = [Line(item, location, -qty) for item, qty in parts]
    in_lines = [Line(item, store, qty, batch_code, pkd) for item, qty, batch_code, pkd, _ in collected]
    locked = lock_balances(out_lines + in_lines)  # every balance row, one sorted pass, before any counter
    common = {
        "entry_date": visit_date,
        "user": user,
        "party": str(complaint.site)[:PARTY_MAX],  # the ref (complaint number) is the link; this is a label
        "ref": complaint.number,
        "note": f"Visit {number}",
        "complaint": complaint,
        "locked": locked,
    }
    out = col = None
    if out_lines:
        try:
            out = post_entry(kind=EntryKind.OUT, lines=out_lines, subtype=ServiceSubtype.COMPLAINT, **common)
        except StockError as exc:
            raise ComplaintError(f"Parts given: {exc.message}") from exc
    if in_lines:
        try:
            col = post_entry(
                kind=EntryKind.IN, lines=in_lines, subtype=ServiceSubtype.DEFECTIVE_COLLECTED, **common
            )
        except StockError as exc:
            raise ComplaintError(f"Failed parts: {exc.message}") from exc
    visit = Visit.objects.create(
        number=number,
        complaint=complaint,
        visit_date=visit_date,
        work_done=work_done,
        next_status=next_status,
        location=location if out else None,
        out_entry=out,
        collect_entry=col,
        created_by=user,
    )
    # VisitTechnician / ComplaintTechnician rows: the through models have no extra fields, so set()/add()
    # work. add() skips technicians already on the complaint.
    visit.technicians.set(technicians)
    complaint.technicians.add(*technicians)
    for n, (item, qty, batch_code, pkd, fault) in enumerate(collected, start=1):
        try:
            collect_pieces(
                entry=col,
                item=item,
                qty=qty,
                source=Source.SITE_VISIT,
                collected_on=visit_date,
                user=user,
                batch_code=batch_code,
                pkd=pkd,
                fault=fault,
                visit=visit,
                note=f"Collected at site ({complaint.number}, {number})",
            )
        except DefectiveError as exc:
            raise ComplaintError(f"Failed parts, line {n}: {exc.message}") from exc
    if complaint.status == Status.NOT_ATTENDED:
        _log(complaint, Status.ATTENDED, at=visit_date, user=user, note=f"Visit {number}")
    if next_status != complaint.status:
        _log(complaint, next_status, at=visit_date, user=user, note=f"Visit {number}")
    return visit


@transaction.atomic
def undo_visit_parts(*, visit, reason, user, at=None):
    """Cancel a visit's parts given: posts the exact reversal of its Stock OUT (kind REV, `reverses` the OUT)
    and returns it. The general Undo refuses a visit's entries, so this is the only way to correct them.

    The reversal keeps `complaint` set, so it shows on the complaint, and its note names the visit and the
    reason ('Parts given on VIS-0003 undone: …'): that entry is the complaint's record of the undo (complaint
    events are status moves only). The collected pieces and the complaint's status are not touched; pieces
    are corrected from the Defectives screens. Allowed on a finished complaint too (it corrects stock only).

    Lock order: Complaint row, then the OUT entry and its balances (_reverse_entry -> post_entry).
    """
    complaint = _locked(visit.complaint)
    visit = Visit.objects.select_related("out_entry").get(pk=visit.pk)
    out = visit.out_entry
    if out is None:
        raise ComplaintError(f"Visit {visit.number} gave no parts, so there is nothing to undo.")
    reason = _tidy(reason)
    if not reason:
        raise ComplaintError("Write why the parts given are being undone.")
    _limit(reason, NOTE_MAX, "reason")
    at = at or timezone.localdate()
    if at > timezone.localdate():
        raise ComplaintError("The date can't be in the future.")
    if at < out.entry_date:
        raise ComplaintError(f"The undo can't be dated before the visit ({out.entry_date:%d-%m-%Y}).")
    done = StockEntry.objects.filter(reverses=out).first()
    if done:
        raise ComplaintError(f"The parts given on {visit.number} were already undone ({done.number}).")
    used = f"The parts given on {visit.number} have already been used, so they can't be undone."
    try:
        return _reverse_entry(
            entry=out,
            note=f"Parts given on {visit.number} undone: {reason}",
            user=user,
            entry_date=at,
            complaint=complaint,
            used_message=used,
        )
    except StockError as exc:
        raise ComplaintError(exc.message) from exc
