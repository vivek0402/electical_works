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

## Phase 2: Items + legacy import + Fresh/Defective lists
- [x] 2.1 `Item`, `ItemAlias` (unique normalised code/alias, pg_trgm GIN index, item_type, is_active); admin
- [x] 2.2 `normalise_code()`, `search_key()`, `parse_qty()` + unit tests with every messy value
- [x] 2.3 `StockDocument`/`StockMovement`/`StockBalance` + constraints + pgtrigger Protect; `post_document()`; selectors; `rebuild_stock_balances`; full posting-core tests (incl. concurrency + DB-level immutability)
- [ ] 2.4 Parsers: header-row detection, 3 file readers → row dicts with source refs
- [ ] 2.5 Type inference (column + prefix rules + generic keywords), conflicts recorded
- [ ] 2.6 Clustering: strong (same search_key) + weak (rapidfuzz ≥ 90, same type); `/` rows → Alternatives
- [ ] 2.7 Complaint parsing (review only): visits, mixed dates, status precedence, phones, cities, customer/site split
- [ ] 2.8 `import_legacy --review` → `data/legacy/import_review.xlsx`
- [ ] 2.9 `import_legacy --apply <reviewed.xlsx> [--dry-run]` (idempotent; doc ref derived from the sheet's title date, e.g. `LEGACY-2026-05-25`) + summary
- [ ] 2.10 Importer tests on fixture xlsx built from the real messy rows (fake phones) + re-run idempotency
- [ ] 2.11 Fresh List / Defective List views (tables2 + filter, paginated) + Excel export in their layouts
- [ ] 2.12 View tests: role access, filters, export layout
- [ ] 2.13 **Verify + demo data:** review on the sample files → apply in dev (`make demo`) → lists in the browser; totals reconcile with the sheet sums

## Decisions (2026-10-11)
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
