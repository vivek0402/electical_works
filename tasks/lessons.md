# Lessons

Read at the start of every session. Each entry: the pattern I got wrong, then the rule that prevents it.

## 2026-10-11 — Plan without prior-art research
- **Pattern:** I presented an architecture plan built only from the brief and the legacy files. The user rejected it twice: first asking for internet research on existing systems, then for GitHub projects to use as reference.
- **Rule:** Before presenting any architecture or module plan, research prior art in a subagent: open-source systems (ERP/FSM/inventory), GitHub repos (stars, last push, licence) and relevant libraries. Put the build-vs-reuse verdict and the borrowed patterns into the plan. Note licence limits (AGPL/GPL = ideas only, no code).

## 2026-10-11 — Always build mocks (standing rule from the user)
- **Pattern:** I went straight from plan to implementation for user-facing work.
- **Rule:** (1) Before building any screen, make a clickable HTML mockup in `mockups/` (fake data, no backend, same Pico styling as the app) and get the user's approval. Only then build the real view. (2) Every feature ships with realistic demo data loaded by `make demo`, so the app is always demoable without real client data.

## 2026-10-11 — Mocked a report instead of the core workflow
- **Pattern:** My first mockup showed only the read-only Fresh/Defective lists (the Excel replacement). The user corrected me: this is a stock management system where users **enter stock IN and OUT** and track it.
- **Rule:** Mock and build the primary *data-entry* workflow first (what users do every day: stock in, stock out, transfer, undo), then the tracking views (current stock, item history, register). Reports and exports come last. Before any mockup, write down the 3–5 actions a user performs daily and make sure each one is clickable in the mockup.

## 2026-10-11 — Copied the Excel sheets instead of designing a data-entry app
- **Pattern:** My mockups reproduced the client's spreadsheets: the same column names (S.NO | FITTING CODE | DRIVER CODE | PCB CODE | QUANTITY), codes placed in type columns, dates typed as DD-MM-YYYY text, and sheet-shaped lists and exports. The user: "Don't copy what was there in the Excel sheet… put input boxes so users can enter data, dropdowns, date calendars, quantity digits."
- **Rule:** The Excel files are only evidence of *what data exists*, never a UI template. Design proper forms. Use a date picker (`type="date"`) for every date; dropdowns or searchable selects for every known value (items, locations, customers, technicians, statuses, reasons); number inputs (`type="number"`, min/step) for quantities and amounts; labelled inputs with validation. Lists show clean app columns (Item, Type, Location, Qty), never sheet columns. This overrides the brief's "feel like their Excel" line unless the user says otherwise.

## 2026-10-11 — Reused the same frontend design every time
- **Pattern:** Every mockup used the same look (Pico CSS, dark-blue top bar, cards), because the brief mentioned Pico. I never offered alternatives or asked about the visual style. The user: "why are you following particular frontend design again and again?"
- **Rule:** Visual design is the user's choice, not a default. Before mocking screens, show 2–3 clearly different design directions (layout, navigation style, colours, density, component library) on the same sample screen, or ask for a reference app or style. Build only in the chosen direction, and record it in CLAUDE.md.

## 2026-10-12 — Treated Wipro as the only company
- **Pattern:** My design for defectives and complaints hard-coded Wipro: "return batches to Wipro", "Wipro complaint no.", "Closed – not a Wipro product", "the sheet Wipro expects". The user: "Wipro is just one of the providers, you are using wipro in everything, correct that."
- **Rule:** Wipro is one company among several (Company master: Wipro Lighting, Havells, Finolex, …). Never name a specific company in models, statuses, labels or screens. Use the Company master instead: returns go to the item's company (or a company you pick), complaints record which company's product it is, the company's own ticket/claim number is a generic optional field, and exits read "Not covered" with a reason. A company-specific value is allowed only as a configurable default (like DEFAULT_COMPANY).
