#!/usr/bin/env python3
"""
Test script to verify the Series chart renders RAW data (frontend-design.md
§15.8, #88 — supersedes the v7.2 bucket flooring of #85).

Covers:
  1. Every data point is plotted: for each numeric column, the dataset holds
     exactly one point per raw row (count matches /api/data), at the row's
     actual timestamp (x values within the day, ascending).
  2. Peaks are visible: the dataset min/max equal the raw-data min/max
     (no binning, no downsampling).
  3. No smoothing: every dataset has tension === 0 and showLine === true
     (straight segments between consecutive samples).
  4. The x-axis still spans the full day 00:00–24:00 (linear time axis).

Requires the app server running on http://localhost:8090 (bash backend/start.sh).

Usage:
  python3 test_series_raw_points.py

Screenshots are saved to frontend/test/screenshots/
"""

import json
import os
import sys
import urllib.request
from urllib.parse import quote, urlencode

# Add the skill directory to sys.path to allow importing
skill_path = "/home/stoflom/.pi/agent/skills/firefox-testing"
if skill_path not in sys.path:
    sys.path.append(skill_path)

from firefox_tester import FirefoxTester
from selenium.webdriver.common.by import By

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
TEST_DATE = "2026-07-27"  # Date with actual data
# The default numeric column set (frontend/src/shared.ts DEFAULT_COLUMN_NAMES)
NUMERIC_COLUMNS = ["current_power", "total_dc_power", "battery_power", "grid_power", "battery_soc"]
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


def fetch_raw_rows():
    """Ground truth: all raw rows for the test date from the API."""
    url = (f"{BASE_URL}/api/data?date={TEST_DATE}"
           f"&columns={quote(','.join(NUMERIC_COLUMNS), safe='')}")
    with urllib.request.urlopen(url, timeout=30) as res:
        payload = json.loads(res.read().decode())
    return payload["rows"]


def raw_stats(rows):
    """Per-column (count, min, max) over numeric samples, ground truth."""
    stats = {}
    for col in NUMERIC_COLUMNS:
        vals = [r[col] for r in rows if isinstance(r.get(col), (int, float))]
        stats[col] = {"count": len(vals), "min": min(vals), "max": max(vals)}
    return stats


