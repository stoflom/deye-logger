#!/usr/bin/env python3
"""
Test script to verify button states in major frontend views.

Covers the following views as per frontend-design.md §9.3:
  - chart
  - grid
  - histogram
  - histogram-grid
  - columns select (transient)
  - error

For each view, verifies:
  - Button visibility (display style)
  - Button enabled/disabled state
  - Button text labels
  - Histogram controls visibility (bin-size, day-filter, split)
  - CSV export visibility

Usage:
  python3 test_button_states.py

Screenshots are saved to frontend/test/screenshots/
"""

import sys
import os
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

# Button/control element IDs
BUTTON_IDS = {
    "prevDay": "prev-day",
    "nextDay": "next-day",
    "today": "today-btn",
    "refresh": "refresh-btn",
    "columnsToggle": "columns-toggle",
    "viewToggle": "view-toggle",
    "histogramToggle": "histogram-btn",
    "exportCsv": "export-btn",
    "split": "split-btn",
}
SELECT_IDS = {
    "binSize": "bin-size-select",
    "dayFilter": "day-filter-select",
}

# ── Expected button states per view ─────────────────────────────────
# Format: { control_name: { "enabled": bool, "visible": bool, "text": str (optional) } }
# "visible" refers to display != "none" (for elements that toggle visibility)
# "enabled" refers to the disabled attribute

EXPECTED_STATES = {
    "chart": {
        # Always-visible controls — enabled
        "prevDay": {"enabled": True, "visible": True},
        "nextDay": {"enabled": True, "visible": True},
        "today": {"enabled": True, "visible": True},
        "refresh": {"enabled": True, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "☰ Select"},
        # View toggle: shows "📋 Data Grid" when in chart
        "viewToggle": {"enabled": True, "visible": True, "text": "📋 Data Grid"},
        # Histogram toggle: shows "📊 Histogram" when in chart
        "histogramToggle": {"enabled": True, "visible": True, "text": "📊 Histogram"},
        # Export: hidden in non-grid views
        "exportCsv": {"enabled": True, "visible": False},
        # Split: hidden in non-histogram views
        "split": {"enabled": True, "visible": False},
        # Histogram controls: hidden in non-histogram modes
        "binSize": {"enabled": True, "visible": False},
        "dayFilter": {"enabled": True, "visible": False},
    },
    "grid": {
        "prevDay": {"enabled": True, "visible": True},
        "nextDay": {"enabled": True, "visible": True},
        "today": {"enabled": True, "visible": True},
        "refresh": {"enabled": True, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "☰ Select"},
        # View toggle: shows "📈 Chart" when in grid
        "viewToggle": {"enabled": True, "visible": True, "text": "📈 Chart"},
        # Histogram toggle: shows "📊 Histogram Grid" when in grid
        "histogramToggle": {"enabled": True, "visible": True, "text": "📊 Histogram Grid"},
        # Export: visible in grid views
        "exportCsv": {"enabled": True, "visible": True},
        "split": {"enabled": True, "visible": False},
        "binSize": {"enabled": True, "visible": False},
        "dayFilter": {"enabled": True, "visible": False},
    },
    "histogram": {
        "prevDay": {"enabled": True, "visible": True},
        "nextDay": {"enabled": True, "visible": True},
        "today": {"enabled": True, "visible": True},
        "refresh": {"enabled": True, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "☰ Select"},
        # View toggle: shows "📊 Histogram Grid" when in histogram
        "viewToggle": {"enabled": True, "visible": True, "text": "📊 Histogram Grid"},
        # Histogram toggle: shows "📋 Raw Chart" when in histogram
        "histogramToggle": {"enabled": True, "visible": True, "text": "📋 Raw Chart"},
        # Export: hidden in histogram views
        "exportCsv": {"enabled": True, "visible": False},
        # Split: visible only in histogram (not histogram-grid)
        "split": {"enabled": True, "visible": True, "text": "Split"},
        # Histogram controls: visible in histogram modes
        "binSize": {"enabled": True, "visible": True},
        "dayFilter": {"enabled": True, "visible": True},
    },
    "histogram-grid": {
        "prevDay": {"enabled": True, "visible": True},
        "nextDay": {"enabled": True, "visible": True},
        "today": {"enabled": True, "visible": True},
        "refresh": {"enabled": True, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "☰ Select"},
        # View toggle: shows "📈 Histogram Chart" when in histogram-grid
        "viewToggle": {"enabled": True, "visible": True, "text": "📈 Histogram Chart"},
        # Histogram toggle: shows "📋 Raw Grid" when in histogram-grid
        "histogramToggle": {"enabled": True, "visible": True, "text": "📋 Raw Grid"},
        # Export: visible in grid views (histogram-grid is a grid)
        "exportCsv": {"enabled": True, "visible": True},
        # Split: hidden in histogram-grid
        "split": {"enabled": True, "visible": False},
        # Histogram controls: visible in histogram modes
        "binSize": {"enabled": True, "visible": True},
        "dayFilter": {"enabled": True, "visible": True},
    },
    "columns": {
        # Only columnsToggle is enabled; all others are disabled.
        # Visibility is inherited from the underlying view (chart here) —
        # the columns panel is a transient overlay, not a view change.
        "prevDay": {"enabled": False, "visible": True},
        "nextDay": {"enabled": False, "visible": True},
        "today": {"enabled": False, "visible": True},
        "refresh": {"enabled": False, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "↻ Load Data"},
        "viewToggle": {"enabled": False, "visible": True},
        "histogramToggle": {"enabled": False, "visible": True},
        "exportCsv": {"enabled": False, "visible": False},  # hidden (inherited from chart)
        "split": {"enabled": False, "visible": False},  # hidden (inherited from chart)
        "binSize": {"enabled": False, "visible": False},  # hidden inside histogram-controls (display:none)
        "dayFilter": {"enabled": False, "visible": False},  # hidden inside histogram-controls (display:none)
    },
    "error": {
        # All controls disabled; error close button is the only enabled element.
        # Visibility inherited from underlying view (chart) — error overlay doesn't change it.
        "prevDay": {"enabled": False, "visible": True},
        "nextDay": {"enabled": False, "visible": True},
        "today": {"enabled": False, "visible": True},
        "refresh": {"enabled": False, "visible": True},
        "columnsToggle": {"enabled": False, "visible": True},
        "viewToggle": {"enabled": False, "visible": True},
        "histogramToggle": {"enabled": False, "visible": True},
        "exportCsv": {"enabled": False, "visible": False},  # hidden (inherited from chart)
        "split": {"enabled": False, "visible": False},  # hidden (inherited from chart)
        "binSize": {"enabled": False, "visible": False},  # hidden inside histogram-controls
        "dayFilter": {"enabled": False, "visible": False},  # hidden inside histogram-controls
    },
}

