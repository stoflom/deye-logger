# Deye Cloud — Design Document

**Version:** 2.2

---

## 1. Overview

The Deye Cloud logger is a Python script (`deye-logger.py`) that fetches telemetry data from the [DeyeCloud API](https://deyecloud.com) and stores it in a local SQLite database. It supports three operational modes:

1. **Normal operation** — fetch latest telemetry and auto-backfill time gaps.
2. **Historical bulk import** — `--fetch-since` for initial data loads.
3. **Spurious data management** — `--find-spurious` / `--delete-spurious` to detect and remove corrupted records.

Command-line arguments:

- `--fetch-since <date>` — bulk import from date
- `-g, --gap <minutes>` — min gap to trigger backfill (default `3`)
- `-u, --update` — maintenance pass: refresh data **and** update column metadata, detect new columns, report versions
- `-fs, --find-spurious` — detect spurious records
- `-ds, --delete-spurious` — delete spurious records
- `-m, --meta` — update column metadata only
- `--force` — override lock file
- `-db <path>` — path to SQLite database

Full reference: §8.

## 2. Architecture

```
┌─────────────┐    HTTP POST    ┌───────────────────┐
│ deye-logger ├─────────────────│  DeyeCloud API    │
│  (Python)   │   Bearer token  │  (eu1-developer)  │
└──────┬──────┘                 └───────────────────┘
       │
       │ SQLite3 (local file)
       ▼
┌─────────────────────────────────────────┐
│  SQLite Database                        │
│  - inverter_telemetry                   │
│  - gap_attempts                         │
│  - spurious_records                     │
│  - _schema_migrations                   │
└─────────────────────────────────────────┘
```

### 2.1 Authentication Flow

```
POST /v1.0/account/token  { appSecret, email, password }
Response: { "code": "1000000", "accessToken": "..." }
```

The script authenticates with each run using email + SHA-256 hashed password. The access token is short-lived and not cached.

### 2.2 Data Flow

```
┌──────────────┐
│ get_access_token()
└──────┬───────┘
       │
  ┌──────────┐
  │ Refresh  │  ──→  -u/--update  ──→  --fetch-since  ──→  --find-spurious
  │ (default)│
  └────┬─────┘
       │
  ┌────┴────────────────────┐
  │ fetch_latest_data()      │
  │ parse_device_data()      │
  │ save_records()           │
  │   → inverter_telemetry   │
  │   + telemetry_text       │
  └────────────┬─────────────┘
               │
  ┌────────────┴────────────────────┐
  │ scan_and_fix_time_gaps()        │
  │   - detect gaps > threshold     │
  │   - group by day                │
  │   - fetch_historical_range()    │
  │   - parse_history_response()    │
  │   - save_records()              │
  │   - record_gap_attempt()        │
  └─────────────────────────────────┘
```

## 3. Configuration

### 3.1 Environment Variables (`.env`)

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DEYE_APP_ID` | Yes | — | DeyeCloud developer `appId` |
| `DEYE_APP_SECRET` | Yes | — | DeyeCloud developer `appSecret` |
| `DEYE_EMAIL` | Yes | — | DeyeCloud account email |
| `DEYE_PASSWORD` | Yes | — | **SHA-256 hash** of DeyeCloud password |
| `DEYE_INVERTER_SN` | Yes | — | Inverter serial number |
| `DEYE_BASE_URL` | No | `https://eu1-developer.deyecloud.com` | API base URL |
| `DB_NAME` | No | `deye_solar_data.db` (same dir) | Path to SQLite database |
| `DEYE_SCRIPT_DIR` | No | Project root | Override `SCRIPT_DIR` for testing (defaults to project root) |

### 3.2 Script Constants

| Constant | Default | Description |
|---|---|---|
| `GAP_THRESHOLD_MINUTES` | `3` | Min gap (minutes) to trigger backfill |

### 3.3 CLI Overrides

Database path resolution priority (highest first):

1. `-db <path>` CLI flag
2. `.env` `DB_NAME`
3. `deye_solar_data.db` in script directory

## 4. API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/v1.0/account/token` | POST | Authentication |
| `/v1.0/device/latest` | POST | Realtime telemetry (45 fields) |
| `/v1.0/device/history` | POST | Historical data (gap backfill & bulk import) |

### 4.1 History API Granularity

| Value | Meaning | Date format | Measure points |
| --- | --- | --- | --- |
| `1` | Intraday (~1 min) | `YYYY-MM-DD` | Required (max 5) |
| `2` | Daily summary | `YYYY-MM-DD` | Must be null |
| `3` | Monthly summary | `YYYY-MM` | Must be null |
| `4` | Yearly summary | `YYYY` | Must be null |

### 4.2 Measure Point Batching

45 fields are split into 9 batches of 5 (API limit):

| Batch | Fields |
| --- | --- |
| 1 | `DailyActiveProduction`, `TotalActiveProduction`, `InverterOutputPowerL1L2`, `SOC`, `BatteryVoltage` |
| 2 | `BatteryCurrent`, `TotalGridPower`, `GridVoltageL1L2`, `GridFrequency`, `DCPowerPV2` |
| 3 | `DCVoltagePV1`, `DCCurrentPV1`, `DCPowerPV1`, `DCVoltagePV2`, `DCCurrentPV2` |
| 4 | `UPSLoadPower`, `DCVoltagePV3`, `DCCurrentPV3`, `DCPowerPV3`, `TotalDCInputPower` |
| 5 | `TotalConsumptionPower`, `CumulativeConsumption`, `DailyConsumption`, `BatteryPower`, `TotalChargeEnergy` |
| 6 | `TotalDischargeEnergy`, `DailyChargingEnergy`, `DailyDischargingEnergy`, `CumulativeGridFeedIn`, `CumulativeEnergyPurchased` |
| 7 | `DailyGridFeedIn`, `DailyEnergyPurchased`, `LoadVoltageL1L2`, `GridCurrentL1L2`, `ExternalCTPowerL1L2` |
| 8 | `BatteryRatedCapacity`, `Temperature- Battery`, `DC Temperature`, `AC Temperature`, `RatedPower` |
| 9 | `GeneratorFrequency`, `GenVoltage`, `TotalGeneratorProduction`, `ACVoltageRUA`, `ACCurrentRUA` |

## 5. API Quirks & Workarounds

### 5.1 Endpoint Naming

The history endpoint is `/v1.0/device/history`, **not** `/v1.0/device/historyRaw` (which returns 500).

### 5.2 Parameter Format

- History API uses string dates (`YYYY-MM-DD`) in `startAt`/`endAt` — epoch millis are rejected.
- Realtime API uses epoch timestamps.

### 5.3 Measure Point Limit (5 per call)

The intraday endpoint returns `"list too long"` if more than 5 measure points are requested. The script batches 45 fields into 9 groups of 5, then merges results by timestamp.

### 5.4 1440-Point Silent Cap

The API silently caps responses at ~1440 data points (one day at 1-min granularity). Multi-day queries return only the first day. Workaround: iterate day-by-day in `fetch_historical_range()`.

### 5.5 Measure Point Names

The history API uses string names (e.g. `"SOC"`, `"BatteryVoltage"`), not numeric IDs. Names are retrieved from `/v1.0/device/measurePoints`.

### 5.6 Bearer Token Casing

Both `Bearer` and `bearer` work in the `Authorization` header.

### 5.7 Superset of Fields — Non-Numeric & Unknown Fields

The `/v1.0/device/latest` and `/v1.0/device/history` endpoints return a
**superset** of measure points, not a fixed set. The realtime endpoint has been
observed to return 58 fields (the design originally assumed 45), and the set
changes as Deye adds new measure points.

Some returned fields are **non-numeric strings** — firmware/software version
identifiers — and are not telemetry. Observed examples (as of 2026-09):

| API key | Example value | Meaning |
| --- | --- | --- |
| `MAIN` | `9028-1727` | Main firmware version string |
| `HMI` | `0000-C381` | HMI firmware version string |

The history endpoint returns these metadata fields even when they are not
requested via `measurePoints`.

Because the field set and value types are not guaranteed, the ingestion script
must treat each response as an **untrusted superset**: numeric conversion is
best-effort (see §6.4), non-numeric fields are persisted in `telemetry_text`
(§6.4), and the script must never assume that all values are numeric or that
the field list matches a known map.

## 6. Data Model

### 6.1 Field Mapping

The script maps DeyeCloud API keys to database columns using two dictionaries:

- **`FIELD_MAP`**: DB column → list of possible API key names (fallback chain, used for realtime data).
- **`HISTORY_FIELD_MAP`**: API key → DB column (direct mapping, used for history data).

A record is marked `complete='Y'` when all 45 `EXPECTED_FIELDS` are present, otherwise `complete='N'`.

Numeric conversion is **best-effort** via a `_to_number()` helper: a value that
parses to a float is stored as a float, any other value (empty, `None`, or a
non-numeric string such as `MAIN` = `9028-1727`) resolves to `None` and never
raises. This keeps ingestion robust to the non-numeric and unknown fields
returned by the API (see §5.7 and §6.4).

### 6.2 Key Fields (Spurious Detection)

Fields checked to determine if a response is likely spurious:
`total_energy`, `daily_energy`, `grid_power`, `total_dc_power`, `total_consumption_power`

### 6.3 Database Tables

#### `inverter_telemetry`

| Column | Type | Description |
| --- | --- | --- |
| `device_timestamp` | TEXT (PK) | Inverter timestamp |
| `fetch_timestamp` | TEXT | Local fetch timestamp |
| `inverter_sn` | TEXT | Inverter serial number |
| `complete` | TEXT | `Y` / `N` (CHECK constraint) |
| `daily_energy` | REAL | Today's production (kWh) |
| `total_energy` | REAL | Lifetime production (kWh) |
| `current_power` | REAL | Inverter output power (W) |
| `battery_soc` | REAL | Battery SoC (%) |
| `battery_voltage` | REAL | Battery voltage (V) |
| `battery_current` | REAL | Battery current (A, - = charging) |
| `grid_power` | REAL | Net grid exchange (W) |
| `grid_voltage` | REAL | Grid voltage L1-L2 (V) |
| `grid_frequency` | REAL | Grid frequency (Hz) |
| `pv1_voltage/current/power` | REAL | PV string 1 (V/A/W) |
| `pv2_voltage/current/power` | REAL | PV string 2 (V/A/W) |
| `load_power` | REAL | UPS/backup load (W) |
| `pv3_voltage/current/power` | REAL | PV string 3 (V/A/W) |
| `total_dc_power` | REAL | Total DC input (W) |
| `total_consumption_power` | REAL | Total home consumption (W) |
| `cumulative_consumption` | REAL | Lifetime home consumption (kWh) |
| `daily_consumption` | REAL | Today's consumption (kWh) |
| `battery_power` | REAL | Battery net power (W, - = charging) |
| `total_charge_energy` | REAL | Lifetime charging (kWh) |
| `total_discharge_energy` | REAL | Lifetime discharging (kWh) |
| `daily_charging_energy` | REAL | Today's charging (kWh) |
| `daily_discharging_energy` | REAL | Today's discharging (kWh) |
| `cumulative_grid_feed_in` | REAL | Lifetime energy sold to grid (kWh) |
| `cumulative_energy_purchased` | REAL | Lifetime energy bought from grid (kWh) |
| `daily_grid_feed_in` | REAL | Today's grid feed-in (kWh) |
| `daily_energy_purchased` | REAL | Today's grid purchase (kWh) |
| `load_voltage` | REAL | UPS load voltage (V) |
| `grid_current` | REAL | Grid current (A) |
| `external_ct_power` | REAL | External CT power (W) |
| `battery_rated_capacity` | REAL | Battery rated capacity (Ah) |
| `battery_temp` | REAL | Battery temperature (°C) |
| `dc_temp` | REAL | DC converter temperature (°C) |
| `ac_temp` | REAL | AC converter temperature (°C) |
| `generator_frequency` | REAL | Generator frequency (Hz) |
| `generator_voltage` | REAL | Generator voltage (V) |
| `total_generator_production` | REAL | Lifetime generator production (kWh) |
| `ac_voltage` | REAL | AC output phase R voltage (V) |
| `ac_current` | REAL | AC output phase R current (A) |
| `rated_power` | REAL | Inverter rated power (W) |

Index: `idx_timestamp` on `device_timestamp`, `idx_complete` on `complete`.

#### `telemetry_text`

Captures **only non-numeric** values returned by the Deye Cloud API (e.g.
`MAIN`, `HMI` firmware strings) and any future text fields the script does not
yet know about. Numeric values are never stored here — they already live in
`inverter_telemetry`. One row per `api_key`, updated only when the value
changes.

| Column | Type | Description |
| --- | --- | --- |
| `api_key` | TEXT (PK) | Raw DeyeCloud field code (e.g. `MAIN`, `HMI`) |
| `value` | TEXT | Latest non-numeric value, exactly as returned |
| `updated_at` | TEXT | Timestamp when the value last changed |

#### `gap_attempts`

Tracks which gaps have been attempted for backfill (prevents re-querying).

| Column | Type | Description |
| --- | --- | --- |
| `gap_start` | TEXT (PK) | Gap start timestamp |
| `gap_end` | TEXT (PK) | Gap end timestamp |
| `attempted_at` | TEXT | When the attempt was made |
| `records_imported` | INTEGER | Records imported (0 = no data available) |

#### `spurious_records`

Stores records identified as spurious before deletion.

| Column | Type | Description |
| --- | --- | --- |
| `device_timestamp` | TEXT (PK) | Timestamp of spurious record |
| `cumulative_consumption` | REAL | The spurious zero value |
| `previous_cumulative_consumption` | REAL | Non-zero value from previous row |
| `identified_at` | TEXT | When detection occurred |

#### `column_metadata`

Stores column metadata (names, labels, units, descriptions, API field codes) fetched from the DeyeCloud API during initialization. This table is the source of truth for all column display information served by the backend's `/api/columns` endpoint. The deye-logger script populates this table at startup.

| Column | Type | Description |
| --- | --- | --- |
| `column_name` | TEXT (PK) | Internal database column name (e.g., `daily_energy`) |
| `display_label` | TEXT | Human-readable label with units (e.g., `Daily Energy (kWh)`) |
| `is_numeric` | INTEGER | `1` if the column contains numeric data, `0` otherwise |
| `unit` | TEXT | Unit of measurement (e.g., `kWh`, `V`, `W`, `%`), empty string if none |
| `api_field_code` | TEXT | Original DeyeCloud API field code (e.g., `DailyActiveProduction`) |
| `description` | TEXT | Optional human-readable description of the column |
| `sort_order` | INTEGER | Display order in UI (0 = first) |

Known migrations: `telemetry_sorted`, `gap_attempts_cleared`, `spurious_records_cleared`, `column_metadata`, `telemetry_text`.

### 6.4 Text Field Capture (`telemetry_text`)

Non-numeric fields returned by the Deye Cloud API — e.g. firmware strings
(`MAIN`, `HMI`) and any future text fields the script does not yet know about
— are persisted in the `telemetry_text` table (§6.3).

- **Non-numeric only**: values that parse as a float belong in
  `inverter_telemetry` and are **not** duplicated into `telemetry_text`.
- **One row per `api_key`** — the latest value and the time it last changed.
- **Change-driven**: a row is inserted (or replaced) only when the value for a
  key **differs** from the previously stored value; unchanged values are
  skipped.
- Numeric time-series display and queries are unaffected — they remain driven
  by `inverter_telemetry` / `column_metadata`.

This keeps the script robust to API changes: a new or non-numeric field is
captured in `telemetry_text` rather than dropped or causing the fetch to fail,
without duplicating the numeric data already in `inverter_telemetry`.

## 7. Operational Modes

### 7.1 Refresh Cycle (default)

The default run (no flags) is a **fast data-only refresh**. This is the path the
backend invokes on every frontend refresh click (`POST /api/refresh` runs
`python3 deye-logger.py` with no arguments), so it must stay fast. It brings
only the **time-series data** up to date and does **not** touch column metadata
or perform any "check for changes" work.

```bash
python deye-logger.py [-g MINUTES] [-db PATH] [--force]
```

1. Check for lock file (`deye_refresh.lock`).
   - If present and PID alive → exit with error (use `--force` to override).
   - If present and PID dead → log warning, remove stale lock, continue.
   - If absent → create lock file with PID and start timestamp.
2. Fetch latest telemetry via `/v1.0/device/latest`.
3. Save to database — known numeric columns to `inverter_telemetry` (`INSERT OR REPLACE`), and **non-numeric** fields to `telemetry_text`, only when the value for a key changed (§6.4).
4. Scan for time gaps > threshold.
5. For each gap, query history API (grouped by day) and backfill.
6. Mark each gap as attempted (even if no data returned).

**The refresh cycle does not** call `/v1.0/device/measurePoints`, refresh
`column_metadata`, or detect new columns / version changes — that work is
deferred to the update pass (§7.2) to keep refresh fast.

### 7.2 Update Maintenance Pass (`-u` / `--update`)

A heavier, less-frequent maintenance pass that does everything the refresh
cycle does **plus** synchronization with the DeyeCloud API's current schema and
version. Run manually or on a schedule (e.g. weekly), or when the API is known
to have changed.

```bash
python deye-logger.py -u        # or --update
```

The update pass performs, in order:

1. **Data refresh** — the normal latest + gap-backfill refresh (§7.1).
2. **Column metadata refresh** — fetch `/v1.0/device/measurePoints` and
   upsert the `column_metadata` table (see §9).
3. **New-column detection** — compare the returned field codes against the known
   field map (`HISTORY_FIELD_MAP`). Any field code not mapped to a known DB
   column is logged as a new/unknown field. No data is lost: every such field is
   already captured in `telemetry_text` on each refresh when its value is
   non-numeric and changed (§6.4); the update pass merely surfaces them so they
   can be promoted to a known column if desired.
4. **Version check** — report the observed API/protocol/firmware identifiers
   (e.g. `ProtocolVersion`, `MAIN`, `HMI`) so changes over time are visible.

`-m` / `--meta` remains as a metadata-only shortcut (step 2 above) for
backward compatibility; `-u` / `--update` is the comprehensive maintenance pass.

### 7.3 Historical Bulk Import

```bash
python deye-logger.py --fetch-since "1 July 2026"
```

Splits the range into 7-day chunks (API rate limit). Each chunk queries day-by-day, batch-by-batch. Duplicate detection is handled by `INSERT OR IGNORE` via the `device_timestamp` primary key.

### 7.4 Lock File Guard

A lock file (`deye_refresh.lock`) in the `deye-cloud/` directory prevents concurrent executions of the script, whether invoked directly (cron, manual) or via the backend API (`POST /api/refresh`). Lock management is **exclusively** handled by the Python script — the backend does not participate in lock file operations.

**Lock file format** (JSON):

```json
{
  "pid": 12345,
  "started_at": "2026-01-15T10:30:00"
}
```

**Behavior:**

| Scenario | Action |
| --- | --- |
| Lock file absent | Create lock file, proceed |
| Lock file present, PID alive | Print error, exit 1 |
| Lock file present, PID dead | Log warning, remove stale lock, proceed |
| `--force` flag | Remove lock file (regardless of PID), log warning, proceed |

**Cleanup:** The lock file is deleted on normal exit, error exit, and signal handlers (SIGTERM, SIGINT).

### 7.5 Spurious Data Detection

```bash
python deye-logger.py --find-spurious
```

Two detection rules:

1. **Zero-reset**: `cumulative_consumption` is 0 but the previous row had a non-zero value.
2. **Incomplete data**: `complete='N'` (API returned fewer than 45 fields).

Consecutive spurious rows are grouped. Results stored in `spurious_records`.

```bash
python deye-logger.py --delete-spurious
```

Deletes all entries from `inverter_telemetry` where `device_timestamp` exists in `spurious_records`, then clears the tracking table.

## 8. Command-Line Interface

```
usage: deye-logger.py [-h] [--fetch-since FETCH_SINCE] [-g GAP]
                      [-u] [-fs] [-ds] [-m] [--force] [-db DB]
```

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--fetch-since` | str | — | Bulk import from date (7-day chunking) |
| `-g, --gap` | int | `3` | Min gap minutes to trigger backfill |
| `-u, --update` | flag | — | Maintenance pass: refresh data **and** update column metadata, detect new columns, and report API/firmware version (§7.2) |
| `-fs, --find-spurious` | flag | — | Detect spurious records |
| `-ds, --delete-spurious` | flag | — | Delete spurious records |
| `-m, --meta` | flag | — | Update column metadata only (subset of `-u`; the metadata step of §7.2) |
| `--force` | flag | — | Override lock file (clear stale/active lock) |
| `-db` | str | script dir | Path to SQLite database |

**Date formats supported** for `--fetch-since`:

- `YYYY-MM-DD`
- `DD Mon YYYY` / `DD MMMM YYYY`
- `YYYY/MM/DD`
- `DD-MM-YYYY`
- `MM/DD/YYYY`

## 9. Column Metadata Management

The deye-logger script fetches column metadata from the DeyeCloud API and stores it in the `column_metadata` table.

### 9.1 Metadata Fetch

The script calls the DeyeCloud API's measure points endpoint to retrieve the full list of available telemetry columns:

```
GET /v1.0/device/measurePoints
Authorization: Bearer {accessToken}
```

The response contains field codes and names for all available measure points. The script maps these to database columns using the field mapping information and stores the result in `column_metadata`.

### 9.2 Initialization

If the `column_metadata` table does not exist, the script creates it automatically (using `CREATE TABLE IF NOT EXISTS`).

### 9.3 Metadata Update

Column metadata is **not updated on every refresh**. It is refreshed only during
the **update** maintenance pass (§7.2):

```bash
python deye-logger.py --update     # full maintenance pass (data + metadata + new-column + version)
python deye-logger.py --meta       # metadata only (backward-compatible shortcut)
```

The `refresh` cycle (§7.1) never touches `column_metadata`, keeping it fast. On
an update, known columns are upserted (INSERT OR REPLACE) so previously-known
columns are preserved even if the API returns fewer fields, and new/unknown API
field codes are surfaced for review (see §7.2 step 3).

### 9.4 Field Mapping

The script uses `FIELD_MAP` (DB column → API key names) and `HISTORY_FIELD_MAP` (API key → DB column) to map DeyeCloud API field codes to internal database column names. These mappings are used for:

1. **Data ingestion**: Translating API responses into the correct DB columns.
2. **Metadata population**: Determining the `column_name` for each `api_field_code` returned by the measure points API.

## 10. Schema Evolution

The script handles migration automatically in `init_database()`:

- **Column additions**: `ALTER TABLE ... ADD COLUMN` with `sqlite3.OperationalError` suppression.
- **Column type conversion**: `complete` column migration from REAL to TEXT (CREATE NEW → INSERT → DROP → RENAME).
- **Table reordering**: `telemetry_sorted` migration for timestamp-ordered data.
- **Stale data cleanup**: `gap_attempts_cleared` and `spurious_records_cleared` one-time migrations.
- **Table replacement**: `telemetry_text` one-time migration — drops the old `telemetry_raw` table (its data duplicated `inverter_telemetry` and was disposable) and creates `telemetry_text` (#93).

## 11. Dependencies

- Python 3.8+
- `requests`
- `python-dotenv`

## 12. Testing

### 12.1 Lock File Guard Tests

Tests are located in `deye-cloud/test/test_lock_guard.sh`. Run with:

```bash
bash deye-cloud/test/test_lock_guard.sh
```

| Test | Description | Expected |
| --- | --- | --- |
| 1 | Lock acquisition on fresh start | Lock file created with valid JSON (`pid`, `started_at`) |
| 2 | Concurrent execution rejection | Second invocation exits 1 with error message |
| 3 | Stale lock detection | Dead PID detected, lock cleaned, proceeds |
| 4 | `--force` flag override | Lock file removed regardless of PID state |
| 5 | Signal cleanup (SIGTERM) | Lock file removed when process receives SIGTERM |
| 6 | Corrupt lock file handling | Invalid JSON detected, lock cleaned, proceeds |

### 12.2 Test Script Structure

The test script (`test_lock_guard.sh`) uses temporary Python helper scripts that import the lock management functions from `deye-logger.py` without executing the full data ingestion pipeline. Each test:

1. Sets up the scenario (creates/destroys lock file as needed)
2. Runs the test invocation
3. Verifies the expected outcome
4. Reports pass/fail
5. Cleans up temporary files

**Note:** Test 7 (Backend lock file format) was removed — the backend no longer participates in lock file management.

### 12.3 Robustness & Raw-Capture Tests

Tests are located in `deye-cloud/test/test_data_capture.py`. Run with:

```bash
python3 deye-cloud/test/test_data_capture.py
```

The suite loads the ingestion functions from `deye-logger.py` (without running
the pipeline) and verifies, against a temporary in-memory database, that:

| Test | Description | Expected |
| --- | --- | --- |
| 1 | `_to_number()` conversion | numeric strings/ints → float; non-numeric (`9028-1727`), empty and `None` → `None`; never raises |
| 2 | `parse_device_data()` with non-numeric fields | a realtime `dataList` containing `MAIN`/`HMI` parses without error; known numeric columns are correct; non-numeric values are preserved in the record's raw capture |
| 3 | `parse_history_response()` with non-numeric fields | a history response containing `MAIN`/`HMI` parses without error and drops unmapped fields |
| 4 | `save_records()` text capture | saving a record writes the known columns to `inverter_telemetry` and stores **only non-numeric** fields (e.g. `MAIN`/`HMI`) into `telemetry_text`; re-saving an unchanged value updates nothing, a changed value replaces the row |

These tests are self-contained (dummy credentials, temp database) and do not
read or write the real `.env` or production database.

## 13. Change Management

This section tracks changes to the design document itself. Every modification to this document must be recorded below.

| Version | Date | Section Changed | Description |
|---------|------|----------------|-------------|
| 1.0.0 | 2025-07-28 | All sections | Initial design document — API integration, data model, operational modes |
| 1.1.0 | 2026-07-30 | §6.3, §8, §9 | Column metadata no longer hardcoded — new `column_metadata` table populated from DeyeCloud API; deye-logger fetches measure points on each run; metadata serves as source of truth for backend `/api/columns` |
| 1.2.0 | 2026-07-30 | §8, §9 | Metadata update is opt-in via `-m/--meta` flag — no longer fetched on every run, reducing unnecessary API calls |
| 1.3.0 | 2026-07-30 | §7, §8 | Lock-file guard — `deye_refresh.lock` prevents concurrent executions; `--force` flag overrides stale/active locks; cleanup on exit and signals |
| 1.4 | 2026-07-30 | §3.1, §7.1, §7.2–§7.4, §12 | Design doc corrections: version format (major.minor only), §7.1 step numbering, §7.2–§7.4 section numbering, §3.1 add DEYE_SCRIPT_DIR env var, §12 test count to 7 scenarios |
| 1.5 | 2026-08-15 | §7.3, §12 | Remove backend lock file guard — lock management delegated entirely to Python script; removed Test 7 (Backend lock file format) from test table; clarified that backend does not participate in lock operations |
| 2.0 | 2026-09-17 | §2, §5.7, §6.1, §6.3, §6.4, §7.1, §7.2, §8, §9 | New features: (1) full raw data capture — new `telemetry_raw` table mirrors every API field (incl. non-numeric `MAIN`/`HMI` firmware strings and unknown fields); best-effort numeric conversion via `_to_number()`; ingestion no longer assumes all values are numeric; document the API's non-fixed superset of fields (§5.7); clearer error logging names the failing stage/endpoint (#91). (2) refresh/update split — the default run is a fast data-only **refresh** (no metadata); new `-u/--update` maintenance pass refreshes column metadata, detects new columns, and reports API/firmware version (§7.2) (#92) |
| 2.2 | 2026-09-17 | §2, §5.7, §6.3, §6.4, §7.1, §7.2, §10, §12 | `telemetry_raw` → `telemetry_text` (#93): only **non-numeric** values are stored (numeric data is no longer duplicated from `inverter_telemetry`); one row per `api_key`, updated only when the value changes; one-time `telemetry_text` migration drops the old `telemetry_raw` data |
| 2.1 | 2026-09-17 | §1 | Overview now lists all command-line arguments accepted by `deye-logger.py` (full reference remains §8) |
