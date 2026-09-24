"""Instrumented single run of Review copies: prints console, page errors, and
every /api request/response so a UI failure can be diagnosed, not guessed at.

    CHROMIUM_PATH=... python3 deploy/e2e_debug.py https://host:3443 clip.mp4
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

url, video = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
    pg = b.new_page(viewport={"width": 420, "height": 900})
    pg.on("console", lambda m: print(f"[console.{m.type}] {m.text}"))
    pg.on("pageerror", lambda e: print(f"[pageerror] {e}"))
    pg.on("request", lambda r: print(f"[req] {r.method} {r.url}") if "/api/" in r.url else None)
    pg.on("response", lambda r: print(f"[res] {r.status} {r.url}") if "/api/" in r.url else None)
    pg.on("requestfailed", lambda r: print(f"[reqfailed] {r.url} {r.failure}"))
    pg.goto(url, wait_until="networkidle")
    menu = pg.get_by_role("button", name="Menu")
    if menu.is_visible():
        menu.click()
    pg.get_by_role("button", name="Repurpose").click()
    pg.get_by_role("button", name="Review copies").click()
    pg.set_input_files("input[type=file]:not([multiple])", video)
    pg.locator("textarea").first.fill("@a\n@b")
    pg.get_by_role("checkbox").check()
    pg.get_by_role("button", name="Generate outputs").click()
    last = ""
    for i in range(60):
        time.sleep(1)
        btn = pg.locator("button.start").first.inner_text()
        err = pg.locator(".error").all_inner_texts()
        dl = pg.get_by_role("link", name="Download ZIP").count()
        line = f"button='{btn}' error={err} downloadLink={dl}"
        if line != last:
            print(f"t={i+1}s {line}")
            last = line
        if dl or err:
            break
    b.close()
