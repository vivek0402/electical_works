# Todo

Approved plan: `C:\Users\vivek\.claude\plans\pasted-content-id-3f22-0-your-jazzy-pancake.md` (2026-10-11).
Tick an item only with evidence (tests pass, server runs, feature works end to end).

## Phase 1: Skeleton
- [x] 1.1 `git init`, `.gitignore` (incl. `data/legacy/*.xlsx`, `.env`), copy the 3 xlsx into `data/legacy/`
- [x] 1.2 `tasks/todo.md`, `tasks/lessons.md`, `CLAUDE.md`
- [x] 1.3 `pyproject.toml` + `uv.lock` with pinned deps; ruff + pytest config
- [x] 1.4 `config/` settings split base/dev/prod/test (django-environ); Asia/Kolkata, DD-MM-YYYY; `.env.example`
- [x] 1.5 Apps under `apps/`: core, accounts, inventory, complaints, defectives, legacy_import, reports
- [x] 1.6 `Dockerfile` (python 3.12-slim, uv, non-root) + `compose.yaml` (web + db postgres:16, healthcheck)
- [x] 1.7 `Location` model + admin; data migration seeding Svkml, Vizag Office, TV Shop, Kartika Class
- [x] 1.8 Roles: Groups ADMIN/OFFICE/TECHNICIAN + permissions (synced after every migrate); `role_required`; `Profile.home_location`
- [x] 1.9 `seed_demo` command: admin, office user, technicians Ramu and Apparao (passwords from env, idempotent)
- [x] 1.10 Login/logout, base layout (Pico, big tap targets, role nav), `/healthz`
- [x] 1.11 Django Admin branding + Location/User admin
- [x] 1.12 Makefile: up, down, migrate, seed, test, lint, shell (import-review/apply targets used from Phase 2)
- [x] 1.13 pre-commit (ruff) + GitHub Actions CI: `test` job (postgres:16 service) + `compose` job (make up/migrate/seed/test + healthz)
- [x] 1.14 Tests: seed idempotent, groups exist, role gating, login flow, healthz
- [x] 1.15 **Verify:** `make up` → `make migrate seed` → `make test` green → log in as each role

## Three systems (approved 2026-10-11): Stock · Defective Pieces · Complaints, one app, linked
Plan file: see "Approved plan" at the top of this file (same path, updated 2026-10-11).

### Step M: Clickable mockup of all 3 systems ⛔ approval gate for every real screen
- [x] M.1 `mockups/app/` shell: index.html, core.js (data, ledger, lookup, router, helpers), three-tile home, role switch (Office/Ramu)
- [x] M.2 System 1 Stock screens moved from stock-app.html; defective options handed to System 2
- [x] M.3 System 2 Defective pieces: dashboard, bulk record (N tagged pieces), pieces list/detail timeline, return batches (Wipro print, mark sent, per-piece result, receive replacement), move pieces, reports
- [x] M.4 System 3 Complaints: list with status tabs + ageing, new complaint, detail + status stepper + close reason, add visit (parts used + defectives collected), technician "My complaints", AP Pending report
- [x] M.5 Seed from sample sheets (18 complaints with fake phones, pieces from the defective list); delete stock-app.html
- [x] M.6 Playwright walkthrough of the cross-system flow (desktop + phone, zero JS errors, defective invariant after every step) → serve at localhost:8080/mockups/app/ for review

### Step M2: Everything Wipro (and others) can send (approved 2026-10-11) ⛔ same approval gate
- [x] M2.1 core.js: item units (NOS/MTR/ROLL/BOX/PKT) + non-Wipro wire item; RECEIVED_FROM_SUPPLIER; piece outcomes REPLACED (any item) / REPAIRED / CREDITED / REJECTED + Wipro notes; matchReplacements with per-line capacity; batch PARTLY_SETTLED
- [x] M2.2 stock.js: Stock IN from Wipro / other supplier / opening; "match replacements" prompt after a Wipro receipt; units in lists and messages
- [x] M2.3 defectives.js: Match-replacements screen; batch actions (Replaced with editable item + extra items, Repaired, Credit note, Rejected, Wipro note); progress "x of y answered"; outcome-mix report
- [x] M2.4 Seed all four cases; extend walkthrough (different item, partial, repaired, credit note, extra stock, wire in MTR); zero JS errors, invariant holds

### Phase 2: item master + ledger core (done on `phase-2`)
- [x] 2.1 `Item`, `ItemAlias` (unique normalised code/alias, pg_trgm GIN index, item_type, is_active); admin
- [x] 2.2 `normalise_code()`, `search_key()`, `parse_qty()` + unit tests with every messy value
- [x] 2.3 `StockDocument`/`StockMovement`/`StockBalance` + constraints + pgtrigger Protect; `post_document()`; `rebuild_stock_balances`; full posting-core tests (incl. concurrency + DB-level immutability)

### Phase 2A: Stock system screens (after mockup approval)
- [ ] Stock IN / OUT / Transfer / Undo views on existing services (HTMX line rows, item picker with alias + trigram search, create-item inline)
- [ ] Current stock (Fresh / Defective / Low) + Excel export in their layout; item card with history; register
- [ ] `make demo` seeds demo entries; view + permission tests

