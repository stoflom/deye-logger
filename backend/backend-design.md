# Backend Design Document — Deye Logger Viewer

> **Status:** v1.2
> **Scope:** Deno + Express server, SQLite (read-only), REST API for inverter telemetry data
> **Language:** TypeScript (via Deno with npm: packages)
> **Runtime:** Deno with `node:sqlite`, Express.js

> **Software Versioning scheme:** Backend version is `major.minor.subminor`.
> - **major** — major new features, architectural changes, number must agree with this document major version
> - **minor** — design changes to implement new features or fix design issues, number must agree with this document minor version
> - **subminor** — bug fixes requiring no design changes

---

## 1. Architecture Overview

The backend is a lightweight HTTP server built with **Deno** and **Express.js** that serves a single purpose: read inverter telemetry data from a **SQLite database** and expose it through a REST API consumed by the frontend single-page application. The SQLite database is opened in **read-only mode** — all data ingestion is handled by the separate Python script (`deye-cloud/deye-logger.py`).

```
┌──────────────┐       ┌──────────────────┐       ┌─────────────────────┐
│   Frontend    │──────▶│  Deno + Express   │──────▶│   SQLite Database   │
│  (SPA in      │◀──────│  HTTP Server      │◀──────│  (read-only)        │
│   public/)    │       └──────────────────┘       └─────────────────────┘
└──────────────┘       │  static file serving  │
                       │  /api/* REST endpoints│
                       └───────────────────────┘
                              │
                              │ POST /api/refresh
                              ▼
                       ┌──────────────────┐
                       │ Python Script     │
                       │ deye-logger.py    │
                       │ (Deye Cloud API)  │
                       └──────────────────┘
```

### 1.1 Source Files

| File | Responsibility |
|------|----------------|
| `main.ts` | Application entry point, Express routes, SQLite queries, static file serving |
| `deno.json` | Deno configuration, task definitions (dev, build) |
| `start.sh` | Startup script — builds frontend, resolves DB path, launches server |

### 1.2 Configuration

The server is configured via command-line arguments (no environment variables required for the server itself):

| Flag | Default | Description |
|------|---------|-------------|
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

All telemetry column names and their human-readable labels are defined in a single source-of-truth record `COLUMN_LABELS` in `main.ts`. This record maps internal column names (matching database columns) to display labels with units.

Available columns (43 total):

| Column Key | Display Label |
|------------|---------------|
| `device_timestamp` | Timestamp |
| `fetch_timestamp` | Fetch Time |
| `inverter_sn` | Inverter SN |
| `daily_energy` | Daily Energy (kWh) |
| `total_energy` | Total Energy (kWh) |
| `current_power` | Current Power (W) |
| `battery_soc` | Battery SOC (%) |
| `battery_voltage` | Battery Voltage (V) |
| `battery_current` | Battery Current (A) |
| `grid_power` | Grid Power (W) |
| `grid_voltage` | Grid Voltage (V) |
| `grid_frequency` | Grid Frequency (Hz) |
| `pv1_voltage` | PV1 Voltage (V) |
| `pv1_current` | PV1 Current (A) |
| `pv1_power` | PV1 Power (W) |
| `pv2_voltage` | PV2 Voltage (V) |
| `pv2_current` | PV2 Current (A) |
| `pv2_power` | PV2 Power (W) |
| `pv3_voltage` | PV3 Voltage (V) |
| `pv3_current` | PV3 Current (A) |
| `pv3_power` | PV3 Power (W) |
| `total_dc_power` | Total DC Power (W) |
| `total_consumption_power` | Total Consumption Power (W) |
| `cumulative_consumption` | Cumulative Consumption (kWh) |
| `daily_consumption` | Daily Consumption (kWh) |
| `battery_power` | Battery Power (W) |
| `total_charge_energy` | Total Charge Energy (kWh) |
| `total_discharge_energy` | Total Discharge Energy (kWh) |
| `daily_charging_energy` | Daily Charging Energy (kWh) |
| `daily_discharging_energy` | Daily Discharging Energy (kWh) |
| `cumulative_grid_feed_in` | Cumulative Grid Feed-in (kWh) |
| `cumulative_energy_purchased` | Cumulative Energy Purchased (kWh) |
| `daily_grid_feed_in` | Daily Grid Feed-in (kWh) |
| `daily_energy_purchased` | Daily Energy Purchased (kWh) |
| `load_voltage` | Load Voltage (V) |
| `grid_current` | Grid Current (A) |
| `external_ct_power` | External CT Power (W) |
| `battery_rated_capacity` | Battery Rated Capacity (Ah) |
| `battery_temp` | Battery Temp (°C) |
| `dc_temp` | DC Temp (°C) |
| `ac_temp` | AC Temp (°C) |
| `generator_frequency` | Generator Frequency (Hz) |
| `generator_voltage` | Generator Voltage (V) |
| `total_generator_production` | Total Generator Prod. (kWh) |
| `ac_voltage` | AC Voltage (V) |
| `ac_current` | AC Current (A) |
| `rated_power` | Rated Power (W) |

### 1.5 Database

The SQLite database (`deye_solar_data.db`) is opened in **read-only mode**. The server creates a prepared statement cache on first query. The database is re-opened after a refresh operation to pick up newly imported data.

#### Database Schema