# ── Helper Functions ────────────────────────────────────────────────

def take_screenshot(tester, filename, description=""):
    """Take screenshot and save to SCREENSHOT_DIR."""
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    tester.screenshot(filepath)
    print(f"  📷 {description}: {filepath}")


def navigate_to_view(tester, view_mode):
    """Navigate to a specific view mode via URL."""
    params = {"date": TEST_DATE, "view": view_mode}
    url = f"{BASE_URL}/?{urlencode(params)}"
    tester.navigate(url)
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)


def get_element_by_id(tester, element_id):
    """Get a DOM element by ID."""
    return tester.find_element(By.ID, element_id)


def is_element_visible(tester, element_id):
    """Check if an element is visible, accounting for ancestor visibility.

    Uses WebElement.is_displayed() which properly handles:
    - element's own display/visibility
    - ancestor display:none (e.g. histogram-controls parent)
    - zero-dimension elements
    """
    el = tester.find_element(By.ID, element_id)
    if el is None:
        return False
    return el.is_displayed()


def is_element_disabled(tester, element_id):
    """Check if an element has the disabled attribute."""
    el = tester.find_element(By.ID, element_id)
    if el is None:
        return True
    disabled = el.get_attribute("disabled")
    return disabled is not None and disabled != "false"


def get_button_text(tester, element_id):
    """Get the text content of a button."""
    el = tester.find_element(By.ID, element_id)
    if el is None:
        return None
    return el.text.strip()


def get_histogram_controls_visible(tester):
    """Check if the histogram-controls container is visible."""
    histogram_controls = tester.find_element(By.ID, "histogram-controls")
    if histogram_controls is None:
        return False
    display = tester.get_computed_style(By.CSS_SELECTOR, "#histogram-controls", "display")
    return display != "none"


