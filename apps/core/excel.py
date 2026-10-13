"""One neat layout for every Excel export (approved via mockups/stock/exports/)."""

import io
import re
from dataclasses import dataclass
from datetime import date, datetime

import xlsxwriter
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header

COMPANY = "SVKML Electrical Works"
HEAD_ROW = 5  # zero-based; rows 0-3 hold the title block
SHEET_BAD = re.compile(r"[\[\]:*?/\\]")  # Excel forbids these in sheet names
MAX_ROWS = 50_000  # keeps one download from exhausting memory
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class Column:
    header: str
    kind: str = "text"  # text | code | int | date
    width: int | None = None  # characters; None = autofit


LOW_STYLE = {"bg_color": "#FDE2E2", "font_color": "#9B1C1C", "bold": True}
KIND_STYLE = {
    "text": {"valign": "top"},
    "code": {"font_name": "Consolas", "num_format": "@"},
    "int": {"num_format": '#,##0;-#,##0;"–"'},
    "date": {"num_format": "dd-mm-yyyy", "align": "left"},
}


def _formats(wb):
    return {
        "company": wb.add_format({"bold": True, "font_size": 15, "font_color": "#0F2744"}),
        "title": wb.add_format({"bold": True, "font_size": 12}),
        "meta": wb.add_format({"italic": True, "font_color": "#555555", "font_size": 9}),
        **{kind: wb.add_format(style) for kind, style in KIND_STYLE.items()},
        # highlighted cells keep their column's number format / font
        **{f"low_{kind}": wb.add_format({**style, **LOW_STYLE}) for kind, style in KIND_STYLE.items()},
    }


def _cell(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time())
    return value


def _title(ws, row, last, text, fmt):
    """Title-block line across the table width (XlsxWriter refuses a one-cell merge)."""
    if last:
        ws.merge_range(row, 0, row, last, text, fmt)
    else:
        ws.write(row, 0, text, fmt)


def workbook_response(
    filename,
    title,
    filters,
    username,
    columns,
    rows,
    low_rows=(),
    low_col=None,
    now=None,
    filters_label="Filters",
):
    """Build the report in memory and return it as a download.

    low_rows: row indexes to highlight in low_col.
    """
    now = now or timezone.localtime()
    buffer = io.BytesIO()
    wb = xlsxwriter.Workbook(
        buffer, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}
    )
    wb.set_properties({"title": title, "company": COMPANY, "author": "SVKML Stock"})
    ws = wb.add_worksheet(SHEET_BAD.sub("-", title)[:31].strip("'") or "Report")
    f = _formats(wb)
    last = len(columns) - 1
    total = len(rows)
    data = [[_cell(v) for v in row] for row in rows[:MAX_ROWS]]
    ws.add_table(
        HEAD_ROW,
        0,
        HEAD_ROW + max(len(data), 1),
        last,
        {
            "style": "Table Style Medium 2",
            "columns": [{"header": c.header, "format": f[c.kind]} for c in columns],
        },
    )
    # Write cells ourselves: write_string() is the only call that never turns text into a formula
    # (add_table's data and write() still treat "{=...}" as an array formula).
    for r, row in enumerate(data or [["(no rows)"] + [None] * last], start=HEAD_ROW + 1):
        for c, value in enumerate(row):
            fmt = f[columns[c].kind]
            if isinstance(value, str):
                ws.write_string(r, c, value, fmt)
            elif value is not None:
                ws.write(r, c, value, fmt)
            else:
                ws.write_blank(r, c, None, fmt)
    for n in (n for n in low_rows if n < len(data)):
        ws.write(HEAD_ROW + 1 + n, low_col, data[n][low_col], f[f"low_{columns[low_col].kind}"])
    ws.freeze_panes(HEAD_ROW + 1, 1)
    ws.autofit(max_width=280)  # before the title rows, so they don't widen column A
    for n, col in enumerate(columns):
        if col.width:
            ws.set_column(n, n, col.width)
    counted = f"{total} rows" if total <= MAX_ROWS else f"first {MAX_ROWS:,} of {total:,} rows"
    _title(ws, 0, last, COMPANY, f["company"])
    _title(ws, 1, last, title, f["title"])
    _title(ws, 2, last, f"{filters_label}: {filters}", f["meta"])
    _title(ws, 3, last, f"Generated on {now:%d-%m-%Y %H:%M} by {username} · {counted}", f["meta"])
    ws.set_row(HEAD_ROW, 30)
    ws.hide_gridlines(2)
    ws.set_landscape()
    ws.set_paper(9)  # A4
    ws.fit_to_pages(1, 0)
    ws.repeat_rows(HEAD_ROW)
    ws.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.set_header(f"&L&8{COMPANY}&R&8{title.replace('&', '&&')}")
    ws.set_footer("&L&8Generated &D &T&R&8Page &P of &N")
    wb.close()
    response = HttpResponse(buffer.getvalue(), content_type=XLSX)
    response["Content-Disposition"] = content_disposition_header(True, f"{filename}_{now:%Y-%m-%d}.xlsx")
    return response
