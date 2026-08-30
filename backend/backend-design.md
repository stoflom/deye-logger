# Backend Design Document — Deye Logger Viewer

> **Status:** v4.2
> **Scope:** Deno + Express server, SQLite (read-only), REST API for inverter telemetry data
> **Language:** TypeScript (via Deno with npm: packages)
> **Runtime:** Deno with `node:sqlite`, Express.js

> **Software Versioning scheme:** Backend version is `major.minor.subminor`.
>
> - **major** — major new features, architectural changes, number must agree with this document major version
> - **minor** — design changes to implement new features or fix design issues, number must agree with this document minor version
> - **subminor** — bug fixes requiring no design changes

---

## 1. Architecture Overview

The backend is a lightweight HTTP server built with **Deno** and **Express.js** that serves a single purpose: read inverter telemetry data from a **SQLite database** and expose it through a REST API consumed by the frontend single-page application. The SQLite database is opened in **read-only mode** — all data ingestion is handled by the separate Python script (`deye-cloud/deye-logger.py`).

```
┌──────────────┐       ┌──────────────────┐       ┌─────────────────────┐
│   Frontend   │─────▶│  Deno + Express  │─────▶│   SQLite Database   │
│  (SPA in     │◀─────│  HTTP Server     │◀─────│  (read-only)        │
│   public/)   │       └──────────────────┘       └─────────────────────┘
└──────────────┘       │  static file serving  │
                       │  /api/* REST endpoints│
                       └───────────────────────┘
                              │
                              │ POST /api/refresh
                              ▼
                       ┌──────────────────┐
                       │ Python Script    │
                       │ deye-logger.py   │
                       │ (Deye Cloud API) │
                       └──────────────────┘
```

### 1.1 Source Files

| File | Responsibility |
| ------ | ---------------- |
| `main.ts` | Application entry point, Express routes, SQLite queries, static file serving |
| `deno.json` | Deno configuration, task definitions (dev, build) |
| `start.sh` | Startup script — builds frontend, resolves DB path, launches server |

### 1.2 Configuration

The server is configured via command-line arguments (no environment variables required for the server itself):

| Flag | Default | Description |
| ------ | --------- | ------------- |
| `--host <host>` | `localhost` | Host to bind to |
| `--port <port>` | `8090` | Port to listen on |
| `--db <db_path>` | *(required)* | Path to the SQLite database file |
| `--help` | — | Show usage information |

The `start.sh` wrapper script auto-detects the project root and resolves the database path to `../deye_solar_data.db` if not specified.

### 1.3 Static File Serving

The backend serves two static directories from the frontend project:

| Path | Served From |
|------|-------------|
| `/` (root) | `../frontend/public/` |
| `/node_modules` | `../frontend/node_modules/` |

This allows the server to serve the complete frontend SPA without a separate web server.

### 1.4 Column Labels

Column metadata (names, display labels, units, numeric flag, sort order) is stored in the `column_metadata` table in the SQLite database and populated by the deye-logger Python script from the DeyeCloud API. No column information is hardcoded in the backend.

The `column_metadata` table schema:

| Column | Type | Description |
| --- | --- | --- |
| `column_name` | TEXT (PK) | Internal database column name |
| `display_label` | TEXT | Human-readable label with units |
| `is_numeric` | INTEGER | `1` if numeric, `0` if metadata/text |
| `unit` | TEXT | Unit of measurement (e.g., `kWh`, `V`, `W`) |
| `api_field_code` | TEXT | Original DeyeCloud API field code |
| `description` | TEXT | Optional description |
| `sort_order` | INTEGER | Display order |

The backend reads this table to serve the `/api/columns` endpoint. The `parseColumnsParam()` function validates incoming column requests against the column names stored in this table (not against a hardcoded list). Numeric columns are identified by the `is_numeric` flag.

### 1.5 Database

The SQLite database (`deye_solar_data.db`) is opened in **read-only mode**. The server creates a prepared statement cache on first query. The database is re-opened after a refresh operation (`POST /api/refresh`) to pick up newly imported data.

