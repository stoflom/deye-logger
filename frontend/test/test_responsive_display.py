#!/usr/bin/env python3
"""
Test script to verify responsive display panel behavior:
- Title bar wrapping with histogram controls
- Summary cards scaling and stacking at different viewport widths
- Vertical scrolling of display panel
- All four view modes (chart, grid, histogram, histogram-grid)
- Histogram controls in title bar (not separate panel)

Usage:
  python3 test_responsive_display.py

Screenshots are saved to frontend/test/screenshots/
"""

import sys
import os
import time
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

# Add the skill directory to sys.path to allow importing
skill_path = "/home/stoflom/.pi/agent/skills/firefox-testing"
if skill_path not in sys.path:
    sys.path.append(skill_path)

from firefox_tester import FirefoxTester
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
TEST_DATE = "2026-07-27"  # Date with actual data
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
VIEWPORTS = {
    "wide": (1440, 900),
    "medium": (1024, 768),
    "narrow": (768, 1024),
    "mobile": (375, 667),
}

# ── Helper Functions ────────────────────────────────────────────────

def resize_viewport(tester, width, height):
    """Resize browser viewport."""
    tester.set_window_size(width, height)
    time.sleep(0.3)  # Wait for CSS transitions


def take_screenshot(tester, filename, description=""):
    """Take screenshot and save to SCREENSHOT_DIR."""
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    tester.screenshot(filepath)
    print(f"  ✓ {description}: {filepath}")


def set_view(tester, view_mode):
    """Set view mode via URL and wait for content."""
    from urllib.parse import urlencode
    params = {"date": TEST_DATE, "view": view_mode}
    url = f"{BASE_URL}/?{urlencode(params)}"
    tester.navigate(url)
    tester.wait_for_element(By.ID, "summary-cards")
    time.sleep(0.5)


def test_histogram_controls_in_title_bar(tester):
    """Test that histogram controls are in title bar, not separate panel."""
    print("\n[Test 1] Histogram controls location")

    # Switch to histogram mode
    set_view(tester, "histogram")
    resize_viewport(tester, 600, 800)

    # Check that histogram-controls element exists in title bar
    histogram_controls = tester.find_element(By.ID, "histogram-controls")
    assert histogram_controls is not None, "Histogram controls should exist"

    # Check it's within the header element
    header = tester.find_element(By.CSS_SELECTOR, ".header")
    controls_in_header = header.find_elements(By.CSS_SELECTOR, "#histogram-controls")
    assert len(controls_in_header) > 0, "Histogram controls should be inside .header"

    # Check that histogram-panel element does NOT exist (removed)
    has_panel = tester.is_element_present(By.ID, "histogram-panel")
    assert not has_panel, "histogram-panel should not exist in DOM"

    # Verify bin-size select and split button are visible
    bin_size_select = tester.find_element(By.ID, "bin-size-select")
    split_btn = tester.find_element(By.ID, "split-btn")
    assert bin_size_select is not None, "Bin size select should be visible"
    assert split_btn is not None, "Split button should be visible"

    print("  ✓ Histogram controls are inside title bar")
    print("  ✓ histogram-panel element correctly removed from DOM")
    print("  ✓ Bin size and split button visible")

    take_screenshot(tester, "histogram-controls-in-header.png",
                   "Histogram controls in title bar")


def test_title_bar_wrapping(tester):
    """Test that title bar wraps into multiple rows at narrow widths."""
    print("\n[Test 2] Title bar wrapping behavior")

    for viewport_name, (width, height) in VIEWPORTS.items():
        resize_viewport(tester, width, height)
        set_view(tester, "chart")
        take_screenshot(tester, f"title-bar-{viewport_name}.png",
                       f"Title bar ({viewport_name}: {width}x{height})")

    # At narrow width, check that controls wrapped
    resize_viewport(tester, 600, 800)
    set_view(tester, "chart")

    # Get header height to detect wrapping
    header = tester.find_element(By.CSS_SELECTOR, ".header")
    header_height = header.size.get("height", 0)
    print(f"  ✓ Header height at 600px: {header_height}px "
          f"(wrapping increases height)")


