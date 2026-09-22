#!/usr/bin/env python3
"""
Test script to verify the status-bar range interval display
(frontend-design.md §2.2, v8.2, #94).

Covers:
  1. Single full day of data → "1 day" (23.98 h rounds to 24.0 → 1 day).
  2. Multi-day range with fractional remainder → "13 days 12.9 hours".
  3. Partial day (< 24 h) → hours with one decimal, e.g. "14.1 hours".
  4. Fractional remainder rounding to 24.0 h carries into whole days → "3 days".
  5. Range with no data rows → calendar-day fallback ("5 days") + info view.
  6. Single sample → zero span → "0 hours".

For cases 2–4 and 6 the expected text is computed from the first/last
`device_timestamp` returned by the data API using the same 0.1 h rounding
rules as formatIntervalMs() in src/shared.ts, and case 2 additionally asserts
the literal string.

Requires the app server running on http://localhost:8090
(bash backend/start.sh -d test_solar_data.db).

Usage:
  python3 test_range_interval.py

Screenshots are saved to frontend/test/screenshots/
"""

import json
import os
import re
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
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

# Test dates (test_solar_data.db contents):
#   2026-07-21 … 2026-08-02 full days, 2026-08-14 single sample at 12:54:41
FULL_DAY = "2026-07-21"          # data 00:00:53 → 23:59:41 (23.98 h → "1 day")
FRACTIONAL_RANGE = ("2026-08-01", "2026-08-14")   # → "13 days 12.9 hours"
PARTIAL_DAY = "2026-08-02"       # data 00:00:xx → 14:07:52 (→ "… hours")
CARRY_RANGE = ("2026-07-21", "2026-07-23")        # 23.97 h remainder → "3 days"
EMPTY_RANGE = ("2026-08-05", "2026-08-09")        # no data → "5 days"
SINGLE_SAMPLE_DAY = "2026-08-14"  # one sample → "0 hours"


from test_helpers import TestResult, guard


def take_screenshot(tester, filename, description=""):
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    tester.screenshot(filepath)
    print(f"  📷 {description}: {filepath}")


def api_timestamps(date_from: str, date_to: str | None) -> list[str]:
    """Fetch device_timestamp values for a range from the data API."""
    if date_to:
        url = f"{BASE_URL}/api/data-range?{urlencode({'from': date_from, 'to': date_to, 'columns': 'device_timestamp'})}"
    else:
        url = f"{BASE_URL}/api/data?{urlencode({'date': date_from, 'columns': 'device_timestamp'})}"
    with urllib.request.urlopen(url, timeout=30) as res:
        rows = json.load(res)["rows"]
    return [str(r["device_timestamp"]) for r in rows]


def fmt_hours(tenths: int) -> str:
    """JS number-to-string convention for remTenths/10 (12.9 → '12.9', 10 → '1')."""
    v = tenths / 10
    return str(int(v)) if v == int(v) else str(v)


def expected_interval(first_ts: str, last_ts: str) -> str:
    """Mirror of formatIntervalMs() in src/shared.ts (0.1 h resolution)."""
    first = datetime.strptime(first_ts, "%Y-%m-%d %H:%M:%S")
    last = datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S")
    total_tenths = round((last - first).total_seconds() / 360)
    days, rem = divmod(total_tenths, 240)
    if days == 0:
        return "1 hour" if rem == 10 else f"{fmt_hours(rem)} hours"
    day_str = "1 day" if days == 1 else f"{days} days"
    return day_str if rem == 0 else f"{day_str} {fmt_hours(rem)} hours"