The backend only reads the `inverter_telemetry` table (primary key on `device_timestamp` TEXT, indexed). Other tables (`gap_attempts`, `spurious_records`, `_schema_migrations`) exist in the same database file but are created and managed exclusively by the Python data ingestion script — see [deye-cloud-design.md](../deye-cloud/deye-cloud-design.md).

---

## 2. API Endpoints

All API endpoints respond with **JSON** and are prefixed with `/api/`.

### 2.1 `GET /api/columns`

Returns the list of all available telemetry columns with their human-readable labels. Data is read from the `column_metadata` table in the SQLite database, which is populated by the deye-logger Python script from the DeyeCloud API.

**Request:**

```
GET /api/columns
```

**Response (200 OK):**

```json
[
  { "name": "device_timestamp", "label": "Timestamp" },
  { "name": "daily_energy", "label": "Daily Energy (kWh)" },
  { "name": "battery_soc", "label": "Battery SOC (%)" },
  ...
]
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Internal column name (matches DB column) |
| `label` | string | Human-readable label with units |

---

### 2.2 `GET /api/version`

Returns the backend server version.

**Request:**

```
GET /api/version
```

**Response (200 OK):**

```json
{ "version": "2.0.0" }
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Semantic version of the backend (major.minor.subminor) |

---

### 2.3 `GET /api/dates`

Returns the minimum and maximum timestamp range available in the database. Useful for the frontend to populate date picker boundaries.

**Request:**

```
GET /api/dates
```

**Response (200 OK):**

