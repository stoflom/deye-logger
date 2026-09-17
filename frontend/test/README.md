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

All frontend tests run against the **test database `test_solar_data.db`** (in the
project root) — *not* the live `deye_solar_data.db`. Start the backend pointed at
it from the project root (this also builds the frontend):

```bash
cd /home/stoflom/Workspace/deye-logger
bash backend/start.sh -d test_solar_data.db
```

The server defaults to `http://localhost:8090`. Pass `-H` / `-p` to override:

```bash
bash backend/start.sh -p 8090 -d test_solar_data.db
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
| 1 | Histogram controls in title bar | Bin-size select lives inside `.header`; major-view buttons in `.header-top` |
| 2 | Title bar wrapping | Buttons wrap into multiple rows at narrow widths |
| 3 | All view modes render | chart, grid, histogram, histogram-grid all render |
| 4 | Summary cards scaling | Cards scale at all viewports, count is consistent |
| 5 | Card stacking at mobile | Cards stack vertically (full-width) at ≤600px |
| 6 | Single scroll pane | `#content-area` scrolls, panels have `min-height: 300px`, no nested scrollbars |
| 7 | Histogram control visibility | Controls hidden in non-histogram views, visible in histogram views |
| 8 | Day filter selector | Day filter dropdown (All/Sun/Mon/Tue/Wed/Thu/Fri/Sat) exists and works, default is 'All' |
| 9 | Histogram controls in histogram modes | Present in both histogram and histogram-grid views |
| 10 | Single scroll pane structure | `#summary-cards` is a direct child of `#content-area`, scrollable |

### `test_chart_axes.py` — Full-range chart axes (design §15.8, #85, #88)

| # | Test | Description |
|---|------|-------------|
| 1 | Series single-day axis | x-axis is a linear time axis spanning 00:00–24:00 with 5-min tick step |
| 2 | Series 2-day axis | x-axis spans the full 2-day range with 30-min tick step |
| 3 | Series SOC axis | % (SOC) y-axis fixed to 0–100 |
| 4 | Histogram axes | Full 00:00–24:00 bin grid (96 × 15-min bins); SOC axis 0–100 |

### `test_series_raw_points.py` — Series raw data, no smoothing (design §15.8, #88)

| # | Test | Description |
|---|------|-------------|
| 1 | Every point plotted | Per column, dataset point count / min / max equal the raw `/api/data` values (no binning, peaks preserved), points in ascending timestamp order within the day; x-axis still spans the full day |
| 2 | No smoothing | Every dataset has `tension === 0` and `showLine === true` (straight segments) |

### `test_background_refresh.py` — Background database refresh (design §10.3, #89)

Requires the Deye Cloud sync to be **mocked** (no `.env` in the dev environment) — start the server with the mock ingestion script:

```bash
DEYE_LOGGER_SCRIPT="$(pwd)/frontend/test/mock_deye_logger.py" bash backend/start.sh -d test_solar_data.db
```

The mock (`mock_deye_logger.py`) mimics `deye-logger.py`'s interface (exit 0, ~3 s simulated sync via `MOCK_REFRESH_SLEEP`) without touching the database.

| # | Test | Description |
|---|------|-------------|
| 1 | Backend version sanity | Version badge shows `BE 4.4.0` (the `DEYE_LOGGER_SCRIPT`-capable backend) |
| 2 | Background refresh (chart view) | View stays visible, `"refreshing ..."` in the status bar, waiting view NOT shown, only Refresh disabled, other controls enabled; on completion the indicator clears, Refresh re-enables and the view re-renders |
| 3 | Background refresh (histogram view) | Same as above in the histogram view |

### `test_button_states.py` — Button states per view

Verifies button **visibility** (display), **enabled/disabled** (greyed-out), and **text labels** across the six major views per [frontend-design.md §9.3](../frontend-design.md#93-button-specification-table).

| # | Test | Description |
|---|------|-------------|
| 1 | Chart view | All nav controls enabled; CSV/histogram controls hidden; correct button labels |
| 2 | Grid view | All nav controls enabled; CSV visible; correct button labels |
| 3 | Histogram view | Histogram controls visible (bin-size, day-filter); CSV hidden; correct labels |
| 4 | Histogram-grid view | Histogram controls visible; CSV visible; correct labels |
| 5 | Columns select | Only `columnsToggle` ("↻ Load Data") enabled; all others greyed-out |
| 6 | Error view | All controls greyed-out; error `Close` button enabled |
| 7 | Chart↔Grid transition | Button labels and CSV visibility toggle correctly on view-toggle |
| 8 | Chart↔Histogram transition | Histogram controls and button labels toggle correctly |
| 9 | Status bar label | `#view-label` shows correct text (Series, Data Grid, Histogram, Histogram Grid) |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: firefox_tester` | Ensure the skill is at `~/.pi/agent/skills/firefox-testing/` |
| `Connection refused` on localhost:8090 | Start the backend first via `backend/start.sh` |
| Geckodriver errors | The skill uses `webdriver-manager` — ensure internet access for first run |
| Firefox not found | Install Firefox and ensure it is on `PATH` |
