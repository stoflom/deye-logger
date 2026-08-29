#!/usr/bin/env python3
"""
Test script to verify button states in major frontend views.

Covers the following views as per frontend-design.md §9.3 (v5.0 button scheme):
  - chart / grid
  - histogram / histogram-grid
  - stats / stats-grid
  - columns select (transient)
  - error

Button scheme (#62):
  - Major views (blue): #chart-btn (Series), #histogram-btn, #stats-btn —
    the active view's button is disabled (grey), the other two are blue;
    hidden in grid views and the columns (Select) view.
  - Grid utility (#view-toggle): "📋 Grid" on major views, "Back" in grid
    views (auto-return to the view that opened the grid).
  - Columns (#columns-toggle): "☰ Select" closed, "Back" open.

For each view, verifies:
  - Button visibility (display style)
  - Button enabled/disabled state
  - Button text labels
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
    "chartBtn": "chart-btn",
    "histogramToggle": "histogram-btn",
    "statsBtn": "stats-btn",
    "exportCsv": "export-btn",
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
        # Major-view buttons: active (Series) disabled (grey); others blue (#62)
        "chartBtn": {"enabled": False, "visible": True, "text": "📈 Series"},
        "histogramToggle": {"enabled": True, "visible": True, "text": "📊 Histogram"},
        "statsBtn": {"enabled": True, "visible": True, "text": "📈 Stats"},
        # Grid utility: opens the grid for the current view (grey in major views)
        "viewToggle": {"enabled": True, "visible": True, "text": "📋 Grid", "blue": False},
        # Export: hidden in non-grid views
        "exportCsv": {"enabled": True, "visible": False},
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
        # Major-view buttons hidden in grid views (#62)
        "chartBtn": {"enabled": False, "visible": False},
        "histogramToggle": {"enabled": False, "visible": False},
        "statsBtn": {"enabled": False, "visible": False},
        # Grid utility reads Back (blue, .active — #76) — auto-return to the Series view
        "viewToggle": {"enabled": True, "visible": True, "text": "Back", "blue": True},
        # Export: visible in grid views
        "exportCsv": {"enabled": True, "visible": True},
        "binSize": {"enabled": True, "visible": False},
        "dayFilter": {"enabled": True, "visible": False},
    },
    "histogram": {
        "prevDay": {"enabled": True, "visible": True},
        "nextDay": {"enabled": True, "visible": True},
        "today": {"enabled": True, "visible": True},
        "refresh": {"enabled": True, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "☰ Select"},
        # Major-view buttons: active (Histogram) disabled (grey); others blue (#62)
        "chartBtn": {"enabled": True, "visible": True, "text": "📈 Series"},
        "histogramToggle": {"enabled": False, "visible": True, "text": "📊 Histogram"},
        "statsBtn": {"enabled": True, "visible": True, "text": "📈 Stats"},
        # Grid utility: opens histogram-grid (grey in major views)
        "viewToggle": {"enabled": True, "visible": True, "text": "📋 Grid", "blue": False},
        # Export: hidden in histogram views
        "exportCsv": {"enabled": True, "visible": False},
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
        # Major-view buttons hidden in grid views (#62)
        "chartBtn": {"enabled": False, "visible": False},
        "histogramToggle": {"enabled": False, "visible": False},
        "statsBtn": {"enabled": False, "visible": False},
        # Grid utility reads Back (blue, .active — #76) — auto-return to the Histogram view
        "viewToggle": {"enabled": True, "visible": True, "text": "Back", "blue": True},
        # Export: visible in grid views (histogram-grid is a grid)
        "exportCsv": {"enabled": True, "visible": True},
        # Histogram controls: visible in histogram modes
        "binSize": {"enabled": True, "visible": True},
        "dayFilter": {"enabled": True, "visible": True},
    },
    "stats": {
        "prevDay": {"enabled": True, "visible": True},
        "nextDay": {"enabled": True, "visible": True},
        "today": {"enabled": True, "visible": True},
        "refresh": {"enabled": True, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "☰ Select"},
        # Major-view buttons: active (Stats) disabled (grey); others blue (#62)
        "chartBtn": {"enabled": True, "visible": True, "text": "📈 Series"},
        "histogramToggle": {"enabled": True, "visible": True, "text": "📊 Histogram"},
        "statsBtn": {"enabled": False, "visible": True, "text": "📈 Stats"},
        # Grid utility: opens stats-grid (table) (grey in major views)
        "viewToggle": {"enabled": True, "visible": True, "text": "📋 Grid", "blue": False},
        "exportCsv": {"enabled": True, "visible": False},
        "binSize": {"enabled": True, "visible": False},
        "dayFilter": {"enabled": True, "visible": True},
    },
    "stats-grid": {
        "prevDay": {"enabled": True, "visible": True},
        "nextDay": {"enabled": True, "visible": True},
        "today": {"enabled": True, "visible": True},
        "refresh": {"enabled": True, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "☰ Select"},
        # Major-view buttons hidden in grid views (#62)
        "chartBtn": {"enabled": False, "visible": False},
        "histogramToggle": {"enabled": False, "visible": False},
        "statsBtn": {"enabled": False, "visible": False},
        # Grid utility reads Back (blue, .active — #76) — auto-return to the Stats view
        "viewToggle": {"enabled": True, "visible": True, "text": "Back", "blue": True},
        # Export: visible in grid views (stats-grid is a grid)
        "exportCsv": {"enabled": True, "visible": True},
        "binSize": {"enabled": True, "visible": False},
        "dayFilter": {"enabled": True, "visible": True},
    },
    "columns": {
        # Only columnsToggle ("Back") is enabled; all others are disabled.
        # Major-view buttons are hidden; visibility of the rest is inherited
        # from the underlying view (chart here) — the columns panel is a
        # transient overlay, not a view change.
        "prevDay": {"enabled": False, "visible": True},
        "nextDay": {"enabled": False, "visible": True},
        "today": {"enabled": False, "visible": True},
        "refresh": {"enabled": False, "visible": True},
        "columnsToggle": {"enabled": True, "visible": True, "text": "Back"},
        # Major-view buttons hidden in the columns (Select) view (#62)
        "chartBtn": {"enabled": False, "visible": False},
        "histogramToggle": {"enabled": False, "visible": False},
        "statsBtn": {"enabled": False, "visible": False},
        "viewToggle": {"enabled": False, "visible": True, "blue": False},  # grey (inherited from chart)
        "exportCsv": {"enabled": False, "visible": False},  # hidden (inherited from chart)
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
        "viewToggle": {"enabled": False, "visible": True, "blue": False},  # grey (inherited from chart)
        "chartBtn": {"enabled": False, "visible": True},
        "histogramToggle": {"enabled": False, "visible": True},
        "statsBtn": {"enabled": False, "visible": True},
        "exportCsv": {"enabled": False, "visible": False},  # hidden (inherited from chart)
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

    # Check blue (.active) styling — #3182ce = rgb(49, 130, 206)
    expected_blue = expected.get("blue")
    if expected_blue is not None:
        bg = tester.get_computed_style(By.ID, element_id, "background-color")
        actual_blue = bg == "rgb(49, 130, 206)"
        if actual_blue != expected_blue:
            failures.append(
                f"  {control_name} blue: expected {expected_blue}, got {actual_blue} (bg={bg})"
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

    take_screenshot(tester, "buttons-histogram-grid.png", "Histogram-grid view buttons")
    print("  ✓ All button states correct for histogram-grid view")


def test_columns_select_button_states(tester):
    """Test button states when columns selection panel is open.

    Per design §6.2 STEP 4a: only columnsToggle ('Back') is enabled and the
    major-view buttons are hidden; all other controls are disabled (#62).
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
    assert view_text == "📋 Grid", f"Expected '📋 Grid', got '{view_text}'"
    print(f"  ✓ Chart: view-toggle text = '{view_text}'")

    # #57: tooltip clarifies grid shows the chart's data; compact padding
    view_title = tester.find_element(By.ID, "view-toggle").get_attribute("title")
    assert view_title == "Show the chart data as a grid", f"view-toggle title (got '{view_title}')"
    padding = tester.execute_script(
        "return getComputedStyle(document.getElementById('view-toggle')).paddingLeft;"
    )
    assert padding == "10px", f"compact horizontal padding 10px (got {padding})"
    print(f"  ✓ #57: tooltip='{view_title}', paddingLeft={padding}")

    # Open grid via the Grid utility button
    view_toggle_btn = tester.find_element(By.ID, "view-toggle")
    view_toggle_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    view_text = get_button_text(tester, "view-toggle")
    assert view_text == "Back", f"Expected 'Back' in grid view, got '{view_text}'"
    print(f"  ✓ Grid: view-toggle text = '{view_text}'")

    # CSV should now be visible
    csv_visible = is_element_visible(tester, "export-btn")
    assert csv_visible, "CSV export should be visible in grid view"
    print("  ✓ CSV export visible in grid view")

    # Major-view buttons must be hidden in grid views (#62)
    for btn_id in ("chart-btn", "histogram-btn", "stats-btn"):
        assert not is_element_visible(tester, btn_id), \
            f"{btn_id} should be hidden in grid view"
    print("  ✓ Major-view buttons hidden in grid view")

    # Auto-return to chart via Back
    view_toggle_btn = tester.find_element(By.ID, "view-toggle")
    view_toggle_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    view_text = get_button_text(tester, "view-toggle")
    assert view_text == "📋 Grid", f"Expected '📋 Grid', got '{view_text}'"
    print(f"  ✓ Chart: view-toggle text = '{view_text}' (after Back auto-return)")

    # CSV should now be hidden; Series button disabled (active view) (#62)
    csv_visible = is_element_visible(tester, "export-btn")
    assert not csv_visible, "CSV export should be hidden in chart view"
    print("  ✓ CSV export hidden in chart view")
    assert is_element_disabled(tester, "chart-btn"), "Series button should be disabled in chart view"
    assert not is_element_disabled(tester, "histogram-btn"), "Histogram button should be enabled in chart view"
    assert not is_element_disabled(tester, "stats-btn"), "Stats button should be enabled in chart view"
    print("  ✓ Series disabled (active); Histogram/Stats enabled in chart view")

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

    # Switch to histogram via the Histogram major-view button
    hist_btn = tester.find_element(By.ID, "histogram-btn")
    hist_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    hist_text = get_button_text(tester, "histogram-btn")
    assert hist_text == "📊 Histogram", f"Expected '📊 Histogram', got '{hist_text}'"
    assert is_element_disabled(tester, "histogram-btn"), \
        "Histogram button should be disabled (grey) in histogram view"
    assert not is_element_disabled(tester, "chart-btn"), \
        "Series button should be enabled in histogram view"
    print(f"  ✓ Histogram: histogram-btn = '{hist_text}' (disabled/active)")

    # Histogram controls should be visible
    assert get_histogram_controls_visible(tester), "histogram-controls should be visible"
    assert is_element_visible(tester, "bin-size-select"), "bin-size-select should be visible"
    assert is_element_visible(tester, "day-filter-select"), "day-filter-select should be visible"

    # histogram → histogram-grid via Grid utility, auto-return via Back (#62)
    grid_btn = tester.find_element(By.ID, "view-toggle")
    grid_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)
    assert get_button_text(tester, "view-toggle") == "Back", \
        "view-toggle should read 'Back' in histogram-grid"
    assert not is_element_visible(tester, "chart-btn"), "major buttons hidden in histogram-grid"
    print("  ✓ histogram-grid: view-toggle = 'Back', major buttons hidden")
    grid_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)
    assert get_button_text(tester, "view-toggle") == "📋 Grid", \
        "Back should auto-return to the Histogram view"
    print("  ✓ Back auto-returned to Histogram view")

    # Switch back to chart via the Series major-view button
    series_btn = tester.find_element(By.ID, "chart-btn")
    series_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    assert is_element_disabled(tester, "chart-btn"), \
        "Series button should be disabled (grey) in chart view"
    assert not is_element_disabled(tester, "histogram-btn"), \
        "Histogram button should be enabled in chart view"
    print("  ✓ Chart: Series disabled (active), Histogram enabled")

    # Histogram controls should be hidden
    assert not get_histogram_controls_visible(tester), "histogram-controls should be hidden"
    print("  ✓ Histogram controls hidden in chart view")

    take_screenshot(tester, "buttons-transition-histogram.png",
                   "Button transition chart<->histogram")
    print("  ✓ Histogram transitions work correctly")


