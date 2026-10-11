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

### Step B: build (after approval)
- [ ] B1 Setup · B2 Masters · B3 Stock engine · B4 Screens · B5 Exports · B6 Demo data (details in the plan)

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