```json
{
  "min": "2025-01-01",
  "max": "2025-07-27"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `min` | string | Earliest available date (YYYY-MM-DD), empty string if no data |
| `max` | string | Latest available date (YYYY-MM-DD), empty string if no data |

---

### 2.4 `GET /api/data`

Fetches raw telemetry rows for a **single date**. The client selects which columns to include.

**Request:**

```
GET /api/data?date=2025-07-27&columns=daily_energy,battery_soc,current_power,battery_voltage
```

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `date` | Yes | Single date in YYYY-MM-DD format |
| `columns` | Yes | Comma-separated list of column keys. Only columns matching known keys are included. `device_timestamp` is automatically prepended if any valid column is requested. |

**Validation:**

- If `date` or `columns` is missing → `400 Bad Request`
- If no valid columns are requested (none match known keys) → `400 Bad Request`

**Response (200 OK):**

```json
{
  "rows": [
    {
      "device_timestamp": "2025-07-27 00:00:00",
      "daily_energy": 12.5,
      "battery_soc": 75.0,
      "current_power": 3200.0,
      "battery_voltage": 52.1
    },
    {
      "device_timestamp": "2025-07-27 00:01:00",
      ...
    }
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `rows` | array | Array of row objects, each containing only the requested columns plus `device_timestamp`. Ordered by `device_timestamp` ascending. |

**Error Response:**

```json
{ "error": "Error message" }
```

---

### 2.5 `GET /api/data-range`

Fetches raw telemetry rows across a **date range**. The client selects which columns to include.

**Request:**

```
GET /api/data-range?from=2025-07-20&to=2025-07-27&columns=daily_energy,battery_soc,current_power
```

**Query Parameters:**

| Parameter | Required | Description |
| ----------- | ---------- | ------------- |
| `from` | Yes | Start date in YYYY-MM-DD format (inclusive) |
| `to` | Yes | End date in YYYY-MM-DD format (inclusive) |
| `columns` | Yes | Comma-separated list of column keys. Only columns matching known keys are included. `device_timestamp` is automatically prepended if any valid column is requested. |

**Validation:**

- If any of `from`, `to`, or `columns` is missing → `400 Bad Request`
- If no valid columns are requested → `400 Bad Request`

**Response (200 OK):**

```json
{
  "rows": [
    { "device_timestamp": "2025-07-20 00:00:00", "daily_energy": 10.2, "battery_soc": 50.0 },
    { "device_timestamp": "2025-07-20 00:05:00", "daily_energy": 10.3, "battery_soc": 51.0 },
    ...
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `rows` | array | Array of row objects, each containing only the requested columns plus `device_timestamp`. Ordered by `device_timestamp` ascending. |

**Error Response:**

```json
{ "error": "Error message" }
```

---

### 2.6 `GET /api/histogram`

Computes time-binned averages of telemetry data across a date range. Designed for the histogram chart view. The results are pre-aggregated: each bin contains the average, minimum and maximum of each numeric column, so the client can display the value range (spread) per bin alongside the mean.

The response **always contains the full 00:00–24:00 bin grid** (1440/binMinutes bins) — rows from multiple days are binned together by time-of-day — so the chart x-axis always spans the whole day. Bins with no data for a column carry `null` in `data`/`min`/`max` (v4.1, #85).

**Request:**

```
GET /api/histogram?from=2025-07-27&to=2025-07-27&columns=daily_energy,battery_soc,current_power,battery_voltage&binMinutes=15
```

**Query Parameters:**

| Parameter | Required | Description |
| ----------- | ---------- | ------------- |
| `from` | Yes | Start date in YYYY-MM-DD format (inclusive) |
| `to` | Yes | End date in YYYY-MM-DD format (inclusive) |
| `columns` | Yes | Comma-separated list of column keys. Only columns matching known keys are included. `device_timestamp` is automatically prepended if any valid column is requested. |
| `binMinutes` | No | Bin size in minutes. Default: `15`. Values: any positive integer (commonly 5, 10, 15, 30, 60). |
| `dayFilter` | No | Day-of-week filter. Default: `all`. Values: `all`, `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat`. When set to a specific day, only rows matching that day of week are included in the histogram bins. |

**Validation:**

- If any of `from`, `to`, or `columns` is missing → `400 Bad Request`
- If no valid columns are requested → `400 Bad Request`
- If `dayFilter` is provided but not one of `all`, `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat` → treated as `all` (ignored)

**Response (200 OK):**

```json
{
  "labels": ["00:00", "00:15", "00:30", "00:45", "01:00", ...],
  "datasets": [
    {
      "label": "Daily Energy (kWh)",
      "data": [10.2, 10.5, 10.8, 11.0, 11.3, ...],
      "min": [9.8, 10.1, 10.4, 10.6, 10.9, ...],
      "max": [10.7, 10.9, 11.2, 11.4, 11.8, ...],
      "unit": "kWh"
    },
    {
      "label": "Battery SOC (%)",
      "data": [50.0, 52.1, 54.3, 55.0, 56.2, ...],
      "min": [49.2, 51.0, 53.5, 54.1, 55.4, ...],
      "max": [50.9, 53.0, 55.2, 55.8, 57.1, ...],
      "unit": "%"
    }
  ],
  "maxValues": {
    "Daily Energy (kWh)": { "value": 15.2, "timestamp": "14:30" },
    "Battery SOC (%)": { "value": 85.0, "timestamp": "18:45" }
  }
}
```

**Response Fields:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `labels` | string[] | Time labels for each bin in `HH:MM` format (e.g., `["00:00", "00:15", "00:30"]`) |
| `datasets` | object[] | One dataset per numeric column (metadata columns like `device_timestamp`, `inverter_sn`, `fetch_timestamp` are excluded). Each dataset contains: |
| `datasets[].label` | string | Human-readable column label (from `column_metadata.display_label`) |
| `datasets[].data` | (number \| null)[] | Averaged values for each bin of the full 00:00–24:00 grid. `null` for bins with no data for that column (rendered as gaps). |
| `datasets[].min` | (number \| null)[] | Minimum value for each bin (parallel to `data`); `null` for empty bins. Shows the low end of the bin's value range. |
| `datasets[].max` | (number \| null)[] | Maximum value for each bin (parallel to `data`); `null` for empty bins. Shows the high end of the bin's value range. |
| `datasets[].unit` | string | Unit extracted from the column metadata (`column_metadata.unit`). Returns `""` if no unit. |
| `maxValues` | object | Map of column label → `{ value: number, timestamp: string }` for peak display in summary cards. Only includes columns that had numeric data. |

**Empty Response:**
If no rows match the query (or no numeric columns are found), returns:

```json
{ "labels": [], "datasets": [], "maxValues": {} }
```

---

### 2.7 `GET /api/stats`

Computes per-column statistics across a date range. Designed for the frontend Stats view: one result object per selected numeric column. All calculations (mean, extremes, high/low durations) are done **entirely in the backend** — the frontend only renders the returned values.

**Request:**

```
GET /api/stats?from=2025-07-20&to=2025-07-27&columns=daily_energy,battery_soc,current_power&dayFilter=all&highCutoff=95&lowCutoff=5
```

**Query Parameters:**

| Parameter | Required | Description |
| ----------- | ---------- | ------------- |
| `from` | Yes | Start date in YYYY-MM-DD format (inclusive) |
| `to` | Yes | End date in YYYY-MM-DD format (inclusive) |
| `columns` | Yes | Comma-separated list of column keys. Only columns matching known keys are included. `device_timestamp` is automatically prepended if any valid column is requested. |
| `dayFilter` | No | Day-of-week filter. Default: `all`. Values: `all`, `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat`. When set, only rows falling on that day of week participate in **all** statistics. Same semantics as `/api/histogram`. Invalid values are treated as `all`. |
| `highCutoff` | No | Cutoff for the "high" threshold. Default: `95`. Allowed values: `50`, `75`, `90`, `95`, `99`. For ordinary units the high threshold is computed from the **observed range**: `max − (1 − highCutoff/100) × range` — the threshold sits `(100 − highCutoff)%` of the full range below the observed maximum (see §2.7 "Range-based thresholds"). For **percentage-unit columns** (`unit === "%"`, e.g. Battery SOC) the selected cutoff value itself is used as the threshold, expressed in percent (see §2.7 "Percentage-unit columns"). Invalid values fall back to the default. |
| `lowCutoff` | No | Cutoff for the "low" threshold. Default: `5`. Allowed values: `1`, `5`, `10`, `25`, `50`. For ordinary units the low threshold is `min + (lowCutoff/100) × range` — the threshold sits `lowCutoff%` of the full range above the observed minimum. For percentage-unit columns the selected cutoff value itself is used as the threshold, expressed in percent. Invalid values fall back to the default. |

**Range-based thresholds** (ordinary units): the data is often non-normally distributed and non-negative, so `mean ± z·σ` is a poor basis for "high/low" thresholds (#87). Instead, both thresholds are inset inward from the respective extreme of the **observed range** over the whole selected range:

    range = max − min

- high threshold = `max − (1 − highCutoff/100) × range`
- low threshold = `min + (lowCutoff/100) × range`

Example (cutoffs `95`/`5`, max `100`, min `20`, range `80`): high threshold `100 − 0.05 × 80 = 96`, low threshold `20 + 0.05 × 80 = 24` — i.e. time spent above `96` and below `24`.

**Validation:**

- If any of `from`, `to`, or `columns` is missing → `400 Bad Request`
- If no valid columns are requested → `400 Bad Request`
- Invalid `dayFilter` / `highCutoff` / `lowCutoff` values → silently treated as defaults

**Response (200 OK):**

```json
{
  "stats": [
    {
      "column": "current_power",
      "label": "Grid Power (W)",
      "unit": "W",
      "count": 2016,
      "mean": 123.45,
      "stdDev": 678.90,
      "max": { "value": 5120.0, "timestamp": "2025-07-22 13:30:00" },
      "min": { "value": -310.0, "timestamp": "2025-07-20 01:05:00" },
      "high": { "cutoff": 95, "threshold": 4848.5, "avgDailyMinutes": 42.5, "method": "range" },
      "low":  { "cutoff": 5,  "threshold": -38.5, "avgDailyMinutes": 6.0, "method": "range" }
    },
    {
      "column": "battery_soc",
      "label": "Battery SOC (%)",
      "unit": "%",
      "count": 2016,
      "mean": 81.2,
      "stdDev": 7.4,
      "max": { "value": 100.0, "timestamp": "2025-07-23 09:00:00" },
      "min": { "value": 58.0, "timestamp": "2025-07-21 22:15:00" },
      "high": { "cutoff": 95, "threshold": 95, "avgDailyMinutes": 30.0, "method": "cutoff" },
      "low":  { "cutoff": 5,  "threshold": 5,  "avgDailyMinutes": 15.0, "method": "cutoff" }
    }
  ]
}
```

The first entry shows the range-based thresholds for an ordinary unit (max `5120`, min `−310`, range `5430`): high `5120 − 0.05 × 5430 = 4848.5`, low `−310 + 0.05 × 5430 = −38.5`, with `"method": "range"`. Note the second entry: `battery_soc` is a percentage-unit column, so the thresholds are the selected cutoff values themselves, in percent (high cutoff `95` → threshold `95`, i.e. 95%; low cutoff `5` → threshold `5`, i.e. 5%), with `"method": "cutoff"` — not the range-based formula.

**Response Fields:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `stats` | object[] | One entry per selected **numeric** column that has at least one non-null sample in the range. Metadata/text columns are excluded. Order follows the order of the requested `columns` parameter. |
| `stats[].column` | string | Internal column name |
| `stats[].label` | string | Human-readable label (`column_metadata.display_label`) |
| `stats[].unit` | string | Unit from `column_metadata.unit`; `""` if none |
| `stats[].count` | number | Number of non-null samples included |
| `stats[].mean` | number | Arithmetic mean of all samples in the range |
| `stats[].stdDev` | number | Population standard deviation: `sqrt(Σ(x − mean)² / n)`. `0` when `count < 2` |
| `stats[].max` | object | `{ value, timestamp }` — maximum value and the **first occurrence** (earliest timestamp) at which it is observed |
| `stats[].min` | object | `{ value, timestamp }` — minimum value and the **first occurrence** (earliest timestamp) at which it is observed |
| `stats[].high` | object | `{ cutoff, threshold, avgDailyMinutes, method }` — the cutoff used, the computed high threshold, the average per-day duration (minutes) the value spent **strictly above** the threshold (see §5.4), and the method: `"range"` (ordinary units — `max − (1 − highCutoff/100) × range`) or `"cutoff"` (the selected cutoff value used directly as the threshold, in percent, for percentage-unit columns) |
| `stats[].low` | object | Same as `high` but **strictly below** the low threshold |

**Empty Response:**
If no data exists or no selected numeric column has samples, returns:

```json
{ "stats": [] }
```

**Edge cases:**

- `count < 2`: `stdDev = 0`, `range = 0`, both thresholds equal `max = min`, durations are `0`.

**Percentage-unit columns** (`unit === "%"` in `column_metadata`, e.g. Battery SOC): the range-based formula is also unsuitable for bounded percentages — the observed range is an arbitrary slice of 0–100%, so insetting it would be meaningless. For these columns the threshold is the **selected cutoff value itself, in percent** (`"method": "cutoff"`): a high cutoff of `95` means the value is compared against `95%` (i.e. minutes the value was above 95%), and a low cutoff of `5` means it is compared against `5%` (minutes below 5%). This is *not* a data percentile — it is the absolute limit the user selected, so the threshold is independent of the sampled values. The high/low *duration* semantics (strictly beyond threshold, consecutive-pair rule, day split) are unchanged — only the threshold value differs.
- A calendar day with samples but none on the relevant side of a threshold contributes `0` minutes but **is counted** in the average denominator ("average per day with data").
- When `dayFilter` is active, per-day grouping is still by calendar day; only matching weekdays contribute rows.

---

### 2.8 `POST /api/refresh`

Triggers the Python data ingestion script (`deye-cloud/deye-logger.py`) to fetch the latest telemetry data from the Deye Cloud API and import it into the SQLite database. After success, the server re-opens the database to pick up new data.

**Request:**

```
POST /api/refresh
```

**Response (200 OK):**

```json
{
  "success": true,
  "code": 0,
  "output": "Importing data...\nDone.",
  "error": ""
}
```

**Response Fields:**

| Field | Type | Description |
| ------- | ------ | ------------- |
| `success` | boolean | Whether the Python script exited with code 0 |
| `code` | number | Exit code of the Python script |
| `output` | string | stdout from the Python script |
| `error` | string | stderr from the Python script |

**Error Response:**

```json
{ "error": "Exception message" }
```

---

## 3. Error Handling

All endpoints follow a consistent error response pattern:

| Status Code | Meaning |
|-------------|---------|
| `400` | Missing or invalid query parameters |
| `500` | Server/database error |

Error responses are always:

```json
{ "error": "Human-readable error message" }
```

---

## 4. Column Filtering Logic

The `parseColumnsParam` function validates incoming column requests:

1. Splits the comma-separated `columns` query parameter.
2. Trims whitespace and filters empty strings.
3. Keeps only columns that exist in the `column_metadata` table (column names from the database).
4. Automatically prepends `device_timestamp` to the list if any valid column was requested (ensures timestamps are always present).
5. Returns the validated list; empty list → 400 error.

---

## 5. Data Fetching Flow

### 5.1 Single-Date Queries (`/api/data`)

```
Client → GET /api/data?date=YYYY-MM-DD&columns=...
           ↓
       Parse columns (validate + prepend timestamp)
           ↓
       Build SQL: SELECT "col1", "col2" FROM inverter_telemetry
                  WHERE device_timestamp >= 'YYYY-MM-DD 00:00:00'
                    AND device_timestamp <= 'YYYY-MM-DD 23:59:59'
                  ORDER BY device_timestamp ASC
           ↓
       Return { rows: [...] }
```

### 5.2 Range Queries (`/api/data-range`)

```
Client → GET /api/data-range?from=YYYY-MM-DD&to=YYYY-MM-DD&columns=...
           ↓
       Parse columns (validate + prepend timestamp)
           ↓
       Build SQL: SELECT "col1", "col2" FROM inverter_telemetry
                  WHERE device_timestamp >= 'YYYY-MM-DD 00:00:00'
                    AND device_timestamp <= 'YYYY-MM-DD 23:59:59'
                  ORDER BY device_timestamp ASC
           ↓
       Return { rows: [...] }
```

### 5.3 Histogram Queries (`/api/histogram`) (`/api/histogram`)

```
Client → GET /api/histogram?from=YYYY-MM-DD&to=YYYY-MM-DD&columns=...&binMinutes=N&dayFilter=X
           ↓
       Parse columns, validate against column_metadata table
           ↓
       Parse dayFilter (default: "all")
           ↓
       Query all rows in range (same SQL as data-range)
           ↓
       If dayFilter != "all", filter rows to matching day-of-week only
           ↓
       Group rows into time bins (floor timestamps to bin boundary)
           ↓
       Build the full 00:00–24:00 bin grid (1440/binMinutes bins);
       bins with no rows carry null (v4.1, #85)
           ↓
       Compute per-bin average, min and max for each numeric column
           ↓
       Retrieve labels and units from column_metadata table
           ↓
       Compute per-column max values (value + timestamp)
           ↓
       Return { labels, datasets, maxValues }
```

**Day-of-week filtering logic:**

- `dayFilter=all` (default): no filtering, all rows included (current behavior).
- `dayFilter=mon` (or any other day): only rows whose `device_timestamp` falls on that day of week are included.
- Day mapping: `sun=0`, `mon=1`, `tue=2`, `wed=3`, `thu=4`, `fri=5`, `sat=6` (JavaScript `Date.getDay()` convention).
- Filtering is applied **after** the SQL range query, before binning. This means the date range still controls the overall window, but only matching days contribute data to the bins.

### 5.4 Stats Queries (`/api/stats`)

```
Client → GET /api/stats?from=YYYY-MM-DD&to=YYYY-MM-DD&columns=...&dayFilter=X&highCutoff=P&lowCutoff=Q
           ↓
       Parse columns (validate against column_metadata, prepend device_timestamp)
           ↓
       Parse dayFilter (default: "all"), highCutoff (default: 95), lowCutoff (default: 5)
           ↓
       Query all rows in range (same SQL as data-range)
           ↓
       If dayFilter != "all", keep only rows on that day of week
           ↓
       For each selected numeric column (in request order):
           collect non-null samples ordered by device_timestamp
           ├─ mean, population stdDev
           ├─ max / min value + earliest timestamp at which each is first observed
           ├─ range = max − min
           ├─ highThreshold = (unit === "%") ? highCutoff   (the selected cutoff, in %)
           │                                 : max − (1 − highCutoff/100) × range
           ├─ lowThreshold  = (unit === "%") ? lowCutoff    (the selected cutoff, in %)
           │                                : min + (lowCutoff/100) × range
           ├─ per calendar day with samples, duration on a side =
           │     Σ (t[i+1] − t[i]) over consecutive sample pairs where
           │     BOTH samples are strictly beyond that threshold
           ├─ avgDailyMinutes = (Σ per-day durations) / (days with ≥1 sample), in minutes
           └─ retrieve label + unit from column_metadata
           ↓
       Return { stats: [...] } (columns with zero samples omitted)
```

**Duration semantics:**

- Time is measured between consecutive samples; an interval counts as "above" (or "below") only when **both** bounding samples are strictly beyond the threshold. This makes the result deterministic and independent of sampling rate, with a small (≤ 1 sample interval) under-count at episode boundaries.
- `avgDailyMinutes` is averaged over days that have at least one sample for that column; days without any qualifying samples contribute `0` but remain in the denominator.
- Null/missing values are skipped — they break continuity (the interval straddling a gap is not counted).

---

## 6. Startup Sequence

1. Parse command-line arguments (`--host`, `--port`, `--db`).
2. Open SQLite database in read-only mode (`DB_PATH` is required).
3. Serve static files from frontend directories.
4. Register all API routes.
5. Start listening on the configured host and port.

---

## 7. Task Definitions (`deno.json`)

| Task | Command | Description |
|------|---------|-------------|
| `dev` | `deno run -A main.ts` | Run development server |
| `build` | `deno run -A npm:esbuild ../frontend/src/app.ts --bundle --outfile=../frontend/public/app.js --format=esm --target=es2020` | Build frontend (called by `start.sh`) |

---

## 8. Testing

### 8.1 Lock File Guard Tests

The lock file guard is tested by `deye-cloud/test/test_lock_guard.sh` (Python side). The backend delegates lock management entirely to the Python script — no backend-side lock checks exist.

| Test | Description |
| --- | --- |
| 1 | Lock acquisition on fresh start — lock file created with valid JSON |
| 2 | Concurrent execution rejection — second invocation exits 1 |
| 3 | Stale lock detection — dead PID detected, lock cleaned |
| 4 | `--force` flag override — lock removed regardless of PID |
| 5 | Signal cleanup (SIGTERM) — lock removed on signal |
| 6 | Corrupt lock file handling — invalid JSON cleaned |
| 7 | Lock file format — correct JSON structure (`pid`, `started_at`) |

### 8.2 Manual Testing

Test the refresh endpoint:

```bash
# Start backend
cd backend && deno run -A main.ts --db ../deye_solar_data.db &

# Trigger refresh
curl -X POST http://localhost:8090/api/refresh
# → { "success": true, "code": 0, "output": "...", "error": "" }

# Verify lock file is managed by Python script
ls -la ../deye-cloud/deye_refresh.lock
```

---

## 9. Change Management

This section tracks changes to the design document itself. Every modification to this document must be recorded below.

| Version | Date | Section Changed | Description |
|---------|------|----------------|-------------|
| 1.2 | 2025-07-28 | §1.4, §1.5, §2.6, §5.3 | Initial — API endpoints, column labels, histogram flow |
| 1.3 | 2025-07-28 | §2.6, §5.3 | Backend stripped of display fields (color, yAxisID, position, palette) from `/api/histogram` — backend only serves `label`, `data`, `unit`; frontend computes display fields locally (color palette, axis grouping, axis position) |
| 2.0 | 2025-07-30 | §2.2, §2.6, §5.3, §8 | Day-of-week filter for histogram — new `dayFilter` query parameter on `/api/histogram`, version bumped to 2.0.0 |
| 2.1 | 2025-07-30 | §2.6 | Remove display fields (color, yAxisID, position) from histogram endpoint response to match frontend v1.6 contract — backend only serves raw data + unit; version bumped to 2.0.1 |
| 2.2 | 2026-07-30 | §1.4, §2.1, §2.6, §4, §5.3 | Column labels no longer hardcoded — backend reads column metadata from `column_metadata` table populated by deye-logger from DeyeCloud API; histogram units from database; column filtering validates against database |
| 2.3 | 2026-07-30 | §2.7, §3 | In-flight guard on `POST /api/refresh` — concurrent requests rejected with `409 Conflict` to prevent multiple Python subprocesses spawning simultaneously |
| 2.4 | 2026-07-30 | §2.7, §3 | Lock-file guard on `POST /api/refresh` — shared `deye_refresh.lock` file replaces in-memory flag; includes PID and age in 409 response; backend and Python script both check the lock file |
| 2.5 | 2026-07-30 | §8 | Lock file guard tests — validates shared lock file format, 409 response with lock details, stale lock auto-cleanup |
| 2.6 | 2026-07-30 | §8 | Test table updated to list all 7 scenarios; manual testing adds lock file path verification |
| 2.7 | 2026-08-15 | §2.7, §3, §8 | Remove backend lock file guard — lock management delegated entirely to Python script; removes redundant lock file that conflicted with Python-side lock; 409 status code removed |
| 3.0 | 2026-08-26 | §2.7, §2.8, §5.4 | New `GET /api/stats` endpoint — per-column statistics (mean, max/min with first-occurrence timestamp, high/low average daily durations) with `dayFilter`, `highCutoff`, `lowCutoff` parameters; all computation in backend; refresh endpoint renumbered to §2.8 |
| 3.1 | 2026-08-26 | §2.7, §5.4 | Percentage-unit columns (`unit === "%"`, e.g. SOC) use the direct data percentile (type-7 linear interpolation) as the high/low threshold instead of `mean ± z·σ`, which can leave the 0–100% bounds; `high`/`low` objects gain a `method` field (`"mean-sigma"` \| `"percentile"`) (#56) |
| 3.2 | 2026-08-26 | §2.7, §5.4 | Percentage-unit columns now use the **selected cutoff value directly** as the threshold in percent (`method` value `"percentile"` → `"cutoff"`) instead of the data percentile — a data percentile is meaningless for a bounded 0–100% column (SOC high 95 → threshold 95%, not the 95th-percentile value ≈ 100%); SOC high/low now read `> 95%` / `< 5%` (#60) |
| 4.0 | 2026-08-28 | §2.6, §5.3 | `/api/histogram` datasets now include per-bin `min` and `max` arrays alongside the average `data` arrays — the bin loop tracks per-column min/max in addition to sum/count, letting the frontend render the per-bin value range (shaded range / tooltip) (#81) |
| 4.1 | 2026-08-29 | §2.6, §5.3 | `/api/histogram` always returns the full 00:00–24:00 bin grid (1440/binMinutes bins; multi-day rows binned together by time-of-day); bins with no data carry `null` in `data`/`min`/`max` so the frontend x-axis always spans the whole day (#85) |
| 4.2 | 2026-08-30 | §2.7, §5.4 | High/low thresholds for ordinary-unit columns are computed from the **observed range** instead of `mean ± z·σ` (which is meaningless for non-normally distributed, non-negative data): high = `max − (1 − highCutoff/100) × range`, low = `min + (lowCutoff/100) × range`, `range = max − min`; the percentile → z mapping is removed; `method` value `"mean-sigma"` → `"range"`. Percentage-unit columns (e.g. SOC) are unchanged — the 0–100% range is absolute, so the selected cutoff applies directly (`"cutoff"`) (#87) |