def navigate_and_read_interval(tester, params: dict) -> str:
    """Navigate to a view URL and poll until #range-days has text."""
    tester.navigate(f"{BASE_URL}/?{urlencode(params)}")
    return tester.execute_script("""
        return new Promise((resolve) => {
            const t0 = Date.now();
            const poll = () => {
                const el = document.getElementById("range-days");
                if (el && el.textContent.trim() !== "") return resolve(el.textContent.trim());
                if (Date.now() - t0 > arguments[0]) return resolve(el ? el.textContent.trim() : null);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, 30_000)


# ── Tests ───────────────────────────────────────────────────────────
def test_single_full_day(tester, t: TestResult):
    """Full day of data rounds to whole days: "1 day"."""
    print("\n[Test 1] Single full day of data → '1 day'")
    text = navigate_and_read_interval(tester, {"date": FULL_DAY, "view": "chart"})
    t.check(text == "1 day", f"#range-days shows '1 day' (got {text!r})")
    take_screenshot(tester, "range-interval-full-day.png", "Full day → '1 day'")


def test_fractional_range(tester, t: TestResult):
    """Multi-day range with fractional remainder → '13 days 12.9 hours'."""
    print("\n[Test 2] 2026-08-01 → 2026-08-14 → '13 days 12.9 hours'")
    text = navigate_and_read_interval(tester, {
        "from": FRACTIONAL_RANGE[0], "to": FRACTIONAL_RANGE[1], "view": "chart",
    })
    t.check(text == "13 days 12.9 hours", f"literal text '13 days 12.9 hours' (got {text!r})")
    tss = api_timestamps(*FRACTIONAL_RANGE)
    t.check(len(tss) > 0, f"API returned data for the range ({len(tss)} rows)")
    if tss:
        exp = expected_interval(tss[0], tss[-1])
        t.check(text == exp, f"matches API-derived span {exp!r} (got {text!r})")
    take_screenshot(tester, "range-interval-fractional.png", "Multi-day with hours")


def test_partial_day_hours(tester, t: TestResult):
    """Partial day (< 24 h) → hours with one decimal."""
    print(f"\n[Test 3] Single partial day {PARTIAL_DAY} → '<N> hours'")
    text = navigate_and_read_interval(tester, {"date": PARTIAL_DAY, "view": "chart"})
    t.check(re.fullmatch(r"\d+(\.\d)? hours", text) is not None,
            f"hours-only format (got {text!r})")
    tss = api_timestamps(PARTIAL_DAY, None)
    t.check(len(tss) > 0, f"API returned data for the day ({len(tss)} rows)")
    if tss:
        exp = expected_interval(tss[0], tss[-1])
        t.check(text == exp, f"matches API-derived span {exp!r} (got {text!r})")
    take_screenshot(tester, "range-interval-partial-day.png", "Partial day → hours")


def test_remainder_carry(tester, t: TestResult):
    """Fractional remainder of 23.97 h rounds to 24.0 and carries: '3 days'."""
    print("\n[Test 4] 2026-07-21 → 2026-07-23 → '3 days' (remainder carry)")
    text = navigate_and_read_interval(tester, {
        "from": CARRY_RANGE[0], "to": CARRY_RANGE[1], "view": "chart",
    })
    t.check(text == "3 days", f"remainder 23.97 h carries to '3 days' (got {text!r})")
    tss = api_timestamps(*CARRY_RANGE)
    if tss:
        exp = expected_interval(tss[0], tss[-1])
        t.check(text == exp, f"matches API-derived span {exp!r} (got {text!r})")
    take_screenshot(tester, "range-interval-carry.png", "Remainder carry → whole days")


def test_empty_range_fallback(tester, t: TestResult):
    """Range with no data → calendar-day fallback + info view."""
    print(f"\n[Test 5] Empty range {EMPTY_RANGE[0]} → {EMPTY_RANGE[1]} → '5 days' fallback")
    text = navigate_and_read_interval(tester, {
        "from": EMPTY_RANGE[0], "to": EMPTY_RANGE[1], "view": "chart",
    })
    t.check(text == "5 days", f"calendar-day fallback '5 days' (got {text!r})")
    info_visible = tester.execute_script(
        "return document.getElementById('info-view').style.display !== 'none';"
    )
    t.check(bool(info_visible), "info view shown for empty range")
    take_screenshot(tester, "range-interval-empty-fallback.png", "Empty range → calendar days")


def test_single_sample(tester, t: TestResult):
    """Single sample → zero span → '0 hours'."""
    print(f"\n[Test 6] Single sample day {SINGLE_SAMPLE_DAY} → '0 hours'")
    text = navigate_and_read_interval(tester, {"date": SINGLE_SAMPLE_DAY, "view": "chart"})
    t.check(text == "0 hours", f"zero span '0 hours' (got {text!r})")
    take_screenshot(tester, "range-interval-single-sample.png", "Single sample → 0 hours")


# ── Main ────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Deye Logger Viewer - Status Bar Range Interval Tests (#94)")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print("\n[Setup] Starting Firefox (headless mode)...")

    t = TestResult()
    with FirefoxTester(headless=True) as tester:
        tester.navigate(f"{BASE_URL}/?{urlencode({'date': FULL_DAY})}")
        print(f"[Setup] Page title: {tester.get_title()}")

        try:
            test_single_full_day(tester, t)
            test_fractional_range(tester, t)
            test_partial_day_hours(tester, t)
            test_remainder_carry(tester, t)
            test_empty_range_fallback(tester, t)
            test_single_sample(tester, t)
        finally:
            sys.exit(t.summary())


if __name__ == "__main__":
    guard(main)
