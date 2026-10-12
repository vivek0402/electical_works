# Defective Pieces & Complaints: Design

**Date:** 2026-10-12. **Status:** approved by the user in brainstorming. The next step is a clickable mockup and its approval, then the implementation plan.
**Builds on:** the Stock Management System on branch `stock-system`, made up of `apps/inventory` (Items, Company, Location, the append-only ledger, and services) and `apps/accounts` (roles ADMIN and OFFICE).

## Goal
Add the two remaining linked modules to the SVKML app:
1. **Defective pieces:** track every failed part individually, from collection to its return to the company and its settlement.
2. **Complaints:** log customer-site complaints, assign technicians, and record visits (parts given, failed parts collected) through to closure.

## Decisions (confirmed with the user)
- **One app, linked modules.**
  - A visit on a complaint posts a real **Stock OUT** for parts given.
  - It also creates **defective pieces** for the failed parts collected.
  - Both are tagged to the complaint.
- **Defectives are tracked one physical piece at a time,** never as item plus quantity.
- **No company is special.**
  - Wipro is one company among several, from the existing Company master.
  - Returns go to a chosen company.
  - Complaints record which company's product failed.
  - No company name appears in any model, status or label.
  - See `tasks/lessons.md`, 2026-10-12.
- **Settlement outcomes:**
  - **Replaced** and **Repaired** post an automatic Stock IN.
  - **Rejected** means the piece returns to the defective store or is scrapped.
  - There are no credit notes.
- **Defective store.**
  - A dedicated **Defective** location sits in the stock ledger, flagged `is_defective_store`.
  - Good-stock totals, low stock and entry-form location pickers exclude it.
  - The Current stock screen shows it as its own column.
- **Complaint statuses:**
  - Not attended → Attended → Material need to check → Awaiting material → Resolved → Closed.
  - **Not covered** can be reached from any open status. It carries a reason: not our product, out of warranty, customer cancelled, or other.
  - Every change is logged.
- **Sites list.** Sites are saved and picked from a searchable dropdown, and each site has its own complaint history.
- **Technicians.** Technicians are a names-only list and don't log in. Complaints are filed by office staff only.
- **Design.** Tabler with the Navy & Amber palette (DESIGN.md), the same patterns as the stock screens, and Excel as downloads only.

## Prior art (research 2026-10-12)
We build this ourselves and borrow patterns only, because GPL and AGPL sources can be used for ideas but not code.
- **InvenTree Return Order** (MIT): the batch status is separate from each line's outcome.
- **Odoo Repair:** part lines are typed as Add or Remove, which maps to "parts given" and "failed parts collected".
- **django-helpdesk** (BSD): every status change is an append-only follow-up row.
- **Frappe Helpdesk:** a paused SLA clock, which is our "Awaiting material" time.
- **OCA/rma:** settlement is per piece, and a batch can be split.

There is no state-machine library. Each model gets a `TRANSITIONS` dict plus a service `change_status()` that runs in a transaction and writes an event row, the same style as the stock services.

## Data model

### Changes to the existing models (`apps/inventory`)
- **`Location.is_defective_store`** (bool, default False). The `0005` migration creates the location "Defective store" with this flag set.
  - Entry forms and good-stock selectors exclude it.
  - Only the defectives services post to it.
- **New `EntryKind`/subtypes, through the existing `post_entry`:**
  - **IN subtype `REPLACEMENT`:** a replacement or repaired piece received back from a company.
  - **OUT subtype `COMPLAINT`:** parts given at a complaint visit.
  - **Collection at a site:** IN subtype `DEFECTIVE_COLLECTED`, posted to the Defective store.
  - **Dispatch to a company:** OUT subtype `RETURN_TO_COMPANY`, posted from the Defective store.
  - **Rejected piece returned by the company:** IN subtype `DEFECTIVE_RETURNED`, posted to the Defective store.
  - **"Mark defective":** a TRF from a good location to the Defective store.
  - **Scrapping a rejected piece:** an ADJ with reason DAMAGED, posted at the Defective store.
- **`StockEntry.complaint`** is a nullable FK, and **`StockEntry.return_batch`** is a nullable FK, so that ledger entries can link back.

