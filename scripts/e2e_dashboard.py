"""End-to-end dashboard verification with Playwright + real screenshots.

Requires the local server (scripts/run_local.ps1) on --base-url.
Checks: KPIs loaded from real data, charts rendered, negative filter works,
live-analyze flow, CSV upload flow, free-tier panel. Saves screenshots to
docs/screenshots/.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def wait_for_data(page) -> None:
    """Wait until KPIs are filled from the API."""
    page.wait_for_function(
        "() => { const t = document.querySelector('#kpiTotal').textContent; return t && t !== '\\u2013' && t.length > 0; }",
        timeout=20000,
    )
    page.wait_for_selector("#reviewsTable tbody tr", timeout=20000)
    page.wait_for_timeout(1300)  # let Chart.js finish animating


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    SHOTS.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        # ---------- light theme, full page ----------
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.add_init_script("localStorage.setItem('rp_theme','light')")
        page.goto(f"{args.base_url}/ui/", wait_until="networkidle")
        wait_for_data(page)

        total = page.text_content("#kpiTotal").strip().replace(",", "")
        check("KPIs loaded from API", total.isdigit() and int(total) > 1000, f"total={total}")
        canvases = page.locator("canvas").count()
        check("4 charts rendered", canvases == 4, f"canvases={canvases}")
        rows = page.locator("#reviewsTable tbody tr").count()
        check("reviews table populated", rows > 0, f"rows={rows}")
        ft_rows = page.locator("#freeTierTable tbody tr").count()
        ft_zero = page.locator("#freeTierTable tbody .badge-ok").count()
        check("free-tier panel complete", ft_rows >= 8 and ft_zero == ft_rows,
              f"{ft_rows} rows, {ft_zero} within-free badges")
        page.screenshot(path=str(SHOTS / "01_dashboard_light_full.png"), full_page=True)

        # ---------- negative filter ----------
        import urllib.request
        with urllib.request.urlopen(f"{args.base_url}/summary?sentiment=negative", timeout=10) as resp:
            import json as _json
            expected_neg = str(_json.loads(resp.read())["summary"]["total_reviews"])
        page.select_option('select[name="sentiment"]', "negative")
        page.click('#filterForm button[type="submit"]')
        page.wait_for_timeout(1500)
        badges = page.locator("#reviewsTable tbody .badge-neg").count()
        total_after = page.text_content("#kpiTotal").strip()
        check("filter sentiment=negative applied", badges > 0 and total_after == expected_neg,
              f"neg rows={badges}, KPI total={total_after} (expected {expected_neg})")
        page.locator("section.card").filter(has=page.locator("#reviewsTable")).screenshot(
            path=str(SHOTS / "03_table_negative_filter.png"))

        # ---------- live analyze flow ----------
        page.click("#resetFiltersBtn")
        page.wait_for_timeout(800)
        page.fill("#analyzeText", "The waiter was rude and my food arrived cold after a 45 minute wait. Never coming back.")
        page.select_option("#analyzeRating", "1")
        page.click("#analyzeBtn")
        page.wait_for_selector("#analyzeResult .badge", timeout=20000)
        result_html = page.inner_html("#analyzeResult")
        check("live analyze returns a sentiment", "confidence" in result_html and "badge" in result_html,
              "analyze box shows label + confidence")
        page.locator("article.card").filter(has=page.locator("#analyzeResult")).screenshot(
            path=str(SHOTS / "04_analyze_live_result.png"))

        # ---------- CSV upload flow ----------
        csv_content = (
            "date,rating,text\n"
            "2024-06-01,5,\"Lovely staff and the coffee was perfect!\"\n"
            "2024-06-02,1,\"Cold food and a filthy table. Awful.\"\n"
            "2024-06-03,9,\"invalid rating row\"\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as fh:
            fh.write(csv_content)
            tmp_csv = fh.name
        page.set_input_files("#uploadFile", tmp_csv)
        page.click("#uploadBtn")
        page.wait_for_function(
            "() => { const el = document.querySelector('#uploadResult'); return el && !el.hidden && el.textContent.includes('valid'); }",
            timeout=20000,
        )
        upload_text = page.text_content("#uploadResult")
        check("CSV upload ingested with row report",
              "2 valid" in upload_text and "1 invalid" in upload_text,
              upload_text.strip()[:90].replace("\n", " "))
        page.locator("article.card").filter(has=page.locator("#uploadResult")).screenshot(
            path=str(SHOTS / "05_upload_result.png"))
        page.close()

        # ---------- dark theme, full page ----------
        page2 = browser.new_page(viewport={"width": 1440, "height": 960})
        page2.add_init_script("localStorage.setItem('rp_theme','dark')")
        page2.goto(f"{args.base_url}/ui/", wait_until="networkidle")
        wait_for_data(page2)
        theme = page2.get_attribute("html", "data-theme")
        check("dark mode active", theme == "dark", f"data-theme={theme}")
        page2.screenshot(path=str(SHOTS / "02_dashboard_dark_full.png"), full_page=True)

        # ---------- responsive check (mobile width) ----------
        page2.set_viewport_size({"width": 390, "height": 844})
        page2.wait_for_timeout(900)
        overflow = page2.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("mobile layout has no horizontal overflow", overflow <= 2, f"overflow={overflow}px")
        page2.screenshot(path=str(SHOTS / "06_mobile_dark.png"), full_page=True)
        browser.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed; screenshots in {SHOTS}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
