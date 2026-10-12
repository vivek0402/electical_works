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
- [ ] Implementation plan (writing-plans): defectives first, then complaints
- [ ] Build with subagent-driven development
