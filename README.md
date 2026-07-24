# DeyeCloud Solar Data Logger

Fetches telemetry data from [DeyeCloud](https://deyecloud.com) and stores it in a local SQLite database. Supports realtime data capture, automatic gap detection/backfill, bulk historical data import, and a browser-based viewer.

## Project Structure

```
deye-logger/
├── deye-cloud/            # Python data-fetching script
│   ├── deye-logger.py     # Main logger script
│   ├── .env               # Credentials (git-ignored)
│   └── .env.example       # Template
├── backend/               # Deno + Express HTTP server
│   ├── main.ts            # Server entry point
│   ├── start.sh           # Build + serve script
│   └── deno.json          # Deno configuration
├── frontend/              # Browser viewer
│   ├── src/               # TypeScript source
│   │   ├── app.ts         # App entry point
│   │   ├── chart.ts       # Chart.js rendering
│   │   ├── columns.ts     # Column selection UI
│   │   ├── data-grid.ts   # AG Grid setup
│   │   ├── histogram-chart.ts
│   │   ├── navigation.ts  # Date navigation
│   │   └── shared.ts      # Shared state, DOM refs, utils
│   ├── public/            # Static files
│   │   ├── index.html     # Viewer HTML
│   │   ├── style.css      # Styles
│   │   ├── favicon.svg
│   │   └── app.js         # Bundled output (git-ignored)
│   └── package.json       # Node dependencies
├── .gitignore
├── deye_solar_data.db     # SQLite database (git-ignored)
└── README.md
```

## Features

- Realtime telemetry polling (45 fields: PV strings 1-3, battery, grid, load, consumption, temperatures, generator)
- Automatic gap detection — finds periods with >3 minute data breaks and backfills from the history API (configurable via `GAP_THRESHOLD_MINUTES`)
- Spurious data detection — identifies rows where `cumulative_consumption` resets to zero after being non-zero (indicative of corrupted API data), or where the API returned an incomplete set of fields (`complete='N'`), with support for consecutive spurious rows
- Spurious data cleanup — removes detected spurious rows from the database
- Bulk historical data import via `--fetch-since` for initial data loads (7-day chunking to stay within API limits)
- SQLite storage with indexed timestamps for efficient queries
- Configuration via `.env` file (credentials and DB path excluded from git)
- Flexible field mapping for both realtime and history API response formats

## Requirements

- Python 3.8+

### Logger only (`deye-cloud/deye-logger.py`)

- `requests`
- `python-dotenv`

### Browser viewer (optional)

- [Deno](https://deno.com/) 2.x+
- Node.js 18+ (with npm) — for the esbuild build step

### Installing Prerequisites (fresh clone)

**Python packages (logger):**
```bash
pip install requests python-dotenv
```

**Deno (viewer only):**
```bash
# Linux / macOS
curl -fsSL https://deno.land/install.sh | sh
# or via package manager
# Debian/Ubuntu:  sudo apt install deno
# Fedora/RHEL/Rocky/Alma:  sudo dnf install deno
# macOS:  brew install deno
# Windows: winget install DenoLand.Deno
```

**Node.js (viewer only):**
```bash
# Debian/Ubuntu:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
# Fedora/RHEL/Rocky/Alma:  sudo dnf install -y nodejs
# macOS:  brew install node
# Windows: winget install OpenJS.NodeJS.LTS
```

**Project dependencies (build tooling, viewer only):**
```bash
cd frontend
npm install
cd ..
```

## Setup

1. **Create the environment file:**

   ```bash
   cp deye-cloud/.env.example deye-cloud/.env
   ```

2. **Edit `deye-cloud/.env`** with your DeyeCloud credentials:

   | Variable | Description |
   |---|---|
   | `DEYE_APP_ID` | Your DeyeCloud developer appId |
   | `DEYE_APP_SECRET` | Your DeyeCloud developer appSecret |
   | `DEYE_EMAIL` | DeyeCloud account email |
   | `DEYE_PASSWORD` | **SHA-256 hash** of your DeyeCloud password |
   | `DEYE_INVERTER_SN` | Your inverter serial number |
   | `DEYE_BASE_URL` | API base URL (defaults to `https://eu1-developer.deyecloud.com`) |
   | `DB_NAME` | Path to SQLite database (relative to script dir; default `../deye_solar_data.db` in project root, or `deye_solar_data.db` in script dir if unset) |

   To compute the password hash:
   ```bash
   echo -n "yourpassword" | sha256sum
   ```

### Script Configuration

The following constants can be modified directly in `deye-cloud/deye-logger.py`:

| Variable | Default | Description |
|---|---|---|
| `GAP_THRESHOLD_MINUTES` | `3` | Minimum gap duration (in minutes) to trigger backfill |

## Usage

### Fetch latest telemetry + backfill gaps (normal operation)

```bash
cd deye-cloud
python deye-logger.py
```

This fetches the most recent telemetry data, saves it to the database, and scans for any time gaps longer than the threshold (default 3 minutes) — automatically backfilling them from the history API. Override the threshold with `-g`/`--gap`:

```bash
python deye-logger.py --gap 5   # only backfill gaps >5 minutes
```

To use a custom database, provide the path with `-db` (overrides `.env DB_NAME` and the default):

```bash
python deye-logger.py -db /custom/path/my_solar_data.db
```

Database path priority: `-db` flag → `.env` `DB_NAME` → fallback `deye_solar_data.db` in the same directory as the script.

### Import historical data (initial setup)

```bash
python deye-logger.py --fetch-since "1 July 2026"
```

Fetches all historical data from the given date up to now. Splits large ranges into 7-day chunks to respect API rate limits. Supports various date formats:

- `YYYY-MM-DD` (e.g., `2026-07-01`)
- `DD Mon YYYY` (e.g., `1 July 2026`)
- `DD MMMM YYYY` (e.g., `1 July 2026`)
- `YYYY/MM/DD` (e.g., `2026/07/01`)

### Find and delete spurious data

The Deye Cloud API sometimes returns incomplete or corrupted data — for example, `cumulative_consumption` resetting to zero after being non-zero, or only a subset of expected fields being returned. The script tracks completeness via a `complete` column (`Y`/`N`). Use these commands to detect and remove spurious records:

```bash
python deye-logger.py --find-spurious
```

Scans the database for spurious records — rows where `cumulative_consumption` is zero but the previous row had a non-zero value, or where `complete='N'` (incomplete API response). Consecutive spurious rows are collected as a group. Results are stored in a `spurious_records` table and displayed with timestamps:

```
Found 12 spurious record(s) in the database.
  5x zero-reset
  7x incomplete-data
  First spurious: 2026-07-15 14:30:00 (zero-reset)
  Last  spurious: 2026-07-15 14:37:00 (incomplete-data)
```

```bash
python deye-logger.py --delete-spurious
```

Removes all spurious records from `inverter_telemetry` using the entries stored in `spurious_records`, then clears the tracking table:

```
Found 12 spurious record(s) in spurious_records table.
Deleting...
Deleted 12 record(s) from the database.
```

The short flags `-fs` and `-ds` are also available.

### Database Schema

| Column | Type | Description |
|---|---|---|
| `device_timestamp` | TEXT (PK) | Inverter timestamp |
| `fetch_timestamp` | TEXT | Local fetch timestamp |
| `inverter_sn` | TEXT | Inverter serial number |
| `complete` | TEXT | `Y` if all expected fields present, `N` if incomplete (`CHECK(complete IN ('Y', 'N'))`) |
| `daily_energy` | REAL | Today's production (kWh) |
| `total_energy` | REAL | Lifetime production (kWh) |
| `current_power` | REAL | Inverter output power (W) |
| `battery_soc` | REAL | Battery state of charge (%) |
| `battery_voltage` | REAL | Battery voltage (V) |
| `battery_current` | REAL | Battery current (A, negative = charging) |
| `grid_power` | REAL | Net grid exchange power (W) |
| `grid_voltage` | REAL | Grid voltage L1-L2 (V) |
| `grid_frequency` | REAL | Grid frequency (Hz) |
| `pv1_voltage` | REAL | PV string 1 voltage (V) |
| `pv1_current` | REAL | PV string 1 current (A) |
| `pv1_power` | REAL | PV string 1 power (W) |
| `pv2_voltage` | REAL | PV string 2 voltage (V) |
| `pv2_current` | REAL | PV string 2 current (A) |
| `pv2_power` | REAL | PV string 2 power (W) |
| `load_power` | REAL | UPS/backup load power (W) |
| `pv3_voltage` | REAL | PV string 3 voltage (V) |
| `pv3_current` | REAL | PV string 3 current (A) |
| `pv3_power` | REAL | PV string 3 power (W) |
| `total_dc_power` | REAL | Total DC input from all PV strings (W) |
| `total_consumption_power` | REAL | Total home consumption (W) |
| `cumulative_consumption` | REAL | Lifetime home consumption (kWh) |
| `daily_consumption` | REAL | Today's home consumption (kWh) |
| `battery_power` | REAL | Battery net power (W, negative = charging) |
| `total_charge_energy` | REAL | Lifetime battery charging (kWh) |
| `total_discharge_energy` | REAL | Lifetime battery discharging (kWh) |
| `daily_charging_energy` | REAL | Today's battery charging (kWh) |
| `daily_discharging_energy` | REAL | Today's battery discharging (kWh) |
| `cumulative_grid_feed_in` | REAL | Lifetime energy sold to grid (kWh) |
| `cumulative_energy_purchased` | REAL | Lifetime energy bought from grid (kWh) |
| `daily_grid_feed_in` | REAL | Today's grid feed-in (kWh) |
| `daily_energy_purchased` | REAL | Today's grid purchase (kWh) |
| `load_voltage` | REAL | UPS/backup load voltage (V) |
| `grid_current` | REAL | Grid current (A) |
| `external_ct_power` | REAL | External CT power measurement (W) |
| `battery_rated_capacity` | REAL | Battery rated capacity (Ah) |
| `battery_temp` | REAL | Battery temperature (°C) |
| `dc_temp` | REAL | DC converter temperature (°C) |
| `ac_temp` | REAL | AC converter temperature (°C) |
| `generator_frequency` | REAL | Generator frequency (Hz) |
| `generator_voltage` | REAL | Generator voltage (V) |
| `total_generator_production` | REAL | Lifetime generator production (kWh) |
| `ac_voltage` | REAL | AC output voltage phase R (V) |
| `ac_current` | REAL | AC output current phase R (A) |
| `rated_power` | REAL | Inverter rated power (W) |

#### `gap_attempts`

| Column | Type | Description |
|---|---|---|
| `gap_start` | TEXT (PK) | Start of the detected gap |
| `gap_end` | TEXT (PK) | End of the detected gap |
| `attempted_at` | TEXT | When the backfill was attempted |
| `records_imported` | INTEGER | Number of records imported (0 = no data available) |

#### `spurious_records`

| Column | Type | Description |
|---|---|---|
| `device_timestamp` | TEXT (PK) | Timestamp of the spurious record |
| `cumulative_consumption` | REAL | The spurious zero value |
| `previous_cumulative_consumption` | REAL | The non-zero value from the previous row |
| `identified_at` | TEXT | When the spurious record was detected |

#### `_schema_migrations`

| Column | Type | Description |
|---|---|---|
| `key` | TEXT (PK) | Migration name (e.g. `telemetry_sorted`, `gap_attempts_cleared`, `spurious_records_cleared`) |
| `done` | INTEGER | Always `1`; row presence indicates the migration has run |

### Deye Cloud API Endpoints Used

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1.0/account/token` | POST | Authentication |
| `/v1.0/device/latest` | POST | Realtime telemetry |
| `/v1.0/device/history` | POST | Historical data (gap backfill & bulk import) |

### Deye API Quirks & Lessons Learned

The Deye Cloud API has several non-obvious behaviours that required workarounds:

**1. Endpoint confusion.**
The history endpoint is `/v1.0/device/history`, not `/v1.0/device/historyRaw`. The latter doesn't exist and returns a 500 with `"invalid param type"`.

**2. Date-based parameters, not timestamps.**
Unlike the realtime endpoint which uses epoch timestamps, the history endpoint uses string date parameters named `startAt` and `endAt` in `YYYY-MM-DD` format. Epoch millis (`startTime`/`endTime`) are rejected with `"invalid param type"`.

**3. Granularity is required.**
A `granularity` integer must be specified:

| Value | Meaning | Date format | Measure points |
|---|---|---|---|
| `1` | Intraday (~1 min intervals) | `startAt`/`endAt` = `YYYY-MM-DD` | Required (max 5) |
| `2` | Daily summary | `startAt`/`endAt` = `YYYY-MM-DD` | Must be null |
| `3` | Monthly summary | `startAt`/`endAt` = `YYYY-MM` | Must be null |
| `4` | Yearly summary | `startAt`/`endAt` = `YYYY` | Must be null |

**4. Max 5 measure points per call.**
The intraday endpoint returns `"list too long"` if more than 5 measure points are requested. The script splits the 45 measure points into 9 batches of 5, then merges results by timestamp.

**5. Measure point names, not numeric IDs.**
The history API uses string measure point names (e.g. `"SOC"`, `"BatteryVoltage"`) obtained from `/v1.0/device/measurePoints`. Numeric IDs (e.g. `"10031059"`) are silently rejected.

**6. Intraday response format.**
The history API returns data grouped by timestamp in a single flat list:

```json
{
  "dataList": [
    {
      "time": "1783288836",
      "itemList": [
        { "key": "SOC", "value": "66", "unit": "%" },
        { "key": "BatteryVoltage", "value": "53.02", "unit": "V" }
      ]
    }
  ]
}
```

The `time` field is a Unix epoch in seconds (not millis). All requested measure points for a given timestamp are bundled into the same `itemList` array.

**7. Bearer token casing.**
Both `Bearer` (upper B) and `bearer` (lower b) work in the `Authorization` header for all endpoints.

**8. ~1440 data point limit per call.**
The history API silently caps responses at about 1440 data points (one day at 1-minute granularity), regardless of the requested date range. Multi-day queries return only the first day's data with no warning. The script works around this by iterating day-by-day, making separate API calls per day per batch of measure points.

## Browser Viewer

A lightweight web viewer lets you browse the SQLite database via a [Deno](https://deno.com/) + [Express](https://expressjs.com/) server that queries a local SQLite database using Node's native `node:sqlite` module.

### Starting the Viewer

**Production build (one-time):**

```bash
bash backend/start.sh
```

Opens `http://localhost:8090` with today's data loaded automatically. The first run will build the frontend via esbuild.

**Development mode (auto-rebuild):**

```bash
cd frontend
npm run dev
```

Watches `src/` for changes and rebuilds `public/app.js` automatically on every `.ts` file save. Useful during development — keep this running in a separate terminal alongside the server.

To force build:

```bash
cd frontend
npm run build
# or from the backend directory:
cd backend
deno task build
```

#### Viewer Options

| Flag | Description | Example |
|---|---|---|
| `-H`, `--host <host>` | Host to bind the server to | `bash backend/start.sh -H 0.0.0.0` |
| `-p`, `--port <port>` | Port to listen on (default: 8090) | `bash backend/start.sh -p 3000` |
| `-d`, `--db <db_path>` | Path to the SQLite database (default: project root) | `bash backend/start.sh -d /custom/path.db` |
| `-h`, `--help` | Show help message | `bash backend/start.sh -h` |

Bind to all interfaces for network access:
```bash
bash backend/start.sh -H 0.0.0.0 -p 8090
```

Or start directly with Deno (skips the build step and auto-kill logic):
```bash
cd backend
deno run -A main.ts --host 0.0.0.0 --port 8090 --db=../deye_solar_data.db
```

> **Note:** `start.sh` uses `lsof` to detect and kill any existing instance on the specified port before starting. If `lsof` is not available on your system, you can use `fuser -k <port>/tcp` as an alternative.

### Features

- **Chart view** (default) — time-series line chart of selected telemetry columns, toggleable
- **Data Grid** — AG Grid with sorting, filtering, column resize, and auto-sizing
- **Histogram view** — time-binned bar chart that aggregates multi-day data into a single average day. Each bar shows the average value of all data points within that time bin across the selected date range. Configurable bin sizes (5/10/15/30/60 minutes). A "Data Grid" button shows the binned averages as a table, and a "Chart" button returns to the raw data line chart. Summary cards display "Max Average" with the bin time of the peak.
- **Date navigation** — ‹/› arrows to step through days, disabled at data range boundaries
- **Date picker** — jump to any day or date range with stored data
- **Column selection** — toggle individual columns on/off (persists in localStorage); "Save as Default" / "Reset Default" buttons to customize the default column set
- **Summary cards** — dynamic max-value cards for all numeric columns
- **CSV export** — export the current grid data as a CSV file
- **Refresh button** — runs `deye-cloud/deye-logger.py` to fetch latest telemetry, then reloads the data
- **Version badge** — displays frontend and backend version numbers in the UI

### Express Routes

| Route | Method | Description |
|---|---|---|
| `/api/columns` | GET | Returns column metadata (name + display label) |
| `/api/dates` | GET | Returns the date range of stored data (`min`/`max` dates) |
| `/api/data` | GET | Query telemetry for a date. Params: `date` (YYYY-MM-DD), `columns` (comma-separated) |
| `/api/data-range` | GET | Query telemetry across a date range. Params: `from`, `to` (YYYY-MM-DD), `columns` (comma-separated) |
| `/api/histogram` | GET | Time-binned averages for histogram view. Params: `from`, `to` (YYYY-MM-DD), `columns` (comma-separated), `binMinutes` (default: 15) |
| `/api/version` | GET | Returns backend version string |
| `/api/refresh` | POST | Runs `deye-cloud/deye-logger.py` to fetch latest data, then reloads the DB |

## Running Periodically to fetch latest data

Use cron for scheduled runs (e.g., every 5 minutes):

```bash
crontab -e
# Add:
*/5 * * * * /usr/bin/python3 /home/<user>/Workspace/deye-logger/deye-cloud/deye-logger.py >> /home/<user>/Workspace/deye-logger/cron.log 2>&1
```
