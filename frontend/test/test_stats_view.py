#!/usr/bin/env python3
"""
Test script to verify the Stats view (frontend-design.md v3.0, §16).

Covers:
  - Stats view render: stat cards, rows, tooltips (design §16.1/§16.2)
  - Title-bar control visibility in stats view (view/histogram toggles
    hidden; day filter + cutoffs visible)
  - Status bar: view label "Stats" and #range-days day count (§10.0)
  - URL state: view=stats, highCutoff/lowCutoff/dayFilter persistence
  - Back-to-Chart toggle returns to chart view
  - Empty data → info view message

Usage:
  python3 test_stats_view.py

Screenshots are saved to frontend/test/screenshots/
"""

import os
import sys

# Add the skill directory to sys.path to allow importing
skill_path = "/home/stoflom/.pi/agent/skills/firefox-testing"
if skill_path not in sys.path:
    sys.path.append(skill_path)

from firefox_tester import FirefoxTester
from selenium.webdriver.common.by import By

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
# 2026-07-27 (Mon) .. 2026-08-02 (Sun): 7 days with real data
RANGE_FROM = "2026-07-27"
RANGE_TO = "2026-08-02"
EMPTY_DATE = "2026-08-08"  # no data on this date
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def check(self, condition: bool, desc: str):
        if condition:
            self.passed += 1
            print(f"  ✓ {desc}")
        else:
            self.failed += 1
            self.failures.append(desc)
            print(f"  ✗ {desc}")