def test_stats_view_button_states(tester):
    """Test button states in stats and stats-grid views + Grid/Back auto-return (#62)."""
    print("\n[Test 10] Stats view button states")
    navigate_to_view(tester, "stats")

    failures = []
    for control, expected in EXPECTED_STATES["stats"].items():
        failures.extend(check_control(tester, control, expected, "stats"))
    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-stats-fail.png", "Stats view button failures")
        raise AssertionError(f"Stats view: {len(failures)} button state failures")
    print("  ✓ All button states correct for stats view")

    # stats → stats-grid via Grid utility, auto-return via Back
    grid_btn = tester.find_element(By.ID, "view-toggle")
    grid_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)

    failures = []
    for control, expected in EXPECTED_STATES["stats-grid"].items():
        failures.extend(check_control(tester, control, expected, "stats-grid"))
    if failures:
        print("  ✗ FAILURES:")
        for f in failures:
            print(f)
        take_screenshot(tester, "buttons-stats-grid-fail.png", "Stats-grid view button failures")
        raise AssertionError(f"Stats-grid view: {len(failures)} button state failures")
    print("  ✓ All button states correct for stats-grid view")

    assert get_button_text(tester, "view-toggle") == "Back", \
        "view-toggle should read 'Back' in stats-grid"
    grid_btn.click()
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)
    assert get_button_text(tester, "view-toggle") == "📋 Grid", \
        "Back should auto-return to the Stats view"
    print("  ✓ Back auto-returned to Stats view")

    take_screenshot(tester, "buttons-stats.png", "Stats view buttons")


def test_view_label_in_status_bar(tester):
    """Test that the view label in the status bar updates correctly."""
    print("\n[Test 9] View label in status bar")

    expected_labels = {
        "chart": "Series",
        "grid": "Data Grid",
        "histogram": "Histogram",
        "histogram-grid": "Histogram Grid",
        "stats": "Stats",
        "stats-grid": "Stats Grid",
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
            test_stats_view_button_states(tester)
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
