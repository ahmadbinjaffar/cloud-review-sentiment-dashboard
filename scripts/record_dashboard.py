"""Record the live dashboard in action (Playwright video, >=30 s).

Starts the local API server, records a headless-Chromium session against
http://127.0.0.1:8765/ui/ (load + assert data, scroll, negative filter, live
analysis), then stops the server. Output: presentation/dashboard_recording.webm.

Run:  .venv\\Scripts\\python.exe scripts\\record_dashboard.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation" / "dashboard_recording.webm"
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def safe(x) -> str:
    return str(x).encode("ascii", "replace").decode("ascii")


def wait_health(timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001 - server not up yet
            time.sleep(0.5)
    raise RuntimeError("server did not become healthy")


def ensure_data(page) -> None:
    """Wait for the boot load; retry loadAll() if it silently failed."""
    page.wait_for_timeout(3000)
    for attempt in range(3):
        if page.evaluate("state.summary !== null"):
            break
        print(f"  boot load empty, retrying loadAll() #{attempt + 1}")
        page.evaluate("loadAll()")
        page.wait_for_timeout(2500)
    page.wait_for_function("state.summary !== null", timeout=15000)
    page.wait_for_selector("#reviewsTable tbody tr", timeout=15000)
    page.wait_for_timeout(1500)                  # let Chart.js animate


def main() -> None:
    from playwright.sync_api import sync_playwright

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.local_server:app",
         "--port", str(PORT), "--log-level", "warning"],
        cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    video_dir = ROOT / "presentation" / "_recording_tmp"
    try:
        wait_health()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=str(video_dir),
                record_video_size={"width": 1280, "height": 720})
            page = ctx.new_page()
            page.on("pageerror", lambda e: print("  pageerror:", safe(e)))
            page.on("console", lambda m: print("  console", m.type,
                                                safe(m.text[:200]))
                    if m.type == "error" else None)
            page.on("response", lambda r: print("  HTTP", r.status,
                                                safe(r.url[-40:]))
                    if r.status >= 400 else None)
            t0 = time.monotonic()
            page.goto(f"{BASE}/ui/", wait_until="networkidle")
            ensure_data(page)

            for _ in range(10):                   # slow scroll down
                page.mouse.wheel(0, 260)
                page.wait_for_timeout(220)
            page.wait_for_timeout(800)

            page.select_option("#filterForm select[name='sentiment']",
                               "negative")
            page.wait_for_timeout(400)
            page.click("#filterForm button[type='submit']")
            page.wait_for_timeout(2500)           # filtered view
            page.click("#resetFiltersBtn")
            page.wait_for_timeout(1500)

            page.fill("#analyzeText",
                      "The waiter was rude and my food arrived cold after a "
                      "45 minute wait. Never coming back.")
            page.wait_for_timeout(400)
            page.click("#analyzeBtn")
            page.wait_for_selector("#analyzeResult .badge", timeout=20000)
            page.wait_for_timeout(2500)           # show stored result

            for _ in range(4):                    # scroll back up
                page.mouse.wheel(0, -500)
                page.wait_for_timeout(200)
            remain_ms = (30.0 - (time.monotonic() - t0)) * 1000
            if remain_ms > 0:
                page.wait_for_timeout(remain_ms)  # cover the demo narration

            ctx.close()                           # video finalized
            browser.close()
        webm = next(video_dir.glob("*.webm"))
        shutil.move(str(webm), str(OUT))
        print(f"saved {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(video_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