def check_control(tester, control_name, expected, view_name):
    """Check a single control's state against expected values."""
    failures = []
    element_id = BUTTON_IDS.get(control_name) or SELECT_IDS.get(control_name)
    if not element_id:
        return [f"Unknown control: {control_name}"]

    # Check visibility
    actual_visible = is_element_visible(tester, element_id)
    if expected.get("visible") is not None:
        if actual_visible != expected["visible"]:
            failures.append(
                f"  {control_name} visibility: expected {expected['visible']}, got {actual_visible} "
                f"(display={tester.get_computed_style(By.ID, element_id, 'display')})"
            )

    # Check enabled/disabled
    actual_disabled = is_element_disabled(tester, element_id)
    expected_enabled = expected.get("enabled")
    if expected_enabled is not None:
        if actual_disabled != (not expected_enabled):
            failures.append(
                f"  {control_name} enabled: expected {expected_enabled}, got {not actual_disabled}"
            )

    # Check button text (if specified)
    expected_text = expected.get("text")
    if expected_text is not None:
        actual_text = get_button_text(tester, element_id)
        if actual_text != expected_text:
            failures.append(
                f"  {control_name} text: expected '{expected_text}', got '{actual_text}'"
            )

    return failures


# ── Test Functions ──────────────────────────────────────────────────

def test_chart_view_button_states(tester):
    """Test button states in chart view."""
    print("\n[Test 1] Chart view button states")
    navigate_to_view(tester, "chart")

    failures = []
    for control, expected in EXPECTED_STATES["chart"].items():
        failures.extend(check_control(tester, control, expected, "chart"))

    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-chart-fail.png", "Chart view button failures")
        raise AssertionError(f"Chart view: {len(failures)} button state failures")

    take_screenshot(tester, "buttons-chart.png", "Chart view buttons")
    print("  ✓ All button states correct for chart view")


def test_grid_view_button_states(tester):
    """Test button states in grid view."""
    print("\n[Test 2] Grid view button states")
    navigate_to_view(tester, "grid")

    failures = []
    for control, expected in EXPECTED_STATES["grid"].items():
        failures.extend(check_control(tester, control, expected, "grid"))

    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-grid-fail.png", "Grid view button failures")
        raise AssertionError(f"Grid view: {len(failures)} button state failures")

    take_screenshot(tester, "buttons-grid.png", "Grid view buttons")
    print("  ✓ All button states correct for grid view")


def test_histogram_view_button_states(tester):
    """Test button states in histogram view."""
    print("\n[Test 3] Histogram view button states")
    navigate_to_view(tester, "histogram")

    failures = []
    for control, expected in EXPECTED_STATES["histogram"].items():
        failures.extend(check_control(tester, control, expected, "histogram"))

    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-histogram-fail.png", "Histogram view button failures")
        raise AssertionError(f"Histogram view: {len(failures)} button state failures")

    # Additional check: histogram-controls container visibility
    hc_visible = get_histogram_controls_visible(tester)
    if not hc_visible:
        print("  ✗ histogram-controls container should be visible in histogram mode")
        raise AssertionError("histogram-controls not visible")
    print("  ✓ histogram-controls container is visible")

    take_screenshot(tester, "buttons-histogram.png", "Histogram view buttons")
    print("  ✓ All button states correct for histogram view")


def test_histogram_grid_view_button_states(tester):
    """Test button states in histogram-grid view."""
    print("\n[Test 4] Histogram-grid view button states")
    navigate_to_view(tester, "histogram-grid")

    failures = []
    for control, expected in EXPECTED_STATES["histogram-grid"].items():
        failures.extend(check_control(tester, control, expected, "histogram-grid"))

    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-histogram-grid-fail.png",
                       "Histogram-grid view button failures")
        raise AssertionError(f"Histogram-grid view: {len(failures)} button state failures")

    # Split button should be hidden in histogram-grid
    split_visible = is_element_visible(tester, "split-btn")
    if split_visible:
        print("  ✗ split-btn should be hidden in histogram-grid view")
        raise AssertionError("split-btn visible in histogram-grid")
    print("  ✓ split-btn correctly hidden in histogram-grid")

    take_screenshot(tester, "buttons-histogram-grid.png", "Histogram-grid view buttons")
    print("  ✓ All button states correct for histogram-grid view")


def test_columns_select_button_states(tester):
    """Test button states when columns selection panel is open.

    Per design §6.2 STEP 4a: only columnsToggle ('↻ Load Data') is enabled.
    All other controls are disabled.
    """
    print("\n[Test 5] Columns select button states")

    # First navigate to chart view
    navigate_to_view(tester, "chart")

    # Click the columns toggle button to open the columns panel
    columns_btn = tester.find_element(By.ID, "columns-toggle")
    columns_btn.click()

    # Wait for columns view to render
    tester.wait_for_element(By.ID, "columns-view")
    time.sleep(0.5)

    failures = []
    for control, expected in EXPECTED_STATES["columns"].items():
        failures.extend(check_control(tester, control, expected, "columns"))

    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-columns-fail.png", "Columns select button failures")
        raise AssertionError(f"Columns select: {len(failures)} button state failures")

    # Verify columns-view panel is visible
    columns_view = tester.find_element(By.ID, "columns-view")
    columns_visible = tester.get_computed_style(By.ID, "columns-view", "display")
    assert columns_visible != "none", "columns-view panel should be visible"

    take_screenshot(tester, "buttons-columns.png", "Columns select buttons")
    print("  ✓ All button states correct for columns select view")


