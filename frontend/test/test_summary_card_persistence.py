#!/usr/bin/env python3
"""
Test script to verify the summary cards Max/Latest toggle persistence
(frontend-design.md v9.2, §17.3 — issue #101).

Covers:
  - Toggle selection survives a page reload (core acceptance criterion)
  - Toggle selection survives repeated reloads (browser-restart equivalent —
    same profile, localStorage kept)
  - Modes are a standing setting (v9.3, #102): ‹/› and date-picker
    navigation keep them — leaving today and coming back restores the
    Latest cards, on every path and after a reload
  - No stored value → default behaviour unchanged (all Max)
  - Corrupt / invalid stored values → default behaviour unchanged (all Max)
  - Version badge shows FE 9.3.0

Fixture: three rows for TODAY are inserted into test_solar_data.db
(identified by fetch_timestamp='test-card-persist-fixture' and removed in a
finally block — the test DB has no data for today otherwise):

  today 08:00  current_power=100  battery_soc=50
  today 09:00  current_power=250  battery_soc=75   (max)
  today 10:00  current_power=42   battery_soc=60   (latest)

Usage:
  python3 test_summary_card_persistence.py

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
FIXTURE_MARKER = "test-card-persist-fixture"
TODAY = date.today().isoformat()
PAST_DAY = "2026-08-01"  # single day with real data in the test DB
STORAGE_KEY = "deye_summary_card_modes"
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


def card_mode(state: list[dict], label_part: str) -> str | None:
    for c in state:
        if label_part.lower() in c["label"].lower():
            return c["mode"]
    return None


def load_today(tester: FirefoxTester, view: str = "chart") -> list[dict]:
    """Navigate (re)load today's raw-data view and wait for the cards."""
    tester.navigate(f"{BASE_URL}/?view={view}&date={TODAY}")
    try:
        tester.wait_for_element(By.CSS_SELECTOR, "#summary-cards.visible .summary-card", timeout=20)
    except Exception:
        pass
    tester.wait(1)
    return card_state(tester)