### `apps/defectives`
- **`DefectivePiece`**
  - Fields:
    - `tag` (DEF-0001, using the EntryCounter pattern) and `item` (FK)
    - `company`: an FK copied from `item.company` when the piece is collected, editable before dispatch
    - `batch_code`, `pkd`, `fault_note`
    - `source`: one of `SITE_VISIT` or `FOUND_IN_STOCK`
    - `visit` (nullable FK) and `collected_on`
    - `status`, `return_batch` (nullable FK), `outcome`, `settled_on`
    - `replacement_entry` (FK to StockEntry, nullable), `created_by`
  - Status flow:
    - `IN_STORE` → `IN_BATCH` (draft batch) → `SENT` → `SETTLED`.
    - `IN_STORE` → `SCRAPPED` is allowed directly, for example when a piece is not worth returning.
  - `outcome` (set when the piece is settled): `REPLACED`, `REPAIRED`, `REJECTED_RETURNED` (the piece is back `IN_STORE`, can be re-batched or scrapped), or `REJECTED_SCRAPPED`.
- **`ReturnBatch`**
  - Fields: `number` (RB-0001), `company` (FK), `created_on`, `dispatched_on`, `docket_no`, `courier`, `note`, and `status`.
  - `status` is either `DRAFT` or `DISPATCHED`. "Partly settled" and "Settled" are worked out from the pieces and never stored.
  - A batch holds pieces of one company only. It is locked once dispatched.
- **`DefectiveEvent`**: append-only, recording piece, from, to, at, by and note.

### `apps/complaints`
- **`Site`**: `name` (unique ignoring case), `city`, `contact_name`, `phone`, `address` (optional), `is_active`.
- **`Technician`**: `name` (unique ignoring case), `phone` (optional), `is_active`.
- **`Complaint`**
  - Fields:
    - `number` (CMP-0001) and `site` (FK)
    - `company` (FK): whose product failed
    - `company_ref`: the company's complaint or ticket number; optional, indexed, not unique
    - `fault`, `qty_affected` (optional int)
    - `reported_on`, `priority` (Normal, High or Urgent)
    - `technicians` (M2M), `status`
    - `not_covered_reason` and `closed_on`
  - The contact name and phone are copied from the site but can be edited per complaint.
- **`ComplaintEvent`**: append-only, recording complaint, from, to, at, by and note.
  - Age = (closed_on or today) − reported_on.
  - Days awaiting material = the sum of the intervals spent in `AWAITING_MATERIAL`, worked out from these events.
- **`Visit`**: `complaint`, `visit_date`, `technicians` (M2M), `work_done`, `next_status`.
  - Parts given go to one linked StockEntry (OUT, subtype COMPLAINT) from the chosen location.
  - Failed parts collected become one `DefectivePiece` per piece.

## Services (the only write path)
| Action | Service | Ledger effect |
|---|---|---|
| File complaint | `complaints.services.file_complaint` | none |
| Change status | `complaints.services.change_status(complaint, to, user, note, reason=None)`, checked against TRANSITIONS | none |
| Record visit | `complaints.services.record_visit(complaint, date, techs, work_done, parts, collected, next_status, user)`. All of it is one transaction. | OUT for the parts given, plus IN to the Defective store for each collected piece |
| Mark defective from stock | `defectives.services.mark_defective(item, from_location, qty, fault, user)` | TRF from the good location to the Defective store; creates qty pieces |
| Create, fill and dispatch a batch | `create_batch(company)`, `add_pieces`, `remove_pieces`, `dispatch(batch, date, docket, courier)` | OUT from the Defective store when dispatched |
| Settle pieces | `settle(pieces, outcome, date, to_location, user)`, in bulk | REPLACED or REPAIRED: IN (REPLACEMENT) to `to_location`. REJECTED_RETURNED: IN back to the Defective store. REJECTED_SCRAPPED: nothing to post, because the piece already left with the OUT. |
| Scrap from store | `scrap(pieces, reason, user)` | ADJ −1 per piece at the Defective store |

All of these reuse `post_entry` and its locking. A visit that would over-issue stock fails the whole transaction.

## Screens (new sidebar sections)
**Complaints:** Dashboard · All complaints · New complaint · Sites · Technicians
- **Dashboard**
  - Open complaints counted by status, as KPI tiles that link to the filtered list.
  - Age buckets: 0–2, 3–7, 8–15 and 15+ days.
  - Oldest open complaints.
  - Count by company and by city.
- **List**
  - Filters: status tab, company, city, technician, age, and search (number, company ref, site).
  - Sortable and paged, the same as the stock lists.
- **New complaint**
  - A searchable site picker that fills in the contact, with "＋ New site" in a modal.
  - Company (searchable), company complaint number, fault, quantity affected, date picker, priority, and technicians (multi-select).
- **Complaint detail**
  - Header with a status badge, age and days awaiting material.
  - A **status timeline** of the events.
  - The visits list.
  - Parts given and defectives collected, each linked.
  - Action buttons: Record visit, Change status, Close as Not covered.
