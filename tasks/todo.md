# Todo

## Restart (2026-10-11)
The user asked to undo everything and start over. The old work is archived in git tags `archive/main-2026-10-11` and `archive/phase-2-2026-10-11`.

Kept: the sample Excel files (`data/legacy/`), `LICENSE`, and `tasks/lessons.md`.

## Stock Management System (plan approved 2026-10-11)
Plan file: `~/.claude/plans/pasted-content-id-3f22-0-your-jazzy-pancake.md`

Confirmed decisions:
- **Item** = a spare with its own code, plus the fitting it belongs to (Product Cat Ref, fitting type, wattage).
- **Actions:** IN / OUT / Transfer / Adjust.
- **Exports:** current stock, movements, item list, low stock. Neat Excel files built with XlsxWriter.
- **Users:** Admin + Office.
- **UI:** proper form controls only (date pickers, dropdowns, Tom Select searchable item select, number inputs). Never sheet layouts.

### Step A: clickable mockup + sample Excel files ⛔ approval gate
- [x] A.1 `mockups/stock/make_demo_data.py` → `demo-data.json` (clean items from the sample sheets plus companies, fitting types, locations, and a few weeks of IN/OUT/transfer/adjust/undo history; never negative)
- [x] A.2 `mockups/stock/` app shell: vendored Pico + Tom Select (pinned), router, ledger replay, dashboard
- [x] A.3 Entry forms: Stock IN, Stock OUT, Transfer, Adjust (date pickers, dropdowns, searchable item select, number qty, live availability check, add/remove lines, inline "create item")
- [x] A.4 Items list + add/edit item form; current stock (per-location columns); item card (date-range history); movements register + entry detail + undo; low stock; masters
- [x] A.5 `make_sample_exports.py` (XlsxWriter) → 4 neat `.xlsx` files; Export buttons download them; read back to verify formatting
- [x] A.6 Playwright walkthrough (desktop + phone, zero JS errors) → serve on localhost for review

### Step A2: redesign as a modern admin dashboard (user's choice) ⛔ approval gate
- [x] Tabler layout (sidebar, top bar with global search, low-stock bell, user menu), KPI cards, weekly IN vs OUT chart (CVD-validated colours, table view), sortable and paged tables, Tabler forms with pill choices, modals and toasts
- [x] Walkthrough passes (desktop + phone, zero JS errors), now also covering global search, column sorting, paging and the phone menu