| Table | Purpose |
|-------|---------|
| `inverter_telemetry` | Main telemetry data, primary key on `device_timestamp` |
| `gap_attempts` | Tracks gap-filling attempts between date ranges |
| `spurious_records` | Records identified as spurious/invalid API responses |
| `_schema_migrations` | Schema migration tracking |

The `inverter_telemetry` table has a primary key on `device_timestamp` (TEXT), an index on `device_timestamp`, and an index on `complete`.

---

## 2. API Endpoints

All API endpoints respond with **JSON** and are prefixed with `/api/`.

### 2.1 `GET /api/columns`

Returns the list of all available telemetry columns with their human-readable labels.

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
{ "version": "1.2.0" }
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
|-----------|----------|-------------|
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

Computes time-binned averages of telemetry data across a date range. Designed for the histogram chart view. The results are pre-aggregated: each bin contains the average of each numeric column.

**Request:**
```
GET /api/histogram?from=2025-07-27&to=2025-07-27&columns=daily_energy,battery_soc,current_power,battery_voltage&binMinutes=15
```

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `from` | Yes | Start date in YYYY-MM-DD format (inclusive) |
| `to` | Yes | End date in YYYY-MM-DD format (inclusive) |
| `columns` | Yes | Comma-separated list of column keys. Only columns matching known keys are included. `device_timestamp` is automatically prepended if any valid column is requested. |
| `binMinutes` | No | Bin size in minutes. Default: `15`. Values: any positive integer (commonly 5, 10, 15, 30, 60). |

**Validation:**
- If any of `from`, `to`, or `columns` is missing → `400 Bad Request`
- If no valid columns are requested → `400 Bad Request`

**Response (200 OK):**
```json
{
  "labels": ["00:00", "00:15", "00:30", "00:45", "01:00", ...],
  "datasets": [
    {
      "label": "Daily Energy (kWh)",
      "data": [10.2, 10.5, 10.8, 11.0, 11.3, ...],
      "color": "#3182ce",
      "unit": "kWh",
      "yAxisID": "y-0",
      "position": "left",
      "max": 15.2,
      "maxTimestamp": "14:30"
    },
    {
      "label": "Battery SOC (%)",
      "data": [50.0, 52.1, 54.3, 55.0, 56.2, ...],
      "color": "#e53e3e",
      "unit": "%",
      "yAxisID": "y-0",
      "position": "left",
      "max": 85.0,
      "maxTimestamp": "18:45"
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
|-------|------|-------------|
| `labels` | string[] | Time labels for each bin in `HH:MM` format (e.g., `["00:00", "00:15", "00:30"]`) |
| `datasets` | object[] | One dataset per numeric column (metadata columns like `device_timestamp`, `inverter_sn`, `fetch_timestamp` are excluded). Each dataset contains: |
| `datasets[].label` | string | Human-readable column label |
| `datasets[].data` | (number\|null)[] | Averaged values for each bin. `null` if no data for that bin. |
| `datasets[].color` | string | Hex color from the palette |
| `datasets[].unit` | string | Unit extracted from the label (e.g., `"kWh"`, `"%"`) |
| `datasets[].yAxisID` | string | Chart.js axis ID (`y-0`, `y-1`, `yR-0`, etc.) based on unit grouping |
| `datasets[].position` | string | `"left"` or `"right"` for Chart.js |
| `datasets[].max` | number\|null | Maximum averaged value across all bins |
| `datasets[].maxTimestamp` | string\|null | Time label where the maximum occurs |
| `maxValues` | object | Map of label → `{ value, timestamp }` for peak display in summary cards |

**Column-to-Axis Assignment:**
- Up to **2 units** are assigned to the **left** y-axis (`y-0`, `y-1`).
- Additional units are assigned to **right** y-axes (`yR-0`, `yR-1`, ...).
- Unit is extracted from the label text within parentheses (e.g., `"kWh"` from `"Daily Energy (kWh)"`).

**Color Palette** (15 colors, reused cyclically):
```
#3182ce, #e53e3e, #38a169, #d69e2e, #805ad5,
#dd6b20, #319795, #d53f8c, #2b6cb0, #c53030,
#276749, #b7791f, #6b46c1, #c05621, #285e61
```

**Empty Response:**
If no data or no numeric columns are found, returns:
```json
{ "labels": [], "datasets": [], "maxValues": {} }
```

---

### 2.7 `POST /api/refresh`

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
|-------|------|-------------|
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
3. Keeps only columns that exist in the `COLUMN_LABELS` registry.
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

### 5.3 Histogram Queries (`/api/histogram`)

```
Client → GET /api/histogram?from=YYYY-MM-DD&to=YYYY-MM-DD&columns=...&binMinutes=N
           ↓
       Parse columns, validate numeric columns (exclude metadata)
           ↓
       Query all rows in range (same SQL as data-range)
           ↓
       Group rows into time bins (floor timestamps to bin boundary)
           ↓
       Compute per-bin average for each numeric column
           ↓
       Assign units to axes (left: first 2 unique units, right: rest)
           ↓
       Build datasets with labels, colors, axis IDs, max values
           ↓
       Return { labels, datasets, maxValues }
```

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

## 8. Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.2 | 2025-07-28 | Initial design document — all current API endpoints, column schema, histogram logic |
