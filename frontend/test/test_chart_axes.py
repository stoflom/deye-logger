#!/usr/bin/env python3
"""
Test script to verify full-range chart axes (frontend-design.md §15.8, #85, #88).

Covers:
  1. Series chart x-axis is a linear time axis spanning the whole selected
     range (single day: 00:00–24:00) at a 5-min tick step.
  2. Series chart x-axis in a 2-day range spans both days at a 30-min tick
     step. (Series data is raw per-point since v7.4/#88 — see
     test_series_raw_points.py.)
  3. Percentage-unit (SOC) y-axis fixed to 0–100 in the series chart.
  4. Histogram x-axis always shows the full 00:00–24:00 bin grid
     (15-min default → 96 labels).
  5. Percentage-unit (SOC) y-axis fixed to 0–100 in the histogram charts.

Requires the app server running on http://localhost:8090 (bash backend/start.sh).

Usage:
  python3 test_chart_axes.py

Screenshots are saved to frontend/test/screenshots/
"""

import sys
import os
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
TEST_DATE = "2026-07-27"  # Date with actual data
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


def take_screenshot(tester, filename, description=""):
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    tester.screenshot(filepath)
    print(f"  📷 {description}: {filepath}")


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


def series_chart_info(tester):
    """X-axis extent/step + y-axis configs of the Series chart."""
    return tester.execute_script("""
        const c = document.getElementById("chart-canvas");
        if (!c || !c.__chartInstance) return null;
        const ch = c.__chartInstance;
        const x = ch.options.scales.x;
        const scales = {};
        for (const [id, s] of Object.entries(ch.options.scales)) {
            if (id === "x") continue;
            scales[id] = {
                title: s.title && s.title.text ? s.title.text : null,
                min: "min" in s ? s.min : undefined,
                max: "max" in s ? s.max : undefined,
            };
        }
        return {
            xType: x.type || "category",
            xMin: "min" in x ? x.min : undefined,
            xMax: "max" in x ? x.max : undefined,
            xStepMs: x.ticks && "stepSize" in x.ticks ? x.ticks.stepSize : undefined,
            scales,
        };
    """)