def set_storage(tester: FirefoxTester, raw: str | None) -> None:
    """Set (or remove) the persisted card-modes value directly."""
    if raw is None:
        tester.execute_script(f"localStorage.removeItem('{STORAGE_KEY}');")
    else:
        tester.execute_script(
            "localStorage.setItem(arguments[0], arguments[1]);", STORAGE_KEY, raw
        )


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    t = TestResult()

    insert_fixture_rows()
    try:
        with FirefoxTester(headless=True) as tester:
            # ── Test 1: fresh profile, no stored value → default (Max) ──
            print(f"\n[Test 1] No stored value → default behaviour (today {TODAY})")
            state = load_today(tester)
            t.check(len(state) >= 2, f"at least two summary cards (got {len(state)})")
            t.check(all(c["mode"] == "max" for c in state), "no stored value → all cards Max")
            t.check(all(c["disabled"] is False for c in state), "toggles enabled for today")
            stored = tester.execute_script(f"return localStorage.getItem('{STORAGE_KEY}');")
            t.check(stored is None, f"nothing stored before any interaction (got '{stored}')")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-persist-default.png"))

            # ── Test 2: click → Latest, survives page reload ───────────
            print("\n[Test 2] Click inverter card → Latest; survives reload")
            toggles = tester.find_elements(By.CSS_SELECTOR, "#summary-cards .card-toggle")
            toggles[0].click()
            tester.wait(1)
            state = card_state(tester)
            inv = card_mode(state, "Inverter Output")
            t.check(inv == "latest", f"inverter card switched to Latest (got {inv})")
            stored = tester.execute_script(f"return localStorage.getItem('{STORAGE_KEY}');") or ""
            t.check("latest" in stored, f"mode written to localStorage (got '{stored}')")

            state = load_today(tester)
            inv = card_mode(state, "Inverter Output")
            t.check(inv == "latest", f"inverter card STILL Latest after reload (got {inv})")
            soc = card_mode(state, "SOC")
            t.check(soc == "max", f"SOC card untouched, still Max (got {soc})")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-persist-reload.png"))

            # ── Test 3: survives a second reload (restart equivalent) ──
            print("\n[Test 3] Second reload keeps the stored mode")
            state = load_today(tester)
            inv = card_mode(state, "Inverter Output")
            t.check(inv == "latest", f"inverter card still Latest after 2nd reload (got {inv})")

            # ── Test 4: ‹/› navigation keeps the modes (v9.3, #102) ─────
            print("\n[Test 4] All cards Latest; ‹ then › back to today keeps them")
            # Shift+click any card currently in Max mode → all cards Latest
            el = tester.find_element(By.CSS_SELECTOR, "#summary-cards .summary-card:nth-child(2) .card-toggle")
            actions = ActionChains(tester.driver)
            actions.key_down(Keys.SHIFT).click(el).key_up(Keys.SHIFT).perform()
            tester.wait(1)
            state = card_state(tester)
            t.check(all(c["mode"] == "latest" for c in state),
                    f"all cards Latest after Shift+click (got {[c['mode'] for c in state]})")

            # ‹ (previous day — 2026-10-04 has no data, cards hidden)
            tester.find_element(By.ID, "prev-day").click()
            tester.wait(2)
            stored = tester.execute_script(f"return localStorage.getItem('{STORAGE_KEY}');") or ""
            t.check("latest" in stored, f"stored modes untouched by ‹ (got '{stored}')")

            # › (next day — back to today): the Latest cards must reappear
            tester.find_element(By.ID, "next-day").click()
            tester.wait(2)
            state = card_state(tester)
            t.check(all(c["mode"] == "latest" for c in state),
                    f"back to today via ›: cards still Latest (got {[c['mode'] for c in state]})")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-persist-prevnext.png"))

            # ── Test 5: date-picker navigation keeps the modes ──────────
            print("\n[Test 5] Date picker to a past day, Today button back — modes kept")
            tester.execute_script(
                "const el = document.getElementById('date-from'); el.value = arguments[0];"
                " el.dispatchEvent(new Event('change', {bubbles: true}));",
                PAST_DAY,
            )
            tester.execute_script(
                "const el = document.getElementById('date-to'); el.value = arguments[0];"
                " el.dispatchEvent(new Event('change', {bubbles: true}));",
                PAST_DAY,
            )
            tester.wait(2)
            state = card_state(tester)
            t.check(all(c["disabled"] is True for c in state), "toggles disabled on past day")
            t.check(all(c["label"].startswith("Max") for c in state), "cards display Max on past day")

            tester.find_element(By.ID, "today-btn").click()
            tester.wait(2)
            state = card_state(tester)
            t.check(all(c["mode"] == "latest" for c in state),
                    f"back to today via Today button: cards still Latest (got {[c['mode'] for c in state]})")

            state = load_today(tester)  # reload after all the navigation
            t.check(all(c["mode"] == "latest" for c in state),
                    f"reload after navigation: still all Latest (got {[c['mode'] for c in state]})")
            tester.screenshot(os.path.join(SCREENSHOT_DIR, "cards-persist-datepicker.png"))

            # ── Test 6: corrupt stored value → default, app unaffected ──
            print("\n[Test 6] Corrupt stored value → default behaviour")
            set_storage(tester, "this-is-not-json")
            state = load_today(tester)
            t.check(len(state) >= 2, f"cards still render with corrupt storage (got {len(state)})")
            t.check(all(c["mode"] == "max" for c in state), "corrupt value → all cards Max")

            # ── Test 7: invalid mode values → ignored ──────────────────
            print("\n[Test 7] Invalid mode values in stored object → ignored")
            set_storage(tester, '{"current_power": "bogus", "battery_soc": "latest"}')
            state = load_today(tester)
            t.check(card_mode(state, "Inverter Output") == "max", "invalid 'bogus' value → Max")
            t.check(card_mode(state, "SOC") == "latest", "valid 'latest' value for SOC honoured")

            # ── Test 8: explicit remove → default (acceptance criterion) ─
            print("\n[Test 8] No stored value (removed) → default behaviour unchanged")
            set_storage(tester, None)
            state = load_today(tester)
            t.check(all(c["mode"] == "max" for c in state), "no stored value → all cards Max")

            # ── Test 9: version badge ──────────────────────────────────
            print("\n[Test 9] Version badge shows FE 9.3.0")
            badge = tester.find_element(By.ID, "version-badge").text
            t.check("FE 9.3.0" in badge, f"version badge shows 'FE 9.3.0' (got '{badge}')")

    finally:
        remove_fixture_rows()

    # ── Summary ─────────────────────────────────────────────────────
    return t.summary()


if __name__ == "__main__":
    sys.exit(guard(main))
