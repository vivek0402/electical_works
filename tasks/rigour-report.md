# Rigour test report

Run on 2026-10-22 against a fresh database, from commit `9ed006d` plus the harness fixes after it, using
`sh e2e/rigour/run_all.sh`. All eight steps pass. The data comes from the three Excel files in `data/legacy/`.

## What the Excel files gave us
- **Fresh and Defective lists** (about 70 rows each): 108 distinct item codes after ignoring case and spaces.
  Quantities are text (`22 NOS`, `1NOS`, `` `7NOS``). Codes repeat across rows.
- **Pending complaints** (19 rows): bad phones (9 and 5 digits, blanks), words in the wrong status column
  (`Saturday`, `Closed Not wipro product`), odd names (`Chenna Keshava;lu`), technician and date in one cell.
- **Store material list**: four location sheets with **headers only, no data**. Only the location names were usable.
- The files hold patterns, not volume, so the 100-per-kind data set is generated from them with a fixed seed.

## What ran
| Step | Result |
|---|---|
| Load: 475 operations through the real forms (items, techs, sites, 124 stock entries, 100 complaints, 79 visits, 157 defective pieces, 10 return batches) | 475 saved, 0 refused, median 158 ms each |
| Audit against an independent stock model: 19 checks | all pass: 412 item/location cells agree, no negative stock, numbers gap-free, Defective store = pieces |
| Consistency: 36 checks (tiles, menu badge, 9 Excel exports, 10 dispatch lists) | all pass except one tile, listed as F3 |
| Performance: 37 pages | slowest page 97 ms; no query count grows between 10 and 50 rows |
| Scenario matrix: 159 cases | 159 behave as predicted |
| Concurrency: 8 users at once | last units, document numbers and scarce parts hold; the double submit failed before F2 and passes now |
| Browser: 39 pages at 1366 px and 390 px, picker, live warning, 25-line entry, search | all pass, no JS errors |
| Final ledger audit after all the abuse | passes |

Project tests after the fixes: 855 pass (850 before), ruff clean, no migration drift.

## Defects found and fixed
**F1. A refused batch action could be silent.** Dispatching an already-dispatched batch, removing a piece from
one, or settling when every piece was already answered reloaded the batch page with no message, because the form
that was posted is not drawn in that state. The complaint page already handled this. Fixed in
`apps/defectives/views/batches.py`; three regression tests. Commit `8eca1fd`.

**F2. The same form posted twice at the same instant saved twice** (6 of 6 runs; the Back/Save and slow-network
case). The one-time token was spent in the session only after the save. `guarded_post` now also claims the token
in the database inside the saving transaction (`core.TokenClaim`, migration `0002`). The second request waits and
is sent to what the first saved; a refused save rolls the claim back. Two tests, one forcing the race.
Commit `0a8a794`. This was listed as a known limit in `tasks/todo.md`; it no longer is.

## Open findings: need a decision from you
**F3. "Answered by companies, last 90 days" tile (Defectives dashboard).** It counts answered pieces (35) but opens
the batches list, which shows batches (10). Your rule is that a tile must match its list. Options: open a pieces
list filtered to "answered in the last 90 days" (the filter does not exist yet), or count batches. Shown as KNOWN in
the consistency check until you choose.

**F4. A return batch cannot be dispatched on an earlier date than the day it was created.** The app dates a new
batch today and refuses a dispatch dated before that ("can't be before the batch was created"). If the courier took
the parcel yesterday and you record it today, you cannot enter yesterday. It also means old history can only be
entered with today's dates. Decide: allow an earlier dispatch date, or let the batch creation date be edited.

**F5. A failed part collected at a visit may have no fault written** (Mark defective requires one). The dispatch
list sent to the company shows the fault per piece, so blanks go out blank.

**F6. No length limit on free text.** A 5,000-character remark and a 10,000-character complaint fault both saved.
Probably harmless, but long text will make Excel exports and cards ugly.

**F7. No warning for an identical complaint** (same site, fault and day), and a technician may bring back more
failed parts than were given. Both saved. The first is already planned in the smart-features design.

## What worked well (worth knowing)
- The look-alike guard caught 5 near-duplicates in the Excel codes: `EI08437`/`EIO8437` (zero against letter O),
  `...-300`/`...-0300`, `...-65NE3`/`...-65-NE3`, `LG26-048-720`/`LG26-048-0720`, `RI103-092-PA`/`R1103-092-PA`. A
  person would have created these as separate items; the app names the existing one.
- Global search finds `EIO8437` when you type the Excel typo `EI08437`.
- Typing `22 NOS` into a quantity box keeps only the number; if it gets through to the server it is refused.
- No open redirect after login; script text typed into a remark is shown as text; a formula typed as a DC number
  is stored as text in Excel; no page returns a server error for 132 odd query strings.

## Limits of this test
- **Scale:** about 100 entries per kind, as you chose. Pages are fast and do not do extra queries per row, which
  is the usual sign of good scaling, but a real multi-year history is not proven. Say if you want a 1,000-per-kind
  run through the services.
- **Bulk load went over HTTP, not clicking.** The server path is the same (forms, validation, services, token
  guard). The browser behaviour is covered by the 39-page browser pass and the existing `e2e/walkthrough.py`.
- Not tested: printing, real phones, slow networks, other browsers, backups, or the deployed (Docker) setup.
- The tests used Admin and Office accounts only.

## Notes for the next session
- Another session had uncommitted edits in `apps/inventory/` (forms, masters, services, urls) while this ran. They
  were not touched or committed here. The suite ran from an isolated git worktree of committed code.
- `svkml_demo` was not changed. The rigour database is `svkml_rigour`.
- The test data I gave you earlier used spare type "PCB" and fitting "Panel light"; in the app they are
  "PCB / LED module" and "Panel".