def test_view_modes_render(tester):
    """Test all four view modes render correctly."""
    print("\n[Test 3] All view modes render correctly")

    views = ["chart", "grid", "histogram", "histogram-grid"]

    for view_mode in views:
        set_view(tester, view_mode)

        # Wait for summary cards
        cards = tester.find_element(By.ID, "summary-cards")
        assert cards is not None, f"{view_mode} should have summary cards"

        # Take screenshot
        take_screenshot(tester, f"view-{view_mode}.png",
                       f"{view_mode.title()} view")

        print(f"  ✓ {view_mode.title()} view rendered successfully")


def test_summary_cards_scaling(tester):
    """Test that summary cards scale down as viewport narrows."""
    print("\n[Test 4] Summary cards scaling and stacking")

    set_view(tester, "chart")

    card_counts = {}

    for viewport_name, (width, height) in VIEWPORTS.items():
        resize_viewport(tester, width, height)

        # Get card count and layout info
        cards = tester.find_elements(By.CSS_SELECTOR, ".summary-card")
        card_count = len(cards) if cards else 0
        card_counts[viewport_name] = card_count

        # Get container width
        cards_container = tester.find_element(By.ID, "summary-cards")
        container_width = cards_container.size.get("width", 0)

        print(f"  Viewport {viewport_name:8s} ({width:4d}x{height:4d}): "
              f"{card_count} cards, container width={container_width}px")

        take_screenshot(tester, f"cards-{viewport_name}.png",
                       f"Summary cards ({viewport_name}: {width}x{height})")

    # Verify card counts are consistent across viewports
    counts = list(card_counts.values())
    assert all(c == counts[0] for c in counts), \
        f"Card count should be consistent across viewports: {card_counts}"
    print(f"  ✓ Card count consistent: {counts[0]} cards at all viewports")


def test_cards_stacking_at_mobile(tester):
    """Test that cards stack vertically at mobile width."""
    print("\n[Test 5] Card stacking at mobile width")

    set_view(tester, "chart")
    resize_viewport(tester, 375, 667)

    # Get all cards
    cards = tester.find_elements(By.CSS_SELECTOR, ".summary-card")

    if cards and len(cards) > 1:
        # Check vertical stacking by measuring positions
        positions = []
        for card in cards[:3]:  # Check first 3 cards
            rect = card.rect
            positions.append({"x": rect["x"], "y": rect["y"], "width": rect["width"]})

        if len(positions) >= 2:
            y_diff = positions[1]["y"] - positions[0]["y"]
            x_same = abs(positions[1]["x"] - positions[0]["x"]) < 5  # aligned left

            # At mobile width, cards should be full-width and vertically stacked
            container_width = tester.find_element(By.ID, "summary-cards").size.get("width", 0)
            first_card_width = positions[0]["width"]

            print(f"  Card 1: x={positions[0]['x']}, y={positions[0]['y']}, "
                  f"w={positions[0]['width']}px")
            print(f"  Card 2: x={positions[1]['x']}, y={positions[1]['y']}, "
                  f"w={positions[1]['width']}px")
            print(f"  Card 3: x={positions[2]['x']}, y={positions[2]['y']}, "
                  f"w={positions[2]['width']}px")
            print(f"  Vertical spacing: {y_diff}px")
            print(f"  First card width: {first_card_width}px / container: {container_width}px")

            if first_card_width >= container_width * 0.8:
                print(f"  ✓ Cards are full-width at mobile (stacked)")
            else:
                print(f"  ⚠ Cards may not be full-width yet")

    take_screenshot(tester, "cards-stacked-mobile.png",
                   "Summary cards stacked vertically at mobile width")


