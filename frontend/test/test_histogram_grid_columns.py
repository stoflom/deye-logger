#!/usr/bin/env python3
"""
Test script to verify the histogram grid avg/min/max columns
(frontend-design.md v8.3, §10.2.2 — #95).

Covers:
  - Histogram grid header layout: `Time` + three columns per measurement
    (`… Avg`, `… Min`, `… Max`, in that order per measurement)
  - Avg/Min/Max cell values match the /api/histogram data/min/max arrays
    (values are formatted with one decimal — tolerance 0.06)
  - Null bins render as em-dash

Requires a running backend on :8090 with data for HISTO_DATE (see
test_histogram_range.py). Run:
  python3 test_histogram_grid_columns.py

Screenshots are saved to frontend/test/screenshots/
"""

import os
import sys
import json
from urllib.parse import urlencode
from urllib.request import urlopen

# Add the skill directory to sys.path to allow importing
skill_path = "/home/stoflom/.pi/agent/skills/firefox-testing"
if skill_path not in sys.path:
    sys.path.append(skill_path)

from firefox_tester import FirefoxTester
from selenium.webdriver.common.by import By

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
HISTO_DATE = "2026-07-27"          # a day with real data (see test_histogram_range.py)
BIN_SIZE = "60"
BINS_PER_DAY = 24                   # 60-min bins on the full-day grid
# The app's hardcoded default selected columns (shared.ts DEFAULT_COLUMN_NAMES)
DEFAULT_COLUMNS = "current_power,total_dc_power,battery_power,grid_power,battery_soc"
CROSS_CHECK_LABELS = {"Inverter Output Power L1L2", "SOC"}  # display labels in the API response
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


from test_helpers import TestResult


def api_histogram(columns: str) -> dict:
    params = urlencode({
        "from": HISTO_DATE, "to": HISTO_DATE,
        "columns": columns, "binMinutes": BIN_SIZE, "dayFilter": "all",
    })
    with urlopen(f"{BASE_URL}/api/histogram?{params}", timeout=30) as res:
        return json.loads(res.read())


def parse_cell(text: str):
    """Cell text → float, or None for empty (em-dash / blank)."""
    t = text.replace(",", "").replace("\u202f", "").replace("\u00a0", "").strip()
    if t in ("", "\u2014"):
        return None
    return float(t)


def value_close(a: float, b: float) -> bool:
    """Tolerance 0.06 — grid cells show one decimal (rounding ≤ 0.05)."""
    return abs(a - b) <= 0.06


