# DeyeCloud Solar Data Logger

Fetches telemetry data from [DeyeCloud](https://deyecloud.com) and stores it in a local SQLite database. Supports realtime data capture, automatic gap detection/backfill, bulk historical data import, and a browser-based viewer.

For detailed design, architecture, data model, and API documentation, see:

- **[deye-cloud-design.md](deye-cloud/deye-cloud-design.md)** — Python logger script (data fetching, gap backfill, spurious data)
- **[frontend-design.md](frontend/frontend-design.md)** — Browser viewer (SPA, Chart.js, AG Grid)
- **[backend-design.md](backend/backend-design.md)** — HTTP server (Deno + Express, REST API)

## Features

- Realtime telemetry polling (45 fields: PV strings 1–3, battery, grid, load, consumption, temperatures, generator)
- Automatic gap detection — backfills data breaks from the history API (configurable via `GAP_THRESHOLD_MINUTES`)
- Spurious data detection & cleanup — removes corrupted API records (zero-reset or incomplete responses)
- Bulk historical import via `--fetch-since` (7-day chunking to respect API limits)
- SQLite storage with indexed timestamps

## Project Structure

```
deye-logger/
├── deye-cloud/            # Python data-fetching script
│   ├── deye-logger.py     # Main logger script
│   ├── deye-cloud-design.md  # Design document (architecture, API, data model)
│   ├── .env               # Credentials (git-ignored)
│   └── .env.example       # Template
├── backend/               # Deno + Express HTTP server — see [backend-design.md](backend/backend-design.md)
│   ├── main.ts            # Server entry point
│   ├── start.sh           # Build + serve script
│   └── deno.json          # Deno configuration
├── frontend/              # Browser viewer — see [frontend-design.md](frontend/frontend-design.md)
│   ├── src/               # TypeScript source
│   ├── public/            # Static files
│   └── package.json       # Node dependencies
├── .gitignore
├── deye_solar_data.db     # SQLite database (git-ignored)
└── README.md
```

## Requirements

- **Python 3.8+** (logger)
- [Deno](https://deno.com/) 2.x+ (viewer)
- Node.js 18+ with npm (viewer build tooling)

### Installing Prerequisites

**Python packages:**
```bash
pip install requests python-dotenv
```

**Deno (viewer only):**
```bash
# Linux / macOS — package manager preferred
sudo apt install deno          # Debian/Ubuntu
brew install deno              # macOS
# or: curl -fsSL https://deno.land/install.sh | sh

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

**Project dependencies (viewer only):**
```bash
cd frontend && npm install && cd ..
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
   | `DB_NAME` | Path to SQLite database (relative to script dir; default `../deye_solar_data.db`) |

   Compute the password hash:
   ```bash
   echo -n "yourpassword" | sha256sum
   ```

## Usage

### Normal operation (fetch latest + backfill gaps)

```bash
cd deye-cloud
python deye-logger.py
```

Fetches latest telemetry, saves to database, and scans for gaps >3 minutes — auto-backfilling from the history API.

```bash
python deye-logger.py --gap 5   # only backfill gaps >5 min
python deye-logger.py -db /custom/path/my_solar_data.db  # custom DB
```

### Bulk historical import

```bash
python deye-logger.py --fetch-since "1 July 2026"
```

Supports formats: `YYYY-MM-DD`, `DD Mon YYYY`, `DD MMMM YYYY`, `YYYY/MM/DD`.

### Spurious data management

```bash
python deye-logger.py --find-spurious   # detect corrupted records
python deye-logger.py --delete-spurious # remove them
```

Short flags `-fs` and `-ds` also available.

## Browser Viewer

A lightweight web viewer ([Chart.js](https://www.chartjs.org/) + [AG Grid](https://www.aggrid.com)) for browsing the SQLite database via a [Deno](https://deno.com/) + [Express](https://expressjs.com/) server using Node's native `node:sqlite` module.

### Starting the Viewer

```bash
bash backend/start.sh
```

Opens `http://localhost:8090` with today's data loaded. Development mode with auto-rebuild:

```bash
cd frontend && npm run dev
```

### Viewer Features

- **Chart view** — time-series line chart, toggleable columns
- **Histogram view** — time-binned bar chart (5/10/15/30/60 min bins) showing averages across a date range
- **Data Grid** — sortable, filterable, resizable AG Grid with CSV export
- **Date navigation** — ‹/› arrows and date picker with range selection
- **Column selection** — toggle columns on/off (persisted in localStorage)
- **Summary cards** — dynamic max-value cards for all numeric columns
- **Refresh button** — triggers `deye-logger.py` to fetch latest telemetry then reloads

### Server Options

| Flag | Description | Example |
|---|---|---|
| `-H, --host` | Bind host | `bash backend/start.sh -H 0.0.0.0` |
| `-p, --port` | Port (default: 8090) | `bash backend/start.sh -p 3000` |
| `-d, --db` | Database path | `bash backend/start.sh -d /custom/path.db` |

Bind to all interfaces for network access: `bash backend/start.sh -H 0.0.0.0`

Or start directly with Deno (skips build step):
```bash
cd backend
deno run -A main.ts --host 0.0.0.0 --port 8090 --db=../deye_solar_data.db
```

> **Note:** `start.sh` uses `lsof` to detect and kill any existing instance on the specified port. If `lsof` is unavailable, use `fuser -k <port>/tcp` instead.

## Scheduled Runs

Use cron for periodic telemetry fetches (e.g., every 5 minutes):

```bash
crontab -e
# Add:
*/5 * * * * /usr/bin/python3 /home/<user>/Workspace/deye-logger/deye-cloud/deye-logger.py >> /home/<user>/Workspace/deye-logger/cron.log 2>&1
```