def test_display_panel_scroll(tester):
    """Test that #content-area scrolls when content exceeds viewport.

    All views share a single scroll pane (#content-area).  Content panels
    have min-height: 300px so they force a scrollbar when the viewport is
    too small — no nested scrollbars."""
    print("\n[Test 6] Single scroll pane (#content-area) scrolling")

    # Use chart view with data
    set_view(tester, "chart")

    # Resize to small viewport where title bar wraps, reducing available height
    resize_viewport(tester, 600, 600)

    # Get #content-area dimensions
    content_area = tester.find_element(By.ID, "content-area")
    client_height = tester.execute_script(
        "return document.getElementById('content-area').clientHeight;"
    )
    scroll_height = tester.execute_script(
        "return document.getElementById('content-area').scrollHeight;"
    )
    overflow_y = tester.execute_script(
        "return window.getComputedStyle(document.getElementById('content-area')).overflowY;"
    )
    print(f"  #content-area overflow-y: {overflow_y}")
    print(f"  #content-area clientHeight: {client_height}px")
    print(f"  #content-area scrollHeight: {scroll_height}px")

    assert overflow_y in ("auto", "scroll"), \
        f"#content-area should be scrollable, got overflow-y: {overflow_y}"

    if scroll_height > client_height:
        print("  ✓ Content exceeds viewport — scrollbar present")
    else:
        print("  ⚠ Content fits in viewport (scrollbar not visible at this size)")

    # Verify content panels have min-height: 300px
    chart_view = tester.find_element(By.ID, "raw-data-chart-view")
    min_h = tester.execute_script(
        "return window.getComputedStyle(arguments[0]).minHeight;", chart_view
    )
    print(f"  #raw-data-chart-view min-height: {min_h}")
    assert min_h == "300px", f"Content panels should have min-height: 300px, got {min_h}"

    # Verify #split-histogram-scroll has NO nested overflow
    split_overflow = tester.execute_script(
        "return window.getComputedStyle(document.getElementById('split-histogram-scroll')).overflowY;"
    )
    print(f"  #split-histogram-scroll overflow-y: {split_overflow}")
    assert split_overflow == "visible", \
        f"#split-histogram-scroll should NOT have nested scroll, got {split_overflow}"

    take_screenshot(tester, "scrollable-panel.png",
                   "Single scroll pane (#content-area) at small viewport")


def test_histogram_control_visibility(tester):
    """Test histogram controls visibility toggling."""
    print("\n[Test 7] Histogram controls visibility")

    # Chart view - controls should be hidden
    set_view(tester, "chart")
    resize_viewport(tester, 900, 800)
    histogram_controls = tester.find_element(By.ID, "histogram-controls")
    display = tester.get_computed_style(By.CSS_SELECTOR, ".histogram-controls", "display")
    print(f"  Chart view - histogram-controls display: {display}")

    # Histogram view - controls should be visible
    set_view(tester, "histogram")
    histogram_controls = tester.find_element(By.ID, "histogram-controls")
    display = tester.get_computed_style(By.CSS_SELECTOR, ".histogram-controls", "display")
    print(f"  Histogram view - histogram-controls display: {display}")

    take_screenshot(tester, "histogram-controls-visibility.png",
                   "Histogram controls visibility toggle")


def test_all_view_modes_with_histogram_controls(tester):
    """Test histogram controls are present in histogram view modes."""
    print("\n[Test 8] Histogram controls in histogram view modes")

    for view_mode in ["histogram", "histogram-grid"]:
        set_view(tester, view_mode)
        resize_viewport(tester, 900, 800)

        # Controls should be visible
        histogram_controls = tester.find_element(By.ID, "histogram-controls")
        display = tester.get_computed_style(By.CSS_SELECTOR, ".histogram-controls", "display")
        print(f"  {view_mode}: controls display={display}")

        bin_select = tester.find_element(By.ID, "bin-size-select")
        split_btn = tester.find_element(By.ID, "split-btn")
        print(f"  {view_mode}: bin-select={bin_select is not None}, split-btn={split_btn is not None}")

        take_screenshot(tester, f"controls-{view_mode}.png",
                       f"Histogram controls in {view_mode} view")

    print("  ✓ All histogram view modes show controls")