def test_error_view_button_states(tester):
    """Test button states in error view.

    Per design §6.2 STEP 4d: all controls disabled, error close button enabled.
    We trigger an error by navigating to a non-existent backend.
    """
    print("\n[Test 6] Error view button states")

    # Trigger error by fetching a non-existent API endpoint via JS
    navigate_to_view(tester, "chart")

    # We simulate an error state by calling setView with a view that will fail
    # Strategy: block all fetch requests then trigger a date nav which calls setView
    tester.execute_script("""
        // Override fetch to simulate error
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            return Promise.reject(new Error("Simulated error for testing"));
        };
    """)

    # Click "Today" button to trigger a setView (which calls fetch)
    today_btn = tester.find_element(By.ID, "today-btn")
    today_btn.click()

    # Wait for error view
    tester.wait_for_element(By.ID, "error-view")
    time.sleep(0.5)

    failures = []
    for control, expected in EXPECTED_STATES["error"].items():
        failures.extend(check_control(tester, control, expected, "error"))

    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-error-fail.png", "Error view button failures")
        raise AssertionError(f"Error view: {len(failures)} button state failures")

    # Verify error close button is enabled
    error_close = tester.find_element(By.ID, "error-close-btn")
    close_disabled = error_close.get_attribute("disabled")
    if close_disabled is not None and close_disabled != "false":
        print("  ✗ error-close-btn should be enabled")
        failures.append("error-close-btn is disabled")

    if failures:
        raise AssertionError(f"Error view: {len(failures)} button state failures")

    take_screenshot(tester, "buttons-error.png", "Error view buttons")
    print("  ✓ All button states correct for error view")

    # Note: fetch is NOT restored here — the caller navigates fresh to chart view
    # which reloads the page and resets fetch to its native behavior.


def test_button_transition_chart_to_grid(tester):
    """Test button states transition when toggling chart -> grid -> chart."""
    print("\n[Test 7] Button transition: chart -> grid -> chart")

    # Start in chart view
    navigate_to_view(tester, "chart")
    view_text = get_button_text(tester, "view-toggle")
    assert view_text == "📋 Data Grid", f"Expected '📋 Data Grid', got '{view_text}'"
    print(f"  ✓ Chart: view-toggle text = '{view_text}'")

    # Toggle to grid
    view_toggle_btn = tester.find_element(By.ID, "view-toggle")
    view_toggle_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    view_text = get_button_text(tester, "view-toggle")
    assert view_text == "📈 Chart", f"Expected '📈 Chart', got '{view_text}'"
    print(f"  ✓ Grid: view-toggle text = '{view_text}'")

    # CSV should now be visible
    csv_visible = is_element_visible(tester, "export-btn")
    assert csv_visible, "CSV export should be visible in grid view"
    print("  ✓ CSV export visible in grid view")

    # Toggle back to chart
    view_toggle_btn = tester.find_element(By.ID, "view-toggle")
    view_toggle_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    view_text = get_button_text(tester, "view-toggle")
    assert view_text == "📋 Data Grid", f"Expected '📋 Data Grid', got '{view_text}'"
    print(f"  ✓ Chart: view-toggle text = '{view_text}' (after toggle back)")

    # CSV should now be hidden
    csv_visible = is_element_visible(tester, "export-btn")
    assert not csv_visible, "CSV export should be hidden in chart view"
    print("  ✓ CSV export hidden in chart view")

    take_screenshot(tester, "buttons-transition.png", "Button transition chart<->grid")
    print("  ✓ Button transitions work correctly")