def wait_for_grid(tester: FirefoxTester, timeout: int = 30) -> bool:
    """Poll until the AG Grid inside #histogram-grid-view has headers and rows."""
    return tester.execute_script("""
        const limit = arguments[0];
        return new Promise((resolve) => {
            const t0 = Date.now();
            const poll = () => {
                const g = document.getElementById("histogram-grid-container");
                const ready = g && g.querySelectorAll(".ag-header-cell-text").length > 0
                    && g.querySelectorAll(".ag-grid-viewport .ag-row").length > 0;
                if (ready) return resolve(true);
                if (Date.now() - t0 > limit) return resolve(false);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, timeout * 1000)


def grid_state(tester: FirefoxTester):
    return tester.execute_script("""
        const g = document.getElementById("histogram-grid-container");
        const headers = Array.from(g.querySelectorAll(".ag-header-cell-text"))
            .map(e => e.textContent.trim());
        const rows = Array.from(g.querySelectorAll(".ag-grid-viewport .ag-row"))
            .map(r => Array.from(r.querySelectorAll(".ag-cell-value")).map(c => c.textContent.trim()));
        return { headers, rows };
    """)


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    t = TestResult()

    # Ground truth from the backend
    api = api_histogram(DEFAULT_COLUMNS)
    datasets = api["datasets"]
    labels = [ds["label"] for ds in datasets]
    t.check(len(labels) == len(DEFAULT_COLUMNS.split(",")),
            f"API returned one dataset per default column (got {len(labels)})")
    t.check(all(ds.get("min") is not None and ds.get("max") is not None
                for ds in datasets),
            "API provides min/max arrays for every dataset")

    with FirefoxTester(headless=True) as tester:
        print(f"\n[Test 1] Histogram grid header layout ({HISTO_DATE}, bin {BIN_SIZE}m)")
        tester.navigate(f"{BASE_URL}/?view=histogram-grid&date={HISTO_DATE}&binSize={BIN_SIZE}")
        ok = wait_for_grid(tester)
        t.check(bool(ok), "histogram grid rendered (headers + rows)")
        tester.wait(1)
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "histogram-grid-avg-min-max.png"))

        if not ok:
            return summary(t)

        state = grid_state(tester)
        headers = state["headers"]
        rows = state["rows"]

        # Time column first, then exactly 3 columns (Avg, Min, Max) per measurement
        t.check(headers[0] == "Time", f"first header is 'Time' (got '{headers[0]}')")
        expected = 1 + 3 * len(labels)
        t.check(len(headers) == expected,
                f"1 Time + 3 columns per measurement (got {len(headers)}, expected {expected})")

        # Per-measurement header triples share a base and are ordered Avg/Min/Max
        triples_ok = len(headers) >= expected
        for i, label in enumerate(labels):
            if not triples_ok:
                break
            trio = headers[1 + 3 * i: 4 + 3 * i]
            if (len(trio) != 3
                    or not trio[0].endswith(" Avg")
                    or not trio[1].endswith(" Min")
                    or not trio[2].endswith(" Max")
                    or len(set(h[:-4].strip() for h in trio)) != 1):
                triples_ok = False
                print(f"      bad trio for '{label}': {trio}")
        t.check(triples_ok, "each measurement has '… Avg' / '… Min' / '… Max' columns in order")

        # Full-day 60-min grid → 24 bin rows (AG Grid virtualizes the tail,
        # so accept at least BINS_PER_DAY - 4 rendered rows; the rendered
        # rows are the top ones, i.e. bins 0..n-1)
        t.check(len(rows) >= BINS_PER_DAY - 4,
                f"one row per bin (got {len(rows)}, expected ~{BINS_PER_DAY})")

        print(f"\n[Test 2] Cell values match /api/histogram (Avg/Min/Max)")
        col_idx = {}  # label -> (avg, min, max) column indexes
        for i, label in enumerate(labels):
            col_idx[label] = (1 + 3 * i, 2 + 3 * i, 3 + 3 * i)

        for label in CROSS_CHECK_LABELS & set(labels):
            ds = next(d for d in datasets if d["label"] == label)
            ia, im, ix = col_idx[label]
            mismatches = []
            nulls_checked = 0
            for j, row in enumerate(rows[:BINS_PER_DAY]):  # rendered rows start at bin 0
                got_a = parse_cell(row[ia])
                got_m = parse_cell(row[im])
                got_x = parse_cell(row[ix])
                exp_a = ds["data"][j]
                exp_m = ds["min"][j]
                exp_x = ds["max"][j]
                if exp_a is None:
                    if got_a is not None:
                        mismatches.append((j, "avg", got_a, exp_a))
                    else:
                        nulls_checked += 1
                elif got_a is None or not value_close(got_a, exp_a):
                    mismatches.append((j, "avg", got_a, exp_a))
                if exp_m is None:
                    if got_m is not None:
                        mismatches.append((j, "min", got_m, exp_m))
                elif got_m is None or not value_close(got_m, exp_m):
                    mismatches.append((j, "min", got_m, exp_m))
                if exp_x is None:
                    if got_x is not None:
                        mismatches.append((j, "max", got_x, exp_x))
                elif got_x is None or not value_close(got_x, exp_x):
                    mismatches.append((j, "max", got_x, exp_x))
            t.check(not mismatches,
                    f"'{label}': all {BINS_PER_DAY} bins Avg/Min/Max match the API"
                    + (f" (first mismatch {mismatches[:3]})" if mismatches else ""))
            nulls = sum(1 for v in ds["data"][: len(rows)] if v is None)
            t.check(nulls_checked == nulls,
                    f"'{label}': null bins render as em-dash (expected {nulls}, got {nulls_checked})")

    return summary(t)


def summary(t: TestResult) -> int:
    return t.summary()


if __name__ == "__main__":
    sys.exit(main())
