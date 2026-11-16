# Design System: SVKML Service (direction B)

## Product Context
- **What this is:** Stock management for SVKML Electrical Works (a Wipro Lighting service partner, Visakhapatnam): stock IN/OUT, transfers, count corrections, stock by location, Excel exports, plus the Complaints and Defective pieces modules in the same app (since 2026-10-12; the app is branded "SVKML Service"). No company is special in the UI: Wipro is one company among several.
- **Who it's for:** Admin and office staff with low tech comfort, mostly on desktop, sometimes on phones.
- **Project type:** Internal web app.
- **Memorable thing:** "Bold, clear business software where colour always means something."

## Aesthetic Direction
- **Direction:** Bold and graphic (direction B), chosen by the user on 2026-11-15 from three mocked directions (A Light and airy, B Bold and graphic, C Task-first) after the user rejected a tidy-up of the old look.
- **Look:** a dark ink top bar and hero over a warm cream page; white rounded cards; big display type for titles and figures; one amber accent; pill buttons.
- **Decoration:** none beyond colour blocks. Colour carries meaning (IN blue, OUT orange, red attention, amber waiting).
- **Mocks (source of truth):** `mockups/design-b/` (dashboard, current stock, Stock IN form, complaints list, complaint page) and `mockups/design-directions/directions.css`.
- **UI kit underneath:** Tabler 1.6.1 + Tabler Icons 3.49.0 (grid, modals, dropdowns), Tom Select 2.6.2 (searchable selects). All vendored; `static/css/app.css` loads last and restyles them. django-unfold for the Django admin.

## Color
Approach: restrained. Ink and cream do the structure, amber is the one accent, meaning colours do the talking. Contrast ratios below were computed (WCAG relative luminance) on 2026-11-15.

| Role | Hex | Use | Contrast |
|---|---|---|---|
| Ink | `#0d1321` | Top bar, hero, text, active pill, dark buttons | on cream 16.2:1, on white 18.6:1 |
| Page (cream) | `#f3efe6` | Page background, shaded "not counted" column, segmented-control track | muted text on it 5.4:1 |
| Surface | `#ffffff` | Cards, inputs, active top-bar pill | |
| Line | `#e6e0d2` | Hairlines inside cards; inputs use `#cfc8b8` | |
| Muted text | `#5a6170` | Captions, labels, hints | on white 6.2:1, on cream 5.4:1 |
| Muted on dark | `#b8c0d0` | Hero context line, inactive pills, back link | on ink 10.2:1 |
| Amber | `#f5b301` | Primary button, count badges, sub-tab counts, the bulb mark, focus ring on dark | ink on amber 10.0:1; amber on ink 10.0:1 |
| Danger | `#b42318` | Errors, required marks, attention figures | on white 6.6:1 |
| Placeholder | `#6b7080` | Input placeholders | on white 4.9:1 |
| Zero quantities | `#6f6a5d` | The "0" in stock matrices | on white 5.4:1, on cream 4.7:1 |

**Meaning colours (identical in every module; unchanged by the redesign):**

| Meaning | Marks/charts | Buttons (white text) | Tint (badges/backgrounds) |
|---|---|---|---|
| **Stock IN** | `#2a78d6` | `#2268c0` (5.5:1) | `rgba(42,120,214,.12)` with text `#1f5fae` (5.4:1) |
| **Stock OUT** | `#eb6834` | `#c2410c` (5.2:1) | `rgba(235,104,52,.14)` with text `#a8441b` (5.3:1) |
| Needs attention | `#d63939` | `btn-danger` `#b42318` | `#fde8e8` with text `#b42318` (5.6:1) |
| OK / success | `#2e9e4f` | | `#e7f6ec` with text `#1e7e34` (4.6:1) |
| Waiting | `#f5b301` | | `#fef3c7` with text `#854d0e` (6.2:1) |
| Transfer / adjustment / neutral | slate | white quiet button | `rgba(71,85,105,.12)` with text `#334155` (opaque `#e6e9ee` on the dark hero, 8.5:1) |
| Finished | grey | | `#eef0f3` with text `#475569` (6.6:1) |

- The IN/OUT chart pair (`#2a78d6` / `#eb6834`) and button pair (`#2268c0` / `#c2410c`) passed the colour-blindness check; green/orange failed, so never use green for IN.
- Status pills (`.st-alert .st-wait .st-ok .st-neutral .st-done`) always carry an icon and a word, never colour alone. Entry badges are `.k-IN .k-OUT .k-TRF .k-ADJ .k-REV`; quantities `.qty-in .qty-out`.
- **Defective store** is shown as its own shaded column ("Not counted"), never part of a total or low-stock check.
- **Excel exports:** company title in navy `#0F2744`, header in Excel's "Table Style Medium 2". Unchanged.
- Never use purple or other decorative colours for actions. Dark mode: not in v1.

## Typography
Three typefaces, vendored as woff2 (SIL OFL) in `static/vendor/fonts/`, declared in `app.css` with `font-display: swap`:
- **Bricolage Grotesque** 800 (and 600): page titles, card titles, figures.
- **Instrument Sans** 400 and 600: all text, labels, buttons, inputs.
- **Geist Mono** 600: item codes, entry numbers, tags (`.code`).

