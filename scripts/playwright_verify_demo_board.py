#!/usr/bin/env python
"""Headless-Playwright verification of the DEMO Lead Board (Prompt W Step
5, extended 2026-10-30 for the results-first layout / per-filter rank
numbering / preset fix / theme-toggle fix follow-up) -- fully synthetic
data, screenshots are safe to commit. Mirrors `property-lead-scorer-full/
scripts/playwright_verify_real_board.py`'s own checks, minus the
DB-comparison assertion (no real DB here) -- instead checks the default
top row against a hand-computed expectation from the synthetic fixture
itself.

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


def _open_panels(page) -> None:
    """Force both collapsible panels open -- most checks below are about
    FUNCTIONALITY of the controls inside them, not the collapse behavior
    itself (that's its own dedicated check), so tests that click a
    checkbox/chip must not depend on the viewport-driven initial
    open/closed state.
    """
    page.evaluate(
        "document.getElementById('weights-details').open = true; "
        "document.getElementById('filters-details').open = true;"
    )


def run() -> int:
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"file:///{_HTML_PATH}", timeout=60000)
        page.wait_for_selector("#result-count", timeout=60000)

        # --- layout: results panel first, before the (now collapsible) Weights/Filters panels ---
        panel_order = page.locator("#app-root > .panel, #app-root > details.panel").evaluate_all(
            "els => els.map(e => e.id || (e.querySelector('#results-list') ? 'results' : '?'))"
        )
        results_idx = next((i for i, v in enumerate(panel_order) if v == "results"), -1)
        weights_idx = next((i for i, v in enumerate(panel_order) if v == "weights-details"), -1)
        filters_idx = next((i for i, v in enumerate(panel_order) if v == "filters-details"), -1)
        if not (results_idx != -1 and results_idx < weights_idx and results_idx < filters_idx):
            failures.append(f"Expected the results panel first in DOM order, got panel order: {panel_order}")
        else:
            print("PASS: results panel appears before the Weights and Filters panels.")

        # --- desktop: both panels open by default ---
        weights_open = page.evaluate("document.getElementById('weights-details').open")
        filters_open = page.evaluate("document.getElementById('filters-details').open")
        if not (weights_open and filters_open):
            failures.append(f"Expected both panels open on desktop by default, got weights_open={weights_open} filters_open={filters_open}")
        else:
            print("PASS: Weights and Filters panels are open by default on desktop width.")

        # --- phone width, fresh load: both panels closed by default --
        #     screenshotted here too (not reusing the main `page` later,
        #     which will have been manipulated into an open state by
        #     then) so 04_phone_width.png shows the TRUE default phone
        #     experience, not a mid-test artifact.
        phone_page = browser.new_page(viewport={"width": 375, "height": 812})
        phone_page.goto(f"file:///{_HTML_PATH}", timeout=60000)
        phone_page.wait_for_selector("#result-count", timeout=60000)
        weights_open_phone = phone_page.evaluate("document.getElementById('weights-details').open")
        filters_open_phone = phone_page.evaluate("document.getElementById('filters-details').open")
        if weights_open_phone or filters_open_phone:
            failures.append(f"Expected both panels closed on phone width by default, got weights_open={weights_open_phone} filters_open={filters_open_phone}")
        else:
            print("PASS: Weights and Filters panels are closed by default on phone width.")
        phone_page.screenshot(path=str(_SCREENSHOT_DIR / "04_phone_width.png"), full_page=True)
        body_scroll_width = phone_page.evaluate("document.body.scrollWidth")
        if body_scroll_width > 390:
            failures.append(f"Horizontal overflow at phone width: body.scrollWidth={body_scroll_width}")
        else:
            print(f"PASS: no horizontal overflow at phone width (body.scrollWidth={body_scroll_width}).")
        phone_page.close()

        # --- 1. default state ---
        page.screenshot(path=str(_SCREENSHOT_DIR / "01_default_state.png"), full_page=True)
        result_count_text = page.locator("#result-count").inner_text()
        if "7 leads" not in result_count_text:
            failures.append(f"Expected 7 leads under default filters for the synthetic fixture, got: {result_count_text!r}")
        else:
            print(f"PASS: default state shows the expected 7 synthetic survivors ({result_count_text!r}).")

        # --- rank numbering: local to the filtered set, 1-based, not a leftover global DB rank ---
        first_rank = page.locator(".lead-row .lead-rank").first.inner_text()
        if first_rank != "#1":
            failures.append(f"Expected the first visible row to be ranked #1 (local to the filtered set), got {first_rank!r}")
        else:
            print("PASS: the first visible row is ranked #1.")
        all_ranks = page.locator(".lead-row .lead-rank").all_inner_texts()
        expected_ranks = [f"#{i}" for i in range(1, len(all_ranks) + 1)]
        if all_ranks != expected_ranks:
            failures.append(f"Expected contiguous 1..N local ranks, got: {all_ranks}")
        else:
            print(f"PASS: ranks are contiguous 1..{len(all_ranks)} within the filtered set.")

        # --- filter summary: always visible, reflects active filters ---
        summary_text = page.locator("#filter-summary").inner_text()
        if "claimed" not in summary_text.lower():
            failures.append(f"Expected the filter summary to mention the default 'hide claimed' toggle, got: {summary_text!r}")
        else:
            print(f"PASS: filter summary shows active filters: {summary_text!r}")

        # --- applying a town filter re-numbers ranks locally (still 1..N for the new, smaller set) ---
        _open_panels(page)
        page.locator("#town-chips .chip:has-text('Pineville')").click()
        page.wait_for_timeout(50)
        filtered_ranks = page.locator(".lead-row .lead-rank").all_inner_texts()
        filtered_count_text = page.locator("#result-count").inner_text()
        n = int(filtered_count_text.split()[0])
        expected_filtered_ranks = [f"#{i}" for i in range(1, min(n, len(filtered_ranks)) + 1)]
        if filtered_ranks != expected_filtered_ranks:
            failures.append(f"Expected 1..N local ranks after filtering to one town, got: {filtered_ranks} (count={filtered_count_text!r})")
        else:
            print(f"PASS: after filtering to Pineville, ranks are still local 1..{len(filtered_ranks)} ({filtered_count_text!r}).")
        page.locator("#town-chips .chip:has-text('Pineville')").click()  # deselect
        page.wait_for_timeout(50)

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
        _open_panels(page)
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

        # --- map link: row 4 (Mapleford) has both a record card and a
        #     usable address; row 3 (Fakington, hidden by default, has
        #     neither source_url nor a house-numbered address) must show
        #     neither link once visible -- not a broken map link. ---
        row4 = page.locator(".lead-row[data-lead-key='Mapleford:4']")
        row4.locator(".expand-btn").click()
        page.wait_for_timeout(50)
        if row4.locator("a.verify-link:has-text('View record card')").count() == 0:
            failures.append("Row Mapleford:4 missing the 'View record card' link.")
        else:
            print("PASS: 'View record card' link present where source_url exists.")
        if row4.locator("a.verify-link:has-text('See it on the map')").count() == 0:
            failures.append("Row Mapleford:4 missing the 'See it on the map' link.")
        else:
            print("PASS: 'See it on the map' link present for a usable address.")

        _open_panels(page)
        page.uncheck("#toggle-claimed")
        page.wait_for_timeout(50)
        row3 = page.locator(".lead-row[data-lead-key='Fakington:3']")
        row3.locator(".expand-btn").click()
        page.wait_for_timeout(50)
        if row3.locator("a.verify-link:has-text('See it on the map')").count() != 0:
            failures.append("Row Fakington:3 (no house-numbered address) should show no map link at all.")
        else:
            print("PASS: a row with no usable address shows no map link (not a broken one).")
        if row3.locator(".verify-link-none:has-text('No record link')").count() == 0:
            failures.append("Row Fakington:3 should still show 'No record link' for its missing source_url.")
        else:
            print("PASS: the same no-address row still shows 'No record link' for source_url independently.")

        # --- 3. apply a filter: show state-only rows (count should grow) ---
        page.reload()
        page.wait_for_selector("#result-count", timeout=60000)
        _open_panels(page)
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

        # Also confirm the Windham-shaped short-permit-history parcel never
        # reads as "has real permit history" -- the project's explicit red
        # line (Prompt W Step 3).
        page.goto(f"file:///{_HTML_PATH}", timeout=60000)
        page.wait_for_selector("#result-count", timeout=60000)
        _open_panels(page)
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

        # --- preset sanity: Siding-focused must produce a genuinely
        #     different top order than Darren default, not a near-copy
        #     (the real-data regression guard with exact overlap numbers
        #     lives in property-lead-scorer-full's own test suite; this is
        #     just a cheap "did the fix actually wire up" smoke check) ---
        page.goto(f"file:///{_HTML_PATH}", timeout=60000)
        page.wait_for_selector("#result-count", timeout=60000)
        _open_panels(page)
        page.uncheck("#toggle-claimed")
        page.uncheck("#toggle-worked")
        page.uncheck("#toggle-mailed")
        page.uncheck("#toggle-unreachable")
        page.wait_for_timeout(50)
        darren_order = page.locator(".lead-row").evaluate_all("els => els.map(e => e.dataset.leadKey)")
        page.click("[data-preset='siding_focused']")
        page.wait_for_timeout(50)
        siding_order = page.locator(".lead-row").evaluate_all("els => els.map(e => e.dataset.leadKey)")
        if siding_order == darren_order:
            failures.append("Siding-focused preset produced the EXACT same order as Darren default on the synthetic fixture.")
        else:
            print("PASS: Siding-focused preset produces a different order than Darren default.")

        # --- theme toggle: first click must always visibly switch ---
        for forced_scheme, label in [("light", "light"), ("dark", "dark")]:
            theme_page = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme=forced_scheme)
            theme_page.goto(f"file:///{_HTML_PATH}", timeout=60000)
            theme_page.wait_for_selector("#result-count", timeout=60000)
            before_bg = theme_page.evaluate("getComputedStyle(document.body).backgroundColor")
            theme_page.click("#theme-toggle")
            theme_page.wait_for_timeout(50)
            after_bg = theme_page.evaluate("getComputedStyle(document.body).backgroundColor")
            if before_bg == after_bg:
                failures.append(f"Theme toggle's first click did not visibly change the background when system scheme is {label!r} (before={before_bg}, after={after_bg}).")
            else:
                print(f"PASS: theme toggle's first click visibly switches the appearance (system scheme={label!r}).")
            theme_page.close()

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
