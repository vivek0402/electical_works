# Todo

Approved plan: `C:\Users\vivek\.claude\plans\pasted-content-id-3f22-0-your-jazzy-pancake.md` (2026-10-11).
Tick an item only with evidence (tests pass, server runs, feature works end to end).

## Phase 1: Skeleton
- [x] 1.1 `git init`, `.gitignore` (incl. `data/legacy/*.xlsx`, `.env`), copy the 3 xlsx into `data/legacy/`
- [x] 1.2 `tasks/todo.md`, `tasks/lessons.md`, `CLAUDE.md`
- [x] 1.3 `pyproject.toml` + `uv.lock` with pinned deps; ruff + pytest config
- [x] 1.4 `config/` settings split base/dev/prod/test (django-environ); Asia/Kolkata, DD-MM-YYYY; `.env.example`
- [x] 1.5 Apps under `apps/`: core, accounts, inventory, complaints, defectives, legacy_import, reports
- [ ] 1.6 `Dockerfile` (python 3.12-slim, uv, non-root) + `compose.yaml` (web + db postgres:16, healthcheck) — *written; build unverified until Docker Desktop is installed*
- [x] 1.7 `Location` model + admin; data migration seeding Svkml, Vizag Office, TV Shop, Kartika Class
- [x] 1.8 Roles: Groups ADMIN/OFFICE/TECHNICIAN + permissions (synced after every migrate); `role_required`; `Profile.home_location`
- [x] 1.9 `seed_demo` command: admin, office user, technicians Ramu and Apparao (passwords from env, idempotent)
- [x] 1.10 Login/logout, base layout (Pico, big tap targets, role nav), `/healthz`
- [x] 1.11 Django Admin branding + Location/User admin
- [ ] 1.12 Makefile: up, down, migrate, seed, test, lint, shell, import-review, import-apply — *written; needs Docker + make to verify*
- [ ] 1.13 pre-commit (ruff) + GitHub Actions CI (postgres:16 service, ruff, pytest) — *pre-commit passes; CI runs on first push (no remote yet)*
- [x] 1.14 Tests: seed idempotent, groups exist, role gating, login flow, healthz
- [ ] 1.15 **Verify:** `make up` → `make migrate seed` → `make test` green → log in as each role

## Phase 2: Items + legacy import + Fresh/Defective lists
- [ ] 2.1 `Item`, `ItemAlias` (unique normalised code/alias, pg_trgm GIN index, item_type, is_active); admin
- [ ] 2.2 `normalise_code()`, `search_key()`, `parse_qty()` + unit tests with every messy value
- [ ] 2.3 `StockDocument`/`StockMovement`/`StockBalance` + constraints + pgtrigger Protect; `post_document()`; selectors; `rebuild_stock_balances`; full posting-core tests (incl. concurrency + DB-level immutability)
- [ ] 2.4 Parsers: header-row detection, 3 file readers → row dicts with source refs
- [ ] 2.5 Type inference (column + prefix rules + generic keywords), conflicts recorded
- [ ] 2.6 Clustering: strong (same search_key) + weak (rapidfuzz ≥ 90, same type); `/` rows → Alternatives
- [ ] 2.7 Complaint parsing (review only): visits, mixed dates, status precedence, phones, cities, customer/site split
- [ ] 2.8 `import_legacy --review` → `data/legacy/import_review.xlsx`
- [ ] 2.9 `import_legacy --apply <reviewed.xlsx> [--dry-run]` (idempotent, ref `LEGACY-2026-05-25`) + summary
- [ ] 2.10 Importer tests on fixture xlsx built from the real messy rows (fake phones) + re-run idempotency
- [ ] 2.11 Fresh List / Defective List views (tables2 + filter, paginated) + Excel export in their layouts
- [ ] 2.12 View tests: role access, filters, export layout
- [ ] 2.13 **Verify:** review on real files → apply → lists in browser; totals reconcile with the sheet sums

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
### Phase 1 (2026-10-11): code complete, Docker verification pending
- Evidence (run against a disposable Postgres 16.2, because Docker isn't installed yet): `pytest` 17 passed with 96% coverage; `ruff` clean; `manage.py check` clean; `makemigrations --check` shows no changes; `check --deploy` leaves 1 deliberate warning (HSTS preload, decide in Phase 6); the location seed migration reverses cleanly; `seed_demo` re-run is idempotent.
- Live walkthrough: /healthz 200; anonymous / → /login/; admin/office/ramu/apparao each log in and see their role; only admin sees and opens /admin/ (others → 302); a wrong password shows a friendly error; vendored static files return 200.
- Root-cause fixes: `.gitattributes` forces LF (git autocrlf would have broken scripts in containers); vendored JS/CSS are excluded from pre-commit.
- Left: 1.6/1.12/1.15 need Docker Desktop + make; 1.13 CI needs a GitHub remote.
