# Frontend Tests

Browser-based UI tests for the Deye Logger Viewer frontend using **Selenium + Firefox (Marionette)**.

## Prerequisites

1. **Firefox** installed and available on `PATH`.
2. **Python 3** with Selenium and webdriver-manager:
   ```bash
   pip install selenium webdriver-manager
   ```
3. **Firefox Marionette Testing Skill** installed at:
   ```
   ~/.pi/agent/skills/firefox-testing/
   ```
   This provides the `FirefoxTester` class (see `SKILL.md` in that directory).

   The skill source code is available on GitHub: <https://github.com/stoflom/pi-skills>.

   The test script auto-discovers it via:
   ```python
   skill_path = "/home/stoflom/.pi/agent/skills/firefox-testing"
   if skill_path not in sys.path:
       sys.path.append(skill_path)
   from firefox_tester import FirefoxTester
   ```

4. **Deno** installed (required by the backend).

## Running the Tests

### 1. Start the application server

From the project root, start the backend (this also builds the frontend):

```bash
cd /home/stoflom/Workspace/deye-logger
bash backend/start.sh
```

The server defaults to `http://localhost:8090`. Pass `-H` / `-p` to override:

```bash
bash backend/start.sh -p 8090 -d /path/to/deye_solar_data.db
```

Leave the server running — the tests need a live instance.

### 2. Run the test suite

```bash
cd frontend/test
python3 test_responsive_display.py
python3 test_button_states.py
```

Screenshots are saved to `frontend/test/screenshots/` (ignored by git).

## What Is Tested

### `test_responsive_display.py` — Layout and rendering

| # | Test | Description |
|---|------|-------------|
| 1 | Histogram controls in title bar | Bin-size select and Split button live inside `.header` |
| 2 | Title bar wrapping | Buttons wrap into multiple rows at narrow widths |
| 3 | All view modes render | chart, grid, histogram, histogram-grid all render |
| 4 | Summary cards scaling | Cards scale at all viewports, count is consistent |
| 5 | Card stacking at mobile | Cards stack vertically (full-width) at ≤600px |
| 6 | Single scroll pane | `#content-area` scrolls, panels have `min-height: 300px`, no nested scrollbars |
| 7 | Histogram control visibility | Controls hidden in non-histogram views, visible in histogram views |
| 8 | Day filter selector | Day filter dropdown (All/Sun/Mon/Tue/Wed/Thu/Fri/Sat) exists and works, default is 'All' |
| 9 | Histogram controls in histogram modes | Present in both histogram and histogram-grid views |
| 10 | Single scroll pane structure | `#summary-cards` is a direct child of `#content-area`, scrollable |

### `test_button_states.py` — Button states per view

Verifies button **visibility** (display), **enabled/disabled** (greyed-out), and **text labels** across the six major views per [frontend-design.md §9.3](../frontend-design.md#93-button-specification-table).

| # | Test | Description |
|---|------|-------------|
| 1 | Chart view | All nav controls enabled; CSV/histogram controls hidden; correct button labels |
| 2 | Grid view | All nav controls enabled; CSV visible; correct button labels |
| 3 | Histogram view | Histogram controls visible (bin-size, day-filter, split); CSV hidden; correct labels |
| 4 | Histogram-grid view | Histogram controls visible; split hidden; CSV visible; correct labels |
| 5 | Columns select | Only `columnsToggle` ("↻ Load Data") enabled; all others greyed-out |
| 6 | Error view | All controls greyed-out; error `Close` button enabled |
| 7 | Chart↔Grid transition | Button labels and CSV visibility toggle correctly on view-toggle |
| 8 | Chart↔Histogram transition | Histogram controls and button labels toggle correctly |
| 9 | Status bar label | `#view-label` shows correct text (Chart, Data Grid, Histogram, Histogram Grid) |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: firefox_tester` | Ensure the skill is at `~/.pi/agent/skills/firefox-testing/` |
| `Connection refused` on localhost:8090 | Start the backend first via `backend/start.sh` |
| Geckodriver errors | The skill uses `webdriver-manager` — ensure internet access for first run |
| Firefox not found | Install Firefox and ensure it is on `PATH` |