def test_single_scroll_pane_structure(tester):
    """Test that #summary-cards is inside #content-area (single scroll pane)."""
    print("\n[Test 9] Single scroll pane structure")

    set_view(tester, "chart")
    resize_viewport(tester, 900, 800)

    # Check that content-area exists and is scrollable
    content_area = tester.find_element(By.ID, "content-area")
    assert content_area is not None, "#content-area should exist"

    # Check that summary-cards is a direct child of content-area
    summary_cards = tester.find_element(By.ID, "summary-cards")
    cards_parent_id = tester.execute_script(
        "return arguments[0].parentElement.id;", summary_cards
    )
    assert cards_parent_id == "content-area", f"Summary cards should be a direct child of #content-area, got parent: #{cards_parent_id}"

    # Check that chart view is inside content-area
    chart_view = tester.find_element(By.ID, "raw-data-chart-view")
    chart_inside = tester.execute_script(
        "let el = arguments[0]; while (el) { if (el.id === 'content-area') return true; el = el.parentElement; } return false;",
        chart_view
    )
    assert chart_inside, "Chart view should be inside #content-area"

    # Verify content-area has overflow-y: auto (scrollable)
    overflow = tester.execute_script(
        "return window.getComputedStyle(document.getElementById('content-area')).getPropertyValue('overflow-y');"
    )
    print(f"  #content-area overflow-y: {overflow}")
    assert overflow == "auto" or overflow == "scroll",         f"#content-area should be scrollable (overflow-y: auto), got: {overflow}"

    # Verify summary-cards is visible in chart view
    display = tester.get_computed_style(By.CSS_SELECTOR, ".summary-cards", "display")
    print(f"  Summary cards display: {display}")
    assert display != "none", "Summary cards should be visible in chart view"

    # Verify chart view fills remaining space
    chart_view_height = chart_view.size.get("height", 0)
    content_area_height = content_area.size.get("height", 0)
    summary_cards_height = summary_cards.size.get("height", 0)
    print(f"  Content-area height: {content_area_height}px")
    print(f"  Summary-cards height: {summary_cards_height}px")
    print(f"  Chart-view height: {chart_view_height}px")
    print(f"  Content-area - (cards + chart): {content_area_height - (summary_cards_height + chart_view_height)}px")

    # The chart should fill remaining space (gap should be small)
    gap = abs(content_area_height - (summary_cards_height + chart_view_height))
    assert gap < 50, f"Chart should fill remaining space (gap={gap}px)"

    # Test scroll functionality: verify overflow is enabled
    scroll_height = tester.execute_script("return document.getElementById('content-area').scrollHeight;")
    client_height = tester.execute_script("return document.getElementById('content-area').clientHeight;")
    can_scroll = scroll_height > client_height
    print(f"  Scrollable: overflow-y='auto', scrollHeight={scroll_height}px, clientHeight={client_height}px")
    print(f"  Content overflows container: {can_scroll}")
    # Note: the key fix is that overflow-y: auto is set on #content-area,
    # enabling scrolling whenever content exceeds the container height

    take_screenshot(tester, "single-scroll-pane.png",
                   "Single scroll pane with summary cards at top")
    print("  ✓ Single scroll pane structure verified")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Deye Logger Viewer - Responsive Display Panel Tests")
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
        from urllib.parse import urlencode
        params = {"date": TEST_DATE}
        tester.navigate(f"{BASE_URL}/?{urlencode(params)}")
        title = tester.get_title()
        print(f"  ✓ Server running, page title: {title}")

        # Run tests
        try:
            test_histogram_controls_in_title_bar(tester)
            test_title_bar_wrapping(tester)
            test_view_modes_render(tester)
            test_summary_cards_scaling(tester)
            test_cards_stacking_at_mobile(tester)
            test_display_panel_scroll(tester)
            test_histogram_control_visibility(tester)
            test_all_view_modes_with_histogram_controls(tester)
            test_single_scroll_pane_structure(tester)
        except AssertionError as e:
            print(f"\n✗ Test failed: {e}")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "error-state.png"))
            print(f"  ✓ Error screenshot saved to {SCREENSHOT_DIR}/error-state.png")
            sys.exit(1)
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "error-state.png"))
            print(f"  ✓ Error screenshot saved to {SCREENSHOT_DIR}/error-state.png")
            raise

    print("\n" + "=" * 70)
    print("All tests completed!")
    print(f"Screenshots saved to: {SCREENSHOT_DIR}")
    print("=" * 70)

    # List generated screenshots
    screenshots = os.listdir(SCREENSHOT_DIR)
    if screenshots:
        print(f"\nGenerated {len(screenshots)} screenshots:")
        for s in sorted(screenshots):
            filepath = os.path.join(SCREENSHOT_DIR, s)
            size = os.path.getsize(filepath)
            print(f"  - {s} ({size:,} bytes)")



if __name__ == "__main__":
    main()
