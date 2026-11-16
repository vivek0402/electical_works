"""Phase 3c: the browser-only behaviour, on the loaded rigour data (Playwright, pinned to 1.63.0).

    PYTHONIOENCODING=utf-8 uv run --with playwright==1.63.0 python e2e/rigour/ui_checks.py http://127.0.0.1:8001 admin <password>

  - walks 40 pages at 1366 px and 390 px: no JS error, no horizontal scroll, no server error page
  - the searchable item picker with ~100 items: finds an Excel code by a fragment, in upper or lower case
  - the live over-issue warning on Stock OUT blocks Save
  - what a number box does when the Excel text '22 NOS' is typed into it
  - one Stock IN entry with 25 lines is saved and shows all 25
  - global search finds an item, a complaint, a site and a piece
Screenshots of failures go to e2e/rigour/shots/. Exit 0 = every check passed.
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE, USER, PASSWORD = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(exist_ok=True)
errors, failures = [], []


def check(name, ok, evidence=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {evidence}" if not ok and evidence else ""))
    if not ok:
        failures.append(name)


def watch(page):
    page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
    page.on("console", lambda m: m.type == "error" and errors.append(f"{page.url}: {m.text}"))


def login(page):
    page.goto(f"{BASE}/login/")
    page.fill("#id_username", USER)
    page.fill("#id_password", PASSWORD)
    page.click("button[type=submit]")
    expect(page.locator(".page-title")).to_be_visible()


def pick_item(page, text, row=0):
    line = page.locator(".lines-table tbody tr").nth(row)
    line.locator(".ts-control").click()
    line.locator(".ts-control input").fill(text)
    option = line.locator(".ts-dropdown .option").first
    expect(option).to_be_visible()
    label = option.inner_text()
    option.click()
    return label


def page_urls(page):
    """40 real addresses: lists, and the first few detail pages found on them."""
    urls = [
        "/",
        "/stock/",
        "/movements/?date_from=2026-01-01&date_to=2026-10-22",
        "/low-stock/",
        "/items/",
        "/items/new/",
        "/stock/in/",
        "/stock/out/",
        "/stock/transfer/",
        "/stock/adjust/",
        "/complaints/",
        "/complaints/list/?tab=all",
        "/complaints/new/",
        "/sites/",
        "/technicians/",
        "/defectives/",
        "/defectives/pieces/",
        "/defectives/mark/",
        "/defectives/batches/",
        "/defectives/batches/new/?company=1",
        "/masters/",
    ]
    for list_url, pattern in (
        ("/items/", r'href="(/items/\d+/)"'),
        ("/complaints/list/?tab=all", r'href="(/complaints/CMP-\d+/)"'),
        ("/defectives/pieces/", r'href="(/defectives/pieces/DEF-\d+/)"'),
        ("/defectives/batches/", r'href="(/defectives/batches/RB-\d+/)"'),
        ("/sites/", r'href="(/sites/\d+/)"'),
        ("/movements/?date_from=2026-01-01&date_to=2026-10-22", r'href="(/entries/[A-Z]+-\d+/)"'),
    ):
        html = page.request.get(BASE + list_url).text()
        urls += list(dict.fromkeys(re.findall(pattern, html)))[:3]
    return urls


def no_side_scroll(page):
    return page.evaluate("document.documentElement.scrollWidth") <= page.viewport_size["width"] + 1


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ============================ desktop ============================
    page = browser.new_page(viewport={"width": 1366, "height": 860})
    watch(page)
    login(page)
    urls = page_urls(page)

    bad = []
    for url in urls:
        r = page.goto(BASE + url)
        if r.status >= 400 or not no_side_scroll(page) or page.locator("text=Server Error").count():
            bad.append(f"{url} -> {r.status}, side-scroll={not no_side_scroll(page)}")
    check(f"{len(urls)} pages at 1366 px: all load, none scrolls sideways", not bad, "; ".join(bad[:5]))
    check("no JavaScript error on any of them", not errors, "; ".join(errors[:4]))

    # --- the item picker: an Excel code typed as a fragment, in lower case --------------------------------------
    page.goto(f"{BASE}/stock/out/")
    page.locator("#id_location").select_option(label="Vizag Office")
    got = pick_item(page, "lg66")
    check(
        "typing the fragment 'lg66' (lower case) in the item picker finds an LG66-... item",
        "LG66" in got.upper(),
        got,
    )

    # --- the live warning on over-issue --------------------------------------------------------------------------
    avail = int(page.locator(".lines-table .avail b").first.inner_text() or 0)
    page.locator("input[name=line_qty]").first.fill(str(avail + 1))
    warning = page.locator(".err").first
    try:
        expect(warning).to_contain_text(f"Only {avail}")
        shown = True
    except AssertionError:
        shown = False
    check(
        f"asking for {avail + 1} when {avail} are available shows 'Only {avail} ... available' at once", shown
    )
    page.fill("#id_party", "UI check site")
    page.click("#entry-form button[type=submit]")
    expect(page.locator("#form-error")).to_contain_text("highlighted")
    check("Save is blocked and the page says which quantities to fix", "/stock/out/" in page.url)

    # --- the Excel text typed into a number box ------------------------------------------------------------------
    box = page.locator("input[name=line_qty]").first
    check(
        "the quantity box is a number box (type=number)",
        box.get_attribute("type") == "number",
        str(box.get_attribute("type")),
    )
    box.click()
    box.press("Control+a")
    page.keyboard.type("22 NOS")
    typed = box.input_value()
    check(
        "typing the Excel text '22 NOS' into it keeps only the number",
        typed in ("22", ""),
        f"the box holds {typed!r}",
    )

    # --- a 25-line Stock IN ---------------------------------------------------------------------------------------
    page.goto(f"{BASE}/stock/in/")
    page.locator("#id_company").select_option(index=1)  # nothing is preselected: pick a supplier and a place
    page.locator("#id_location").select_option(index=1)
    page.locator("#id_ref").fill("UI-25-LINES")
    for n in range(25):
        if n:
            page.get_by_text("Add another item").first.click()
        pick_item(page, "LG7" if n % 2 else "LG6", row=n)
        page.locator("input[name=line_qty]").nth(n).fill(str(n + 1))
    check(
        "25 lines are on the Stock IN form",
        page.locator(".lines-table tbody tr").count() == 25,
        str(page.locator(".lines-table tbody tr").count()),
    )
    page.screenshot(path=str(SHOTS / "stock-in-25-lines.png"), full_page=True)
    page.click("button.btn-in[type=submit]")
    page.wait_for_url(re.compile(r"/entries/IN-\d+/"), timeout=20000)
    lines = page.locator("table tbody tr").count()
    check(f"the saved entry shows 25 lines (page has {lines} table rows)", lines >= 25, page.url)

    # --- global search ----------------------------------------------------------------------------------------------
    def search_finds(text, expect_text):
        page.goto(f"{BASE}/")
        page.fill("#gsearch", text)
        try:
            expect(page.locator("#gresults [role=option]", has_text=expect_text).first).to_be_visible(
                timeout=5000
            )
            return True
        except AssertionError:
            return False

    check("global search 'cmp-0010' finds the complaint", search_finds("cmp-0010", "CMP-0010"))
    check("global search 'laurus' finds the site", search_finds("laurus", "Laurus"))
    check("global search 'def-0010' finds the piece", search_finds("def-0010", "DEF-0010"))
    check("global search finds an item by a fragment of its code", search_finds("lg66-040", "LG66-040"))
    check(
        "global search 'EI08437' (the Excel typo of EIO8437) finds the item",
        search_finds("EI08437", "EIO8437"),
    )
    page.close()

    # ============================ phone ============================
    ph = browser.new_page(viewport={"width": 390, "height": 844})
    errors_before = len(errors)
    watch(ph)
    login(ph)
    expect(ph.locator(".navbar-toggler")).to_have_count(0)  # no hamburger: the top bar scrolls sideways
    ph.locator(".b-nav .b-pill-link", has_text="Stock").first.click()
    expect(ph.get_by_role("link", name="Stock IN").first).to_be_visible()
    bad = []
    for url in urls:
        r = ph.goto(BASE + url)
        if r.status >= 400 or not no_side_scroll(ph):
            ph.screenshot(path=str(SHOTS / ("phone-" + re.sub(r"\W+", "_", url) + ".png")), full_page=True)
            bad.append(f"{url} (width {ph.evaluate('document.documentElement.scrollWidth')})")
    check(f"{len(urls)} pages at 390 px: none scrolls sideways", not bad, "; ".join(bad[:6]))
    check(
        "no JavaScript error on the phone pass",
        len(errors) == errors_before,
        "; ".join(errors[errors_before : errors_before + 3]),
    )
    browser.close()

print(
    f"\n{'ALL UI CHECKS PASSED' if not failures else str(len(failures)) + ' FAILED: ' + '; '.join(failures)}"
)
sys.exit(1 if failures else 0)
