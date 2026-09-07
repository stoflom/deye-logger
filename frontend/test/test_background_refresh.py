#!/usr/bin/env python3
"""
Test the background database refresh behaviour (frontend v8.0, design §10.3, #89).

Requirements under test:
  1. Clicking ↻ Refresh starts the database update in the BACKGROUND —
     the current view stays visible and all controls stay usable
     (only the Refresh button itself is disabled).
  2. While the update is running, "refreshing ..." is shown in the STATUS BAR
     (#refresh-status); the waiting view (spinner) is NOT used for refresh.
  3. When the update completes, the indicator is cleared, the Refresh button
     is re-enabled, and the current view is re-rendered.

The Deye Cloud sync must be mocked (no .env in the dev environment): the server
has to be started with the mock ingestion script, e.g.

  DEYE_LOGGER_SCRIPT="$(pwd)/frontend/test/mock_deye_logger.py" bash backend/start.sh

The mock sleeps ~3 s (MOCK_REFRESH_SLEEP), giving the tests a comfortable
window to assert the in-flight state.

Usage:
  python3 test_background_refresh.py

Screenshots are saved to frontend/test/screenshots/
"""

import os
import sys
import time
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
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

REFRESH_SLEEP = float(os.environ.get("MOCK_REFRESH_SLEEP", "3"))
REFRESH_TIMEOUT = 60  # max seconds to wait for the background refresh to finish


# ── Helper Functions ────────────────────────────────────────────────

def open_view(tester, view_mode):
    """Navigate to a view mode and wait until it has fully rendered."""
    url = f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': view_mode})}"
    tester.navigate(url)
    # The view is rendered once the waiting view is hidden and the panel shown
    for _ in range(100):
        if not tester.find_element(By.ID, "waiting-view").is_displayed():
            break
        time.sleep(0.1)
    time.sleep(0.3)


def panel_visible(tester, element_id):
    el = tester.find_element(By.ID, element_id)
    return el is not None and el.is_displayed()


def element_enabled(tester, element_id):
    el = tester.find_element(By.ID, element_id)
    if el is None:
        return False
    return el.get_attribute("disabled") in (None, "false")


def refresh_status_visible(tester):
    el = tester.find_element(By.ID, "refresh-status")
    return el is not None and el.is_displayed()


