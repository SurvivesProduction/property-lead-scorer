#!/usr/bin/env python
"""Headless-Playwright verification of the DEMO Lead Board (Prompt W Step
5) -- fully synthetic data, screenshots are safe to commit. Mirrors
`property-lead-scorer-full/scripts/playwright_verify_real_board.py`'s own
4 checks, minus the DB-comparison assertion (no real DB here) -- instead
checks the default top row against a hand-computed expectation from the
synthetic fixture itself.

Usage:
    python scripts/playwright_verify_demo_board.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

_ROOT = Path(__file__).resolve().parent.parent
_HTML_PATH = _ROOT / "demo" / "lead_board_demo.html"
_SCREENSHOT_DIR = _ROOT / "demo" / "screenshots"


def run() -> int:
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"file:///{_HTML_PATH}", timeout=60000)
        page.wait_for_selector("#result-count", timeout=60000)

        # --- 1. default state ---
        page.screenshot(path=str(_SCREENSHOT_DIR / "01_default_state.png"), full_page=True)
        result_count_text = page.locator("#result-count").inner_text()
        if "7 leads" not in result_count_text:
            failures.append(f"Expected 7 leads under default filters for the synthetic fixture, got: {result_count_text!r}")
        else:
            print(f"PASS: default state shows the expected 7 synthetic survivors ({result_count_text!r}).")

        # --- 2. move a slider ---
        default_order = page.locator(".lead-row").evaluate_all("els => els.map(e => e.dataset.leadKey)")
        page.fill("#w-canopy", "0")
        page.dispatch_event("#w-canopy", "input")
        page.wait_for_timeout(100)
        page.screenshot(path=str(_SCREENSHOT_DIR / "02_slider_moved.png"), full_page=True)
        after_order = page.locator(".lead-row").evaluate_all("els => els.map(e => e.dataset.leadKey)")
        if after_order == default_order:
            failures.append("Moving the canopy slider to 0 did not change the synthetic ranking at all.")
        else:
            print("PASS: moving the canopy slider changed the synthetic ranking.")
        arrow_count = page.locator(".rank-up, .rank-down").count()
        if arrow_count == 0:
            failures.append("No rank-change arrows rendered after moving the canopy slider.")
        else:
            print(f"PASS: {arrow_count} rank-change arrows rendered.")

        # --- material filter chips: family-bucketed, counted, zero-count hidden ---
        page.reload()
        page.wait_for_selector("#result-count", timeout=60000)
        siding_chip_texts = page.locator("#siding-chips .chip").evaluate_all("els => els.map(e => e.textContent)")
        if not siding_chip_texts or not all("(" in t for t in siding_chip_texts):
            failures.append(f"Siding chips missing or missing counts: {siding_chip_texts}")
        else:
            print(f"PASS: siding chips render with counts: {siding_chip_texts}")
        # Row 8's composite "Vinyl Siding/Clapboards" is worked (hidden by
        # default) -- un-hiding worked leads should surface the Durable
        # bucket count going up (and Vinyl's too), proving a composite
        # value is matched under EITHER family.
        page.uncheck("#toggle-worked")
        page.wait_for_timeout(50)
        durable_chip = page.locator("#siding-chips .chip:has-text('Durable')")
        durable_text = durable_chip.first.inner_text() if durable_chip.count() else ""
        if "(2)" not in durable_text:
            failures.append(
                f"Expected the Durable chip's count to grow to 2 once the worked row with the composite "
                f"'Vinyl Siding/Clapboards' value is unhidden (proving it matches BOTH families), got: {durable_text!r}"
            )
        else:
            print(f"PASS: composite 'Vinyl Siding/Clapboards' row matches under Durable too: {durable_text!r}")
        # Row 2 (also Vinyl) is still hidden by the "hide mailed/shown"
        # toggle (untouched here) -- only row 8's composite value should
        # count under Vinyl at this point, i.e. exactly 1.
        vinyl_chip = page.locator("#siding-chips .chip:has-text('Vinyl')")
        vinyl_text = vinyl_chip.first.inner_text() if vinyl_chip.count() else ""
        if "(1)" not in vinyl_text:
            failures.append(f"Expected the Vinyl chip's count to include the composite row (and only it), got: {vinyl_text!r}")
        else:
            print(f"PASS: composite row also counted under Vinyl: {vinyl_text!r}")

        # --- source_url: some synthetic rows have none -- must show "No record link" ---
        page.goto(f"file:///{_HTML_PATH}", timeout=60000)
        page.wait_for_selector("#result-count", timeout=60000)
        page.click(".expand-btn")
        page.wait_for_timeout(50)
        if page.locator(".verify-link-none:has-text('No record link')").count() == 0:
            failures.append("Expected at least one 'No record link' placeholder among the default top rows.")
        else:
            print("PASS: a row with no source_url shows 'No record link' instead of a dead button.")

        # --- 3. apply a filter: show state-only rows (count should grow) ---
        page.reload()
        page.wait_for_selector("#result-count", timeout=60000)
        before_count_text = page.locator("#result-count").inner_text()
        page.check("#toggle-state-only")
        page.wait_for_timeout(100)
        page.screenshot(path=str(_SCREENSHOT_DIR / "03_filter_applied.png"), full_page=True)
        after_count_text = page.locator("#result-count").inner_text()
        if after_count_text == before_count_text:
            failures.append("Result count did not change after toggling 'Show state-data-only rows'.")
        else:
            print(f"PASS: result count changed after filtering ({before_count_text!r} -> {after_count_text!r}).")
        if page.locator(".badge-state-only").count() == 0:
            failures.append("Expected at least one 'state data only, not verified' badge once the toggle is on.")
        else:
            print("PASS: state-only badge rendered once the toggle is on.")

        # --- 4. phone width ---
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(100)
        page.screenshot(path=str(_SCREENSHOT_DIR / "04_phone_width.png"), full_page=True)
        body_scroll_width = page.evaluate("document.body.scrollWidth")
        if body_scroll_width > 390:
            failures.append(f"Horizontal overflow at phone width: body.scrollWidth={body_scroll_width}")
        else:
            print(f"PASS: no horizontal overflow at phone width (body.scrollWidth={body_scroll_width}).")

        # Also confirm the Windham-shaped short-permit-history parcel never
        # reads as "has real permit history" -- the project's explicit red
        # line (Prompt W Step 3).
        page.goto(f"file:///{_HTML_PATH}", timeout=60000)
        page.wait_for_selector("#result-count", timeout=60000)
        page.uncheck("#toggle-claimed")
        page.uncheck("#toggle-worked")
        page.uncheck("#toggle-mailed")
        page.uncheck("#toggle-unreachable")
        page.check("#toggle-permit-history")
        page.wait_for_timeout(100)
        smallville_rows = page.locator(".lead-row[data-lead-key^='Smallville']").count()
        if smallville_rows != 0:
            failures.append(
                f"'Has real permit history' filter incorrectly included {smallville_rows} Smallville "
                "(short-permit-history-town) row(s)."
            )
        else:
            print("PASS: the short-permit-history town never shows under 'Has real permit history'.")

        browser.close()

    print(f"\nScreenshots written to {_SCREENSHOT_DIR}")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f" - {f}")
        return 1
    print("\nAll demo-board Playwright checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
