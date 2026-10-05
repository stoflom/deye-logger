#!/usr/bin/env python3
"""
Test script to verify the summary cards Max/Latest toggle
(frontend-design.md v9.0, §17 — issue #99).

Covers:
  - Per-card `.card-toggle` present on raw-data views (chart/grid)
  - Toggle enabled only for a single-day selection of today
  - Click switches only that card to the latest reading ("Latest")
  - Shift+click switches ALL cards to the same mode
  - Previous days: toggle disabled, cards show "Max"
  - Histogram view: no toggle rendered
  - Version badge shows FE 9.3.0

Fixture: three rows for TODAY are inserted into test_solar_data.db
(identified by fetch_timestamp='test-toggle-fixture' and removed in a
finally block — the test DB has no data for today otherwise):

  today 08:00  current_power=100  battery_soc=50
  today 09:00  current_power=250  battery_soc=75   (max)
  today 10:00  current_power=42   battery_soc=60   (current / latest)

Usage:
  python3 test_summary_card_toggle.py

Screenshots are saved to frontend/test/screenshots/
"""

import os
import sqlite3
import sys
from datetime import date
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# Add the skill directory to sys.path to allow importing
skill_path = "/home/stoflom/.pi/agent/skills/firefox-testing"
if skill_path not in sys.path:
    sys.path.append(skill_path)

from firefox_tester import FirefoxTester

from test_helpers import TestResult, guard

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "http://localhost:8090"
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "test_solar_data.db"))
SN = "2602111624"
FIXTURE_MARKER = "test-toggle-fixture"
TODAY = date.today().isoformat()
PAST_DAY = "2026-08-01"  # single day with real data in the test DB
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


def insert_fixture_rows() -> None:
    rows = [
        (f"{TODAY} 08:00:00", 100.0, 50.0),
        (f"{TODAY} 09:00:00", 250.0, 75.0),
        (f"{TODAY} 10:00:00", 42.0, 60.0),
    ]
    with sqlite3.connect(DB_PATH) as conn:
        for ts, power, soc in rows:
            conn.execute(
                "INSERT INTO inverter_telemetry"
                " (device_timestamp, fetch_timestamp, inverter_sn, complete, current_power, battery_soc)"
                " VALUES (?, ?, ?, 'Y', ?, ?)",
                (ts, FIXTURE_MARKER, SN, power, soc),
            )
        conn.commit()


def remove_fixture_rows() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM inverter_telemetry WHERE fetch_timestamp = ?", (FIXTURE_MARKER,))
        conn.commit()


def shift_click(tester: FirefoxTester, css: str) -> None:
    el = tester.find_element(By.CSS_SELECTOR, css)
    actions = ActionChains(tester.driver)
    actions.key_down(Keys.SHIFT).click(el).key_up(Keys.SHIFT).perform()


def card_state(tester: FirefoxTester) -> list[dict]:
    """All summary cards: {label, value, ts, toggle, mode, disabled}."""
    return tester.execute_script(
        "return Array.from(document.querySelectorAll('#summary-cards .summary-card')).map(c => {"
        "  const t = c.querySelector('.card-toggle');"
        "  return {"
        "    label: c.querySelector('.label') ? c.querySelector('.label').textContent.trim() : '',"
        "    value: c.querySelector('.value') ? c.querySelector('.value').textContent.trim() : '',"
        "    ts: c.children[c.children.length - 1] ? c.children[c.children.length - 1].textContent.trim() : '',"
        "    toggle: !!t,"
        "    mode: t ? t.dataset.mode : null,"
        "    disabled: t ? t.disabled : null,"
        "  };"
        "});"
    )


def visible(t: FirefoxTester, css: str) -> bool:
    try:
        return t.is_element_visible(By.CSS_SELECTOR, css, timeout=3)
    except Exception:
        return False


