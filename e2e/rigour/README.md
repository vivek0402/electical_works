# Rigour tests

A repeatable stress and scenario test for the whole app, driven by the legacy Excel files in `data/legacy/`.
Results of the last full run and the defects it found: `tasks/rigour-report.md`.

## Run it
1. Postgres 16 on port 52207 (the pgserver data folder from earlier sessions; see CLAUDE.md for the port).
2. A server on a throwaway database, from the code you want to test:
   `DATABASE_URL=postgresql://postgres:@127.0.0.1:52207/svkml_rigour uv run python manage.py runserver 8001 --noreload`
3. `sh e2e/rigour/run_all.sh 8001`  (about 3 minutes). It rebuilds the data, **drops and recreates `svkml_rigour`**
   (never `svkml_demo`), and writes one report per step to `e2e/rigour/out/`.

Exit 0 and `ALL RIGOUR STEPS PASSED` mean every step passed.

## The steps
| File | What it does |
|---|---|
| `build_scenarios.py` | Reads the Excel files (read-only) and builds `scenarios.json`: about 475 operations with an independent stock model. Seeded, so the same every time. |
| `load_entries.py` | Replays them through the app's real forms over HTTP, in date order, and logs every outcome and its time. |
| `audit.py` | Ledger = cached balances, no negative stock, app stock = the independent model, numbers gap-free, Defective store = pieces. `--no-model` for a ledger-only pass after the abuse tests. |
| `consistency.py` | Dashboard tiles, menu badges and Excel exports against the lists they belong to. |
| `perf.py` | Page times and queries per page, and an N+1 check (10 rows against 50). |
| `scenario_matrix.py` | About 155 business-rule, messy-input and permission cases, each with an expected result decided first. |
| `concurrency.py` | Eight users at once: last units, document numbers, scarce parts, and a double submit. |
| `ui_checks.py` | Playwright 1.63.0: 39 pages at 1366 px and 390 px, the item picker, live warnings, a 25-line entry, search. |

## Notes
- The loader and matrix post forms over HTTP (the server code path is the real one: forms, services, token guard).
  The browser's JavaScript is covered by `ui_checks.py` and the main `e2e/walkthrough.py`.
- `KNOWN_OPEN` in `consistency.py` lists findings that wait for a decision. They are printed, never hidden.
  Delete an entry when it is fixed.
- Output files (`*.json`, `out/`, `shots/`) are regenerated every run and are not tracked by git.
