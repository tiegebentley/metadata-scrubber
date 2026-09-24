"""Drive the real UI in headless Chromium: upload a video, run Review copies, download the zip.

Run against the deployed services:
    python3 deploy/e2e_review_copies.py http://100.79.168.65:3000 /path/to/video.mp4

This exercises the page as a browser does, over plain http, which is what
caught the crypto.randomUUID crash that API-level curl tests could not.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ui_url, video = sys.argv[1], Path(sys.argv[2])
errors: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
    page = browser.new_page(viewport={"width": 420, "height": 900})  # phone-ish
    page.on("response", lambda r: errors.append(f"http {r.status}: {r.url}") if r.status >= 400 else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

    page.goto(ui_url, wait_until="networkidle")

    def nav(label: str) -> None:
        # At phone width the sidebar is behind the hamburger; open it first.
        menu = page.get_by_role("button", name="Menu")
        if menu.is_visible():
            menu.click()
        page.get_by_role("button", name=label).click()

    nav("Repurpose")
    page.get_by_role("button", name="Review copies").click()
    page.set_input_files("input[type=file]:not([multiple])", str(video))
    page.get_by_placeholder("@handle").or_(page.locator("textarea")).first.fill("@test1\n@test2\n@test3\n@test4")
    page.get_by_role("checkbox").check()

    with page.expect_download(timeout=600_000) as dl_info:
        page.get_by_role("button", name="Generate outputs").click()
        page.get_by_role("link", name="Download ZIP").wait_for(timeout=600_000)
        page.get_by_role("link", name="Download ZIP").click()
    out = Path("/tmp/e2e_review.zip")
    dl_info.value.save_as(out)

    nav("History")
    history_rows = page.locator(".historyRow").count()
    browser.close()

names = zipfile.ZipFile(out).namelist()
print("zip:", names)
print("history rows:", history_rows)
print("page errors:", errors or "none")
ok = len(names) == 4 and history_rows >= 1 and not errors
print("E2E", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
