#!/usr/bin/env python3
"""
Test script to verify all-zero columns are still carded and plotted
(frontend-design.md v8.1 §15.2, backend-design.md v4.4, #90).

A selected column whose samples are all 0 is a valid numeric column:
  1. Chart view: it gets a summary card ("Max 0 …") AND a plotted series
     with one point per raw row, all at y=0 — on a y-axis that does not
     collapse (Chart.js must render a usable range for constant data).
  2. Histogram view: the backend includes it in /api/histogram (dataset
     values 0, maxValues entry 0) and the UI shows its bar chart and
     "Max Average 0 …" summary card.
  3. Stats view: a stat card shows Average/Max/Min 0 and 0 mins/day
     (already worked — regression guard).
  4. Non-zero columns are unaffected in every view.

Fixture: `daily_grid_feed_in` is entirely 0 on TEST_DATE in the real
database — no synthetic data needed. The column selection is injected via
localStorage (`deye_selected_columns`) before navigation.

Requires the app server running on http://localhost:8090 (bash backend/start.sh).

Usage:
  python3 test_all_zero_columns.py

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
TEST_DATE = "2026-07-27"          # Date with actual data
ZERO_COL = "daily_grid_feed_in"   # All-zero column on TEST_DATE (kWh)
ZERO_LABEL = "Daily Grid Feed In"
NORMAL_COL = "current_power"      # Non-zero column (W) — control
NORMAL_LABEL = "Inverter Output Power L1L2"
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


# ── API ground truth ────────────────────────────────────────────────
def api_get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as res:
        return json.loads(res.read().decode())


def raw_stats():
    """Per-column (count, max) from /api/data for the test date."""
    cols = f"{ZERO_COL},{NORMAL_COL},device_timestamp"
    payload = api_get(f"/api/data?date={TEST_DATE}&columns={quote(cols, safe='')}")
    rows = payload["rows"]
    stats = {}
    for col in (ZERO_COL, NORMAL_COL):
        vals = [r[col] for r in rows if isinstance(r.get(col), (int, float))]
        stats[col] = {"count": len(vals), "max": max(vals) if vals else None}
    return rows, stats


def check_fixture(t: TestResult):
    """The fixture column must actually be all-zero on the test date."""
    rows, stats = raw_stats()
    vals = [r[ZERO_COL] for r in rows if isinstance(r.get(ZERO_COL), (int, float))]
    t.check(len(vals) > 0, f"fixture: {ZERO_COL} has numeric samples ({len(vals)})")
    t.check(all(v == 0 for v in vals), f"fixture: {ZERO_COL} is entirely 0 on {TEST_DATE}")
    t.check((stats[NORMAL_COL]["max"] or 0) > 0,
            f"fixture: {NORMAL_COL} has non-zero data (max {stats[NORMAL_COL]['max']})")
    return rows, stats


# ── Column selection via localStorage ───────────────────────────────
def select_columns(tester, columns):
    """Persist the column selection, then (re)load the app."""
    tester.navigate(f"{BASE_URL}/")
    tester.execute_script(
        "localStorage.setItem('deye_selected_columns', JSON.stringify(arguments[0]));",
        columns,
    )


def open_view(tester, view: str):
    tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': view})}")


def wait_for_series_and_card(tester, label: str, timeout: int = 30):
    """Poll until the chart instance AND a summary card with the label exist.

    `#summary-cards` (the container) is always present in the DOM, so waiting
    on it alone races with card rendering — wait for the card content.
    """
    return tester.execute_script("""
        return new Promise((resolve) => {
            const t0 = Date.now();
            const poll = () => {
                const c = document.getElementById("chart-canvas");
                const card = Array.from(document.querySelectorAll("#summary-cards .summary-card .label"))
                    .some((el) => el.textContent && el.textContent.includes(arguments[1]));
                if (c && c.__chartInstance && card) return resolve(true);
                if (Date.now() - t0 > arguments[0]) return resolve(false);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, timeout * 1000, label)


# ── Chart (series) helpers ──────────────────────────────────────────
def wait_for_series_chart(tester, timeout: int = 30):
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
    return tester.execute_script("""
        const c = document.getElementById("chart-canvas");
        if (!c || !c.__chartInstance) return null;
        const ch = c.__chartInstance;
        return ch.data.datasets.map((ds) => {
            const pts = ds.data;
            const ys = pts.map((p) => p.y);
            return {
                label: ds.label,
                yAxisId: ds.yAxisID,
                count: pts.length,
                allZero: ys.length > 0 && ys.every((y) => y === 0),
                yMin: ys.length ? Math.min(...ys) : null,
                yMax: ys.length ? Math.max(...ys) : null,
            };
        });
    """)


def scale_range(tester, axis_id: str):
    return tester.execute_script("""
        const c = document.getElementById("chart-canvas");
        if (!c || !c.__chartInstance) return null;
        const s = c.__chartInstance.scales[arguments[0]];
        return s ? { min: s.min, max: s.max } : null;
    """, axis_id)


def summary_cards():
    return """
        return Array.from(document.querySelectorAll("#summary-cards .summary-card"))
            .map((el) => ({
                label: el.querySelector(".label") ? el.querySelector(".label").textContent : "",
                value: el.querySelector(".value") ? el.querySelector(".value").textContent : "",
            }))
    """


# ── Tests ───────────────────────────────────────────────────────────
def test_chart_view(tester, t: TestResult, rows, stats):
    print("\n[Test 1] Chart view: all-zero column carded + plotted")
    select_columns(tester, [ZERO_COL, NORMAL_COL, "device_timestamp"])
    open_view(tester, "chart")
    ok = wait_for_series_and_card(tester, ZERO_LABEL)
    t.check(ok, "series chart + all-zero summary card rendered")
    if not ok:
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "zero-col-chart-missing.png"))
        return

    # Summary card: "Max Daily Grid Feed In" with value "0 kWh"
    cards = tester.execute_script(summary_cards())
    zero_card = next((c for c in cards if ZERO_LABEL in c["label"]), None)
    t.check(zero_card is not None, f"summary card for '{ZERO_LABEL}' present")
    if zero_card:
        t.check(zero_card["value"].startswith("0"),
                f"all-zero card shows 0 (got '{zero_card['value']}')")
    normal_card = next((c for c in cards if NORMAL_LABEL in c["label"]), None)
    t.check(normal_card is not None and not normal_card["value"].startswith("0"),
            f"non-zero column card unaffected (got "
            f"{normal_card['value'] if normal_card else 'MISSING'})")

    # Plotted series: one point per raw row, all at y=0
    ds_list = series_datasets_info(tester)
    zero_ds = next((d for d in ds_list if ZERO_LABEL in d["label"]), None)
    t.check(zero_ds is not None, f"plotted dataset for '{ZERO_LABEL}' present")
    if zero_ds:
        t.check(zero_ds["count"] == stats[ZERO_COL]["count"],
                f"all-zero series has one point per raw row "
                f"({zero_ds['count']} vs {stats[ZERO_COL]['count']})")
        t.check(zero_ds["allZero"] and zero_ds["yMin"] == 0 and zero_ds["yMax"] == 0,
                "all-zero series sits at y=0")
        # The y-axis must not collapse to a zero-width range (Chart.js
        # widens constant scales) — otherwise the line would be invisible.
        rng = scale_range(tester, zero_ds["yAxisId"])
        t.check(rng is not None and rng["max"] > rng["min"],
                f"y-axis for all-zero column not collapsed (got {rng})")
    normal_ds = next((d for d in ds_list if NORMAL_LABEL in d["label"]), None)
    t.check(normal_ds is not None and normal_ds["yMax"] > 0,
            f"non-zero series unaffected (max "
            f"{normal_ds['yMax'] if normal_ds else 'MISSING'})")

    tester.screenshot(os.path.join(SCREENSHOT_DIR, "zero-col-chart.png"))


