#!/usr/bin/env python3
"""
Test script to verify the Stats view (frontend-design.md v3.0, §16).

Covers:
  - Stats view render: stat cards, rows, tooltips (design §16.1/§16.2)
  - Title-bar control visibility in stats view (view/histogram toggles
    hidden; day filter + cutoffs visible)
  - Status bar: view label "Stats" and #range-days data span (§10.0, v8.4 — #97)
  - URL state: view=stats, highCutoff/lowCutoff/dayFilter persistence
  - Back-to-Chart toggle returns to chart view
  - Empty data → info view message

Usage:
  python3 test_stats_view.py

Screenshots are saved to frontend/test/screenshots/
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from urllib.parse import urlencode

# Add the skill directory to sys.path to allow importing
skill_path = "/home/stoflom/.pi/agent/skills/firefox-testing"
if skill_path not in sys.path:
    sys.path.append(skill_path)

from firefox_tester import FirefoxTester
from selenium.webdriver.common.by import By

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
# 2026-07-27 (Mon) .. 2026-08-02 (Sun): 7 calendar days with real data.
# Data span (first → last sample): 2026-07-27 00:00:49 → 2026-08-02 14:07:52
# → "6 days 14.1 hours" (v8.4 — #97: status bar shows the backend data span).
RANGE_FROM = "2026-07-27"
RANGE_TO = "2026-08-02"


def api_span(date_from: str, date_to: str) -> tuple[str, str]:
    """Fetch the `span` field from /api/stats (backend v4.5, #97)."""
    url = f"{BASE_URL}/api/stats?{urlencode({'from': date_from, 'to': date_to, 'columns': 'current_power'})}"
    with urllib.request.urlopen(url, timeout=30) as res:
        span = json.load(res)["span"]
    return span["first"], span["last"]


def expected_interval(first_ts: str, last_ts: str) -> str:
    """Mirror of formatIntervalMs() in src/shared.ts (0.1 h resolution)."""
    first = datetime.strptime(first_ts, "%Y-%m-%d %H:%M:%S")
    last = datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S")
    total_tenths = round((last - first).total_seconds() / 360)
    days, rem = divmod(total_tenths, 240)
    if days == 0:
        v = rem / 10
        return "1 hour" if rem == 10 else (f"{int(v)} hours" if v == int(v) else f"{v} hours")
    v = rem / 10
    rem_str = "" if rem == 0 else (f" {int(v)} hours" if v == int(v) else f" {v} hours")
    day_str = "1 day" if days == 1 else f"{days} days"
    return day_str + rem_str
EMPTY_DATE = "2026-08-08"  # no data on this date
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


from test_helpers import TestResult


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
        # v8.4 (#97): stats view shows the backend data span, not the
        # calendar-day count (last day is partial: data ends 14:07:52)
        t.check(range_days.strip() == "6 days 14.1 hours",
                f"range-days shows data span '6 days 14.1 hours' (got '{range_days.strip()}')")
        first_ts, last_ts = api_span(RANGE_FROM, RANGE_TO)
        t.check(range_days.strip() == expected_interval(first_ts, last_ts),
                f"range-days matches /api/stats span {first_ts} → {last_ts}")

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
        # #60: the cutoff is no longer echoed in braces on the card (shown in the top bar)
        t.check("(" not in high_sub, f"high sub-line has no cutoff in braces (got '{high_sub}')")

        # #60: a %-unit column (Battery SOC) shows the selected cutoff as an
        # absolute percent limit — high '> 95 %', low '< 5 %' (defaults 95/5).
        soc = tester.execute_script(
            "const cards = Array.from(document.querySelectorAll('.stat-card'));"
            "const c = cards.find(c => {const h = c.querySelector('.stat-card-header');"
            "  return h && h.textContent.includes('SOC');});"
            "if (!c) return null;"
            "const rows = c.querySelectorAll('.stat-row');"
            "const hs = rows[3].querySelector('.stat-row-sub');"
            "const ls = rows[4].querySelector('.stat-row-sub');"
            "return [hs ? hs.textContent.trim() : '', ls ? ls.textContent.trim() : ''];"
        )
        t.check(soc is not None, "Battery SOC stat card present")
        if soc:
            t.check(soc[0] == "> 95 %", f"SOC high sub reads '> 95 %' (got '{soc[0]}')")
            t.check(soc[1] == "< 5 %", f"SOC low sub reads '< 5 %' (got '{soc[1]}')")

        # Control visibility in stats view
        vt = tester.find_element(By.ID, "view-toggle")
        t.check(visible(tester, "#view-toggle"), "view-toggle visible in stats view")
        t.check(vt.text == "\U0001F4CB Grid", f"view-toggle offers 'Grid' in stats view (got '{vt.text}')")
        # #62: stats is a major view — the other major buttons stay visible (blue);
        # only grid views and the Select view hide them
        t.check(visible(tester, "#histogram-btn"), "histogram-btn visible (blue) in stats view")
        t.check(visible(tester, "#chart-btn"), "Series (chart-btn) visible (blue) in stats view")
        t.check(not visible(tester, "#histogram-controls"), "bin-size/day-filter controls hidden")
        t.check(not visible(tester, "#export-btn"), "CSV export hidden")
        t.check(visible(tester, "#day-filter-group"), "day filter group visible")
        t.check(visible(tester, "#stats-cutoffs"), "cutoff selects visible")

        # #62: the active major-view button is disabled (grey)
        stats_btn = tester.find_element(By.ID, "stats-btn")
        t.check(stats_btn.text.strip() == "\U0001F4C8 Stats", f"stats button reads 'Stats' (got '{stats_btn.text}')")
        t.check(stats_btn.get_attribute("disabled") is not None,
                "stats button disabled (grey, active view) in stats view")
        t.check(tester.find_element(By.ID, "histogram-btn").get_attribute("disabled") is None,
                "histogram button enabled (blue) in stats view")
        # #61: minutes use 'mins' so they are not confused with 'Min' (minimum)
        high_main = tester.find_elements(By.CSS_SELECTOR, ".stat-card:first-child .stat-row-main")[3].text
        t.check("mins/day" in high_main and " min/day" not in high_main,
                f"high row uses 'mins/day' for minutes (got '{high_main}')")

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
        # #87: highCutoff=90 → threshold at top 10% of the observed range
        t.check("top 10% of the observed range" in (tip or ""), "high-row tooltip echoes observed-range cutoff")

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

        # ── Test 5: return to the Series view via the Series major button ──
        print("\n[Test 5] Series button returns to the chart view")
        tester.navigate(f"{BASE_URL}/?view=stats&from={RANGE_FROM}&to={RANGE_TO}")
        try:
            tester.wait_for_element(By.CSS_SELECTOR, ".stat-card", timeout=20)
        except Exception:
            pass
        tester.find_element(By.ID, "chart-btn").click()
        try:
            tester.wait_for_element(By.CSS_SELECTOR, "#raw-data-chart-view.visible", timeout=20)
        except Exception:
            pass
        t.check(visible(tester, "#raw-data-chart-view"), "chart view visible after switch")
        t.check(not visible(tester, "#stats-view"), "stats view hidden after switch")
        t.check(visible(tester, "#view-toggle"), "view-toggle visible again")
        t.check(visible(tester, "#histogram-btn"), "histogram-btn visible again")
        t.check(not visible(tester, "#stats-cutoffs"), "cutoffs hidden in chart view")
        stats_btn = tester.find_element(By.ID, "stats-btn")
        t.check("Stats" in stats_btn.text and "Back" not in stats_btn.text, f"stats button reads 'Stats' (got '{stats_btn.text}')")
        t.check(stats_btn.get_attribute("disabled") is None, "stats button enabled in chart view")
        t.check(tester.find_element(By.ID, "chart-btn").get_attribute("disabled") is not None,
                "Series button disabled (grey, active view) in chart view")
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
        t.check(not visible(tester, "#chart-btn"), "Series (chart-btn) hidden in stats-grid")
        vt = tester.find_element(By.ID, "view-toggle")
        t.check(vt.text == "Back", f"view-toggle reads 'Back' in stats-grid (got '{vt.text}')")

        cols = tester.find_elements(By.CSS_SELECTOR, ".stats-grid-table thead th")
        t.check(len(cols) == 9, f"9 stat columns (got {len(cols)})")
        col_texts = [c.text.lower() for c in cols]  # CSS uppercases header text
        t.check(col_texts[0] == "measurement" and col_texts[-2:] == ["high mins/day", "low mins/day"],
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
        t.check("high threshold" in hi_tip and "observed range" in hi_tip, f"high cell tooltip (got '{hi_tip[:60]}…')")
        # #59: cutoff change in stats-grid keeps the grid variant
        tester.select_dropdown_option(By.ID, "high-cutoff-select", "value=90")
        try:
            tester.wait_for_url_contains("highCutoff=90", timeout=15)
        except Exception:
            pass
        t.check("view=stats-grid" in tester.get_url() and "highCutoff=90" in tester.get_url(),
                f"cutoff change keeps stats-grid in URL (got {tester.get_url()})")
        t.check(visible(tester, ".stats-grid-table"), "stats table re-rendered (not cards)")
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
    return t.summary()


if __name__ == "__main__":
    sys.exit(main())