- **Record visit**, a page from the complaint
  - Date, technicians and work done.
  - **Parts given:** the same line editor as Stock OUT, with an item picker, the available quantity at the chosen location, and a live over-issue error.
  - **Failed parts collected:** item, quantity, batch code, PKD and fault. A line with quantity N creates N tagged pieces.
  - Next status.
- **Sites:** a list plus a site card showing its complaint history.
- **Technicians:** a simple list, plus open complaints per technician.

**Defectives:** Dashboard · Pieces · Mark defective · Return batches
- **Dashboard**
  - Pieces in store per company.
  - Pieces sent and awaiting settlement per company, with the age of the oldest batch.
  - Outcomes over the last 90 days: replaced, repaired and rejected.
- **Pieces**
  - Filters: company, item, status, source and date range. Each row has its tag, item, company, source (a complaint link or "stock") and status.
  - Bulk actions: add to a draft batch, scrap.
- **Mark defective (from stock):** location, item, quantity and fault.
- **Return batches**
  - The list and a "New batch" button. A new batch is for one company and offers only that company's `IN_STORE` pieces.
  - **Batch detail**
    - Before dispatch: add or remove pieces.
    - Dispatch: date, docket and courier, after which the batch is locked.
    - Settle: tick pieces, pick an outcome, and pick a location for replacements.
- **Item card and Current stock** gain a "Defective store" quantity (shown separately, never part of the total).

**Excel downloads** (same layout as the stock exports):
- **Pending complaints:** the "AP pending" report, filterable.
- **Complaint list:** current filters.
- **Defective list:** grouped by company, with item code, description, batch, PKD and quantity in store.
- **Return-batch dispatch list:** one company; tag, code, batch, PKD and fault per piece. It goes with the shipment.

## Errors and rules
- Each status change is checked against TRANSITIONS. A change that isn't allowed gives a friendly error, for example "A closed complaint can't move to Attended".
- Only Admin can reopen a closed complaint. Reopening moves it to Attended and logs the change.
- A visit whose parts exceed the available stock fails as a whole and saves nothing, using the same message as Stock OUT.
- A batch can't mix companies, can't be dispatched while empty, and can't be edited after dispatch.
- Settling is allowed only for `SENT` pieces, and replacements require a good location.
- The Defective store can't be hidden, picked in the Stock IN, OUT, Transfer or Adjust forms, or deleted.
- Every ledger effect goes through `post_entry`, so it is append-only and Undo works the same way. Undo of a visit's OUT entry is allowed. Undo of a collection or dispatch entry is blocked; the defectives screens are used instead.

## Permissions
- OFFICE can do everything in both modules, including adding and editing sites and technicians. Staff add a new site inline while filing a complaint.
- ADMIN-only:
  - hiding a site or technician;
  - reopening a closed complaint;
  - the existing masters page (companies, locations).
- ADMIN: everything.
- The existing permission sweep test covers the new routes automatically.

## Demo data
- `make_demo_data` is extended from the two legacy sheets: the defective list (about 80 rows) and AP Pending Complaints (about 30 rows). Their sites, cities, contacts, technicians and remarks seed realistic complaints, visits and pieces **across several companies**. Some lines are deliberately non-Wipro, for example Finolex wire and Havells MCB.
- It includes:
  - two return batches, one partly settled;
  - one "Not covered" complaint;
  - one complaint in Awaiting material.

## Testing
- **Services:** every transition, the visit transaction (including over-issue rollback), batch rules, settlement ledger effects, and that the Defective store is excluded from good-stock selectors.
- **Views:** forms, filters and exports, the same patterns as the stock tests.
- **Permission sweep:** automatic.
- **Playwright walkthrough** (desktop and phone):
  - file a complaint with a new site;
  - record a visit giving parts and collecting 2 failed pieces;
  - set Awaiting material, then Resolved, then Closed;
  - mark 1 piece defective from stock;
  - create a batch for one company, dispatch it, and settle it as 1 replaced (stock IN) and 1 rejected-returned;
  - download the exports.

## Order of work
1. **Clickable mockup** in `mockups/service/`. It reuses the stock mockup's Tabler shell, vendor files and patterns, and uses multi-company demo data. A Playwright walkthrough must pass with zero JS errors. ⛔ Needs the user's approval.
2. **Implementation plan** (writing-plans), executed with subagent-driven development as for stock: **defectives first** (Defective store, pieces, batches), then **complaints** (sites, technicians, complaints, visits).
