import io
from datetime import date, datetime

import openpyxl

from apps.core.excel import Column, workbook_response


def test_report_layout():
    response = workbook_response(
        "Test_Report",
        "Test Report",
        "All items",
        "office",
        [Column("Code", "code"), Column("Qty", "int"), Column("Date", "date")],
        [["A1", 3, date(2026, 10, 1)], ["B2", 0, date(2026, 10, 2)]],
        low_rows={1},
        low_col=1,
        now=datetime(2026, 10, 11, 14, 5),
    )
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'filename="Test_Report_2026-10-11.xlsx"' in response["Content-Disposition"]
    ws = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert ws["A1"].value == "SVKML Electrical Works" and ws["A2"].value == "Test Report"
    assert ws["A3"].value == "Filters: All items"
    assert ws["A4"].value == "Generated on 11-10-2026 14:05 by office · 2 rows"
    assert [c.value for c in ws[6]] == ["Code", "Qty", "Date"]
    assert ws.freeze_panes == "B7"
    assert ws["C7"].number_format == "dd-mm-yyyy" and ws["B8"].fill.fgColor.rgb.endswith("FDE2E2")
    assert ws.page_setup.orientation == "landscape" and ws.print_title_rows.replace("$", "") == "6:6"


def test_empty_report_still_valid():
    response = workbook_response(
        "Empty", "Empty", "-", "office", [Column("Code", "code")], [], now=datetime(2026, 10, 11)
    )
    ws = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert ws["A7"].value == "(no rows)"
