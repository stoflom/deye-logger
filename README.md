# DeyeCloud Solar Data Logger

Fetches telemetry data from [DeyeCloud](https://deyecloud.com) and stores it in a local SQLite database. Supports realtime data capture, automatic gap detection/backfill, bulk historical data import, and a browser-based viewer.

## Features

- Realtime telemetry polling (45 fields: PV strings 1-3, battery, grid, load, consumption, temperatures, generator)
- Automatic gap detection — finds periods with >3 minute data breaks and backfills from the history API (configurable via `GAP_THRESHOLD_MINUTES`)
- Gap tracking — stores attempted backfills in a `gap_attempts` table to avoid retrying unhelpful gaps
- Bulk historical data import via `--fetch-since` for initial data loads (7-day chunking to stay within API limits)
- SQLite storage with indexed timestamps for efficient queries
- Configuration via `.env` file (credentials and DB path excluded from git)
- Flexible field mapping for both realtime and history API response formats

## Requirements

- Python 3.8+
- `requests`
- `python-dotenv`

Install with:

```bash
pip install requests python-dotenv
```

## Setup

1. **Create the environment file:**

   ```bash
   cp .env.example .env
   ```

2. **Edit `.env`** with your DeyeCloud credentials:

   | Variable | Description |
   |---|---|
   | `DEYE_APP_ID` | Your DeyeCloud developer appId |
   | `DEYE_APP_SECRET` | Your DeyeCloud developer appSecret |
   | `DEYE_EMAIL` | DeyeCloud account email |
   | `DEYE_PASSWORD` | **SHA-256 hash** of your DeyeCloud password |
   | `DEYE_INVERTER_SN` | Your inverter serial number |
   | `DEYE_BASE_URL` | API base URL (defaults to `https://eu1-developer.deyecloud.com`) |
   | `DB_NAME` | Path to SQLite database (defaults to `./deye_solar_data.db`) |

   To compute the password hash:
   ```bash
   echo -n "yourpassword" | sha256sum
   ```

3. **Install dependencies:**

   ```bash
   pip install requests python-dotenv
   ```

### Script Configuration

The following constants can be modified directly in `deye-logger.py`:

| Variable | Default | Description |
|---|---|---|
| `GAP_THRESHOLD_MINUTES` | `3` | Minimum gap duration (in minutes) to trigger backfill |

## Usage

### Fetch latest telemetry + backfill gaps (normal operation)

```bash
python deye-logger.py
```

This fetches the most recent telemetry data, saves it to the database, and scans for any time gaps longer than the threshold (default 3 minutes) — automatically backfilling them from the history API. Override the threshold with `-g`/`--gap`:

```bash
python deye-logger.py --gap 5   # only backfill gaps >5 minutes
```

### Import historical data (initial setup)

```bash
python deye-logger.py --fetch-since "1 July 2026"
```

Fetches all historical data from the given date up to now. Splits large ranges into 7-day chunks to respect API rate limits. Supports various date formats:

- `YYYY-MM-DD` (e.g., `2026-07-01`)
- `DD Mon YYYY` (e.g., `1 July 2026`)
- `DD MMMM YYYY` (e.g., `1 July 2026`)
- `YYYY/MM/DD` (e.g., `2026/07/01`)

### Database Schema

| Column | Type | Description |
|---|---|---|
| `device_timestamp` | TEXT (PK) | Inverter timestamp |
| `fetch_timestamp` | TEXT | Local fetch timestamp |
| `inverter_sn` | TEXT | Inverter serial number |
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

### API Endpoints Used

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

A lightweight web viewer lets you browse the SQLite database via a [Deno](https://deno.com/) + [Express](https://expressjs.com/) server that queries a local SQLite database using [sql.js](https://sql.js.org/) (SQLite compiled to WebAssembly).

### Starting the Viewer

```bash
./start.sh
```

Opens `http://localhost:8090` with today's data loaded automatically.

### Features

- **Date picker** — navigate to any day with stored data (dates outside available range are blocked)
- **Column selection** — toggle individual columns on/off (selection persists in localStorage)
- **Refresh button** — runs `deye-logger.py` to fetch latest telemetry, then reloads the data
- **Horizontal scrolling** — for wide column selections

### Express Routes

| Route | Method | Description |
|---|---|---|
| `/api/columns` | GET | Returns column metadata (name + display label) |
| `/api/dates` | GET | Returns the date range of stored data (`min`/`max` dates) |
| `/api/data` | GET | Query telemetry for a date. Params: `date` (YYYY-MM-DD), `columns` (comma-separated) |
| `/api/refresh` | POST | Runs `deye-logger.py` to fetch latest data, then reloads the DB |

### Requirements

- [Deno](https://deno.com/) 2.x+
- Node.js/npm (for esbuild build step)

```bash
npm install
```

## Running Periodically

Use cron for scheduled runs (e.g., every 5 minutes):

```bash
crontab -e
# Add:
*/5 * * * * /usr/bin/python3 /home/<user>/Workspace/deye-logger/deye-logger.py >> /home/<user>/Workspace/deye-logger/cron.log 2>&1
```

## File Structure

```
deye-logger/
├── deye-logger.py     # Main data-fetching script
├── start.sh           # Build + serve browser viewer
├── main.ts            # Deno HTTP server for viewer
├── src/app.ts         # Browser-side viewer (TypeScript)
├── public/
│   ├── index.html     # Viewer HTML + CSS
│   └── app.js         # Bundled viewer (generated, git-ignored)
├── .env               # Credentials (git-ignored)
├── .env.example       # Template for .env
├── .gitignore         # Excludes *.db, .env, IDE files, etc.
├── deno.json          # Deno configuration
├── package.json       # Node/npm dependencies (esbuild, sql.js)
├── README.md
└── deye_solar_data.db # SQLite database (created on first run, git-ignored)
```
