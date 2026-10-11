# CLAUDE.md

SVKML Electrical Works (Wipro Lighting service partner, Visakhapatnam). We are building a web app with three linked systems: **Stock management**, **Defective pieces tracking**, and **Complaint filing & tracking**.

**Project restarted from scratch on 2026-10-11, at the user's request.** The earlier work is archived in the git tags `archive/main-2026-10-11` and `archive/phase-2-2026-10-11`. It is reference only: do not restore it unless the user asks.

## Session start
1. Read `tasks/lessons.md` and follow every rule in it.
2. Read `tasks/todo.md`.

## Workflow
- Plan anything with 3+ steps in plan mode. Research prior art in a subagent first. Wait for approval.
- **Mock every screen** with proper input controls and get approval before building it. Every feature ships with demo data.
- **The Excel files in `data/legacy/` show what data exists. They are never a UI template.** Use proper forms: date pickers, dropdowns/searchable selects, number inputs, validation. Excel is only an "Export to Excel" download with clean app columns.
- Tick todo items only with evidence. After any correction, add a rule to `tasks/lessons.md`.