def cards_by_label(state: list[dict], label_part: str) -> dict | None:
    for c in state:
        if label_part.lower() in c["label"].lower():
            return c
    return None


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    t = TestResult()

    insert_fixture_rows()
    try:
        with FirefoxTester(headless=True) as tester:
            # ── Test 1: chart view, today — toggles enabled, Max mode ──
            print(f"\n[Test 1] Chart view, today ({TODAY}): toggles enabled, Max values")
            tester.navigate(f"{BASE_URL}/?view=chart&date={TODAY}")
            try:
                tester.wait_for_element(By.CSS_SELECTOR, "#summary-cards.visible .summary-card", timeout=20)
            except Exception:
                pass
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-toggle-today-max.png"))

            state = card_state(tester)
            t.check(len(state) >= 2, f"at least two summary cards (got {len(state)})")
            inv = cards_by_label(state, "Inverter Output")
            soc = cards_by_label(state, "SOC")
            t.check(inv is not None, "Inverter Output Power card present")
            t.check(soc is not None, "SOC card present")

            for name, c, val in [("inverter", inv, "250 W"), ("soc", soc, "75 %")]:
                if c:
                    t.check(c["toggle"], f"{name}: card carries a toggle")
                    t.check(c["toggle"] and c["mode"] == "max", f"{name}: toggle in Max mode (got {c['mode']})")
                    t.check(c["toggle"] and c["disabled"] is False, f"{name}: toggle enabled for today")
                    t.check(c["value"] == val, f"{name}: Max value '{val}' (got '{c['value']}')")
                    t.check(c["label"].startswith("Max"), f"{name}: label starts with 'Max' (got '{c['label']}')")
                    t.check("09:00:00" in c["ts"], f"{name}: Max timestamp at 09:00 (got '{c['ts']}')")

            # ── Test 2: click switches only that card to Latest ──────
            print("\n[Test 2] Click on inverter card → only that card shows Latest")
            # Click the first card's toggle (Inverter Output Power is first default column)
            toggles = tester.find_elements(By.CSS_SELECTOR, "#summary-cards .card-toggle")
            toggles[0].click()
            tester.wait(1)

            state = card_state(tester)
            inv = cards_by_label(state, "Inverter Output")
            soc = cards_by_label(state, "SOC")
            if inv:
                t.check(inv["mode"] == "latest", f"inverter switched to Latest (got {inv['mode']})")
                t.check(inv["label"].startswith("Latest"), f"inverter label 'Latest …' (got '{inv['label']}')")
                t.check(inv["value"] == "42 W", f"inverter Latest value '42 W' (got '{inv['value']}')")
                t.check("10:00:00" in inv["ts"], f"inverter Latest timestamp at 10:00 (got '{inv['ts']}')")
            if soc:
                t.check(soc["mode"] == "max", f"SOC stays in Max mode (got {soc['mode']})")
                t.check(soc["value"] == "75 %", f"SOC still shows Max '75 %' (got '{soc['value']}')")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-toggle-one-current.png"))

            # ── Test 3: Shift+click switches ALL cards ────────────────
            print("\n[Test 3] Shift+click on SOC card → all cards switch to Latest")
            shift_click(tester, "#summary-cards .summary-card:nth-child(2) .card-toggle")
            tester.wait(1)

            state = card_state(tester)
            for name, val, ts in [
                ("inverter", "42 W", "10:00:00"),
                ("soc", "60 %", "10:00:00"),
            ]:
                c = cards_by_label(state, "Inverter Output" if name == "inverter" else "SOC")
                if c:
                    t.check(c["mode"] == "latest", f"{name} switched to Latest by Shift+click (got {c['mode']})")
                    t.check(c["value"] == val, f"{name} Latest value '{val}' (got '{c['value']}')")
                    t.check(ts in c["ts"], f"{name} Latest timestamp at {ts} (got '{c['ts']}')")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-toggle-all-current.png"))

            # Shift+click again → all back to Max
            shift_click(tester, "#summary-cards .summary-card:nth-child(2) .card-toggle")
            tester.wait(1)
            state = card_state(tester)
            all_max = all(c["mode"] == "max" for c in state)
            t.check(all_max, f"all cards back to Max after second Shift+click (got {[c['mode'] for c in state]})")

            # ── Test 4: previous day — toggle disabled, Max ───────────
            print(f"\n[Test 4] Previous day ({PAST_DAY}): toggle disabled, Max values")
            tester.navigate(f"{BASE_URL}/?view=chart&date={PAST_DAY}")
            try:
                tester.wait_for_element(By.CSS_SELECTOR, "#summary-cards.visible .summary-card", timeout=20)
            except Exception:
                pass
            state = card_state(tester)
            t.check(len(state) >= 1, f"summary cards rendered for past day (got {len(state)})")
            if state:
                t.check(all(c["toggle"] for c in state), "toggles rendered on past-day cards")
                t.check(all(c["disabled"] is True for c in state), "all toggles disabled on past day")
                t.check(all(c["mode"] == "max" for c in state), "all cards in Max mode on past day")
                t.check(all(c["label"].startswith("Max") for c in state), "labels show 'Max' on past day")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-toggle-past-disabled.png"))

            # ── Test 5: histogram view, today — no toggle ─────────────
            print(f"\n[Test 5] Histogram view, today ({TODAY}): no toggle")
            tester.navigate(f"{BASE_URL}/?view=histogram&date={TODAY}")
            try:
                tester.wait_for_element(By.CSS_SELECTOR, "#histogram-view.visible", timeout=20)
            except Exception:
                pass
            try:
                toggles = tester.find_elements(By.CSS_SELECTOR, "#summary-cards .card-toggle", timeout=3)
            except Exception:
                toggles = []
            t.check(len(toggles) == 0, f"no card-toggle in histogram view (got {len(toggles)})")

            # ── Test 6: grid view, today — toggle works ───────────────
            print(f"\n[Test 6] Grid view, today ({TODAY}): click switches to Latest")
            tester.navigate(f"{BASE_URL}/?view=grid&date={TODAY}")
            try:
                tester.wait_for_element(By.CSS_SELECTOR, "#summary-cards.visible .summary-card", timeout=20)
            except Exception:
                pass
            state = card_state(tester)
            t.check(all(c["mode"] == "max" for c in state), "grid cards in Max mode (modes are a standing setting; all Max so far)")
            if state:
                toggles = tester.find_elements(By.CSS_SELECTOR, "#summary-cards .card-toggle")
                t.check(toggles[0].get_attribute("disabled") is None, "grid toggle enabled for today")
                toggles[0].click()
                tester.wait(1)
                state = card_state(tester)
                first = state[0]
                t.check(first["mode"] == "latest", f"grid card 1 switched to Latest (got {first['mode']})")
                if "Inverter Output" in first["label"]:
                    t.check(first["value"] == "42 W", f"grid inverter Latest '42 W' (got '{first['value']}')")

            # ── Test 7: version badge ─────────────────────────────────
            print("\n[Test 7] Version badge shows FE 9.3.0")
            badge = tester.find_element(By.ID, "version-badge").text
            t.check("FE 9.3.0" in badge, f"version badge shows 'FE 9.3.0' (got '{badge}')")

    finally:
        remove_fixture_rows()

    # ── Summary ─────────────────────────────────────────────────────
    return t.summary()


if __name__ == "__main__":
    sys.exit(guard(main))