Exactly **five sizes**, as CSS variables: `--s1` 13px (captions, labels, pills, table headers), `--s2` 15px (body, inputs, buttons), `--s3` 18px (card titles, lead text), `--s4` 28px (large figures, phone page title), `--s5` 48px (page title on desktop, hero figures). Weights: 400 and 600 for text, 800 for display headings and figures. Tabular figures for quantities.

## Layout and shell
- **Top bar** (ink, 68px): brand with the amber bulb mark and "SVKML Service"; five section pills Home, Stock, Complaints, Defectives, Setup (active = white pill); open-complaints and pieces-in-store count badges in amber beside their pills (hidden at zero, each linking to the list that shows exactly that many rows); global search; low-stock bell; user menu (Users for admins, Logout).
- **Hero** (ink, under the bar): optional back link, page title, one line of context, the section's actions, then the section's sub-tabs. Content cards overlap the hero's bottom edge by 72px.
- **Sub-tabs and actions per section:** Stock (Current stock, Movements, Low stock; Stock IN, Stock OUT, Transfer, Adjust), Complaints (Overview, All complaints, Sites, Technicians; New complaint), Defectives (Overview, Pieces, Return batches; Mark defective, New return batch), Setup (Items, Masters for admins; New item), Home (no tabs; Stock IN, Stock OUT, New complaint, Transfer, Adjust). Form and detail pages show a back link, not tabs or section actions. A page's own action is never shown twice.
- **Phones:** the top bar scrolls sideways, search takes the full width, no hamburger; the hero's action buttons are one sideways-scrolling row (not a stack of wrapped rows); the overview blocks and filter fields sit two per row. Entry lines stack as cards. No horizontal page scroll.
- **Screen order rule:** main actions, then what needs attention, then related groups, then history.
- **One card style:** white, 18px corners, no border, 26px padding (18px on phones). Cards group one subject each.
- **Controls:** pill buttons 44px high; inputs 48px high with 12px radius; segmented control for 2-4 choices; checkboxes 22px. Touch targets at least 44px. Visible `:focus-visible` rings (ink on light, amber on dark).
- **Tables:** header row 13px 600 with a 2px ink rule, hairlines between rows, no striping, numbers right-aligned.
- **Motion:** minimal and functional.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-11-15 | Redesign direction **B · Bold and graphic** | The user rejected a tidy-up of the sidebar look as "not major changes", allowed layout, colour, typeface and components to change, and chose B over A (Light and airy) and C (Task-first) |
| 2026-11-15 | Dark top bar and hero replace the left sidebar; five sections with sub-tabs | Fewer menu entries to scan; each section's actions sit with its title. Form and detail pages get a back link |
| 2026-11-15 | Screen order: main actions, what needs attention, related groups, history | The user asked for clearer hierarchy with related things grouped |
| 2026-11-15 | Bricolage Grotesque + Instrument Sans + Geist Mono, vendored; five sizes 13/15/18/28/48 | Distinct display type for titles and figures; no external font request; one scale everywhere |
| 2026-11-15 | Tabler stays underneath, restyled by `app.css` | Keeps modals, dropdowns, pickers and every script working while the look changes completely |
| 2026-11-15 | Zero quantities darkened to `#6f6a5d`; opaque neutral tint on the hero | The mock's lighter zero and the translucent neutral tint failed AA contrast |
| 2026-10-11 | Modern admin dashboard on Tabler | User chose it over Pico/minimal. No build step, complete components |
| 2026-10-11 | IN blue / OUT orange | Green/orange failed the CVD check; blue/orange passes |
| 2026-10-11 | Deeper IN/OUT button shades | White text on `#eb6834` was 3.2:1 (fails AA); `#c2410c` is 5.2:1 |
| 2026-10-11 | Palette **A · Navy & Amber** | User picked it from 3 live options (A Navy & Amber, B Slate & Teal, C Clean light). The brand blue matches IN, navy reads as trustworthy, amber nods to lighting |
| 2026-10-11 | Restraint: colour only for meaning | The first version used 6+ loud colours (purple Adjust, rainbow KPI icons) and looked like a template |
| 2026-10-12 | Defective store column is shown but never counted | Failed pieces must stay visible next to stock (so nothing is lost) but must never inflate good stock, totals or low-stock checks. Pickers and totals use `Location.objects.good()` |
| 2026-10-12 | Status pills: five tints, always icon + word | Seven complaint statuses plus piece, batch and outcome states needed colour without a rainbow. Tints reuse the meaning colours (red attention, amber waiting, green done well, slate in progress, grey finished) |
| 2026-10-13 | Site and complaint phones accept mobile or STD landline | The user chose it: many sites (banks, offices) only have a landline. Technicians stay mobile-only. Shown formatted (e.g. 0891-2345678) |
| 2026-10-14 | Brand subtitle "Service" instead of "Stock" | The app now covers stock, complaints and defectives, as in the approved service mockup. Logo mark and colours unchanged |
