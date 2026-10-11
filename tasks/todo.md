# Todo

## Restart (2026-10-11)
The user asked to undo everything and start over. The old work is archived in git tags `archive/main-2026-10-11` and `archive/phase-2-2026-10-11`.

Kept: the sample Excel files (`data/legacy/`), `LICENSE`, and `tasks/lessons.md`.

### Confirmed with the user so far (still valid)
- Three linked systems in one app: Stock management, Defective pieces tracking (each piece individually), Complaint filing & tracking (filed by staff).
- Wipro can send: a different item as the replacement, a repair, a credit note, "under investigation", partial or mismatched quantities, and extra/new stock. Other suppliers and brands also exist. Each item has a unit (NOS/MTR/ROLL/BOX/PKT), with whole-number quantities.
- Screens are proper data-entry forms (date pickers, dropdowns, number inputs), not copies of the Excel sheets. Excel is a download only.

### Next
- [ ] Plan the restart (plan mode): stack and setup, then mock the data-entry screens with proper controls, and get approval before building