### Phase 2B: Legacy loader (sample sheets → demo data)
- [ ] Parsers (header-row detection), type inference (column + prefix rules), clustering (strong/weak), complaint parsing
- [ ] `import_legacy --review` → import_review.xlsx; `--apply` (idempotent; ref from sheet title date); opening defectives become pieces (after Phase 3 models)
- [ ] Importer tests on the messy sample rows

### Phase 3: Defective Pieces system
- [ ] DefectivePiece, DefectiveEvent, ReturnBatch; transitions map; bulk record; move pieces; Wipro print/export; outcomes + replacement link; reports
- [ ] Invariant check: DEFECTIVE qty == pieces AT_OFFICE + IN_RETURN_BATCH (command + tests)

### Phase 4: Complaints system
- [ ] Customer/Site, Complaint, Visit, Event; filing; visits issue stock + create pieces; guarded statuses + closure; technician view; AP Pending report + export; legacy complaints import

### Phase 5: Dashboard + hardening · Phase 6: Go-live (as in the original brief)

## Decisions (2026-10-11)
- **Always build mocks** (user rule): a clickable UI mockup is approved before each screen is built, and every feature ships demo data via `make demo`. This applies to every later phase.
- The Excel files are reference + demo data, not the production dataset. Build a generic importer (any file in these layouts) and load the samples as demo data. Samples are committed to the private repo.
- Repo: github.com/vivek0402/electical_works (private). CI: `test` + `compose` jobs.

## OPEN QUESTIONS (defaults in use until answered)
| Question | Blocks | Default |
|---|---|---|
| Q2 Where does the 25-05-2026 snapshot physically sit? | 2.9 | Vizag Office (`--location`) |
| Q10 Exact user list and names | 1.9 | admin + office + Ramu + Apparao |
| Is an `A/B` row one interchangeable item or two items? | 2.9 | one item, 2nd code as alias |
| Client approval of merges/types in `import_review.xlsx` | 2.9 (real data) | nothing merged until approved |
| Fresh List export layout: 25-5-2026 snapshot (7 columns) or store template? | 2.11 | snapshot layout |
| "material at office": MATERIAL_TO_CHECK or AWAITING_MATERIAL? | Phase 4 load | MATERIAL_TO_CHECK |

## Review
### Phase 1 (2026-10-11): DONE
- Evidence (run against a disposable Postgres 16.2, because Docker isn't installed yet): `pytest` 17 passed with 96% coverage; `ruff` clean; `manage.py check` clean; `makemigrations --check` shows no changes; `check --deploy` leaves 1 deliberate warning (HSTS preload, decide in Phase 6); the location seed migration reverses cleanly; `seed_demo` re-run is idempotent.
- Live walkthrough: /healthz 200; anonymous / → /login/; admin/office/ramu/apparao each log in and see their role; only admin sees and opens /admin/ (others → 302); a wrong password shows a friendly error; vendored static files return 200.
- Root-cause fixes: `.gitattributes` forces LF (git autocrlf would have broken scripts in containers); vendored JS/CSS are excluded from pre-commit.
- Docker verification is done in CI (repo github.com/vivek0402/electical_works, private). The `compose` job runs `make up → migrate → seed → test`: 17 passed, healthz ok. The `test` job is green too. A local Docker Desktop install is still recommended for day-to-day dev, but no longer blocks anything.

### Phase 2 progress (2026-10-11): 2.1–2.3 done
- CI on postgres:16: 80 passed. Coverage: services 98%, normalise 100%, models 95%. The Postgres log shows every DB guard firing in its test (code check, unique opening ref, pgtrigger append-only, non-negative balance).
- `search_key` is a stored generated column (SQL twin of `normalise.search_key`); a parity test keeps the two in sync.
- Local test runs use CI, because the throwaway Windows Postgres lacks pg_trgm. Docker Desktop would give a local loop.

### Step M (2026-10-11): 3-system mockup built, waiting for approval ⛔
- `mockups/app/` (index.html, core.js, ui.js, stock.js, defectives.js, complaints.js, mockup.css), served at http://localhost:8080/mockups/app/
- Evidence: `mockups/walkthrough.py` (Playwright, desktop + phone) passes with zero JS errors. Flow: file complaint (bad phone warns) → technician visit (an over-issue is refused, nothing saved; then 2 parts issued + 2 tagged pieces collected) → return batch → Wipro list → sent → 1 replaced (fresh +1, linked) + 1 rejected → batch SETTLED → close refused without reason, accepted with one. Defective invariant holds after every step.

### Step M2 (2026-10-11): Wipro "other" outcomes in the mockup, waiting for approval ⛔
- Evidence: `mockups/walkthrough.py` passes, zero JS errors, invariant holds. It covers: a Wipro receipt with 3 lines matched to 2 pieces (one a different item), an over-match refused, 10 units left as new stock, batch PARTLY_SETTLED → repaired (fresh +1) → credit note → SETTLED; the batch "Replaced" dialog accepting an old spelling of a different item plus 3 extra LENS; another supplier's 40 MTR of wire, and an over-issue refused with "Only 130 MTR of WIRE 1.5 SQMM".
