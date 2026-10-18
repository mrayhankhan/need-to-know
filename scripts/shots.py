"""Capture screenshots of every screen (used in CI and for the README)."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "results/shots")
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name):
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ["light", "dark"]:
        page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=scheme)
        page.goto(BASE)
        page.wait_for_selector(".persona")
        page.click(".persona[data-id='p_priya']")
        page.fill("#q", "Why did Acme Corp's invoice go up in October?")
        page.click("#ask-form button")
        page.wait_for_selector(".ans")
        shot(page, f"1-ask-intern-{scheme}")
        if scheme == "dark":
            break
        page.click(".tab[data-tab='compare']")
        page.click("#cmp-form button")
        page.wait_for_selector("#cmp .ans")
        shot(page, "2-compare")
        page.click(".tab[data-tab='ask']")
        page.click("#mode button[data-mode='off']")
        page.wait_for_timeout(900)
        shot(page, "3-ask-access-off")
        page.click("#mode button[data-mode='graph']")
        page.click(".tab[data-tab='agents']")
        page.click("#run-case")
        page.wait_for_selector(".steps")
        shot(page, "4-agents")
        page.click("#run-case-off")
        page.wait_for_timeout(900)
        shot(page, "5-agents-off")
        page.click("#run-case")
        page.click(".tab[data-tab='memory']")
        page.click("#peek")
        page.wait_for_selector("#peek-out .result")
        shot(page, "6-memory")
        page.click(".tab[data-tab='scan']")
        page.click("#run-scan")
        page.wait_for_selector(".find")
        page.click("[data-test='o0']")
        page.wait_for_selector("#find-o0 .result")
        shot(page, "7-scan")
        page.click(".tab[data-tab='proof']")
        page.click("#run-eval")
        page.wait_for_selector("#eval-out table", timeout=120000)
        shot(page, "8-proof")
        mob = b.new_page(viewport={"width": 390, "height": 844})
        mob.goto(BASE)
        mob.wait_for_selector(".persona")
        mob.fill("#q", "Why did Acme Corp's invoice go up in October?")
        mob.click("#ask-form button")
        mob.wait_for_selector(".ans")
        shot(mob, "9-mobile")
    b.close()
print("screenshots in", OUT)
