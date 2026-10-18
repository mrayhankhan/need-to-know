"""Capture screenshots of every screen (used in CI and for the README)."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "results/shots")
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name, full=True):
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def nav(page, view):
    page.click(f".nav button[data-view='{view}']")


with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ["light", "dark"]:
        page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=scheme)
        page.goto(BASE)
        page.wait_for_selector(".answer .a-text")
        shot(page, f"1-ask-{scheme}")
        if scheme == "dark":
            break
        page.select_option("[data-compare]", "p_meera")
        page.wait_for_selector(".split .answer")
        page.locator(".split").scroll_into_view_if_needed()
        shot(page, "2-compare")
        page.click("#who")
        page.click("#who-menu button[data-id='p_meera']")
        page.wait_for_timeout(1200)
        shot(page, "3-ask-finance-head")
        nav(page, "company")
        page.wait_for_selector("#v-company .stats")
        page.click("#peek")
        page.wait_for_selector("#peek-out .result")
        shot(page, "4-company")
        nav(page, "agents")
        page.click("#run-case")
        page.wait_for_selector(".steps")
        shot(page, "5-agents")
        page.click("#run-case-off")
        page.wait_for_timeout(900)
        shot(page, "6-agents-off")
        page.click("#run-case")
        nav(page, "health")
        page.click("#run-scan")
        page.wait_for_selector("[data-test='o0']")
        page.click("[data-test='o0']")
        page.wait_for_selector("#find-o0 .result")
        shot(page, "7-health")
        nav(page, "how")
        page.click("#try-run")
        page.wait_for_selector("#try-out .card")
        page.click("#load-eval")
        page.wait_for_selector("#eval-out table", timeout=120000)
        shot(page, "8-how")
        mob = b.new_page(viewport={"width": 390, "height": 844})
        mob.goto(BASE)
        mob.wait_for_selector(".answer .a-text")
        shot(mob, "9-mobile")
    b.close()
print("screenshots in", OUT)