### Step B: build (after approval)
Plan: `docs/superpowers/plans/2026-10-11-stock-system.md` (12 tasks). Executed with subagent-driven development: one implementer per task, then a spec review and a code-quality review. Local tests use the pgserver Postgres 16 (scratchpad `pgdata2`).
- [x] Task 1 Skeleton: a36dfd1 + review fixes a4e3e7d (3 tests pass; spec ✅ quality ✅)
- [x] Task 2 Accounts, roles, login, static, admin: fd14283 + review fixes 516425c (16 tests; spec ✅ quality ✅)
- [x] Task 3 Masters, Item, code normalisation: 5c39213 + integrity fixes 37fdba7 (32 tests; spec ✅ quality ✅)
- [x] Task 4 Ledger models + posting services: 2843d36 + validation fixes 79227a4 (72 tests incl. 2-thread oversell; spec ✅ quality ✅)
- [x] Task 5 Item services: 965cbc9 + review fixes b135ef9 (89 tests; spec ✅ quality ✅)
- [x] Task 6 Layout + dashboard: 9188adf + review fixes 5b9cbe4 (104 tests; 0 JS errors; spec ✅ quality ✅)
- [x] Task 7 Current stock / movements / low stock lists: 9ddadc4 + review fixes 6009b20 (130 tests; fits 1366px; spec ✅ quality ✅)
- [x] Task 8 Items list, form, item card: 6f1d045 + review fixes e0a3304 (156 tests; 0 JS errors; spec ✅ quality ✅)
- [x] Task 9 Entry forms, entry detail, undo: 93bf29d + review fixes 2aac19b (197 tests; 23-step browser walkthrough, 0 JS errors; spec ✅ quality ✅). Known limit: two truly simultaneous POSTs of one form could both save (button guard + session token cover double-clicks).
- [x] Task 10 Excel exports: 4bdf48a + review fixes edb588b (217 tests; formula/URL injection blocked; spec ✅ quality ✅)
- [x] Task 11 Masters page, global search, permission sweep: 0a8a3a0 + review fixes cbb2891 (286 tests; every route guarded; spec ✅ quality ✅)
- [x] Task 12 Demo data, e2e walkthrough, docs: d487777 + review fixes c471396 (294 tests; spec ✅ quality ✅; walkthrough re-run twice, both exit 0; seed refuses without --force when DEBUG is off; `seed_stock_demo` loads 28 items and 35 entries with the demo file's exact numbers and no balance drift; `e2e/walkthrough.py` exits 0 with 0 JS errors at 1366px and 390px; `check --deploy` only warns about HSTS preload)
- Step B is built and pending the user's review.

### Step A result (2026-10-11): mockup ready, waiting for the user's approval ⛔
- Open: http://localhost:8080/mockups/stock/ (run `python -m http.server 8080` from the repo root). Sample exports are in `mockups/stock/exports/`.
- Evidence: `mockups/stock/walkthrough.py` (Playwright, desktop + phone) passes with zero JS errors. It covers:
  - Stock IN with an old spelling and a new item created inline;
  - an over-issue shown live and refused;
  - a transfer (same-location refused);
  - an adjustment (reason required, difference shown);
  - undo (reason required, stock restored);
  - a look-alike duplicate item refused, then a new item saved;
  - filters and the item-card date range;
  - all 4 export files served.
- Exports were read back with openpyxl and each has: company/title/filter rows, a styled table (TableStyleMedium2) with filter buttons, frozen header, real dates in dd-mm-yyyy, A4 landscape fit-to-width, repeated header row, and auto-fit widths.
- [x] Final whole-branch review: fixes b4fc55e (305 tests; item deactivate/unit guards, backdated-stock check, low-stock Stock IN button + unit, dashboard links, movements search on old spellings). TRUNCATE trigger deliberately not added (breaks test DB flush); see models.py comment.

## Defective pieces + Complaints (branch `service-modules`, started 2026-10-12)
Spec: `docs/superpowers/specs/2026-10-12-defectives-complaints-design.md`. Approved in brainstorming after the user's correction that Wipro is just one company (see lessons).
- [x] Prior-art research (InvenTree Return Order, Odoo Repair, django-helpdesk, OCA/rma). Verdict: build ourselves, borrow patterns only.
- [x] Clickable mockup `mockups/service/`, one linked app with Stock, Complaints and Defectives, commit 2b5c8be. Walkthrough exits 0 with 0 JS errors and covers 11 flows plus the phone layout. Exports were read back with openpyxl. No company is hard-coded.
- [x] User approved the mockup (2026-10-12: "yes it is good enough")
- [x] Implementation plan `docs/superpowers/plans/2026-10-12-defectives-complaints.md` (18 tasks, 119b2ca; self-reviewed against the real code; demo replay simulated with 107 actions and 0 errors)
- [ ] Build with subagent-driven development (Postgres now on port 61579; it may move after a reboot, so check `scratchpad/pgdata2/postmaster.pid` line 4)
  - [x] S1 Defective store location + entry subtypes: deac8d2 + fixes 0fbeade (323 tests; spec ✅ quality ✅)
  - [x] S2 Good stock excludes the Defective store: 0c0a23b + fixes acd8aef (342 tests; fits 1366px; spec ✅ quality ✅)
  - [x] S3 Counter, defectives models, batch link: 26da1e8 + DB constraints 49df2cc (359 tests; spec ✅ quality ✅)
  - [x] S4 Piece services (create, mark defective, scrap): 4fc893e + fixes fda69cc (407 tests; spec ✅ quality ✅)
  - [x] S5 Batch services (create, add, remove, dispatch, settle): 7f2b895 + settle deadlock fix de0ecc0 (433 tests; spec ✅ quality ✅)
  - [x] S6 Shared line editor + Mark defective page: 3d21107 + follow-ups bf04da1 (463 tests; walkthrough exit 0; spec ✅ quality ✅)
  - [x] S7 Return batch screens + piece card: 431f72f + fixes 4ee901b (527 tests; token replay fixed app-wide; spec ✅ quality ✅)
  - [x] S8 Pieces list + bulk actions: 94c9a46 + fixes 98705c5 (557 tests; spec ✅ quality ✅). Final review: tighten the 30-piece bulk-add query guard (80 is loose)
  - [x] S9 Defectives dashboard + 2 exports: 55d37be + fixes 8ea4969 (581 tests; spec ✅ quality ✅)
  - [x] S10 Complaints models + links: 851d64c + integrity fixes 56d38f8 + landline phones 56f3a92 (624 tests; spec ✅ quality ✅)
  - [x] S11 Complaints services: acc1821 + fixes 785f6ba + post_entry hardening 5e7692b (685 tests; deadlock-free lock order verified; spec ✅ quality ✅)
  - [ ] S12 New complaint + complaint page
  - [ ] S13 Record visit page
  - [ ] S14 Complaints list, dashboard + 2 exports
  - [ ] S15 Sites & technicians screens
  - [ ] S16 Integration (nav, search, dashboard, links, sweep)
  - [ ] S17 Service demo data
  - [ ] S18 Walkthrough, docs, todo

### Brief notes for the remaining service tasks (from reviews; give these to each implementer)
- Postgres for tests: `postgresql://postgres:@127.0.0.1:61579/postgres`. Any `transaction=True` test needs `serialized_rollback=True`.
- **Lock order** (top of `apps/defectives/services.py`): ReturnBatch row → pieces in tag order → `post_entry` → `next_number(s)`. Exception to document: a document's *own* new number (RB / VIS / CMP) may be taken first.
- **Task 5:**
  - After `_lock`, call `_check_after_history(pieces, date, what="…")`.
  - Use `_move_all` + `bulk_update`.
  - `add_pieces` must clear `outcome=""` and `settled_on=None`; the history stays on BatchLine.
  - Respect the defectives/0002 DB constraints.
- **Task 11** `record_visit`:
  - Collect failed parts with `collect_pieces(entry=…, item, qty, source=SITE_VISIT, collected_on=visit_date, user, batch_code, pkd, fault, visit=visit, note=…)`, one call per line, not one `create_piece` call per piece.
  - Cap visit lines at 200 pieces.
- **Task 13:** add `visit=None` to `collect_pieces` (passed into the `bulk_create`) and to `create_piece`.
- **Task 17:**
  - Replay the demo in date order.
  - Re-seed `svkml_demo` fresh: it holds test-only MARK_DEFECTIVE entries with no pieces.
- **From Task 5:**
  - Service signatures:
    - `create_batch(*, company, user, pieces=(), note="", created_on=None)`
    - `add_pieces` / `remove_pieces(*, batch, pieces, user, at=None)`
    - `dispatch(*, batch, dispatched_on, courier, docket_no, user)`, which returns the entry
    - `settle(*, batch, pieces, outcome, settled_on, user, to_location=None)`, which returns the entries
  - Forms must cap courier at 60 characters, docket at 40 and note at 200; the services refuse longer values rather than truncating.
  - Read each batch's answers from `BatchLine`: a piece's `outcome` is empty while it is in a draft or sent batch.
  - Task 17 must pass every date in order.
- **Settle (after de0ecc0):**
  - `settle` posts **one entry per call** and returns `[entry]` or `[]`.
  - One replacement entry can belong to several pieces and items; use `entry.replaced_pieces` and `entry.settled_lines`.
  - Batch detail should group lines by entry.
  - The Task 17 replay calls `settle` once per (batch, outcome, date, location) group.
- **Rule:** at most one `post_entry` per service call. **Task 11 `record_visit` breaks it:** it posts the parts-given OUT and the collected IN in one transaction. The implementer and reviewer must check that this order can't deadlock against Stock IN/OUT, mark_defective and settle, and either document why it is safe or restructure it.
- **Line editor (after bf04da1):**
  - Task 13 puts the `out` and `collect` editors in one `form[data-lines-form]` with a single `[data-form-error]`, each with its own `data-initial` and `data-summary` id. See the header comment in `static/js/line-editor.js`.
  - Remove each built screen from `UNBUILT` in `tests/core/test_tags_and_nav.py`.
  - The Mark defective step is in `e2e/walkthrough.py`.
- **Follow-up after Task 13:** merge `static/js/entry-form.js` into `LineEditor` (in/trf/adj modes), or at least share `esc`/`norm`/`lookKey`.
- **Brand subtitle:** change "Stock" to "Service", as in the mockup. That belongs in Task 16.
- **Tokens (after 4ee901b):** every write view uses `apps.core.tokens.guarded_post(request, run)`, and pages get their token with `page_token(session, path)`; `new_token` no longer exists. A replay counts only when the same action is posted again (fingerprint of path + POST). Add `@never_cache` to form pages. Defectives views are now a package: `apps/defectives/views/{marking,batches,pieces,common}.py`. `pieces_by_tag` refuses unknown tags.
- **From Task 9:**
  - Task 10 must fill `apps.defectives.selectors.complaint_cells` (the complaint number and the company complaint number for the dispatch list), and the complaint link in `templates/defectives/_source.html`.
  - `UNBUILT` is now an empty set.
  - Outcome counts come from `BatchLine`.
- **Task 16:**
  - `service_stats` must import `defectives.selectors.piece_counts()`; don't recount pieces.
  - Use the date-window convention `__gt=today - N days`.
  - The defectives chart ids are prefixed `def-chart-*`.
  - `workbook_response(filters_label=…)` exists.
- **From Task 10:**
  - The user chose **mobile or STD landline** for site and complaint phones; technicians stay mobile-only. Use `apps/complaints/phones.normalise_phone`.
  - Undo now refuses any entry linked to a complaint, so **Task 11 needs a `undo_visit_parts(visit, reason, user)` service, and Task 13 needs an "Undo parts given" button on the complaint page.** The service posts the reversal with `complaint=` set, so it stays linked and shows on the complaint, and logs a complaint event. Without these, staff can't correct a visit's parts. The spec allowed undoing a visit's parts; this keeps that, just from the complaint page.
  - `change_status(at=…)` must refuse a date before `reported_on` with a friendly message; the database enforces it too.
  - Technicians go through `ComplaintTechnician` and `VisitTechnician` (PROTECT on technician).
  - Visits can't be deleted.
- **From Task 11** (acc1821):
  - **Service signatures:**
    - `record_visit(*, complaint, visit_date, technicians, work_done, next_status, user, location=None, parts=[(item, qty)], collected=[(item, qty, batch_code, pkd, fault)])`
    - `undo_visit_parts(*, visit, reason, user, at=None)`, which returns the REV entry
    - `change_status(*, complaint, to, user, note="", reason="", at=None)`
    - `reopen(*, complaint, user, note, at=None)`, Admin only
    - `close_not_covered`
    - `save_site(*, data, site=None)`
    - `save_technician(*, name, phone="", technician=None)`
    - `file_complaint(..., contact_name=None, phone=None)`, where None means "copy from the site"
  - **Task 12/13 complaint page:**
    - Show the REV undo on the timeline or visits (`visit.out_entry.reversed_by`).
    - The "Undo parts given" button hides when there is no OUT or it is already reversed.
    - The entry page's notice for a REV with a complaint may need different wording.
    - Forms offer only active sites and technicians, and `file_complaint` / `record_visit` refuse a hidden one: "{name} is hidden. Show it again in Sites (or Technicians), or choose another."
  - A status change can't be dated before the complaint's latest event.
  - Tests: use your own `DATABASE_URL` database name if another run is using `test_postgres`.
- **From the Task 11 spec review:**
  - Task 15's plan test expects "Phone must be a 10-digit mobile number." for a *site*. Site phones now allow landlines, so assert the new message ("…or an STD landline like 0891-2345678.").
  - Task 13 must keep the plan's view-level message "Failed parts collected: Line 1: choose an item. Nothing was saved." (from `entry_lines`).
  - `undo_visit_parts` records the undo as a REV entry linked to the complaint, not as a ComplaintEvent (events are status moves only). The complaint page shows it from `visit.out_entry.reversed_by`.
- **From the Task 11 review fixes:**
  - `reverse_entry` is now `_reverse_entry` (private; only `undo_entry` and `complaints.undo_visit_parts` call it). It refuses defectives-owned entries unless they belong to a complaint visit, and takes `used_message=`.
  - `lock_balances(lines)` returns a `LockedBalances`; pass it to `post_entry(locked=…)`, which must cover every row and re-locks them (never waits; never reads unlocked). `record_visit` does this, so every balance lock comes before the first EntryCounter.
  - A visit's entries carry the site name cut to `StockEntry.party`'s 120 characters; the `ref` (complaint number) is the link.
  - New message: "The parts given on VIS-xxxx have already been used, so they can't be undone." (a guard: an OUT's reversal only adds stock).