def test_histogram_view(tester, t: TestResult):
    print("\n[Test 2] Histogram view: all-zero column binned + carded")
    select_columns(tester, [ZERO_COL, NORMAL_COL, "device_timestamp"])

    # API ground truth (backend-design v4.4: all-zero columns are included)
    cols = f"{ZERO_COL},{NORMAL_COL}"
    hist = api_get(
        f"/api/histogram?from={TEST_DATE}&to={TEST_DATE}"
        f"&columns={quote(cols, safe='')}&binMinutes=15&dayFilter=all"
    )
    zero_ds = next((d for d in hist["datasets"] if d["label"] == ZERO_LABEL), None)
    t.check(zero_ds is not None, "/api/histogram includes the all-zero dataset")
    if zero_ds:
        vals = [v for v in zero_ds["data"] if v is not None]
        t.check(len(vals) > 0 and all(v == 0 for v in vals),
                "all-zero histogram bins are 0")
    mv = hist["maxValues"].get(ZERO_LABEL)
    t.check(mv is not None and mv["value"] == 0,
            f"/api/histogram maxValues for '{ZERO_LABEL}' is 0 (got {mv})")
    normal_mv = hist["maxValues"].get(NORMAL_LABEL)
    t.check(normal_mv is not None and normal_mv["value"] > 0,
            "non-zero column maxValues unaffected")

    open_view(tester, "histogram")
    # Wait for the per-column histogram canvases
    ok = tester.execute_script("""
        return new Promise((resolve) => {
            const t0 = Date.now();
            const poll = () => {
                const c = document.querySelector(".histogram-chart-item canvas");
                const card = Array.from(document.querySelectorAll("#summary-cards .summary-card .label"))
                    .some((el) => el.textContent && el.textContent.includes(arguments[1]));
                if (c && c.__chartInstance && card) return resolve(true);
                if (Date.now() - t0 > arguments[0]) return resolve(false);
                setTimeout(poll, 250);
            };
            poll();
        });
    """, 30 * 1000, ZERO_LABEL)
    t.check(ok, "histogram charts + all-zero summary card rendered")
    if not ok:
        tester.screenshot(os.path.join(SCREENSHOT_DIR, "zero-col-hist-missing.png"))
        return

    titles = tester.execute_script(
        "return Array.from(document.querySelectorAll('.histogram-chart-title'))"
        ".map((el) => el.textContent);")
    t.check(any(ZERO_LABEL in (s or "") for s in (titles or [])),
            f"histogram chart for '{ZERO_LABEL}' rendered")

    cards = tester.execute_script(summary_cards())
    zero_card = next((c for c in cards if ZERO_LABEL in c["label"]), None)
    t.check(zero_card is not None and zero_card["value"].startswith("0"),
            f"'Max Average {ZERO_LABEL}' card shows 0 (got "
            f"{zero_card['value'] if zero_card else 'MISSING'})")

    tester.screenshot(os.path.join(SCREENSHOT_DIR, "zero-col-hist.png"))


