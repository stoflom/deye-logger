# Deye Cloud — Design Document

**Version:** 1.0.0

---

## 1. Overview

The Deye Cloud logger is a Python script (`deye-logger.py`) that fetches telemetry data from the [DeyeCloud API](https://deyecloud.com) and stores it in a local SQLite database. It supports three operational modes:

1. **Normal operation** — fetch latest telemetry and auto-backfill time gaps.
2. **Historical bulk import** — `--fetch-since` for initial data loads.
3. **Spurious data management** — `--find-spurious` / `--delete-spurious` to detect and remove corrupted records.

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
  ┌────┴─────┐
  │  Normal  │  ──→  --fetch-since  ──→  --find-spurious
  │  mode    │
  └────┬─────┘
       │
  ┌────┴────────────────────┐
  │ fetch_latest_data()     │
  │ parse_device_data()     │
  │ save_records()          │
  └────────────┬────────────┘
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
|---|---|---|---|
| `DEYE_APP_ID` | Yes | — | DeyeCloud developer `appId` |
| `DEYE_APP_SECRET` | Yes | — | DeyeCloud developer `appSecret` |
| `DEYE_EMAIL` | Yes | — | DeyeCloud account email |
| `DEYE_PASSWORD` | Yes | — | **SHA-256 hash** of DeyeCloud password |
| `DEYE_INVERTER_SN` | Yes | — | Inverter serial number |
| `DEYE_BASE_URL` | No | `https://eu1-developer.deyecloud.com` | API base URL |
| `DB_NAME` | No | `deye_solar_data.db` (same dir) | Path to SQLite database |

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
|---|---|---|
| `/v1.0/account/token` | POST | Authentication |
| `/v1.0/device/latest` | POST | Realtime telemetry (45 fields) |
| `/v1.0/device/history` | POST | Historical data (gap backfill & bulk import) |

### 4.1 History API Granularity

| Value | Meaning | Date format | Measure points |
|---|---|---|---|
| `1` | Intraday (~1 min) | `YYYY-MM-DD` | Required (max 5) |
| `2` | Daily summary | `YYYY-MM-DD` | Must be null |
| `3` | Monthly summary | `YYYY-MM` | Must be null |
| `4` | Yearly summary | `YYYY` | Must be null |

### 4.2 Measure Point Batching

45 fields are split into 9 batches of 5 (API limit):

| Batch | Fields |
|---|---|
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

## 6. Data Model

### 6.1 Field Mapping

The script maps DeyeCloud API keys to database columns using two dictionaries:

- **`FIELD_MAP`**: DB column → list of possible API key names (fallback chain, used for realtime data).
- **`HISTORY_FIELD_MAP`**: API key → DB column (direct mapping, used for history data).

A record is marked `complete='Y'` when all 45 `EXPECTED_FIELDS` are present, otherwise `complete='N'`.

### 6.2 Key Fields (Spurious Detection)

Fields checked to determine if a response is likely spurious:
`total_energy`, `daily_energy`, `grid_power`, `total_dc_power`, `total_consumption_power`

### 6.3 Database Tables

#### `inverter_telemetry`

| Column | Type | Description |
|---|---|---|
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

#### `gap_attempts`

Tracks which gaps have been attempted for backfill (prevents re-querying).

| Column | Type | Description |
|---|---|---|
| `gap_start` | TEXT (PK) | Gap start timestamp |
| `gap_end` | TEXT (PK) | Gap end timestamp |
| `attempted_at` | TEXT | When the attempt was made |
| `records_imported` | INTEGER | Records imported (0 = no data available) |

#### `spurious_records`

Stores records identified as spurious before deletion.

| Column | Type | Description |
|---|---|---|
| `device_timestamp` | TEXT (PK) | Timestamp of spurious record |
| `cumulative_consumption` | REAL | The spurious zero value |
| `previous_cumulative_consumption` | REAL | Non-zero value from previous row |
| `identified_at` | TEXT | When detection occurred |

#### `_schema_migrations`

One-time migration tracking.

| Column | Type | Description |
|---|---|---|
| `key` | TEXT (PK) | Migration name |
| `done` | INTEGER | Always `1`; row presence = migration applied |

Known migrations: `telemetry_sorted`, `gap_attempts_cleared`, `spurious_records_cleared`.

## 7. Operational Modes

### 7.1 Normal Operation

```bash
python deye-logger.py [-g MINUTES] [-db PATH]
```

1. Fetch latest telemetry via `/v1.0/device/latest`.
2. Save to database (`INSERT OR REPLACE`).
3. Scan for time gaps > threshold.
4. For each gap, query history API (grouped by day) and backfill.
5. Mark each gap as attempted (even if no data returned).

### 7.2 Historical Bulk Import

```bash
python deye-logger.py --fetch-since "1 July 2026"
```

Splits the range into 7-day chunks (API rate limit). Each chunk queries day-by-day, batch-by-batch. Duplicate detection is handled by `INSERT OR IGNORE` via the `device_timestamp` primary key.

### 7.3 Spurious Data Detection

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
                      [-fs] [-ds] [-db DB]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--fetch-since` | str | — | Bulk import from date (7-day chunking) |
| `-g, --gap` | int | `3` | Min gap minutes to trigger backfill |
| `-fs, --find-spurious` | flag | — | Detect spurious records |
| `-ds, --delete-spurious` | flag | — | Delete spurious records |
| `-db` | str | script dir | Path to SQLite database |

**Date formats supported** for `--fetch-since`:
- `YYYY-MM-DD`
- `DD Mon YYYY` / `DD MMMM YYYY`
- `YYYY/MM/DD`
- `DD-MM-YYYY`
- `MM/DD/YYYY`

## 9. Schema Evolution

The script handles migration automatically in `init_database()`:

- **Column additions**: `ALTER TABLE ... ADD COLUMN` with `sqlite3.OperationalError` suppression.
- **Column type conversion**: `complete` column migration from REAL to TEXT (CREATE NEW → INSERT → DROP → RENAME).
- **Table reordering**: `telemetry_sorted` migration for timestamp-ordered data.
- **Stale data cleanup**: `gap_attempts_cleared` and `spurious_records_cleared` one-time migrations.

## 10. Dependencies

- Python 3.8+
- `requests`
- `python-dotenv`

## 11. Change Management

This section tracks changes to the design document itself. Every modification to this document must be recorded below.

| Version | Date | Section Changed | Description |
|---------|------|----------------|-------------|
| 1.0.0 | 2025-07-28 | All sections | Initial design document — API integration, data model, operational modes |