def wait_for(tester, predicate, timeout=REFRESH_TIMEOUT, interval=0.2):
    """Poll until predicate() is True or timeout; returns True if met."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def check(name, condition, detail=""):
    if condition:
        print(f"  ✅ {name}")
        return True
    print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
    return False


def test_backend_mock(tester, failures):
    """Sanity: the server serves the new backend version (mock-capable)."""
    print("\n── Test 1: Backend serves v4.4.0 (DEYE_LOGGER_SCRIPT-capable)")
    badge = tester.find_element(By.ID, "version-badge")
    # The badge is filled by an async /api/version fetch — wait it out
    text = ""
    for _ in range(50):
        text = badge.text.strip() if badge is not None else ""
        if "BE ?" not in text and text:
            break
        time.sleep(0.1)
    ok = check(
        "Version badge shows BE 4.4.0",
        "BE 4.4.0" in text,
        f"badge text: '{text}' — was the server started with the v4.4 backend?",
    )
    if not ok:
        failures.append("test_backend_mock")


def test_background_refresh(view_mode, panel_id, tester, failures):
    """Core test: refresh runs in the background while the view stays active."""
    print(f"\n── Test: Background refresh in '{view_mode}' view")
    open_view(tester, view_mode)

    # Precondition: view is rendered, no refresh in flight
    if not check(f"'{view_mode}' view is rendered before refresh",
                 panel_visible(tester, panel_id)):
        failures.append(f"test_background_refresh:{view_mode}-pre")
        return
    if not check("No 'refreshing ...' indicator before refresh",
                 not refresh_status_visible(tester)):
        failures.append(f"test_background_refresh:{view_mode}-pre")
        return
    tester.screenshot(os.path.join(SCREENSHOT_DIR, f"bgrefresh_{view_mode}_before.png"))

    # Trigger the refresh
    tester.find_element(By.ID, "refresh-btn").click()
    time.sleep(0.3)  # let the click handler start the background operation

    # In-flight state: view stays visible, indicator shown, controls usable
    if not check("'refreshing ...' shown in the status bar",
                 refresh_status_visible(tester) and
                 "refreshing" in tester.find_element(By.ID, "refresh-status").text.lower()):
        failures.append(f"test_background_refresh:{view_mode}-indicator")
    if not check(f"the '{view_mode}' view stays visible during the refresh",
                 panel_visible(tester, panel_id)):
        failures.append(f"test_background_refresh:{view_mode}-panel")
    if not check("the waiting view (spinner) is NOT used for the refresh",
                 not panel_visible(tester, "waiting-view")):
        failures.append(f"test_background_refresh:{view_mode}-waiting")
    if not check("the Refresh button is disabled during the refresh",
                 not element_enabled(tester, "refresh-btn")):
        failures.append(f"test_background_refresh:{view_mode}-refresh-btn")
    other_controls_ok = True
    for cid in ("today-btn", "date-from", "columns-toggle", "view-toggle"):
        if not element_enabled(tester, cid):
            other_controls_ok = False
            print(f"     ↳ control '{cid}' is disabled during the refresh")
    if not check("other controls (Today, date, Select, Grid) stay enabled",
                 other_controls_ok):
        failures.append(f"test_background_refresh:{view_mode}-controls")
    tester.screenshot(os.path.join(SCREENSHOT_DIR, f"bgrefresh_{view_mode}_during.png"))

    # Wait for the refresh to complete (mock sleeps ~REFRESH_SLEEP seconds)
    done = wait_for(tester,
                    lambda: not refresh_status_visible(tester)
                    and element_enabled(tester, "refresh-btn"))
    if not check("refresh completes — indicator cleared, Refresh re-enabled", done,
                 f"still in flight after {REFRESH_TIMEOUT}s"):
        failures.append(f"test_background_refresh:{view_mode}-complete")
        return

    # Post-condition: the current view was re-rendered
    rendered = wait_for(tester,
                        lambda: not panel_visible(tester, "waiting-view")
                        and panel_visible(tester, panel_id),
                        timeout=15)
    if not check(f"the '{view_mode}' view is re-rendered after the refresh",
                 rendered):
        failures.append(f"test_background_refresh:{view_mode}-rerender")
        return
    row_count = tester.find_element(By.ID, "row-count").text.strip()
    if not check("row count is populated after the re-render",
                 len(row_count) > 0, f"row-count text: '{row_count}'"):
        failures.append(f"test_background_refresh:{view_mode}-rowcount")
    tester.screenshot(os.path.join(SCREENSHOT_DIR, f"bgrefresh_{view_mode}_after.png"))


def main():
    failures = []
    print("🔄 Background database refresh test (#89, design §10.3)")
    print(f"   BASE_URL: {BASE_URL}  (mock sleep: {REFRESH_SLEEP}s)")

    with FirefoxTester(headless=True, window_size=(1400, 900)) as tester:
        tester.navigate(f"{BASE_URL}/?{urlencode({'date': TEST_DATE, 'view': 'chart'})}")
        tester.wait_for_element(By.ID, "refresh-status")  # always in the DOM (hidden unless refreshing)

        test_backend_mock(tester, failures)
        test_background_refresh("chart", "raw-data-chart-view", tester, failures)
        test_background_refresh("histogram", "histogram-view", tester, failures)

    print("\n" + "═" * 50)
    if failures:
        print(f"❌ FAILED: {len(failures)} failure(s): {failures}")
        sys.exit(1)
    print("✅ ALL TESTS PASSED")


if __name__ == "__main__":
    main()
