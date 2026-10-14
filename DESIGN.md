# Design System: SVKML Stock

## Product Context
- **What this is:** Stock management for SVKML Electrical Works (a Wipro Lighting service partner, Visakhapatnam): stock IN/OUT, transfers, count corrections, stock by location, Excel exports, plus the Complaints and Defective pieces modules in the same app (since 2026-10-12; the app is branded "SVKML Service").
- **Who it's for:** Admin and office staff with low tech comfort, mostly on desktop, sometimes on phones.
- **Project type:** Internal web app with an admin-dashboard layout.
- **Memorable thing:** "Calm, serious business software where colour always means something."

## Aesthetic Direction
- **Direction:** Industrial/utilitarian, modern admin dashboard (user's choice): left sidebar, top search bar, white cards, sortable and paged tables.
- **Decoration:** Minimal. Colour carries meaning, never decoration.
- **UI kit:** Tabler 1.6.1 + Tabler Icons 3.49.0, Tom Select 2.6.2 (Bootstrap 5 CSS), ApexCharts for charts. django-unfold for the Django admin.

## Color: Navy & Amber (chosen by the user, 2026-10-11)
- **Approach:** Restrained. One brand blue, neutrals, and meaning colours (IN, OUT, alerts). Everything else is quiet.

| Role | Hex | Use | Contrast |
|---|---|---|---|
| Sidebar (navy) | `#0f2744` | Left menu background | text `#c9d6e8` on it 10.2:1; section labels `#8ea3bf` 5.8:1 |
| Brand accent (amber) | `#f5b301` | **Logo mark only** (the bulb, the lighting trade) | navy icon on amber 8.1:1 |
| Primary (brand blue) | `#1f5fbf` | Primary buttons, links, active page, focus, KPI icons on `#e8eef8` | white text 6.1:1 |
| Primary hover | `#1a51a3` | Hover/pressed | |
| Page background | `#f4f6fa` | Behind cards | body text `#1f2937` 13.6:1 |
| Surface | `#ffffff` | Cards, tables, inputs | muted text `#5b6b80` 5.4:1 |
| Border | Tabler default (`#e6e7e9`-ish) | Cards, inputs | |

**Meaning colours (identical in every module):**

| Meaning | Marks/charts | Buttons (white text) | Tint (badges/backgrounds) |
|---|---|---|---|
| **Stock IN** | `#2a78d6` | `#2268c0` (5.5:1) | `rgba(42,120,214,.12)` with text `#1f5fae` |
| **Stock OUT** | `#eb6834` | `#c2410c` (5.2:1) | `rgba(235,104,52,.14)` with text `#a8441b` |
| Needs attention (low stock, errors, undo) | `#d63939` (Tabler red) | Tabler `btn-danger` | `#fde8e8` with text `#b42318` |
| OK / success | Tabler green | | `#e7f6ec` with text `#1e7e34` |
| Transfer / adjustment / neutral | slate | white "quiet" button with blue icon | `rgba(71,85,105,.12)` with text `#334155` |

- The **IN/OUT chart pair** (`#2a78d6` / `#eb6834`) passed the colour-blindness validator: worst adjacent CVD ΔE 24.7, normal-vision ΔE 33.6. Green/orange **failed** (deutan ΔE 5.5), so never use green for IN.
- The **button pair** (`#2268c0` / `#c2410c`) also passes the CVD check (ΔE 25.0), and both pass WCAG AA with white text.
- **Rules:**
  - Never use purple or other decorative colours for actions.
  - Secondary actions (Transfer, Adjust, Cancel) are white "quiet" buttons.
  - Status always pairs colour with an icon or word, never colour alone.
- **Status pills** (complaints, pieces, batches, outcomes) are tinted badges with an icon and a word, never colour alone. Five tints (`.st-*` in `static/css/app.css`): `st-alert` red `#fde8e8`/`#b42318` (Not attended, Urgent, rejected outcomes); `st-wait` amber `#fef3c7`/`#854d0e` (Awaiting material, High, Sent/Dispatched, Partly settled); `st-ok` green `#e7f6ec`/`#1e7e34` (Resolved, Settled, Replaced, Repaired); `st-neutral` slate `rgba(71,85,105,.12)`/`#334155` (Attended, Material need to check, In store, Draft); `st-done` grey `#eef0f3`/`#475569` (Closed, Not covered, Scrapped).
- **Defective store:** shown next to stock as its own shaded column (dashed left border, "not counted" under the heading; a recycle icon marks it in Movements), never part of a total or low-stock check.
- **Excel exports:** company title in navy `#0F2744`, header in Excel's "Table Style Medium 2" (blue).
- **Dark mode:** not in v1.

## Typography
- Tabler's default sans-serif stack (system UI fonts), monospace for item codes and entry numbers, tabular figures for quantities. Not reviewed yet; the user asked only about colours. Revisit if wanted.

## Spacing, Layout, Motion
- Tabler defaults: 4px base, comfortable density, cards with `row-cards` gutters, `container-xl`.
- Large tap targets: quick-action buttons at least 4.5rem tall; form controls are Tabler's standard size.
- Motion: minimal and functional (Bootstrap modal/collapse transitions only). Charts have animations off.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-10-11 | Modern admin dashboard on Tabler | User chose it over Pico/minimal. No build step, complete components |
| 2026-10-11 | IN blue / OUT orange | Green/orange failed the CVD check; blue/orange passes |
| 2026-10-11 | Deeper IN/OUT button shades | White text on `#eb6834` was 3.2:1 (fails AA); `#c2410c` is 5.2:1 |
| 2026-10-11 | Palette **A · Navy & Amber** | User picked it from 3 live options (A Navy & Amber, B Slate & Teal, C Clean light). The brand blue matches IN, navy reads as trustworthy, amber nods to lighting |
| 2026-10-11 | Restraint: colour only for meaning | The first version used 6+ loud colours (purple Adjust, rainbow KPI icons) and looked like a template |
| 2026-10-12 | Defective store column is shown but never counted | Failed pieces must stay visible next to stock (so nothing is lost) but must never inflate good stock, totals or low-stock checks. Pickers and totals use `Location.objects.good()` |
| 2026-10-12 | Status pills: five tints, always icon + word | Seven complaint statuses plus piece, batch and outcome states needed colour without a rainbow. Tints reuse the meaning colours (red attention, amber waiting, green done well, slate in progress, grey finished) |
| 2026-10-13 | Site and complaint phones accept mobile or STD landline | The user chose it: many sites (banks, offices) only have a landline. Technicians stay mobile-only. Shown formatted (e.g. 0891-2345678) |
| 2026-10-14 | Brand subtitle "Service" instead of "Stock" | The app now covers stock, complaints and defectives, as in the approved service mockup. Logo mark and colours unchanged |