def wait_for_series_chart(tester, timeout: int = 30):
    """Poll until the test hook exposes the live Series Chart instance."""
    return tester.execute_script("""
        return new Promise((resolve) => {
            const t0 = Date.now();
            const poll = () => {
                const c = document.getElementById("chart-canvas");
                if (c && c.__chartInstance) return resolve(true);
                if (Date.now() - t0 > arguments[0]) return resolve(false);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, timeout * 1000)


def series_datasets_info(tester):
    """Per-dataset geometry + options of the Series chart."""
    return tester.execute_script("""
        const c = document.getElementById("chart-canvas");
        if (!c || !c.__chartInstance) return null;
        const ch = c.__chartInstance;
        const x = ch.options.scales.x;
        const out = ch.data.datasets.map((ds) => {
            const pts = ds.data;
            const ys = pts.map((p) => p.y);
            const xs = pts.map((p) => p.x);
            let sorted = true;
            for (let i = 1; i < xs.length; i++) if (xs[i] < xs[i-1]) { sorted = false; break; }
            return {
                label: ds.label,
                count: pts.length,
                yMin: ys.length ? Math.min(...ys) : null,
                yMax: ys.length ? Math.max(...ys) : null,
                xFirst: xs.length ? xs[0] : null,
                xLast: xs.length ? xs[xs.length-1] : null,
                xSorted: sorted,
                tension: "tension" in ds ? ds.tension : undefined,
                showLine: "showLine" in ds ? ds.showLine : undefined,
            };
        });
        return {
            xMin: "min" in x ? x.min : undefined,
            xMax: "max" in x ? x.max : undefined,
            datasets: out,
        };
    """)


def test_series_raw_points(tester, t: TestResult):
    print("\n[Test 1] Series chart: every raw point plotted, peaks preserved")
    rows = fetch_raw_rows()
    stats = raw_stats(rows)
    print(f"  (ground truth: {len(rows)} rows from /api/data)")

    tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': 'chart'})}")
    tester.wait_for_element(By.ID, "summary-cards")
    ok = wait_for_series_chart(tester)
    t.check(ok, "Series chart instance exposed on #chart-canvas")
    if not ok:
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "rawpoints-missing.png"))
        return

    info = series_datasets_info(tester)
    day0 = tester.execute_script(f"return new Date('{TEST_DATE}T00:00:00').getTime();")
    day1 = day0 + 86_400_000
    t.check(info["xMin"] == day0 and info["xMax"] == day1,
            "x-axis still spans full day 00:00–24:00")

    ds_list = info["datasets"]
    t.check(len(ds_list) == len(NUMERIC_COLUMNS),
            f"{len(NUMERIC_COLUMNS)} numeric datasets rendered (got {len(ds_list)})")

    # Match each ground-truth column to a dataset by (count, min, max).
    used = set()
    for col in NUMERIC_COLUMNS:
        s = stats[col]
        match = next(
            (i for i, d in enumerate(ds_list) if i not in used
             and d["count"] == s["count"]
             and (s["min"] is None or d["yMin"] == s["min"])
             and (s["max"] is None or d["yMax"] == s["max"])),
            None,
        )
        if match is None:
            t.check(False,
                    f"{col}: dataset with raw count/min/max not found "
                    f"(want {s['count']} pts, min {s['min']}, max {s['max']})")
            continue
        used.add(match)
        d = ds_list[match]
        t.check(d["count"] == s["count"],
                f"{col}: all {s['count']} points plotted (got {d['count']})")
        t.check(d["yMax"] == s["max"],
                f"{col}: peak preserved (dataset max {d['yMax']} == raw max {s['max']})")
        t.check(d["xSorted"], f"{col}: points in ascending timestamp order")
        t.check(d["xFirst"] is not None and day0 <= d["xFirst"] < day1
                and d["xLast"] is not None and day0 <= d["xLast"] < day1,
                f"{col}: points lie within the selected day")

    tester.screenshot(os.path.join(SCREENSHOT_DIR, "rawpoints-series.png"))


def test_series_no_smoothing(tester, t: TestResult):
    print("\n[Test 2] Series chart: no curve smoothing (straight segments)")
    info = series_datasets_info(tester)
    ds_list = info["datasets"]
    t.check(len(ds_list) > 0, "Series datasets present")
    for d in ds_list:
        t.check(d["tension"] == 0, f"{d['label']}: tension === 0 (got {d['tension']})")
        t.check(d["showLine"] is True, f"{d['label']}: showLine === true")


# ── Main ────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Deye Logger Viewer - Series Raw-Points Tests (#88)")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print("\n[Setup] Starting Firefox (headless mode)...")

    t = TestResult()
    uncaught = None
    with FirefoxTester(headless=True) as tester:
        tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE})}")
        print(f"[Setup] Page title: {tester.get_title()}")

        try:
            test_series_raw_points(tester, t)
            # Re-navigate to a fresh chart for the smoothing checks
            tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': 'chart'})}")
            tester.wait_for_element(By.ID, "summary-cards")
            wait_for_series_chart(tester)
            test_series_no_smoothing(tester, t)
        except Exception as exc:  # re-raised after summary so errors are visible
            uncaught = exc
        finally:
            print("\n" + "=" * 70)
            print(f"Results: {t.passed}/{t.passed + t.failed} passed, {t.failed} failed")
            if t.failed > 0:
                print("\nFailed tests:")
                for f in t.failures:
                    print(f"  - {f}")
            print("=" * 70)

    if uncaught is not None:
        raise uncaught
    sys.exit(1 if t.failed > 0 else 0)


if __name__ == "__main__":
    main()