def wait_for_histogram_charts(tester, timeout: int = 30):
    """Poll until every histogram canvas exposes a live Chart instance."""
    return tester.execute_script("""
        return new Promise((resolve) => {
            const t0 = Date.now();
            const poll = () => {
                const canvases = document.querySelectorAll(".histogram-chart-item canvas");
                if (canvases.length > 0 && [...canvases].every((c) => c.__chartInstance)) {
                    return resolve(true);
                }
                if (Date.now() - t0 > arguments[0]) return resolve(false);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, timeout * 1000)


def histogram_charts_info(tester):
    """Per-chart info: title, labels, y-axis configs."""
    return tester.execute_script("""
        const out = [];
        document.querySelectorAll(".histogram-chart-item canvas").forEach((c) => {
            const ch = c.__chartInstance;
            if (!ch) return;
            const scales = {};
            for (const [id, s] of Object.entries(ch.options.scales)) {
                if (id === "x") continue;
                scales[id] = {
                    title: s.title && s.title.text ? s.title.text : null,
                    min: "min" in s ? s.min : undefined,
                    max: "max" in s ? s.max : undefined,
                };
            }
            out.push({
                title: c.closest(".histogram-chart-item")
                    .querySelector(".histogram-chart-title").textContent,
                labels: ch.data.labels,
                scales,
            });
        });
        return out;
    """)


# ── Tests ───────────────────────────────────────────────────────────
def test_series_single_day_axis(tester, t: TestResult):
    """Series x-axis is linear, spans the full day 00:00–24:00, 5-min ticks."""
    print("\n[Test 1] Series x-axis: full-day linear time axis (single day)")
    tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': 'chart'})}")
    tester.wait_for_element(By.ID, "summary-cards")
    ok = wait_for_series_chart(tester)
    t.check(ok, "Series chart instance exposed on #chart-canvas")
    if not ok:
        take_screenshot(tester, "axes-series-missing.png", "Series chart not ready")
        return

    day0 = int(datetime(2026, 7, 27, 0, 0, 0).timestamp() * 1000)
    info = series_chart_info(tester)
    t.check(info["xType"] == "linear", f"x-axis type linear, got {info['xType']}")
    t.check(info["xMin"] == day0, f"x-axis starts 00:00 (got {info['xMin']}, want {day0})")
    t.check(info["xMax"] == day0 + 86_400_000,
            f"x-axis ends 24:00 (got {info['xMax']}, want {day0 + 86_400_000})")
    t.check(info["xStepMs"] == 5 * 60_000,
            f"x-axis tick step 5 min (got {info['xStepMs']})")
    take_screenshot(tester, "axes-series-single-day.png", "Series single-day full range")


def test_series_range_axis(tester, t: TestResult):
    """Series x-axis is linear, spans the full 2-day range, 30-min ticks."""
    print("\n[Test 2] Series x-axis: full 2-day linear time axis (30-min ticks)")
    tester.navigate(f"{BASE_URL}/?{urlencode({'from': '2026-07-27', 'to': '2026-07-28', 'view': 'chart'})}")
    tester.wait_for_element(By.ID, "summary-cards")
    ok = wait_for_series_chart(tester)
    t.check(ok, "Series chart instance exposed on #chart-canvas")
    if not ok:
        return

    day0 = int(datetime(2026, 7, 27, 0, 0, 0).timestamp() * 1000)
    info = series_chart_info(tester)
    t.check(info["xType"] == "linear", f"x-axis type linear, got {info['xType']}")
    t.check(info["xMin"] == day0, f"x-axis starts 07-27 00:00 (got {info['xMin']}, want {day0})")
    t.check(info["xMax"] == day0 + 2 * 86_400_000,
            f"x-axis ends 07-29 00:00 (got {info['xMax']}, want {day0 + 2 * 86_400_000})")
    t.check(info["xStepMs"] == 30 * 60_000,
            f"x-axis tick step 30 min (got {info['xStepMs']})")


def test_series_soc_axis(tester, t: TestResult):
    """Series y-axis for % (SOC) is fixed to 0–100."""
    print("\n[Test 3] Series y-axis: SOC fixed 0–100")
    tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': 'chart'})}")
    tester.wait_for_element(By.ID, "summary-cards")
    ok = wait_for_series_chart(tester)
    t.check(ok, "Series chart instance exposed on #chart-canvas")
    if not ok:
        return

    info = series_chart_info(tester)
    pct = {aid: s for aid, s in info["scales"].items() if s["title"] == "%"}
    t.check(len(pct) >= 1, f"Found % axis in series chart (got {len(pct)})")
    for aid, s in pct.items():
        t.check(s["min"] == 0 and s["max"] == 100,
                f"Axis {aid} fixed 0–100 (got {s['min']}–{s['max']})")
    take_screenshot(tester, "axes-series-soc.png", "Series SOC axis 0–100")


def test_histogram_axes(tester, t: TestResult):
    """Histogram x-axis full-day bin grid + SOC y-axis 0–100."""
    print("\n[Test 4] Histogram: full-day bin grid + SOC axis 0–100")
    tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': 'histogram'})}")
    tester.wait_for_element(By.ID, "summary-cards")
    ok = wait_for_histogram_charts(tester)
    t.check(ok, "All histogram chart instances exposed")
    if not ok:
        take_screenshot(tester, "axes-histogram-missing.png", "Histogram charts not ready")
        return

    charts = histogram_charts_info(tester)
    t.check(len(charts) > 0, f"At least one histogram chart (got {len(charts)})")

    soc_chart = next((c for c in charts if c["title"] and "SOC" in c["title"]), None)
    t.check(soc_chart is not None, "SOC histogram chart found (default columns)")

    for c in charts:
        labels = c["labels"]
        t.check(len(labels) == 96,
                f"{c['title']}: 96 bins (15-min grid), got {len(labels)}")
        t.check(labels[0] == "00:00" and labels[-1] == "23:45",
                f"{c['title']}: bins span 00:00–23:45 (got {labels[0]}–{labels[-1]})")

    if soc_chart:
        pct = {aid: s for aid, s in soc_chart["scales"].items() if s["title"] == "%"}
        t.check(len(pct) == 1, f"SOC chart has exactly one % axis (got {len(pct)})")
        for aid, s in pct.items():
            t.check(s["min"] == 0 and s["max"] == 100,
                    f"SOC axis {aid} fixed 0–100 (got {s['min']}–{s['max']})")
    take_screenshot(tester, "axes-histogram.png", "Histogram full-day grid + SOC axis")


# ── Main ────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Deye Logger Viewer - Chart Axes Tests (#85)")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print("\n[Setup] Starting Firefox (headless mode)...")

    t = TestResult()
    with FirefoxTester(headless=True) as tester:
        tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE})}")
        print(f"[Setup] Page title: {tester.get_title()}")

        try:
            test_series_single_day_axis(tester, t)
            test_series_range_axis(tester, t)
            test_series_soc_axis(tester, t)
            test_histogram_axes(tester, t)
        finally:
            print("\n" + "=" * 70)
            print(f"Results: {t.passed}/{t.passed + t.failed} passed, {t.failed} failed")
            if t.failed > 0:
                print("\nFailed tests:")
                for f in t.failures:
                    print(f"  - {f}")
            print("=" * 70)
            sys.exit(1 if t.failed > 0 else 0)


if __name__ == "__main__":
    main()