def visible(t: FirefoxTester, css: str) -> bool:
    try:
        return t.is_element_visible(By.CSS_SELECTOR, css, timeout=3)
    except Exception:
        return False


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    t = TestResult()

    with FirefoxTester(headless=True) as tester:
        # ── Test 1: Stats view render (7-day range) ──────────────────
        print(f"\n[Test 1] Stats view render: {RANGE_FROM} → {RANGE_TO}")
        tester.navigate(f"{BASE_URL}/?view=stats&from={RANGE_FROM}&to={RANGE_TO}")
        try:
            tester.wait_for_element(By.CSS_SELECTOR, ".stat-card", timeout=20)
        except Exception:
            pass

        tester.screenshot(os.path.join(SCREENSHOT_DIR, "stats-view-7day.png"))

        t.check(visible(tester, "#stats-view"), "stats-view panel visible")
        cards = tester.find_elements(By.CSS_SELECTOR, ".stat-card")
        t.check(len(cards) >= 1, f"at least one stat card rendered (got {len(cards)})")

        # View label + range days in status bar
        view_label = tester.find_element(By.ID, "view-label").text
        t.check(view_label.strip() == "Stats", f"view label is 'Stats' (got '{view_label.strip()}')")
        range_days = tester.find_element(By.ID, "range-days").text
        t.check(range_days.strip() == "7 days", f"range-days shows '7 days' (got '{range_days.strip()}')")

        # Summary-cards bar hidden in stats view
        t.check(not visible(tester, "#summary-cards"), "summary-cards bar hidden")

        if cards:
            card = cards[0]
            # Card structure: header + 5 stat rows (mean, max, min, high, low)
            rows = tester.find_elements(By.CSS_SELECTOR, ".stat-card:first-child .stat-row")
            t.check(len(rows) == 5, f"card has 5 stat rows (got {len(rows)})")
            # Card + every row carry a tooltip
            t.check(bool(card.get_attribute("data-tooltip")), "card has data-tooltip")
            no_tip = [r for r in rows if not r.get_attribute("data-tooltip")]
            t.check(len(no_tip) == 0, "all stat rows have data-tooltip")
            # Row contents: Main/Max/Min/High/Low prefixes
            mains = [el.text for el in tester.find_elements(By.CSS_SELECTOR, ".stat-card:first-child .stat-row-main", timeout=5)]
            prefixes = [m.split()[0] for m in mains]
            t.check(prefixes[0].startswith("Average"), f"row 1 is Average (got '{mains[0]}')")
            t.check(prefixes[1].startswith("Max"), f"row 2 is Max (got '{mains[1]}')")
            t.check(prefixes[2].startswith("Min"), f"row 3 is Min (got '{mains[2]}')")
            t.check(prefixes[3].startswith("High"), f"row 4 is High (got '{mains[3]}')")
            t.check(prefixes[4].startswith("Low"), f"row 5 is Low (got '{mains[4]}')")
            # Max/Min rows carry a timestamp sub-line
            subs = tester.find_elements(By.CSS_SELECTOR, ".stat-card:first-child .stat-row-sub")
            t.check(len(subs) == 4, f"max/min/high/low sub-lines present (got {len(subs)})")

        # #55: per-measurement accent colors + percent cutoffs
        accents = tester.execute_script(
            "return Array.from(document.querySelectorAll('.stat-card'))"
            ".map(c => getComputedStyle(c).borderTopColor);"
        )
        t.check(
            len(accents) >= 2 and accents[0] != accents[1],
            f"stat cards carry distinct accent colors (got {accents[:3]})",
        )
        header_color = tester.execute_script(
            "const h = document.querySelector('.stat-card .stat-card-header');"
            "return h ? getComputedStyle(h).color : null;"
        )
        t.check(header_color == accents[0] if accents else False, f"header text uses accent color (got {header_color})")

        high_sub = tester.find_element(By.CSS_SELECTOR, ".stat-card:first-child .stat-row:nth-child(5) .stat-row-sub").text
        t.check("pct" not in high_sub and "%" in high_sub, f"high sub-line uses percent, not 'pct' (got '{high_sub}')")

        # Control visibility in stats view
        vt = tester.find_element(By.ID, "view-toggle")
        t.check(visible(tester, "#view-toggle"), "view-toggle visible in stats view")
        t.check(vt.text == "\U0001F4CB Grid", f"view-toggle offers 'Grid' in stats view (got '{vt.text}')")
        t.check(not visible(tester, "#histogram-btn"), "histogram-btn hidden in stats view")
        t.check(not visible(tester, "#histogram-controls"), "bin-size/split controls hidden")
        t.check(not visible(tester, "#export-btn"), "CSV export hidden")
        t.check(visible(tester, "#day-filter-group"), "day filter group visible")
        t.check(visible(tester, "#stats-cutoffs"), "cutoff selects visible")

        stats_btn = tester.find_element(By.ID, "stats-btn")
        t.check("Back to Chart" in stats_btn.text, f"stats button shows 'Back to Chart' (got '{stats_btn.text}')")

        # ── Test 2: CSS tooltip renders on keyboard focus ────────────
        print("\n[Test 2] CSS tooltip on focus (:focus-visible ::after)")
        tester.wait(1)
        content = tester.execute_script(
            "const row = document.querySelector('.stat-card .stat-row');\n"
            "if (!row) return null;\n"
            "row.focus();\n"
            "return getComputedStyle(row, '::after').content;"
        )
        t.check(
            isinstance(content, str) and len(content) > 4,
            f"focused row renders ::after tooltip (got {str(content)[:60]!r}…)",
        )

        # ── Test 3: URL state — cutoff + day filter ──────────────────
        print("\n[Test 3] URL state: highCutoff / lowCutoff / dayFilter")
        tester.select_dropdown_option(By.ID, "high-cutoff-select", "value=90")
        try:
            tester.wait_for_url_contains("highCutoff=90", timeout=15)
        except Exception:
            pass
        t.check("highCutoff=90" in tester.get_url(), f"URL carries highCutoff=90 (got {tester.get_url()})")

        tester.select_dropdown_option(By.ID, "low-cutoff-select", "value=10")
        try:
            tester.wait_for_url_contains("lowCutoff=10", timeout=15)
        except Exception:
            pass
        t.check("lowCutoff=10" in tester.get_url(), f"URL carries lowCutoff=10 (got {tester.get_url()})")

        tester.select_dropdown_option(By.ID, "day-filter-select", "value=mon")
        try:
            tester.wait_for_url_contains("dayFilter=mon", timeout=15)
        except Exception:
            pass
        t.check("dayFilter=mon" in tester.get_url(), f"URL carries dayFilter=mon (got {tester.get_url()})")

        # Cards re-rendered with the effective cutoffs echoed in tooltips
        tester.wait(2)
        # children: 1=header, 2=avg, 3=max, 4=min, 5=high, 6=low
        tip = tester.find_element(By.CSS_SELECTOR, ".stat-card:first-child .stat-row:nth-child(5)").get_attribute("data-tooltip")
        t.check("90th percentile" in (tip or ""), "high-row tooltip echoes 90th percentile cutoff")

        tester.screenshot(os.path.join(SCREENSHOT_DIR, "stats-view-cutoffs.png"))

        # ── Test 4: single day → '1 day' in status bar ───────────────
        print("\n[Test 4] Single day: range-days shows '1 day'")
        tester.navigate(f"{BASE_URL}/?view=stats&date={RANGE_FROM}")
        try:
            tester.wait_for_element(By.CSS_SELECTOR, ".stat-card", timeout=20)
        except Exception:
            pass
        range_days = tester.find_element(By.ID, "range-days").text
        t.check(range_days.strip() == "1 day", f"range-days shows '1 day' (got '{range_days.strip()}')")

        # ── Test 5: Back to Chart ────────────────────────────────────
        print("\n[Test 5] Back to Chart button")
        tester.navigate(f"{BASE_URL}/?view=stats&from={RANGE_FROM}&to={RANGE_TO}")
        try:
            tester.wait_for_element(By.CSS_SELECTOR, ".stat-card", timeout=20)
        except Exception:
            pass
        tester.find_element(By.ID, "stats-btn").click()
        try:
            tester.wait_for_element(By.CSS_SELECTOR, "#raw-data-chart-view.visible", timeout=20)
        except Exception:
            pass
        t.check(visible(tester, "#raw-data-chart-view"), "chart view visible after back")
        t.check(not visible(tester, "#stats-view"), "stats view hidden after back")
        t.check(visible(tester, "#view-toggle"), "view-toggle visible again")
        t.check(visible(tester, "#histogram-btn"), "histogram-btn visible again")
        t.check(not visible(tester, "#stats-cutoffs"), "cutoffs hidden in chart view")
        stats_btn = tester.find_element(By.ID, "stats-btn")
        t.check("Stats" in stats_btn.text and "Back" not in stats_btn.text, f"stats button back to 'Stats' (got '{stats_btn.text}')")
        t.check("view=chart" in tester.get_url(), f"URL has view=chart (got {tester.get_url()})")

        # ── Test 6: empty data → info view ───────────────────────────
        print(f"\n[Test 6] Empty range → info view ({EMPTY_DATE})")
        tester.navigate(f"{BASE_URL}/?view=stats&date={EMPTY_DATE}")
        try:
            tester.wait_for_element(By.CSS_SELECTOR, "#info-view.visible", timeout=20)
        except Exception:
            pass
        t.check(visible(tester, "#info-view"), "info view visible")
        info_msg = tester.find_element(By.ID, "info-message").text
        t.check("No statistics available" in info_msg, f"info message mentions statistics (got '{info_msg[:60]}…')")
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "stats-view-empty.png"))

        # ── Test 7: stats-grid table variant (design §16.6) ──────────
        print("\n[Test 7] stats-grid table variant")
        tester.navigate(f"{BASE_URL}/?view=stats-grid&from={RANGE_FROM}&to={RANGE_TO}")
        try:
            tester.wait_for_element(By.CSS_SELECTOR, ".stats-grid-table tbody tr", timeout=20)
        except Exception:
            pass
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "stats-grid-view.png"))

        t.check(visible(tester, "#stats-view.stats-grid-mode"), "stats panel in grid mode")
        view_label = tester.find_element(By.ID, "view-label").text
        t.check(view_label.strip() == "Stats Grid", f"view label is 'Stats Grid' (got '{view_label.strip()}')")
        t.check(visible(tester, "#view-toggle"), "view-toggle visible in stats-grid")
        t.check(not visible(tester, "#histogram-btn"), "histogram-btn hidden in stats-grid")
        vt = tester.find_element(By.ID, "view-toggle")
        t.check(vt.text == "\U0001F4C8 Stats Cards", f"view-toggle offers 'Stats Cards' (got '{vt.text}')")

        cols = tester.find_elements(By.CSS_SELECTOR, ".stats-grid-table thead th")
        t.check(len(cols) == 9, f"9 stat columns (got {len(cols)})")
        col_texts = [c.text.lower() for c in cols]  # CSS uppercases header text
        t.check(col_texts[0] == "measurement" and col_texts[-2:] == ["high min/day", "low min/day"],
                f"column headers ordered per design (got {col_texts})")
        rows = tester.find_elements(By.CSS_SELECTOR, ".stats-grid-table tbody tr")
        t.check(len(rows) >= 1, f"at least one measurement row (got {len(rows)})")
        cells = tester.find_elements(By.CSS_SELECTOR, ".stats-grid-table tbody tr:first-child td")
        t.check(len(cells) == 9, f"row has 9 cells (got {len(cells)})")
        # Accent color on the measurement cell
        name_color = tester.execute_script(
            "const n = document.querySelector('.stats-grid-table tbody td.stats-grid-name');"
            "return n ? getComputedStyle(n).color : null;"
        )
        t.check(name_color is not None and "rgb" in name_color, f"measurement cell colored (got {name_color})")
        # High/Low cells carry method-aware tooltips
        hi_tip = cells[7].get_attribute("data-tooltip") or ""
        t.check("high threshold" in hi_tip and "percentile" in hi_tip, f"high cell tooltip (got '{hi_tip[:60]}…')")
        # Toggle back to cards
        vt.click()
        try:
            tester.wait_for_element(By.CSS_SELECTOR, ".stat-card", timeout=20)
        except Exception:
            pass
        t.check(visible(tester, ".stat-card"), "cards rendered after toggling back")
        t.check("view=stats" in tester.get_url() and "stats-grid" not in tester.get_url(),
                f"URL has view=stats after toggle (got {tester.get_url()})")

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"Results: {t.passed}/{t.passed + t.failed} passed, {t.failed} failed")
    if t.failures:
        print("\nFailed tests:")
        for f in t.failures:
            print(f"  - {f}")
    print("=" * 70)
    return 1 if t.failed else 0


if __name__ == "__main__":
    sys.exit(main())
