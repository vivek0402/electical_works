# Vendored fonts

Latin subset, woff2, from the @fontsource packages (via cdn.jsdelivr.net), fetched 2026-11-15.
All three families are licensed under the SIL Open Font License 1.1 (https://openfontlicense.org), which allows bundling and redistribution.

| Family | Files | Use |
|---|---|---|
| Bricolage Grotesque | `bricolage-grotesque-latin-600-normal.woff2`, `-800-normal.woff2` | Display headings and figures |
| Instrument Sans | `instrument-sans-latin-400-normal.woff2`, `-600-normal.woff2` | Text and controls |
| Geist Mono | `geist-mono-latin-600-normal.woff2` | Item codes and entry numbers |

Declared with `@font-face` in `static/css/app.css`. No request goes to Google Fonts.
`tabler-icons.woff*` here belong to Tabler Icons (MIT), loaded by `vendor/tabler-icons.min.css`.
