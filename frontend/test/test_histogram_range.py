#!/usr/bin/env python3
"""
Test script to verify the histogram per-bin value range rendering
(frontend-design.md v7.1, §9.2/§10.2.1 — #82/#83).

Covers:
  - One bar chart per selected column (`.histogram-chart-item canvas`)
  - Range band: full-width translucent floating-bar dataset ([min,max] per
    bin, null for zero-spread bins), `barPercentage:1, categoryPercentage:1,
    grouped:false`, behind the average bar (order 1)
  - Average bar: centred on top of the band at ~60% width
    (`barPercentage:0.6, categoryPercentage:1, grouped:false`, order 0)
  - Dataset values match the /api/histogram response exactly
  - Tooltip: range datasets filtered out; min/max appended to the average
    label as `(range min–max)`

Requires a running backend on :8090 with data for HISTO_DATE (see
test_stats_view.py). Run:
  python3 test_histogram_range.py

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

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
HISTO_DATE = "2026-07-27"          # a day with real data (see test_stats_view.py)
BIN_SIZE = "60"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

# Columns cross-checked against the raw API (must exist in the DB)
CROSS_CHECK_COLUMNS = "current_power,battery_soc"


from test_helpers import TestResult, guard


def api_histogram(columns: str) -> dict:
    params = urlencode({
        "from": HISTO_DATE, "to": HISTO_DATE,
        "columns": columns, "binMinutes": BIN_SIZE, "dayFilter": "all",
    })
    with urlopen(f"{BASE_URL}/api/histogram?{params}", timeout=30) as res:
        return json.loads(res.read())


def wait_for_charts(tester: FirefoxTester, timeout: int = 30):
    """Poll until the test hook exposes a live Chart instance on a canvas."""
    return tester.execute_script("""
        return new Promise((resolve) => {
            const t0 = Date.now();
            const poll = () => {
                const c = document.querySelector(".histogram-chart-item canvas");
                if (c && c.__chartInstance) return resolve(true);
                if (Date.now() - t0 > arguments[0]) return resolve(false);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, timeout * 1000)


def chart_info(tester: FirefoxTester, canvas_id: str):
    """Return the chart's datasets (with the fields the tests need) + options."""
    return tester.execute_script("""
        const c = document.getElementById(arguments[0]).__chartInstance;
        if (!c) return null;
        return {
            title: c.canvas.parentElement.parentElement.querySelector(".histogram-chart-title")?.textContent ?? null,
            legendDisplay: c.options.plugins.legend.display,
            datasets: c.data.datasets.map(ds => ({
                label: ds.label,
                isRange: !!ds._isRange,
                minArr: ds._min ? Array.from(ds._min) : null,
                maxArr: ds._max ? Array.from(ds._max) : null,
                data: ds.data,
                backgroundColor: ds.backgroundColor,
                barPercentage: ds.barPercentage,
                categoryPercentage: ds.categoryPercentage,
                grouped: ds.grouped,
                order: ds.order,
            })),
        };
    """, canvas_id)


def has_spread(mins, maxs) -> bool:
    return any(a != b for a, b in zip(mins, maxs))


def approx_equal(a, b) -> bool:
    """List equality with float tolerance (JS↔Python round-trip can shift
    the last ULP, e.g. 905.4333333333332 vs ...333)."""
    if a is None or b is None:
        return a is b
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x is None or y is None:
            if x is not y:
                return False
        elif abs(x - y) > 1e-9 * max(1.0, abs(x), abs(y)):
            return False
    return True


def range_entries_ok(range_data, mins, maxs) -> bool:
    """[min,max] per bin with spread, null for zero-spread bins."""
    for j, entry in enumerate(range_data):
        if mins[j] == maxs[j]:
            if entry is not None:
                return False
        elif (not isinstance(entry, list)) or len(entry) != 2:
            return False
        elif not approx_equal(entry, [mins[j], maxs[j]]):
            return False
    return True


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    t = TestResult()

    # Ground truth from the backend (chart label = API label + unit suffix)
    api = api_histogram(CROSS_CHECK_COLUMNS)
    api_by_label = {ds["label"]: ds for ds in api["datasets"]}

    with FirefoxTester(headless=True) as tester:
        # ── Test 1: per-column charts — range band + average geometry ──
        print(f"\n[Test 1] Per-column histogram range rendering ({HISTO_DATE}, bin {BIN_SIZE}m)")
        tester.navigate(f"{BASE_URL}/?view=histogram&date={HISTO_DATE}&binSize={BIN_SIZE}")
        ok = wait_for_charts(tester)
        t.check(bool(ok), "per-column chart instance present")
        tester.wait(1)
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "histogram-range-per-column.png"))

        canvas_ids = tester.execute_script(
            "return Array.from(document.querySelectorAll('.histogram-chart-item canvas'))"
            ".map(c => c.id);")
        t.check(len(canvas_ids) >= 1, f"per-column canvases present (got {len(canvas_ids)})")

        with_spread = 0
        checked = 0
        for cid in canvas_ids or []:
            info = chart_info(tester, cid)
            if not info:
                continue

            t.check(info["title"] is not None, f"{cid}: chart title present")
            t.check(info["legendDisplay"] is False, f"{cid}: legend hidden")

            api_ds = api_by_label.get(info["title"])
            dss = info["datasets"]
            avg = dss[-1]
            has_range = len(dss) > 1 and bool(dss[0]["isRange"])

            # Geometry: average bar centred on the full-width range band (#83)
            t.check(avg["barPercentage"] == 0.6 and avg["categoryPercentage"] == 1
                    and avg["grouped"] is False and avg["order"] == 0,
                    f"'{info['title']}': average bar ~60% width, centred (grouped:false)")

            if api_ds is not None:
                expected_spread = has_spread(api_ds["min"], api_ds["max"])
                t.check(has_range == expected_spread,
                        f"'{info['title']}': range dataset present={has_range}, expected {expected_spread}")
                t.check(approx_equal(avg["minArr"], api_ds["min"])
                        and approx_equal(avg["maxArr"], api_ds["max"]),
                        f"'{info['title']}': chart min/max equal /api/histogram values")
                t.check(approx_equal(avg["data"], api_ds["data"]),
                        f"'{info['title']}': average values equal /api/histogram values")
                if has_range and expected_spread:
                    band = dss[0]
                    t.check(band["label"].endswith(" (range)"),
                            f"'{info['title']}': range dataset label ends with '(range)'")
                    t.check(isinstance(band["backgroundColor"], str)
                             and band["backgroundColor"].endswith("33"),
                            f"'{info['title']}': range band uses ~20% opacity fill (got {band['backgroundColor']})")
                    t.check(band["barPercentage"] == 1 and band["categoryPercentage"] == 1
                            and band["grouped"] is False and band["order"] == 1,
                            f"'{info['title']}': range band full-width behind average (grouped:false)")
                    t.check(range_entries_ok(band["data"], api_ds["min"], api_ds["max"]),
                            f"'{info['title']}': range band data matches API min/max for all bins")
                if expected_spread:
                    with_spread += 1
                checked += 1

        t.check(checked >= 2, f"at least {CROSS_CHECK_COLUMNS} charts cross-checked (got {checked})")
        t.check(with_spread >= 1, f"at least one column shows a range (got {with_spread})")

        # ── Test 2: tooltip — range appended to the average label ─────
        print(f"\n[Test 2] Tooltip on a per-column chart")
        tip = tester.execute_script("""
            const canvas = Array.from(document.querySelectorAll(".histogram-chart-item canvas"))
                .find(c => {
                    const ch = c.__chartInstance;
                    const avg = ch && ch.data.datasets[ch.data.datasets.length - 1];
                    return avg && avg._min && avg._min.some((m, j) => m !== avg._max[j]);
                });
            if (!canvas) return null;
            const c = canvas.__chartInstance;
            const idx = c.data.datasets.findIndex(ds => ds._isRange !== true);
            const ds = c.data.datasets[idx];
            const j = ds._min.findIndex((m, k) => m !== ds._max[k]);
            c.setActiveElements([{ datasetIndex: idx, index: j }], { x: 10, y: 10 });
            c.tooltip._active = c._active;
            c.tooltip._eventPosition = { x: 10, y: 10 };
            c.tooltip.update(true);
            const points = (c.tooltip.dataPoints || []).map(d => d.dataset.label);
            const lines = (c.tooltip.body || []).map(b => (b.lines || []).join(" "));
            return { points, lines };
        """)
        t.check(tip is not None and tip.get("points"), f"tooltip produced for a spread bin (got {tip})")
        if tip:
            t.check(all("(range)" not in p for p in tip["points"]),
                    f"tooltip excludes range datasets (got {tip['points']})")
            t.check(any("(range " in line for line in tip["lines"]),
                    f"tooltip label appends '(range min–max)' (got {tip['lines']})")

    return summary(t)


def summary(t: TestResult) -> int:
    return t.summary()


if __name__ == "__main__":
    guard(main)
