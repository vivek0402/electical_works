# Lessons

Read at the start of every session. Each entry: the pattern I got wrong, then the rule that prevents it.

## 2026-10-11 — Plan without prior-art research
- **Pattern:** I presented an architecture plan built only from the brief and the legacy files. The user rejected it twice: first asking for internet research on existing systems, then for GitHub projects to use as reference.
- **Rule:** Before presenting any architecture or module plan, research prior art in a subagent: open-source systems (ERP/FSM/inventory), GitHub repos (stars, last push, licence) and relevant libraries. Put the build-vs-reuse verdict and the borrowed patterns into the plan. Note licence limits (AGPL/GPL = ideas only, no code).

## 2026-10-11 — Always build mocks (standing rule from the user)
- **Pattern:** I went straight from plan to implementation for user-facing work.
- **Rule:** (1) Before building any screen, make a clickable HTML mockup in `mockups/` (fake data, no backend, same Pico styling as the app) and get the user's approval. Only then build the real view. (2) Every feature ships with realistic demo data loaded by `make demo`, so the app is always demoable without real client data.