def test_button_transition_normal_to_histogram(tester):
    """Test button states transition when toggling chart -> histogram -> chart."""
    print("\n[Test 8] Button transition: chart -> histogram -> chart")

    # Start in chart view
    navigate_to_view(tester, "chart")
    hist_text = get_button_text(tester, "histogram-btn")
    assert hist_text == "📊 Histogram", f"Expected '📊 Histogram', got '{hist_text}'"
    print(f"  ✓ Chart: histogram-btn text = '{hist_text}'")

    # Toggle to histogram
    hist_btn = tester.find_element(By.ID, "histogram-btn")
    hist_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    hist_text = get_button_text(tester, "histogram-btn")
    assert hist_text == "📋 Raw Chart", f"Expected '📋 Raw Chart', got '{hist_text}'"
    print(f"  ✓ Histogram: histogram-btn text = '{hist_text}'")

    # Histogram controls should be visible
    assert get_histogram_controls_visible(tester), "histogram-controls should be visible"
    assert is_element_visible(tester, "split-btn"), "split-btn should be visible"
    assert is_element_visible(tester, "bin-size-select"), "bin-size-select should be visible"
    assert is_element_visible(tester, "day-filter-select"), "day-filter-select should be visible"
    print("  ✓ Histogram controls visible (bin-size, day-filter, split)")

    # Toggle back to chart (via histogram toggle which goes back to chart)
    hist_btn = tester.find_element(By.ID, "histogram-btn")
    hist_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    hist_text = get_button_text(tester, "histogram-btn")
    assert hist_text == "📊 Histogram", f"Expected '📊 Histogram', got '{hist_text}'"
    print(f"  ✓ Chart: histogram-btn text = '{hist_text}' (after toggle back)")

    # Histogram controls should be hidden
    assert not get_histogram_controls_visible(tester), "histogram-controls should be hidden"
    assert not is_element_visible(tester, "split-btn"), "split-btn should be hidden"
    print("  ✓ Histogram controls hidden in chart view")

    take_screenshot(tester, "buttons-transition-histogram.png",
                   "Button transition chart<->histogram")
    print("  ✓ Histogram transitions work correctly")


def test_view_label_in_status_bar(tester):
    """Test that the view label in the status bar updates correctly."""
    print("\n[Test 9] View label in status bar")

    expected_labels = {
        "chart": "Chart",
        "grid": "Data Grid",
        "histogram": "Histogram",
        "histogram-grid": "Histogram Grid",
    }

    for view_mode, expected_label in expected_labels.items():
        navigate_to_view(tester, view_mode)

        label_el = tester.find_element(By.ID, "view-label")
        actual_label = label_el.text.strip() if label_el else ""
        assert actual_label == expected_label, \
            f"View label in {view_mode}: expected '{expected_label}', got '{actual_label}'"
        print(f"  ✓ {view_mode}: view-label = '{actual_label}'")

    print("  ✓ All view labels correct in status bar")


# ── Main ────────────────────────────────────────────────────────────

def main():
    """Run all tests."""
    print("=" * 70)
    print("Deye Logger Viewer - Button State Tests")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")
    print(f"Screenshots: {SCREENSHOT_DIR}")
    print("=" * 70)

    # Create screenshots directory
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # Start Firefox tester (headless)
    print("\n[Setup] Starting Firefox (headless mode)...")

    with FirefoxTester(headless=True) as tester:
        # Verify server is running
        print("[Setup] Checking if server is running...")
        params = {"date": TEST_DATE}
        tester.navigate(f"{BASE_URL}/?{urlencode(params)}")
        title = tester.get_title()
        print(f"  ✓ Server running, page title: {title}")

        # Run tests
        try:
            test_chart_view_button_states(tester)
            test_grid_view_button_states(tester)
            test_histogram_view_button_states(tester)
            test_histogram_grid_view_button_states(tester)
            test_columns_select_button_states(tester)

            # Close columns panel before continuing
            navigate_to_view(tester, "chart")

            test_error_view_button_states(tester)

            # After error, navigate to chart to continue
            # The error test restores fetch but the page is in error state
            # Navigate fresh to get out of error state
            navigate_to_view(tester, "chart")

            test_button_transition_chart_to_grid(tester)
            test_button_transition_normal_to_histogram(tester)
            test_view_label_in_status_bar(tester)

        except AssertionError as e:
            print(f"\n✗ Test failed: {e}")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "error-state.png"))
            print(f"  Error screenshot saved to {SCREENSHOT_DIR}/error-state.png")
            sys.exit(1)
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "error-state.png"))
            print(f"  Error screenshot saved to {SCREENSHOT_DIR}/error-state.png")
            raise

    print("\n" + "=" * 70)
    print("All button state tests passed!")
    print(f"Screenshots saved to: {SCREENSHOT_DIR}")
    print("=" * 70)

    # List generated screenshots
    screenshots = sorted(f for f in os.listdir(SCREENSHOT_DIR) if f.startswith("buttons-"))
    if screenshots:
        print(f"\nGenerated {len(screenshots)} button test screenshots:")
        for s in screenshots:
            filepath = os.path.join(SCREENSHOT_DIR, s)
            size = os.path.getsize(filepath)
            print(f"  - {s} ({size:,} bytes)")


if __name__ == "__main__":
    main()
