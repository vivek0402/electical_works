# Defective Pieces & Complaints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two linked service modules to the SVKML app, matching the approved mockup (`mockups/service/`) and the spec (`docs/superpowers/specs/2026-10-12-defectives-complaints-design.md`). **Defective pieces** tracks every failed part one physical piece at a time, from collection through a return batch to the company's answer. **Complaints** logs customer-site complaints, assigns technicians and records visits; a visit posts a real Stock OUT for the parts given and creates tagged defective pieces for the failed parts collected.

**Architecture:** Two new Django apps, `apps/defectives` and `apps/complaints`, built the same way as `apps/inventory`. All writes go through `services.py` (one transaction each, rules checked there, every stock effect posted with the existing `inventory.services.post_entry`). All reads live in `selectors.py`. Views are thin function views guarded by `role_required`. Each piece and each complaint has an append-only event table (pgtrigger `append_only`) and a `TRANSITIONS` dict instead of a state-machine library. A dedicated **Defective store** location sits in the same ledger; it is flagged `is_defective_store`, kept out of every good-stock figure and form, and shown as its own column.

**Tech Stack:** Python 3.12, Django 5.2.18, PostgreSQL 16, django-pgtrigger, XlsxWriter, Tabler 1.6.1 + Tabler Icons 3.49.0 + Tom Select 2.6.2 (all vendored, no build step), pytest + pytest-django, Playwright for the browser walkthrough.

---

## Decisions locked in (do not revisit while executing)

Taken from the spec and the approved mockup. Where this plan adds or changes something, it says so under **Divergences**.

- **One app, linked modules.** A visit posts a Stock OUT (subtype `COMPLAINT`) for the parts given and a Stock IN at the Defective store (subtype `DEFECTIVE_COLLECTED`) for the failed parts collected, both linked to the complaint, all in one transaction.
- **One physical piece = one `DefectivePiece`** with its own tag `DEF-0001`. A collected line of quantity 3 makes 3 tags.
- **No company is special.** Wipro is one company in the Company master. A piece's company is copied from its item. A return batch is for one company. A complaint records which company's product failed and the company's own ticket number (`company_ref`, optional, indexed, not unique). No company name appears in code, statuses or labels; `settings.DEFAULT_COMPANY` is only the starting value of a dropdown.
- **Settlement outcomes:** `REPLACED` and `REPAIRED` post a Stock IN (subtype `REPLACEMENT`) into a good location. `REJECTED_RETURNED` posts a Stock IN (subtype `DEFECTIVE_RETURNED`) back into the Defective store and the piece is back in store. `REJECTED_SCRAPPED` posts nothing (the piece already left with the dispatch OUT). No credit notes.
- **Defective store:** a `Location` flagged `is_defective_store` (exactly one, created by a data migration). Good-stock totals, low stock, the dashboard and the entry-form location pickers exclude it. Current stock and the item card show it as a separate "Defective store (not counted)" figure. It can't be hidden.
- **Complaint statuses:** Not attended → Attended → Material need to check → Awaiting material → Resolved → Closed, plus **Not covered** from any open status with a reason (Not our product, Out of warranty, Customer cancelled, Other; Other needs a note). Every change is an append-only `ComplaintEvent`. Only Admin can reopen a Closed complaint; reopening moves it to Attended and needs a note.
- **Transitions** (exactly the mockup's dict):

  | From | Allowed to |
  |---|---|
  | Not attended | Attended, Not covered |
  | Attended | Material need to check, Awaiting material, Resolved, Not covered |
  | Material need to check | Attended, Awaiting material, Resolved, Not covered |
  | Awaiting material | Attended, Material need to check, Resolved, Not covered |
  | Resolved | Closed, Attended, Not covered |
  | Closed | (none; Admin reopen → Attended) |
  | Not covered | (none) |

- **Piece statuses:** `IN_STORE` → `IN_BATCH` (draft batch) → `SENT` → `SETTLED`; `IN_STORE` → `SCRAPPED`; `IN_BATCH` → `IN_STORE` (removed from the draft); `SENT` → `IN_STORE` (rejected and sent back).
- **Batch status** is stored as `DRAFT` or `DISPATCHED`. "Partly settled" and "Settled" are worked out from the lines, never stored. A batch is locked once dispatched.
- **Age** = (closed_on or today) − reported_on. **Days awaiting material** = the sum of the intervals spent in Awaiting material, worked out from the events.
- **Sites** are saved and picked from a searchable dropdown; "＋ New site" opens a modal. **Technicians** are a names-only list and never log in. Office staff file complaints.
- **Permissions:** OFFICE can do everything in both modules, including adding and editing sites and technicians. ADMIN only: hiding a site or technician, reopening a closed complaint, the existing masters page.
- **Undo:** a visit's parts-given OUT can be undone like any OUT. Every entry the defectives screens own (collection, mark defective, dispatch, settlement, scrap) refuses Undo with "This entry belongs to the defective pieces. Use the Defectives screens instead of Undo."
- **UI rules (lessons.md):** proper controls only (date pickers, Tom Select searchable selects, number inputs, radio pill groups); lists show clean app columns; Excel is a download only; colour always comes with an icon or a word; IN blue / OUT orange; red = needs attention, amber = waiting, green = done well, slate = neutral.
- **Demo data:** the approved `mockups/service/demo-data.json` (31 items, 78 ledger entries, 18 sites, 4 technicians, 26 complaints, 22 visits, 60 pieces, 3 return batches, several companies) is copied into the app and replayed through the services by a new `seed_service_demo` command. `make demo` uses it.

### Divergences from the spec or mockup (follow these)

1. **Two extra internal subtypes.** Besides the spec's five (`REPLACEMENT`, `COMPLAINT`, `DEFECTIVE_COLLECTED`, `RETURN_TO_COMPANY`, `DEFECTIVE_RETURNED`), the mark-defective transfer is posted with subtype `MARK_DEFECTIVE` and the scrap adjustment with `SCRAP_DEFECTIVE`. The real `_validate` refuses a subtype on TRF/ADJ today; the subtype makes the Undo block and the "Marked defective" / "Defective pieces scrapped" labels exact without guessing from lines or party names. They are never offered on a stock form.
2. **`StockEntry.subtype` grows from 10 to 20 characters** (`DEFECTIVE_COLLECTED` is 19).
3. **`BatchLine` model (new).** The spec keeps `outcome` on the piece only. A piece rejected and sent back can go out again in a later batch, and the first batch must still show its answer (the mockup keeps `batch.lines[].outcome`). `BatchLine(batch, piece, outcome, settled_on, to_location, entry)` holds the per-batch answer; `DefectivePiece.outcome/settled_on/return_batch/replacement_entry` keep the latest values as the spec says.
4. **`DefectiveEvent.entry` (new FK).** Each piece event records the ledger entry that moved it. The entry detail page uses it to list the pieces an entry touched; the spec's piece fields stay as written.
5. **Service signatures are keyword-only and take lists**, following the real code (`post_entry(*, ...)`): `mark_defective(*, location, lines, entry_date, user)` takes several `(item, qty, fault)` lines (the mockup's Mark defective form has several lines; the spec wrote one item), and `settle(*, batch, pieces, outcome, settled_on, user, to_location=None)` names the batch.
6. **Site uniqueness is name + city** (ignoring case), as the mockup does ("Andhra University, Visakhapatnam" and "Andhra University, Guntur" are different sites). The spec said name only.
7. **Courier is a text box with suggestions** (`<datalist>` from `settings.COURIERS` plus couriers used before), not a closed dropdown: couriers change and the mockup's list was demo data.
8. **One numbering helper** `apps/core/numbers.next_number(prefix)` backed by a `core.Counter` row per series (`DEF`, `RB`, `CMP`, `VIS`), the same lock-and-increment pattern as `EntryCounter` (which stays as it is: its `kind` column only allows the five entry kinds).
9. **A new `static/js/line-editor.js`** (a generalised copy of the item-line logic in `entry-form.js`) powers Mark defective and Record visit, which need two editors on one page and extra Fault / Batch / PKD columns. `entry-form.js` is left untouched so the four stock forms cannot regress.
10. **Movements export:** the new "Complaint" and "Return batch" columns go at the end (the sample put them before "Batch code"), so the existing tests that read the Note column by position keep passing.
11. **Filing event date:** the "Complaint filed" event is dated `reported_on` (the mockup used today) so age and the timeline agree.

## Local test environment (this Windows machine has no Docker)

PostgreSQL 16 runs locally; pytest creates its own test database on it. **The port changes after a reboot:** check the port your local PostgreSQL is listening on (line 4 of its data directory's `postmaster.pid`) and use it in place of `<port>` below.

```bash
DATABASE_URL="postgresql://postgres:@127.0.0.1:<port>/postgres" uv run pytest -q
uv run ruff format --check . && uv run ruff check .
```

The dev database for browser checks is `svkml_demo`:

```bash
export DATABASE_URL="postgresql://postgres:@127.0.0.1:<port>/svkml_demo"
uv run python manage.py migrate
SEED_PASSWORD="<strong password>" uv run python manage.py seed_users
uv run python manage.py seed_service_demo      # after Task 17; empty ledger only
uv run python manage.py runserver 8000
```

Every task ends with the full suite green (`uv run pytest -q`) and ruff clean: run `uv run ruff format . && uv run ruff check --fix .` before each commit (code in this plan is written for readability; let the formatter wrap long lines). Migrations are generated with `uv run python manage.py makemigrations ...` exactly as each task says and committed with the task.

## File structure

```
config/settings/base.py                    + apps.defectives, apps.complaints in INSTALLED_APPS; COURIERS
apps/core/
  models.py                                Counter (last number per series)                       [new]
  numbers.py                               next_number("DEF") -> "DEF-0001"                       [new]
  tokens.py                                one-time form tokens (moved out of inventory/views.py)  [new]
  migrations/0001_initial.py               generated                                              [new]
  templatetags/core_tags.py                + st_badge (colour + icon + word)
apps/inventory/
  models.py                                Location.is_defective_store + .good(); ServiceSubtype; StockEntry
                                           subtype 20 chars, return_batch + complaint FKs, is_defective
  services.py                              _validate service subtypes + Defective store rules; undo block;
                                           post_entry(return_batch=, complaint=)
  selectors.py                             good stock only; defective column; default_location(); movement links
  filters.py / forms.py / views.py         store excluded from filters, pickers, entry forms; item card figure
  masters.py                               store can't be hidden
  exports.py                               current stock: Defective column; movements: Complaint / Return batch
  entry_lines.py                           raw_lines(prefix); fault column; collect / mark modes; allow_empty
  context_processors.py                    NAV gains Complaints + Defectives sections and two badges
  management/commands/seed_stock_demo.py   load_masters_and_items() shared with the service seed
  migrations/0005..0008                    store flag + subtype length, store row, return_batch FK, complaint FK
apps/defectives/                                                                                   [new app]
  apps.py models.py                        PieceStatus/Outcome/Source/BatchStatus/ScrapReason, TRANSITIONS,
                                           ReturnBatch, DefectivePiece, BatchLine, DefectiveEvent
  services.py                              create_piece, mark_defective, scrap, create_batch, add_pieces,
                                           remove_pieces, dispatch, settle, normalise_tag
  selectors.py filters.py forms.py         reads, list filters, MarkDefective/Dispatch/Settle forms
  views.py urls.py exports.py              screens and the two Excel downloads
  templatetags/defective_tags.py           piece / outcome / batch badges, pkd_month
  migrations/0001_initial.py 0002_defectivepiece_visit.py
apps/complaints/                                                                                   [new app]
  apps.py models.py                        Status/Priority/NotCoveredReason, TRANSITIONS, Site, Technician,
                                           Complaint, ComplaintEvent, Visit
  services.py                              save_site, save_technician, set_active, file_complaint,
                                           change_status, reopen, close_not_covered, visit_next_options,
                                           record_visit
  selectors.py filters.py forms.py         age, awaiting days, rows, dashboard, sites, technicians
  views.py urls.py exports.py              screens and the two Excel downloads
  templatetags/complaint_tags.py           status / priority / age badges
  demo/service-demo.json                   copy of mockups/service/demo-data.json
  management/commands/seed_service_demo.py replay the demo through the services
  migrations/0001_initial.py
templates/
  base.html                                nav badges for open complaints and pieces in store
  inventory/current_stock.html item_detail.html entry_detail.html movements.html dashboard.html
  defectives/  mark.html pieces.html piece_detail.html batches.html batch_new.html batch_detail.html
               dashboard.html _source.html
  complaints/  dashboard.html list.html form.html detail.html visit.html sites.html site_detail.html
               site_form.html technicians.html technician_form.html _bars.html _site_modal.html
static/
  css/app.css                              service styles (status badges, chips, timeline, defective column)
  js/line-editor.js                        LineEditor + auto-wiring of [data-lines] editors          [new]
  js/service.js                            data-ts selects, tick-all boxes, settle panel, submit-once [new]
  js/site-picker.js                        site picker + New site modal (New complaint, Sites)       [new]
  js/app.js                                global search shows complaints, sites and pieces
tests/
  factories.py                             store(), give_stock(), make_pieces(), make_site(), make_tech(),
                                           make_complaint()
  core/test_numbers.py
  inventory/test_defective_store.py test_good_stock.py
  defectives/ test_models.py test_piece_services.py test_batch_services.py test_mark_view.py
              test_batch_views.py test_pieces_views.py test_dashboard_exports.py
  complaints/ test_models.py test_services.py test_list_dashboard.py test_complaint_views.py
              test_visit_view.py test_sites_techs.py test_seed_service_demo.py
  test_integration_service.py test_permissions.py
  inventory/test_search.py test_dashboard.py test_masters.py test_entry_lines.py   (updated)
e2e/walkthrough.py                         + service flows (desktop) and complaints on a phone
README.md CLAUDE.md Makefile tasks/todo.md docs
```

---

### Task 1: Defective store location and service entry subtypes

**Files:**
- Modify: `apps/inventory/models.py` (Location, new `ServiceSubtype` and subtype sets, `StockEntry.subtype`, `details`, `is_defective`)
- Create: generated `apps/inventory/migrations/0005_defective_store.py`, hand-written `apps/inventory/migrations/0006_create_defective_store.py`
- Modify: `apps/inventory/services.py` (`_validate`, `undo_entry`)
- Modify: `apps/inventory/views.py` (`entry_detail`), `templates/inventory/entry_detail.html`
- Modify: `tests/factories.py` (add `store`), `tests/inventory/test_masters.py` (`test_masters_seeded`)
- Test: `tests/inventory/test_defective_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/factories.py` (below `loc`):
```python
def store():
    """The Defective store (created by migration inventory 0006)."""
    return Location.defective_store()
```

Create `tests/inventory/test_defective_store.py`:
```python
import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.inventory.models import AdjustReason, EntryKind, Location, ServiceSubtype, StockEntry
from apps.inventory.services import Line, StockError, post_entry, undo_entry
from tests.factories import loc, make_item, make_user, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def user(db):
    return make_user("clerk", "OFFICE")


@pytest.fixture
def drv(db):
    return make_item("LG78-150-700")


def post(kind, *lines, user, **kw):
    return post_entry(kind=kind, entry_date=TODAY, lines=list(lines), user=user, **kw)


def stock(item, qty, user):
    return post(EntryKind.IN, Line(item, loc(), qty), user=user, subtype="SUPPLIER")


def collect(item, qty, user):
    return post(EntryKind.IN, Line(item, store(), qty), user=user, subtype=ServiceSubtype.DEFECTIVE_COLLECTED)


def test_migration_creates_one_active_defective_store():
    s = Location.defective_store()
    assert s.name == "Defective store" and s.is_active
    assert list(Location.objects.filter(is_defective_store=True)) == [s]
    assert s not in Location.objects.good()
    assert set(Location.objects.good().values_list("name", flat=True)) == {
        "Vizag Office",
        "Svkml",
        "TV Shop",
        "Kartika Class",
    }


def test_only_one_defective_store():
    with pytest.raises(IntegrityError), transaction.atomic():
        Location.objects.create(name="Second store", is_defective_store=True)


def test_collection_and_dispatch_post_at_the_store(drv, user):
    e = collect(drv, 2, user)
    assert e.details == "Failed parts collected at site" and e.is_defective
    e.refresh_from_db()
    assert e.subtype == "DEFECTIVE_COLLECTED"  # 19 characters fit
    out = post(EntryKind.OUT, Line(drv, store(), -2), user=user, subtype=ServiceSubtype.RETURN_TO_COMPANY)
    assert out.details == "Defectives returned to company" and out.is_defective


def test_store_subtype_refused_at_a_good_location(drv, user):
    with pytest.raises(StockError, match="must be posted at the Defective store"):
        post(EntryKind.IN, Line(drv, loc(), 1), user=user, subtype=ServiceSubtype.DEFECTIVE_COLLECTED)


def test_ordinary_entries_cannot_touch_the_store(drv, user):
    with pytest.raises(StockError, match="managed from the Defectives screens"):
        post(EntryKind.IN, Line(drv, store(), 1), user=user, subtype="SUPPLIER")
    stock(drv, 3, user)
    with pytest.raises(StockError, match="managed from the Defectives screens"):
        post(EntryKind.TRF, Line(drv, loc(), -1), Line(drv, store(), 1), user=user)


def test_mark_defective_is_a_transfer_into_the_store(drv, user):
    stock(drv, 3, user)
    e = post(
        EntryKind.TRF,
        Line(drv, loc(), -1),
        Line(drv, store(), 1),
        user=user,
        subtype=ServiceSubtype.MARK_DEFECTIVE,
    )
    assert e.details == "Marked defective" and e.is_defective
    with pytest.raises(StockError, match="from a good location into the Defective store"):
        post(
            EntryKind.TRF,
            Line(drv, loc(), -1),
            Line(drv, loc("TV Shop"), 1),
            user=user,
            subtype=ServiceSubtype.MARK_DEFECTIVE,
        )


def test_service_subtype_must_match_the_kind(drv, user):
    with pytest.raises(StockError, match="Choose where the stock came from"):
        post(EntryKind.IN, Line(drv, loc(), 1), user=user, subtype=ServiceSubtype.COMPLAINT)
    with pytest.raises(StockError, match="don't take a type"):
        post(
            EntryKind.ADJ,
            Line(drv, loc(), 1),
            user=user,
            subtype=ServiceSubtype.MARK_DEFECTIVE,
            reason=AdjustReason.FOUND,
            note="x",
        )


def test_scrap_is_an_adjustment_at_the_store(drv, user):
    collect(drv, 1, user)
    e = post(
        EntryKind.ADJ,
        Line(drv, store(), -1),
        user=user,
        subtype=ServiceSubtype.SCRAP_DEFECTIVE,
        reason=AdjustReason.DAMAGED,
        note="Scrapped DEF-0001",
    )
    assert e.details == "Defective pieces scrapped" and e.is_defective


def test_complaint_out_is_ordinary_and_can_be_undone(drv, user):
    stock(drv, 3, user)
    e = post(
        EntryKind.OUT,
        Line(drv, loc(), -1),
        user=user,
        subtype=ServiceSubtype.COMPLAINT,
        party="BARC, Visakhapatnam",
    )
    assert e.details == "Parts given at complaint visit" and not e.is_defective
    assert undo_entry(entry=e, reason="typed twice", user=user).kind == EntryKind.REV


def test_replacement_in_goes_to_good_stock(drv, user):
    e = post(EntryKind.IN, Line(drv, loc(), 1), user=user, subtype=ServiceSubtype.REPLACEMENT)
    assert e.details == "Replacement / repaired piece from company" and e.is_defective


def test_defective_entries_cannot_be_undone(drv, user):
    e = collect(drv, 1, user)
    with pytest.raises(StockError, match="Use the Defectives screens instead of Undo"):
        undo_entry(entry=e, reason="oops", user=user)
    assert not StockEntry.objects.filter(kind=EntryKind.REV).exists()


def test_entry_page_hides_undo_for_defective_entries(office_client, office_user, drv):
    e = collect(drv, 1, office_user)
    html = office_client.get(f"/entries/{e.number}/").content.decode()
    assert "Undo this entry" not in html and "belongs to the defective pieces" in html
    assert office_client.post(f"/entries/{e.number}/undo/", {"reason": "x"}).status_code == 302
    assert not StockEntry.objects.filter(kind=EntryKind.REV).exists()
```

In `tests/inventory/test_masters.py`, change the first assertion of `test_masters_seeded` to read good locations only:
```python
def test_masters_seeded():
    assert set(Location.objects.good().values_list("name", flat=True)) == {
        "Vizag Office",
        "Svkml",
        "TV Shop",
        "Kartika Class",
    }
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/inventory/test_defective_store.py -q`
Expected: FAIL with `ImportError: cannot import name 'ServiceSubtype'`.

- [ ] **Step 3: Add the store flag and the subtypes to `apps/inventory/models.py`**

Replace `class Location(Master): pass` with:
```python
class LocationQuerySet(models.QuerySet):
    def good(self):
        """Locations that hold good stock: everything except the Defective store."""
        return self.filter(is_defective_store=False)


class Location(Master):
    # The one location that holds failed pieces. Only the defectives services post to it; it is never
    # offered on the stock forms and never counted as good stock.
    is_defective_store = models.BooleanField(default=False, editable=False)

    objects = LocationQuerySet.as_manager()

    class Meta(Master.Meta):
        constraints = [
            *Master.Meta.constraints,
            models.UniqueConstraint(
                fields=["is_defective_store"],
                condition=Q(is_defective_store=True),
                name="one_defective_store",
            ),
        ]

    @classmethod
    def defective_store(cls):
        return cls.objects.get(is_defective_store=True)
```

Below `class AdjustReason`, add:
```python
class ServiceSubtype(models.TextChoices):
    """Subtypes posted only by the complaints and defectives services, never chosen on a stock form."""

    REPLACEMENT = "REPLACEMENT", "Replacement / repaired piece from company"
    DEFECTIVE_COLLECTED = "DEFECTIVE_COLLECTED", "Failed parts collected at site"
    DEFECTIVE_RETURNED = "DEFECTIVE_RETURNED", "Rejected piece back from company"
    COMPLAINT = "COMPLAINT", "Parts given at complaint visit"
    RETURN_TO_COMPANY = "RETURN_TO_COMPANY", "Defectives returned to company"
    MARK_DEFECTIVE = "MARK_DEFECTIVE", "Marked defective"
    SCRAP_DEFECTIVE = "SCRAP_DEFECTIVE", "Defective pieces scrapped"


SERVICE_SUBTYPES = {
    EntryKind.IN: {ServiceSubtype.REPLACEMENT, ServiceSubtype.DEFECTIVE_COLLECTED, ServiceSubtype.DEFECTIVE_RETURNED},
    EntryKind.OUT: {ServiceSubtype.COMPLAINT, ServiceSubtype.RETURN_TO_COMPANY},
    EntryKind.TRF: {ServiceSubtype.MARK_DEFECTIVE},
    EntryKind.ADJ: {ServiceSubtype.SCRAP_DEFECTIVE},
}
# Every line of these entries is at the Defective store.
STORE_SUBTYPES = {
    ServiceSubtype.DEFECTIVE_COLLECTED,
    ServiceSubtype.DEFECTIVE_RETURNED,
    ServiceSubtype.RETURN_TO_COMPANY,
    ServiceSubtype.SCRAP_DEFECTIVE,
}
# Entries the defectives screens own. Undo is refused for them.
DEFECTIVE_SUBTYPES = STORE_SUBTYPES | {ServiceSubtype.MARK_DEFECTIVE, ServiceSubtype.REPLACEMENT}
```

In `StockEntry`, change the subtype field and its comment:
```python
    subtype = models.CharField(max_length=20, blank=True)  # InSource / OutTarget / ServiceSubtype
```

Replace the `details` property and add `is_defective` below it:
```python
    @property
    def details(self):
        """Short human description.

        e.g. 'From supplier', 'To site / customer', 'Damaged', 'Marked defective', 'Undo of OUT-0003'.
        """
        if self.subtype in ServiceSubtype.values:
            return ServiceSubtype(self.subtype).label
        if self.kind == EntryKind.IN:
            return InSource(self.subtype).label if self.subtype else ""
        if self.kind == EntryKind.OUT:
            return f"To {OutTarget(self.subtype).label.lower()}" if self.subtype else ""
        if self.kind == EntryKind.TRF:
            return "Between locations"
        if self.kind == EntryKind.ADJ:
            return self.get_reason_display()
        return f"Undo of {self.reverses.number}" if self.reverses_id else "Undo"

    @property
    def is_defective(self):
        """True for entries the defectives screens own (collection, mark, dispatch, settlement, scrap)."""
        return self.subtype in DEFECTIVE_SUBTYPES
```

- [ ] **Step 4: Generate the schema migration and write the data migration**

Run: `uv run python manage.py makemigrations inventory --name defective_store`
Expected: `apps/inventory/migrations/0005_defective_store.py` with `AddField location.is_defective_store`, `AddConstraint one_defective_store` and `AlterField stockentry.subtype (max_length=20)`.

Create `apps/inventory/migrations/0006_create_defective_store.py`:
```python
from django.db import migrations

NAME = "Defective store"


def create(apps, schema_editor):
    """Create (or flag an existing, same-named) Defective store. There is exactly one."""
    Location = apps.get_model("inventory", "Location")
    place = Location.objects.filter(name__iexact=NAME).first() or Location(name=NAME)
    place.is_defective_store = True
    place.is_active = True
    place.save()


def unflag(apps, schema_editor):
    apps.get_model("inventory", "Location").objects.filter(is_defective_store=True).update(
        is_defective_store=False
    )


class Migration(migrations.Migration):
    dependencies = [("inventory", "0005_defective_store")]
    operations = [migrations.RunPython(create, unflag)]
```

- [ ] **Step 5: Enforce the rules in `apps/inventory/services.py`**

Add `SERVICE_SUBTYPES`, `STORE_SUBTYPES` and `ServiceSubtype` to the `from .models import (...)` list.

In `_validate`, replace the block from `# Kind-specific checks for new entries.` down to (and including) the `raise StockError(f"{EntryKind(kind).label} entries don't take a type.")` line with:
```python
    # Kind-specific checks for new entries.
    service = SERVICE_SUBTYPES.get(kind, set())
    if kind == EntryKind.IN:
        if subtype and subtype not in InSource.values and subtype not in service:
            raise StockError("Choose where the stock came from.")
    elif kind == EntryKind.OUT:
        if subtype and subtype not in OutTarget.values and subtype not in service:
            raise StockError("Choose who the stock was issued to.")
    elif subtype and subtype not in service:
        raise StockError(f"{EntryKind(kind).label} entries don't take a type.")
```

In `_validate`, directly after the `inactive_place` check (before `label = EntryKind(kind).label`), add:
```python
    # Only the defectives services post to the Defective store, and their entries only post there.
    at_store = [line.location.is_defective_store for line in lines]
    if subtype in STORE_SUBTYPES and not all(at_store):
        raise StockError(f"{ServiceSubtype(subtype).label} must be posted at the Defective store.")
    if subtype == ServiceSubtype.MARK_DEFECTIVE and (all(at_store) or not any(at_store)):
        raise StockError("Marking defective moves stock from a good location into the Defective store.")
    if any(at_store) and subtype not in STORE_SUBTYPES and subtype != ServiceSubtype.MARK_DEFECTIVE:
        raise StockError("The Defective store is managed from the Defectives screens.")
```

In `undo_entry`, directly after the `if entry.kind == EntryKind.REV:` check, add:
```python
    if entry.is_defective:
        raise StockError(
            "This entry belongs to the defective pieces. Use the Defectives screens instead of Undo."
        )
```

- [ ] **Step 6: Hide Undo on defective entries (`views.entry_detail` + template)**

In `apps/inventory/views.py`, `entry_detail`, change the `can_undo` line:
```python
            "can_undo": entry.kind != EntryKind.REV and undone_by is None and not entry.is_defective,
```

In `templates/inventory/entry_detail.html`, directly after the `{% if entry.reverses %}...{% endif %}` alert line, add:
```html
{% if entry.is_defective %}<div class="alert alert-info"><div class="d-flex gap-2"><i class="ti ti-info-circle"></i><div>This entry belongs to the defective pieces, so it can't be undone here. Use the Defectives screens instead.</div></div></div>{% endif %}
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `uv run pytest tests/inventory -q`
Expected: PASS (all inventory tests, including the updated `test_masters_seeded`).

- [ ] **Step 8: Commit**

```bash
git add apps/inventory/models.py apps/inventory/services.py apps/inventory/views.py apps/inventory/migrations/0005_defective_store.py apps/inventory/migrations/0006_create_defective_store.py templates/inventory/entry_detail.html tests/factories.py tests/inventory/test_defective_store.py tests/inventory/test_masters.py
git commit -m "feat(inventory): Defective store location and service entry subtypes"
```

---

### Task 2: Good stock everywhere excludes the Defective store

**Files:**
- Modify: `apps/inventory/selectors.py`, `apps/inventory/filters.py` (`stock_filters`), `apps/inventory/forms.py` (location pickers), `apps/inventory/views.py` (`_masters`, `movements`, `current_stock`, `item_detail`, `_default_location`, `_entry_page`), `apps/inventory/masters.py` (`_refuse_hide`), `apps/inventory/exports.py` (`current_stock_xlsx`)
- Modify: `templates/inventory/current_stock.html`, `templates/inventory/item_detail.html`
- Modify: `static/css/app.css` (service styles used from here on)
- Test: `tests/inventory/test_good_stock.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/inventory/test_good_stock.py`:
```python
import io

import openpyxl
import pytest
from django.utils import timezone

from apps.inventory import selectors
from apps.inventory.models import EntryKind, Location, ServiceSubtype
from apps.inventory.services import Line, post_entry
from tests.factories import loc, make_item, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def stocked(office_user):
    """EIO6006: 6 good at Vizag Office (reorder 10) and 4 failed pieces in the Defective store."""
    a = make_item("EIO6006", reorder=10, spare_type="PCB / LED module")
    post_entry(kind=EntryKind.IN, entry_date=TODAY, lines=[Line(a, loc(), 6)], user=office_user, subtype="SUPPLIER")
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
    assert "Defective store (not counted)" in html and "never part of the total" in html


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
    html = admin_client.post("/masters/toggle/", {"kind": "location", "pk": s.pk}, follow=True).content.decode()
    s.refresh_from_db()
    assert s.is_active and "holds the defective pieces" in html


def test_last_good_location_rule_ignores_the_store(admin_client):
    Location.objects.good().exclude(name="TV Shop").update(is_active=False)
    place = loc("TV Shop")
    html = admin_client.post("/masters/toggle/", {"kind": "location", "pk": place.pk}, follow=True).content.decode()
    place.refresh_from_db()
    assert place.is_active and "At least one location must stay active" in html


def test_current_stock_export_lists_the_store_separately(office_client, stocked):
    ws = openpyxl.load_workbook(io.BytesIO(office_client.get("/stock/export/").content)).active
    headers = [c.value for c in ws[6]]
    assert headers[-1] == "Defective store (not counted)" and "Defective store" not in headers[:-1]
    assert ws.cell(7, headers.index("Total") + 1).value == 6 and ws.cell(7, len(headers)).value == 4
```

Note for every test in this plan: Django escapes `'` in rendered messages as `&#x27;`, so assertions on rendered HTML never include an apostrophe.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/inventory/test_good_stock.py -q`
Expected: FAIL (`item_totals()` returns 10, no `defective` key, store offered on the forms).

- [ ] **Step 3: Good-stock selectors (`apps/inventory/selectors.py`)**

Replace `item_totals`, `low_stock_count`, `location_unit_totals`, `stock_locations` and `current_stock_rows`, change the NOS line of `dashboard_stats` and the lines query of `weekly_in_out`, and add `defective_store_id` and `default_location`:
```python
def defective_store_id():
    """pk of the Defective store."""
    return Location.objects.filter(is_defective_store=True).values_list("pk", flat=True).first()


def default_location():
    """The location entry forms start on: Vizag Office if active, else the first active good location."""
    places = Location.objects.good().filter(is_active=True)
    return places.filter(name="Vizag Office").first() or places.first()


def item_totals():
    """{item_id: good-stock total}. The Defective store is never part of a total."""
    rows = (
        StockBalance.objects.filter(location__is_defective_store=False)
        .values("item_id")
        .annotate(total=Sum("qty"))
    )
    return {r["item_id"]: r["total"] for r in rows}


def low_stock_count():
    """Number of active items at or below their reorder level (good stock only), in one query."""
    good = Q(balances__location__is_defective_store=False)
    return (
        Item.objects.filter(is_active=True, reorder_level__gt=0)
        .annotate(t=Coalesce(Sum("balances__qty", filter=good), 0))
        .filter(t__lte=F("reorder_level"))
        .count()
    )


def location_unit_totals():
    """[(location, {unit: qty})] for the 'Stock by location' card. Good locations only."""
    totals = defaultdict(lambda: defaultdict(int))
    rows = (
        StockBalance.objects.exclude(qty=0)
        .filter(location__is_defective_store=False)
        .values("location_id", "item__unit")
        .annotate(q=Sum("qty"))
    )
    for row in rows:
        totals[row["location_id"]][row["item__unit"]] += row["q"]
    # same rule as stock_locations: active, or hidden but still holding stock
    places = Location.objects.good().filter(Q(is_active=True) | Q(pk__in=list(totals)))
    return [(place, dict(totals[place.pk])) for place in places]
```

In `dashboard_stats`, the first line becomes:
```python
    nos = (
        StockBalance.objects.filter(item__unit="NOS", location__is_defective_store=False).aggregate(
            t=Sum("qty")
        )["t"]
        or 0
    )
```

In `weekly_in_out`, add `.exclude(location__is_defective_store=True)` to the `StockLine.objects.filter(...)` chain, directly before `.values_list("entry__entry_date", "qty")`.

```python
def stock_locations(bal):
    """Active good locations, plus any hidden good location that still holds stock."""
    held = {loc_id for (_, loc_id), qty in bal.items() if qty}
    return list(Location.objects.good().filter(Q(is_active=True) | Q(pk__in=held)))


def current_stock_rows(f):
    """(rows, locations). Row: {item, per_loc: {location_id: qty}, total, low, defective}.

    Good stock only: the Defective store is never a column or part of `total`; its quantity is `defective`,
    shown separately. Hides items with no stock anywhere (good or defective).
    """
    bal = balance_map()
    store_id = defective_store_id()
    locations = [f.location] if f.location else stock_locations(bal)
    good_ids = list(Location.objects.good().values_list("pk", flat=True))
    rows = []
    for item in _filtered_items(f).filter(is_active=True):
        per_loc = {pk: bal.get((item.pk, pk), 0) for pk in good_ids}
        total = sum(per_loc.values())
        defective = bal.get((item.pk, store_id), 0)
        low = is_low(item, total)
        if f.location:
            shown = per_loc.get(f.location.pk, 0) != 0
        else:
            shown = total != 0 or defective != 0 or f.low
        if shown and (low or not f.low):
            rows.append({"item": item, "per_loc": per_loc, "total": total, "low": low, "defective": defective})
    return rows, locations
```

- [ ] **Step 4: Filters, forms, views, masters, export**

`apps/inventory/filters.py`, replace `stock_filters`:
```python
def stock_filters(params):
    place = _obj(Location, params.get("location"))
    if place is not None and place.is_defective_store:
        place = None  # the Defective store has its own column, it is not a location filter here
    return StockFilters(
        place,
        _obj(SpareType, params.get("spare_type")),
        _obj(Company, params.get("company")),
        _text(params.get("q")),
        params.get("low") == "1",
    )
```

`apps/inventory/forms.py`: in `EntryHeaderForm` change the location field, and in `TransferForm` the `to_location` field, to good locations:
```python
    location = forms.ModelChoiceField(Location.objects.good().filter(is_active=True), empty_label=None)
```
```python
    to_location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True), empty_label=None, label="To location"
    )
```

`apps/inventory/views.py`:
```python
def _masters():
    return {
        "all_locations": Location.objects.good().filter(is_active=True),
        "spare_types": SpareType.objects.filter(is_active=True),
        "companies": Company.objects.filter(is_active=True),
    }
```
In `current_stock`, add a sorter before the `for p in locations:` loop:
```python
        "def": lambda r: r["defective"],
```
In `movements`, the render context becomes (the Defective store stays filterable here):
```python
        {
            "f": f,
            "table": table,
            "kinds": EntryKind.choices,
            **_masters(),
            "all_locations": Location.objects.filter(is_active=True),
        },
```
Replace `item_detail`:
```python
@role_required(OFFICE)
def item_detail(request, pk):
    item = get_object_or_404(Item.objects.select_related("spare_type", "company", "fitting_type"), pk=pk)
    date_from, date_to, location = history_filters(request.GET, timezone.localdate())
    held = dict(StockBalance.objects.filter(item=item).values_list("location_id", "qty"))
    store = Location.objects.filter(is_defective_store=True).first()
    places = list(
        Location.objects.good().filter(Q(is_active=True) | Q(pk__in=[k for k, q in held.items() if q]))
    )
    per_loc = [(p, held.get(p.pk, 0)) for p in places]
    total = sum(q for _, q in per_loc)
    return render(
        request,
        "inventory/item_detail.html",
        {
            "item": item,
            "per_loc": per_loc,
            "total": total,
            "defective": held.get(store.pk, 0) if store else 0,
            "low": selectors.is_low(item, total),
            "history": selectors.item_history(item, date_from, date_to, location),
            "date_from": date_from,
            "date_to": date_to,
            "location": location,
            "all_locations": places + ([store] if store else []),
        },
    )
```
Replace `_default_location` and the transfer `others` line in `_entry_page`:
```python
def _default_location():
    return selectors.default_location()
```
```python
        others = (
            Location.objects.good()
            .filter(is_active=True)
            .exclude(pk=getattr(initial["location"], "pk", None))
        )
```

`apps/inventory/masters.py`, replace `_refuse_hide`:
```python
def _refuse_hide(model, label, row):
    """Reason this row may not be hidden, or None."""
    if model is Location and row.is_defective_store:
        return f"{row.name} holds the defective pieces and can't be hidden."
    if model is Location and StockBalance.objects.filter(location=row).exclude(qty=0).exists():
        return f"{row.name} still holds stock. Move or adjust it to zero first."
    if model is Company and row.name == settings.DEFAULT_COMPANY:
        return f"{row.name} is the default supplier and can't be hidden."
    if model in (Location, Company):
        others = model.objects.filter(is_active=True).exclude(pk=row.pk)
        if model is Location:
            others = others.filter(is_defective_store=False)
        if not others.exists():
            return f"At least one {'location' if model is Location else 'company'} must stay active."
    return None
```

`apps/inventory/exports.py`, in `current_stock_xlsx`: the last `cols +=` line becomes
```python
    cols += [
        Column("Total", "int"),
        Column("Unit"),
        Column("Reorder level", "int"),
        Column("Status"),
        Column("Defective store (not counted)", "int"),
    ]
```
the end of each data row becomes
```python
        + [r["total"], r["item"].unit, r["item"].reorder_level, "LOW" if r["low"] else "OK", r["defective"]]
```
the `filters = _describe(...)` call gains a last argument `"Total = good stock only; the Defective store is listed separately"`, and the `return workbook_response(...)` passes `len(cols) - 2` (the Status column) instead of `len(cols) - 1`.

- [ ] **Step 5: Templates and styles**

`templates/inventory/current_stock.html`:
- In `<thead>`, after `{% if not f.location %}{% sort_th "total" "Total" True %}{% endif %}`, add:
```html
      {% if not f.location %}{% sort_th "def" "Defective store (not counted)" True "col-def" %}{% endif %}
```
- In the row, after the Total `<td>` block `{% if not f.location %}<td class="num">...</td>{% endif %}`, add:
```html
      {% if not f.location %}<td class="num col-def">{% if r.defective and nav_urls.defective_pieces %}<a href="{{ nav_urls.defective_pieces }}?item={{ r.item.pk }}&amp;status=IN_STORE" title="Open the pieces">{{ r.defective }}</a>{% else %}{{ r.defective|qty }}{% endif %}</td>{% endif %}
```
- Replace the footer note with:
```html
<p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> Red total = at or below the item's reorder level. The <b>Defective store</b> column shows failed pieces waiting to go back to the company; they are never part of the total.</p>
```

`templates/inventory/item_detail.html`, in the "Stock by location" card replace the `<div class="list-group-item d-flex bg-light"><b>Total</b>...</div></div></div></div>` ending with:
```html
    <div class="list-group-item d-flex bg-light"><b>Total (good stock)</b><span class="ms-auto fw-bold">{{ total|qty }} {{ item.unit }}</span></div></div>
    <div class="card-footer d-flex align-items-center"><i class="ti ti-recycle me-2 text-secondary"></i><span>Defective store: <b>{{ defective }}</b> {{ item.unit }}<span class="d-block small text-secondary">Failed pieces, not counted above</span></span>
      {% if defective and nav_urls.defective_pieces %}<a class="btn btn-sm btn-quiet ms-auto" href="{{ nav_urls.defective_pieces }}?item={{ item.pk }}&amp;status=IN_STORE"><i class="ti ti-tags"></i> Pieces</a>{% endif %}</div></div></div>
```

Append to `static/css/app.css` (the service styles from `mockups/service/style.css`, used by every later task):
```css
/* ===== Service modules (complaints + defectives). Colour carries meaning, always with a word or an icon:
   red = needs attention, amber = waiting on someone, green = done well, slate = neutral / finished. ===== */
.nav-badge { background: rgba(255,255,255,.12); color: var(--brand-sidebar-text); font-weight: 600; }
.badge.st { display: inline-flex; align-items: center; gap: .25rem; font-weight: 600; white-space: nowrap; }
.badge.st .ti { font-size: .95em; }
.st-alert { background: #fde8e8 !important; color: #b42318 !important; }
.st-wait { background: #fef3c7 !important; color: #854d0e !important; }
.st-ok { background: #e7f6ec !important; color: #1e7e34 !important; }
.st-neutral { background: rgba(71,85,105,.12) !important; color: #334155 !important; }
.st-done { background: #eef0f3 !important; color: #475569 !important; }
.kpi-wait { background: #fef3c7; color: #854d0e; }
.bar-brand { background: var(--tblr-primary); }
.progress-sm { height: .35rem; }
.chip { display: inline-flex; align-items: center; gap: .35rem; padding: .3rem .65rem; border-radius: 1rem; background: #fff;
  border: 1px solid var(--tblr-border-color); font-size: .85rem; color: var(--tblr-body-color); }
.chip .ti { color: var(--tblr-secondary); }
.chip-alert { background: #fde8e8; border-color: #f6c6c6; color: #b42318; } .chip-alert .ti { color: #b42318; }
.chip-wait { background: #fef3c7; border-color: #f5dd9b; color: #854d0e; } .chip-wait .ti { color: #854d0e; }
a.chip-link:hover { border-color: var(--tblr-primary); text-decoration: none; }
.tl { list-style: none; margin: 0; padding: 0; }
.tl-item { position: relative; display: flex; gap: .75rem; padding-bottom: 1rem; }
.tl-item:not(:last-child)::before { content: ""; position: absolute; left: .85rem; top: 1.9rem; bottom: .2rem; width: 2px; background: var(--tblr-border-color); }
.tl-dot { flex: none; width: 1.75rem; height: 1.75rem; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; }
.tl-body { min-width: 0; padding-top: .15rem; }
.table td.cell-wrap { white-space: normal; min-width: 12rem; max-width: 26rem; }
.status-tabs { flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
.status-tabs .nav-link { white-space: nowrap; padding: .5rem .6rem; }
.status-tabs .badge { padding: .2em .45em; }
.table td.col-def, .table th.col-def { background: #f7f8fa; border-left: 1px dashed var(--tblr-border-color); }
.table th.col-def a { white-space: normal; display: inline-block; max-width: 7rem; text-align: right; }
.table td.col-def a { font-weight: 600; }
td.c-check, th.c-check { width: 1%; }
.bulk-bar { position: sticky; top: 0; z-index: 5; background: var(--tblr-primary-lt); border-bottom: 1px solid var(--tblr-border-color); }
.lines-table td.c-fault { min-width: 12rem; }
.lines-table td[data-label="Batch code"] { min-width: 8rem; }
.lines-table td[data-label="PKD (packed)"] { min-width: 10rem; }
.settle-panel { background: #f8fafc; }
.page-title .badge.st { font-size: .8rem; vertical-align: middle; margin-left: .35rem; }
@media (max-width: 767.98px) {
  .lines-table td.c-fault { grid-column: 1 / -1; }
  .page-header .btn-list { flex-wrap: wrap; }
}
/* Six sidebar sections: keep the menu compact on desktop (it still scrolls on short screens). */
@media (min-width: 992px) {
  .navbar-vertical .nav-section { padding: .7rem 1rem .2rem; }
  .navbar-vertical .navbar-nav .nav-link { padding-top: .38rem; padding-bottom: .38rem; }
}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest tests/inventory -q`
Expected: PASS, including `test_list_queries_do_not_grow_with_items` (the two new lookups are constant).

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/selectors.py apps/inventory/filters.py apps/inventory/forms.py apps/inventory/views.py apps/inventory/masters.py apps/inventory/exports.py templates/inventory/current_stock.html templates/inventory/item_detail.html static/css/app.css tests/inventory/test_good_stock.py
git commit -m "feat(inventory): keep the Defective store out of good stock; show it as its own column"
```

---

### Task 3: Numbering counter, defectives models, ledger link to return batches

**Files:**
- Create: `apps/core/models.py`, `apps/core/numbers.py`, `apps/core/migrations/__init__.py`, generated `apps/core/migrations/0001_initial.py`
- Create: `apps/defectives/__init__.py` (empty), `apps/defectives/apps.py`, `apps/defectives/models.py`, `apps/defectives/migrations/__init__.py` (empty), generated `apps/defectives/migrations/0001_initial.py`
- Modify: `config/settings/base.py` (INSTALLED_APPS, COURIERS)
- Modify: `apps/inventory/models.py` (`StockEntry.return_batch`), generated `apps/inventory/migrations/0007_stockentry_return_batch.py`
- Modify: `apps/inventory/services.py` (`post_entry(return_batch=...)`)
- Test: `tests/core/test_numbers.py`, `tests/defectives/__init__.py` (empty), `tests/defectives/test_models.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_numbers.py`:
```python
import pytest
from django.db import transaction

from apps.core.models import Counter
from apps.core.numbers import next_number

pytestmark = pytest.mark.django_db


def test_series_count_up_independently():
    with transaction.atomic():
        assert [next_number("DEF"), next_number("DEF"), next_number("RB")] == ["DEF-0001", "DEF-0002", "RB-0001"]
    assert Counter.objects.get(prefix="DEF").last == 2


def test_a_rolled_back_number_is_used_again():
    with pytest.raises(RuntimeError), transaction.atomic():
        next_number("CMP")
        raise RuntimeError("the save failed")
    with transaction.atomic():
        assert next_number("CMP") == "CMP-0001"
```

Create `tests/defectives/__init__.py` (empty) and `tests/defectives/test_models.py`:
```python
import pytest
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.defectives.models import (
    TRANSITIONS,
    BatchLine,
    DefectiveEvent,
    DefectivePiece,
    PieceStatus,
    ReturnBatch,
    Source,
)
from apps.inventory.models import Company, EntryKind, ServiceSubtype
from apps.inventory.services import Line, post_entry
from tests.factories import make_item, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def make_batch(user, number="RB-0001"):
    company = Company.objects.get(name="Wipro Lighting")
    return ReturnBatch.objects.create(number=number, company=company, created_on=TODAY, created_by=user)


def make_piece(user, item, tag="DEF-0001"):
    return DefectivePiece.objects.create(
        tag=tag, item=item, company=item.company, source=Source.FOUND_IN_STOCK, collected_on=TODAY, created_by=user
    )


def test_piece_defaults(office_user):
    p = make_piece(office_user, make_item("LG78-150-700"))
    assert str(p) == "DEF-0001" and p.status == PieceStatus.IN_STORE and p.outcome == ""
    assert p.company.name == "Wipro Lighting" and p.return_batch is None


def test_transitions_end_at_settled_and_scrapped():
    assert TRANSITIONS[PieceStatus.SETTLED] == set() and TRANSITIONS[PieceStatus.SCRAPPED] == set()
    assert TRANSITIONS[PieceStatus.SENT] == {PieceStatus.SETTLED, PieceStatus.IN_STORE}


def test_a_piece_is_in_a_batch_only_once(office_user):
    b, p = make_batch(office_user), make_piece(office_user, make_item("X1"))
    BatchLine.objects.create(batch=b, piece=p)
    with pytest.raises(IntegrityError), transaction.atomic():
        BatchLine.objects.create(batch=b, piece=p)


def test_piece_events_are_append_only(office_user):
    p = make_piece(office_user, make_item("X2"))
    ev = DefectiveEvent.objects.create(piece=p, to_status=PieceStatus.IN_STORE, at=TODAY, by=office_user)
    with pytest.raises(DatabaseError), transaction.atomic():
        DefectiveEvent.objects.filter(pk=ev.pk).update(note="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        ev.delete()


def test_ledger_entry_links_to_its_return_batch(office_user):
    b, item = make_batch(office_user), make_item("X3")
    post_entry(
        kind=EntryKind.IN,
        entry_date=TODAY,
        lines=[Line(item, store(), 1)],
        user=office_user,
        subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
    )
    e = post_entry(
        kind=EntryKind.OUT,
        entry_date=TODAY,
        lines=[Line(item, store(), -1)],
        user=office_user,
        subtype=ServiceSubtype.RETURN_TO_COMPANY,
        return_batch=b,
    )
    assert e.return_batch == b and list(b.entries.all()) == [e]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/core/test_numbers.py tests/defectives -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core.models'` / `'apps.defectives'`.

- [ ] **Step 3: Write the counter**

`apps/core/models.py`:
```python
from django.db import models


class Counter(models.Model):
    """Last number used per document series (DEF, RB, CMP, VIS). Locked while a number is taken."""

    prefix = models.CharField(max_length=4, primary_key=True)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.prefix}: {self.last}"
```

`apps/core/numbers.py`:
```python
"""Gap-free document numbers (DEF-0001, RB-0001, CMP-0001, VIS-0001), the same pattern as stock entry numbers."""

from .models import Counter


def next_number(prefix):
    """The next number in a series, e.g. 'DEF-0042'.

    Call inside a transaction: the counter row stays locked until commit, so two saves never get the same
    number, and a save that fails gives its number back.
    """
    Counter.objects.get_or_create(prefix=prefix)
    counter = Counter.objects.select_for_update().get(prefix=prefix)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"{prefix}-{counter.last:04d}"
```

Create `apps/core/migrations/__init__.py` (empty).

- [ ] **Step 4: Write the defectives models**

`apps/defectives/apps.py`:
```python
from django.apps import AppConfig


class DefectivesConfig(AppConfig):
    name = "apps.defectives"
    label = "defectives"
    verbose_name = "Defective pieces"
```

`apps/defectives/models.py`:
```python
"""Defective pieces: every failed part tracked one physical piece at a time, from collection to the company's
answer. Statuses move only through services.py, which checks TRANSITIONS and logs a DefectiveEvent."""

from django.conf import settings
from django.db import models

from apps.inventory.models import IMMUTABLE, Company, Item, Location, StockEntry


class PieceStatus(models.TextChoices):
    IN_STORE = "IN_STORE", "In store"
    IN_BATCH = "IN_BATCH", "In draft batch"
    SENT = "SENT", "Sent to company"
    SETTLED = "SETTLED", "Settled"
    SCRAPPED = "SCRAPPED", "Scrapped"


# Moves a piece may make. SENT -> IN_STORE means "rejected, and the company sent it back".
TRANSITIONS = {
    PieceStatus.IN_STORE: {PieceStatus.IN_BATCH, PieceStatus.SCRAPPED},
    PieceStatus.IN_BATCH: {PieceStatus.IN_STORE, PieceStatus.SENT},
    PieceStatus.SENT: {PieceStatus.SETTLED, PieceStatus.IN_STORE},
    PieceStatus.SETTLED: set(),
    PieceStatus.SCRAPPED: set(),
}


class Outcome(models.TextChoices):
    REPLACED = "REPLACED", "Replaced"
    REPAIRED = "REPAIRED", "Repaired"
    REJECTED_RETURNED = "REJECTED_RETURNED", "Rejected (returned)"
    REJECTED_SCRAPPED = "REJECTED_SCRAPPED", "Rejected (scrapped)"


GOOD_OUTCOMES = {Outcome.REPLACED, Outcome.REPAIRED}  # a piece comes back into good stock


class Source(models.TextChoices):
    SITE_VISIT = "SITE_VISIT", "Site visit"
    FOUND_IN_STOCK = "FOUND_IN_STOCK", "Found in stock"


class BatchStatus(models.TextChoices):
    """Stored status. 'Partly settled' and 'Settled' are worked out from the lines (selectors.batch_label)."""

    DRAFT = "DRAFT", "Draft"
    DISPATCHED = "DISPATCHED", "Dispatched"


class ScrapReason(models.TextChoices):
    NOT_WORTH = "NOT_WORTH", "Not worth returning"
    BURNT = "BURNT", "Burnt / physically damaged"
    REJECTED = "REJECTED", "Rejected by the company"
    OTHER = "OTHER", "Other"


class ReturnBatch(models.Model):
    """Pieces going back to one company together. Locked once dispatched."""

    number = models.CharField(max_length=12, unique=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="return_batches")
    created_on = models.DateField()
    status = models.CharField(max_length=10, choices=BatchStatus.choices, default=BatchStatus.DRAFT)
    dispatched_on = models.DateField(null=True, blank=True)
    docket_no = models.CharField("docket / LR no.", max_length=40, blank=True)
    courier = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=200, blank=True)
    dispatch_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="dispatched_batch"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "return batches"

    def __str__(self):
        return self.number

    @property
    def is_draft(self):
        return self.status == BatchStatus.DRAFT


class DefectivePiece(models.Model):
    """One physical failed piece with its own tag. Its company is copied from the item when it is collected."""

    tag = models.CharField(max_length=12, unique=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="defective_pieces")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="defective_pieces")
    batch_code = models.CharField(max_length=40, blank=True)
    pkd = models.DateField("packed (month)", null=True, blank=True)
    fault = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    collected_on = models.DateField()
    status = models.CharField(max_length=10, choices=PieceStatus.choices, default=PieceStatus.IN_STORE)
    # The batch the piece is in (draft, sent or settled). Cleared when it is removed or sent back rejected.
    return_batch = models.ForeignKey(
        ReturnBatch, on_delete=models.PROTECT, null=True, blank=True, related_name="pieces"
    )
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)  # the latest answer
    settled_on = models.DateField(null=True, blank=True)
    replacement_entry = models.ForeignKey(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="replaced_pieces"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["status", "company"], name="piece_status_company_idx")]

    def __str__(self):
        return self.tag


class BatchLine(models.Model):
    """One piece in one return batch, with the company's answer for it. A piece that was rejected and sent
    back can go out again in a later batch, so its earlier answers stay on record here."""

    batch = models.ForeignKey(ReturnBatch, on_delete=models.PROTECT, related_name="lines")
    piece = models.ForeignKey(DefectivePiece, on_delete=models.PROTECT, related_name="batch_lines")
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    settled_on = models.DateField(null=True, blank=True)
    to_location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    entry = models.ForeignKey(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="settled_lines"
    )

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["batch", "piece"], name="piece_once_per_batch")]

    def __str__(self):
        return f"{self.batch} / {self.piece}"


class DefectiveEvent(models.Model):
    """Append-only history of a piece: every status change, with the ledger entry that moved it (if any)."""

    piece = models.ForeignKey(DefectivePiece, on_delete=models.PROTECT, related_name="events")
    from_status = models.CharField(max_length=10, choices=PieceStatus.choices, blank=True)
    to_status = models.CharField(max_length=10, choices=PieceStatus.choices)
    at = models.DateField()
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    entry = models.ForeignKey(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="defective_events"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]
        triggers = [IMMUTABLE]

    def __str__(self):
        return f"{self.piece}: {self.from_status or '-'} -> {self.to_status}"
```

Create `apps/defectives/migrations/__init__.py` (empty).

- [ ] **Step 5: Install the app, link ledger entries to batches**

`config/settings/base.py`: add `"apps.defectives",` to `INSTALLED_APPS` directly after `"apps.inventory",`, and below `DEFAULT_COMPANY` add:
```python
# Suggestions for the courier box when a return batch is dispatched (any other name can be typed).
COURIERS = env.list("COURIERS", default=["DTDC", "Professional Couriers", "ST Courier", "VRL Logistics", "By hand"])
```

`apps/inventory/models.py`, in `StockEntry` below `reverses`:
```python
    # Set by the defectives services: the return batch a dispatch or settlement entry belongs to.
    return_batch = models.ForeignKey(
        "defectives.ReturnBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="entries"
    )
```

`apps/inventory/services.py`, `post_entry`: add the keyword `return_batch=None,` after `reverses=None,` in the signature and `return_batch=return_batch,` after `reverses=reverses,` in `StockEntry.objects.create(...)`.

- [ ] **Step 6: Generate the migrations**

Run: `uv run python manage.py makemigrations core`
Expected: `apps/core/migrations/0001_initial.py` (Counter).

Run: `uv run python manage.py makemigrations defectives inventory`
Expected: `apps/defectives/migrations/0001_initial.py` (depends on `inventory.0006_create_defective_store`) and `apps/inventory/migrations/0007_stockentry_return_batch.py` (depends on `defectives.0001_initial`). Open both and check those dependencies; rename the inventory file to `0007_stockentry_return_batch.py` if Django picked another name.

- [ ] **Step 7: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS (whole suite).

- [ ] **Step 8: Commit**

```bash
git add apps/core apps/defectives apps/inventory/models.py apps/inventory/services.py apps/inventory/migrations/0007_stockentry_return_batch.py config/settings/base.py tests/core/test_numbers.py tests/defectives
git commit -m "feat(defectives): pieces, return batches, batch lines and append-only piece events"
```

---

### Task 4: Defectives services for pieces (create, mark defective, scrap)

**Files:**
- Create: `apps/defectives/services.py`
- Modify: `tests/factories.py` (add `give_stock`, `make_pieces`)
- Test: `tests/defectives/test_piece_services.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/factories.py` (new imports at the top: `from django.utils import timezone`, `from apps.inventory.models import EntryKind`, `from apps.inventory.services import Line, post_entry`):
```python
def give_stock(item, qty, user, place=None):
    """A supplier Stock IN of `qty` at `place` (default Vizag Office), dated today."""
    return post_entry(
        kind=EntryKind.IN,
        entry_date=timezone.localdate(),
        lines=[Line(item, place or loc(), qty)],
        user=user,
        subtype="SUPPLIER",
        party="Test supplier",
    )


def make_pieces(item, qty, user, fault="no output"):
    """`qty` tagged pieces in the Defective store: stocked at Vizag Office, then marked defective."""
    from apps.defectives.services import mark_defective

    give_stock(item, qty, user)
    _, pieces = mark_defective(
        location=loc(), lines=[(item, qty, fault)], entry_date=timezone.localdate(), user=user
    )
    return pieces
```

Create `tests/defectives/test_piece_services.py`:
```python
import pytest
from django.utils import timezone

from apps.defectives.models import DefectiveEvent, DefectivePiece, PieceStatus, ScrapReason, Source
from apps.defectives.services import DefectiveError, mark_defective, normalise_tag, scrap
from apps.inventory.models import EntryKind, ServiceSubtype, StockBalance
from apps.inventory.services import NotEnoughStock, balance_drift
from tests.factories import give_stock, loc, make_item, make_pieces, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def qty(item, place):
    row = StockBalance.objects.filter(item=item, location=place).first()
    return row.qty if row else 0


@pytest.fixture
def drv(db):
    return make_item("LG78-150-700")


def test_mark_defective_moves_stock_and_tags_each_piece(drv, office_user):
    give_stock(drv, 5, office_user)
    entry, pieces = mark_defective(
        location=loc(), lines=[(drv, 2, "Dead on arrival")], entry_date=TODAY, user=office_user
    )
    assert entry.kind == EntryKind.TRF and entry.subtype == ServiceSubtype.MARK_DEFECTIVE
    assert [p.tag for p in pieces] == ["DEF-0001", "DEF-0002"]
    assert qty(drv, loc()) == 3 and qty(drv, store()) == 2
    p = DefectivePiece.objects.get(tag="DEF-0001")
    assert (p.status, p.source, p.company.name, p.fault, p.collected_on) == (
        PieceStatus.IN_STORE,
        Source.FOUND_IN_STOCK,
        "Wipro Lighting",
        "Dead on arrival",
        TODAY,
    )
    ev = DefectiveEvent.objects.get(piece=p)
    assert (ev.from_status, ev.to_status, ev.entry) == ("", PieceStatus.IN_STORE, entry)
    assert balance_drift() == []


def test_piece_company_comes_from_the_item(office_user):
    mcb = make_item("MCB 16A SP", company="Havells", spare_type="Accessory")
    [p] = make_pieces(mcb, 1, office_user)
    assert p.company.name == "Havells"


def test_every_line_needs_a_fault(drv, office_user):
    give_stock(drv, 5, office_user)
    with pytest.raises(DefectiveError, match="Line 2: write what is wrong with the piece."):
        mark_defective(
            location=loc(), lines=[(drv, 1, "no output"), (drv, 1, " ")], entry_date=TODAY, user=office_user
        )


def test_over_marking_saves_nothing_and_uses_no_tag(drv, office_user):
    give_stock(drv, 1, office_user)
    with pytest.raises(NotEnoughStock):
        mark_defective(location=loc(), lines=[(drv, 2, "x")], entry_date=TODAY, user=office_user)
    assert not DefectivePiece.objects.exists()
    _, [p] = mark_defective(location=loc(), lines=[(drv, 1, "x")], entry_date=TODAY, user=office_user)
    assert p.tag == "DEF-0001"


def test_cannot_mark_from_the_store(drv, office_user):
    with pytest.raises(DefectiveError, match="good-stock location"):
        mark_defective(location=store(), lines=[(drv, 1, "x")], entry_date=TODAY, user=office_user)


def test_scrap_writes_off_pieces_in_store(drv, office_user):
    pieces = make_pieces(drv, 3, office_user)
    entry = scrap(pieces=pieces[:2], reason=ScrapReason.NOT_WORTH, user=office_user)
    assert (entry.kind, entry.subtype, entry.reason) == (EntryKind.ADJ, ServiceSubtype.SCRAP_DEFECTIVE, "DAMAGED")
    assert "Scrapped DEF-0001, DEF-0002: Not worth returning" in entry.note and qty(drv, store()) == 1
    statuses = list(DefectivePiece.objects.order_by("tag").values_list("status", flat=True))
    assert statuses == [PieceStatus.SCRAPPED, PieceStatus.SCRAPPED, PieceStatus.IN_STORE]
    assert DefectiveEvent.objects.filter(entry=entry).count() == 2
    assert balance_drift() == []


def test_scrap_rules(drv, office_user):
    pieces = make_pieces(drv, 2, office_user)
    with pytest.raises(DefectiveError, match="Tick at least one piece."):
        scrap(pieces=[], reason=ScrapReason.BURNT, user=office_user)
    with pytest.raises(DefectiveError, match="Choose why the pieces are scrapped."):
        scrap(pieces=pieces, reason="", user=office_user)
    with pytest.raises(DefectiveError, match="Write a note when the reason is Other."):
        scrap(pieces=pieces, reason=ScrapReason.OTHER, user=office_user)
    scrap(pieces=pieces[:1], reason=ScrapReason.OTHER, note="fell off the shelf", user=office_user)
    with pytest.raises(DefectiveError, match="DEF-0001 is scrapped. Only pieces in store can be scrapped."):
        scrap(pieces=pieces[:1], reason=ScrapReason.BURNT, user=office_user)


@pytest.mark.parametrize(
    "text, tag",
    [("def-42", "DEF-0042"), ("DEF0042", "DEF-0042"), (" DEF-0007 ", "DEF-0007"), ("rb-1", "RB-1")],
)
def test_normalise_tag(text, tag):
    assert normalise_tag(text) == tag
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/defectives/test_piece_services.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.defectives.services'`.

- [ ] **Step 3: Write `apps/defectives/services.py`**

```python
"""All writes for defective pieces and return batches. Views and commands call these; nothing else changes a
piece. Every stock effect goes through inventory's post_entry (append-only ledger, row locks, never negative)."""

import re
from collections import Counter

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.numbers import next_number
from apps.inventory.models import AdjustReason, EntryKind, Location, ServiceSubtype
from apps.inventory.services import Line, post_entry

from .models import TRANSITIONS, DefectiveEvent, DefectivePiece, PieceStatus, ScrapReason, Source

TAG = re.compile(r"^DEF-?(\d{1,6})$")


class DefectiveError(ValidationError):
    """A defectives rule was broken. The message is safe to show to staff as-is."""


def normalise_tag(text):
    """'def-42' or 'DEF0042' -> 'DEF-0042' (what staff type or scan). Anything else comes back upper-cased."""
    raw = (text or "").strip().upper()
    match = TAG.match(raw)
    return f"DEF-{int(match.group(1)):04d}" if match else raw


def _lock(pieces):
    """The same pieces re-read and row-locked in tag order, so two people can't move one piece twice."""
    return list(
        DefectivePiece.objects.select_for_update(of=("self",))
        .filter(pk__in=[p.pk for p in pieces])
        .select_related("item", "company", "return_batch")
        .order_by("tag")
    )


def _move(piece, to, *, at, user, note="", entry=None):
    """Change a piece's status (checked against TRANSITIONS) and log it. The caller saves the piece."""
    if to not in TRANSITIONS[piece.status]:
        raise DefectiveError(
            f"{piece.tag} is {piece.get_status_display().lower()}, so it can't become "
            f"{PieceStatus(to).label.lower()}."
        )
    DefectiveEvent.objects.create(
        piece=piece, from_status=piece.status, to_status=to, at=at, by=user, note=note[:300], entry=entry
    )
    piece.status = to


def _not_in_store(piece, action, hint=""):
    where = f" ({piece.return_batch.number})" if piece.return_batch_id else ""
    status = piece.get_status_display().lower()
    return f"{piece.tag} is {status}{where}. Only pieces in store can be {action}{hint}."


def _check_date(day, what="The date", missing="Choose the date."):
    if day is None:
        raise DefectiveError(missing)
    if day > timezone.localdate():
        raise DefectiveError(f"{what} can't be in the future.")


def _per_item(pieces):
    """[(item, count)] for a group of pieces, in item-code order (one ledger line per item)."""
    counts = Counter(p.item_id for p in pieces)
    items = {p.item_id: p.item for p in pieces}
    return sorted(((items[i], n) for i, n in counts.items()), key=lambda pair: pair[0].code)


@transaction.atomic
def create_piece(*, item, source, collected_on, user, entry, batch_code="", pkd=None, fault="", note=""):
    """One tagged piece in the Defective store. The caller has already posted `entry`, the ledger entry that
    brought it there (a collection Stock IN or a mark-defective transfer)."""
    piece = DefectivePiece.objects.create(
        tag=next_number("DEF"),
        item=item,
        company=item.company,
        batch_code=(batch_code or "").strip()[:40],
        pkd=pkd,
        fault=(fault or "").strip()[:200],
        source=source,
        collected_on=collected_on,
        created_by=user,
    )
    DefectiveEvent.objects.create(
        piece=piece, to_status=PieceStatus.IN_STORE, at=collected_on, by=user, note=note[:300], entry=entry
    )
    return piece


@transaction.atomic
def mark_defective(*, location, lines, entry_date, user):
    """Move faulty pieces from good stock into the Defective store and tag each one.

    lines: [(item, qty, fault)]. Posts one Transfer (MARK_DEFECTIVE) and creates `qty` pieces per line.
    Returns (entry, pieces). Raises DefectiveError or StockError and saves nothing.
    """
    if location.is_defective_store:
        raise DefectiveError("Choose the good-stock location where the faulty pieces were found.")
    if not lines:
        raise DefectiveError("Add at least one item.")
    for n, (_, _, fault) in enumerate(lines, start=1):
        if not fault.strip():
            raise DefectiveError(f"Line {n}: write what is wrong with the piece.")
    _check_date(entry_date)
    store = Location.defective_store()
    moves = [ln for item, qty, _ in lines for ln in (Line(item, location, -qty), Line(item, store, qty))]
    entry = post_entry(
        kind=EntryKind.TRF,
        entry_date=entry_date,
        lines=moves,
        user=user,
        subtype=ServiceSubtype.MARK_DEFECTIVE,
        party=store.name,
        note="Marked defective",
    )
    pieces = [
        create_piece(
            item=item,
            source=Source.FOUND_IN_STOCK,
            collected_on=entry_date,
            user=user,
            entry=entry,
            fault=fault,
            note="Marked defective from stock",
        )
        for item, qty, fault in lines
        for _ in range(qty)
    ]
    return entry, pieces


@transaction.atomic
def scrap(*, pieces, reason, user, note="", entry_date=None):
    """Write off pieces in store that are not worth returning: one Adjustment (Damaged) at the Defective store,
    -1 per piece. Returns the entry."""
    entry_date = entry_date or timezone.localdate()
    pieces = _lock(pieces)
    if not pieces:
        raise DefectiveError("Tick at least one piece.")
    if reason not in ScrapReason.values:
        raise DefectiveError("Choose why the pieces are scrapped.")
    note = (note or "").strip()
    if reason == ScrapReason.OTHER and not note:
        raise DefectiveError("Write a note when the reason is Other.")
    for p in pieces:
        if p.status != PieceStatus.IN_STORE:
            hint = "; remove it from the batch first" if p.status == PieceStatus.IN_BATCH else ""
            raise DefectiveError(_not_in_store(p, "scrapped", hint))
    store = Location.defective_store()
    label = ScrapReason(reason).label
    why = label + (f" · {note}" if note else "")
    entry = post_entry(
        kind=EntryKind.ADJ,
        entry_date=entry_date,
        lines=[Line(item, store, -n) for item, n in _per_item(pieces)],
        user=user,
        subtype=ServiceSubtype.SCRAP_DEFECTIVE,
        reason=AdjustReason.DAMAGED,
        note=f"Scrapped {', '.join(p.tag for p in pieces)}: {why}",
    )
    for p in pieces:
        _move(p, PieceStatus.SCRAPPED, at=entry_date, user=user, note=why, entry=entry)
        p.settled_on = entry_date
        p.save(update_fields=["status", "settled_on"])
    return entry
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/defectives -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/defectives/services.py tests/factories.py tests/defectives/test_piece_services.py
git commit -m "feat(defectives): mark defective from stock and scrap pieces through the ledger"
```

---

### Task 5: Defectives services for return batches (create, add, remove, dispatch, settle)

**Files:**
- Modify: `apps/defectives/services.py` (append the batch services)
- Test: `tests/defectives/test_batch_services.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/defectives/test_batch_services.py`:
```python
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.defectives.models import BatchLine, BatchStatus, DefectivePiece, Outcome, PieceStatus
from apps.defectives.services import DefectiveError, add_pieces, create_batch, dispatch, remove_pieces, settle
from apps.inventory.models import Company, EntryKind, ServiceSubtype, StockBalance
from apps.inventory.services import balance_drift
from tests.factories import loc, make_item, make_pieces, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def qty(item, place):
    row = StockBalance.objects.filter(item=item, location=place).first()
    return row.qty if row else 0


def wipro():
    return Company.objects.get(name="Wipro Lighting")


def fresh(piece):
    piece.refresh_from_db()
    return piece


@pytest.fixture
def wipro_pieces(office_user):
    return make_pieces(make_item("LG78-150-700"), 3, office_user)  # DEF-0001..0003


@pytest.fixture
def havells_piece(office_user):
    return make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user)[0]


def sent_batch(pieces, user):
    b = create_batch(company=wipro(), user=user, pieces=pieces)
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D51243817", user=user)
    b.refresh_from_db()
    return b


def test_create_batch_with_pieces(wipro_pieces, office_user):
    b = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:2], note=" Drivers ")
    assert (b.number, b.status, b.note, b.created_on) == ("RB-0001", BatchStatus.DRAFT, "Drivers", TODAY)
    assert [fresh(p).status for p in wipro_pieces] == [
        PieceStatus.IN_BATCH,
        PieceStatus.IN_BATCH,
        PieceStatus.IN_STORE,
    ]
    assert fresh(wipro_pieces[0]).return_batch == b and b.lines.count() == 2


def test_company_is_required(office_user):
    with pytest.raises(DefectiveError, match="Choose the company the pieces go back to."):
        create_batch(company=None, user=office_user)


def test_a_batch_holds_one_company(wipro_pieces, havells_piece, office_user):
    with pytest.raises(DefectiveError, match="DEF-0004 is a Havells piece. A batch holds one company"):
        create_batch(company=wipro(), user=office_user, pieces=[wipro_pieces[0], havells_piece])
    b = create_batch(company=wipro(), user=office_user)
    with pytest.raises(DefectiveError, match="RB-0001 is for Wipro Lighting, but DEF-0004 is a Havells piece"):
        add_pieces(batch=b, pieces=[havells_piece], user=office_user)


def test_only_pieces_in_store_can_be_added(wipro_pieces, office_user):
    create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:1])
    b2 = create_batch(company=wipro(), user=office_user)
    with pytest.raises(DefectiveError, match=r"DEF-0001 is in draft batch \(RB-0001\)\. Only pieces in store"):
        add_pieces(batch=b2, pieces=wipro_pieces[:1], user=office_user)
    with pytest.raises(DefectiveError, match="Tick at least one piece."):
        add_pieces(batch=b2, pieces=[], user=office_user)


def test_remove_puts_the_piece_back_in_store(wipro_pieces, office_user):
    b = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:2])
    remove_pieces(batch=b, pieces=wipro_pieces[:1], user=office_user)
    p = fresh(wipro_pieces[0])
    assert p.status == PieceStatus.IN_STORE and p.return_batch is None
    assert list(b.lines.values_list("piece__tag", flat=True)) == ["DEF-0002"]
    with pytest.raises(DefectiveError, match="DEF-0001 is not in RB-0001."):
        remove_pieces(batch=b, pieces=wipro_pieces[:1], user=office_user)


def test_dispatch_posts_one_out_and_locks_the_batch(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    b = sent_batch(wipro_pieces[:2], office_user)
    e = b.dispatch_entry
    assert (e.kind, e.subtype, e.return_batch, e.ref, e.party) == (
        EntryKind.OUT,
        ServiceSubtype.RETURN_TO_COMPANY,
        b,
        "D51243817",
        "Wipro Lighting",
    )
    assert [(ln.item, ln.location, ln.qty) for ln in e.lines.all()] == [(drv, store(), -2)]
    assert (b.status, b.courier, b.docket_no, b.dispatched_on) == (BatchStatus.DISPATCHED, "DTDC", "D51243817", TODAY)
    assert fresh(wipro_pieces[0]).status == PieceStatus.SENT and qty(drv, store()) == 1
    with pytest.raises(DefectiveError, match="RB-0001 was dispatched on .*, so it is locked. Start a new batch."):
        add_pieces(batch=b, pieces=wipro_pieces[2:], user=office_user)
    with pytest.raises(DefectiveError, match="RB-0001 is dispatched and locked."):
        remove_pieces(batch=b, pieces=wipro_pieces[:1], user=office_user)
    with pytest.raises(DefectiveError, match="RB-0001 was already dispatched."):
        dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="X", user=office_user)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"dispatched_on": None}, "Choose the dispatch date."),
        ({"dispatched_on": TODAY + timedelta(days=1)}, "The dispatch date can't be in the future."),
        ({"dispatched_on": TODAY - timedelta(days=1)}, "can't be before the batch was created"),
        ({"courier": " "}, "Choose the courier."),
        ({"docket_no": ""}, "Enter the docket / LR number."),
    ],
)
def test_dispatch_rules(wipro_pieces, office_user, change, message):
    b = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[:1])
    args = {"dispatched_on": TODAY, "courier": "DTDC", "docket_no": "D1", **change}
    with pytest.raises(DefectiveError, match=message):
        dispatch(batch=b, user=office_user, **args)


def test_empty_batch_cannot_be_dispatched(office_user):
    b = create_batch(company=wipro(), user=office_user)
    with pytest.raises(DefectiveError, match="An empty batch can't be dispatched. Add pieces first."):
        dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)


def test_replaced_posts_stock_in_to_good_stock(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    good_before = qty(drv, loc())
    b = sent_batch(wipro_pieces[:2], office_user)
    [e] = settle(
        batch=b, pieces=wipro_pieces[:1], outcome=Outcome.REPLACED, settled_on=TODAY, to_location=loc(), user=office_user
    )
    assert (e.kind, e.subtype, e.return_batch, e.ref) == (EntryKind.IN, ServiceSubtype.REPLACEMENT, b, "RB-0001")
    assert qty(drv, loc()) == good_before + 1
    p = fresh(wipro_pieces[0])
    assert (p.status, p.outcome, p.settled_on, p.replacement_entry) == (PieceStatus.SETTLED, Outcome.REPLACED, TODAY, e)
    line = BatchLine.objects.get(batch=b, piece=p)
    assert (line.outcome, line.to_location, line.entry, line.settled_on) == (Outcome.REPLACED, loc(), e, TODAY)


def test_rejected_returned_goes_back_to_the_store_and_can_go_again(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    b = sent_batch(wipro_pieces[:1], office_user)
    [e] = settle(batch=b, pieces=wipro_pieces[:1], outcome=Outcome.REJECTED_RETURNED, settled_on=TODAY, user=office_user)
    assert e.subtype == ServiceSubtype.DEFECTIVE_RETURNED and qty(drv, store()) == 3
    p = fresh(wipro_pieces[0])
    assert (p.status, p.outcome, p.return_batch) == (PieceStatus.IN_STORE, Outcome.REJECTED_RETURNED, None)
    b2 = create_batch(company=wipro(), user=office_user, pieces=[p])
    assert BatchLine.objects.get(batch=b, piece=p).outcome == Outcome.REJECTED_RETURNED
    assert BatchLine.objects.get(batch=b2, piece=p).outcome == ""


def test_rejected_scrapped_posts_nothing(wipro_pieces, office_user):
    b = sent_batch(wipro_pieces[:1], office_user)
    done = settle(batch=b, pieces=wipro_pieces[:1], outcome=Outcome.REJECTED_SCRAPPED, settled_on=TODAY, user=office_user)
    assert done == [] and fresh(wipro_pieces[0]).status == PieceStatus.SETTLED


def test_settle_rules(wipro_pieces, office_user):
    draft = create_batch(company=wipro(), user=office_user, pieces=wipro_pieces[2:])  # RB-0001, DEF-0003
    with pytest.raises(DefectiveError, match="Only a dispatched batch can be settled."):
        settle(batch=draft, pieces=wipro_pieces[2:], outcome=Outcome.REPLACED, settled_on=TODAY, to_location=loc(), user=office_user)
    b = sent_batch(wipro_pieces[:2], office_user)  # RB-0002
    cases = [
        ({"pieces": []}, "Tick the pieces the company has answered for."),
        ({"outcome": ""}, "Choose the outcome."),
        ({"settled_on": None}, "Choose the settlement date."),
        ({"settled_on": TODAY + timedelta(days=1)}, "The date can't be in the future."),
        ({"settled_on": TODAY - timedelta(days=1)}, "can't be before the batch was dispatched"),
        ({"to_location": None}, "Choose the good-stock location the replacement pieces go into."),
        ({"to_location": store()}, "Choose the good-stock location the replacement pieces go into."),
        ({"pieces": wipro_pieces[2:]}, "DEF-0003 is not in RB-0002."),
    ]
    for change, message in cases:
        args = {"pieces": wipro_pieces[:1], "outcome": Outcome.REPLACED, "settled_on": TODAY, "to_location": loc(), **change}
        with pytest.raises(DefectiveError, match=message):
            settle(batch=b, user=office_user, **args)
    settle(batch=b, pieces=wipro_pieces[:1], outcome=Outcome.REPAIRED, settled_on=TODAY, to_location=loc(), user=office_user)
    with pytest.raises(DefectiveError, match="DEF-0001 is not waiting on the company"):
        settle(batch=b, pieces=wipro_pieces[:1], outcome=Outcome.REPAIRED, settled_on=TODAY, to_location=loc(), user=office_user)


def test_store_matches_the_pieces_after_a_full_cycle(wipro_pieces, office_user):
    drv = wipro_pieces[0].item
    b = sent_batch(wipro_pieces, office_user)
    settle(batch=b, pieces=wipro_pieces[:1], outcome=Outcome.REPLACED, settled_on=TODAY, to_location=loc(), user=office_user)
    settle(batch=b, pieces=wipro_pieces[1:2], outcome=Outcome.REJECTED_RETURNED, settled_on=TODAY, user=office_user)
    settle(batch=b, pieces=wipro_pieces[2:], outcome=Outcome.REJECTED_SCRAPPED, settled_on=TODAY, user=office_user)
    in_store = DefectivePiece.objects.filter(status__in=[PieceStatus.IN_STORE, PieceStatus.IN_BATCH]).count()
    assert qty(drv, store()) == in_store == 1 and balance_drift() == []
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/defectives/test_batch_services.py -q`
Expected: FAIL with `ImportError: cannot import name 'add_pieces'`.

- [ ] **Step 3: Append the batch services to `apps/defectives/services.py`**

Extend the model import to:
```python
from .models import (
    GOOD_OUTCOMES,
    TRANSITIONS,
    BatchLine,
    BatchStatus,
    DefectiveEvent,
    DefectivePiece,
    Outcome,
    PieceStatus,
    ReturnBatch,
    ScrapReason,
    Source,
)
```

Append:
```python
def _lock_batch(batch):
    return ReturnBatch.objects.select_for_update(of=("self",)).select_related("company").get(pk=batch.pk)


@transaction.atomic
def create_batch(*, company, user, pieces=(), note="", created_on=None):
    """A new draft return batch for one company, optionally filled with pieces in store."""
    if company is None:
        raise DefectiveError("Choose the company the pieces go back to.")
    for p in pieces:
        if p.company_id != company.pk:
            raise DefectiveError(
                f"{p.tag} is a {p.company.name} piece. A batch holds one company's pieces only."
            )
    created_on = created_on or timezone.localdate()
    batch = ReturnBatch.objects.create(
        number=next_number("RB"),
        company=company,
        created_on=created_on,
        note=(note or "").strip()[:200],
        created_by=user,
    )
    if pieces:
        add_pieces(batch=batch, pieces=pieces, user=user, at=created_on)
    return batch


@transaction.atomic
def add_pieces(*, batch, pieces, user, at=None):
    """Put pieces in store into a draft batch of the same company."""
    batch = _lock_batch(batch)
    if not batch.is_draft:
        raise DefectiveError(
            f"{batch.number} was dispatched on {batch.dispatched_on:%d-%m-%Y}, so it is locked. Start a new batch."
        )
    pieces = _lock(pieces)
    if not pieces:
        raise DefectiveError("Tick at least one piece.")
    for p in pieces:
        if p.company_id != batch.company_id:
            raise DefectiveError(
                f"{batch.number} is for {batch.company.name}, but {p.tag} is a {p.company.name} piece. "
                "A batch holds one company's pieces only."
            )
        if p.status != PieceStatus.IN_STORE:
            raise DefectiveError(_not_in_store(p, "added"))
    at = at or timezone.localdate()
    for p in pieces:
        _move(p, PieceStatus.IN_BATCH, at=at, user=user, note=f"Added to {batch.number}")
        p.return_batch = batch
        p.save(update_fields=["status", "return_batch"])
        BatchLine.objects.create(batch=batch, piece=p)
    return batch


@transaction.atomic
def remove_pieces(*, batch, pieces, user, at=None):
    """Take pieces out of a draft batch; they are back in store."""
    batch = _lock_batch(batch)
    if not batch.is_draft:
        raise DefectiveError(f"{batch.number} is dispatched and locked.")
    pieces = _lock(pieces)
    for p in pieces:
        if p.return_batch_id != batch.pk or p.status != PieceStatus.IN_BATCH:
            raise DefectiveError(f"{p.tag} is not in {batch.number}.")
    at = at or timezone.localdate()
    for p in pieces:
        _move(p, PieceStatus.IN_STORE, at=at, user=user, note=f"Removed from {batch.number}")
        p.return_batch = None
        p.save(update_fields=["status", "return_batch"])
    BatchLine.objects.filter(batch=batch, piece__in=pieces).delete()
    return batch


@transaction.atomic
def dispatch(*, batch, dispatched_on, courier, docket_no, user):
    """Send a draft batch: one Stock OUT (RETURN_TO_COMPANY) from the Defective store, then lock the batch."""
    batch = _lock_batch(batch)
    if not batch.is_draft:
        raise DefectiveError(f"{batch.number} was already dispatched.")
    lines = list(batch.lines.select_related("piece__item"))
    if not lines:
        raise DefectiveError("An empty batch can't be dispatched. Add pieces first.")
    _check_date(dispatched_on, "The dispatch date", "Choose the dispatch date.")
    if dispatched_on < batch.created_on:
        raise DefectiveError(
            f"The dispatch date can't be before the batch was created ({batch.created_on:%d-%m-%Y})."
        )
    courier, docket_no = (courier or "").strip()[:60], (docket_no or "").strip()[:40]
    if not courier:
        raise DefectiveError("Choose the courier.")
    if not docket_no:
        raise DefectiveError("Enter the docket / LR number.")
    store = Location.defective_store()
    pieces = _lock([line.piece for line in lines])
    entry = post_entry(
        kind=EntryKind.OUT,
        entry_date=dispatched_on,
        lines=[Line(item, store, -n) for item, n in _per_item(pieces)],
        user=user,
        subtype=ServiceSubtype.RETURN_TO_COMPANY,
        party=batch.company.name,
        company=batch.company,
        ref=docket_no,
        note=f"{courier} {docket_no}",
        return_batch=batch,
    )
    batch.status, batch.dispatched_on, batch.dispatch_entry = BatchStatus.DISPATCHED, dispatched_on, entry
    batch.courier, batch.docket_no = courier, docket_no
    batch.save(update_fields=["status", "dispatched_on", "dispatch_entry", "courier", "docket_no"])
    for p in pieces:
        _move(
            p,
            PieceStatus.SENT,
            at=dispatched_on,
            user=user,
            note=f"Dispatched with {batch.number} ({courier} {docket_no})",
            entry=entry,
        )
        p.save(update_fields=["status"])
    return entry


@transaction.atomic
def settle(*, batch, pieces, outcome, settled_on, user, to_location=None):
    """Record the company's answer for sent pieces. One ledger entry per piece:

    REPLACED / REPAIRED: Stock IN (REPLACEMENT) of 1 into `to_location`, a good-stock location.
    REJECTED_RETURNED: Stock IN (DEFECTIVE_RETURNED) of 1 back into the Defective store; the piece is in store.
    REJECTED_SCRAPPED: nothing to post, the piece already left with the dispatch OUT.
    Returns the entries posted.
    """
    batch = _lock_batch(batch)
    if batch.is_draft:
        raise DefectiveError("Only a dispatched batch can be settled.")
    pieces = _lock(pieces)
    if not pieces:
        raise DefectiveError("Tick the pieces the company has answered for.")
    if outcome not in Outcome.values:
        raise DefectiveError("Choose the outcome.")
    _check_date(settled_on, "The date", "Choose the settlement date.")
    if settled_on < batch.dispatched_on:
        raise DefectiveError(
            f"The date can't be before the batch was dispatched ({batch.dispatched_on:%d-%m-%Y})."
        )
    good = outcome in GOOD_OUTCOMES
    if good and (to_location is None or to_location.is_defective_store or not to_location.is_active):
        raise DefectiveError("Choose the good-stock location the replacement pieces go into.")
    for p in pieces:
        if p.return_batch_id != batch.pk:
            raise DefectiveError(f"{p.tag} is not in {batch.number}.")
        if p.status != PieceStatus.SENT:
            raise DefectiveError(
                f"{p.tag} is not waiting on the company (it is {p.get_status_display().lower()}). "
                "Only sent pieces can be settled."
            )
    store = Location.defective_store()
    label = Outcome(outcome).label
    entries = []
    for p in pieces:
        entry = None
        common = {
            "kind": EntryKind.IN,
            "entry_date": settled_on,
            "user": user,
            "party": batch.company.name,
            "company": batch.company,
            "ref": batch.number,
            "return_batch": batch,
        }
        if good:
            entry = post_entry(
                lines=[Line(p.item, to_location, 1)],
                subtype=ServiceSubtype.REPLACEMENT,
                note=f"{label} for {p.tag}",
                **common,
            )
        elif outcome == Outcome.REJECTED_RETURNED:
            entry = post_entry(
                lines=[Line(p.item, store, 1, p.batch_code, p.pkd)],
                subtype=ServiceSubtype.DEFECTIVE_RETURNED,
                note=f"Rejected by company, {p.tag} sent back",
                **common,
            )
        to = PieceStatus.IN_STORE if outcome == Outcome.REJECTED_RETURNED else PieceStatus.SETTLED
        where = f" → {to_location.name}" if good else ""
        _move(p, to, at=settled_on, user=user, note=f"{batch.number}: {label}{where}", entry=entry)
        p.outcome, p.settled_on = outcome, settled_on
        if good:
            p.replacement_entry = entry
        if to == PieceStatus.IN_STORE:
            p.return_batch = None
        p.save(update_fields=["status", "outcome", "settled_on", "replacement_entry", "return_batch"])
        BatchLine.objects.filter(batch=batch, piece=p).update(
            outcome=outcome, settled_on=settled_on, to_location=to_location if good else None, entry=entry
        )
        if entry:
            entries.append(entry)
    return entries
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/defectives -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/defectives/services.py tests/defectives/test_batch_services.py
git commit -m "feat(defectives): return batches (draft, dispatch, settle) posted through the ledger"
```

---

### Task 6: Shared line parsing and line editor, Mark defective page

**Files:**
- Create: `apps/core/tokens.py`; Modify: `apps/inventory/views.py` (use it)
- Modify: `apps/inventory/entry_lines.py` (prefix, fault, `collect` / `mark` modes, `allow_empty`)
- Modify: `apps/inventory/forms.py` (`first_error` moves into `TablerFormMixin`)
- Modify: `apps/inventory/context_processors.py` (Defectives section)
- Create: `apps/defectives/forms.py`, `apps/defectives/views.py`, `apps/defectives/urls.py`; Modify: `config/urls.py`
- Create: `templates/defectives/mark.html`, `static/js/line-editor.js`
- Test: `tests/inventory/test_entry_lines.py` (append), `tests/defectives/test_mark_view.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/inventory/test_entry_lines.py` (add `from datetime import date` to the imports):
```python
def service_post(prefix, rows):
    q = QueryDict(mutable=True)
    for row in rows:
        for name in ("item", "qty", "batch", "pkd", "fault"):
            q.appendlist(f"{prefix}_{name}", str(row.get(name, "")))
    return q


def test_raw_lines_reads_a_prefix_and_the_fault():
    rows = raw_lines(service_post("col", [{"item": 7, "qty": 2, "fault": "no output"}]), "col")
    assert rows == [{"item": "7", "qty": "2", "batch": "", "pkd": "", "expected": "", "fault": "no output"}]


def test_collect_lines_keep_batch_pkd_fault_and_allow_repeats():
    a = make_item("LG78-150-700")
    q = service_post(
        "col",
        [
            {"item": a.pk, "qty": 2, "batch": "B2405", "pkd": "2026-03", "fault": "no output"},
            {"item": a.pk, "qty": 1, "fault": "burnt"},
        ],
    )
    parsed = parse_lines(raw_lines(q, "col"), "collect")
    assert [(p.qty, p.batch, p.pkd, p.fault) for p in parsed] == [
        (2, "B2405", date(2026, 3, 1), "no output"),
        (1, "", None, "burnt"),
    ]


def test_mark_lines_refuse_the_same_item_twice():
    a = make_item("X9")
    q = service_post("line", [{"item": a.pk, "qty": 1, "fault": "a"}, {"item": a.pk, "qty": 1, "fault": "b"}])
    with pytest.raises(StockError, match="The same item is on two lines"):
        parse_lines(raw_lines(q), "mark")


def test_allow_empty_returns_no_lines():
    rows = raw_lines(service_post("part", [{}]), "part")
    assert parse_lines(rows, "out", allow_empty=True) == []
    with pytest.raises(StockError, match="Add at least one item."):
        parse_lines(rows, "out")
```

Create `tests/defectives/test_mark_view.py`:
```python
import pytest
from django.utils import timezone

from apps.defectives.models import DefectivePiece
from apps.inventory.models import StockEntry
from tests.factories import give_stock, loc, make_item

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate().isoformat()
URL = "/defectives/mark/"


def submit(client, data):
    """Open the page (which issues a one-time token), then post with that token."""
    client.get(URL)
    return client.post(URL, {**data, "entry_token": client.session["entry_tokens"][-1]})


def mark_data(item, qty, fault="Dead on arrival"):
    return {
        "entry_date": TODAY,
        "location": loc().pk,
        "line_item": [str(item.pk)],
        "line_qty": [str(qty)],
        "line_fault": [fault],
    }


@pytest.fixture
def drv(office_user):
    item = make_item("LG78-150-700")
    give_stock(item, 5, office_user)
    return item


def test_page_offers_good_locations_and_a_mark_editor(office_client, drv):
    html = office_client.get(URL).content.decode()
    assert "Mark defective from stock" in html and "Defective store</option>" not in html
    assert 'id="items-data"' in html and 'data-lines="line"' in html and 'data-mode="mark"' in html


def test_mark_saves_one_transfer_and_tags_pieces(office_client, drv):
    r = submit(office_client, mark_data(drv, 2))
    entry = StockEntry.objects.get(subtype="MARK_DEFECTIVE")
    assert r.status_code == 302 and r.url == f"/entries/{entry.number}/"
    assert list(DefectivePiece.objects.order_by("tag").values_list("tag", flat=True)) == ["DEF-0001", "DEF-0002"]
    assert "New defective tags: DEF-0001, DEF-0002." in office_client.get(r.url).content.decode()


def test_mark_needs_a_fault(office_client, drv):
    html = submit(office_client, mark_data(drv, 1, fault="")).content.decode()
    assert "Line 1: write what is wrong with the piece. Nothing was saved." in html
    assert not DefectivePiece.objects.exists()


def test_mark_over_quantity_is_refused(office_client, drv):
    html = submit(office_client, mark_data(drv, 9)).content.decode()
    assert "Only 5 NOS of LG78-150-700 at Vizag Office. Nothing was saved." in html


def test_resubmitting_does_not_mark_twice(office_client, drv):
    office_client.get(URL)
    data = {**mark_data(drv, 1), "entry_token": office_client.session["entry_tokens"][-1]}
    first = office_client.post(URL, data)
    again = office_client.post(URL, data)
    assert again.url == first.url and DefectivePiece.objects.count() == 1


def test_item_param_prefills_a_line(office_client, drv):
    html = office_client.get(f"{URL}?item={drv.pk}").content.decode()
    assert f'"item": "{drv.pk}"' in html


def test_nav_links_mark_defective(office_client):
    assert 'href="/defectives/mark/"' in office_client.get("/").content.decode()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/inventory/test_entry_lines.py tests/defectives/test_mark_view.py -q`
Expected: FAIL (`raw_lines()` takes 1 positional argument; `/defectives/mark/` is 404).

- [ ] **Step 3: Move the one-time form tokens to `apps/core/tokens.py`**

```python
"""One-time form tokens: a resubmitted form (double click, Back + Save) never saves twice.

Each page gets a fresh token. Saving spends it and remembers what it saved (an entry or complaint number),
so a second submit of the same token is sent to what was already saved instead of saving again.
"""

import uuid

TOKENS, SAVED, KEEP_TOKENS = "entry_tokens", "entry_saved", 20
EXPIRED = "This form had expired, so nothing was saved. Check the details and save again."


def new_token(session):
    token = uuid.uuid4().hex
    session[TOKENS] = [*session.get(TOKENS, []), token][-KEEP_TOKENS:]
    return token


def spend_token(session, token, saved):
    session[TOKENS] = [t for t in session.get(TOKENS, []) if t != token]
    done = {**session.get(SAVED, {}), token: saved}
    session[SAVED] = dict(list(done.items())[-KEEP_TOKENS:])


def already_saved(session, token):
    """What this token saved before (e.g. 'TRF-0004'), or None."""
    return session.get(SAVED, {}).get(token)


def is_issued(session, token):
    return token in session.get(TOKENS, [])
```

In `apps/inventory/views.py`: delete `import uuid`, delete the block from the comment `# One-time form tokens stop a resubmitted form ...` through the end of `_spend_token`, and add to the imports:
```python
from apps.core.tokens import SAVED, TOKENS
from apps.core.tokens import new_token as _new_token
from apps.core.tokens import spend_token as _spend_token
```
(The session keys stay `entry_tokens` / `entry_saved`, so the existing entry-form tests keep passing.)

- [ ] **Step 4: Generalise `apps/inventory/entry_lines.py`**

Replace the module docstring, `FIELDS`, `ParsedLine`, `raw_lines` and `parse_lines` (keep `MAX_QTY`, `MAX_DIGITS`, `DIGITS`, `_month`, `_digits`, `_small`, `_qty` as they are):
```python
"""Read the item lines a form posts as parallel arrays <prefix>_item, <prefix>_qty, <prefix>_batch, <prefix>_pkd,
<prefix>_fault (prefix "line" on the stock forms), plus line_expected on the adjust form (the system quantity the
user saw when typing the count). The service pages use other prefixes: "part" (parts given on a visit) and
"col" (failed parts collected)."""
```
```python
FIELDS = ("item", "qty", "batch", "pkd", "expected", "fault")
IN_LIKE = ("in", "collect")  # lines that bring stock in: the same item may be on several lines (batches)
```
```python
class ParsedLine(NamedTuple):
    item: Item
    qty: int
    batch: str
    pkd: date | None
    expected: int | None  # adjust only; None when not sent
    n: int  # the line number the user sees (blank rows still count)
    fault: str = ""  # mark defective / failed parts collected


def raw_lines(post, prefix="line"):
    """[{item, qty, batch, pkd, expected, fault}] exactly as typed (strings); sent back to the page on errors."""
    columns = [post.getlist(f"{prefix}_{name}") for name in FIELDS]
    count = max((len(c) for c in columns), default=0)
    return [
        {name: (col[n].strip() if n < len(col) else "") for name, col in zip(FIELDS, columns, strict=True)}
        for n in range(count)
    ]
```
```python
def parse_lines(rows, mode, allow_empty=False):
    """[ParsedLine] for mode in|out|trf|adj (stock forms) or collect|mark (service forms).

    Raises StockError with the first problem. Blank rows are skipped but still counted, so "Line 2" is the
    second row on the screen. allow_empty returns [] instead of "Add at least one item." (a visit may give
    no parts).
    """
    ids = [_small(r["item"]) for r in rows]
    items = Item.objects.in_bulk([i for i in ids if i is not None])
    parsed = []
    for n, (row, item_id) in enumerate(zip(rows, ids, strict=True), start=1):
        if not any(row.get(name) for name in ("item", "qty", "batch", "pkd", "fault")):
            continue
        item = items.get(item_id)
        if item is None:
            raise StockError(f"Line {n}: choose an item.")
        if not item.is_active:
            raise StockError(f"Line {n}: this item is no longer active.")
        qty = _qty(row["qty"], n, mode)
        expected = _small(row.get("expected", "")) if mode == "adj" else None
        batch, pkd = row.get("batch", "")[:40], _month(row.get("pkd", ""), n)
        parsed.append(ParsedLine(item, qty, batch, pkd, expected, n, row.get("fault", "")[:200]))
    if not parsed:
        if allow_empty:
            return []
        raise StockError("Add at least one item.")
    if mode not in IN_LIKE and len({line.item.pk for line in parsed}) != len(parsed):
        raise StockError("The same item is on two lines. Combine them into one line.")
    return parsed
```

- [ ] **Step 5: `first_error` for every form (`apps/inventory/forms.py`)**

Move the `first_error` method out of `EntryHeaderForm` into `TablerFormMixin` (same body), so the new service forms can use it:
```python
    def first_error(self):
        """The first problem as one sentence, with the field's label when it belongs to a field."""
        name, errors = next(iter(self.errors.items()))
        if name == NON_FIELD_ERRORS:
            return errors[0]
        return f"{self.fields[name].label or name.replace('_', ' ').capitalize()}: {errors[0]}"
```

- [ ] **Step 6: The defectives form, view, URL and menu entry**

`apps/defectives/forms.py`:
```python
from django import forms

from apps.inventory.forms import EntryHeaderForm
from apps.inventory.models import Location


class MarkDefectiveForm(EntryHeaderForm):
    """Date and the good-stock location the faulty pieces were found at. No remarks box: each line has a fault."""

    note = None
    location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True), empty_label=None, label="Found at location"
    )
```

`apps/defectives/views.py`:
```python
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tokens import EXPIRED, already_saved, is_issued, new_token, spend_token
from apps.inventory import selectors as stock
from apps.inventory.entry_lines import parse_lines, raw_lines
from apps.inventory.services import StockError

from . import services
from .forms import MarkDefectiveForm
from .services import DefectiveError


@role_required(OFFICE)
def mark_defective(request):
    """Faulty pieces found in good stock: a transfer into the Defective store, one tag per piece."""
    initial = {"entry_date": timezone.localdate(), "location": stock.default_location()}
    form = MarkDefectiveForm(request.POST or None, initial=initial)
    error, lines, token = None, [], ""
    if request.method == "POST":
        lines = raw_lines(request.POST)
        token = request.POST.get("entry_token", "")
        done = already_saved(request.session, token)
        if done:
            messages.warning(request, "This was already saved.")
            return redirect("entry_detail", number=done)
        if not is_issued(request.session, token):
            token, error = "", EXPIRED
        elif form.is_valid():
            try:
                parsed = parse_lines(lines, "mark")
                entry, pieces = services.mark_defective(
                    location=form.cleaned_data["location"],
                    lines=[(p.item, p.qty, p.fault) for p in parsed],
                    entry_date=form.cleaned_data["entry_date"],
                    user=request.user,
                )
            except (StockError, DefectiveError) as exc:
                error = f"{exc.message} Nothing was saved."
            else:
                spend_token(request.session, token, entry.number)
                tags = ", ".join(p.tag for p in pieces)
                messages.success(
                    request, f"{entry.number} saved. New defective tag{'s' if len(pieces) > 1 else ''}: {tags}."
                )
                return redirect("entry_detail", number=entry.number)
        else:
            error = form.first_error()
    elif request.GET.get("item", "").isdecimal():
        lines = [{"item": request.GET["item"], "qty": "", "fault": ""}]
    items, balances = stock.picker_data()
    return render(
        request,
        "defectives/mark.html",
        {
            "form": form,
            "error": error,
            "token": token or new_token(request.session),
            "items_data": items,
            "balances_data": balances,
            "initial_lines": lines,
        },
    )
```

`apps/defectives/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path("defectives/mark/", views.mark_defective, name="mark_defective"),
]
```

`config/urls.py`: add `path("", include("apps.defectives.urls")),` after the inventory include.

`apps/inventory/context_processors.py`: insert this section into `NAV` directly before the `("Setup", ...)` section:
```python
    ("Defectives", [("mark_defective", "Mark defective", "alert-octagon", "", False)]),
```

- [ ] **Step 7: The page and the line editor**

`templates/defectives/mark.html`:
```html
{% extends "base.html" %}{% load static %}
{% block title %}Mark defective{% endblock %}
{% block pretitle %}Defectives{% endblock %}
{% block page_title %}<i class="ti ti-alert-octagon"></i> Mark defective from stock{% endblock %}
{% block content %}
<form method="post" novalidate data-lines-form>{% csrf_token %}<input type="hidden" name="entry_token" value="{{ token }}">
  <div class="card mb-3"><div class="card-header"><h3 class="card-title"><i class="ti ti-file-description"></i> Details</h3>
    <div class="card-subtitle ms-2 text-secondary">A piece in good stock turned out faulty</div></div>
    <div class="card-body"><div class="row g-3">
      <div class="col-12 col-md-3"><label class="form-label required" for="{{ form.entry_date.id_for_label }}">Date</label>
        <div class="input-icon"><span class="input-icon-addon"><i class="ti ti-calendar"></i></span>{{ form.entry_date }}</div></div>
      <div class="col-12 col-md-3"><label class="form-label required" for="{{ form.location.id_for_label }}">Found at location</label>{{ form.location }}</div>
      <div class="col-12 col-md-6 d-flex align-items-end"><div class="text-secondary small"><i class="ti ti-info-circle"></i> Moves the pieces out of good stock into the <b>Defective store</b> (a transfer) and gives each piece its own tag. Quantity 2 = 2 tags.</div></div>
    </div></div></div>
  <div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-list-details"></i> Faulty pieces</h3></div>
    <div class="card-body"><div data-lines="line" data-mode="mark" data-loc="id_location" data-initial="initial-lines" data-summary="lines-summary" data-add-label="Add another item"></div></div>
    <div class="card-footer d-flex flex-wrap align-items-center gap-2"><span id="lines-summary" class="text-secondary"></span>
      <div class="ms-auto btn-list"><a href="{{ nav_urls.defectives_dashboard|default:'/' }}" class="btn btn-link link-secondary">Cancel</a>
        <button type="submit" class="btn btn-primary"><i class="ti ti-device-floppy"></i> Mark as defective</button></div></div></div>
  <div id="form-error" class="mt-3" tabindex="-1" aria-live="polite">{% if error %}<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>{{ error }}</div></div></div>{% endif %}</div>
</form>
{{ items_data|json_script:"items-data" }}{{ balances_data|json_script:"balances-data" }}{{ initial_lines|json_script:"initial-lines" }}
{% endblock %}
{% block scripts %}<script src="{% static 'js/line-editor.js' %}"></script>{% endblock %}
```

`static/js/line-editor.js`:
```js
/* Item-line editors for the service pages (Mark defective, Record visit). Same look and rules as the stock entry
   forms (static/js/entry-form.js): searchable item picker with look-alike codes, live availability at the chosen
   location, and an over-issue warning. Every element <div data-lines="<prefix>" data-mode="out|mark|collect"
   data-loc="<location select id>" data-initial="<json_script id>" data-summary="<id>" data-add-label="…"> inside a
   <form data-lines-form> becomes an editor posting <prefix>_item, <prefix>_qty, <prefix>_batch, <prefix>_pkd and
   <prefix>_fault. The page also needs json_script blocks "items-data" and "balances-data". */
(function () {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Same rules as apps/inventory/normalise.normalise_code and search_key.
  const norm = s => String(s || "").toUpperCase().replace(/[`'"]/g, "").replace(/\s+/g, " ").replace(/^[ .,;:]+|[ .,;:]+$/g, "");
  const lookKey = s => norm(s).replace(/O/g, "0").replace(/I/g, "1")
    .replace(/(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)/g, "$1$2").replace(/[^A-Z0-9]/g, "");
  const HEADS = {
    out: ["#", "Item", "Available", "Quantity", ""],
    mark: ["#", "Item", "Available", "Quantity", "Fault", ""],
    collect: ["#", "Item", "Quantity", "Batch code", "PKD (packed)", "Fault", ""],
  };

  class LineEditor {
    constructor({ host, mode, prefix, items, balances, locSelect, addLabel, summaryEl }) {
      Object.assign(this, { host, mode, prefix, items, balances, locSelect, summaryEl, rows: [] });
      host.innerHTML = `<div class="lines-wrap"><table class="table table-vcenter lines-table mb-0"><thead><tr>${HEADS[mode]
        .map((h, i) => `<th${i === 0 ? ' class="w-1"' : ""}>${h}</th>`).join("")}</tr></thead><tbody></tbody></table></div>
        <button type="button" class="btn btn-outline-primary mt-3 add-line"><i class="ti ti-plus"></i> ${esc(addLabel || "Add another item")}</button>`;
      this.body = host.querySelector("tbody");
      host.querySelector(".add-line").addEventListener("click", () => this.add({}, true));
      if (locSelect) locSelect.addEventListener("change", () => this.rows.forEach(r => this.refresh(r)));
    }
    name(field) { return `${this.prefix}_${field}`; }
    option(i) { return { ...i, value: String(i.id), hay: norm([i.code, ...i.aliases, i.desc, i.cat, i.type, i.company].join(" ")) }; }
    qtyCell() {
      return `<td data-label="Quantity" style="min-width:9rem"><div class="input-group"><input type="number" name="${this.name("qty")}" class="form-control qty"
        min="1" max="1000000" step="1" inputmode="numeric" placeholder="0" aria-label="Quantity"><span class="input-group-text u">—</span></div>
        <div class="invalid-feedback d-block err"></div></td>`;
    }
    faultCell(placeholder) {
      return `<td data-label="Fault" class="c-fault"><input name="${this.name("fault")}" class="form-control fault" maxlength="200" placeholder="${placeholder}" aria-label="Fault"></td>`;
    }
    add(init = {}, focus = false) {
      const tr = document.createElement("tr"), row = { tr };
      const cells = {
        out: `<td data-label="Available" class="avail"></td>` + this.qtyCell(),
        mark: `<td data-label="Available" class="avail"></td>` + this.qtyCell() + this.faultCell("e.g. dead on arrival"),
        collect: this.qtyCell()
          + `<td data-label="Batch code"><input name="${this.name("batch")}" class="form-control batch" maxlength="40" placeholder="e.g. B2405" aria-label="Batch code"></td>`
          + `<td data-label="PKD (packed)"><input name="${this.name("pkd")}" class="form-control pkd" type="month" aria-label="PKD (packed)"></td>`
          + this.faultCell("e.g. no output"),
      }[this.mode];
      tr.innerHTML = `<td class="c-n text-secondary"></td><td class="c-item"><select name="${this.name("item")}" class="form-select" aria-label="Item"><option value=""></option></select>
        <small class="form-hint line-meta"></small></td>${cells}<td class="c-rm"><button type="button" class="btn btn-icon btn-ghost-danger remove" title="Remove line" aria-label="Remove line"><i class="ti ti-trash"></i></button></td>`;
      this.body.appendChild(tr);
      row.ts = new TomSelect(tr.querySelector("select"), {
        options: [...this.items.values()].map(i => this.option(i)), valueField: "value", labelField: "code", maxOptions: 60,
        closeAfterSelect: true, openOnFocus: false, placeholder: "Type code, old spelling or description…",
        score(search) { // text anywhere, or a look-alike code (O/0, I/1, hyphens, leading zeros)
          const t = norm(search), k = lookKey(search);
          return it => !t ? 1 : it.hay.includes(t) ? 2 : (k.length > 2 && it.keys.includes(k)) ? 1.5 : 0;
        },
        render: {
          option: d => `<div><span class="opt-code">${esc(d.code)}</span><span class="opt-meta">${esc(d.type)} · ${esc(d.desc)} · ${esc(d.company)}</span></div>`,
          item: d => `<div>${esc(d.code)}</div>`,
          no_results: () => `<div class="no-results">No matching item.</div>`,
        },
        onChange: () => this.refresh(row),
      });
      row.qty = tr.querySelector(".qty");
      row.qty.addEventListener("input", () => this.refresh(row));
      tr.querySelector(".remove").addEventListener("click", () => this.remove(row));
      this.rows.push(row);
      if (init.item && this.items.has(String(init.item))) row.ts.setValue(String(init.item), true);
      row.qty.value = init.qty || "";
      for (const f of ["batch", "pkd", "fault"]) { const el = tr.querySelector(`.${f}`); if (el) el.value = init[f] || ""; }
      this.number(); this.refresh(row);
      if (focus) setTimeout(() => row.ts.focus(), 0);
    }
    remove(row) {
      if (this.rows.length === 1) { row.ts.clear(); row.tr.querySelectorAll("input").forEach(i => { i.value = ""; }); this.refresh(row); return; }
      row.ts.destroy(); row.tr.remove(); this.rows.splice(this.rows.indexOf(row), 1); this.number(); this.summary();
    }
    number() { this.rows.forEach((r, n) => { r.tr.querySelector(".c-n").textContent = n + 1; }); }
    refresh(row) {
      const it = this.items.get(row.ts.getValue()), unit = it ? it.unit : "—";
      row.tr.querySelectorAll(".u").forEach(s => { s.textContent = unit; });
      row.tr.querySelector(".line-meta").textContent = it ? `${it.type} · ${it.desc}` : "";
      const err = row.tr.querySelector(".err");
      err.textContent = ""; row.qty.classList.remove("is-invalid");
      const avail = row.tr.querySelector(".avail");
      if (avail && this.locSelect) {
        if (!it) { avail.textContent = ""; } else {
          const n = this.balances[`${it.id}-${this.locSelect.value}`] || 0;
          const place = this.locSelect.options[this.locSelect.selectedIndex].text;
          avail.innerHTML = `<b>${n}</b> ${esc(unit)} <span class="text-secondary d-block small">at ${esc(place)}</span>`;
          if (Number(row.qty.value) > n) { err.textContent = `Only ${n} ${unit} available`; row.qty.classList.add("is-invalid"); }
        }
      }
      this.summary();
    }
    summary() {
      if (!this.summaryEl) return;
      const totals = {}, chosen = this.rows.filter(r => r.ts.getValue());
      for (const r of chosen) { const it = this.items.get(r.ts.getValue()), v = Number(r.qty.value); if (it && v > 0) totals[it.unit] = (totals[it.unit] || 0) + v; }
      const parts = Object.entries(totals).map(([u, q]) => `${q} ${u}`);
      this.summaryEl.textContent = chosen.length ? `${chosen.length} item${chosen.length > 1 ? "s" : ""}${parts.length ? " · " + parts.join(" · ") : ""}` : "";
    }
    invalid() { return this.rows.find(r => r.qty.classList.contains("is-invalid")) || null; }
  }
  window.LineEditor = LineEditor;

  const form = document.querySelector("form[data-lines-form]");
  if (!form) return;
  const json = id => JSON.parse(document.getElementById(id).textContent);
  const items = new Map(json("items-data").map(i => [String(i.id), i]));
  const balances = json("balances-data");
  const editors = [...form.querySelectorAll("[data-lines]")].map(host => {
    const ed = new LineEditor({
      host, mode: host.dataset.mode, prefix: host.dataset.lines, items, balances,
      locSelect: host.dataset.loc ? document.getElementById(host.dataset.loc) : null,
      addLabel: host.dataset.addLabel, summaryEl: host.dataset.summary ? document.getElementById(host.dataset.summary) : null,
    });
    const initial = json(host.dataset.initial);
    (initial.length ? initial : [{}]).forEach(line => ed.add(line));
    return ed;
  });
  const errorBox = document.getElementById("form-error");
  form.addEventListener("input", () => { errorBox.innerHTML = ""; });
  form.addEventListener("submit", e => {
    const bad = editors.map(ed => ed.invalid()).find(Boolean);
    if (bad) {
      e.preventDefault();
      errorBox.innerHTML = `<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>Fix the highlighted quantities first.</div></div></div>`;
      bad.qty.focus();
      return;
    }
    const save = form.querySelector("button[type=submit]");
    save.disabled = true; save.classList.add("btn-loading"); // one click, one save
  });
  window.addEventListener("pageshow", e => { // coming Back to a cached page: allow saving again
    if (!e.persisted) return;
    const save = form.querySelector("button[type=submit]");
    save.disabled = false; save.classList.remove("btn-loading");
  });
  if (errorBox.textContent.trim()) { errorBox.scrollIntoView({ block: "center" }); errorBox.focus({ preventScroll: true }); }
})();
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS (whole suite, including the existing entry-form tests that use the moved tokens).

- [ ] **Step 9: Check it in a browser**

Run the dev server on `svkml_demo` (see "Local test environment"), open http://127.0.0.1:8000/defectives/mark/, pick an item, type a quantity above the available figure (red "Only N NOS available" appears and Save is refused), fix it, write a fault and save. Expected: redirected to the TRF entry page with "New defective tag: DEF-…" and no console errors.

- [ ] **Step 10: Commit**

```bash
git add apps/core/tokens.py apps/inventory/views.py apps/inventory/entry_lines.py apps/inventory/forms.py apps/inventory/context_processors.py apps/defectives/forms.py apps/defectives/views.py apps/defectives/urls.py config/urls.py templates/defectives/mark.html static/js/line-editor.js tests/inventory/test_entry_lines.py tests/defectives/test_mark_view.py
git commit -m "feat(defectives): Mark defective page with a reusable item-line editor"
```

---

### Task 7: Return batch screens (list, new batch, batch detail with dispatch and settle) and the piece card

**Files:**
- Modify: `apps/core/templatetags/core_tags.py` (add `st_badge`)
- Modify: `apps/defectives/models.py` (add `BATCH_LABELS`)
- Create: `apps/defectives/selectors.py`, `apps/defectives/filters.py`, `apps/defectives/templatetags/__init__.py` (empty), `apps/defectives/templatetags/defective_tags.py`
- Modify: `apps/defectives/forms.py` (`DispatchForm`, `SettleForm`), `apps/defectives/views.py`, `apps/defectives/urls.py`
- Modify: `apps/inventory/context_processors.py` (menu entry, active aliases)
- Create: `templates/defectives/_source.html`, `templates/defectives/batches.html`, `templates/defectives/batch_new.html`, `templates/defectives/batch_detail.html`, `templates/defectives/piece_detail.html`, `static/js/service.js`
- Test: `tests/defectives/test_batch_views.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/defectives/test_batch_views.py`:
```python
import pytest
from django.utils import timezone

from apps.defectives.models import BatchStatus, Outcome, ReturnBatch
from apps.defectives.services import create_batch, dispatch, settle
from apps.inventory.models import Company
from tests.factories import loc, make_item, make_pieces

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def wipro():
    return Company.objects.get(name="Wipro Lighting")


@pytest.fixture
def pieces(office_user):
    """DEF-0001..0003 (Wipro), after IN-0001 (stock) and TRF-0001 (marked defective)."""
    return make_pieces(make_item("LG78-150-700", description="LED driver 150W"), 3, office_user)


def test_new_batch_offers_only_that_companys_pieces(office_client, office_user, pieces):
    make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user)
    html = office_client.get(f"/defectives/batches/new/?company={wipro().pk}").content.decode()
    assert "DEF-0001" in html and "DEF-0004" not in html
    assert ">Havells</option>" in html and ">Wipro Lighting</option>" in html


def test_create_batch_from_the_form(office_client, pieces):
    r = office_client.post(
        "/defectives/batches/new/", {"company": wipro().pk, "tag": ["DEF-0001", "DEF-0002"], "note": "Bank sites"}
    )
    assert r.status_code == 302 and r.url == "/defectives/batches/RB-0001/"
    b = ReturnBatch.objects.get()
    assert b.note == "Bank sites" and b.lines.count() == 2


def test_new_batch_needs_a_company(office_client, pieces):
    html = office_client.post("/defectives/batches/new/", {"tag": ["DEF-0001"]}).content.decode()
    assert "Choose the company the pieces go back to." in html and not ReturnBatch.objects.exists()


def test_draft_add_by_typed_tag_and_remove(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    url = f"/defectives/batches/{b.number}/"
    html = office_client.get(url).content.decode()
    assert "Draft" in html and "Dispatch" in html and "DEF-0002" in html
    html = office_client.post(url + "add/", {"tag_text": "def-2"}, follow=True).content.decode()
    assert "DEF-0002 added to RB-0001." in html and b.lines.count() == 2
    html = office_client.post(url + "remove/", {"tag": "DEF-0001"}, follow=True).content.decode()
    assert "DEF-0001 removed from RB-0001. It is back in store." in html
    html = office_client.post(url + "add/", {"tag_text": "DEF-0099"}, follow=True).content.decode()
    assert "There is no piece tagged DEF-0099." in html


def test_add_ticked_pieces(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user)
    office_client.post(f"/defectives/batches/{b.number}/add/", {"tag": ["DEF-0002", "DEF-0003"]})
    assert sorted(b.lines.values_list("piece__tag", flat=True)) == ["DEF-0002", "DEF-0003"]


def test_dispatch_and_settle_from_the_detail_page(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:2])
    url = f"/defectives/batches/{b.number}/"
    day = TODAY.isoformat()
    html = office_client.post(
        url + "dispatch/", {"dispatched_on": day, "courier": "DTDC", "docket_no": "D51243817"}, follow=True
    ).content.decode()
    assert "RB-0001 dispatched. Stock OUT OUT-0001 posted from the Defective store." in html
    assert "Settle ticked pieces" in html and "D51243817" in html
    html = office_client.post(
        url + "settle/", {"tag": ["DEF-0001"], "outcome": "REPLACED", "settled_on": day, "to_location": loc().pk}, follow=True
    ).content.decode()
    assert "1 piece(s) settled as Replaced. Entries: IN-0002." in html and "Partly settled" in html
    html = office_client.post(
        url + "settle/", {"tag": ["DEF-0002"], "outcome": "REJECTED_RETURNED", "settled_on": day}, follow=True
    ).content.decode()
    assert "settled as Rejected (returned)" in html and "All pieces are settled." in html
    assert ReturnBatch.objects.get().status == BatchStatus.DISPATCHED


def test_dispatch_errors_are_shown(office_client, office_user):
    b = create_batch(company=wipro(), user=office_user)
    html = office_client.post(
        f"/defectives/batches/{b.number}/dispatch/",
        {"dispatched_on": TODAY.isoformat(), "courier": "DTDC", "docket_no": "D1"},
        follow=True,
    ).content.decode()
    assert "An empty batch" in html


def test_batches_list_shows_the_worked_out_status(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:2])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(batch=b, pieces=pieces[:1], outcome=Outcome.REPLACED, settled_on=TODAY, to_location=loc(), user=office_user)
    create_batch(company=wipro(), user=office_user)  # RB-0002, a draft
    html = office_client.get("/defectives/batches/").content.decode()
    assert "Partly settled" in html and "1 / 2" in html and "RB-0002" in html
    html = office_client.get("/defectives/batches/?status=Partly+settled").content.decode()
    assert "RB-0001" in html and "RB-0002" not in html


def test_piece_card_shows_history_batches_and_entries(office_client, office_user, pieces):
    b = create_batch(company=wipro(), user=office_user, pieces=pieces[:1])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(batch=b, pieces=pieces[:1], outcome=Outcome.REJECTED_RETURNED, settled_on=TODAY, user=office_user)
    html = office_client.get("/defectives/pieces/DEF-0001/").content.decode()
    assert "Marked defective from stock" in html and "Dispatched with RB-0001 (DTDC D1)" in html
    assert "Rejected (returned)" in html and "In store" in html
    assert "TRF-0001" in html and "OUT-0001" in html and "IN-0002" in html


def test_nav_links_return_batches(office_client):
    assert 'href="/defectives/batches/"' in office_client.get("/").content.decode()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/defectives/test_batch_views.py -q`
Expected: FAIL (404 on `/defectives/batches/new/`).

- [ ] **Step 3: Badge helper, labels, selectors, filters, template tags**

`apps/core/templatetags/core_tags.py`, add:
```python
@register.simple_tag
def st_badge(css, icon, word):
    """A status badge: colour + icon + word (DESIGN.md: colour is never the only signal)."""
    return format_html('<span class="badge st {}"><i class="ti ti-{}"></i>{}</span>', css, icon, word)
```

`apps/defectives/models.py`, below `class BatchStatus`:
```python
# What a batch shows: the stored DRAFT / DISPATCHED, split by how many lines the company has answered.
BATCH_LABELS = ("Draft", "Dispatched", "Partly settled", "Settled")
```

`apps/defectives/selectors.py`:
```python
"""All reads for the defectives screens. Views call these; no queries in templates."""

from django.conf import settings
from django.db.models import Count, Q

from .models import DefectivePiece, ReturnBatch, Source

# What a piece row shows. Task 10 adds the complaint and site of the visit that collected it.
PIECE_RELATED = ["item", "company", "return_batch"]


def pieces_qs():
    return DefectivePiece.objects.select_related(*PIECE_RELATED)


def batch_label(batch, lines, settled):
    """'Draft', 'Dispatched', 'Partly settled' or 'Settled' (worked out, never stored)."""
    if batch.is_draft:
        return "Draft"
    if settled == 0:
        return "Dispatched"
    return "Partly settled" if settled < lines else "Settled"


def batches_with_counts():
    return ReturnBatch.objects.select_related("company").annotate(
        n_lines=Count("lines", distinct=True),
        n_settled=Count("lines", filter=~Q(lines__outcome=""), distinct=True),
    )


def batch_rows(f, today):
    """Return-batch list rows: {batch, label, waiting (days since dispatch while not fully settled)}."""
    batches = batches_with_counts()
    if f.company:
        batches = batches.filter(company=f.company)
    rows = []
    for b in batches:
        label = batch_label(b, b.n_lines, b.n_settled)
        if f.status and label != f.status:
            continue
        waiting = (today - b.dispatched_on).days if b.dispatched_on and label != "Settled" else None
        rows.append({"batch": b, "label": label, "waiting": waiting})
    return rows


def batch_lines(batch):
    """The batch's lines with their pieces, in tag order."""
    related = [f"piece__{name}" for name in PIECE_RELATED]
    return list(batch.lines.select_related(*related, "to_location", "entry").order_by("piece__tag"))


def courier_suggestions():
    """Couriers to suggest when dispatching: the configured list, then any others used before."""
    used = ReturnBatch.objects.exclude(courier="").order_by("-id").values_list("courier", flat=True)[:200]
    return list(dict.fromkeys([*settings.COURIERS, *used]))


def complaint_cells(piece):
    """[complaint no., company complaint no.] for the dispatch list. Task 10 fills these from the visit."""
    return ["Found in stock" if piece.source == Source.FOUND_IN_STOCK else "", ""]
```

`apps/defectives/filters.py`:
```python
"""Parse the defectives list screens' GET params once; views and Excel exports share them."""

from dataclasses import dataclass

from apps.inventory.filters import _obj
from apps.inventory.models import Company

from .models import BATCH_LABELS


@dataclass
class BatchFilters:
    company: Company | None
    status: str  # one of BATCH_LABELS, or "" for any


def batch_filters(params):
    status = params.get("status", "")
    return BatchFilters(_obj(Company, params.get("company")), status if status in BATCH_LABELS else "")
```

`apps/defectives/templatetags/defective_tags.py`:
```python
from django import template
from django.utils.html import format_html

from apps.core.templatetags.core_tags import st_badge

from ..models import Outcome, PieceStatus

register = template.Library()

# (css class, Tabler icon) per value. Red = needs attention, amber = waiting, green = done well, slate = neutral.
PIECE_STYLE = {
    PieceStatus.IN_STORE: ("st-neutral", "building-warehouse"),
    PieceStatus.IN_BATCH: ("st-neutral", "packages"),
    PieceStatus.SENT: ("st-wait", "truck"),
    PieceStatus.SETTLED: ("st-ok", "circle-check"),
    PieceStatus.SCRAPPED: ("st-done", "trash"),
}
OUTCOME_STYLE = {
    Outcome.REPLACED: ("st-ok", "replace"),
    Outcome.REPAIRED: ("st-ok", "tool"),
    Outcome.REJECTED_RETURNED: ("st-alert", "arrow-back"),
    Outcome.REJECTED_SCRAPPED: ("st-alert", "trash"),
}
BATCH_STYLE = {
    "Draft": ("st-neutral", "pencil"),
    "Dispatched": ("st-wait", "truck"),
    "Partly settled": ("st-wait", "progress-check"),
    "Settled": ("st-ok", "circle-check"),
}


@register.filter
def piece_badge(status):
    css, icon = PIECE_STYLE[status]
    return st_badge(css, icon, PieceStatus(status).label)


@register.filter
def piece_css(status):
    return PIECE_STYLE[status][0]


@register.filter
def piece_icon(status):
    return PIECE_STYLE[status][1]


@register.filter
def outcome_badge(outcome):
    if not outcome:
        return ""
    css, icon = OUTCOME_STYLE[outcome]
    return st_badge(css, icon, Outcome(outcome).label)


@register.filter
def batch_badge(label):
    css, icon = BATCH_STYLE[label]
    return st_badge(css, icon, label)


@register.filter
def pkd_month(value):
    return f"{value:%m-%Y}" if value else ""


@register.filter
def waiting_badge(days):
    """'12 days', or a red badge after 30 days. Empty when nothing is waiting."""
    if days is None:
        return ""
    if days > 30:
        return format_html('<span class="badge st st-alert"><i class="ti ti-alert-triangle"></i>{} days</span>', days)
    return f"{days} days"
```

- [ ] **Step 4: Forms, views and URLs**

Append to `apps/defectives/forms.py` (add `from apps.inventory.forms import TablerFormMixin` and `from .models import Outcome` to the imports):
```python
DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class DispatchForm(TablerFormMixin, forms.Form):
    """Parses the dispatch modal. The service gives the friendly messages for empty courier / docket."""

    dispatched_on = forms.DateField(
        label="Dispatch date", widget=DATE, error_messages={"required": "Choose the dispatch date."}
    )
    courier = forms.CharField(max_length=60, required=False)
    docket_no = forms.CharField(max_length=40, required=False, label="Docket / LR no.")


class SettleForm(TablerFormMixin, forms.Form):
    """Parses the settle panel. Missing outcome / date / location get the service's messages."""

    outcome = forms.ChoiceField(choices=Outcome.choices, required=False, widget=forms.RadioSelect)
    settled_on = forms.DateField(required=False, label="Date answered", widget=DATE)
    to_location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True), required=False, label="Goes into location"
    )
```

Replace `apps/defectives/views.py` imports with the full set below and append the new views (keep `mark_defective` as it is):
```python
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.tables import sort_and_page
from apps.core.tokens import EXPIRED, already_saved, is_issued, new_token, spend_token
from apps.inventory import selectors as stock
from apps.inventory.entry_lines import parse_lines, raw_lines
from apps.inventory.filters import _obj
from apps.inventory.models import Company, Location
from apps.inventory.services import StockError

from . import selectors, services
from .filters import batch_filters
from .forms import DispatchForm, MarkDefectiveForm, SettleForm
from .models import BATCH_LABELS, BatchStatus, DefectivePiece, Outcome, PieceStatus, ReturnBatch
from .services import DefectiveError, normalise_tag
from .templatetags.defective_tags import OUTCOME_STYLE


def _back(request, fallback):
    """Where to go after a POST: the page's `next` (this site only), else `fallback`."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback
```
```python
@role_required(OFFICE)
def piece_detail(request, tag):
    piece = get_object_or_404(
        selectors.pieces_qs().select_related("item__spare_type", "replacement_entry"), tag=tag
    )
    events = list(piece.events.select_related("by", "entry").order_by("-at", "-id"))
    entries = list(dict.fromkeys(ev.entry for ev in reversed(events) if ev.entry_id))
    drafts = []
    if piece.status == PieceStatus.IN_STORE:
        drafts = ReturnBatch.objects.filter(status=BatchStatus.DRAFT, company=piece.company)
    return render(
        request,
        "defectives/piece_detail.html",
        {
            "piece": piece,
            "events": events,
            "entries": entries,
            "lines": piece.batch_lines.select_related("batch", "to_location", "entry").order_by("-batch_id"),
            "drafts": drafts,
        },
    )


@role_required(OFFICE)
def return_batches(request):
    f = batch_filters(request.GET)
    rows = selectors.batch_rows(f, timezone.localdate())
    sorters = {
        "no": lambda r: r["batch"].number,
        "company": lambda r: r["batch"].company.name,
        "created": lambda r: r["batch"].created_on,
        "status": lambda r: BATCH_LABELS.index(r["label"]),
        "pieces": lambda r: r["batch"].n_lines,
        "settled": lambda r: r["batch"].n_settled,
        "disp": lambda r: r["batch"].dispatched_on,
        "wait": lambda r: r["waiting"] if r["waiting"] is not None else -1,
    }
    table = sort_and_page(request, rows, sorters, "no", "desc")
    return render(
        request,
        "defectives/batches.html",
        {"f": f, "table": table, "companies": Company.objects.filter(is_active=True), "labels": BATCH_LABELS},
    )


@role_required(OFFICE)
def batch_new(request):
    """Pick a company, tick its pieces in store, create a draft batch."""
    source = request.POST if request.method == "POST" else request.GET
    company = _obj(Company, source.get("company"))
    ticked = set(source.getlist("tag"))
    error = None
    if request.method == "POST":
        chosen = list(DefectivePiece.objects.filter(tag__in=ticked).select_related("company"))
        try:
            batch = services.create_batch(
                company=company, user=request.user, pieces=chosen, note=request.POST.get("note", "")
            )
        except DefectiveError as exc:
            error = exc.message
        else:
            messages.success(
                request,
                f"Draft batch {batch.number} created for {batch.company.name} with {len(chosen)} piece(s).",
            )
            return redirect("batch_detail", number=batch.number)
    available = []
    if company:
        available = list(
            selectors.pieces_qs().filter(company=company, status=PieceStatus.IN_STORE).order_by("tag")
        )
    companies = Company.objects.filter(defective_pieces__status=PieceStatus.IN_STORE).distinct().order_by("name")
    return render(
        request,
        "defectives/batch_new.html",
        {
            "companies": companies,
            "company": company,
            "ticked": ticked,
            "available": available,
            "note": source.get("note", ""),
            "error": error,
        },
    )


@role_required(OFFICE)
def batch_detail(request, number):
    batch = get_object_or_404(ReturnBatch.objects.select_related("company", "dispatch_entry"), number=number)
    lines = selectors.batch_lines(batch)
    settled = sum(1 for line in lines if line.outcome)
    today = timezone.localdate()
    available = []
    if batch.is_draft:
        available = list(
            selectors.pieces_qs().filter(company=batch.company, status=PieceStatus.IN_STORE).order_by("tag")
        )
    return render(
        request,
        "defectives/batch_detail.html",
        {
            "batch": batch,
            "lines": lines,
            "settled": settled,
            "label": selectors.batch_label(batch, len(lines), settled),
            "sent": [ln for ln in lines if not ln.outcome and ln.piece.status == PieceStatus.SENT],
            "waiting": (today - batch.dispatched_on).days if batch.dispatched_on else 0,
            "today": today,
            "available": available,
            "locations": Location.objects.good().filter(is_active=True),
            "couriers": selectors.courier_suggestions(),
            "outcome_choices": [(v, label, OUTCOME_STYLE[v][1]) for v, label in Outcome.choices],
        },
    )


@role_required(OFFICE)
@require_POST
def batch_add(request, number):
    batch = get_object_or_404(ReturnBatch, number=number)
    typed = normalise_tag(request.POST.get("tag_text", ""))
    tags = [typed] if typed else request.POST.getlist("tag")
    try:
        if typed and not DefectivePiece.objects.filter(tag=typed).exists():
            raise DefectiveError(f"There is no piece tagged {typed}.")
        if not tags:
            raise DefectiveError("Type a tag (e.g. DEF-0042) or tick pieces to add.")
        services.add_pieces(batch=batch, pieces=list(DefectivePiece.objects.filter(tag__in=tags)), user=request.user)
    except DefectiveError as exc:
        messages.error(request, exc.message)
    else:
        added = ", ".join(sorted(tags)) if len(tags) <= 3 else f"{len(tags)} pieces"
        messages.success(request, f"{added} added to {batch.number}.")
    return redirect(_back(request, reverse("batch_detail", args=[number])))


@role_required(OFFICE)
@require_POST
def batch_remove(request, number):
    batch = get_object_or_404(ReturnBatch, number=number)
    tag = request.POST.get("tag", "")
    try:
        services.remove_pieces(batch=batch, pieces=list(DefectivePiece.objects.filter(tag=tag)), user=request.user)
    except DefectiveError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, f"{tag} removed from {batch.number}. It is back in store.")
    return redirect("batch_detail", number=number)


@role_required(OFFICE)
@require_POST
def batch_dispatch(request, number):
    batch = get_object_or_404(ReturnBatch, number=number)
    form = DispatchForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.first_error())
        return redirect("batch_detail", number=number)
    try:
        entry = services.dispatch(batch=batch, user=request.user, **form.cleaned_data)
    except (DefectiveError, StockError) as exc:
        messages.error(request, exc.message)
    else:
        messages.success(
            request, f"{batch.number} dispatched. Stock OUT {entry.number} posted from the Defective store."
        )
    return redirect("batch_detail", number=number)


@role_required(OFFICE)
@require_POST
def batch_settle(request, number):
    batch = get_object_or_404(ReturnBatch, number=number)
    form = SettleForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.first_error())
        return redirect("batch_detail", number=number)
    chosen = list(DefectivePiece.objects.filter(tag__in=request.POST.getlist("tag")))
    data = form.cleaned_data
    try:
        entries = services.settle(
            batch=batch,
            pieces=chosen,
            outcome=data["outcome"],
            settled_on=data["settled_on"],
            to_location=data["to_location"],
            user=request.user,
        )
    except (DefectiveError, StockError) as exc:
        messages.error(request, exc.message)
    else:
        made = f" Entries: {', '.join(e.number for e in entries)}." if entries else ""
        messages.success(request, f"{len(chosen)} piece(s) settled as {Outcome(data['outcome']).label}.{made}")
    return redirect("batch_detail", number=number)
```

`apps/defectives/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path("defectives/mark/", views.mark_defective, name="mark_defective"),
    path("defectives/pieces/<str:tag>/", views.piece_detail, name="piece_detail"),
    path("defectives/batches/", views.return_batches, name="return_batches"),
    path("defectives/batches/new/", views.batch_new, name="batch_new"),
    path("defectives/batches/<str:number>/", views.batch_detail, name="batch_detail"),
    path("defectives/batches/<str:number>/add/", views.batch_add, name="batch_add"),
    path("defectives/batches/<str:number>/remove/", views.batch_remove, name="batch_remove"),
    path("defectives/batches/<str:number>/dispatch/", views.batch_dispatch, name="batch_dispatch"),
    path("defectives/batches/<str:number>/settle/", views.batch_settle, name="batch_settle"),
]
```

`apps/inventory/context_processors.py`: the Defectives section becomes
```python
    (
        "Defectives",
        [
            ("mark_defective", "Mark defective", "alert-octagon", "", False),
            ("return_batches", "Return batches", "truck-return", "", False),
        ],
    ),
```
and `ACTIVE_ALIASES` gains `"batch_new": "return_batches"`, `"batch_detail": "return_batches"`, `"piece_detail": "defective_pieces"`.

- [ ] **Step 5: Templates and `service.js`**

`templates/defectives/_source.html`:
```html
{# Where a piece came from. Needs `p`, a DefectivePiece from selectors.pieces_qs(). Task 10 links the complaint. #}
{% if p.source == "SITE_VISIT" %}<span><i class="ti ti-map-pin text-secondary"></i> Site visit</span>{% else %}<span class="text-secondary"><i class="ti ti-building-warehouse"></i> Stock</span>{% endif %}
```

`templates/defectives/batches.html`:
```html
{% extends "base.html" %}{% load core_tags defective_tags %}
{% block title %}Return batches{% endblock %}
{% block pretitle %}Defectives{% endblock %}
{% block page_title %}Return batches{% endblock %}
{% block actions %}<a href="{% url 'batch_new' %}" class="btn btn-primary"><i class="ti ti-plus"></i> New batch</a>{% endblock %}
{% block content %}
<div class="card">
  <div class="card-header"><form method="get" class="row g-2 w-100 align-items-end">
    <div class="col-12 col-sm-6 col-lg-3"><label class="form-label small text-secondary mb-1" for="bf-co">Company</label>
      <select id="bf-co" name="company" class="form-select" onchange="this.form.submit()"><option value="">All companies</option>
        {% for c in companies %}<option value="{{ c.pk }}" {% if f.company == c %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-3"><label class="form-label small text-secondary mb-1" for="bf-st">Status</label>
      <select id="bf-st" name="status" class="form-select" onchange="this.form.submit()"><option value="">Any status</option>
        {% for label in labels %}<option value="{{ label }}" {% if f.status == label %}selected{% endif %}>{{ label }}</option>{% endfor %}</select></div>
  </form></div>
  <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
    <thead><tr>{% sort_th "no" "Batch" %}{% sort_th "company" "Company" %}{% sort_th "created" "Created" %}{% sort_th "status" "Status" %}{% sort_th "pieces" "Pieces" True %}{% sort_th "settled" "Settled" True %}{% sort_th "disp" "Dispatched" %}{% sort_th "wait" "Waiting" True %}<th>Note</th></tr></thead>
    <tbody>{% for r in table.page %}{% with b=r.batch %}<tr>
      <td><a class="code" href="{% url 'batch_detail' b.number %}">{{ b.number }}</a></td><td>{{ b.company.name }}</td><td class="nowrap">{{ b.created_on|date }}</td>
      <td>{{ r.label|batch_badge }}</td><td class="num">{{ b.n_lines }}</td>
      <td class="num">{% if b.is_draft %}<span class="text-secondary">—</span>{% else %}{{ b.n_settled }} / {{ b.n_lines }}{% endif %}</td>
      <td>{% if b.dispatched_on %}{{ b.dispatched_on|date }}<div class="small text-secondary">{{ b.courier }} · <span class="code">{{ b.docket_no }}</span></div>{% else %}<span class="text-secondary">Not yet</span>{% endif %}</td>
      <td class="num">{{ r.waiting|waiting_badge }}</td><td class="cell-wrap text-secondary">{{ b.note }}</td></tr>{% endwith %}
    {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No return batches match.</td></tr>{% endfor %}</tbody>
  </table></div>
  {% include "core/_pagination.html" %}
</div>
<p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> A batch holds one company's pieces. "Partly settled" and "Settled" come from the company's answers for its pieces.</p>
{% endblock %}
```

`templates/defectives/batch_new.html`:
```html
{% extends "base.html" %}{% load static %}
{% block title %}New return batch{% endblock %}
{% block pretitle %}Defectives · Return batches{% endblock %}
{% block page_title %}<i class="ti ti-plus"></i> New return batch{% endblock %}
{% block content %}
<form method="get" class="card mb-3"><div class="card-body"><div class="row g-3">
  <div class="col-12 col-md-5"><label class="form-label required" for="b-company">Company the pieces go back to</label>
    <select id="b-company" name="company" class="form-select" onchange="this.form.submit()"><option value="">Choose…</option>
      {% for c in companies %}<option value="{{ c.pk }}" {% if company == c %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select>
    <small class="form-hint">Only companies with pieces in store are listed.</small></div></div></div></form>
<form method="post" novalidate data-once>{% csrf_token %}{% if company %}<input type="hidden" name="company" value="{{ company.pk }}">{% endif %}
  <div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-tags"></i> Pieces in store</h3>
    <div class="card-subtitle ms-2 text-secondary">{% if company %}{{ available|length }} {{ company.name }} piece(s) in store{% else %}Choose the company first{% endif %}</div></div>
    <div class="card-body border-bottom"><label class="form-label" for="b-note">Note</label><input id="b-note" name="note" class="form-control" maxlength="200" value="{{ note }}" placeholder="e.g. Drivers from the bank sites"></div>
    {% if company %}<div class="table-responsive"><table class="table table-vcenter card-table">
      <thead><tr><th class="c-check"><input type="checkbox" class="form-check-input m-0" data-tick-all aria-label="Tick all"></th><th>Tag</th><th>Item</th><th>Source</th><th>Batch · PKD</th><th>Fault</th><th>Collected</th></tr></thead>
      <tbody>{% for p in available %}<tr><td class="c-check"><input type="checkbox" class="form-check-input m-0" name="tag" value="{{ p.tag }}" data-tick aria-label="Tick {{ p.tag }}"{% if p.tag in ticked %} checked{% endif %}></td>
        <td><a class="code" href="{% url 'piece_detail' p.tag %}">{{ p.tag }}</a></td><td><span class="code">{{ p.item.code }}</span><div class="small text-secondary">{{ p.item.description }}</div></td>
        <td>{% include "defectives/_source.html" %}</td><td class="nowrap">{{ p.batch_code|default:"—" }}{% if p.pkd %} · {{ p.pkd|date:"m-Y" }}{% endif %}</td><td class="cell-wrap">{{ p.fault }}</td><td class="nowrap">{{ p.collected_on|date }}</td></tr>
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No {{ company.name }} pieces in store.</td></tr>{% endfor %}</tbody></table></div>
    {% else %}<div class="card-body text-secondary">Only that company's pieces in store are offered.</div>{% endif %}
    <div class="card-footer d-flex flex-wrap align-items-center gap-2"><span class="text-secondary" data-tick-count></span><span class="text-secondary small">You can also create an empty draft and add pieces later.</span>
      <div class="ms-auto btn-list"><a href="{% url 'return_batches' %}" class="btn btn-link link-secondary">Cancel</a><button type="submit" class="btn btn-primary"><i class="ti ti-device-floppy"></i> Create draft batch</button></div></div></div>
  <div id="form-error" class="mt-3" aria-live="polite">{% if error %}<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>{{ error }}</div></div></div>{% endif %}</div>
</form>
{% endblock %}
{% block scripts %}<script src="{% static 'js/service.js' %}"></script>{% endblock %}
```

`templates/defectives/batch_detail.html`:
```html
{% extends "base.html" %}{% load static core_tags defective_tags %}
{% block title %}{{ batch.number }}{% endblock %}
{% block pretitle %}Return batch · {{ batch.company.name }}{% endblock %}
{% block page_title %}<span class="code">{{ batch.number }}</span> {{ label|batch_badge }}{% endblock %}
{% block actions %}
  {% if batch.is_draft %}<button type="button" class="btn btn-out" data-bs-toggle="modal" data-bs-target="#dispatch-modal"><i class="ti ti-truck"></i> Dispatch…</button>{% endif %}
  <a href="{% url 'return_batches' %}" class="btn btn-quiet"><i class="ti ti-list"></i> All batches</a>
{% endblock %}
{% block content %}
<div class="row row-cards">
  <div class="col-12"><div class="d-flex flex-wrap gap-2">
    <span class="chip"><i class="ti ti-building-store"></i> {{ batch.company.name }}</span>
    <span class="chip"><i class="ti ti-calendar"></i> Created {{ batch.created_on|date }}</span>
    <span class="chip"><i class="ti ti-tags"></i> <b>{{ lines|length }}</b> piece(s)</span>
    {% if not batch.is_draft %}
      <span class="chip"><i class="ti ti-truck"></i> Dispatched {{ batch.dispatched_on|date }} · {{ batch.courier }} <span class="code">{{ batch.docket_no }}</span></span>
      <span class="chip{% if sent %} chip-wait{% endif %}"><i class="ti ti-progress-check"></i> Settled <b>{{ settled }}</b> of {{ lines|length }}</span>
      {% if sent %}<span class="chip{% if waiting > 30 %} chip-alert{% endif %}"><i class="ti ti-clock"></i> Waiting <b>{{ waiting }}</b> days</span>{% endif %}
      <a class="chip chip-link" href="{% url 'entry_detail' batch.dispatch_entry.number %}"><i class="ti ti-package-export"></i> {{ batch.dispatch_entry.number }}</a>
    {% endif %}
    {% if batch.note %}<span class="chip"><i class="ti ti-note"></i> {{ batch.note }}</span>{% endif %}
  </div></div>
{% if batch.is_draft %}
  <div class="col-12"><div class="alert alert-info mb-0"><i class="ti ti-pencil"></i> <b>Draft.</b> Add or remove {{ batch.company.name }} pieces, then <b>Dispatch</b>. Dispatching posts a Stock OUT from the Defective store and locks the batch.</div></div>
  <div class="col-lg-7"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-packages"></i> In this batch</h3><span class="badge bg-secondary-lt ms-2">{{ lines|length }}</span></div>
    <div class="table-responsive"><table class="table table-vcenter card-table">
      <thead><tr><th>Tag</th><th>Item</th><th>Batch · PKD</th><th>Fault</th><th></th></tr></thead>
      <tbody>{% for line in lines %}{% with p=line.piece %}<tr>
        <td><a class="code" href="{% url 'piece_detail' p.tag %}">{{ p.tag }}</a></td>
        <td><a class="code" href="{% url 'item_detail' p.item.pk %}">{{ p.item.code }}</a><div class="small text-secondary">{{ p.item.description }}</div></td>
        <td class="nowrap">{{ p.batch_code|default:"—" }}{% if p.pkd %} · {{ p.pkd|pkd_month }}{% endif %}</td><td class="cell-wrap">{{ p.fault }}</td>
        <td><form method="post" action="{% url 'batch_remove' batch.number %}">{% csrf_token %}<input type="hidden" name="tag" value="{{ p.tag }}">
          <button class="btn btn-sm btn-icon btn-quiet" title="Remove {{ p.tag }} from the batch" aria-label="Remove {{ p.tag }}"><i class="ti ti-x"></i></button></form></td></tr>{% endwith %}
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No pieces yet. Add some from the right.</td></tr>{% endfor %}</tbody>
    </table></div></div></div>
  <div class="col-lg-5"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-plus"></i> Add pieces</h3></div>
    <div class="card-body border-bottom"><form method="post" action="{% url 'batch_add' batch.number %}" class="input-group" novalidate>{% csrf_token %}
      <label class="visually-hidden" for="add-tag">Type or scan a tag</label>
      <input id="add-tag" name="tag_text" class="form-control code" placeholder="Type or scan a tag, e.g. DEF-0042" autocomplete="off">
      <button class="btn btn-primary"><i class="ti ti-plus"></i> Add</button></form></div>
    <form method="post" action="{% url 'batch_add' batch.number %}">{% csrf_token %}
      <div class="table-responsive"><table class="table table-vcenter card-table">
        <thead><tr><th class="c-check"><input type="checkbox" class="form-check-input m-0" data-tick-all aria-label="Tick all"></th><th>Tag</th><th>Item</th><th>Source</th></tr></thead>
        <tbody>{% for p in available %}<tr>
          <td class="c-check"><input type="checkbox" class="form-check-input m-0" name="tag" value="{{ p.tag }}" data-tick aria-label="Tick {{ p.tag }}"></td>
          <td><a class="code" href="{% url 'piece_detail' p.tag %}">{{ p.tag }}</a></td><td><span class="code">{{ p.item.code }}</span></td><td>{% include "defectives/_source.html" %}</td></tr>
        {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No other {{ batch.company.name }} pieces in store.</td></tr>{% endfor %}</tbody>
      </table></div>
      <div class="card-footer d-flex align-items-center gap-2"><span class="text-secondary small" data-tick-count></span>
        <button class="btn btn-quiet ms-auto"><i class="ti ti-check"></i> Add ticked</button></div></form></div></div>
{% else %}
  <div class="col-12"><div class="alert alert-secondary mb-0"><i class="ti ti-lock"></i> Dispatched on {{ batch.dispatched_on|date }}, so this batch is locked. Settle each piece when the company answers.</div></div>
  <div class="col-12"><form method="post" action="{% url 'batch_settle' batch.number %}" class="card" novalidate data-once>{% csrf_token %}
    <div class="card-header"><h3 class="card-title"><i class="ti ti-tags"></i> Pieces</h3><span class="badge bg-secondary-lt ms-2">{{ lines|length }}</span>
      <div class="card-subtitle ms-2 text-secondary">{% if sent %}{{ sent|length }} still with {{ batch.company.name }}. Tick the ones they answered for.{% else %}All pieces are settled.{% endif %}</div></div>
    <div class="table-responsive"><table class="table table-vcenter card-table">
      <thead><tr><th class="c-check">{% if sent %}<input type="checkbox" class="form-check-input m-0" data-tick-all aria-label="Tick all sent pieces">{% endif %}</th><th>Tag</th><th>Item</th><th>Batch · PKD</th><th>Fault</th><th>Source</th><th>Outcome</th><th>Entry</th></tr></thead>
      <tbody>{% for line in lines %}{% with p=line.piece %}<tr>
        <td class="c-check">{% if line in sent %}<input type="checkbox" class="form-check-input m-0" name="tag" value="{{ p.tag }}" data-tick aria-label="Tick {{ p.tag }}">{% else %}<span class="text-secondary" title="Already answered"><i class="ti ti-lock"></i></span>{% endif %}</td>
        <td><a class="code" href="{% url 'piece_detail' p.tag %}">{{ p.tag }}</a></td>
        <td><a class="code" href="{% url 'item_detail' p.item.pk %}">{{ p.item.code }}</a><div class="small text-secondary">{{ p.item.description }}</div></td>
        <td class="nowrap">{{ p.batch_code|default:"—" }}{% if p.pkd %} · {{ p.pkd|pkd_month }}{% endif %}</td><td class="cell-wrap">{{ p.fault }}</td><td>{% include "defectives/_source.html" %}</td>
        <td>{% if line.outcome %}{{ line.outcome|outcome_badge }}<div class="small text-secondary mt-1">{{ line.settled_on|date }}{% if line.to_location %} → {{ line.to_location.name }}{% endif %}</div>{% else %}{{ p.status|piece_badge }}{% endif %}</td>
        <td>{% if line.entry %}<a class="code" href="{% url 'entry_detail' line.entry.number %}">{{ line.entry.number }}</a>{% endif %}</td></tr>{% endwith %}{% endfor %}</tbody>
    </table></div>
    {% if sent %}<div class="card-body settle-panel border-top"><h4 class="mb-3"><i class="ti ti-gavel"></i> Settle ticked pieces <span class="text-secondary fw-normal" data-tick-count></span></h4>
      <div class="row g-3 align-items-start">
        <div class="col-12"><label class="form-label required">Answer from the company</label><div class="form-selectgroup">
          {% for value, text, icon in outcome_choices %}<label class="form-selectgroup-item"><input type="radio" name="outcome" value="{{ value }}" class="form-selectgroup-input" data-outcome{% if forloop.first %} checked{% endif %}><span class="form-selectgroup-label"><i class="ti ti-{{ icon }}"></i> {{ text }}</span></label>{% endfor %}</div></div>
        <div class="col-12 col-md-3"><label class="form-label required" for="s-date">Date answered</label><input id="s-date" name="settled_on" type="date" class="form-control" value="{{ today|date:'Y-m-d' }}" min="{{ batch.dispatched_on|date:'Y-m-d' }}" max="{{ today|date:'Y-m-d' }}"></div>
        <div class="col-12 col-md-3" id="w-sloc"><label class="form-label required" for="s-loc">Goes into location</label><select id="s-loc" name="to_location" class="form-select"><option value="">Choose…</option>{% for place in locations %}<option value="{{ place.pk }}">{{ place.name }}</option>{% endfor %}</select></div>
        <div class="col-12 col-md-6"><div class="text-secondary small pt-md-4" id="settle-hint"></div></div>
      </div>
      <div class="d-flex mt-3"><button type="submit" class="btn btn-primary ms-auto"><i class="ti ti-check"></i> Settle ticked pieces</button></div></div>{% endif %}
  </form></div>
{% endif %}
</div>
{% if batch.is_draft %}
<div class="modal modal-blur fade" id="dispatch-modal" tabindex="-1" aria-labelledby="dispatch-title" aria-hidden="true"><div class="modal-dialog modal-lg modal-dialog-centered"><div class="modal-content">
  <form method="post" action="{% url 'batch_dispatch' batch.number %}" novalidate data-once>{% csrf_token %}
    <div class="modal-header"><h5 class="modal-title" id="dispatch-title"><i class="ti ti-truck"></i> Dispatch {{ batch.number }} to {{ batch.company.name }}</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
    <div class="modal-body"><p class="text-secondary">{{ lines|length }} piece(s). This posts a Stock OUT from the Defective store and locks the batch.</p>
      <div class="row g-3">
        <div class="col-12 col-md-4"><label class="form-label required" for="d-date">Dispatch date</label><input id="d-date" name="dispatched_on" type="date" class="form-control" value="{{ today|date:'Y-m-d' }}" min="{{ batch.created_on|date:'Y-m-d' }}" max="{{ today|date:'Y-m-d' }}"></div>
        <div class="col-12 col-md-4"><label class="form-label required" for="d-courier">Courier</label><input id="d-courier" name="courier" class="form-control" list="couriers" maxlength="60" placeholder="e.g. DTDC" autocomplete="off"><datalist id="couriers">{% for c in couriers %}<option value="{{ c }}">{% endfor %}</datalist></div>
        <div class="col-12 col-md-4"><label class="form-label required" for="d-docket">Docket / LR no.</label><input id="d-docket" name="docket_no" class="form-control code" maxlength="40" placeholder="e.g. D51243817"></div>
      </div></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button><button type="submit" class="btn btn-out ms-auto"><i class="ti ti-truck"></i> Dispatch</button></div>
  </form></div></div></div>
{% endif %}
{% endblock %}
{% block scripts %}<script src="{% static 'js/service.js' %}"></script>{% endblock %}
```

`templates/defectives/piece_detail.html`:
```html
{% extends "base.html" %}{% load static defective_tags %}
{% block title %}{{ piece.tag }}{% endblock %}
{% block pretitle %}Defective piece · {{ piece.company.name }}{% endblock %}
{% block page_title %}<span class="code">{{ piece.tag }}</span> {{ piece.status|piece_badge }} {{ piece.outcome|outcome_badge }}{% endblock %}
{% block actions %}
  {% if piece.status == "IN_STORE" %}<div class="dropdown"><button type="button" class="btn btn-primary dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false"><i class="ti ti-packages"></i> Add to a return batch</button>
    <div class="dropdown-menu dropdown-menu-end">
      {% for b in drafts %}<form method="post" action="{% url 'batch_add' b.number %}">{% csrf_token %}<input type="hidden" name="tag" value="{{ piece.tag }}"><button class="dropdown-item" type="submit">Draft <span class="code ms-1">{{ b.number }}</span><span class="text-secondary ms-2 small">created {{ b.created_on|date }}</span></button></form>{% endfor %}
      <a class="dropdown-item" href="{% url 'batch_new' %}?company={{ piece.company_id }}&amp;tag={{ piece.tag }}"><i class="ti ti-plus"></i> New batch for {{ piece.company.name }}</a>
    </div></div>{% endif %}
  {% if piece.return_batch %}<a href="{% url 'batch_detail' piece.return_batch.number %}" class="btn btn-quiet"><i class="ti ti-truck-return"></i> Batch {{ piece.return_batch.number }}</a>{% endif %}
{% endblock %}
{% block content %}
<div class="row row-cards">
  <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Details</h3></div><div class="card-body"><div class="datagrid">
    <div class="datagrid-item"><div class="datagrid-title">Item</div><div class="datagrid-content"><a class="code" href="{% url 'item_detail' piece.item.pk %}">{{ piece.item.code }}</a><div class="small text-secondary">{{ piece.item.spare_type.name }} · {{ piece.item.description }}</div></div></div>
    <div class="datagrid-item"><div class="datagrid-title">Company</div><div class="datagrid-content">{{ piece.company.name }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Source</div><div class="datagrid-content">{% include "defectives/_source.html" with p=piece %}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Collected on</div><div class="datagrid-content">{{ piece.collected_on|date }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Batch code</div><div class="datagrid-content">{% if piece.batch_code %}<span class="code">{{ piece.batch_code }}</span>{% else %}—{% endif %}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">PKD (packed)</div><div class="datagrid-content">{{ piece.pkd|pkd_month|default:"—" }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Fault</div><div class="datagrid-content">{{ piece.fault|default:"—" }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Outcome</div><div class="datagrid-content">{% if piece.outcome %}{{ piece.outcome|outcome_badge }} <span class="text-secondary small">on {{ piece.settled_on|date }}</span>{% else %}—{% endif %}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Ledger entries</div><div class="datagrid-content">{% for e in entries %}<a class="code" href="{% url 'entry_detail' e.number %}">{{ e.number }}</a>{% if not forloop.last %} · {% endif %}{% empty %}—{% endfor %}</div></div>
  </div></div></div>
  {% if lines %}<div class="card mt-3"><div class="card-header"><h3 class="card-title"><i class="ti ti-truck-return"></i> Return batches</h3></div>
    <div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Batch</th><th>Dispatched</th><th>Answer</th><th>Entry</th></tr></thead>
      <tbody>{% for line in lines %}<tr><td><a class="code" href="{% url 'batch_detail' line.batch.number %}">{{ line.batch.number }}</a></td><td>{{ line.batch.dispatched_on|date|default:"Not yet" }}</td>
        <td>{% if line.outcome %}{{ line.outcome|outcome_badge }} <span class="small text-secondary">{{ line.settled_on|date }}{% if line.to_location %} → {{ line.to_location.name }}{% endif %}</span>{% else %}<span class="text-secondary">Waiting</span>{% endif %}</td>
        <td>{% if line.entry %}<a class="code" href="{% url 'entry_detail' line.entry.number %}">{{ line.entry.number }}</a>{% endif %}</td></tr>{% endfor %}</tbody></table></div></div>{% endif %}
  </div>
  <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-timeline"></i> History</h3></div>
    <div class="card-body"><ul class="tl">{% for ev in events %}<li class="tl-item"><span class="tl-dot {{ ev.to_status|piece_css }}"><i class="ti ti-{{ ev.to_status|piece_icon }}"></i></span>
      <div class="tl-body"><div class="fw-medium">{% if ev.from_status %}{{ ev.get_from_status_display }} → {% endif %}{{ ev.get_to_status_display }}</div>
        <div class="small text-secondary">{{ ev.at|date }} · {{ ev.by.first_name|default:ev.by.username }}</div>{% if ev.note %}<div class="small">{{ ev.note }}</div>{% endif %}</div></li>{% endfor %}</ul></div></div></div>
</div>
{% endblock %}
```

`static/js/service.js`:
```js
/* Small behaviours shared by the complaints and defectives pages:
   - <select data-ts> becomes a Tom Select (multi-selects get remove buttons);
   - in a form, a [data-tick-all] box ticks every [data-tick] box, [data-tick-count] shows how many are ticked,
     and a [data-bulk] bar is shown only while something is ticked;
   - [data-outcome] radios show the location field (#w-sloc) only for Replaced / Repaired, with a hint;
   - forms marked [data-once] disable their submit button after the first click. */
(function () {
  document.querySelectorAll("select[data-ts]").forEach(s => new TomSelect(s, {
    maxOptions: 100, allowEmptyOption: true, closeAfterSelect: !s.multiple, plugins: s.multiple ? ["remove_button"] : [],
  }));

  document.querySelectorAll("form").forEach(form => {
    const all = form.querySelector("input[data-tick-all]");
    const counters = form.querySelectorAll("[data-tick-count]");
    const bulk = form.querySelector("[data-bulk]");
    if (!all && !counters.length && !bulk) return;
    const boxes = () => [...form.querySelectorAll("input[data-tick]:not(:disabled)")];
    const update = () => {
      const n = boxes().filter(b => b.checked).length;
      counters.forEach(c => { c.textContent = n ? `${n} ticked` : ""; });
      if (bulk) bulk.hidden = n === 0;
      if (all) all.checked = n > 0 && n === boxes().length;
    };
    if (all) all.addEventListener("change", () => { boxes().forEach(b => { b.checked = all.checked; }); update(); });
    form.addEventListener("change", e => { if (e.target.matches("input[data-tick]")) update(); });
    update();
  });

  const HINTS = {
    REPLACED: "Posts a Stock IN (replacement from the company) into the chosen good-stock location.",
    REPAIRED: "Posts a Stock IN (repaired piece back from the company) into the chosen good-stock location.",
    REJECTED_RETURNED: "The company sent the piece back. It returns to the Defective store; you can batch it again or scrap it.",
    REJECTED_SCRAPPED: "The company kept and scrapped it. Nothing is posted: the piece already left with the dispatch.",
  };
  const outcomes = [...document.querySelectorAll("input[data-outcome]")];
  const showOutcome = () => {
    const picked = outcomes.find(r => r.checked);
    const good = picked && (picked.value === "REPLACED" || picked.value === "REPAIRED");
    const wrap = document.getElementById("w-sloc"), hint = document.getElementById("settle-hint");
    if (wrap) wrap.hidden = !good;
    if (hint) hint.textContent = picked ? HINTS[picked.value] : "";
  };
  outcomes.forEach(r => r.addEventListener("change", showOutcome));
  if (outcomes.length) showOutcome();

  document.querySelectorAll("form[data-once]").forEach(form => form.addEventListener("submit", () => {
    const b = form.querySelector("button[type=submit]");
    if (b) { b.disabled = true; b.classList.add("btn-loading"); }
  }));
  window.addEventListener("pageshow", e => {
    if (!e.persisted) return;
    document.querySelectorAll("form[data-once] button[type=submit]").forEach(b => { b.disabled = false; b.classList.remove("btn-loading"); });
  });
})();
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Check it in a browser**

On the dev server: create a batch from `/defectives/batches/new/`, add a piece by typing `def-1`, dispatch it from the modal (courier suggestions appear), tick one piece and settle it as Replaced into Vizag Office (the location box shows only for Replaced / Repaired), and open a piece card. Expected: no console errors; the batch list shows "Partly settled".

- [ ] **Step 8: Commit**

```bash
git add apps/core/templatetags/core_tags.py apps/defectives apps/inventory/context_processors.py templates/defectives static/js/service.js tests/defectives/test_batch_views.py
git commit -m "feat(defectives): return batch screens (new, add/remove, dispatch, settle) and the piece card"
```

---

### Task 8: Pieces list with filters and bulk actions (add to batch, scrap)

**Files:**
- Modify: `apps/defectives/filters.py` (`PieceFilters`, `piece_filters`), `apps/defectives/selectors.py` (`piece_search_q`, `piece_rows`, `piece_items`)
- Modify: `apps/defectives/views.py` (`defective_pieces`, `pieces_bulk`, `_add_to_batch`; `piece_detail` passes scrap reasons), `apps/defectives/urls.py`
- Modify: `apps/inventory/context_processors.py` (menu entry)
- Create: `templates/defectives/pieces.html`, `templates/defectives/_scrap_modal.html`; Modify: `templates/defectives/piece_detail.html` (Scrap button)
- Test: `tests/defectives/test_pieces_views.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/defectives/test_pieces_views.py`:
```python
import re

import pytest

from apps.defectives.models import DefectivePiece, PieceStatus, ReturnBatch
from apps.defectives.services import create_batch
from apps.inventory.models import Company
from tests.factories import make_item, make_pieces

pytestmark = pytest.mark.django_db
LIST, BULK = "/defectives/pieces/", "/defectives/pieces/bulk/"


@pytest.fixture
def mixed(office_user):
    """DEF-0001, DEF-0002 (Wipro driver, 'no output') and DEF-0003 (Havells MCB, 'trips')."""
    make_pieces(make_item("LG78-150-700"), 2, office_user, fault="no output")
    make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user, fault="trips")


def tags(client, query=""):
    html = client.get(LIST + query).content.decode()
    return re.findall(r'href="/defectives/pieces/(DEF-\d{4})/"', html)


def test_list_newest_first_and_filters(office_client, mixed):
    assert tags(office_client) == ["DEF-0003", "DEF-0002", "DEF-0001"]
    havells = Company.objects.get(name="Havells")
    assert tags(office_client, f"?company={havells.pk}") == ["DEF-0003"]
    assert tags(office_client, "?q=def-1") == ["DEF-0001"]
    assert tags(office_client, "?q=trips") == ["DEF-0003"]
    assert tags(office_client, "?q=MCB") == ["DEF-0003"]
    assert tags(office_client, "?status=SENT") == []
    assert tags(office_client, "?source=SITE_VISIT") == []
    assert tags(office_client, "?status=IN_STORE&sort=tag&dir=asc") == ["DEF-0001", "DEF-0002", "DEF-0003"]


def test_only_pieces_in_store_can_be_ticked(office_client, office_user, mixed):
    create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user,
                 pieces=list(DefectivePiece.objects.filter(tag="DEF-0001")))
    html = office_client.get(LIST).content.decode()
    assert 'value="DEF-0002" data-tick' in html and 'value="DEF-0001" data-tick' not in html


def test_bulk_add_to_a_new_batch(office_client, mixed):
    r = office_client.post(BULK, {"action": "batch", "batch": "new", "tag": ["DEF-0001", "DEF-0002"]})
    assert r.status_code == 302 and r.url == "/defectives/batches/RB-0001/"
    assert ReturnBatch.objects.get().company.name == "Wipro Lighting"


def test_bulk_add_refuses_mixed_companies(office_client, mixed):
    data = {"action": "batch", "batch": "new", "tag": ["DEF-0001", "DEF-0003"], "next": LIST}
    html = office_client.post(BULK, data, follow=True).content.decode()
    assert "belong to 2 companies (Havells, Wipro Lighting)" in html and not ReturnBatch.objects.exists()


def test_bulk_add_to_an_existing_draft(office_client, office_user, mixed):
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user)
    office_client.post(BULK, {"action": "batch", "batch": b.number, "tag": ["DEF-0002"]})
    assert list(b.lines.values_list("piece__tag", flat=True)) == ["DEF-0002"]


def test_bulk_scrap(office_client, mixed):
    r = office_client.post(BULK, {"action": "scrap", "reason": "BURNT", "tag": ["DEF-0001"], "next": LIST + "?status=IN_STORE"})
    assert r.url == LIST + "?status=IN_STORE"
    assert DefectivePiece.objects.get(tag="DEF-0001").status == PieceStatus.SCRAPPED
    html = office_client.post(BULK, {"action": "scrap", "reason": "OTHER", "tag": ["DEF-0002"]}, follow=True).content.decode()
    assert "Write a note when the reason is Other." in html


def test_unsafe_next_is_ignored(office_client, mixed):
    r = office_client.post(BULK, {"action": "scrap", "reason": "BURNT", "tag": ["DEF-0001"], "next": "https://evil.example/"})
    assert r.url == LIST


def test_nothing_ticked(office_client, mixed):
    html = office_client.post(BULK, {"action": "scrap", "reason": "BURNT"}, follow=True).content.decode()
    assert "Tick at least one piece." in html


def test_piece_card_offers_scrap_for_a_piece_in_store(office_client, mixed):
    html = office_client.get(LIST + "DEF-0001/").content.decode()
    assert "Scrap…" in html and f'action="{BULK}"' in html


def test_nav_links_pieces(office_client):
    assert f'href="{LIST}"' in office_client.get("/").content.decode()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/defectives/test_pieces_views.py -q`
Expected: FAIL (`/defectives/pieces/` resolves to `piece_detail` with tag "" → 404).

- [ ] **Step 3: Filters and selectors**

Append to `apps/defectives/filters.py` (imports become `from datetime import date`, `from apps.inventory.filters import _date, _obj, _text`, `from apps.inventory.models import Company, Item`, `from .models import BATCH_LABELS, Outcome, PieceStatus, Source`):
```python
@dataclass
class PieceFilters:
    company: Company | None
    item: Item | None
    status: str
    source: str
    outcome: str
    date_from: date | None  # collected on or after
    date_to: date | None
    q: str


def piece_filters(params):
    status, source, outcome = params.get("status", ""), params.get("source", ""), params.get("outcome", "")
    date_from, date_to = _date(params.get("date_from"), None), _date(params.get("date_to"), None)
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return PieceFilters(
        _obj(Company, params.get("company")),
        _obj(Item, params.get("item")),
        status if status in PieceStatus.values else "",
        source if source in Source.values else "",
        outcome if outcome in Outcome.values else "",
        date_from,
        date_to,
        _text(params.get("q")),
    )
```

Append to `apps/defectives/selectors.py` (imports gain `from apps.inventory.models import Item`, `from apps.inventory.normalise import normalise_code`, `from .services import normalise_tag`):
```python
def piece_search_q(text):
    """The pieces search box: a tag typed loosely (def-42), batch code, fault, return batch no. or item code.
    Task 10 adds the complaint number."""
    return (
        Q(tag__icontains=normalise_tag(text))
        | Q(batch_code__icontains=text)
        | Q(fault__icontains=text)
        | Q(return_batch__number__icontains=text)
        | Q(item__code__icontains=normalise_code(text))
    )


def piece_rows(f):
    pieces = pieces_qs()
    for field, value in (
        ("company", f.company),
        ("item", f.item),
        ("status", f.status),
        ("source", f.source),
        ("outcome", f.outcome),
    ):
        if value:
            pieces = pieces.filter(**{field: value})
    if f.date_from:
        pieces = pieces.filter(collected_on__gte=f.date_from)
    if f.date_to:
        pieces = pieces.filter(collected_on__lte=f.date_to)
    if f.q:
        pieces = pieces.filter(piece_search_q(f.q))
    return list(pieces)


def piece_items():
    """Items that have ever had a defective piece (the item filter on the pieces list)."""
    return Item.objects.filter(defective_pieces__isnull=False).distinct().order_by("code")
```

- [ ] **Step 4: Views and URLs**

In `apps/defectives/views.py`: import `piece_filters` from `.filters`, `ScrapReason` and `Source` from `.models`; in `piece_detail` add `"scrap_reasons": ScrapReason.choices,` to the context; append:
```python
@role_required(OFFICE)
def defective_pieces(request):
    f = piece_filters(request.GET)
    rows = selectors.piece_rows(f)
    order = list(PieceStatus.values)
    sorters = {
        "tag": lambda p: p.tag,
        "code": lambda p: p.item.code,
        "company": lambda p: p.company.name,
        "source": lambda p: p.source,
        "collected": lambda p: (p.collected_on, p.tag),
        "bpkd": lambda p: p.batch_code,
        "status": lambda p: order.index(p.status),
        "rb": lambda p: p.return_batch.number if p.return_batch_id else "",
    }
    table = sort_and_page(request, rows, sorters, "tag", "desc")
    return render(
        request,
        "defectives/pieces.html",
        {
            "f": f,
            "table": table,
            "companies": Company.objects.filter(is_active=True),
            "items": selectors.piece_items(),
            "statuses": PieceStatus.choices,
            "sources": Source.choices,
            "outcome_label": Outcome(f.outcome).label if f.outcome else "",
            "drafts": ReturnBatch.objects.filter(status=BatchStatus.DRAFT).select_related("company"),
            "scrap_reasons": ScrapReason.choices,
        },
    )


def _add_to_batch(request, chosen):
    names = sorted({p.company.name for p in chosen})
    if len(names) > 1:
        raise DefectiveError(
            f"The ticked pieces belong to {len(names)} companies ({', '.join(names)}). A return batch holds "
            "one company's pieces only. Filter the list by company, or untick the others."
        )
    target = request.POST.get("batch", "new")
    if target == "new":
        return services.create_batch(company=chosen[0].company, user=request.user, pieces=chosen)
    batch = ReturnBatch.objects.filter(number=target).first()
    if batch is None:
        raise DefectiveError("Choose a draft batch.")
    return services.add_pieces(batch=batch, pieces=chosen, user=request.user)


@role_required(OFFICE)
@require_POST
def pieces_bulk(request):
    """Bulk actions from the pieces list (and Scrap from a piece card): add ticked pieces to a batch, or scrap."""
    back = _back(request, reverse("defective_pieces"))
    chosen = list(DefectivePiece.objects.filter(tag__in=request.POST.getlist("tag")).select_related("company"))
    action = request.POST.get("action", "")
    try:
        if not chosen:
            raise DefectiveError("Tick at least one piece.")
        if action == "batch":
            batch = _add_to_batch(request, chosen)
            messages.success(request, f"{len(chosen)} piece(s) added to {batch.number}.")
            return redirect("batch_detail", number=batch.number)
        if action == "scrap":
            services.scrap(
                pieces=chosen,
                reason=request.POST.get("reason", ""),
                note=request.POST.get("note", ""),
                user=request.user,
            )
            messages.success(request, f"{len(chosen)} piece(s) scrapped: {', '.join(sorted(p.tag for p in chosen))}.")
            return redirect(back)
        raise DefectiveError("Choose what to do with the ticked pieces.")
    except (DefectiveError, StockError) as exc:
        messages.error(request, exc.message)
        return redirect(back)
```

`apps/defectives/urls.py`: add, **before** the `defectives/pieces/<str:tag>/` line,
```python
    path("defectives/pieces/", views.defective_pieces, name="defective_pieces"),
    path("defectives/pieces/bulk/", views.pieces_bulk, name="pieces_bulk"),
```

`apps/inventory/context_processors.py`, Defectives section:
```python
    (
        "Defectives",
        [
            ("defective_pieces", "Pieces", "tags", "", False),
            ("mark_defective", "Mark defective", "alert-octagon", "", False),
            ("return_batches", "Return batches", "truck-return", "", False),
        ],
    ),
```

- [ ] **Step 5: Templates**

`templates/defectives/_scrap_modal.html`:
```html
{# Scrap dialog. In the pieces list it sits inside the bulk form; on a piece card (standalone) it has its own form. #}
<div class="modal modal-blur fade" id="scrap-modal" tabindex="-1" aria-labelledby="scrap-title" aria-hidden="true"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
  {% if standalone %}<form method="post" action="{% url 'pieces_bulk' %}">{% csrf_token %}<input type="hidden" name="tag" value="{{ tag }}"><input type="hidden" name="next" value="{{ request.get_full_path }}">{% endif %}
  <div class="modal-header"><h5 class="modal-title" id="scrap-title"><i class="ti ti-trash"></i> Scrap {% if standalone %}{{ tag }}{% else %}the ticked pieces{% endif %}</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
  <div class="modal-body"><p class="text-secondary">Use this when a piece is not worth sending back. It leaves the Defective store with an adjustment (Damaged) and can't be batched again.</p>
    <label class="form-label required" for="sc-reason">Reason</label><select id="sc-reason" name="reason" class="form-select"><option value="">Choose…</option>{% for value, label in scrap_reasons %}<option value="{{ value }}">{{ label }}</option>{% endfor %}</select>
    <label class="form-label mt-3" for="sc-note">Note</label><textarea id="sc-note" name="note" class="form-control" rows="2" maxlength="200" placeholder="Required when the reason is Other"></textarea></div>
  <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button><button type="submit" name="action" value="scrap" class="btn btn-danger ms-auto"><i class="ti ti-trash"></i> Scrap</button></div>
  {% if standalone %}</form>{% endif %}
</div></div></div>
```

`templates/defectives/pieces.html`:
```html
{% extends "base.html" %}{% load static core_tags defective_tags %}
{% block title %}Defective pieces{% endblock %}
{% block pretitle %}Defectives{% endblock %}
{% block page_title %}Defective pieces{% endblock %}
{% block actions %}<a href="{% url 'mark_defective' %}" class="btn btn-quiet"><i class="ti ti-alert-octagon"></i> Mark defective</a>{% endblock %}
{% block content %}
<div class="card">
  <div class="card-body border-bottom py-3"><form method="get" class="row g-2 align-items-end">
    {% if f.outcome %}<input type="hidden" name="outcome" value="{{ f.outcome }}">{% endif %}
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="pf-co">Company</label>
      <select id="pf-co" name="company" class="form-select" onchange="this.form.submit()"><option value="">All companies</option>
        {% for c in companies %}<option value="{{ c.pk }}" {% if f.company == c %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-3"><label class="form-label small text-secondary mb-1" for="pf-item">Item</label>
      <select id="pf-item" name="item" data-ts onchange="this.form.submit()"><option value="">All items</option>
        {% for i in items %}<option value="{{ i.pk }}" {% if f.item == i %}selected{% endif %}>{{ i.code }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="pf-st">Status</label>
      <select id="pf-st" name="status" class="form-select" onchange="this.form.submit()"><option value="">Any status</option>
        {% for v, label in statuses %}<option value="{{ v }}" {% if f.status == v %}selected{% endif %}>{{ label }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="pf-src">Source</label>
      <select id="pf-src" name="source" class="form-select" onchange="this.form.submit()"><option value="">Any source</option>
        {% for v, label in sources %}<option value="{{ v }}" {% if f.source == v %}selected{% endif %}>{{ label }}</option>{% endfor %}</select></div>
    <div class="col-12 col-lg-3"><label class="form-label small text-secondary mb-1" for="pf-q">Search</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>
      <input id="pf-q" type="search" name="q" value="{{ f.q }}" class="form-control" placeholder="Tag, batch code, CMP / RB no., fault"></div></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="pf-from">Collected from</label><input id="pf-from" type="date" name="date_from" value="{{ f.date_from|date:'Y-m-d' }}" class="form-control" onchange="this.form.submit()"></div>
    <div class="col-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="pf-to">Collected to</label><input id="pf-to" type="date" name="date_to" value="{{ f.date_to|date:'Y-m-d' }}" class="form-control" onchange="this.form.submit()"></div>
    {% if f.outcome %}<div class="col-auto pb-2">Outcome: {{ f.outcome|outcome_badge }}</div>{% endif %}
    <div class="col-auto ms-auto pb-1"><a href="{% url 'defective_pieces' %}" class="btn btn-link link-secondary px-0"><i class="ti ti-filter-off"></i> Clear filters</a></div>
  </form></div>
  <form method="post" action="{% url 'pieces_bulk' %}">{% csrf_token %}<input type="hidden" name="next" value="{{ request.get_full_path }}">
    <div class="bulk-bar px-3 py-2 d-flex flex-wrap align-items-center gap-2" data-bulk hidden><b data-tick-count></b>
      <div class="ms-auto btn-list"><button type="button" class="btn btn-sm btn-primary" data-bs-toggle="modal" data-bs-target="#batch-modal"><i class="ti ti-packages"></i> Add to draft batch…</button>
        <button type="button" class="btn btn-sm btn-quiet" data-bs-toggle="modal" data-bs-target="#scrap-modal"><i class="ti ti-trash"></i> Scrap…</button></div></div>
    <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
      <thead><tr><th class="c-check"><input type="checkbox" class="form-check-input m-0" data-tick-all aria-label="Tick all pieces in store on this page"></th>
        {% sort_th "tag" "Tag" %}{% sort_th "code" "Item" %}{% sort_th "company" "Company" %}{% sort_th "source" "Source" %}{% sort_th "collected" "Collected" %}{% sort_th "bpkd" "Batch · PKD" %}{% sort_th "status" "Status" %}{% sort_th "rb" "Return batch" %}</tr></thead>
      <tbody>{% for p in table.page %}<tr>
        <td class="c-check">{% if p.status == "IN_STORE" %}<input type="checkbox" class="form-check-input m-0" name="tag" value="{{ p.tag }}" data-tick aria-label="Tick {{ p.tag }}">{% else %}<span class="text-secondary" title="Only pieces in store can be batched or scrapped"><i class="ti ti-lock"></i></span>{% endif %}</td>
        <td><a class="code" href="{% url 'piece_detail' p.tag %}">{{ p.tag }}</a></td>
        <td><a class="code" href="{% url 'item_detail' p.item.pk %}">{{ p.item.code }}</a><div class="small text-secondary">{{ p.item.description }}</div></td>
        <td>{{ p.company.name }}</td><td>{% include "defectives/_source.html" %}</td><td class="nowrap">{{ p.collected_on|date }}</td>
        <td class="nowrap">{{ p.batch_code|default:"—" }}{% if p.pkd %} · {{ p.pkd|pkd_month }}{% endif %}</td>
        <td>{{ p.status|piece_badge }}{% if p.outcome %}<div class="mt-1">{{ p.outcome|outcome_badge }}</div>{% endif %}</td>
        <td>{% if p.return_batch %}<a class="code" href="{% url 'batch_detail' p.return_batch.number %}">{{ p.return_batch.number }}</a>{% else %}<span class="text-secondary">—</span>{% endif %}</td></tr>
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No pieces match these filters.</td></tr>{% endfor %}</tbody>
    </table></div>
    <div class="modal modal-blur fade" id="batch-modal" tabindex="-1" aria-labelledby="batch-title" aria-hidden="true"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title" id="batch-title"><i class="ti ti-packages"></i> Add the ticked pieces to a draft batch</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
      <div class="modal-body"><p class="text-secondary">A batch holds one company's pieces. Pick a draft batch of the same company, or start a new one.</p>
        <div class="form-selectgroup form-selectgroup-boxes d-flex flex-column gap-2">
          {% for b in drafts %}<label class="form-selectgroup-item flex-fill"><input type="radio" name="batch" value="{{ b.number }}" class="form-selectgroup-input"><div class="form-selectgroup-label d-flex align-items-center p-2 text-start"><span class="form-selectgroup-check me-2"></span><span><span class="code">{{ b.number }}</span><span class="text-secondary ms-2">{{ b.company.name }} · created {{ b.created_on|date }}</span></span></div></label>{% endfor %}
          <label class="form-selectgroup-item flex-fill"><input type="radio" name="batch" value="new" class="form-selectgroup-input" checked><div class="form-selectgroup-label d-flex align-items-center p-2 text-start"><span class="form-selectgroup-check me-2"></span><span><i class="ti ti-plus"></i> New batch for the company of the ticked pieces</span></div></label>
        </div></div>
      <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button><button type="submit" name="action" value="batch" class="btn btn-primary ms-auto"><i class="ti ti-check"></i> Add to batch</button></div>
    </div></div></div>
    {% include "defectives/_scrap_modal.html" with standalone=False %}
  </form>
  {% include "core/_pagination.html" %}
</div>
<p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> Tick pieces that are in store to add them to a draft return batch or scrap them. Pieces in a batch, sent or settled are locked.</p>
{% endblock %}
{% block scripts %}<script src="{% static 'js/service.js' %}"></script>{% endblock %}
```
(The pagination include stays outside the bulk `<form>`: it contains its own GET form, and forms can't nest.)

`templates/defectives/piece_detail.html`: in `{% block actions %}`, directly after the `{% endif %}` that closes the "Add to a return batch" dropdown, add
```html
  {% if piece.status == "IN_STORE" %}<button type="button" class="btn btn-quiet" data-bs-toggle="modal" data-bs-target="#scrap-modal"><i class="ti ti-trash"></i> Scrap…</button>{% endif %}
```
and directly before `{% endblock %}` of the content block, add
```html
{% if piece.status == "IN_STORE" %}{% include "defectives/_scrap_modal.html" with standalone=True tag=piece.tag %}{% endif %}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Check it in a browser**

Open `/defectives/pieces/`, tick two pieces of one company (the blue bulk bar appears with "2 ticked"), add them to a new batch; tick pieces of two companies and try again (red message, nothing saved); scrap one piece with reason "Other" and no note (refused), then with a note. Expected: no console errors.

- [ ] **Step 8: Commit**

```bash
git add apps/defectives apps/inventory/context_processors.py templates/defectives tests/defectives/test_pieces_views.py
git commit -m "feat(defectives): pieces list with filters, bulk add-to-batch and scrap"
```

---

### Task 9: Defectives dashboard and the two Excel downloads

**Files:**
- Modify: `apps/defectives/selectors.py` (`dashboard`, `defective_list_rows`)
- Create: `apps/defectives/exports.py`; Modify: `apps/defectives/views.py` (`defectives_dashboard`), `apps/defectives/urls.py`
- Modify: `apps/inventory/context_processors.py` (menu entry)
- Create: `templates/defectives/dashboard.html`; Modify: `templates/defectives/pieces.html`, `templates/defectives/batch_detail.html` (export buttons)
- Test: `tests/defectives/test_dashboard_exports.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/defectives/test_dashboard_exports.py`:
```python
import io

import openpyxl
import pytest
from django.utils import timezone

from apps.defectives import selectors
from apps.defectives.models import Outcome
from apps.defectives.services import create_batch, dispatch, settle
from apps.inventory.models import Company
from tests.factories import loc, make_item, make_pieces

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def sheet(response):
    assert response.status_code == 200
    return openpyxl.load_workbook(io.BytesIO(response.content)).active


def wipro():
    return Company.objects.get(name="Wipro Lighting")


@pytest.fixture
def story(office_user):
    """Wipro DEF-0001..0004, Havells DEF-0005. RB-0001 sent with 0001+0002, 0001 replaced. RB-0002 draft with 0003."""
    w = make_pieces(make_item("LG78-150-700", description="LED driver 150W"), 4, office_user)
    make_pieces(make_item("MCB 16A SP", company="Havells", spare_type="Accessory"), 1, office_user)
    b = create_batch(company=wipro(), user=office_user, pieces=w[:2])
    dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    settle(batch=b, pieces=w[:1], outcome=Outcome.REPLACED, settled_on=TODAY, to_location=loc(), user=office_user)
    create_batch(company=wipro(), user=office_user, pieces=w[2:3])
    return w


def test_dashboard_numbers(office_client, story):
    d = selectors.dashboard(TODAY)
    assert (d["in_store"], d["in_batch"], d["sent"], d["drafts"], d["answered"]) == (2, 1, 1, 1, 1)
    assert [(r["company__name"], r["store"], r["batch"]) for r in d["store_rows"]] == [
        ("Havells", 1, 0),
        ("Wipro Lighting", 1, 1),
    ]
    [row] = d["sent_rows"]
    assert (row["company__name"], row["n"], row["waiting"], row["oldest"].number) == ("Wipro Lighting", 1, 0, "RB-0001")
    assert {value: n for value, _, n in d["outcomes"]}["REPLACED"] == 1
    assert [r["piece"].tag for r in d["oldest"]] == ["DEF-0004", "DEF-0005"]
    html = office_client.get("/defectives/").content.decode()
    assert "Pieces in store" in html and "Sent, awaiting settlement" in html and "Outcomes, last 90 days" in html


def test_defective_list_export_groups_by_company(office_client, story):
    ws = sheet(office_client.get("/defectives/export/"))
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=7)]
    assert [(r[0], r[1], r[5], r[6], r[7]) for r in rows] == [
        ("Havells", "MCB 16A SP", 1, 0, "DEF-0005"),
        ("Wipro Lighting", "LG78-150-700", 2, 1, "DEF-0003, DEF-0004"),
    ]


def test_dispatch_list_export(office_client, story):
    ws = sheet(office_client.get("/defectives/batches/RB-0001/export/"))
    assert "Return Batch RB-0001 · Wipro Lighting" in ws["A2"].value and "DTDC D1" in ws["A3"].value
    assert [ws.cell(r, 1).value for r in (7, 8)] == ["DEF-0001", "DEF-0002"]
    assert ws.cell(7, 7).value == "Found in stock" and ws.cell(7, 10).value == "Replaced"


def test_export_buttons(office_client, story):
    assert 'href="/defectives/export/' in office_client.get("/defectives/pieces/").content.decode()
    assert 'href="/defectives/batches/RB-0001/export/"' in office_client.get("/defectives/batches/RB-0001/").content.decode()


def test_nav_links_the_dashboard(office_client):
    assert 'href="/defectives/"' in office_client.get("/").content.decode()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/defectives/test_dashboard_exports.py -q`
Expected: FAIL (`module 'apps.defectives.selectors' has no attribute 'dashboard'`).

- [ ] **Step 3: Selectors**

Append to `apps/defectives/selectors.py` (imports gain `from collections import defaultdict`, `from datetime import date, timedelta` and `BatchLine, BatchStatus, Outcome, PieceStatus` from `.models`):
```python
def dashboard(today):
    """Figures for the defectives dashboard."""
    counts = dict(DefectivePiece.objects.values_list("status").annotate(n=Count("id")))
    in_store, in_batch = Q(status=PieceStatus.IN_STORE), Q(status=PieceStatus.IN_BATCH)
    store_rows = list(
        DefectivePiece.objects.filter(in_store | in_batch)
        .values("company_id", "company__name")
        .annotate(store=Count("id", filter=in_store), batch=Count("id", filter=in_batch))
        .order_by("-store", "company__name")
    )
    sent_rows = []
    sent = DefectivePiece.objects.filter(status=PieceStatus.SENT)
    for row in sent.values("company_id", "company__name").annotate(n=Count("id")).order_by("company__name"):
        batches = list(
            ReturnBatch.objects.filter(company_id=row["company_id"], pieces__status=PieceStatus.SENT)
            .distinct()
            .order_by("dispatched_on", "id")
        )
        sent_rows.append(
            {**row, "batches": batches, "oldest": batches[0], "waiting": (today - batches[0].dispatched_on).days}
        )
    sent_rows.sort(key=lambda r: -r["waiting"])
    answered = BatchLine.objects.exclude(outcome="").filter(settled_on__gte=today - timedelta(days=90))
    by_outcome = dict(answered.values_list("outcome").annotate(n=Count("id")))
    total = sum(by_outcome.values())
    oldest = pieces_qs().filter(status=PieceStatus.IN_STORE).order_by("collected_on", "tag")[:6]
    return {
        "in_store": counts.get(PieceStatus.IN_STORE, 0),
        "in_batch": counts.get(PieceStatus.IN_BATCH, 0),
        "sent": counts.get(PieceStatus.SENT, 0),
        "drafts": ReturnBatch.objects.filter(status=BatchStatus.DRAFT).count(),
        "answered": total,
        "store_rows": store_rows,
        "sent_rows": sent_rows,
        "outcomes": [(value, label, by_outcome.get(value, 0)) for value, label in Outcome.choices],
        "outcome_max": max(total, 1),
        "oldest": [{"piece": p, "days": (today - p.collected_on).days} for p in oldest],
    }


def defective_list_rows():
    """Pieces physically in the Defective store (in store + in draft batches), grouped by company, item, batch code
    and PKD: [company, item code, description, batch code, PKD, qty, of which in a draft batch, tags]."""
    groups = defaultdict(list)
    for p in pieces_qs().filter(status__in=[PieceStatus.IN_STORE, PieceStatus.IN_BATCH]).order_by("tag"):
        groups[(p.company.name, p.item.code, p.batch_code, p.pkd)].append(p)
    ordered = sorted(groups.items(), key=lambda kv: (*kv[0][:3], kv[0][3] or date.min))
    return [
        [
            company,
            code,
            ps[0].item.description,
            batch,
            f"{pkd:%m-%Y}" if pkd else "",
            len(ps),
            sum(p.status == PieceStatus.IN_BATCH for p in ps),
            ", ".join(p.tag for p in ps),
        ]
        for (company, code, batch, pkd), ps in ordered
    ]
```

- [ ] **Step 4: Exports, view, URLs, menu**

`apps/defectives/exports.py`:
```python
"""Excel downloads for the defectives module, in the same layout as the stock exports."""

from django.shortcuts import get_object_or_404

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.excel import Column, workbook_response

from . import selectors
from .models import ReturnBatch


def _who(request):
    return request.user.first_name or request.user.username


@role_required(OFFICE)
def defective_list_xlsx(request):
    cols = [
        Column("Company"),
        Column("Item code", "code"),
        Column("Description", width=28),
        Column("Batch code", "code"),
        Column("PKD"),
        Column("Qty in store", "int"),
        Column("Of which in a draft batch", "int"),
        Column("Tags", "code", width=40),
    ]
    return workbook_response(
        "Defective_List",
        "Defective List",
        "Pieces in the Defective store (in store + in draft batches) · grouped by company",
        _who(request),
        cols,
        selectors.defective_list_rows(),
    )


@role_required(OFFICE)
def batch_xlsx(request, number):
    """The dispatch list that goes with the shipment: one row per piece."""
    batch = get_object_or_404(ReturnBatch.objects.select_related("company"), number=number)
    lines = selectors.batch_lines(batch)
    if batch.is_draft:
        status = "Draft (not dispatched yet)"
    else:
        status = f"Dispatched {batch.dispatched_on:%d-%m-%Y} · {batch.courier} {batch.docket_no}"
    cols = [
        Column("Tag", "code"),
        Column("Item code", "code"),
        Column("Description", width=28),
        Column("Batch code", "code"),
        Column("PKD"),
        Column("Fault", width=30),
        Column("Complaint", "code"),
        Column("Company complaint no.", "code"),
        Column("Collected on", "date"),
        Column("Outcome"),
    ]
    data = [
        [
            ln.piece.tag,
            ln.piece.item.code,
            ln.piece.item.description,
            ln.piece.batch_code,
            f"{ln.piece.pkd:%m-%Y}" if ln.piece.pkd else "",
            ln.piece.fault,
            *selectors.complaint_cells(ln.piece),
            ln.piece.collected_on,
            ln.get_outcome_display(),
        ]
        for ln in lines
    ]
    note = f" · {batch.note}" if batch.note else ""
    return workbook_response(
        f"Return_Batch_{batch.number}",
        f"Return Batch {batch.number} · {batch.company.name}",
        f"{status} · {len(lines)} pieces{note}",
        _who(request),
        cols,
        data,
    )
```

`apps/defectives/views.py`, append:
```python
@role_required(OFFICE)
def defectives_dashboard(request):
    return render(request, "defectives/dashboard.html", {"d": selectors.dashboard(timezone.localdate())})
```

`apps/defectives/urls.py`: add `from . import exports, views` and
```python
    path("defectives/", views.defectives_dashboard, name="defectives_dashboard"),
    path("defectives/export/", exports.defective_list_xlsx, name="defective_list_xlsx"),
    path("defectives/batches/<str:number>/export/", exports.batch_xlsx, name="batch_xlsx"),
```

`apps/inventory/context_processors.py`, Defectives section becomes:
```python
    (
        "Defectives",
        [
            ("defectives_dashboard", "Dashboard", "recycle", "", False),
            ("defective_pieces", "Pieces", "tags", "", False),
            ("mark_defective", "Mark defective", "alert-octagon", "", False),
            ("return_batches", "Return batches", "truck-return", "", False),
        ],
    ),
```

- [ ] **Step 5: Templates**

`templates/defectives/dashboard.html`:
```html
{% extends "base.html" %}{% load defective_tags %}
{% block title %}Defectives dashboard{% endblock %}
{% block pretitle %}Defectives{% endblock %}
{% block page_title %}Defectives dashboard{% endblock %}
{% block actions %}<a href="{% url 'mark_defective' %}" class="btn btn-quiet"><i class="ti ti-alert-octagon"></i> Mark defective</a>
  <a href="{% url 'batch_new' %}" class="btn btn-primary"><i class="ti ti-plus"></i> New return batch</a>
  <a href="{% url 'defective_list_xlsx' %}" class="btn btn-outline-primary"><i class="ti ti-file-spreadsheet"></i> Defective list</a>{% endblock %}
{% block content %}{% url 'defective_pieces' as pieces_url %}{% url 'return_batches' as batches_url %}
<div class="row row-deck row-cards">
  <div class="col-6 col-lg-3"><a class="card card-sm card-link h-100" href="{{ pieces_url }}?status=IN_STORE"><div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar kpi-brand"><i class="ti ti-building-warehouse"></i></span>
    <div><div class="fw-medium fs-2 lh-1">{{ d.in_store }}</div><div class="text-secondary small mt-1">Pieces in store</div><div class="small text-secondary">not yet in a batch</div></div></div></div></a></div>
  <div class="col-6 col-lg-3"><a class="card card-sm card-link h-100" href="{{ batches_url }}?status=Draft"><div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar kpi-brand"><i class="ti ti-packages"></i></span>
    <div><div class="fw-medium fs-2 lh-1">{{ d.in_batch }}</div><div class="text-secondary small mt-1">In draft batches</div><div class="small text-secondary">{{ d.drafts }} draft batch(es)</div></div></div></div></a></div>
  <div class="col-6 col-lg-3"><a class="card card-sm card-link h-100" href="{{ pieces_url }}?status=SENT"><div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar {% if d.sent %}kpi-wait{% else %}kpi-brand{% endif %}"><i class="ti ti-truck"></i></span>
    <div><div class="fw-medium fs-2 lh-1">{{ d.sent }}</div><div class="text-secondary small mt-1">Sent, awaiting settlement</div><div class="small text-secondary">with the companies</div></div></div></div></a></div>
  <div class="col-6 col-lg-3"><a class="card card-sm card-link h-100" href="{{ batches_url }}"><div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar kpi-brand"><i class="ti ti-circle-check"></i></span>
    <div><div class="fw-medium fs-2 lh-1">{{ d.answered }}</div><div class="text-secondary small mt-1">Answered by companies</div><div class="small text-secondary">last 90 days</div></div></div></div></a></div>
  <div class="col-lg-5"><div class="card"><div class="card-header"><div><h3 class="card-title"><i class="ti ti-building-warehouse"></i> In the Defective store, per company</h3><div class="card-subtitle">Physical pieces waiting to go back</div></div></div>
    <div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Company</th><th class="num">In store</th><th class="num">In draft batch</th><th class="num">Total</th></tr></thead>
      <tbody>{% for r in d.store_rows %}<tr><td><a href="{{ pieces_url }}?company={{ r.company_id }}&amp;status=IN_STORE">{{ r.company__name }}</a></td><td class="num"><b>{{ r.store }}</b></td><td class="num">{{ r.batch }}</td><td class="num">{{ r.store|add:r.batch }}</td></tr>
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">The Defective store is empty.</td></tr>{% endfor %}</tbody></table></div></div></div>
  <div class="col-lg-7"><div class="card"><div class="card-header"><div><h3 class="card-title"><i class="ti ti-truck"></i> Sent, awaiting settlement</h3><div class="card-subtitle">Red = the oldest batch has waited more than 30 days</div></div></div>
    <div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Company</th><th class="num">Pieces</th><th>Batches</th><th>Oldest dispatched</th><th class="num">Waiting</th></tr></thead>
      <tbody>{% for r in d.sent_rows %}<tr><td><a href="{{ pieces_url }}?company={{ r.company_id }}&amp;status=SENT">{{ r.company__name }}</a></td><td class="num"><b>{{ r.n }}</b></td>
        <td>{% for b in r.batches %}<a class="code" href="{% url 'batch_detail' b.number %}">{{ b.number }}</a>{% if not forloop.last %}, {% endif %}{% endfor %}</td><td class="nowrap">{{ r.oldest.dispatched_on|date }}</td><td class="num">{{ r.waiting|waiting_badge }}</td></tr>
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">Nothing is waiting on a company.</td></tr>{% endfor %}</tbody></table></div></div></div>
  <div class="col-lg-5"><div class="card"><div class="card-header"><div><h3 class="card-title"><i class="ti ti-chart-bar"></i> Outcomes, last 90 days</h3><div class="card-subtitle">{{ d.answered }} pieces answered by the companies</div></div></div>
    <div class="list-group list-group-flush">{% for value, label, n in d.outcomes %}<a class="list-group-item list-group-item-action py-2" href="{{ pieces_url }}?outcome={{ value }}">
      <div class="d-flex align-items-center gap-2 mb-1">{{ value|outcome_badge }}<span class="ms-auto fw-bold num">{{ n }}</span></div>
      <div class="progress progress-sm"><div class="progress-bar {% if value == 'REJECTED_RETURNED' or value == 'REJECTED_SCRAPPED' %}bg-red{% else %}bar-brand{% endif %}" style="width:{% widthratio n d.outcome_max 100 %}%"></div></div></a>{% endfor %}</div></div></div>
  <div class="col-lg-7"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-clock"></i> Longest in store</h3>
    <div class="card-actions"><a href="{{ pieces_url }}?status=IN_STORE" class="btn btn-sm btn-outline-primary">All in store <i class="ti ti-arrow-right"></i></a></div></div>
    <div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Tag</th><th>Item</th><th>Company</th><th>Source</th><th class="num">In store</th></tr></thead>
      <tbody>{% for r in d.oldest %}{% with p=r.piece %}<tr><td><a class="code" href="{% url 'piece_detail' p.tag %}">{{ p.tag }}</a></td><td><span class="code">{{ p.item.code }}</span><div class="small text-secondary">{{ p.item.description }}</div></td>
        <td>{{ p.company.name }}</td><td>{% include "defectives/_source.html" %}</td><td class="num">{{ r.days }} days</td></tr>{% endwith %}
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">Nothing in store.</td></tr>{% endfor %}</tbody></table></div></div></div>
</div>
{% endblock %}
```

`templates/defectives/pieces.html`, `{% block actions %}` becomes:
```html
{% block actions %}<a href="{% url 'mark_defective' %}" class="btn btn-quiet"><i class="ti ti-alert-octagon"></i> Mark defective</a>
  <a href="{% url 'defective_list_xlsx' %}" class="btn btn-outline-primary"><i class="ti ti-file-spreadsheet"></i> Export to Excel</a>{% endblock %}
```

`templates/defectives/batch_detail.html`, in `{% block actions %}` directly before the "All batches" link, add:
```html
  <a href="{% url 'batch_xlsx' batch.number %}" class="btn btn-outline-primary"><i class="ti ti-file-spreadsheet"></i> Export dispatch list</a>
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/defectives apps/inventory/context_processors.py templates/defectives tests/defectives/test_dashboard_exports.py
git commit -m "feat(defectives): dashboard, defective list and dispatch list downloads"
```

---

### Task 10: Complaints models, and the links from ledger entries and pieces

**Files:**
- Create: `apps/complaints/__init__.py` (empty), `apps/complaints/apps.py`, `apps/complaints/models.py`, `apps/complaints/migrations/__init__.py` (empty), generated `apps/complaints/migrations/0001_initial.py`
- Modify: `config/settings/base.py` (INSTALLED_APPS)
- Modify: `apps/inventory/models.py` (`StockEntry.complaint`), `apps/inventory/services.py` (`post_entry(complaint=...)`), generated `apps/inventory/migrations/0008_stockentry_complaint.py`
- Modify: `apps/defectives/models.py` (`DefectivePiece.visit`), generated `apps/defectives/migrations/0002_defectivepiece_visit.py`
- Modify: `apps/defectives/services.py` (`create_piece(visit=...)`), `apps/defectives/selectors.py` (`PIECE_RELATED`, `piece_search_q`, `complaint_cells`)
- Modify: `tests/factories.py` (add `make_site`, `make_tech`)
- Test: `tests/complaints/__init__.py` (empty), `tests/complaints/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/factories.py`:
```python
def make_site(name="BARC", city="Visakhapatnam", **extra):
    """A site (reused if one with exactly this name and city exists)."""
    from apps.complaints.models import Site

    return Site.objects.get_or_create(name=name, city=city, defaults=extra)[0]


def make_tech(name="Ramu", **extra):
    from apps.complaints.models import Technician

    return Technician.objects.get_or_create(name=name, defaults=extra)[0]
```

Create `tests/complaints/__init__.py` (empty) and `tests/complaints/test_models.py`:
```python
import pytest
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.complaints.models import TRANSITIONS, Complaint, ComplaintEvent, Site, Status, Visit
from apps.defectives import selectors as defective_selectors
from apps.defectives.models import DefectivePiece, Source
from apps.defectives.services import create_piece
from apps.inventory.models import Company, EntryKind, ServiceSubtype
from apps.inventory.services import Line, post_entry
from tests.factories import make_item, make_site, make_tech, store

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def complaint(user, **extra):
    return Complaint.objects.create(
        number="CMP-0001",
        site=make_site(),
        company=Company.objects.get(name="Wipro Lighting"),
        fault="Flood lights not glowing",
        reported_on=TODAY,
        created_by=user,
        **extra,
    )


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
    p = create_piece(item=item, source=Source.SITE_VISIT, collected_on=TODAY, user=office_user, entry=e, visit=v)
    assert e.complaint == c and list(c.entries.all()) == [e] and p.visit == v
    found = defective_selectors.pieces_qs().get(pk=p.pk)
    assert defective_selectors.complaint_cells(found) == ["CMP-0001", "WL/AP/24871"]
    assert list(DefectivePiece.objects.filter(defective_selectors.piece_search_q("cmp-0001"))) == [p]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/complaints -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.complaints'`.

- [ ] **Step 3: Write the app and its models**

`apps/complaints/apps.py`:
```python
from django.apps import AppConfig


class ComplaintsConfig(AppConfig):
    name = "apps.complaints"
    label = "complaints"
```

`apps/complaints/models.py`:
```python
"""Complaints from customer sites: who reported what, which company's product failed, who visited and what was
done. Statuses move only through services.py, which checks TRANSITIONS and logs a ComplaintEvent."""

import re

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.inventory.models import IMMUTABLE, Company, Location, StockEntry


class Status(models.TextChoices):
    NOT_ATTENDED = "NOT_ATTENDED", "Not attended"
    ATTENDED = "ATTENDED", "Attended"
    MATERIAL_CHECK = "MATERIAL_CHECK", "Material need to check"
    AWAITING_MATERIAL = "AWAITING_MATERIAL", "Awaiting material"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"
    NOT_COVERED = "NOT_COVERED", "Not covered"


OPEN_STATUSES = [
    Status.NOT_ATTENDED,
    Status.ATTENDED,
    Status.MATERIAL_CHECK,
    Status.AWAITING_MATERIAL,
    Status.RESOLVED,
]
# Moves allowed from each status, in the order they are offered. NOT_COVERED is its own action (it needs a
# reason). A CLOSED complaint can only be reopened by Admin (services.reopen), which moves it to ATTENDED.
TRANSITIONS = {
    Status.NOT_ATTENDED: [Status.ATTENDED, Status.NOT_COVERED],
    Status.ATTENDED: [Status.MATERIAL_CHECK, Status.AWAITING_MATERIAL, Status.RESOLVED, Status.NOT_COVERED],
    Status.MATERIAL_CHECK: [Status.ATTENDED, Status.AWAITING_MATERIAL, Status.RESOLVED, Status.NOT_COVERED],
    Status.AWAITING_MATERIAL: [Status.ATTENDED, Status.MATERIAL_CHECK, Status.RESOLVED, Status.NOT_COVERED],
    Status.RESOLVED: [Status.CLOSED, Status.ATTENDED, Status.NOT_COVERED],
    Status.CLOSED: [],
    Status.NOT_COVERED: [],
}


class Priority(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class NotCoveredReason(models.TextChoices):
    NOT_OURS = "NOT_OURS", "Not our product"
    OUT_OF_WARRANTY = "OUT_OF_WARRANTY", "Out of warranty"
    CANCELLED = "CANCELLED", "Customer cancelled"
    OTHER = "OTHER", "Other"


def _tidy(text):
    return re.sub(r"\s+", " ", text or "").strip()


class Site(models.Model):
    """A customer site. Picked from a searchable list when filing a complaint; keeps its complaint history."""

    name = models.CharField(max_length=120)
    city = models.CharField(max_length=60)
    contact_name = models.CharField("contact person", max_length=80, blank=True)
    phone = models.CharField(max_length=10, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "city"]
        constraints = [models.UniqueConstraint(Lower("name"), Lower("city"), name="site_name_city_ci_unique")]

    def __str__(self):
        return f"{self.name}, {self.city}"

    def save(self, *args, **kwargs):
        self.name, self.city = _tidy(self.name), _tidy(self.city)
        super().save(*args, **kwargs)


class Technician(models.Model):
    """A technician who visits sites. Names only; technicians don't log in."""

    name = models.CharField(max_length=60)
    phone = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="technician_name_ci_unique")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = _tidy(self.name)
        super().save(*args, **kwargs)


class Complaint(models.Model):
    number = models.CharField(max_length=12, unique=True)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="complaints")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="complaints")  # whose product
    company_ref = models.CharField("company complaint no.", max_length=60, blank=True, db_index=True)
    fault = models.TextField()
    qty_affected = models.PositiveIntegerField(null=True, blank=True)
    reported_on = models.DateField()
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    technicians = models.ManyToManyField(Technician, blank=True, related_name="complaints")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_ATTENDED)
    contact_name = models.CharField("contact person", max_length=80, blank=True)  # copied from the site
    phone = models.CharField(max_length=10, blank=True)
    not_covered_reason = models.CharField(max_length=20, choices=NotCoveredReason.choices, blank=True)
    closed_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reported_on", "-id"]
        indexes = [models.Index(fields=["status"], name="complaint_status_idx")]

    def __str__(self):
        return self.number

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES


class ComplaintEvent(models.Model):
    """Append-only history: every status change of a complaint, who made it, when, and why."""

    complaint = models.ForeignKey(Complaint, on_delete=models.PROTECT, related_name="events")
    from_status = models.CharField(max_length=20, choices=Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Status.choices)
    at = models.DateField()
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    reason = models.CharField(max_length=20, choices=NotCoveredReason.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]
        triggers = [IMMUTABLE]

    def __str__(self):
        return f"{self.complaint}: {self.from_status or '-'} -> {self.to_status}"


class Visit(models.Model):
    """A technicians' visit to the site: work done, parts given (one Stock OUT) and failed parts collected
    (one Stock IN at the Defective store, one tagged piece per unit)."""

    number = models.CharField(max_length=12, unique=True)
    complaint = models.ForeignKey(Complaint, on_delete=models.PROTECT, related_name="visits")
    visit_date = models.DateField()
    technicians = models.ManyToManyField(Technician, related_name="visits")
    work_done = models.TextField()
    next_status = models.CharField(max_length=20, choices=Status.choices)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    out_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="visit_given"
    )
    collect_entry = models.OneToOneField(
        StockEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="visit_collected"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visit_date", "-id"]

    def __str__(self):
        return self.number
```

- [ ] **Step 4: Install the app and add the links**

`config/settings/base.py`: add `"apps.complaints",` to `INSTALLED_APPS` directly after `"apps.defectives",`.

`apps/inventory/models.py`, in `StockEntry` below `return_batch`:
```python
    # Set by the complaints services: the complaint a visit's parts-given / collection entry belongs to.
    complaint = models.ForeignKey(
        "complaints.Complaint", on_delete=models.PROTECT, null=True, blank=True, related_name="entries"
    )
```

`apps/inventory/services.py`, `post_entry`: add the keyword `complaint=None,` after `return_batch=None,` in the signature and `complaint=complaint,` after `return_batch=return_batch,` in `StockEntry.objects.create(...)`.

`apps/defectives/models.py`, in `DefectivePiece` below `collected_on`:
```python
    visit = models.ForeignKey(
        "complaints.Visit", on_delete=models.PROTECT, null=True, blank=True, related_name="pieces"
    )  # the visit that collected it (source SITE_VISIT)
```

`apps/defectives/services.py`, `create_piece`: add the keyword `visit=None` after `note=""` in the signature and `visit=visit,` after `collected_on=collected_on,` in `DefectivePiece.objects.create(...)`.

`apps/defectives/selectors.py`:
```python
# What a piece row shows, including the complaint and site of the visit that collected it.
PIECE_RELATED = ["item", "company", "return_batch", "visit__complaint__site"]
```
In `piece_search_q`, add `| Q(visit__complaint__number__icontains=text)` as the last alternative and drop "Task 10 adds the complaint number." from its docstring. Replace `complaint_cells`:
```python
def complaint_cells(piece):
    """[complaint no., company complaint no.] for the dispatch list ('Found in stock' for pieces from stock)."""
    if piece.visit_id:
        return [piece.visit.complaint.number, piece.visit.complaint.company_ref]
    return ["Found in stock" if piece.source == Source.FOUND_IN_STOCK else "", ""]
```

- [ ] **Step 5: Generate the migrations**

Run: `uv run python manage.py makemigrations complaints defectives inventory`
Expected: `apps/complaints/migrations/0001_initial.py` (depends on `inventory.0007_stockentry_return_batch`), `apps/defectives/migrations/0002_defectivepiece_visit.py` and `apps/inventory/migrations/0008_stockentry_complaint.py` (both depend on `complaints.0001_initial`). Rename the two generated add-field files to exactly those names if Django picked others.

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/complaints apps/inventory/models.py apps/inventory/services.py apps/inventory/migrations/0008_stockentry_complaint.py apps/defectives config/settings/base.py tests/factories.py tests/complaints
git commit -m "feat(complaints): sites, technicians, complaints, events and visits linked to the ledger"
```

---

### Task 11: Complaints services (sites, technicians, filing, status changes, visits)

**Files:**
- Create: `apps/complaints/services.py`
- Modify: `tests/factories.py` (add `make_complaint`)
- Test: `tests/complaints/test_services.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/factories.py` (it uses `Company` and `timezone`, which the file already imports):
```python
def make_complaint(user, site=None, company="Wipro Lighting", reported_on=None, **extra):
    """A complaint filed through the service: Not attended, with its 'Complaint filed' event."""
    from apps.complaints.services import file_complaint

    return file_complaint(
        site=site or make_site(),
        company=Company.objects.get(name=company),
        fault=extra.pop("fault", "Flood lights not glowing"),
        reported_on=reported_on or timezone.localdate(),
        user=user,
        **extra,
    )
```

Create `tests/complaints/test_services.py`:
```python
from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.complaints.models import NotCoveredReason, Priority, Status, Visit
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
    visit_next_options,
)
from apps.defectives.models import DefectivePiece, Source
from apps.inventory.models import Company, EntryKind, ServiceSubtype, StockBalance, StockEntry
from apps.inventory.services import balance_drift
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


def test_save_site_tidies_and_checks():
    s = save_site(
        data={"name": " Andhra  University ", "city": "Visakhapatnam", "contact_name": "Estate office", "phone": "98488 12345"}
    )
    assert (s.name, s.contact_name, s.phone) == ("Andhra University", "Estate office", "9848812345")
    with pytest.raises(ComplaintError, match="Andhra University, Visakhapatnam already exists. Pick it from the list."):
        save_site(data={"name": "andhra university", "city": "visakhapatnam"})
    assert save_site(data={"name": "Andhra University", "city": "Guntur"}).pk != s.pk
    for data, message in [
        ({"name": "", "city": "X"}, "Enter the site name."),
        ({"name": "X", "city": " "}, "Enter the city."),
        ({"name": "X", "city": "Y", "phone": "12345"}, "Phone must be a 10-digit mobile number."),
    ]:
        with pytest.raises(ComplaintError, match=message):
            save_site(data=data)


def test_edit_site_keeps_its_own_name():
    s = make_site("BARC", "Visakhapatnam")
    data = {"name": "BARC", "city": "Visakhapatnam", "contact_name": "Chenna Keshavulu"}
    assert save_site(site=s, data=data).contact_name == "Chenna Keshavulu"


def test_save_technician_and_hide():
    t = save_technician(name="  Suresh ", phone="9876543210")
    assert t.name == "Suresh"
    with pytest.raises(ComplaintError, match="Suresh is already in the list."):
        save_technician(name="suresh")
    with pytest.raises(ComplaintError, match="Enter the name of the technician."):
        save_technician(name=" ")
    set_active(t, active=False)
    t.refresh_from_db()
    assert not t.is_active


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
    assert (c.number, c.status, c.fault, c.contact_name, c.phone, c.priority) == (
        "CMP-0001",
        Status.NOT_ATTENDED,
        "Battens failed in canteen",
        "Murthy",
        "9908127999",
        Priority.HIGH,
    )
    assert list(c.technicians.all()) == [tech] and moves(c) == [("", Status.NOT_ATTENDED)]
    filed = c.events.get()
    assert (filed.note, filed.at) == ("Complaint filed", TODAY)


def test_contact_can_be_changed_for_one_complaint(office_user):
    c = make_complaint(office_user, site=make_site(contact_name="Murthy"), contact_name="Bujji Babu", phone="")
    assert (c.contact_name, c.phone) == ("Bujji Babu", "")


@pytest.mark.parametrize(
    "change, message",
    [
        ({"site": None}, "Choose the site."),
        ({"company": None}, "Choose the company whose product failed."),
        ({"fault": " "}, "Describe the fault."),
        ({"reported_on": None}, "Choose the date the complaint was reported."),
        ({"reported_on": TODAY + timedelta(days=1)}, "The reported date can't be in the future."),
        ({"qty_affected": 0}, "Quantity affected must be a whole number of 1 or more."),
        ({"phone": "123"}, "Phone must be a 10-digit mobile number."),
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
    change_status(complaint=c, to=Status.RESOLVED, user=office_user)
    change_status(complaint=c, to=Status.CLOSED, user=office_user)
    c.refresh_from_db()
    assert c.closed_on == TODAY and not c.is_open
    assert moves(c)[-1] == (Status.RESOLVED, Status.CLOSED)


def test_not_covered_needs_a_reason(office_user):
    c = make_complaint(office_user)
    with pytest.raises(ComplaintError, match="Choose why the complaint is not covered."):
        close_not_covered(complaint=c, reason="", user=office_user)
    with pytest.raises(ComplaintError, match="Write a note when the reason is Other."):
        close_not_covered(complaint=c, reason=NotCoveredReason.OTHER, user=office_user)
    close_not_covered(complaint=c, reason=NotCoveredReason.NOT_OURS, user=office_user, note="Another brand")
    c.refresh_from_db()
    assert (c.status, c.not_covered_reason, c.closed_on) == (Status.NOT_COVERED, "NOT_OURS", TODAY)
    assert c.events.last().reason == "NOT_OURS"
    with pytest.raises(ComplaintError, match="can't move to Attended"):
        change_status(complaint=c, to=Status.ATTENDED, user=office_user)


def test_only_admin_reopens_a_closed_complaint(office_user, admin_user):
    c = make_complaint(office_user)
    for to in (Status.ATTENDED, Status.RESOLVED, Status.CLOSED):
        change_status(complaint=c, to=to, user=office_user)
    with pytest.raises(ComplaintError, match="A closed complaint can't move to Attended. Only Admin can reopen it."):
        change_status(complaint=c, to=Status.ATTENDED, user=office_user)
    with pytest.raises(ComplaintError, match="Write why the complaint is being reopened."):
        reopen(complaint=c, user=admin_user, note=" ")
    change_status(complaint=c, to=Status.ATTENDED, user=admin_user, note="Lights failed again")
    c.refresh_from_db()
    assert (c.status, c.closed_on) == (Status.ATTENDED, None)
    assert c.events.last().note == "Reopened: Lights failed again"


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
        collected=[(stocked, 2, "B2405", date(2026, 3, 1), "no output")],
    )
    assert v.number == "VIS-0001" and v.location == loc()
    out, col = v.out_entry, v.collect_entry
    assert (out.kind, out.subtype, out.complaint, out.ref, out.party) == (
        EntryKind.OUT,
        ServiceSubtype.COMPLAINT,
        c,
        "CMP-0001",
        "BARC, Visakhapatnam",
    )
    assert (col.kind, col.subtype, col.complaint) == (EntryKind.IN, ServiceSubtype.DEFECTIVE_COLLECTED, c)
    assert qty(stocked, loc()) == 3 and qty(stocked, store()) == 2
    pieces = [(p.tag, p.source, p.visit, p.batch_code, p.fault) for p in DefectivePiece.objects.order_by("tag")]
    assert pieces == [
        ("DEF-0001", Source.SITE_VISIT, v, "B2405", "no output"),
        ("DEF-0002", Source.SITE_VISIT, v, "B2405", "no output"),
    ]
    c.refresh_from_db()
    assert c.status == Status.MATERIAL_CHECK
    assert moves(c)[1:] == [(Status.NOT_ATTENDED, Status.ATTENDED), (Status.ATTENDED, Status.MATERIAL_CHECK)]
    assert set(c.technicians.all()) == {ramu, appa} and balance_drift() == []


def test_visit_without_parts_or_pieces(office_user):
    c = make_complaint(office_user)
    v = record_visit(
        complaint=c,
        visit_date=TODAY,
        technicians=[make_tech()],
        work_done="Site checked, drivers needed",
        next_status=Status.ATTENDED,
        user=office_user,
    )
    assert v.out_entry is None and v.collect_entry is None and not StockEntry.objects.exists()
    assert moves(c)[-1] == (Status.NOT_ATTENDED, Status.ATTENDED)


def test_over_issue_saves_nothing_at_all(office_user, stocked):
    c = make_complaint(office_user)
    with pytest.raises(ComplaintError, match="Parts given: Only 5 NOS of LG78-150-700 at Vizag Office."):
        record_visit(
            complaint=c,
            visit_date=TODAY,
            technicians=[make_tech()],
            work_done="x",
            next_status=Status.ATTENDED,
            user=office_user,
            location=loc(),
            parts=[(stocked, 9)],
            collected=[(stocked, 1, "", None, "x")],
        )
    assert not Visit.objects.exists() and not DefectivePiece.objects.exists()
    assert StockEntry.objects.count() == 1  # only the opening stock
    c.refresh_from_db()
    assert c.status == Status.NOT_ATTENDED and c.events.count() == 1
    v = record_visit(
        complaint=c, visit_date=TODAY, technicians=[make_tech()], work_done="x", next_status=Status.ATTENDED, user=office_user
    )
    assert v.number == "VIS-0001"  # the refused visit used no number


@pytest.mark.parametrize(
    "change, message",
    [
        ({"visit_date": None}, "Choose the visit date."),
        ({"visit_date": TODAY + timedelta(days=1)}, "The visit date can't be in the future."),
        ({"visit_date": TODAY - timedelta(days=5)}, "The visit can't be before the complaint was reported"),
        ({"technicians": []}, "Choose who attended."),
        ({"work_done": " "}, "Write what work was done."),
        ({"next_status": Status.CLOSED}, "A complaint that is Not attended can't move to Closed."),
        ({"location": None}, "Choose the location the parts were given from."),
    ],
)
def test_visit_rules(office_user, stocked, change, message):
    c = make_complaint(office_user)
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


def test_no_visits_on_a_finished_complaint(office_user):
    c = make_complaint(office_user)
    close_not_covered(complaint=c, reason=NotCoveredReason.CANCELLED, user=office_user)
    with pytest.raises(ComplaintError, match="This complaint is Not covered, so visits can't be added."):
        record_visit(
            complaint=c, visit_date=TODAY, technicians=[make_tech()], work_done="x", next_status=Status.ATTENDED, user=office_user
        )
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/complaints/test_services.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.complaints.services'`.

- [ ] **Step 3: Write `apps/complaints/services.py`**

```python
"""All writes for complaints, sites and technicians. Views and commands call these; nothing else changes a
complaint. A visit's stock effects go through inventory's post_entry and defectives' create_piece, all in one
transaction, so a visit that would over-issue stock saves nothing at all."""

import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import ADMIN, has_role
from apps.core.numbers import next_number
from apps.defectives.models import Source
from apps.defectives.services import create_piece
from apps.inventory.models import EntryKind, Location, ServiceSubtype
from apps.inventory.services import Line, StockError, post_entry

from .models import TRANSITIONS, Complaint, ComplaintEvent, NotCoveredReason, Priority, Site, Status, Technician, Visit

PHONE = re.compile(r"[6-9]\d{9}")  # a 10-digit Indian mobile number
# Where a visit can leave a complaint. A first visit always logs Not attended -> Attended first.
WORK_STATUSES = [Status.ATTENDED, Status.MATERIAL_CHECK, Status.AWAITING_MATERIAL, Status.RESOLVED]


class ComplaintError(ValidationError):
    """A complaints rule was broken. The message is safe to show to staff as-is."""


def _tidy(text):
    return " ".join((text or "").split())


def _phone(text):
    phone = re.sub(r"\s", "", text or "")
    if phone and not PHONE.fullmatch(phone):
        raise ComplaintError("Phone must be a 10-digit mobile number.")
    return phone


def _label(status):
    return Status(status).label


# ---------------------------------------------------------------- sites and technicians


@transaction.atomic
def save_site(*, data, site=None):
    """Create (site=None) or update a site. data keys: name, city, contact_name, phone, address."""
    name, city = _tidy(data.get("name"))[:120], _tidy(data.get("city"))[:60]
    if not name:
        raise ComplaintError("Enter the site name.")
    if not city:
        raise ComplaintError("Enter the city.")
    duplicate = f"{name}, {city} already exists. Pick it from the list."
    clash = Site.objects.filter(name__iexact=name, city__iexact=city).exclude(pk=getattr(site, "pk", None)).first()
    if clash:  # name the saved site as it is spelled, not as it was typed
        raise ComplaintError(f"{clash} already exists. Pick it from the list.")
    site = site or Site()
    site.name, site.city = name, city
    site.contact_name = _tidy(data.get("contact_name"))[:80]
    site.phone = _phone(data.get("phone"))
    site.address = (data.get("address") or "").strip()
    try:
        with transaction.atomic():
            site.save()
    except IntegrityError as exc:  # someone saved the same site a moment ago
        raise ComplaintError(duplicate) from exc
    return site


@transaction.atomic
def save_technician(*, name, phone="", technician=None):
    name = _tidy(name)[:60]
    if not name:
        raise ComplaintError("Enter the name of the technician.")
    duplicate = f"{name} is already in the list."
    clash = Technician.objects.filter(name__iexact=name).exclude(pk=getattr(technician, "pk", None)).first()
    if clash:  # name the saved technician as spelled ("Suresh"), not as typed ("suresh")
        raise ComplaintError(f"{clash.name} is already in the list.")
    technician = technician or Technician()
    technician.name, technician.phone = name, _phone(phone)
    try:
        with transaction.atomic():
            technician.save()
    except IntegrityError as exc:
        raise ComplaintError(duplicate) from exc
    return technician


def set_active(obj, *, active):
    """Show or hide a site or technician in the dropdowns (Admin only; the view checks the role)."""
    obj.is_active = active
    obj.save(update_fields=["is_active"])
    return obj


# ---------------------------------------------------------------- complaints


def _log(complaint, to, *, at, user, note="", reason=""):
    """Record a status change (append-only event) and apply it to the complaint."""
    ComplaintEvent.objects.create(
        complaint=complaint, from_status=complaint.status, to_status=to, at=at, by=user, note=note[:300], reason=reason
    )
    complaint.status = to
    if to in (Status.CLOSED, Status.NOT_COVERED):
        complaint.closed_on = at
    else:
        complaint.closed_on = None  # a reopened complaint is open again
    if reason:
        complaint.not_covered_reason = reason
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
    """A new complaint, Not attended. Contact and phone default to the site's; pass them to override."""
    if site is None:
        raise ComplaintError("Choose the site.")
    if company is None:
        raise ComplaintError("Choose the company whose product failed.")
    if not (fault or "").strip():
        raise ComplaintError("Describe the fault.")
    if reported_on is None:
        raise ComplaintError("Choose the date the complaint was reported.")
    if reported_on > timezone.localdate():
        raise ComplaintError("The reported date can't be in the future.")
    if qty_affected is not None and (not isinstance(qty_affected, int) or qty_affected < 1):
        raise ComplaintError("Quantity affected must be a whole number of 1 or more.")
    if priority not in Priority.values:
        raise ComplaintError("Choose the priority.")
    complaint = Complaint.objects.create(
        number=next_number("CMP"),
        site=site,
        company=company,
        company_ref=_tidy(company_ref)[:60],
        fault=fault.strip(),
        qty_affected=qty_affected,
        reported_on=reported_on,
        priority=priority,
        contact_name=_tidy(site.contact_name if contact_name is None else contact_name)[:80],
        phone=_phone(site.phone if phone is None else phone),
        created_by=user,
    )
    complaint.technicians.set(technicians)
    ComplaintEvent.objects.create(
        complaint=complaint, to_status=Status.NOT_ATTENDED, at=reported_on, by=user, note="Complaint filed"
    )
    return complaint


@transaction.atomic
def reopen(*, complaint, user, note, at=None):
    """Admin only: a Closed complaint goes back to Attended. The reason is logged."""
    complaint = Complaint.objects.select_for_update().get(pk=complaint.pk)
    if complaint.status != Status.CLOSED:
        raise ComplaintError("Only a closed complaint can be reopened.")
    if not has_role(user, ADMIN):
        raise ComplaintError("A closed complaint can't move to Attended. Only Admin can reopen it.")
    if not (note or "").strip():
        raise ComplaintError("Write why the complaint is being reopened.")
    _log(complaint, Status.ATTENDED, at=at or timezone.localdate(), user=user, note=f"Reopened: {note.strip()}")
    return complaint


@transaction.atomic
def change_status(*, complaint, to, user, note="", reason="", at=None):
    """Move a complaint to `to`, checked against TRANSITIONS, and log it."""
    complaint = Complaint.objects.select_for_update().get(pk=complaint.pk)
    at = at or timezone.localdate()
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
    note = (note or "").strip()
    if to == Status.NOT_COVERED:
        if reason not in NotCoveredReason.values:
            raise ComplaintError("Choose why the complaint is not covered.")
        if reason == NotCoveredReason.OTHER and not note:
            raise ComplaintError("Write a note when the reason is Other.")
    else:
        reason = ""
    _log(complaint, to, at=at, user=user, note=note, reason=reason)
    return complaint


def close_not_covered(*, complaint, reason, user, note="", at=None):
    """Close a complaint that isn't ours to do (any open status), with a reason."""
    return change_status(complaint=complaint, to=Status.NOT_COVERED, user=user, note=note, reason=reason, at=at)


# ---------------------------------------------------------------- visits


def visit_next_options(complaint):
    """Statuses a visit can leave this complaint in."""
    if complaint.status == Status.NOT_ATTENDED:
        return list(WORK_STATUSES)
    allowed = TRANSITIONS[complaint.status]
    return [s for s in WORK_STATUSES if s == complaint.status or s in allowed]


@transaction.atomic
def record_visit(
    *, complaint, visit_date, technicians, work_done, next_status, user, location=None, parts=(), collected=()
):
    """One visit, all or nothing: parts given (one Stock OUT, subtype COMPLAINT, from `location`), failed parts
    collected (one Stock IN at the Defective store, one tagged piece per unit) and the status change.

    parts: [(item, qty)]. collected: [(item, qty, batch_code, pkd, fault)]. Returns the Visit.
    """
    complaint = Complaint.objects.select_for_update().select_related("site").get(pk=complaint.pk)
    if not complaint.is_open:
        raise ComplaintError(f"This complaint is {_label(complaint.status)}, so visits can't be added.")
    if visit_date is None:
        raise ComplaintError("Choose the visit date.")
    if visit_date > timezone.localdate():
        raise ComplaintError("The visit date can't be in the future.")
    if visit_date < complaint.reported_on:
        raise ComplaintError(
            f"The visit can't be before the complaint was reported ({complaint.reported_on:%d-%m-%Y})."
        )
    if not technicians:
        raise ComplaintError("Choose who attended.")
    if not (work_done or "").strip():
        raise ComplaintError("Write what work was done.")
    if next_status not in visit_next_options(complaint):
        raise ComplaintError(f"A complaint that is {_label(complaint.status)} can't move to {_label(next_status)}.")
    if parts and location is None:
        raise ComplaintError("Choose the location the parts were given from.")
    number = next_number("VIS")
    party = f"{complaint.site.name}, {complaint.site.city}"
    common = {"entry_date": visit_date, "user": user, "party": party, "ref": complaint.number, "complaint": complaint}
    out = None
    if parts:
        try:
            out = post_entry(
                kind=EntryKind.OUT,
                lines=[Line(item, location, -qty) for item, qty in parts],
                subtype=ServiceSubtype.COMPLAINT,
                note=f"Visit {number}",
                **common,
            )
        except StockError as exc:
            raise ComplaintError(f"Parts given: {exc.message}") from exc
    col = None
    if collected:
        store = Location.defective_store()
        col = post_entry(
            kind=EntryKind.IN,
            lines=[Line(item, store, qty, batch, pkd) for item, qty, batch, pkd, _ in collected],
            subtype=ServiceSubtype.DEFECTIVE_COLLECTED,
            note=f"Visit {number}",
            **common,
        )
    visit = Visit.objects.create(
        number=number,
        complaint=complaint,
        visit_date=visit_date,
        work_done=work_done.strip(),
        next_status=next_status,
        location=location if parts else None,
        out_entry=out,
        collect_entry=col,
        created_by=user,
    )
    visit.technicians.set(technicians)
    complaint.technicians.add(*technicians)
    for item, qty, batch, pkd, fault in collected:
        for _ in range(qty):
            create_piece(
                item=item,
                source=Source.SITE_VISIT,
                collected_on=visit_date,
                user=user,
                entry=col,
                batch_code=batch,
                pkd=pkd,
                fault=fault,
                visit=visit,
                note=f"Collected at site ({complaint.number})",
            )
    if complaint.status == Status.NOT_ATTENDED:
        _log(complaint, Status.ATTENDED, at=visit_date, user=user, note=f"Visit {number}")
    if next_status != complaint.status:
        _log(complaint, next_status, at=visit_date, user=user, note=f"Visit {number}")
    return visit
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/complaints -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/complaints/services.py tests/factories.py tests/complaints/test_services.py
git commit -m "feat(complaints): file, change status, reopen, not covered and record visit as one transaction"
```

---

### Task 12: New complaint (with the New site modal) and the complaint page (timeline, visits, status changes)

**Files:**
- Create: `apps/complaints/forms.py`, `apps/complaints/selectors.py`, `apps/complaints/views.py`, `apps/complaints/urls.py`, `apps/complaints/templatetags/__init__.py` (empty), `apps/complaints/templatetags/complaint_tags.py`
- Modify: `config/urls.py`, `apps/inventory/context_processors.py` (Complaints section)
- Create: `templates/complaints/form.html`, `templates/complaints/_site_modal.html`, `templates/complaints/detail.html`, `static/js/site-picker.js`
- Modify: `templates/defectives/_source.html` (link the complaint)
- Test: `tests/complaints/test_complaint_views.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/complaints/test_complaint_views.py`:
```python
import pytest
from django.utils import timezone

from apps.complaints.models import Complaint, Status
from apps.complaints.services import change_status, record_visit
from apps.inventory.models import Company
from tests.factories import make_complaint, make_item, make_site, make_tech

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


def test_new_complaint_page(office_client):
    make_site(contact_name="Murthy")
    html = office_client.get(NEW).content.decode()
    assert 'id="sites-data"' in html and "Murthy" in html and 'id="new-site-btn"' in html
    assert "selected>Wipro Lighting</option>" in html  # the configured default company, changeable


def test_file_a_complaint(office_client):
    site = make_site(contact_name="Murthy", phone="9908127999")
    r = submit(office_client, complaint_data(site))
    c = Complaint.objects.get()
    assert r.url == f"/complaints/{c.number}/"
    assert (c.contact_name, c.phone, c.priority, c.company.name) == ("Murthy", "9908127999", "HIGH", "Havells")
    html = office_client.get(r.url).content.decode()
    assert "Complaint CMP-0001 filed for BARC." in html and "Not attended" in html and "Complaint filed" in html


def test_errors_keep_the_form(office_client):
    html = submit(office_client, complaint_data(make_site(), fault="")).content.decode()
    assert "Fault: Describe the fault." in html and not Complaint.objects.exists()


def test_resubmit_does_not_file_twice(office_client):
    office_client.get(NEW)
    data = {**complaint_data(make_site()), "entry_token": office_client.session["entry_tokens"][-1]}
    first, again = office_client.post(NEW, data), office_client.post(NEW, data)
    assert again.url == first.url and Complaint.objects.count() == 1


def test_site_quick_create(office_client):
    data = {"ns-name": "Andhra University", "ns-city": "Visakhapatnam", "ns-contact_name": "Estate office", "ns-phone": "9848812345"}
    made = office_client.post("/sites/quick-create/", data).json()
    assert made["ok"] and (made["site"]["name"], made["site"]["contact"]) == ("Andhra University", "Estate office")
    dup = office_client.post("/sites/quick-create/", data).json()
    assert not dup["ok"] and "already exists" in dup["error"]
    bad = office_client.post("/sites/quick-create/", {"ns-name": "", "ns-city": "X"}).json()
    assert bad == {"ok": False, "error": "Site name: Enter the site name."}


def test_detail_shows_details_timeline_and_actions(office_client, office_user):
    c = make_complaint(office_user, company_ref="WL/AP/24871")
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, note="Called the site")
    html = office_client.get(f"/complaints/{c.number}/").content.decode()
    assert "WL/AP/24871" in html and "Not attended → Attended" in html and "Called the site" in html
    assert "Change status" in html and "Close as Not covered" in html
    assert "Awaiting material <b>0</b> days" in html


def test_change_status_from_the_page(office_client, office_user):
    c = make_complaint(office_user)
    url = f"/complaints/{c.number}/status/"
    html = office_client.post(url, {"to": "ATTENDED", "note": "Called"}, follow=True).content.decode()
    assert "CMP-0001: Not attended → Attended." in html
    html = office_client.post(url, {"to": "CLOSED"}, follow=True).content.decode()
    assert "A complaint that is Attended" in html


def test_not_covered_from_the_page(office_client, office_user):
    c = make_complaint(office_user)
    html = office_client.post(
        f"/complaints/{c.number}/not-covered/", {"reason": "OUT_OF_WARRANTY", "note": ""}, follow=True
    ).content.decode()
    assert "CMP-0001 closed as Not covered (Out of warranty)." in html
    c.refresh_from_db()
    assert c.status == Status.NOT_COVERED


def test_reopen_is_admin_only(office_client, admin_client, office_user):
    c = make_complaint(office_user)
    for to in (Status.ATTENDED, Status.RESOLVED, Status.CLOSED):
        change_status(complaint=c, to=to, user=office_user)
    detail, status = f"/complaints/{c.number}/", f"/complaints/{c.number}/status/"
    html = office_client.get(detail).content.decode()
    assert "Only Admin can reopen it" in html and "Reopen (move to Attended)" not in html
    html = office_client.post(status, {"to": "ATTENDED", "note": "x"}, follow=True).content.decode()
    assert "Only Admin can reopen it." in html
    assert "Reopen (move to Attended)" in admin_client.get(detail).content.decode()
    admin_client.post(status, {"to": "ATTENDED", "note": "Failed again"})
    c.refresh_from_db()
    assert c.status == Status.ATTENDED


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
    assert 'href="/defectives/pieces/DEF-0001/"' in office_client.get(f"/complaints/{c.number}/").content.decode()


def test_nav_links_new_complaint(office_client):
    assert 'href="/complaints/new/"' in office_client.get("/").content.decode()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/complaints/test_complaint_views.py -q`
Expected: FAIL (404 on `/complaints/new/`).

- [ ] **Step 3: Forms, selectors, template tags**

`apps/complaints/forms.py`:
```python
from django import forms
from django.conf import settings
from django.utils import timezone

from apps.inventory.forms import TablerFormMixin
from apps.inventory.models import Company

from .models import Priority, Site, Technician

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
PHONE = forms.TextInput(attrs={"type": "tel", "inputmode": "numeric", "maxlength": 10, "placeholder": "10-digit mobile"})


class ComplaintForm(TablerFormMixin, forms.Form):
    site = forms.ModelChoiceField(
        Site.objects.filter(is_active=True),
        error_messages={"required": "Choose the site.", "invalid_choice": "Choose the site."},
    )
    contact_name = forms.CharField(
        max_length=80, required=False, label="Contact person",
        widget=forms.TextInput(attrs={"placeholder": "Filled from the site"}),
    )
    phone = forms.CharField(max_length=10, required=False, widget=PHONE)
    company = forms.ModelChoiceField(
        Company.objects.filter(is_active=True),
        label="Company (whose product failed)",
        empty_label=None,
        widget=forms.Select(attrs={"data-ts": ""}),
    )
    company_ref = forms.CharField(
        max_length=60, required=False, label="Company complaint no.",
        widget=forms.TextInput(attrs={"placeholder": "The company's ticket no., if any"}),
    )
    reported_on = forms.DateField(
        label="Reported on", widget=DATE, error_messages={"required": "Choose the date the complaint was reported."}
    )
    qty_affected = forms.IntegerField(
        min_value=1, required=False, label="Qty affected",
        widget=forms.NumberInput(attrs={"min": 1, "step": 1, "inputmode": "numeric", "placeholder": "e.g. 6"}),
        error_messages={"min_value": "Quantity affected must be a whole number of 1 or more."},
    )
    fault = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. 6 linear fittings flickering on the 2nd floor"}),
        error_messages={"required": "Describe the fault."},
    )
    priority = forms.ChoiceField(choices=Priority.choices, initial=Priority.NORMAL, widget=forms.RadioSelect)
    technicians = forms.ModelMultipleChoiceField(
        Technician.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={"data-ts": "", "placeholder": "Assign now or later"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reported_on"].widget.attrs["max"] = timezone.localdate().isoformat()
        if not self.is_bound and not self.initial.get("company"):
            default = Company.objects.filter(name=settings.DEFAULT_COMPANY, is_active=True).first()
            if default:
                self.fields["company"].initial = default.pk


class SiteForm(TablerFormMixin, forms.Form):
    """The New site modal (prefix "ns") and the site edit page."""

    name = forms.CharField(
        max_length=120, label="Site name", error_messages={"required": "Enter the site name."},
        widget=forms.TextInput(attrs={"placeholder": "e.g. Andhra University"}),
    )
    city = forms.CharField(
        max_length=60, error_messages={"required": "Enter the city."},
        widget=forms.TextInput(attrs={"list": "site-cities", "placeholder": "e.g. Visakhapatnam"}),
    )
    contact_name = forms.CharField(
        max_length=80, required=False, label="Contact person",
        widget=forms.TextInput(attrs={"placeholder": "Name at the site"}),
    )
    phone = forms.CharField(max_length=10, required=False, widget=PHONE)
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional"}))
```

`apps/complaints/selectors.py`:
```python
"""All reads for the complaints screens. Views call these; no queries in templates."""

from django.db.models import Count, Max, Prefetch

from .models import Complaint, ComplaintEvent, Site, Status


def age_days(c, today):
    """Days since the complaint was reported, until it was closed."""
    return ((c.closed_on or today) - c.reported_on).days


def awaiting_days(c, today):
    """Days spent in Awaiting material (the paused clock), summed from the events in date order."""
    total, since = 0, None
    for ev in c.events.all():
        if since is not None and ev.to_status != Status.AWAITING_MATERIAL:
            total += (ev.at - since).days
            since = None
        if ev.to_status == Status.AWAITING_MATERIAL and since is None:
            since = ev.at
    if since is not None:
        total += ((c.closed_on or today) - since).days
    return total


def complaint_qs():
    """Complaints with what a list row or the detail page shows (site, company, technicians, events, visits)."""
    return (
        Complaint.objects.select_related("site", "company")
        .prefetch_related("technicians", Prefetch("events", queryset=ComplaintEvent.objects.select_related("by")))
        .annotate(n_visits=Count("visits", distinct=True), last_visit=Max("visits__visit_date"))
    )


def site_option(site):
    """What the site picker needs for one site."""
    return {"id": site.pk, "name": site.name, "city": site.city, "contact": site.contact_name, "phone": site.phone}


def site_options():
    return [site_option(s) for s in Site.objects.filter(is_active=True)]


def cities():
    return list(Site.objects.order_by("city").values_list("city", flat=True).distinct())
```

`apps/complaints/templatetags/complaint_tags.py`:
```python
from django import template
from django.utils.html import format_html

from apps.core.templatetags.core_tags import st_badge

from ..models import Priority, Status

register = template.Library()

# Red = needs attention, amber = waiting on someone, green = done well, slate = neutral / finished.
STATUS_STYLE = {
    Status.NOT_ATTENDED: ("st-alert", "alert-circle"),
    Status.ATTENDED: ("st-neutral", "tool"),
    Status.MATERIAL_CHECK: ("st-neutral", "zoom-question"),
    Status.AWAITING_MATERIAL: ("st-wait", "hourglass"),
    Status.RESOLVED: ("st-ok", "circle-check"),
    Status.CLOSED: ("st-done", "lock"),
    Status.NOT_COVERED: ("st-done", "ban"),
}


@register.filter
def status_badge(status):
    css, icon = STATUS_STYLE[status]
    return st_badge(css, icon, Status(status).label)


@register.filter
def status_css(status):
    return STATUS_STYLE[status][0]


@register.filter
def status_icon(status):
    return STATUS_STYLE[status][1]


@register.filter
def priority_badge(priority):
    if priority == Priority.URGENT:
        return st_badge("st-alert", "urgent", "Urgent")
    if priority == Priority.HIGH:
        return st_badge("st-wait", "arrow-up", "High")
    return format_html('<span class="text-secondary">{}</span>', "Normal")


@register.simple_tag
def age_badge(days, is_open):
    """'12 d', or a red badge when an open complaint is older than 15 days."""
    if is_open and days > 15:
        return format_html('<span class="badge st st-alert">{} d</span>', days)
    return f"{days} d"
```

- [ ] **Step 4: Views and URLs**

`apps/complaints/views.py`:
```python
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN, OFFICE, has_role
from apps.core.tokens import EXPIRED, already_saved, is_issued, new_token, spend_token

from . import selectors, services
from .forms import ComplaintForm, SiteForm
from .models import TRANSITIONS, Complaint, NotCoveredReason, Status
from .services import ComplaintError


@role_required(OFFICE)
def complaint_new(request):
    initial = {"reported_on": timezone.localdate()}
    if request.GET.get("site", "").isdecimal():
        initial["site"] = request.GET["site"]
    form = ComplaintForm(request.POST or None, initial=initial)
    error, token = None, ""
    if request.method == "POST":
        token = request.POST.get("entry_token", "")
        done = already_saved(request.session, token)
        if done:
            messages.warning(request, "This complaint was already saved.")
            return redirect("complaint_detail", number=done)
        if not is_issued(request.session, token):
            token, error = "", EXPIRED
        elif form.is_valid():
            data = form.cleaned_data
            try:
                c = services.file_complaint(
                    site=data["site"],
                    company=data["company"],
                    fault=data["fault"],
                    reported_on=data["reported_on"],
                    user=request.user,
                    company_ref=data["company_ref"],
                    qty_affected=data["qty_affected"],
                    priority=data["priority"],
                    technicians=data["technicians"],
                    contact_name=data["contact_name"] or None,  # blank: use the site's
                    phone=data["phone"] or None,
                )
            except ComplaintError as exc:
                error = exc.message
            else:
                spend_token(request.session, token, c.number)
                messages.success(request, f"Complaint {c.number} filed for {c.site.name}.")
                return redirect("complaint_detail", number=c.number)
        else:
            error = form.first_error()
    return render(
        request,
        "complaints/form.html",
        {
            "form": form,
            "error": error,
            "token": token or new_token(request.session),
            "site_form": SiteForm(prefix="ns"),
            "sites_data": selectors.site_options(),
            "cities": selectors.cities(),
        },
    )


@role_required(OFFICE)
@require_POST
def site_quick_create(request):
    """The New site modal: save a site and return it as JSON for the picker."""
    form = SiteForm(request.POST, prefix="ns")
    if not form.is_valid():
        return JsonResponse({"ok": False, "error": form.first_error()})
    try:
        site = services.save_site(data=form.cleaned_data)
    except ComplaintError as exc:
        return JsonResponse({"ok": False, "error": exc.message})
    return JsonResponse({"ok": True, "site": selectors.site_option(site)})


@role_required(OFFICE)
def complaint_detail(request, number):
    c = get_object_or_404(selectors.complaint_qs(), number=number)
    today = timezone.localdate()
    visits = (
        c.visits.select_related("out_entry")
        .prefetch_related("technicians", "pieces__item", "out_entry__lines__item")
        .order_by("-visit_date", "-id")
    )
    return render(
        request,
        "complaints/detail.html",
        {
            "c": c,
            "age": selectors.age_days(c, today),
            "awaiting": selectors.awaiting_days(c, today),
            "events": list(reversed(c.events.all())),
            "visits": visits,
            "next_statuses": [(s, Status(s).label) for s in TRANSITIONS[c.status] if s != Status.NOT_COVERED],
            "reasons": NotCoveredReason.choices,
            "can_reopen": c.status == Status.CLOSED and has_role(request.user, ADMIN),
        },
    )


@role_required(OFFICE)
@require_POST
def complaint_status(request, number):
    c = get_object_or_404(Complaint, number=number)
    before = c.get_status_display()
    try:
        c = services.change_status(
            complaint=c, to=request.POST.get("to", ""), user=request.user, note=request.POST.get("note", "")
        )
    except ComplaintError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, f"{c.number}: {before} → {c.get_status_display()}.")
    return redirect("complaint_detail", number=number)


@role_required(OFFICE)
@require_POST
def complaint_not_covered(request, number):
    c = get_object_or_404(Complaint, number=number)
    try:
        c = services.close_not_covered(
            complaint=c, reason=request.POST.get("reason", ""), user=request.user, note=request.POST.get("note", "")
        )
    except ComplaintError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, f"{c.number} closed as Not covered ({c.get_not_covered_reason_display()}).")
    return redirect("complaint_detail", number=number)
```

`apps/complaints/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path("complaints/new/", views.complaint_new, name="complaint_new"),
    path("complaints/<str:number>/", views.complaint_detail, name="complaint_detail"),
    path("complaints/<str:number>/status/", views.complaint_status, name="complaint_status"),
    path("complaints/<str:number>/not-covered/", views.complaint_not_covered, name="complaint_not_covered"),
    path("sites/quick-create/", views.site_quick_create, name="site_quick_create"),
]
```

`config/urls.py`: add `path("", include("apps.complaints.urls")),` after the defectives include.

`apps/inventory/context_processors.py`: insert directly before the Defectives section
```python
    ("Complaints", [("complaint_new", "New complaint", "plus", "", False)]),
```
and add `"complaint_detail": "complaints"` to `ACTIVE_ALIASES`.

- [ ] **Step 5: Templates and the site picker**

`templates/complaints/_site_modal.html`:
```html
{# New site dialog. Needs `site_form` (SiteForm, prefix "ns") and `cities`. Saved through site_quick_create by site-picker.js. #}
<div class="modal modal-blur fade" id="site-modal" tabindex="-1" aria-labelledby="site-title" aria-hidden="true"><div class="modal-dialog modal-lg modal-dialog-centered"><div class="modal-content">
  <form id="site-form" data-url="{% url 'site_quick_create' %}" novalidate>{% csrf_token %}
    <div class="modal-header"><h5 class="modal-title" id="site-title"><i class="ti ti-building"></i> New site</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
    <div class="modal-body"><div class="row g-3">
      <div class="col-12 col-md-8"><label class="form-label required" for="{{ site_form.name.id_for_label }}">Site name</label>{{ site_form.name }}</div>
      <div class="col-12 col-md-4"><label class="form-label required" for="{{ site_form.city.id_for_label }}">City</label>{{ site_form.city }}<datalist id="site-cities">{% for city in cities %}<option value="{{ city }}">{% endfor %}</datalist></div>
      <div class="col-12 col-md-6"><label class="form-label" for="{{ site_form.contact_name.id_for_label }}">Contact person</label>{{ site_form.contact_name }}</div>
      <div class="col-12 col-md-6"><label class="form-label" for="{{ site_form.phone.id_for_label }}">Phone</label>{{ site_form.phone }}</div>
      <div class="col-12"><label class="form-label" for="{{ site_form.address.id_for_label }}">Address</label>{{ site_form.address }}</div>
    </div><div id="ns-err" class="text-danger mt-3" aria-live="polite"></div></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button><button type="submit" class="btn btn-primary ms-auto"><i class="ti ti-check"></i> Save site</button></div>
  </form></div></div></div>
```

`templates/complaints/form.html`:
```html
{% extends "base.html" %}{% load static %}
{% block title %}New complaint{% endblock %}
{% block pretitle %}Complaints{% endblock %}
{% block page_title %}<i class="ti ti-message-report"></i> New complaint{% endblock %}
{% block content %}
<form method="post" novalidate id="complaint-form" data-once>{% csrf_token %}<input type="hidden" name="entry_token" value="{{ token }}">
  <div class="card mb-3"><div class="card-header"><h3 class="card-title"><i class="ti ti-building"></i> Site</h3><div class="card-subtitle ms-2 text-secondary">Where the problem is</div></div>
    <div class="card-body"><div class="row g-3">
      <div class="col-12 col-md-6"><label class="form-label required" for="id_site">Site</label>{{ form.site }}<small class="form-hint">Type to search saved sites, or add a new one.</small></div>
      <div class="col-6 col-md-3"><label class="form-label" for="id_contact_name">Contact person</label>{{ form.contact_name }}</div>
      <div class="col-6 col-md-3"><label class="form-label" for="id_phone">Phone</label>{{ form.phone }}</div>
      <div class="col-12"><button type="button" class="btn btn-quiet btn-sm" id="new-site-btn"><i class="ti ti-plus"></i> New site</button>
        <span class="small text-secondary ms-2">Contact and phone are copied from the site; change them here for this complaint only.</span></div>
    </div></div></div>
  <div class="card mb-3"><div class="card-header"><h3 class="card-title"><i class="ti ti-file-description"></i> Complaint</h3></div>
    <div class="card-body"><div class="row g-3">
      <div class="col-12 col-md-4"><label class="form-label required" for="id_company">Company (whose product failed)</label>{{ form.company }}<small class="form-hint">Only a starting value. Change it for other companies' products.</small></div>
      <div class="col-12 col-md-4"><label class="form-label" for="id_company_ref">Company complaint no.</label>{{ form.company_ref }}</div>
      <div class="col-6 col-md-2"><label class="form-label required" for="id_reported_on">Reported on</label>{{ form.reported_on }}</div>
      <div class="col-6 col-md-2"><label class="form-label" for="id_qty_affected">Qty affected</label>{{ form.qty_affected }}</div>
      <div class="col-12"><label class="form-label required" for="id_fault">Fault</label>{{ form.fault }}</div>
      <div class="col-12 col-md-5"><label class="form-label required">Priority</label><div class="form-selectgroup">{% for value, label in form.priority.field.choices %}<label class="form-selectgroup-item"><input type="radio" name="priority" value="{{ value }}" class="form-selectgroup-input"{% if form.priority.value == value %} checked{% endif %}><span class="form-selectgroup-label"><i class="ti ti-{% if value == 'URGENT' %}urgent{% elif value == 'HIGH' %}arrow-up{% else %}minus{% endif %}"></i> {{ label }}</span></label>{% endfor %}</div></div>
      <div class="col-12 col-md-7"><label class="form-label" for="id_technicians">Technicians</label>{{ form.technicians }}</div>
    </div></div>
    <div class="card-footer d-flex flex-wrap align-items-center gap-2"><span class="text-secondary small"><i class="ti ti-info-circle"></i> Saved as <b>Not attended</b>. Every status change is logged.</span>
      <div class="ms-auto btn-list"><a href="{{ nav_urls.complaints|default:'/' }}" class="btn btn-link link-secondary">Cancel</a><button type="submit" class="btn btn-primary"><i class="ti ti-device-floppy"></i> Save complaint</button></div></div></div>
  <div id="form-error" class="mt-3" tabindex="-1" aria-live="polite">{% if error %}<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>{{ error }}</div></div></div>{% endif %}</div>
</form>
{% include "complaints/_site_modal.html" %}
{{ sites_data|json_script:"sites-data" }}
{% endblock %}
{% block scripts %}<script src="{% static 'js/service.js' %}"></script><script src="{% static 'js/site-picker.js' %}"></script>{% endblock %}
```

`templates/complaints/detail.html`:
```html
{% extends "base.html" %}{% load static complaint_tags %}
{% block title %}{{ c.number }}{% endblock %}
{% block pretitle %}Complaint · {{ c.company.name }}{% endblock %}
{% block page_title %}<span class="code">{{ c.number }}</span> {{ c.status|status_badge }}{% endblock %}
{% block actions %}
  {% if c.status != "NOT_COVERED" %}<button type="button" class="btn btn-quiet" data-bs-toggle="modal" data-bs-target="#status-modal"><i class="ti ti-arrows-right-left"></i> Change status</button>{% endif %}
  {% if c.is_open %}<button type="button" class="btn btn-quiet" data-bs-toggle="modal" data-bs-target="#nc-modal"><i class="ti ti-ban"></i> Close as Not covered</button>{% endif %}
{% endblock %}
{% block content %}
<div class="row row-cards">
  <div class="col-12"><div class="d-flex flex-wrap gap-2">
    <span class="chip"><i class="ti ti-calendar"></i> Reported {{ c.reported_on|date }}</span>
    <span class="chip{% if c.is_open and age > 15 %} chip-alert{% endif %}"><i class="ti ti-clock"></i> Age <b>{{ age }}</b> days{% if c.closed_on %} (closed {{ c.closed_on|date }}){% endif %}</span>
    <span class="chip{% if c.status == 'AWAITING_MATERIAL' %} chip-wait{% endif %}"><i class="ti ti-hourglass"></i> Awaiting material <b>{{ awaiting }}</b> days</span>
    {% if c.priority != "NORMAL" %}{{ c.priority|priority_badge }}{% endif %}
    {% if c.not_covered_reason %}<span class="chip"><i class="ti ti-ban"></i> Not covered: <b>{{ c.get_not_covered_reason_display }}</b></span>{% endif %}
  </div></div>
  <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Details</h3></div><div class="card-body"><div class="datagrid">
    <div class="datagrid-item"><div class="datagrid-title">Site</div><div class="datagrid-content">{{ c.site.name }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">City</div><div class="datagrid-content">{{ c.site.city }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Contact</div><div class="datagrid-content">{{ c.contact_name|default:"—" }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Phone</div><div class="datagrid-content">{% if c.phone %}<a href="tel:{{ c.phone }}">{{ c.phone }}</a>{% else %}—{% endif %}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Company</div><div class="datagrid-content">{{ c.company.name }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Company complaint no.</div><div class="datagrid-content">{% if c.company_ref %}<span class="code">{{ c.company_ref }}</span>{% else %}—{% endif %}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Qty affected</div><div class="datagrid-content">{{ c.qty_affected|default:"—" }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Priority</div><div class="datagrid-content">{{ c.get_priority_display }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Technicians</div><div class="datagrid-content">{{ c.technicians.all|join:", "|default:"Not assigned" }}</div></div>
  </div><div class="mt-3"><div class="datagrid-title">Fault</div><div>{{ c.fault|linebreaksbr }}</div></div></div></div></div>
  <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-timeline"></i> Status timeline</h3></div>
    <div class="card-body"><ul class="tl">{% for ev in events %}<li class="tl-item"><span class="tl-dot {{ ev.to_status|status_css }}"><i class="ti ti-{{ ev.to_status|status_icon }}"></i></span>
      <div class="tl-body"><div class="fw-medium">{% if ev.from_status %}{{ ev.get_from_status_display }} → {% endif %}{{ ev.get_to_status_display }}</div>
        <div class="small text-secondary">{{ ev.at|date }} · {{ ev.by.first_name|default:ev.by.username }}</div>
        {% if ev.reason %}<div class="small">Reason: <b>{{ ev.get_reason_display }}</b></div>{% endif %}{% if ev.note %}<div class="small">{{ ev.note }}</div>{% endif %}</div></li>{% endfor %}</ul></div></div></div>
  <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-clipboard-list"></i> Visits</h3><span class="badge bg-secondary-lt ms-2">{{ visits|length }}</span></div>
    <div class="table-responsive"><table class="table table-vcenter card-table">
      <thead><tr><th>Visit</th><th>Technicians</th><th>Work done</th><th>Parts given</th><th>Failed parts collected</th><th>Status after</th></tr></thead>
      <tbody>{% for v in visits %}<tr>
        <td><span class="code">{{ v.number }}</span><div class="small text-secondary nowrap">{{ v.visit_date|date }}</div></td>
        <td>{{ v.technicians.all|join:", " }}</td><td class="cell-wrap">{{ v.work_done }}</td>
        <td>{% if v.out_entry %}<a class="code" href="{% url 'entry_detail' v.out_entry.number %}">{{ v.out_entry.number }}</a>{% if v.out_entry.is_undone %} <span class="badge bg-secondary-lt">undone</span>{% endif %}
          <div class="small">{% for line in v.out_entry.lines.all %}<span class="code">{{ line.item.code }}</span> × {{ line.qty|stringformat:"d"|slice:"1:" }}{% if not forloop.last %}<br>{% endif %}{% endfor %}</div>{% else %}<span class="text-secondary">None</span>{% endif %}</td>
        <td>{% for p in v.pieces.all %}<span class="nowrap"><a class="code" href="{% url 'piece_detail' p.tag %}">{{ p.tag }}</a> <span class="small text-secondary">{{ p.item.code }}</span></span>{% if not forloop.last %}<br>{% endif %}{% empty %}<span class="text-secondary">None</span>{% endfor %}</td>
        <td>{{ v.next_status|status_badge }}</td></tr>
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No visits yet.</td></tr>{% endfor %}</tbody>
    </table></div></div></div>
</div>
{% if c.status != "NOT_COVERED" %}
<div class="modal modal-blur fade" id="status-modal" tabindex="-1" aria-labelledby="status-title" aria-hidden="true"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
  <form method="post" action="{% url 'complaint_status' c.number %}" data-once>{% csrf_token %}
  {% if c.status == "CLOSED" %}
    <div class="modal-header"><h5 class="modal-title" id="status-title"><i class="ti ti-lock"></i> {{ c.number }} is Closed</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
    <div class="modal-body"><p class="text-secondary">A closed complaint is final. Only Admin can reopen it; reopening moves it back to <b>Attended</b> and is logged.</p>
      {% if can_reopen %}<input type="hidden" name="to" value="ATTENDED"><label class="form-label required" for="st-note">Why is it being reopened?</label><textarea id="st-note" name="note" class="form-control" rows="2" maxlength="280"></textarea>{% endif %}</div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button>
      {% if can_reopen %}<button type="submit" class="btn btn-outline-danger ms-auto"><i class="ti ti-arrow-back-up"></i> Reopen (move to Attended)</button>{% endif %}</div>
  {% else %}
    <div class="modal-header"><h5 class="modal-title" id="status-title"><i class="ti ti-arrows-right-left"></i> Change status of {{ c.number }}</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
    <div class="modal-body"><div class="mb-2 text-secondary">Now: {{ c.status|status_badge }}. Only the moves allowed from here are offered.</div>
      <div class="form-selectgroup form-selectgroup-boxes d-flex flex-column gap-2">{% for value, label in next_statuses %}<label class="form-selectgroup-item flex-fill"><input type="radio" name="to" value="{{ value }}" class="form-selectgroup-input"{% if forloop.first %} checked{% endif %}><div class="form-selectgroup-label d-flex align-items-center p-2"><span class="form-selectgroup-check me-2"></span>{{ value|status_badge }}</div></label>{% endfor %}</div>
      <label class="form-label mt-3" for="st-note">Note</label><textarea id="st-note" name="note" class="form-control" rows="2" maxlength="300" placeholder="Optional: what happened"></textarea></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button><button type="submit" class="btn btn-primary ms-auto"><i class="ti ti-check"></i> Change status</button></div>
  {% endif %}
  </form></div></div></div>
{% endif %}
{% if c.is_open %}
<div class="modal modal-blur fade" id="nc-modal" tabindex="-1" aria-labelledby="nc-title" aria-hidden="true"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
  <form method="post" action="{% url 'complaint_not_covered' c.number %}" data-once>{% csrf_token %}
    <div class="modal-header"><h5 class="modal-title" id="nc-title"><i class="ti ti-ban"></i> Close {{ c.number }} as Not covered</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
    <div class="modal-body"><p class="text-secondary">Use this when the job is not ours to do. It can be done from any open status and is logged.</p>
      <label class="form-label required" for="nc-reason">Reason</label><select id="nc-reason" name="reason" class="form-select"><option value="">Choose…</option>{% for value, label in reasons %}<option value="{{ value }}">{{ label }}</option>{% endfor %}</select>
      <label class="form-label mt-3" for="nc-note">Note</label><textarea id="nc-note" name="note" class="form-control" rows="2" maxlength="300" placeholder="Required when the reason is Other"></textarea></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" data-bs-dismiss="modal">Cancel</button><button type="submit" class="btn btn-danger ms-auto"><i class="ti ti-ban"></i> Close as Not covered</button></div>
  </form></div></div></div>
{% endif %}
{% endblock %}
{% block scripts %}<script src="{% static 'js/service.js' %}"></script>{% endblock %}
```

`templates/defectives/_source.html` becomes:
```html
{# Where a piece came from. Needs `p`, a DefectivePiece from selectors.pieces_qs(). #}
{% if p.visit %}<a class="code" href="{% url 'complaint_detail' p.visit.complaint.number %}">{{ p.visit.complaint.number }}</a><div class="small text-secondary">{{ p.visit.complaint.site.name }}</div>{% elif p.source == "SITE_VISIT" %}<span><i class="ti ti-map-pin text-secondary"></i> Site visit</span>{% else %}<span class="text-secondary"><i class="ti ti-building-warehouse"></i> Stock</span>{% endif %}
```

`static/js/site-picker.js`:
```js
/* Site picker on the New complaint page (searchable, fills contact + phone, "＋ New site" opens the modal) and the
   New site modal itself (also used on the Sites page, where a saved site reloads the page). The modal posts to
   site_quick_create and gets the new site back as JSON. */
(function () {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const BS = window.bootstrap || (window.tabler && window.tabler.bootstrap);
  const modalEl = document.getElementById("site-modal"), siteForm = document.getElementById("site-form");
  if (!modalEl || !siteForm) return;
  const errBox = document.getElementById("ns-err");
  const select = document.getElementById("id_site");
  const dataEl = document.getElementById("sites-data");
  const sites = new Map(dataEl ? JSON.parse(dataEl.textContent).map(s => [String(s.id), s]) : []);
  const option = s => ({ value: String(s.id), name: s.name, city: s.city, contact: s.contact, hay: `${s.name} ${s.city} ${s.contact}` });
  let pending = null, picker = null;

  function openModal(name) {
    siteForm.reset();
    document.getElementById("id_ns-name").value = name || "";
    errBox.textContent = "";
    BS.Modal.getOrCreateInstance(modalEl).show();
  }
  modalEl.addEventListener("shown.bs.modal", () => {
    document.getElementById(document.getElementById("id_ns-name").value ? "id_ns-city" : "id_ns-name").focus();
  });
  modalEl.addEventListener("hidden.bs.modal", () => { if (pending) { pending(false); pending = null; } });
  const newButton = document.getElementById("new-site-btn");
  if (newButton) newButton.addEventListener("click", () => { pending = null; openModal(""); });

  if (select) {
    const contact = document.getElementById("id_contact_name"), phone = document.getElementById("id_phone");
    const chosen = select.value;
    select.innerHTML = '<option value=""></option>'; // options come from sites-data (with city and contact)
    picker = new TomSelect(select, {
      options: [...sites.values()].map(option), items: chosen ? [chosen] : [], valueField: "value", labelField: "name",
      searchField: ["hay"], maxOptions: 50, closeAfterSelect: true, placeholder: "Type site name, city or contact…",
      create: (input, done) => { pending = done; openModal(input); },
      render: {
        option: d => `<div><span class="fw-medium">${esc(d.name)}</span><span class="opt-meta">${esc(d.city)}${d.contact ? " · " + esc(d.contact) : ""}</span></div>`,
        item: d => `<div>${esc(d.name)}, ${esc(d.city)}</div>`,
        option_create: d => `<div class="create">＋ New site <b>${esc(d.input)}</b>…</div>`,
        no_results: () => `<div class="no-results">No saved site. Keep typing to add it.</div>`,
      },
      onChange: v => { const s = sites.get(String(v)); if (s) { contact.value = s.contact; phone.value = s.phone; } },
    });
  }

  siteForm.addEventListener("submit", async e => {
    e.preventDefault();
    const button = siteForm.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const r = await fetch(siteForm.dataset.url, { method: "POST", body: new FormData(siteForm), headers: { Accept: "application/json" } });
      const res = await r.json();
      if (!res.ok) { errBox.textContent = res.error; return; }
      if (!picker) { location.reload(); return; } // Sites page: show the new row
      sites.set(String(res.site.id), res.site);
      const done = pending; pending = null;
      BS.Modal.getInstance(modalEl).hide();
      if (done) done(option(res.site)); else picker.addOption(option(res.site));
      picker.setValue(String(res.site.id));
    } catch (err) {
      errBox.textContent = "Could not save the site. Check the connection and try again.";
    } finally {
      button.disabled = false;
    }
  });
})();
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Check it in a browser**

Open `/complaints/new/`: type a new site name in the Site box, pick "＋ New site …", save the modal (the site is selected and its contact fills in), choose Havells, set High priority and two technicians, save. On the complaint page open "Change status" (only allowed moves are offered) and "Close as Not covered" (reason required). Expected: no console errors.

- [ ] **Step 8: Commit**

```bash
git add apps/complaints config/urls.py apps/inventory/context_processors.py templates/complaints templates/defectives/_source.html static/js/site-picker.js tests/complaints/test_complaint_views.py
git commit -m "feat(complaints): new complaint with site picker and New site modal; complaint page with timeline"
```

---

### Task 13: Record visit page

**Files:**
- Modify: `apps/complaints/forms.py` (`VisitForm`), `apps/complaints/views.py` (`visit_new`, `_visit_lines`), `apps/complaints/urls.py`
- Modify: `apps/inventory/context_processors.py` (`ACTIVE_ALIASES`)
- Create: `templates/complaints/visit.html`; Modify: `templates/complaints/detail.html` (Record visit buttons)
- Test: `tests/complaints/test_visit_view.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/complaints/test_visit_view.py`:
```python
import pytest
from django.utils import timezone

from apps.complaints.models import NotCoveredReason, Visit
from apps.complaints.services import close_not_covered
from apps.defectives.models import DefectivePiece
from tests.factories import give_stock, loc, make_complaint, make_item, make_tech

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def url(c):
    return f"/complaints/{c.number}/visit/"


def submit(client, c, data):
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


@pytest.fixture
def setup(office_user):
    drv = make_item("LG78-150-700")
    give_stock(drv, 5, office_user)  # IN-0001
    return drv, make_tech("Ramu"), make_complaint(office_user)


def test_visit_page(office_client, setup):
    drv, tech, c = setup
    html = office_client.get(url(c)).content.decode()
    assert 'data-lines="part"' in html and 'data-lines="col"' in html and 'data-mode="collect"' in html
    assert "The first visit also logs" in html and "Material need to check" in html
    assert "Defective store</option>" not in html


def test_record_a_visit_with_parts_and_two_failed_pieces(office_client, setup):
    drv, tech, c = setup
    data = visit_data(
        tech,
        part_item=[str(drv.pk)],
        part_qty=["1"],
        col_item=[str(drv.pk)],
        col_qty=["2"],
        col_batch=["B2405"],
        col_pkd=["2026-03"],
        col_fault=["no output"],
    )
    r = submit(office_client, c, data)
    assert r.status_code == 302 and r.url == f"/complaints/{c.number}/"
    html = office_client.get(r.url).content.decode()
    assert "Visit VIS-0001 saved. Parts given: OUT-0001. New defective tags: DEF-0001, DEF-0002." in html
    assert "Material need to check" in html and 'href="/defectives/pieces/DEF-0002/"' in html
    assert DefectivePiece.objects.filter(visit__complaint=c).count() == 2


def test_over_issue_is_refused_and_keeps_the_lines(office_client, setup):
    drv, tech, c = setup
    html = submit(office_client, c, visit_data(tech, part_item=[str(drv.pk)], part_qty=["9"])).content.decode()
    assert "Parts given: Only 5 NOS of LG78-150-700 at Vizag Office. Nothing was saved." in html
    assert f'"item": "{drv.pk}", "qty": "9"' in html and not Visit.objects.exists()


def test_a_bad_collected_line_names_its_table(office_client, setup):
    drv, tech, c = setup
    data = visit_data(tech, col_item=[""], col_qty=["2"], col_batch=[""], col_pkd=[""], col_fault=["x"])
    html = submit(office_client, c, data).content.decode()
    assert "Failed parts collected: Line 1: choose an item. Nothing was saved." in html


def test_a_visit_needs_a_technician(office_client, setup):
    drv, tech, c = setup
    html = submit(office_client, c, visit_data(tech, technicians=[])).content.decode()
    assert "Choose who attended." in html and not Visit.objects.exists()


def test_no_visit_page_for_a_finished_complaint(office_client, office_user, setup):
    drv, tech, c = setup
    close_not_covered(complaint=c, reason=NotCoveredReason.CANCELLED, user=office_user)
    r = office_client.get(url(c))
    assert r.status_code == 302 and r.url == f"/complaints/{c.number}/"
    assert url(c) not in office_client.get(r.url).content.decode()


def test_record_visit_button_while_open(office_client, setup):
    drv, tech, c = setup
    assert f'href="{url(c)}"' in office_client.get(f"/complaints/{c.number}/").content.decode()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/complaints/test_visit_view.py -q`
Expected: FAIL (404 on `/complaints/CMP-0001/visit/`).

- [ ] **Step 3: Form, view, URL**

Append to `apps/complaints/forms.py` (imports gain `from apps.inventory.models import Location`, `from .models import Status` and `from .services import visit_next_options`):
```python
class VisitForm(TablerFormMixin, forms.Form):
    """The visit header. The two item tables (parts given, failed parts collected) are parsed separately."""

    visit_date = forms.DateField(label="Visit date", widget=DATE, error_messages={"required": "Choose the visit date."})
    technicians = forms.ModelMultipleChoiceField(
        Technician.objects.filter(is_active=True),
        label="Technicians who attended",
        widget=forms.SelectMultiple(attrs={"data-ts": ""}),
        error_messages={"required": "Choose who attended."},
    )
    work_done = forms.CharField(
        label="Work done",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. Changed 2 drivers, 4 fittings still to check"}),
        error_messages={"required": "Write what work was done."},
    )
    location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True), empty_label=None, label="From location"
    )
    next_status = forms.ChoiceField(label="Status after this visit", widget=forms.RadioSelect)

    def __init__(self, *args, complaint, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["next_status"].choices = [(s, Status(s).label) for s in visit_next_options(complaint)]
        self.fields["visit_date"].widget.attrs.update(
            min=complaint.reported_on.isoformat(), max=timezone.localdate().isoformat()
        )
```

In `apps/complaints/views.py` add the imports
```python
from apps.defectives.services import DefectiveError
from apps.inventory import selectors as stock
from apps.inventory.entry_lines import parse_lines, raw_lines
from apps.inventory.services import StockError
```
(and `VisitForm` from `.forms`), then append:
```python
def _visit_lines(raw_parts, raw_collected):
    """(parts, collected) as ParsedLines. A problem names its table: 'Parts given: Line 2: …'."""
    try:
        parts = parse_lines(raw_parts, "out", allow_empty=True)
    except StockError as exc:
        raise ComplaintError(f"Parts given: {exc.message}") from exc
    try:
        collected = parse_lines(raw_collected, "collect", allow_empty=True)
    except StockError as exc:
        raise ComplaintError(f"Failed parts collected: {exc.message}") from exc
    return parts, collected


@role_required(OFFICE)
def visit_new(request, number):
    """Record a visit: work done, parts given (Stock OUT), failed parts collected (tagged pieces), next status."""
    complaint = get_object_or_404(Complaint.objects.select_related("site", "company"), number=number)
    if not complaint.is_open:
        messages.warning(request, f"{complaint.number} is {complaint.get_status_display()}, so visits can't be added.")
        return redirect("complaint_detail", number=number)
    first = complaint.status == Status.NOT_ATTENDED
    initial = {
        "visit_date": timezone.localdate(),
        "location": stock.default_location(),
        "technicians": [t.pk for t in complaint.technicians.filter(is_active=True)],
        "next_status": Status.ATTENDED if first else complaint.status,
    }
    form = VisitForm(request.POST or None, initial=initial, complaint=complaint)
    error, token, raw_parts, raw_collected = None, "", [], []
    if request.method == "POST":
        raw_parts, raw_collected = raw_lines(request.POST, "part"), raw_lines(request.POST, "col")
        token = request.POST.get("entry_token", "")
        if already_saved(request.session, token):
            messages.warning(request, "This visit was already saved.")
            return redirect("complaint_detail", number=number)
        if not is_issued(request.session, token):
            token, error = "", EXPIRED
        elif form.is_valid():
            data = form.cleaned_data
            try:
                parts, collected = _visit_lines(raw_parts, raw_collected)
                visit = services.record_visit(
                    complaint=complaint,
                    visit_date=data["visit_date"],
                    technicians=list(data["technicians"]),
                    work_done=data["work_done"],
                    next_status=data["next_status"],
                    user=request.user,
                    location=data["location"],
                    parts=[(p.item, p.qty) for p in parts],
                    collected=[(p.item, p.qty, p.batch, p.pkd, p.fault) for p in collected],
                )
            except (ComplaintError, StockError, DefectiveError) as exc:
                error = f"{exc.message} Nothing was saved."
            else:
                spend_token(request.session, token, visit.number)
                text = f"Visit {visit.number} saved."
                if visit.out_entry:
                    text += f" Parts given: {visit.out_entry.number}."
                tags = list(visit.pieces.order_by("tag").values_list("tag", flat=True))
                if tags:
                    text += f" New defective tags: {', '.join(tags)}."
                messages.success(request, text)
                return redirect("complaint_detail", number=number)
        else:
            error = form.first_error()
    items, balances = stock.picker_data()
    return render(
        request,
        "complaints/visit.html",
        {
            "c": complaint,
            "form": form,
            "first": first,
            "error": error,
            "token": token or new_token(request.session),
            "items_data": items,
            "balances_data": balances,
            "initial_parts": raw_parts,
            "initial_collected": raw_collected,
        },
    )
```

`apps/complaints/urls.py`: add `path("complaints/<str:number>/visit/", views.visit_new, name="visit_new"),` after the `complaint_detail` line.

`apps/inventory/context_processors.py`: add `"visit_new": "complaints"` to `ACTIVE_ALIASES`.

- [ ] **Step 4: Templates**

`templates/complaints/visit.html`:
```html
{% extends "base.html" %}{% load static complaint_tags %}
{% block title %}Record visit · {{ c.number }}{% endblock %}
{% block pretitle %}Complaint {{ c.number }} · {{ c.site.name }}, {{ c.site.city }}{% endblock %}
{% block page_title %}<i class="ti ti-clipboard-plus"></i> Record visit{% endblock %}
{% block content %}
<form method="post" novalidate data-lines-form>{% csrf_token %}<input type="hidden" name="entry_token" value="{{ token }}">
  <div class="card mb-3"><div class="card-body py-2 d-flex flex-wrap align-items-center gap-2">{{ c.status|status_badge }}<span class="fw-medium">{{ c.fault }}</span><span class="text-secondary">· {{ c.company.name }} · reported {{ c.reported_on|date }}</span></div></div>
  <div class="card mb-3"><div class="card-header"><h3 class="card-title"><i class="ti ti-calendar-event"></i> Visit</h3></div><div class="card-body"><div class="row g-3">
    <div class="col-12 col-md-3"><label class="form-label required" for="id_visit_date">Visit date</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-calendar"></i></span>{{ form.visit_date }}</div></div>
    <div class="col-12 col-md-9"><label class="form-label required" for="id_technicians">Technicians who attended</label>{{ form.technicians }}</div>
    <div class="col-12"><label class="form-label required" for="id_work_done">Work done</label>{{ form.work_done }}</div>
  </div></div></div>
  <div class="card mb-3"><div class="card-header flex-wrap gap-2"><h3 class="card-title"><i class="ti ti-package-export"></i> Parts given</h3><div class="card-subtitle ms-2 text-secondary">Posts a Stock OUT from the location. Leave empty if no parts were given.</div></div>
    <div class="card-body"><div class="row g-3 mb-3"><div class="col-12 col-md-3"><label class="form-label" for="id_location">From location</label>{{ form.location }}</div></div>
      <div data-lines="part" data-mode="out" data-loc="id_location" data-initial="initial-parts" data-summary="parts-summary" data-add-label="Add another part"></div></div>
    <div class="card-footer text-secondary" id="parts-summary"></div></div>
  <div class="card mb-3"><div class="card-header flex-wrap gap-2"><h3 class="card-title"><i class="ti ti-recycle"></i> Failed parts collected</h3><div class="card-subtitle ms-2 text-secondary">Each piece gets its own tag (quantity 3 = 3 tags) and goes to the Defective store, not good stock.</div></div>
    <div class="card-body"><div data-lines="col" data-mode="collect" data-initial="initial-collected" data-summary="collect-summary" data-add-label="Add another failed part"></div></div>
    <div class="card-footer text-secondary" id="collect-summary"></div></div>
  <div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-flag"></i> Status after this visit</h3></div>
    <div class="card-body"><div class="form-selectgroup">{% for value, label in form.next_status.field.choices %}<label class="form-selectgroup-item"><input type="radio" name="next_status" value="{{ value }}" class="form-selectgroup-input"{% if form.next_status.value == value %} checked{% endif %}><span class="form-selectgroup-label"><i class="ti ti-{{ value|status_icon }}"></i> {{ label }}</span></label>{% endfor %}</div>
      {% if first %}<div class="form-hint mt-2">The first visit also logs Not attended → Attended.</div>{% endif %}</div>
    <div class="card-footer d-flex"><div class="ms-auto btn-list"><a href="{% url 'complaint_detail' c.number %}" class="btn btn-link link-secondary">Cancel</a><button type="submit" class="btn btn-primary"><i class="ti ti-device-floppy"></i> Save visit</button></div></div></div>
  <div id="form-error" class="mt-3" tabindex="-1" aria-live="polite">{% if error %}<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>{{ error }}</div></div></div>{% endif %}</div>
</form>
{{ items_data|json_script:"items-data" }}{{ balances_data|json_script:"balances-data" }}{{ initial_parts|json_script:"initial-parts" }}{{ initial_collected|json_script:"initial-collected" }}
{% endblock %}
{% block scripts %}<script src="{% static 'js/service.js' %}"></script><script src="{% static 'js/line-editor.js' %}"></script>{% endblock %}
```

`templates/complaints/detail.html`:
- At the start of `{% block actions %}` add:
```html
  {% if c.is_open %}<a href="{% url 'visit_new' c.number %}" class="btn btn-primary"><i class="ti ti-clipboard-plus"></i> Record visit</a>{% endif %}
```
- In the Visits card header, after `<span class="badge bg-secondary-lt ms-2">{{ visits|length }}</span>`, add:
```html
{% if c.is_open %}<div class="card-actions"><a href="{% url 'visit_new' c.number %}" class="btn btn-sm btn-outline-primary"><i class="ti ti-plus"></i> Record visit</a></div>{% endif %}
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Check it in a browser**

Record a visit on an open complaint: give 1 part from Vizag Office (the Available column follows the location; typing more than available turns the box red and Save is refused), collect 2 failed parts with batch, PKD and fault, set "Awaiting material", save. Expected: back on the complaint with the success message naming the OUT entry and the two new tags, the timeline showing Not attended → Attended → Awaiting material, and no console errors.

- [ ] **Step 7: Commit**

```bash
git add apps/complaints apps/inventory/context_processors.py templates/complaints tests/complaints/test_visit_view.py
git commit -m "feat(complaints): record visit (parts given, failed parts collected, next status) in one save"
```

---

### Task 14: Complaints list, dashboard and the two Excel downloads

**Files:**
- Create: `apps/complaints/filters.py`, `apps/complaints/exports.py`
- Modify: `apps/complaints/selectors.py` (`age_bucket`, `in_tab`, `complaint_row`, `complaint_rows`, `dashboard`), `apps/complaints/views.py` (`complaints_dashboard`, `complaint_list`), `apps/complaints/urls.py`
- Modify: `apps/inventory/context_processors.py` (menu entries)
- Create: `templates/complaints/list.html`, `templates/complaints/dashboard.html`, `templates/complaints/_bars.html`
- Test: `tests/complaints/test_list_dashboard.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/complaints/test_list_dashboard.py`:
```python
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
TODAY = timezone.localdate()
LIST = "/complaints/list/"


def ago(days):
    return TODAY - timedelta(days=days)


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
    return re.findall(r'href="/complaints/(CMP-\d{4})/"', client.get(LIST + query).content.decode())


def test_age_and_days_awaiting_material(office_user):
    c = make_complaint(office_user, reported_on=ago(20))
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=ago(18))
    change_status(complaint=c, to=Status.AWAITING_MATERIAL, user=office_user, at=ago(15))
    change_status(complaint=c, to=Status.ATTENDED, user=office_user, at=ago(10))  # 5 days waiting
    change_status(complaint=c, to=Status.AWAITING_MATERIAL, user=office_user, at=ago(4))  # still waiting: +4
    found = selectors.complaint_qs().get(pk=c.pk)
    assert (selectors.age_days(found, TODAY), selectors.awaiting_days(found, TODAY)) == (20, 9)
    change_status(complaint=c, to=Status.RESOLVED, user=office_user, at=ago(2))  # +2, then the clock stops
    change_status(complaint=c, to=Status.CLOSED, user=office_user, at=ago(2))
    found = selectors.complaint_qs().get(pk=c.pk)
    assert (selectors.age_days(found, TODAY), selectors.awaiting_days(found, TODAY)) == (18, 7)


@pytest.mark.parametrize("days, bucket", [(0, "0-2"), (2, "0-2"), (3, "3-7"), (8, "8-15"), (15, "8-15"), (16, "15+")])
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


def test_tab_counts(several):
    _, tabs = selectors.complaint_rows(complaint_filters(QueryDict("")), TODAY)
    counts = {key: n for key, _, n in tabs}
    assert (counts["open"], counts["NOT_ATTENDED"], counts["NOT_COVERED"], counts["all"]) == (2, 2, 1, 3)


def test_an_old_open_complaint_shows_a_red_age(office_client, several):
    assert '<span class="badge st st-alert">20 d</span>' in office_client.get(LIST).content.decode()


def test_dashboard(office_client, several):
    d = selectors.dashboard(TODAY)
    assert (d["counts"]["NOT_ATTENDED"], d["closed_30"], d["open"]) == (2, 1, 2)
    assert [(a["key"], a["n"]) for a in d["ages"]] == [("0-2", 1), ("3-7", 0), ("8-15", 0), ("15+", 1)]
    assert [r["c"].number for r in d["oldest"]] == ["CMP-0001", "CMP-0002"]
    assert {r["label"]: r["n"] for r in d["companies"]} == {"Wipro Lighting": 1, "Havells": 1}
    assert [(r["label"], r["n"]) for r in d["cities"]] == [("Visakhapatnam", 2)]
    html = office_client.get("/complaints/").content.decode()
    assert "Complaints dashboard" in html and "Oldest open complaints" in html
    assert f'href="{LIST}?tab=NOT_ATTENDED"' in html


def test_pending_export_lists_open_complaints_oldest_first(office_client, several):
    ws = sheet(office_client.get("/complaints/pending/export/"))
    assert [ws.cell(r, 1).value for r in range(7, ws.max_row + 1)] == ["CMP-0001", "CMP-0002"]
    headers = [c.value for c in ws[6]]
    age = ws.cell(7, headers.index("Age (days)") + 1)
    assert age.value == 20 and age.fill.fgColor.rgb.endswith("FDE2E2")
    assert ws.cell(7, headers.index("Company complaint no.") + 1).value == "WL/AP/24990"


def test_complaint_list_export_uses_the_filters(office_client, several):
    ws = sheet(office_client.get("/complaints/export/?tab=all"))
    headers = [c.value for c in ws[6]]
    assert headers[-3:] == ["Closed on", "Not covered reason", "Visits"]
    reasons = {ws.cell(r, 1).value: ws.cell(r, len(headers) - 1).value for r in range(7, ws.max_row + 1)}
    assert set(reasons) == {"CMP-0001", "CMP-0002", "CMP-0003"} and reasons["CMP-0003"] == "Not our product"


def test_export_buttons_keep_the_filters(office_client, several):
    assert 'href="/complaints/export/?tab=all"' in office_client.get(LIST + "?tab=all").content.decode()
    assert 'href="/complaints/pending/export/"' in office_client.get("/complaints/").content.decode()


def test_nav_links_complaints(office_client):
    html = office_client.get("/").content.decode()
    assert 'href="/complaints/"' in html and f'href="{LIST}"' in html
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/complaints/test_list_dashboard.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.complaints.filters'`.

- [ ] **Step 3: Filters and selectors**

`apps/complaints/filters.py`:
```python
"""Parse the complaints list's GET params once; the list, the dashboard links and the Excel exports share them."""

from dataclasses import dataclass

from apps.inventory.filters import _obj, _text
from apps.inventory.models import Company

from .models import OPEN_STATUSES, Status, Technician

TABS = ["open", *OPEN_STATUSES, Status.CLOSED, Status.NOT_COVERED, "all"]
TAB_LABELS = {"open": "Open", **{s: Status(s).label for s in Status.values}, "all": "All"}
# (key, label, from days, to days or None)
AGE_BUCKETS = [("0-2", "0–2 days", 0, 2), ("3-7", "3–7 days", 3, 7), ("8-15", "8–15 days", 8, 15), ("15+", "Over 15 days", 16, None)]


@dataclass
class ComplaintFilters:
    tab: str
    company: Company | None
    city: str
    technician: Technician | None
    age: str  # an AGE_BUCKETS key, or ""
    q: str


def complaint_filters(params):
    tab, age = params.get("tab", "open"), params.get("age", "")
    return ComplaintFilters(
        tab if tab in TABS else "open",
        _obj(Company, params.get("company")),
        _text(params.get("city")),
        _obj(Technician, params.get("technician")),
        age if age in {key for key, *_ in AGE_BUCKETS} else "",
        _text(params.get("q")),
    )
```

Append to `apps/complaints/selectors.py` (imports gain `from collections import Counter`, `from datetime import timedelta`, `from django.db.models import Q`, `from .filters import AGE_BUCKETS, TAB_LABELS, TABS` and `OPEN_STATUSES` from `.models`):
```python
def age_bucket(days):
    for key, _, low, high in AGE_BUCKETS:
        if days >= low and (high is None or days <= high):
            return key
    return AGE_BUCKETS[0][0]


def in_tab(c, tab):
    if tab == "all":
        return True
    if tab == "open":
        return c.status in OPEN_STATUSES
    return c.status == tab


def complaint_row(c, today):
    return {
        "c": c,
        "age": age_days(c, today),
        "awaiting": awaiting_days(c, today),
        "techs": ", ".join(t.name for t in c.technicians.all()),
    }


def complaint_rows(f, today):
    """(rows, tabs). Rows match every filter; tabs are [(key, label, count)] counted before the tab filter."""
    complaints = complaint_qs()
    if f.company:
        complaints = complaints.filter(company=f.company)
    if f.city:
        complaints = complaints.filter(site__city__iexact=f.city)
    if f.technician:
        complaints = complaints.filter(technicians=f.technician)
    if f.q:
        complaints = complaints.filter(
            Q(number__icontains=f.q)
            | Q(company_ref__icontains=f.q)
            | Q(site__name__icontains=f.q)
            | Q(fault__icontains=f.q)
        )
    rows = [complaint_row(c, today) for c in complaints]
    if f.age:
        rows = [r for r in rows if age_bucket(r["age"]) == f.age]
    tabs = [(key, TAB_LABELS[key], sum(1 for r in rows if in_tab(r["c"], key))) for key in TABS]
    return [r for r in rows if in_tab(r["c"], f.tab)], tabs


def dashboard(today):
    counts = dict(Complaint.objects.values_list("status").annotate(n=Count("id")))
    open_rows = [complaint_row(c, today) for c in complaint_qs().filter(status__in=OPEN_STATUSES)]
    closed_30 = Complaint.objects.filter(
        status__in=[Status.CLOSED, Status.NOT_COVERED], closed_on__gt=today - timedelta(days=30)
    ).count()
    ages = [
        {"key": key, "label": label, "n": sum(1 for r in open_rows if age_bucket(r["age"]) == key), "alert": key == "15+"}
        for key, label, _, _ in AGE_BUCKETS
    ]
    companies = Counter((r["c"].company_id, r["c"].company.name) for r in open_rows)
    cities = Counter(r["c"].site.city for r in open_rows)
    return {
        "counts": {s: counts.get(s, 0) for s in Status.values},
        "open": len(open_rows),
        "closed_30": closed_30,
        "ages": ages,
        "ages_top": max([a["n"] for a in ages] + [1]),
        "oldest": sorted(open_rows, key=lambda r: -r["age"])[:6],
        "companies": [{"id": cid, "label": name, "n": n} for (cid, name), n in companies.most_common()],
        "companies_top": max(list(companies.values()) + [1]),
        "cities": [{"label": city, "n": n} for city, n in cities.most_common()],
        "cities_top": max(list(cities.values()) + [1]),
    }
```

- [ ] **Step 4: Views, exports, URLs, menu**

Append to `apps/complaints/views.py` (imports gain `from urllib.parse import urlencode`, `from django.urls import reverse`, `from apps.core.tables import sort_and_page`, `from apps.inventory.models import Company`, `from .filters import AGE_BUCKETS, complaint_filters`, and `Priority`, `Technician` from `.models`):
```python
@role_required(OFFICE)
def complaints_dashboard(request):
    d = selectors.dashboard(timezone.localdate())
    base = reverse("complaints")
    for row in d["ages"]:
        row["href"] = f"{base}?{urlencode({'age': row['key']})}"
    for row in d["companies"]:
        row["href"] = f"{base}?company={row['id']}"
    for row in d["cities"]:
        row["href"] = f"{base}?{urlencode({'city': row['label']})}"
    n = d["counts"]
    tiles = [
        {"n": n[Status.NOT_ATTENDED], "label": "Not attended", "icon": "alert-circle", "sub": "",
         "css": "kpi-alert" if n[Status.NOT_ATTENDED] else "kpi-brand", "href": f"{base}?tab=NOT_ATTENDED"},
        {"n": n[Status.ATTENDED], "label": "Attended", "icon": "tool", "sub": "", "css": "kpi-brand",
         "href": f"{base}?tab=ATTENDED"},
        {"n": n[Status.MATERIAL_CHECK], "label": "Material need to check", "icon": "zoom-question", "sub": "",
         "css": "kpi-brand", "href": f"{base}?tab=MATERIAL_CHECK"},
        {"n": n[Status.AWAITING_MATERIAL], "label": "Awaiting material", "icon": "hourglass", "sub": "",
         "css": "kpi-wait" if n[Status.AWAITING_MATERIAL] else "kpi-brand", "href": f"{base}?tab=AWAITING_MATERIAL"},
        {"n": n[Status.RESOLVED], "label": "Resolved", "icon": "circle-check", "sub": "to be closed",
         "css": "kpi-brand", "href": f"{base}?tab=RESOLVED"},
        {"n": d["closed_30"], "label": "Closed / not covered", "icon": "lock", "sub": "last 30 days",
         "css": "kpi-brand", "href": f"{base}?tab=CLOSED"},
    ]
    return render(request, "complaints/dashboard.html", {"d": d, "tiles": tiles})


@role_required(OFFICE)
def complaint_list(request):
    f = complaint_filters(request.GET)
    rows, tabs = selectors.complaint_rows(f, timezone.localdate())
    statuses, priorities = list(Status.values), list(Priority.values)
    sorters = {
        "no": lambda r: r["c"].number,
        "reported": lambda r: (r["c"].reported_on, r["c"].number),
        "site": lambda r: r["c"].site.name,
        "company": lambda r: r["c"].company.name,
        "techs": lambda r: r["techs"],
        "priority": lambda r: priorities.index(r["c"].priority),
        "status": lambda r: statuses.index(r["c"].status),
        "age": lambda r: r["age"],
    }
    table = sort_and_page(request, rows, sorters, "reported", "desc")
    return render(
        request,
        "complaints/list.html",
        {
            "f": f,
            "table": table,
            "tabs": tabs,
            "companies": Company.objects.filter(is_active=True),
            "cities": selectors.cities(),
            "technicians": Technician.objects.all(),
            "ages": AGE_BUCKETS,
        },
    )
```

`apps/complaints/exports.py`:
```python
"""Excel downloads for complaints, in the same layout as the stock exports."""

from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.core.excel import Column, workbook_response

from . import selectors
from .filters import AGE_BUCKETS, TAB_LABELS, complaint_filters

COLUMNS = [
    Column("Complaint no.", "code"),
    Column("Reported on", "date"),
    Column("Site", width=26),
    Column("City"),
    Column("Contact"),
    Column("Phone", "code"),
    Column("Company"),
    Column("Company complaint no.", "code"),
    Column("Fault", width=40),
    Column("Qty affected", "int"),
    Column("Technicians"),
    Column("Priority"),
    Column("Status"),
    Column("Age (days)", "int"),
    Column("Days awaiting material", "int"),
    Column("Last visit", "date"),
]
AGE_COLUMN = 13  # highlighted red when an open complaint is older than 15 days


def _who(request):
    return request.user.first_name or request.user.username


def _describe(f, *first):
    ages = {key: label for key, label, _, _ in AGE_BUCKETS}
    parts = [
        *first,
        f.company.name if f.company else "all companies",
        f.city or "all cities",
        f.technician.name if f.technician else "",
        f"age {ages[f.age]}" if f.age else "",
        f'search "{f.q}"' if f.q else "",
    ]
    return " · ".join(p for p in parts if p)


def _cells(row):
    c = row["c"]
    return [
        c.number,
        c.reported_on,
        c.site.name,
        c.site.city,
        c.contact_name,
        c.phone,
        c.company.name,
        c.company_ref,
        c.fault,
        c.qty_affected,
        row["techs"],
        c.get_priority_display(),
        c.get_status_display(),
        row["age"],
        row["awaiting"],
        c.last_visit,
    ]


@role_required(OFFICE)
def pending_complaints_xlsx(request):
    """Every open complaint (the list's other filters apply), oldest first; red age = open more than 15 days."""
    f = complaint_filters(request.GET)
    f.tab = "open"
    rows, _ = selectors.complaint_rows(f, timezone.localdate())
    rows.sort(key=lambda r: (r["c"].reported_on, r["c"].number))
    filters = _describe(f, "Open complaints (Not attended, Attended, Material need to check, Awaiting material, Resolved)")
    late = {n for n, r in enumerate(rows) if r["age"] > 15}
    return workbook_response(
        "Pending_Complaints", "Pending Complaints", filters, _who(request), COLUMNS, [_cells(r) for r in rows], late, AGE_COLUMN
    )


@role_required(OFFICE)
def complaints_xlsx(request):
    """The complaint list with its current filters (all pages), newest first."""
    f = complaint_filters(request.GET)
    rows, _ = selectors.complaint_rows(f, timezone.localdate())
    rows.sort(key=lambda r: (r["c"].reported_on, r["c"].number), reverse=True)
    cols = [*COLUMNS, Column("Closed on", "date"), Column("Not covered reason"), Column("Visits", "int")]
    data = [
        _cells(r) + [r["c"].closed_on, r["c"].get_not_covered_reason_display(), r["c"].n_visits] for r in rows
    ]
    return workbook_response(
        "Complaint_List", "Complaint List", _describe(f, TAB_LABELS[f.tab]), _who(request), cols, data
    )
```

`apps/complaints/urls.py`: add `from . import exports, views` and put these four lines **first** in `urlpatterns` (before `complaints/<str:number>/`):
```python
    path("complaints/", views.complaints_dashboard, name="complaints_dashboard"),
    path("complaints/list/", views.complaint_list, name="complaints"),
    path("complaints/export/", exports.complaints_xlsx, name="complaints_xlsx"),
    path("complaints/pending/export/", exports.pending_complaints_xlsx, name="pending_complaints_xlsx"),
```

`apps/inventory/context_processors.py`, Complaints section becomes:
```python
    (
        "Complaints",
        [
            ("complaints_dashboard", "Dashboard", "message-report", "", False),
            ("complaints", "All complaints", "list-details", "", False),
            ("complaint_new", "New complaint", "plus", "", False),
        ],
    ),
```

- [ ] **Step 5: Templates**

`templates/complaints/_bars.html`:
```html
{# Bar list: one hue, value labels, red only when the row needs attention. Needs `rows` [{label, n, href, alert}] and `top`. #}
<div class="list-group list-group-flush">{% for r in rows %}<a class="list-group-item list-group-item-action py-2" href="{{ r.href }}">
  <div class="d-flex align-items-center gap-2 mb-1"><span class="{% if r.alert %}text-danger fw-medium{% endif %}">{% if r.alert %}<i class="ti ti-alert-triangle me-1"></i>{% endif %}{{ r.label }}</span><span class="ms-auto fw-bold num">{{ r.n }}</span></div>
  <div class="progress progress-sm"><div class="progress-bar {% if r.alert %}bg-red{% else %}bar-brand{% endif %}" style="width:{% widthratio r.n top 100 %}%"></div></div></a>
{% empty %}<div class="list-group-item text-secondary">Nothing open.</div>{% endfor %}</div>
```

`templates/complaints/dashboard.html`:
```html
{% extends "base.html" %}{% load complaint_tags %}
{% block title %}Complaints dashboard{% endblock %}
{% block pretitle %}Complaints{% endblock %}
{% block page_title %}Complaints dashboard{% endblock %}
{% block actions %}<a href="{% url 'complaint_new' %}" class="btn btn-primary"><i class="ti ti-plus"></i> New complaint</a>
  <a href="{% url 'pending_complaints_xlsx' %}" class="btn btn-outline-primary"><i class="ti ti-file-spreadsheet"></i> Pending complaints</a>{% endblock %}
{% block content %}
<div class="row row-deck row-cards">
  {% for t in tiles %}<div class="col-6 col-md-4 col-xl-2"><a class="card card-sm card-link h-100" href="{{ t.href }}"><div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar {{ t.css }}"><i class="ti ti-{{ t.icon }}"></i></span>
    <div><div class="fw-medium fs-2 lh-1">{{ t.n }}</div><div class="text-secondary small mt-1">{{ t.label }}</div>{% if t.sub %}<div class="small text-secondary">{{ t.sub }}</div>{% endif %}</div></div></div></a></div>{% endfor %}
  <div class="col-lg-4"><div class="card"><div class="card-header"><div><h3 class="card-title">Open complaints by age</h3><div class="card-subtitle">{{ d.open }} open · days since reported</div></div></div>
    {% include "complaints/_bars.html" with rows=d.ages top=d.ages_top %}</div></div>
  <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Oldest open complaints</h3>
    <div class="card-actions"><a href="{% url 'complaints' %}" class="btn btn-sm btn-outline-primary">All open <i class="ti ti-arrow-right"></i></a></div></div>
    <div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Complaint</th><th>Site</th><th>Company</th><th>Status</th><th class="num">Age</th></tr></thead>
      <tbody>{% for r in d.oldest %}<tr><td><a class="code" href="{% url 'complaint_detail' r.c.number %}">{{ r.c.number }}</a></td><td>{{ r.c.site.name }}<div class="small text-secondary">{{ r.c.site.city }}</div></td>
        <td>{{ r.c.company.name }}</td><td>{{ r.c.status|status_badge }}</td><td class="num">{% age_badge r.age r.c.is_open %}</td></tr>
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">Nothing open.</td></tr>{% endfor %}</tbody></table></div></div></div>
  <div class="col-md-6"><div class="card"><div class="card-header"><h3 class="card-title">Open by company</h3></div>{% include "complaints/_bars.html" with rows=d.companies top=d.companies_top %}</div></div>
  <div class="col-md-6"><div class="card"><div class="card-header"><h3 class="card-title">Open by city</h3></div>{% include "complaints/_bars.html" with rows=d.cities top=d.cities_top %}</div></div>
</div>
{% endblock %}
```

`templates/complaints/list.html`:
```html
{% extends "base.html" %}{% load core_tags complaint_tags %}
{% block title %}Complaints{% endblock %}
{% block pretitle %}Complaints{% endblock %}
{% block page_title %}All complaints{% endblock %}
{% block actions %}<a href="{% url 'complaint_new' %}" class="btn btn-primary"><i class="ti ti-plus"></i> New complaint</a>
  <a href="{% export_url 'complaints_xlsx' %}" class="btn btn-outline-primary"><i class="ti ti-file-spreadsheet"></i> Export to Excel</a>{% endblock %}
{% block content %}
<div class="card">
  <div class="card-header pb-0 border-0"><ul class="nav nav-tabs card-header-tabs status-tabs mb-0">{% for key, label, n in tabs %}
    <li class="nav-item"><a href="{% url_with tab=key page=None %}" class="nav-link{% if f.tab == key %} active{% endif %}">{{ label }} <span class="badge {% if f.tab == key %}bg-primary text-white{% else %}bg-secondary-lt{% endif %} ms-1">{{ n }}</span></a></li>{% endfor %}</ul></div>
  <div class="card-body border-bottom py-3"><form method="get" class="row g-2 align-items-end"><input type="hidden" name="tab" value="{{ f.tab }}">
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="cf-co">Company</label><select id="cf-co" name="company" class="form-select" onchange="this.form.submit()"><option value="">All companies</option>
      {% for c in companies %}<option value="{{ c.pk }}" {% if f.company == c %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="cf-city">City</label><select id="cf-city" name="city" class="form-select" onchange="this.form.submit()"><option value="">All cities</option>
      {% for city in cities %}<option value="{{ city }}" {% if f.city|lower == city|lower %}selected{% endif %}>{{ city }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="cf-tech">Technician</label><select id="cf-tech" name="technician" class="form-select" onchange="this.form.submit()"><option value="">Anyone</option>
      {% for t in technicians %}<option value="{{ t.pk }}" {% if f.technician == t %}selected{% endif %}>{{ t.name }}</option>{% endfor %}</select></div>
    <div class="col-12 col-sm-6 col-lg-2"><label class="form-label small text-secondary mb-1" for="cf-age">Age</label><select id="cf-age" name="age" class="form-select" onchange="this.form.submit()"><option value="">Any age</option>
      {% for key, label, low, high in ages %}<option value="{{ key }}" {% if f.age == key %}selected{% endif %}>{{ label }}</option>{% endfor %}</select></div>
    <div class="col-12 col-lg-4"><label class="form-label small text-secondary mb-1" for="cf-q">Search</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>
      <input id="cf-q" type="search" name="q" value="{{ f.q }}" class="form-control" placeholder="Complaint no., company ref, site, fault"></div></div>
  </form></div>
  <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
    <thead><tr>{% sort_th "no" "Complaint" %}{% sort_th "reported" "Reported" %}{% sort_th "site" "Site" %}{% sort_th "company" "Company" %}<th>Fault</th>{% sort_th "techs" "Technicians" %}{% sort_th "priority" "Priority" %}{% sort_th "status" "Status" %}{% sort_th "age" "Age" True %}</tr></thead>
    <tbody>{% for r in table.page %}<tr>
      <td><a class="code" href="{% url 'complaint_detail' r.c.number %}">{{ r.c.number }}</a></td><td class="nowrap">{{ r.c.reported_on|date }}</td>
      <td>{{ r.c.site.name }}<div class="small text-secondary">{{ r.c.site.city }}</div></td>
      <td>{{ r.c.company.name }}{% if r.c.company_ref %}<div class="small text-secondary code">{{ r.c.company_ref }}</div>{% endif %}</td>
      <td class="cell-wrap">{{ r.c.fault }}{% if r.c.qty_affected %} <span class="text-secondary">({{ r.c.qty_affected }})</span>{% endif %}</td>
      <td>{{ r.techs|default:"Not assigned" }}</td><td>{{ r.c.priority|priority_badge }}</td><td>{{ r.c.status|status_badge }}</td><td class="num">{% age_badge r.age r.c.is_open %}</td></tr>
    {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No complaints match these filters.</td></tr>{% endfor %}</tbody>
  </table></div>
  {% include "core/_pagination.html" %}
</div>
<p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> Age = days since the complaint was reported (until it was closed). Red = open for more than 15 days.</p>
{% endblock %}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/complaints apps/inventory/context_processors.py templates/complaints tests/complaints/test_list_dashboard.py
git commit -m "feat(complaints): list with status tabs and filters, dashboard, pending and complaint list downloads"
```

---

### Task 15: Sites and technicians screens

**Files:**
- Modify: `apps/complaints/forms.py` (`TechnicianForm`), `apps/complaints/selectors.py` (`site_rows`, `technician_rows`), `apps/complaints/views.py` (sites, site card, edit, hide; technicians, edit, hide), `apps/complaints/urls.py`
- Modify: `apps/inventory/context_processors.py` (menu entries, active aliases), `tests/test_permissions.py` (`ADMIN_ONLY`)
- Create: `templates/complaints/sites.html`, `templates/complaints/site_detail.html`, `templates/complaints/site_form.html`, `templates/complaints/technicians.html`, `templates/complaints/technician_form.html`
- Modify: `templates/complaints/detail.html`, `templates/complaints/list.html`, `templates/complaints/dashboard.html` (link the site)
- Test: `tests/complaints/test_sites_techs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/complaints/test_sites_techs.py`:
```python
import pytest
from django.utils import timezone

from apps.complaints import selectors
from apps.complaints.models import Technician
from tests.factories import make_complaint, make_site, make_tech

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def test_sites_list_and_search(office_client, office_user):
    make_complaint(office_user)  # at BARC, Visakhapatnam
    make_site("NSL Textiles", "Guntur", contact_name="Jagadeesh")
    html = office_client.get("/sites/").content.decode()
    assert "BARC" in html and "NSL Textiles" in html and 'id="site-modal"' in html
    html = office_client.get("/sites/?q=jagadeesh").content.decode()
    assert "NSL Textiles" in html and "BARC" not in html
    assert "BARC" not in office_client.get("/sites/?city=Guntur").content.decode()


def test_site_rows_count_open_complaints(office_user):
    make_complaint(office_user)
    [row] = selectors.site_rows()
    assert (row.n_open, row.n_all, row.last) == (1, 1, TODAY)


def test_site_card_shows_its_complaint_history(office_client, office_user):
    c = make_complaint(office_user)
    html = office_client.get(f"/sites/{c.site.pk}/").content.decode()
    assert f'href="/complaints/{c.number}/"' in html and f'href="/complaints/new/?site={c.site.pk}"' in html


def test_edit_site(office_client):
    site = make_site()
    data = {"name": "BARC", "city": "Visakhapatnam", "contact_name": "Chenna Keshavulu", "phone": "9849669594", "address": ""}
    r = office_client.post(f"/sites/{site.pk}/edit/", data)
    assert r.url == f"/sites/{site.pk}/"
    site.refresh_from_db()
    assert site.contact_name == "Chenna Keshavulu"
    html = office_client.post(f"/sites/{site.pk}/edit/", {**data, "phone": "123"}).content.decode()
    assert "Phone must be a 10-digit mobile number." in html


def test_only_admin_hides_sites_and_technicians(office_client, admin_client):
    site, tech = make_site(), make_tech()
    assert office_client.post(f"/sites/{site.pk}/toggle/").status_code == 403
    admin_client.post(f"/sites/{site.pk}/toggle/")
    site.refresh_from_db()
    assert not site.is_active
    assert office_client.post(f"/technicians/{tech.pk}/toggle/").status_code == 403
    admin_client.post(f"/technicians/{tech.pk}/toggle/")
    tech.refresh_from_db()
    assert not tech.is_active
    html = office_client.get("/complaints/new/").content.decode()
    assert "BARC" not in html and "Ramu" not in html  # hidden ones are not offered


def test_add_and_edit_technicians(office_client):
    html = office_client.post("/technicians/", {"name": "Suresh", "phone": "9876543210"}, follow=True).content.decode()
    assert "Technician Suresh added." in html
    html = office_client.post("/technicians/", {"name": "suresh"}, follow=True).content.decode()
    assert "Suresh is already in the list." in html
    t = Technician.objects.get(name="Suresh")
    office_client.post(f"/technicians/{t.pk}/edit/", {"name": "Suresh K", "phone": ""})
    t.refresh_from_db()
    assert (t.name, t.phone) == ("Suresh K", "")


def test_technician_rows_and_links(office_client, office_user):
    ramu = make_tech("Ramu")
    make_complaint(office_user, technicians=[ramu])
    [row] = selectors.technician_rows(TODAY)
    assert (row.n_open, row.n_visits) == (1, 0)
    assert f'href="/complaints/list/?technician={ramu.pk}"' in office_client.get("/technicians/").content.decode()


def test_complaint_pages_link_the_site(office_client, office_user):
    c = make_complaint(office_user)
    assert f'href="/sites/{c.site.pk}/"' in office_client.get(f"/complaints/{c.number}/").content.decode()
    assert f'href="/sites/{c.site.pk}/"' in office_client.get("/complaints/list/").content.decode()


def test_nav_links_sites_and_technicians(office_client):
    html = office_client.get("/").content.decode()
    assert 'href="/sites/"' in html and 'href="/technicians/"' in html
```

In `tests/test_permissions.py`, change `ADMIN_ONLY` to:
```python
ADMIN_ONLY = {"masters", "masters_toggle", "site_toggle", "technician_toggle"}
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/complaints/test_sites_techs.py -q`
Expected: FAIL (404 on `/sites/`).

- [ ] **Step 3: Form and selectors**

Append to `apps/complaints/forms.py`:
```python
class TechnicianForm(TablerFormMixin, forms.Form):
    name = forms.CharField(
        max_length=60, error_messages={"required": "Enter the name of the technician."},
        widget=forms.TextInput(attrs={"placeholder": "e.g. Suresh"}),
    )
    phone = forms.CharField(max_length=10, required=False, widget=PHONE)
```

Append to `apps/complaints/selectors.py` (`Technician` joins the `.models` import):
```python
def site_rows(q="", city=""):
    """Sites with their open and total complaint counts and the last reported date."""
    sites = Site.objects.annotate(
        n_open=Count("complaints", filter=Q(complaints__status__in=OPEN_STATUSES)),
        n_all=Count("complaints"),
        last=Max("complaints__reported_on"),
    )
    if city:
        sites = sites.filter(city__iexact=city)
    if q:
        sites = sites.filter(
            Q(name__icontains=q) | Q(city__icontains=q) | Q(contact_name__icontains=q) | Q(phone__icontains=q)
        )
    return list(sites)


def technician_rows(today):
    """Technicians with open complaints assigned, visits in the last 30 days, and the last visit date."""
    return list(
        Technician.objects.annotate(
            n_open=Count("complaints", filter=Q(complaints__status__in=OPEN_STATUSES), distinct=True),
            n_visits=Count("visits", filter=Q(visits__visit_date__gt=today - timedelta(days=30)), distinct=True),
            last=Max("visits__visit_date"),
        )
    )
```

- [ ] **Step 4: Views and URLs**

Append to `apps/complaints/views.py` (imports gain `from apps.inventory.filters import _text`, `TechnicianForm` from `.forms` and `Site` from `.models`):
```python
@role_required(OFFICE)
def sites(request):
    q, city = _text(request.GET.get("q")), _text(request.GET.get("city"))  # _text drops NUL bytes
    rows = selectors.site_rows(q, city)
    sorters = {
        "name": lambda s: s.name,
        "city": lambda s: s.city,
        "contact": lambda s: s.contact_name,
        "open": lambda s: s.n_open,
        "total": lambda s: s.n_all,
        "last": lambda s: s.last,
    }
    table = sort_and_page(request, rows, sorters, "name")
    return render(
        request,
        "complaints/sites.html",
        {"table": table, "q": q, "city": city, "cities": selectors.cities(), "site_form": SiteForm(prefix="ns")},
    )


@role_required(OFFICE)
def site_detail(request, pk):
    site = get_object_or_404(Site, pk=pk)
    today = timezone.localdate()
    rows = [selectors.complaint_row(c, today) for c in selectors.complaint_qs().filter(site=site)]
    return render(
        request,
        "complaints/site_detail.html",
        {"site": site, "rows": rows, "n_open": sum(1 for r in rows if r["c"].is_open)},
    )


@role_required(OFFICE)
def site_edit(request, pk):
    site = get_object_or_404(Site, pk=pk)
    initial = {f: getattr(site, f) for f in ("name", "city", "contact_name", "phone", "address")}
    form = SiteForm(request.POST or None, initial=initial)
    error = None
    if request.method == "POST":
        if form.is_valid():
            try:
                services.save_site(site=site, data=form.cleaned_data)
            except ComplaintError as exc:
                error = exc.message
            else:
                messages.success(request, f"Site {site.name} saved.")
                return redirect("site_detail", pk=site.pk)
        else:
            error = form.first_error()
    return render(
        request, "complaints/site_form.html", {"site": site, "form": form, "error": error, "cities": selectors.cities()}
    )


@role_required(ADMIN)
@require_POST
def site_toggle(request, pk):
    site = get_object_or_404(Site, pk=pk)
    services.set_active(site, active=not site.is_active)
    messages.success(request, f"{site.name} is now {'active' if site.is_active else 'hidden from the site list'}.")
    return redirect("site_detail", pk=pk)


@role_required(OFFICE)
def technicians(request):
    form = TechnicianForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                tech = services.save_technician(**form.cleaned_data)
            except ComplaintError as exc:
                messages.error(request, exc.message)
            else:
                messages.success(request, f"Technician {tech.name} added.")
        else:
            messages.error(request, form.first_error())
        return redirect("technicians")
    rows = sorted(selectors.technician_rows(timezone.localdate()), key=lambda t: (not t.is_active, t.name))
    return render(request, "complaints/technicians.html", {"rows": rows, "form": form})


@role_required(OFFICE)
def technician_edit(request, pk):
    tech = get_object_or_404(Technician, pk=pk)
    form = TechnicianForm(request.POST or None, initial={"name": tech.name, "phone": tech.phone})
    error = None
    if request.method == "POST":
        if form.is_valid():
            try:
                services.save_technician(technician=tech, **form.cleaned_data)
            except ComplaintError as exc:
                error = exc.message
            else:
                messages.success(request, f"Technician {tech.name} saved.")
                return redirect("technicians")
        else:
            error = form.first_error()
    return render(request, "complaints/technician_form.html", {"tech": tech, "form": form, "error": error})


@role_required(ADMIN)
@require_POST
def technician_toggle(request, pk):
    tech = get_object_or_404(Technician, pk=pk)
    services.set_active(tech, active=not tech.is_active)
    messages.success(request, f"{tech.name} is now {'active' if tech.is_active else 'hidden from the lists'}.")
    return redirect("technicians")
```

`apps/complaints/urls.py`, add (keep `sites/quick-create/` before `sites/<int:pk>/`):
```python
    path("sites/", views.sites, name="sites"),
    path("sites/<int:pk>/", views.site_detail, name="site_detail"),
    path("sites/<int:pk>/edit/", views.site_edit, name="site_edit"),
    path("sites/<int:pk>/toggle/", views.site_toggle, name="site_toggle"),
    path("technicians/", views.technicians, name="technicians"),
    path("technicians/<int:pk>/edit/", views.technician_edit, name="technician_edit"),
    path("technicians/<int:pk>/toggle/", views.technician_toggle, name="technician_toggle"),
```

`apps/inventory/context_processors.py`: the Complaints section gains, after `complaint_new`,
```python
            ("sites", "Sites", "building", "", False),
            ("technicians", "Technicians", "users", "", False),
```
and `ACTIVE_ALIASES` gains `"site_detail": "sites"`, `"site_edit": "sites"`, `"technician_edit": "technicians"`.

- [ ] **Step 5: Templates**

`templates/complaints/sites.html`:
```html
{% extends "base.html" %}{% load static core_tags %}
{% block title %}Sites{% endblock %}
{% block pretitle %}Complaints{% endblock %}
{% block page_title %}Sites{% endblock %}
{% block actions %}<button type="button" class="btn btn-primary" id="new-site-btn"><i class="ti ti-plus"></i> Add site</button>{% endblock %}
{% block content %}
<div class="card"><div class="card-body border-bottom py-3"><form method="get" class="row g-2 align-items-end">
    <div class="col-12 col-lg-4"><label class="form-label small text-secondary mb-1" for="sf-q">Search</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>
      <input id="sf-q" type="search" name="q" value="{{ q }}" class="form-control" placeholder="Site, city, contact, phone"></div></div>
    <div class="col-12 col-sm-6 col-lg-3"><label class="form-label small text-secondary mb-1" for="sf-city">City</label><select id="sf-city" name="city" class="form-select" onchange="this.form.submit()"><option value="">All cities</option>
      {% for c in cities %}<option value="{{ c }}" {% if city|lower == c|lower %}selected{% endif %}>{{ c }}</option>{% endfor %}</select></div>
  </form></div>
  <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
    <thead><tr>{% sort_th "name" "Site" %}{% sort_th "city" "City" %}{% sort_th "contact" "Contact" %}<th>Phone</th>{% sort_th "open" "Open complaints" True %}{% sort_th "total" "All complaints" True %}{% sort_th "last" "Last complaint" %}</tr></thead>
    <tbody>{% for s in table.page %}<tr class="{% if not s.is_active %}text-secondary{% endif %}">
      <td><a href="{% url 'site_detail' s.pk %}" class="fw-medium">{{ s.name }}</a>{% if not s.is_active %} <span class="badge st st-done">Hidden</span>{% endif %}</td><td>{{ s.city }}</td><td>{{ s.contact_name }}</td>
      <td>{% if s.phone %}<a href="tel:{{ s.phone }}">{{ s.phone }}</a>{% endif %}</td><td class="num">{% if s.n_open %}<b>{{ s.n_open }}</b>{% else %}{{ s.n_open|qty }}{% endif %}</td><td class="num">{{ s.n_all }}</td><td class="nowrap">{{ s.last|date }}</td></tr>
    {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No sites match.</td></tr>{% endfor %}</tbody>
  </table></div>
  {% include "core/_pagination.html" %}
</div>
{% include "complaints/_site_modal.html" %}
{% endblock %}
{% block scripts %}<script src="{% static 'js/site-picker.js' %}"></script>{% endblock %}
```

`templates/complaints/site_detail.html`:
```html
{% extends "base.html" %}{% load complaint_tags %}
{% block title %}{{ site.name }}{% endblock %}
{% block pretitle %}Site · {{ site.city }}{% endblock %}
{% block page_title %}{{ site.name }}{% if not site.is_active %} <span class="badge st st-done">Hidden</span>{% endif %}{% endblock %}
{% block actions %}
  <a href="{% url 'complaint_new' %}?site={{ site.pk }}" class="btn btn-primary"><i class="ti ti-plus"></i> New complaint for this site</a>
  <a href="{% url 'site_edit' site.pk %}" class="btn btn-quiet"><i class="ti ti-edit"></i> Edit</a>
  {% if is_admin %}<form method="post" action="{% url 'site_toggle' site.pk %}">{% csrf_token %}<button class="btn btn-outline-secondary">{% if site.is_active %}<i class="ti ti-eye-off"></i> Hide{% else %}<i class="ti ti-eye"></i> Show{% endif %}</button></form>{% endif %}
{% endblock %}
{% block content %}
<div class="row row-cards">
  <div class="col-12"><div class="card"><div class="card-body"><div class="datagrid">
    <div class="datagrid-item"><div class="datagrid-title">City</div><div class="datagrid-content">{{ site.city }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Contact</div><div class="datagrid-content">{{ site.contact_name|default:"—" }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Phone</div><div class="datagrid-content">{% if site.phone %}<a href="tel:{{ site.phone }}">{{ site.phone }}</a>{% else %}—{% endif %}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Address</div><div class="datagrid-content">{{ site.address|default:"—"|linebreaksbr }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">Open complaints</div><div class="datagrid-content">{{ n_open }}</div></div>
    <div class="datagrid-item"><div class="datagrid-title">All complaints</div><div class="datagrid-content">{{ rows|length }}</div></div>
  </div></div></div></div>
  <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-history"></i> Complaint history</h3></div>
    <div class="table-responsive"><table class="table table-vcenter card-table table-striped">
      <thead><tr><th>Complaint</th><th>Reported</th><th>Company</th><th>Fault</th><th class="num">Visits</th><th>Status</th><th class="num">Age</th></tr></thead>
      <tbody>{% for r in rows %}<tr><td><a class="code" href="{% url 'complaint_detail' r.c.number %}">{{ r.c.number }}</a></td><td class="nowrap">{{ r.c.reported_on|date }}</td><td>{{ r.c.company.name }}</td>
        <td class="cell-wrap">{{ r.c.fault }}</td><td class="num">{{ r.c.n_visits }}</td><td>{{ r.c.status|status_badge }}</td><td class="num">{% age_badge r.age r.c.is_open %}</td></tr>
      {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No complaints for this site yet.</td></tr>{% endfor %}</tbody>
    </table></div></div></div>
</div>
{% endblock %}
```

`templates/complaints/site_form.html`:
```html
{% extends "base.html" %}
{% block title %}Edit {{ site.name }}{% endblock %}
{% block pretitle %}Sites{% endblock %}
{% block page_title %}<i class="ti ti-edit"></i> Edit site{% endblock %}
{% block content %}
<form method="post" novalidate class="card">{% csrf_token %}<div class="card-body"><div class="row g-3">
  <div class="col-12 col-md-8"><label class="form-label required" for="id_name">Site name</label>{{ form.name }}</div>
  <div class="col-12 col-md-4"><label class="form-label required" for="id_city">City</label>{{ form.city }}<datalist id="site-cities">{% for c in cities %}<option value="{{ c }}">{% endfor %}</datalist></div>
  <div class="col-12 col-md-6"><label class="form-label" for="id_contact_name">Contact person</label>{{ form.contact_name }}</div>
  <div class="col-12 col-md-6"><label class="form-label" for="id_phone">Phone</label>{{ form.phone }}</div>
  <div class="col-12"><label class="form-label" for="id_address">Address</label>{{ form.address }}</div>
  {% if error %}<div class="col-12"><div class="alert alert-danger mb-0" role="alert">{{ error }}</div></div>{% endif %}
</div></div>
<div class="card-footer d-flex"><div class="ms-auto btn-list"><a href="{% url 'site_detail' site.pk %}" class="btn btn-link link-secondary">Cancel</a><button type="submit" class="btn btn-primary"><i class="ti ti-device-floppy"></i> Save site</button></div></div></form>
{% endblock %}
```

`templates/complaints/technicians.html`:
```html
{% extends "base.html" %}{% load core_tags %}
{% block title %}Technicians{% endblock %}
{% block pretitle %}Complaints{% endblock %}
{% block page_title %}Technicians{% endblock %}
{% block content %}
<div class="row row-cards">
  <div class="col-lg-8"><div class="card"><div class="table-responsive"><table class="table table-vcenter card-table table-striped">
    <thead><tr><th>Technician</th><th>Phone</th><th class="num">Open complaints</th><th class="num">Visits (30 days)</th><th>Last visit</th><th>Status</th><th></th></tr></thead>
    <tbody>{% for t in rows %}<tr class="{% if not t.is_active %}text-secondary{% endif %}">
      <td><span class="avatar avatar-xs bg-secondary-lt me-2">{{ t.name|slice:":2"|upper }}</span>{{ t.name }}</td><td>{% if t.phone %}<a href="tel:{{ t.phone }}">{{ t.phone }}</a>{% endif %}</td>
      <td class="num">{% if t.n_open %}<a href="{% url 'complaints' %}?technician={{ t.pk }}" class="fw-bold">{{ t.n_open }}</a>{% else %}{{ t.n_open|qty }}{% endif %}</td>
      <td class="num">{{ t.n_visits }}</td><td class="nowrap">{{ t.last|date }}</td>
      <td>{% if t.is_active %}<span class="badge st st-ok"><i class="ti ti-check"></i>Active</span>{% else %}<span class="badge st st-done">Hidden</span>{% endif %}</td>
      <td class="text-end nowrap"><a href="{% url 'technician_edit' t.pk %}" class="btn btn-sm btn-ghost-primary"><i class="ti ti-edit"></i> Edit</a>
        {% if is_admin %}<form method="post" action="{% url 'technician_toggle' t.pk %}" class="d-inline">{% csrf_token %}<button class="btn btn-sm btn-ghost-secondary">{% if t.is_active %}Hide{% else %}Show{% endif %}</button></form>{% endif %}</td></tr>
    {% empty %}<tr><td colspan="99" class="text-center text-secondary py-4">No technicians yet.</td></tr>{% endfor %}</tbody>
  </table></div></div>
  <p class="text-secondary small mt-2"><i class="ti ti-info-circle"></i> Technicians don't log in. Office staff record their visits. Hiding a technician is Admin only.</p></div>
  <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-user-plus"></i> Add technician</h3></div>
    <form method="post" class="card-body" novalidate>{% csrf_token %}
      <label class="form-label required" for="id_name">Name</label>{{ form.name }}
      <label class="form-label mt-3" for="id_phone">Phone</label>{{ form.phone }}
      <button type="submit" class="btn btn-primary w-100 mt-3"><i class="ti ti-plus"></i> Add technician</button></form></div></div>
</div>
{% endblock %}
```

`templates/complaints/technician_form.html`:
```html
{% extends "base.html" %}
{% block title %}Edit {{ tech.name }}{% endblock %}
{% block pretitle %}Technicians{% endblock %}
{% block page_title %}<i class="ti ti-edit"></i> Edit technician{% endblock %}
{% block content %}
<form method="post" novalidate class="card" style="max-width:32rem">{% csrf_token %}<div class="card-body">
  <label class="form-label required" for="id_name">Name</label>{{ form.name }}
  <label class="form-label mt-3" for="id_phone">Phone</label>{{ form.phone }}
  {% if error %}<div class="alert alert-danger mt-3 mb-0" role="alert">{{ error }}</div>{% endif %}</div>
  <div class="card-footer d-flex"><div class="ms-auto btn-list"><a href="{% url 'technicians' %}" class="btn btn-link link-secondary">Cancel</a><button type="submit" class="btn btn-primary"><i class="ti ti-device-floppy"></i> Save</button></div></div></form>
{% endblock %}
```

Link the site from the complaint pages:
- `templates/complaints/detail.html`: the Site row becomes `<div class="datagrid-content"><a href="{% url 'site_detail' c.site.pk %}">{{ c.site.name }}</a></div>`.
- `templates/complaints/list.html`: the site cell becomes `<td><a href="{% url 'site_detail' r.c.site.pk %}">{{ r.c.site.name }}</a><div class="small text-secondary">{{ r.c.site.city }}</div></td>`.
- `templates/complaints/dashboard.html`: the oldest-complaints site cell becomes `<td><a href="{% url 'site_detail' r.c.site.pk %}">{{ r.c.site.name }}</a><div class="small text-secondary">{{ r.c.site.city }}</div></td>`.

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS, including the permission sweep with the two new Admin-only routes.

- [ ] **Step 7: Commit**

```bash
git add apps/complaints apps/inventory/context_processors.py templates/complaints tests/complaints/test_sites_techs.py tests/test_permissions.py
git commit -m "feat(complaints): sites with complaint history, technicians, Admin-only hide"
```

---

### Task 16: Integration (menu badges, global search, dashboard figures, movements and entry links, route sweep)

**Files:**
- Modify: `apps/inventory/context_processors.py` (badges), `templates/base.html`
- Modify: `apps/inventory/views.py` (`dashboard`, `entry_detail`, `global_search`), `apps/inventory/selectors.py` (`service_stats`, `entries_with_lines`, `movement_rows`), `apps/inventory/exports.py` (`movements_xlsx`)
- Modify: `templates/inventory/dashboard.html`, `templates/inventory/movements.html`, `templates/inventory/entry_detail.html`, `static/js/app.js`
- Modify: `tests/test_permissions.py`, `tests/inventory/test_search.py`, `tests/inventory/test_dashboard.py`
- Test: `tests/test_integration_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_integration_service.py`:
```python
import io

import openpyxl
import pytest
from django.utils import timezone

from apps.complaints.models import Status
from apps.complaints.services import record_visit
from apps.defectives.services import create_batch, dispatch
from apps.inventory.models import Company, StockEntry
from tests.factories import give_stock, loc, make_complaint, make_item, make_pieces, make_site, make_tech

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def visited(office_user):
    """IN-0001 stock; CMP-0001 at Laurus Labs Unit-2 (WL/AP/24871); a visit giving 1 part (OUT-0001) and
    collecting 2 failed pieces DEF-0001/0002 (IN-0002, batch code B2405)."""
    item = make_item("LG78-150-700")
    give_stock(item, 5, office_user)
    c = make_complaint(office_user, company_ref="WL/AP/24871", site=make_site("Laurus Labs Unit-2", "Visakhapatnam"))
    record_visit(
        complaint=c,
        visit_date=TODAY,
        technicians=[make_tech()],
        work_done="Changed 1 driver",
        next_status=Status.MATERIAL_CHECK,
        user=office_user,
        location=loc(),
        parts=[(item, 1)],
        collected=[(item, 2, "B2405", None, "no output")],
    )
    return c


def test_global_search_finds_complaints_refs_sites_and_tags(office_client, visited):
    found = office_client.get("/search/?q=cmp-0001").json()["complaints"]
    assert found[0]["number"] == "CMP-0001" and found[0]["url"] == "/complaints/CMP-0001/"
    assert office_client.get("/search/?q=24871").json()["complaints"][0]["number"] == "CMP-0001"
    assert office_client.get("/search/?q=laurus").json()["sites"][0]["name"] == "Laurus Labs Unit-2"
    pieces = office_client.get("/search/?q=def-1").json()["pieces"]
    assert pieces[0] == {
        "tag": "DEF-0001",
        "url": "/defectives/pieces/DEF-0001/",
        "label": "LG78-150-700 · Wipro Lighting",
        "status": "In store",
    }
    assert office_client.get("/search/?q=b2405").json()["pieces"][0]["tag"] in {"DEF-0001", "DEF-0002"}


def test_menu_badges(office_client, visited):
    html = office_client.get("/").content.decode()
    assert 'title="Open complaints">1</span>' in html and 'title="Pieces in the Defective store">2</span>' in html


def test_dashboard_shows_service_figures(office_client, visited):
    html = office_client.get("/").content.decode()
    for text in ("Open complaints", "Defective pieces in store", "Pieces with companies", "Visits this week"):
        assert text in html


def test_movements_label_and_link_service_entries(office_client, visited):
    html = office_client.get("/movements/").content.decode()
    assert "Parts given at complaint visit" in html and "Failed parts collected at site" in html
    assert 'href="/complaints/CMP-0001/"' in html and "Defective store" in html
    html = office_client.get("/movements/?q=cmp-0001").content.decode()
    assert 'href="/entries/OUT-0001/"' in html and 'href="/entries/IN-0001/"' not in html


def test_entry_pages_link_back_and_list_pieces(office_client, office_user, visited):
    html = office_client.get("/entries/IN-0002/").content.decode()
    assert 'href="/complaints/CMP-0001/"' in html and 'href="/defectives/pieces/DEF-0002/"' in html
    assert "Undo this entry" not in html
    assert "Undo this entry" in office_client.get("/entries/OUT-0001/").content.decode()  # parts given can be undone
    pieces = make_pieces(make_item("X1"), 1, office_user)
    b = create_batch(company=Company.objects.get(name="Wipro Lighting"), user=office_user, pieces=pieces)
    entry = dispatch(batch=b, dispatched_on=TODAY, courier="DTDC", docket_no="D1", user=office_user)
    html = office_client.get(f"/entries/{entry.number}/").content.decode()
    assert f'href="/defectives/batches/{b.number}/"' in html and "Docket / ref no." in html


def test_movements_export_has_complaint_and_batch_columns(office_client, visited):
    response = office_client.get("/movements/export/")
    ws = openpyxl.load_workbook(io.BytesIO(response.content)).active
    headers = [c.value for c in ws[6]]
    assert headers[-2:] == ["Complaint", "Return batch"]
    complaint_of = {ws.cell(r, 2).value: ws.cell(r, len(headers) - 1).value for r in range(7, ws.max_row + 1)}
    assert complaint_of["OUT-0001"] == "CMP-0001" and complaint_of["IN-0001"] in (None, "")


def test_store_location_is_marked_in_movements(office_client, visited):
    assert '<i class="ti ti-recycle"></i> Defective store' in office_client.get("/movements/").content.decode()


def test_parts_given_entry_is_undone_like_any_out(office_client, visited):
    r = office_client.post("/entries/OUT-0001/undo/", {"reason": "typed twice"}, follow=True)
    assert "OUT-0001 undone by REV-0001" in r.content.decode()
    assert StockEntry.objects.filter(number="REV-0001", reverses__number="OUT-0001").exists()
```

In `tests/inventory/test_search.py`, `test_short_query_returns_nothing` compares with the new empty answer:
```python
EMPTY = {"items": [], "entries": [], "complaints": [], "sites": [], "pieces": []}


def test_short_query_returns_nothing(office_client):
    assert office_client.get("/search/?q=e").json() == EMPTY
    assert office_client.get("/search/?q=ab").json() == EMPTY
    assert office_client.get("/search/?q=a%00b").json() == EMPTY
```

In `tests/inventory/test_dashboard.py`, `test_dashboard_query_count`: the dashboard now reads three service figures and the menu shows two badges, so the bound becomes `django_assert_max_num_queries(25)`.

In `tests/test_permissions.py`, below `EXPECTED_STOCK_ROUTES`, add:
```python
EXPECTED_SERVICE_ROUTES = {
    "defectives_dashboard", "defective_pieces", "pieces_bulk", "piece_detail", "mark_defective", "return_batches",
    "batch_new", "batch_detail", "batch_add", "batch_remove", "batch_dispatch", "batch_settle",
    "defective_list_xlsx", "batch_xlsx", "complaints_dashboard", "complaints", "complaint_new", "complaint_detail",
    "complaint_status", "complaint_not_covered", "visit_new", "complaints_xlsx", "pending_complaints_xlsx",
    "site_quick_create", "sites", "site_detail", "site_edit", "site_toggle", "technicians", "technician_edit",
    "technician_toggle",
}  # fmt: skip
```
and change `test_sweep_finds_the_routes` to `assert names >= EXPECTED_STOCK_ROUTES | EXPECTED_SERVICE_ROUTES`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_integration_service.py tests/inventory/test_search.py tests/test_permissions.py -q`
Expected: FAIL (`KeyError: 'complaints'` from the search JSON, no badges, no Details column).

- [ ] **Step 3: Menu badges**

`apps/inventory/context_processors.py`, add below `_url`:
```python
def _open_complaints():
    from apps.complaints.models import OPEN_STATUSES, Complaint  # imported here: complaints depends on inventory

    return Complaint.objects.filter(status__in=OPEN_STATUSES).count()


def _pieces_in_store():
    from apps.defectives.models import DefectivePiece, PieceStatus

    return DefectivePiece.objects.filter(status__in=[PieceStatus.IN_STORE, PieceStatus.IN_BATCH]).count()
```
and the return value of `nav` becomes
```python
    return {
        "nav_sections": sections,
        "nav_urls": urls,
        "nav_low_count": SimpleLazyObject(low_stock_count),
        "nav_open_complaints": SimpleLazyObject(_open_complaints),
        "nav_pieces_in_store": SimpleLazyObject(_pieces_in_store),
    }
```

`templates/base.html`, directly after the `{% if e.name == 'low_stock' and nav_low_count %}…{% endif %}` badge, add:
```html
                {% if e.name == 'complaints' and nav_open_complaints %}<span class="badge nav-badge ms-auto" title="Open complaints">{{ nav_open_complaints }}</span>{% endif %}
                {% if e.name == 'defective_pieces' and nav_pieces_in_store %}<span class="badge nav-badge ms-auto" title="Pieces in the Defective store">{{ nav_pieces_in_store }}</span>{% endif %}
```
and change the search box placeholder to `Search items, entries, complaints, sites, tags…`.

- [ ] **Step 4: Selectors**

`apps/inventory/selectors.py`:
```python
def service_stats(today):
    """The service figures on the stock dashboard, in three queries."""
    from apps.complaints.models import OPEN_STATUSES, Complaint, Status, Visit  # complaints depends on inventory
    from apps.defectives.models import DefectivePiece, PieceStatus

    complaints = Complaint.objects.aggregate(
        open=Count("id", filter=Q(status__in=OPEN_STATUSES)),
        not_attended=Count("id", filter=Q(status=Status.NOT_ATTENDED)),
    )
    pieces = DefectivePiece.objects.aggregate(
        in_store=Count("id", filter=Q(status=PieceStatus.IN_STORE)),
        sent=Count("id", filter=Q(status=PieceStatus.SENT)),
    )
    visits = Visit.objects.filter(visit_date__gt=today - timedelta(days=7)).count()
    return {**complaints, **pieces, "visits_week": visits}
```
(add `Count` to the `django.db.models` import).

In `entries_with_lines`, the `select_related` becomes `.select_related("reverses", "created_by", "complaint", "return_batch")`.

In `movement_rows`, add `"entry__complaint", "entry__return_batch"` to the `select_related(...)` list, and extend the search match:
```python
        match = (
            Q(item__code__icontains=f.q)
            | Q(entry__party__icontains=f.q)
            | Q(entry__ref__icontains=f.q)
            | Q(entry__number__icontains=f.q)
            | Q(entry__complaint__number__icontains=f.q)
            | Q(entry__return_batch__number__icontains=f.q)
        )
```

- [ ] **Step 5: Views**

`apps/inventory/views.py`. In `dashboard`, add `"service": selectors.service_stats(today),` to the context. Add the imports
```python
from apps.complaints.models import Complaint, Site
from apps.defectives.models import DefectivePiece
from apps.defectives.services import normalise_tag
```
Replace `entry_detail`:
```python
@role_required(OFFICE)
def entry_detail(request, number):
    entry = get_object_or_404(selectors.entries_with_lines(StockEntry.objects.all()), number=number)
    undone_by = StockEntry.objects.filter(reverses=entry).first()
    pieces = DefectivePiece.objects.filter(events__entry=entry).distinct().select_related("item").order_by("tag")
    return render(
        request,
        "inventory/entry_detail.html",
        {
            "entry": entry,
            "undone_by": undone_by,
            "can_undo": entry.kind != EntryKind.REV and undone_by is None and not entry.is_defective,
            "pieces": pieces,
        },
    )
```
Replace `global_search`:
```python
SEARCH_EMPTY = {"items": [], "entries": [], "complaints": [], "sites": [], "pieces": []}


@role_required(OFFICE)
def global_search(request):
    """Top-bar search: items, entry numbers, complaints (number or company's ticket no.), sites and piece tags."""
    q = _text(request.GET.get("q"))
    if len(q) <= 2:
        return JsonResponse(SEARCH_EMPTY)
    found = [
        {**selectors.picker_option(i), "url": reverse("item_detail", args=[i.pk])}
        for i in search_items(q, limit=8)
    ]
    entries = StockEntry.objects.filter(number__icontains=q).order_by("-id")[:5]
    complaints = (
        Complaint.objects.filter(Q(number__icontains=q) | Q(company_ref__icontains=q))
        .select_related("site", "company")
        .order_by("-id")[:5]
    )
    sites = Site.objects.filter(Q(name__icontains=q) | Q(city__icontains=q) | Q(contact_name__icontains=q))[:4]
    pieces = (
        DefectivePiece.objects.filter(Q(tag__icontains=normalise_tag(q)) | Q(batch_code__icontains=q))
        .select_related("item", "company")
        .order_by("-id")[:5]
    )
    return JsonResponse(
        {
            "items": found,
            "entries": [
                {"number": e.number, "url": reverse("entry_detail", args=[e.number]), "label": e.get_kind_display()}
                for e in entries
            ],
            "complaints": [
                {
                    "number": c.number,
                    "url": reverse("complaint_detail", args=[c.number]),
                    "label": f"{c.site.name}, {c.site.city} · {c.company.name}",
                    "ref": c.company_ref,
                    "status": c.get_status_display(),
                }
                for c in complaints
            ],
            "sites": [
                {
                    "name": s.name,
                    "url": reverse("site_detail", args=[s.pk]),
                    "label": s.city + (f" · {s.contact_name}" if s.contact_name else ""),
                }
                for s in sites
            ],
            "pieces": [
                {
                    "tag": p.tag,
                    "url": reverse("piece_detail", args=[p.tag]),
                    "label": f"{p.item.code} · {p.company.name}",
                    "status": p.get_status_display(),
                }
                for p in pieces
            ],
        }
    )
```

`apps/inventory/exports.py`, `movements_xlsx`: append `Column("Complaint", "code"), Column("Return batch", "code")` to `cols`, and append to each data row
```python
                e.complaint.number if e.complaint_id else "",
                e.return_batch.number if e.return_batch_id else "",
```

- [ ] **Step 6: Templates and search script**

`templates/inventory/dashboard.html`: directly after the fourth KPI tile (the "Entries, last 7 days" card), add:
```html
  <div class="col-sm-6 col-lg-3"><a href="{{ nav_urls.complaints_dashboard|default:'#' }}" class="card card-sm card-link card-link-pop"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar {% if service.not_attended %}kpi-alert{% else %}kpi-brand{% endif %}"><i class="ti ti-message-report"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ service.open }}</div><div class="text-secondary">Open complaints</div><div class="small text-secondary">{% if service.not_attended %}{{ service.not_attended }} not attended yet{% else %}all attended{% endif %}</div></div></div></div></a></div>
  <div class="col-sm-6 col-lg-3"><a href="{{ nav_urls.defectives_dashboard|default:'#' }}" class="card card-sm card-link card-link-pop"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar kpi-brand"><i class="ti ti-recycle"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ service.in_store }}</div><div class="text-secondary">Defective pieces in store</div><div class="small text-secondary">not counted in stock above</div></div></div></div></a></div>
  <div class="col-sm-6 col-lg-3"><a href="{{ nav_urls.return_batches|default:'#' }}" class="card card-sm card-link card-link-pop"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar {% if service.sent %}kpi-wait{% else %}kpi-brand{% endif %}"><i class="ti ti-truck-return"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ service.sent }}</div><div class="text-secondary">Pieces with companies</div><div class="small text-secondary">sent, awaiting settlement</div></div></div></div></a></div>
  <div class="col-sm-6 col-lg-3"><a href="{{ nav_urls.complaints|default:'#' }}" class="card card-sm card-link card-link-pop"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar kpi-brand"><i class="ti ti-clipboard-check"></i></span></div>
    <div class="col"><div class="fw-medium fs-3">{{ service.visits_week }}</div><div class="text-secondary">Visits this week</div><div class="small text-secondary">recorded on complaints</div></div></div></div></a></div>
```

`templates/inventory/movements.html`:
- the search placeholder becomes `Item, supplier, customer, ref, CMP / RB no.`;
- in `<thead>`, after `{% sort_th "kind" "Type" %}` add `<th>Details</th>`;
- in each row, after the Type `<td>`, add
```html
      <td>{{ r.entry.details }}{% if r.entry.complaint %} · <a class="code" href="{% url 'complaint_detail' r.entry.complaint.number %}">{{ r.entry.complaint.number }}</a>{% elif r.entry.return_batch %} · <a class="code" href="{% url 'batch_detail' r.entry.return_batch.number %}">{{ r.entry.return_batch.number }}</a>{% endif %}</td>
```
- the location cell becomes `<td>{% if r.line.location.is_defective_store %}<span class="text-secondary"><i class="ti ti-recycle"></i> {{ r.line.location.name }}</span>{% else %}{{ r.line.location.name }}{% endif %}</td>`;
- the footnote gains ` Rows at the Defective store are failed pieces, not good stock.`

`templates/inventory/entry_detail.html`:
- in `{% block actions %}`, before the "All movements" link, add
```html
  {% if entry.complaint %}<a href="{% url 'complaint_detail' entry.complaint.number %}" class="btn btn-quiet"><i class="ti ti-message-report"></i> Complaint {{ entry.complaint.number }}</a>{% endif %}
  {% if entry.return_batch %}<a href="{% url 'batch_detail' entry.return_batch.number %}" class="btn btn-quiet"><i class="ti ti-truck-return"></i> Batch {{ entry.return_batch.number }}</a>{% endif %}
```
- the Task 1 info alert becomes
```html
{% if entry.is_defective %}<div class="alert alert-info"><div class="d-flex gap-2"><i class="ti ti-info-circle"></i><div>This entry belongs to the defective pieces, so it can't be undone here. Use {% if entry.return_batch %}return batch <a href="{% url 'batch_detail' entry.return_batch.number %}">{{ entry.return_batch.number }}</a>{% else %}the <a href="{% url 'defective_pieces' %}">Defectives screens</a>{% endif %} instead.</div></div></div>{% endif %}
```
- in the Details datagrid, after the DC / ref item, add
```html
    {% if entry.complaint %}<div class="datagrid-item"><div class="datagrid-title">Complaint</div><div class="datagrid-content"><a class="code" href="{% url 'complaint_detail' entry.complaint.number %}">{{ entry.complaint.number }}</a></div></div>{% endif %}
    {% if entry.return_batch %}<div class="datagrid-item"><div class="datagrid-title">Return batch</div><div class="datagrid-content"><a class="code" href="{% url 'batch_detail' entry.return_batch.number %}">{{ entry.return_batch.number }}</a></div></div>{% endif %}
```
  and the DC / ref title becomes `{% if entry.return_batch %}Docket / ref no.{% else %}DC / ref no.{% endif %}`;
- after the Items card (before the closing `</div>` of `row row-cards`), add
```html
  {% if pieces %}<div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title"><i class="ti ti-tags"></i> Defective pieces</h3><span class="badge bg-secondary-lt ms-2">{{ pieces|length }}</span></div>
    <div class="card-body"><div class="d-flex flex-wrap gap-2">{% for p in pieces %}<a class="chip chip-link" href="{% url 'piece_detail' p.tag %}"><span class="code">{{ p.tag }}</span> <span class="text-secondary">{{ p.item.code }}</span></a>{% endfor %}</div></div></div></div>{% endif %}
```
  The chips card is `col-12`, so it gets its own row under the Details and Items cards.

`static/js/app.js`: replace the block that builds `items`, `entries`, `menu.innerHTML` and the `announce(...)` call with:
```js
      const items = d.items.map((i, n) => `<a class="dropdown-item" role="option" id="gs-i${n}" href="${esc(i.url)}"><span><span class="code">${esc(i.code)}</span><br>
        <small class="text-secondary">${esc(i.type)} · ${esc(i.desc)}${i.aliases.length ? " · also " + esc(i.aliases.join(", ")) : ""}</small></span></a>`);
      const entries = d.entries.map((e, n) => `<a class="dropdown-item" role="option" id="gs-e${n}" href="${esc(e.url)}"><span class="code">${esc(e.number)}</span><span class="ms-2 text-secondary">${esc(e.label)}</span></a>`);
      const complaints = d.complaints.map((c, n) => `<a class="dropdown-item" role="option" id="gs-c${n}" href="${esc(c.url)}"><span><span class="code">${esc(c.number)}</span> <span class="text-secondary">${esc(c.status)}</span><br>
        <small class="text-secondary">${esc(c.label)}${c.ref ? ` · <span class="code">${esc(c.ref)}</span>` : ""}</small></span></a>`);
      const sites = d.sites.map((s, n) => `<a class="dropdown-item" role="option" id="gs-s${n}" href="${esc(s.url)}"><span><i class="ti ti-building"></i> ${esc(s.name)}<br><small class="text-secondary">${esc(s.label)}</small></span></a>`);
      const pieces = d.pieces.map((p, n) => `<a class="dropdown-item" role="option" id="gs-p${n}" href="${esc(p.url)}"><span><span class="code">${esc(p.tag)}</span> <span class="text-secondary">${esc(p.status)}</span><br><small class="text-secondary">${esc(p.label)}</small></span></a>`);
      const groups = [["Items", items], ["Entries", entries], ["Complaints", complaints], ["Sites", sites], ["Defective pieces", pieces]];
      menu.innerHTML = groups.filter(([, list]) => list.length).map(([title, list]) => `<span class="dropdown-header" role="presentation">${title}</span>${list.join("")}`).join("")
        || `<span class="dropdown-item-text text-secondary" role="presentation">Nothing found for “${esc(q)}”.</span>`;
      menu.classList.add("show"); active = -1; box.setAttribute("aria-expanded", "true");
      const total = groups.reduce((n, [, list]) => n + list.length, 0);
      announce(total ? `${total} result${total > 1 ? "s" : ""}` : "Nothing found");
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS (whole suite).

- [ ] **Step 8: Check it in a browser**

Type `cmp-`, a company ticket number, a site name and `def-1` into the top search (each group appears and Enter opens the first hit); open the dashboard (eight tiles, the four new ones link to the service screens); open Movements and a collection entry (Details links to the complaint, Undo is hidden, the pieces are listed). Expected: no console errors.

- [ ] **Step 9: Commit**

```bash
git add apps/inventory templates/base.html templates/inventory static/js/app.js tests/test_integration_service.py tests/inventory/test_search.py tests/inventory/test_dashboard.py tests/test_permissions.py
git commit -m "feat: link stock, complaints and defectives (menu badges, search, dashboard, movements, entry pages)"
```

---

### Task 17: Service demo data (`seed_service_demo`)

**Files:**
- Modify: `apps/inventory/management/commands/seed_stock_demo.py` (extract `load_masters_and_items`)
- Create: `apps/complaints/demo/service-demo.json` (copy), `apps/complaints/management/__init__.py`, `apps/complaints/management/commands/__init__.py` (both empty), `apps/complaints/management/commands/seed_service_demo.py`
- Test: `tests/complaints/test_seed_service_demo.py`

The replay order in `Replay.actions()` was checked offline against `mockups/service/demo-data.json` with a pure-Python simulation of these services (numbering per series, TRANSITIONS, visit options, piece statuses, batch rules and the backdated-stock check): all 107 actions replay with the demo's exact numbers and end states.

- [ ] **Step 1: Copy the approved demo data**

```bash
mkdir -p apps/complaints/demo
cp mockups/service/demo-data.json apps/complaints/demo/service-demo.json
```

- [ ] **Step 2: Write the failing tests**

Create `tests/complaints/test_seed_service_demo.py`:
```python
import io
import json
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.db.models import Max, Sum
from django.utils import timezone

from apps.complaints.models import Complaint, Status, Visit
from apps.defectives import selectors
from apps.defectives.models import DefectivePiece, PieceStatus, ReturnBatch
from apps.inventory.models import StockBalance, StockEntry
from apps.inventory.services import balance_drift

pytestmark = pytest.mark.django_db
DEMO = Path(__file__).resolve().parents[2] / "apps" / "complaints" / "demo" / "service-demo.json"


def seed(**kwargs):
    call_command("seed_service_demo", force=True, stdout=kwargs.pop("stdout", io.StringIO()), **kwargs)


def test_seed_loads_the_whole_demo(admin_user, office_user):
    out = io.StringIO()
    seed(stdout=out)
    db = json.loads(DEMO.read_text(encoding="utf-8"))
    assert set(StockEntry.objects.values_list("number", flat=True)) == {e["no"] for e in db["entries"]}
    assert Complaint.objects.count() == len(db["complaints"]) and Visit.objects.count() == len(db["visits"])
    assert DefectivePiece.objects.count() == len(db["pieces"]) and ReturnBatch.objects.count() == len(db["batches"])
    assert f"{len(db['complaints'])} complaints" in out.getvalue() and balance_drift() == []


def test_seed_tells_the_demo_story(admin_user, office_user):
    seed()
    db = json.loads(DEMO.read_text(encoding="utf-8"))
    assert {c.number: c.status for c in Complaint.objects.all()} == {c["no"]: c["status"] for c in db["complaints"]}
    assert {p.tag: p.status for p in DefectivePiece.objects.all()} == {p["tag"]: p["status"] for p in db["pieces"]}
    assert Complaint.objects.filter(status=Status.NOT_COVERED).exists()
    assert Complaint.objects.filter(status=Status.AWAITING_MATERIAL).exists()
    labels = {b.number: selectors.batch_label(b, b.n_lines, b.n_settled) for b in selectors.batches_with_counts()}
    assert labels == {"RB-0001": "Partly settled", "RB-0002": "Dispatched", "RB-0003": "Draft"}
    in_store = DefectivePiece.objects.filter(status__in=[PieceStatus.IN_STORE, PieceStatus.IN_BATCH]).count()
    store_qty = StockBalance.objects.filter(location__is_defective_store=True).aggregate(t=Sum("qty"))["t"]
    assert store_qty == in_store
    # order_by() drops Meta.ordering, which would otherwise join the DISTINCT and count every complaint
    assert Complaint.objects.order_by().values("company").distinct().count() >= 3  # several companies, not one


def test_seed_dates_are_never_in_the_future(admin_user, office_user):
    seed()
    today = timezone.localdate()
    assert StockEntry.objects.aggregate(m=Max("entry_date"))["m"] <= today
    assert Complaint.objects.aggregate(m=Max("reported_on"))["m"] <= today


def test_seed_refuses_a_used_system(admin_user, office_user):
    seed()
    with pytest.raises(CommandError, match="only for an empty system"):
        seed()


def test_seed_needs_force_without_debug(settings, admin_user, office_user):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="Pass --force"):
        call_command("seed_service_demo", stdout=io.StringIO())
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `uv run pytest tests/complaints/test_seed_service_demo.py -q`
Expected: FAIL with `CommandError: Unknown command: 'seed_service_demo'`.

- [ ] **Step 4: Share the item loader in `seed_stock_demo.py`**

Add this module-level function (the body is the block that `handle` used to run between `shift = ...` and the entries loop) and make `handle` call it with `places, companies, items = load_masters_and_items(db)`:
```python
def load_masters_and_items(db):
    """(places, companies, items) from a demo file: masters created if missing, items saved through save_item.

    Shared by seed_stock_demo and seed_service_demo. `items` is {code: Item}.
    """
    places = _masters(Location, db["locations"])
    spare_types = _masters(SpareType, db["spareTypes"])
    fitting_types = _masters(FittingType, db["fittingTypes"])
    companies = _masters(Company, db["companies"])
    items = {}
    for d in db["items"]:
        items[d["code"]] = save_item(
            data={
                "code": d["code"],
                "spare_type": spare_types[d["type"]],
                "company": companies[d["company"]],
                "description": d["desc"],
                "cat_ref": d["catRef"],
                "fitting_type": fitting_types[d["fittingType"]] if d["fittingType"] else None,
                "wattage_w": d["watt"],
                "current_ma": d["ma"],
                "unit": d["unit"],
                "reorder_level": d["reorder"],
                "aliases": d["aliases"],
                "is_active": d["active"],
            }
        )
    return places, companies, items
```

- [ ] **Step 5: Write `apps/complaints/management/commands/seed_service_demo.py`**

```python
"""Load the approved service demo (a copy of mockups/service/demo-data.json): items, the shared stock ledger, sites,
technicians, complaints with visits, defective pieces and return batches, across several companies.

Everything is replayed through the real services in the order the demo happened, so entries, pieces, events and
numbers are what the app itself records. Dates are shifted so the demo's "today" is today. Within one day:
complaints are filed first; then every action that posts to the ledger, in ledger order (plain stock entries,
visits, mark defective, scrap, dispatch, settlement); then status changes and visits that posted nothing; then
new return batches and "rejected (scrapped)" answers, which post nothing either.
"""

import json
from datetime import date
from functools import partial
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import ADMIN, OFFICE
from apps.complaints import services as complaints
from apps.complaints.models import Complaint, NotCoveredReason, Priority
from apps.defectives import services as defectives
from apps.defectives.models import DefectivePiece, ScrapReason
from apps.inventory.management.commands.seed_stock_demo import REASONS, _user, load_masters_and_items
from apps.inventory.models import EntryKind, InSource, StockEntry
from apps.inventory.services import Line, post_entry, undo_entry

DEMO = Path(__file__).resolve().parents[2] / "demo" / "service-demo.json"
REASON_VALUES = {label: value for value, label in NotCoveredReason.choices}
PRIORITY_VALUES = {label: value for value, label in Priority.choices}


def _month(text):
    """'2026-03' -> date(2026, 3, 1); '' -> None."""
    return date(int(text[:4]), int(text[5:7]), 1) if text else None


class Replay:
    def __init__(self, db, users):
        self.db, self.users = db, users
        self.shift = timezone.localdate() - date.fromisoformat(db["today"])
        self.places, self.companies, self.items = load_masters_and_items(db)
        self.by_no = {e["no"]: e for e in db["entries"]}
        self.demo_pieces = {p["tag"]: p for p in db["pieces"]}
        self.sites, self.techs, self.complaints, self.batches, self.entries = {}, {}, {}, {}, {}

    def day(self, iso):
        return date.fromisoformat(iso) + self.shift

    def check(self, posted, demo_no):
        if posted.number != demo_no:
            raise CommandError(f"Demo entry {demo_no} was numbered {posted.number}. Is the ledger empty?")
        self.entries[demo_no] = posted

    def load_people(self):
        for s in self.db["sites"]:
            self.sites[s["id"]] = complaints.save_site(
                data={
                    "name": s["name"],
                    "city": s["city"],
                    "contact_name": s["contact"],
                    "phone": s["phone"],
                    "address": s["address"],
                }
            )
        for t in self.db["techs"]:
            self.techs[t["name"]] = complaints.save_technician(name=t["name"], phone=t["phone"])

    def actions(self):
        """Every demo action as (date, phase, kind, order, callable), sorted in the order the demo made them."""
        db = self.db
        index = {e["no"]: n for n, e in enumerate(db["entries"])}
        in_visits = {no for v in db["visits"] for no in (v["outEntry"], v["collectEntry"]) if no}
        acts = [(c["reportedOn"], 0, 0, n, partial(self.file, c)) for n, c in enumerate(db["complaints"])]
        for n, v in enumerate(db["visits"]):
            posted = [index[no] for no in (v["outEntry"], v["collectEntry"]) if no]
            if posted:
                acts.append((v["date"], 1, 0, min(posted), partial(self.visit, v)))
            else:
                acts.append((v["date"], 2, 1, n, partial(self.visit, v)))
        for e in db["entries"]:
            if e["no"] not in in_visits:
                acts.append((e["date"], 1, 0, index[e["no"]], partial(self.entry, e)))
        for n, ev in enumerate(db["complaintEvents"]):
            if ev["from"] is not None and not ev["note"].startswith("Visit VIS-"):
                acts.append((ev["at"], 2, 0, n, partial(self.status, ev)))
        for n, b in enumerate(db["batches"]):
            acts.append((b["createdOn"], 3, 0, n, partial(self.create_batch, b)))
            for line in b["lines"]:
                if line["outcome"] == "REJECTED_SCRAPPED":
                    acts.append((line["settledOn"], 3, 1, n, partial(self.settle, b, line, self.users["Office"])))
        return sorted(acts, key=lambda a: a[:4])

    # ---------------------------------------------------------------- complaints

    def file(self, c):
        made = complaints.file_complaint(
            site=self.sites[c["site"]],
            company=self.companies[c["company"]],
            fault=c["fault"],
            reported_on=self.day(c["reportedOn"]),
            user=self.users["Office"],
            company_ref=c["companyRef"],
            qty_affected=c["qty"],
            priority=PRIORITY_VALUES[c["priority"]],
            technicians=[self.techs[t] for t in c["techs"]],
            contact_name=c["contact"],
            phone=c["phone"],
        )
        if made.number != c["no"]:
            raise CommandError(f"Demo complaint {c['no']} was numbered {made.number}.")
        self.complaints[c["no"]] = made

    def status(self, ev):
        complaints.change_status(
            complaint=self.complaints[ev["complaint"]],
            to=ev["to"],
            user=self.users[ev["by"]],
            note=ev["note"],
            reason=REASON_VALUES.get(ev.get("reason", ""), ""),
            at=self.day(ev["at"]),
        )

    def visit(self, v):
        out = self.by_no.get(v["outEntry"]) if v["outEntry"] else None
        col = self.by_no.get(v["collectEntry"]) if v["collectEntry"] else None
        parts = [(self.items[ln["code"]], -ln["qty"]) for ln in out["lines"]] if out else []
        collected, tags = [], list(v["tags"])
        for ln in col["lines"] if col else []:
            fault = self.demo_pieces[tags[0]]["fault"]
            tags = tags[ln["qty"] :]
            collected.append((self.items[ln["code"]], ln["qty"], ln.get("batch", ""), _month(ln.get("pkd", "")), fault))
        made = complaints.record_visit(
            complaint=self.complaints[v["complaint"]],
            visit_date=self.day(v["date"]),
            technicians=[self.techs[t] for t in v["techs"]],
            work_done=v["work"],
            next_status=v["nextStatus"],
            user=self.users["Office"],
            location=self.places[out["lines"][0]["loc"]] if out else None,
            parts=parts,
            collected=collected,
        )
        if out:
            self.check(made.out_entry, out["no"])
        if col:
            self.check(made.collect_entry, col["no"])

    # ---------------------------------------------------------------- ledger entries outside visits

    def entry(self, e):
        user, when, store = self.users[e["by"]], self.day(e["date"]), self.db["defStore"]
        if e["kind"] == EntryKind.TRF and e.get("party") == store:
            good = next(ln for ln in e["lines"] if ln["qty"] < 0)
            fault = e["note"].split(": ", 1)[1] if ": " in e["note"] else e["note"]
            posted, _ = defectives.mark_defective(
                location=self.places[good["loc"]],
                lines=[(self.items[good["code"]], -good["qty"], fault)],
                entry_date=when,
                user=user,
            )
        elif e["kind"] == EntryKind.ADJ and all(ln["loc"] == store for ln in e["lines"]):
            head, why = e["note"].split(": ", 1)
            tags = head.removeprefix("Scrapped ").split(", ")
            posted = defectives.scrap(
                pieces=list(DefectivePiece.objects.filter(tag__in=tags)),
                reason=ScrapReason.NOT_WORTH,
                note=why,
                user=user,
                entry_date=when,
            )
        elif e.get("subtype") == "RETURN_TO_COMPANY":
            b = next(b for b in self.db["batches"] if b["dispatchEntry"] == e["no"])
            posted = defectives.dispatch(
                batch=self.batches[b["no"]], dispatched_on=when, courier=b["courier"], docket_no=b["docket"], user=user
            )
        elif e.get("subtype") in ("REPLACEMENT", "DEFECTIVE_RETURNED"):
            b = next(b for b in self.db["batches"] if any(ln["entry"] == e["no"] for ln in b["lines"]))
            line = next(ln for ln in b["lines"] if ln["entry"] == e["no"])
            [posted] = self.settle(b, line, user)
        elif e["kind"] == EntryKind.REV:
            posted = undo_entry(entry=self.entries[e["reverses"]], reason=e["note"], user=user, entry_date=when)
        else:
            subtype = e.get("subtype", "")
            posted = post_entry(
                kind=e["kind"],
                entry_date=when,
                lines=[
                    Line(self.items[ln["code"]], self.places[ln["loc"]], ln["qty"], ln.get("batch", ""), _month(ln.get("pkd", "")))
                    for ln in e["lines"]
                ],
                user=user,
                subtype=subtype,
                party=e.get("party", ""),
                company=self.companies.get(e.get("party")) if subtype == InSource.SUPPLIER else None,
                ref=e.get("ref", ""),
                reason=REASONS[e["reason"]] if e["kind"] == EntryKind.ADJ else "",
                note=e.get("note", ""),
            )
        self.check(posted, e["no"])

    # ---------------------------------------------------------------- return batches

    def create_batch(self, b):
        made = defectives.create_batch(
            company=self.companies[b["company"]],
            user=self.users["Office"],
            pieces=list(DefectivePiece.objects.filter(tag__in=[ln["tag"] for ln in b["lines"]])),
            note=b["note"],
            created_on=self.day(b["createdOn"]),
        )
        if made.number != b["no"]:
            raise CommandError(f"Demo batch {b['no']} was numbered {made.number}.")
        self.batches[b["no"]] = made

    def settle(self, b, line, user):
        return defectives.settle(
            batch=self.batches[b["no"]],
            pieces=[DefectivePiece.objects.get(tag=line["tag"])],
            outcome=line["outcome"],
            settled_on=self.day(line["settledOn"]),
            to_location=self.places.get(line["toLoc"]),
            user=user,
        )

    def verify(self):
        """The replay must end exactly where the demo ended."""
        for c in self.db["complaints"]:
            status = Complaint.objects.get(number=c["no"]).status
            if status != c["status"]:
                raise CommandError(f"{c['no']} ended {status}; the demo says {c['status']}.")
        for p in self.db["pieces"]:
            piece = DefectivePiece.objects.select_related("item").get(tag=p["tag"])
            if (piece.status, piece.item.code) != (p["status"], p["code"]):
                raise CommandError(f"{p['tag']} ended {piece.status} ({piece.item.code}); the demo says {p['status']}.")


class Command(BaseCommand):
    help = (
        "Load the service demo: stock, complaints, visits, defective pieces and return batches "
        "(empty system only, and only with DEBUG or --force)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Load demo data even when DEBUG is off.")

    @transaction.atomic
    def handle(self, *args, force=False, **options):
        if not settings.DEBUG and not force:
            raise CommandError("Demo data is for development. Pass --force to load it anyway.")
        if StockEntry.objects.exists() or Complaint.objects.exists():
            raise CommandError("The database already has stock entries or complaints. Demo data is only for an empty system.")
        db = json.loads(DEMO.read_text(encoding="utf-8"))
        replay = Replay(db, {"Admin": _user(ADMIN), "Office": _user(OFFICE)})
        replay.load_people()
        for *_, action in replay.actions():
            action()
        replay.verify()
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(db['items'])} items, {len(db['entries'])} entries, {len(db['complaints'])} complaints, "
                f"{len(db['visits'])} visits, {len(db['pieces'])} defective pieces, {len(db['batches'])} return batches."
            )
        )
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest tests/complaints/test_seed_service_demo.py tests/inventory/test_seed_demo.py -q`
Expected: PASS (the stock seed still loads 28 items and 35 entries). If a replay step fails, the CommandError names the demo entry, complaint or piece that diverged; fix the replay order or mapping in `actions()`, never the demo file.

Then run the whole suite and ruff: `uv run pytest -q && uv run ruff format --check . && uv run ruff check .`. Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/management/commands/seed_stock_demo.py apps/complaints/demo apps/complaints/management tests/complaints/test_seed_service_demo.py
git commit -m "feat: service demo data replayed through the services"
```

---

### Task 18: Browser walkthrough, docs, todo

**Files:**
- Modify: `e2e/walkthrough.py`, `Makefile`, `README.md`, `CLAUDE.md`, `tasks/todo.md`

Needs Task 17: the walkthrough runs against a database loaded with `seed_service_demo`.

- [ ] **Step 1: Extend the browser walkthrough (`e2e/walkthrough.py`)**

Update the module docstring's second paragraph to: "Re-runnable: each run creates a new item TEST-<timestamp> and a new site, files a new complaint and posts a few service entries; it undoes the stock entries it can (Stock IN, transfer, adjustment, the visit's parts given), so good stock ends where it started. A replaced piece comes back into stock, which balances the piece it marked defective."

Below `NEW = ...` add:
```python
STAMP = int(time.time())
ITEM = "LG78-150-700"  # a Wipro driver with stock at Vizag Office in the demo data
```

Add these functions above `with sync_playwright() as p:`:
```python
def ts_pick(page, select_id, text, create=False):
    """Type into a Tom Select box and pick the first match (or its 'create' option)."""
    control = page.locator(f"#{select_id}-ts-control")
    control.click()
    control.fill(text)
    dropdown = page.locator(f"#{select_id}-ts-dropdown")
    target = dropdown.locator(".create") if create else dropdown.locator(".option").first
    expect(target).to_be_visible()
    target.click()


def success_text(page):
    alert = page.locator(".alert-success").first
    expect(alert).to_be_visible()
    return alert.inner_text()


def download(page, url, link_text, prefix):
    page.goto(url)
    with page.expect_download() as dl:
        page.locator("a", has_text=link_text).first.click()
    name = dl.value.suggested_filename
    check(name.startswith(prefix) and name.endswith(".xlsx"), f"unexpected export file name {name!r}")


def service(page):
    """Complaints and defectives on desktop (spec walkthrough)."""
    site = f"Walkthrough Site {STAMP}"
    step("file a complaint with a new site from the site picker")
    page.goto(f"{BASE}/complaints/new/")
    ts_pick(page, "id_site", site, create=True)
    expect(page.locator("#site-modal")).to_be_visible()
    expect(page.locator("#id_ns-name")).to_have_value(site)
    page.fill("#id_ns-city", "Visakhapatnam")
    page.fill("#id_ns-contact_name", "Walkthrough contact")
    page.fill("#id_ns-phone", "9876543210")
    page.click("#site-form button[type=submit]")
    expect(page.locator("#site-modal")).to_be_hidden()
    expect(page.locator("#id_contact_name")).to_have_value("Walkthrough contact")
    page.fill("#id_company_ref", f"WT-{STAMP}")
    page.fill("#id_fault", "2 flood lights not glowing (walkthrough)")
    page.locator(".form-selectgroup-label", has_text="High").click()
    page.click("#complaint-form button[type=submit]")
    cmp_no = entry_number(page, "CMP")

    step("record a visit: 1 part given, 2 failed pieces collected")
    page.locator("a", has_text="Record visit").first.click()
    ts_pick(page, "id_technicians", "Ramu")
    page.fill("#id_work_done", "Changed 1 driver, 2 taken back (walkthrough)")
    pick_item(page, ITEM, row=0)
    have = int(page.locator("[data-lines=part] .avail b").first.inner_text())
    check(have >= 2, f"{ITEM} has only {have} at Vizag Office; re-seed the demo data")
    page.locator("input[name=part_qty]").first.fill("1")
    pick_item(page, ITEM, row=1)
    page.locator("input[name=col_qty]").first.fill("2")
    page.locator("input[name=col_batch]").first.fill("B2405")
    page.locator("input[name=col_fault]").first.fill("no output")
    page.locator(".form-selectgroup-label", has_text="Material need to check").click()
    page.click("form[data-lines-form] button[type=submit]")
    text = success_text(page)
    tags = re.findall(r"DEF-\d{4}", text)
    check(len(tags) == 2, f"expected 2 new tags, got {text!r}")
    out_no = re.search(r"OUT-\d{4}", text).group(0)

    step("Awaiting material, then Resolved, then Closed")
    for label in ("Awaiting material", "Resolved", "Closed"):
        page.locator("button", has_text="Change status").click()
        modal = page.locator("#status-modal")
        expect(modal).to_be_visible()
        modal.locator(".form-selectgroup-label", has_text=label).click()
        modal.locator("button[type=submit]").click()
        expect(page.locator(".page-title")).to_contain_text(label)

    step("mark 1 piece defective from stock")
    page.goto(f"{BASE}/defectives/mark/")
    pick_item(page, ITEM)
    page.locator("input[name=line_qty]").first.fill("1")
    page.locator("input[name=line_fault]").first.fill("Dead on arrival (walkthrough)")
    page.click("form[data-lines-form] button[type=submit]")
    entry_number(page, "TRF")
    marked = re.search(r"DEF-\d{4}", success_text(page)).group(0)

    step("create a return batch for one company, dispatch it")
    page.goto(f"{BASE}/defectives/batches/new/")
    page.select_option("#b-company", label="Wipro Lighting")
    page.wait_for_url(re.compile(r"company=\d+"))
    for tag in (marked, tags[0]):
        page.check(f"input[name=tag][value='{tag}']")
    page.fill("#b-note", "Walkthrough batch")
    page.locator("button", has_text="Create draft batch").click()
    rb_no = entry_number(page, "RB")
    page.locator("button", has_text="Dispatch…").click()
    expect(page.locator("#dispatch-modal")).to_be_visible()
    page.fill("#d-courier", "DTDC")
    page.fill("#d-docket", f"WT{STAMP}")
    page.click("#dispatch-modal button[type=submit]")
    check("dispatched" in success_text(page), "the batch was not dispatched")

    step("settle: 1 replaced (Stock IN to Vizag Office), 1 rejected and returned")
    page.check(f"input[name=tag][value='{marked}']")
    page.locator(".form-selectgroup-label", has_text="Replaced").click()
    page.select_option("#s-loc", label="Vizag Office")
    page.locator("button[type=submit]", has_text="Settle ticked pieces").click()
    check("settled as Replaced" in success_text(page), "the replacement was not settled")
    page.check(f"input[name=tag][value='{tags[0]}']")
    page.locator(".form-selectgroup-label", has_text="Rejected (returned)").click()
    page.locator("button[type=submit]", has_text="Settle ticked pieces").click()
    check("Rejected (returned)" in success_text(page), "the rejection was not settled")
    expect(page.locator(".page-title")).to_contain_text("Settled")

    step("download the four service reports")
    download(page, f"{BASE}/complaints/", "Pending complaints", "Pending_Complaints_")
    download(page, f"{BASE}/complaints/list/?tab=all", "Export to Excel", "Complaint_List_")
    download(page, f"{BASE}/defectives/", "Defective list", "Defective_List_")
    download(page, f"{BASE}/defectives/batches/{rb_no}/", "Export dispatch list", f"Return_Batch_{rb_no}_")

    step(f"clean-up: undo the parts given on {cmp_no} ({out_no})")
    page.goto(f"{BASE}/entries/{out_no}/")
    undo(page, out_no, "walkthrough cleanup")


def service_phone(page):
    step("complaints and defective pieces on a phone")
    page.goto(f"{BASE}/complaints/list/")
    expect(page.locator("table")).to_be_visible()
    page.click(".navbar-toggler")
    expect(page.get_by_role("link", name="All complaints").first).to_be_visible()
    page.goto(f"{BASE}/defectives/pieces/")
    expect(page.locator("table")).to_be_visible()
```

In the main loop, the two branches become:
```python
            if size["width"] > 500:
                run(page)
                service(page)
            else:
                phone(page)
                service_phone(page)
```

- [ ] **Step 2: Run the walkthrough against the demo database**

```bash
export DATABASE_URL="postgresql://postgres:@127.0.0.1:<port>/svkml_demo"
uv run python manage.py migrate
SEED_PASSWORD="<strong password>" uv run python manage.py seed_users
uv run python manage.py seed_service_demo        # only on an empty svkml_demo; drop and recreate the database first if it has data
uv run python manage.py runserver 8000            # in a second terminal
uv run --with playwright python e2e/walkthrough.py http://127.0.0.1:8000 office "<SEED_PASSWORD>"
```
Expected: every step printed, `JS errors: none`, exit code 0. Run it a second time: also exit 0.

- [ ] **Step 3: Docs, Makefile and todo**

`Makefile`, the `demo` target becomes:
```make
demo:
	$(RUN) python manage.py seed_users
	$(RUN) python manage.py seed_service_demo
```

`README.md`:
- In the first paragraph, replace "Five reports download as neatly formatted Excel files." with: "Two linked modules use the same ledger. **Complaints** logs customer-site complaints with saved sites and technicians; a visit gives parts (a real Stock OUT) and collects failed parts. **Defective pieces** tags every failed part, keeps it in a separate Defective store that never counts as good stock, and tracks it through a return batch to the company's answer (replaced, repaired or rejected). No company is special: Wipro is one company among several. Nine reports download as neatly formatted Excel files."
- In "Run it with Docker", the `make demo` comment becomes `# users admin + office; demo stock, complaints, visits, defective pieces, return batches`, and the next paragraph's `seed_stock_demo --force` becomes `seed_service_demo --force`.
- In "Run it without Docker", `seed_stock_demo     # optional demo data` becomes `seed_service_demo   # optional demo data (stock + complaints + defectives)`.
- In "Browser walkthrough", append: "It then files a complaint with a new site, records a visit that gives a part and collects two failed pieces, moves the complaint through Awaiting material, Resolved and Closed, marks a piece defective, dispatches a return batch and settles it (one replaced, one rejected and returned), downloads the four service reports, and undoes the visit's parts."
- The Roles table becomes:
```markdown
| Role   | Can do |
|--------|--------|
| Admin  | Everything: all stock, complaints and defectives screens, masters (locations, companies, fitting types, spare types), hiding sites and technicians, reopening a closed complaint, users and the Django admin back office. |
| Office | Every stock screen, every complaints and defectives screen (file complaints, record visits, mark defective, return batches, settle), add and edit items, sites and technicians. |
```

`CLAUDE.md`, append:
```markdown
## Service modules (built 2026-10-12, plan `docs/superpowers/plans/2026-10-12-defectives-complaints.md`)
- `apps/complaints` and `apps/defectives` write only through their `services.py`; every stock effect goes through `inventory.services.post_entry`, so the ledger stays append-only.
- The **Defective store** is the one `Location` with `is_defective_store=True`. Use `Location.objects.good()` for anything that means good stock (totals, low stock, pickers). Only the defectives services post to it, and their entries refuse Undo.
- Demo data: `seed_service_demo` replays `apps/complaints/demo/service-demo.json` (a copy of the approved mockup data) through the services. `make demo` runs it.
```

`tasks/todo.md`, in the "Defective pieces + Complaints" section: tick "Implementation plan" (with the plan path) and, under "Build with subagent-driven development", list one line per task of this plan in the same style as the stock build (`- [x] Task N <name>: <commit> + review fixes <commit> (<test count> tests; spec ✅ quality ✅)`). Tick a line only with its evidence: the commit, the passing suite, and for this task the walkthrough exit code and JS-error count from Step 2. Leave the build item open until the user has reviewed it.

- [ ] **Step 4: Full check and commit**

Run: `uv run pytest -q && uv run ruff format --check . && uv run ruff check .`
Expected: all pass.

```bash
git add e2e/walkthrough.py Makefile README.md CLAUDE.md tasks/todo.md
git commit -m "feat: e2e service walkthrough, docs and todo for the service modules"
```

