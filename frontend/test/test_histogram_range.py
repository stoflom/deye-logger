#!/usr/bin/env python3
"""
Test script to verify the histogram per-bin value range rendering
(frontend-design.md v6.0, §10.2.1 — #81).

Covers:
  - Combined histogram: per-column translucent floating-bar range datasets
    ([min,max] per bin, null for zero-spread bins) alongside the average bars
  - Range dataset data matches the /api/histogram min/max response exactly
  - Range datasets are excluded from the legend
  - Tooltip: range datasets filtered out; min/max appended to the average
    label as `(range min–max)`
  - Split mode: each per-column chart carries the same range rendering

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
from selenium.webdriver.common.by import By

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
HISTO_DATE = "2026-07-27"          # a day with real data (see test_stats_view.py)
BIN_SIZE = "60"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

# Columns cross-checked against the raw API (must exist in the DB)
CROSS_CHECK_COLUMNS = "current_power,battery_soc"


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


def api_histogram(columns: str) -> dict:
    params = urlencode({
        "from": HISTO_DATE, "to": HISTO_DATE,
        "columns": columns, "binMinutes": BIN_SIZE, "dayFilter": "all",
    })
    with urlopen(f"{BASE_URL}/api/histogram?{params}", timeout=30) as res:
        return json.loads(res.read())


def wait_for_chart(tester: FirefoxTester, canvas_id: str, timeout: int = 30):
    """Poll until the test hook exposes a live Chart instance on the canvas."""
    tester.execute_script("""
        return new Promise((resolve) => {
            const canvas = document.getElementById(arguments[0]);
            const t0 = Date.now();
            const poll = () => {
                if (canvas && canvas.__chartInstance) return resolve(true);
                if (Date.now() - t0 > arguments[1]) return resolve(false);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, canvas_id, timeout * 1000)


def chart_datasets(tester: FirefoxTester, canvas_id: str):
    """Return the chart's dataset array with the fields the tests need."""
    return tester.execute_script("""
        const c = document.getElementById(arguments[0]).__chartInstance;
        if (!c) return null;
        return c.data.datasets.map(ds => ({
            label: ds.label,
            isRange: !!ds._isRange,
            minArr: ds._min ? Array.from(ds._min) : null,
            maxArr: ds._max ? Array.from(ds._max) : null,
            data: ds.data,
            backgroundColor: ds.backgroundColor,
        }));
    """, canvas_id)


def has_spread(mins, maxs) -> bool:
    return any(a != b for a, b in zip(mins, maxs))


def range_entries_ok(range_data, mins, maxs) -> bool:
    """[min,max] per bin with spread, null for zero-spread bins."""
    for j, entry in enumerate(range_data):
        if mins[j] == maxs[j]:
            if entry is not None:
                return False
        elif (not isinstance(entry, list)) or len(entry) != 2 \
                or abs(entry[0] - mins[j]) > 1e-9 or abs(entry[1] - maxs[j]) > 1e-9:
            return False
    return True


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    t = TestResult()

    # Ground truth from the backend (chart label = API label + unit suffix)
    api = api_histogram(CROSS_CHECK_COLUMNS)
    api_by_chart_label = {
        (f"{ds['label']} ({ds['unit']})" if ds["unit"] else ds["label"]): ds
        for ds in api["datasets"]
    }

    with FirefoxTester(headless=True) as tester:
        # ── Test 1: combined histogram — range datasets ─────────────
        print(f"\n[Test 1] Combined histogram range rendering ({HISTO_DATE}, bin {BIN_SIZE}m)")
        tester.navigate(f"{BASE_URL}/?view=histogram&date={HISTO_DATE}&binSize={BIN_SIZE}")
        wait_for_chart(tester, "histogram-canvas")
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "histogram-range-combined.png"))

        datasets = chart_datasets(tester, "histogram-canvas")
        t.check(datasets is not None, "combined chart instance present on canvas")
        if datasets is None:
            return summary(t)

        avg_with_spread = 0
        for i, ds in enumerate(datasets):
            if ds["isRange"]:
                t.check(ds["label"].endswith(" (range)"),
                        f"range dataset {i} label ends with '(range)' (got '{ds['label']}')")
                t.check(isinstance(ds["backgroundColor"], str) and ds["backgroundColor"].endswith("33"),
                        f"range dataset {i} uses ~20% opacity fill (got {ds['backgroundColor']})")
                continue

            paired = i + 1 < len(datasets) and datasets[i + 1]["isRange"]
            api_ds = api_by_chart_label.get(ds["label"])

            if ds["minArr"] is not None and ds["maxArr"] is not None:
                expected = has_spread(ds["minArr"], ds["maxArr"])
                t.check(paired == expected,
                        f"'{ds['label']}': range dataset present={paired}, expected {expected}")
                if expected:
                    avg_with_spread += 1
                    t.check(range_entries_ok(datasets[i + 1]["data"], ds["minArr"], ds["maxArr"]),
                            f"'{ds['label']}': range entries are [min,max] per spread bin, null otherwise")

            # Cross-check against the raw API for the known columns
            if api_ds is not None:
                t.check(ds["minArr"] is not None and ds["maxArr"] is not None,
                        f"'{ds['label']}': chart carries min/max arrays")
                if ds["minArr"] is not None and ds["maxArr"] is not None:
                    t.check(ds["minArr"] == api_ds["min"] and ds["maxArr"] == api_ds["max"],
                            f"'{ds['label']}': chart min/max equal /api/histogram values")
                    if has_spread(api_ds["min"], api_ds["max"]):
                        t.check(paired and range_entries_ok(datasets[i + 1]["data"],
                                                            api_ds["min"], api_ds["max"]),
                                f"'{ds['label']}': range dataset matches API min/max for all bins")

        t.check(avg_with_spread >= 1, f"at least one column shows a range (got {avg_with_spread})")

        # Legend: no '(range)' entries
        legend_items = tester.execute_script(
            "const c = document.getElementById('histogram-canvas').__chartInstance;"
            "return c ? c.legend.legendItems.map(i => i.text) : null;")
        t.check(legend_items is not None, "legend items readable")
        if legend_items:
            t.check(all("(range)" not in item for item in legend_items),
                    f"legend has no '(range)' entries (got {legend_items})")

        # Tooltip: range datasets filtered out; range appended to the average label
        tip = tester.execute_script("""
            const c = document.getElementById('histogram-canvas').__chartInstance;
            if (!c) return null;
            const idx = c.data.datasets.findIndex(ds => ds._isRange !== true
                && ds._min && ds._min.some((m, j) => m !== ds._max[j]));
            if (idx < 0) return null;
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

        # ── Test 2: split mode — per-column charts carry ranges ─────
        print(f"\n[Test 2] Split mode range rendering ({HISTO_DATE}, bin {BIN_SIZE}m)")
        tester.navigate(f"{BASE_URL}/?view=histogram&date={HISTO_DATE}&binSize={BIN_SIZE}&split=1")
        try:
            tester.wait_for_element(By.CSS_SELECTOR, ".split-histogram-item canvas", timeout=30)
        except Exception:
            pass
        tester.wait(2)
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "histogram-range-split.png"))

        canvas_ids = tester.execute_script(
            "return Array.from(document.querySelectorAll('.split-histogram-item canvas'))"
            ".map(c => c.id);")
        t.check(len(canvas_ids) >= 1, f"split canvases present (got {len(canvas_ids)})")

        checked = 0
        for cid in canvas_ids or []:
            datasets = chart_datasets(tester, cid)
            if not datasets:
                continue
            avg = datasets[0]
            api_ds = api_by_chart_label.get(avg["label"])
            if api_ds is None:
                continue
            has_range = len(datasets) > 1 and bool(datasets[1].get("isRange"))
            expected = has_spread(api_ds["min"], api_ds["max"])
            t.check(has_range == expected,
                    f"split '{avg['label']}': range dataset present={has_range}, expected {expected}")
            if has_range and expected:
                t.check(range_entries_ok(datasets[1]["data"], api_ds["min"], api_ds["max"]),
                        f"split '{avg['label']}': range data matches API min/max")
            checked += 1
        t.check(checked >= 1, f"at least one split chart cross-checked (got {checked})")

    return summary(t)


def summary(t: TestResult) -> int:
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