def test_stats_view(tester, t: TestResult):
    print("\n[Test 3] Stats view: all-zero stat card (regression guard)")
    select_columns(tester, [ZERO_COL, NORMAL_COL, "device_timestamp"])
    open_view(tester, "stats")
    tester.wait_for_element(By.CSS_SELECTOR, ".stat-card", timeout=30)

    card_info = tester.execute_script("""
        const cards = Array.from(document.querySelectorAll('.stat-card'));
        return cards.map((c) => {
            const header = c.querySelector('.stat-card-header');
            const mains = Array.from(c.querySelectorAll('.stat-row-main'))
                .map((el) => el.textContent);
            return { header: header ? header.textContent : "", mains };
        });
    """)

    zero = next((c for c in card_info if c["header"] == ZERO_LABEL), None)
    t.check(zero is not None, f"stat card for '{ZERO_LABEL}' present")
    if zero:
        mains = " | ".join(zero["mains"])
        t.check(any(m.startswith("Average 0 ") for m in zero["mains"]),
                f"average is 0 ({mains})")
        t.check(any(m.startswith("Max 0 ") for m in zero["mains"]),
                f"max is 0 ({mains})")
        t.check(any(m.startswith("Min 0 ") for m in zero["mains"]),
                f"min is 0 ({mains})")
        t.check(any(m.startswith("High 0 mins/day") for m in zero["mains"]),
                f"high duration is 0 ({mains})")
        t.check(any(m.startswith("Low 0 mins/day") for m in zero["mains"]),
                f"low duration is 0 ({mains})")
    normal = next((c for c in card_info if NORMAL_LABEL in c["header"]), None)
    t.check(normal is not None and any("Max " in m for m in normal["mains"]),
            f"stat card for '{NORMAL_LABEL}' unaffected")

    tester.screenshot(os.path.join(SCREENSHOT_DIR, "zero-col-stats.png"))


# ── Main ────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Deye Logger Viewer - All-Zero Column Tests (#90)")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print("\n[Setup] Checking fixture data via API...")
    t = TestResult()
    rows, stats = check_fixture(t)
    if t.failed > 0:
        print("\nFixture invalid — aborting (no server data on this date?).")
        sys.exit(1)

    print("\n[Setup] Starting Firefox (headless mode)...")
    uncaught = None
    with FirefoxTester(headless=True) as tester:
        try:
            test_chart_view(tester, t, rows, stats)
            test_histogram_view(tester, t)
            test_stats_view(tester, t)
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
