#!/usr/bin/env -S deno run -A

const BACKEND_VERSION = "1.2.0";

import express from "npm:express";
import { DatabaseSync } from "node:sqlite";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Parse command-line arguments
const args = Deno.args;

function parseArg(flag: string): string | undefined {
  const found = args.find((a) => a === flag || a.startsWith(flag + "="));
  if (!found) return undefined;
  const eq = found.indexOf("=");
  return eq >= 0 ? found.substring(eq + 1) : args[args.indexOf(found) + 1];
}

const HOST = args.includes("--help")
  ? undefined
  : (parseArg("--host") ?? "localhost");
const PORT = Number(parseArg("--port")) || 8090;
const DB_PATH = parseArg("--db");

if (args.includes("--help")) {
  console.log(`Usage: deno run -A main.ts [--host <host>] [--port <port>] [--db <db_path>] [--help]

Options:
  --host <host>   Host to bind to (default: localhost)
  --port <port>   Port to listen on (default: 8090)
  --db <db_path>  Path to the SQLite database (required)
  --help          Show this help message`);
  Deno.exit(0);
}

if (!DB_PATH) {
  console.error("Error: --db <path> is required. Use --help for usage.");
  Deno.exit(1);
}

const __dirname = dirname(fileURLToPath(import.meta.url));

// Column labels (single source of truth)
const COLUMN_LABELS: Record<string, string> = {
  device_timestamp: "Timestamp",
  fetch_timestamp: "Fetch Time",
  inverter_sn: "Inverter SN",
  daily_energy: "Daily Energy (kWh)",
  total_energy: "Total Energy (kWh)",
  current_power: "Current Power (W)",
  battery_soc: "Battery SOC (%)",
  battery_voltage: "Battery Voltage (V)",
  battery_current: "Battery Current (A)",
  grid_power: "Grid Power (W)",
  grid_voltage: "Grid Voltage (V)",
  grid_frequency: "Grid Frequency (Hz)",
  pv1_voltage: "PV1 Voltage (V)",
  pv1_current: "PV1 Current (A)",
  pv1_power: "PV1 Power (W)",
  pv2_voltage: "PV2 Voltage (V)",
  pv2_current: "PV2 Current (A)",
  pv2_power: "PV2 Power (W)",
  load_power: "Load Power (W)",
  pv3_voltage: "PV3 Voltage (V)",
  pv3_current: "PV3 Current (A)",
  pv3_power: "PV3 Power (W)",
  total_dc_power: "Total DC Power (W)",
  total_consumption_power: "Total Consumption Power (W)",
  cumulative_consumption: "Cumulative Consumption (kWh)",
  daily_consumption: "Daily Consumption (kWh)",
  battery_power: "Battery Power (W)",
  total_charge_energy: "Total Charge Energy (kWh)",
  total_discharge_energy: "Total Discharge Energy (kWh)",
  daily_charging_energy: "Daily Charging Energy (kWh)",
  daily_discharging_energy: "Daily Discharging Energy (kWh)",
  cumulative_grid_feed_in: "Cumulative Grid Feed-in (kWh)",
  cumulative_energy_purchased: "Cumulative Energy Purchased (kWh)",
  daily_grid_feed_in: "Daily Grid Feed-in (kWh)",
  daily_energy_purchased: "Daily Energy Purchased (kWh)",
  load_voltage: "Load Voltage (V)",
  grid_current: "Grid Current (A)",
  external_ct_power: "External CT Power (W)",
  battery_rated_capacity: "Battery Rated Capacity (Ah)",
  battery_temp: "Battery Temp (°C)",
  dc_temp: "DC Temp (°C)",
  ac_temp: "AC Temp (°C)",
  generator_frequency: "Generator Frequency (Hz)",
  generator_voltage: "Generator Voltage (V)",
  total_generator_production: "Total Generator Prod. (kWh)",
  ac_voltage: "AC Voltage (V)",
  ac_current: "AC Current (A)",
  rated_power: "Rated Power (W)",
};

function buildColumns(): { name: string; label: string }[] {
  return Object.entries(COLUMN_LABELS).map(([name, label]) => ({ name, label }));
}

// ── SQLite Database (native node:sqlite) ─────────────────────
let db: DatabaseSync | null = null;

function openDatabase(): DatabaseSync {
  if (db) return db;
  db = new DatabaseSync(DB_PATH, { readOnly: true });
  return db!;
}

// Helper: build a quoted, comma-separated column list from an array of column names
function colListFromArray(cols: string[]): string {
  return cols.map((c) => `"${c}"`).join(", ");
}

// Validate and parse the incoming columns query param against known COLUMN_LABELS
function parseColumnsParam(columnsParam: string | undefined): string[] {
  if (!columnsParam) return [];
  const requested = columnsParam.split(",").map((c) => c.trim()).filter(Boolean);
  const allowed = Object.keys(COLUMN_LABELS);
  const valid = requested.filter((c) => allowed.includes(c));
  // Always ensure timestamp is present first
  if (!valid.includes("device_timestamp")) valid.unshift("device_timestamp");
  return valid;
}

// Helper: query telemetry rows between two timestamps for the requested columns
function queryTelemetryBetween(db: DatabaseSync, columns: string[], fromTs: string, toTs: string) {
  const colList = colListFromArray(columns);
  const stmt = db.prepare(
    `SELECT ${colList} FROM inverter_telemetry WHERE device_timestamp >= ? AND device_timestamp <= ? ORDER BY device_timestamp ASC`,
  );
  return stmt.all(fromTs, toTs);
}

// ── Express app ──────────────────────────────────────────────
const app = express();

// Serve static files
app.use(express.static(join(__dirname, "..", "frontend", "public")));
app.use("/node_modules", express.static(join(__dirname, "..", "frontend", "node_modules")));

// Column metadata
app.get("/api/columns", (_req: express.Request, res: express.Response) => {
  res.json(buildColumns());
});

// Version info
app.get("/api/version", (_req: express.Request, res: express.Response) => {
  res.json({ version: BACKEND_VERSION });
});

// Date range
app.get("/api/dates", async (_req: express.Request, res: express.Response) => {
  try {
    const db = openDatabase();
    const row = db.prepare(
      "SELECT MIN(device_timestamp) as min_ts, MAX(device_timestamp) as max_ts FROM inverter_telemetry",
    ).all() as { min_ts?: string; max_ts?: string }[];
    res.json({
      min: row[0]?.min_ts ? String(row[0].min_ts).slice(0, 10) : "",
      max: row[0]?.max_ts ? String(row[0].max_ts).slice(0, 10) : "",
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Query data for a specific date and columns
app.get("/api/data", async (req: express.Request, res: express.Response) => {
  try {
    const db = openDatabase();
    const date = req.query.date as string;
    const columns = req.query.columns as string;

    if (!date || !columns) {
      res.status(400).json({ error: "Missing 'date' and 'columns' query params" });
      return;
    }

    const from = `${date} 00:00:00`;
    const to = `${date} 23:59:59`;

    const parsedCols = parseColumnsParam(columns);
    if (parsedCols.length === 0) {
      res.status(400).json({ error: "No valid columns requested" });
      return;
    }
    const rows = queryTelemetryBetween(db, parsedCols, from, to);

    res.json({ rows });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Query data across a date range
app.get("/api/data-range", async (req: express.Request, res: express.Response) => {
  try {
    const db = openDatabase();
    const from = req.query.from as string;
    const to = req.query.to as string;
    const columns = req.query.columns as string;

    if (!from || !to || !columns) {
      res.status(400).json({ error: "Missing 'from', 'to', and 'columns' query params" });
      return;
    }

    const fromTs = `${from} 00:00:00`;
    const toTs = `${to} 23:59:59`;

    const parsedCols = parseColumnsParam(columns);
    if (parsedCols.length === 0) {
      res.status(400).json({ error: "No valid columns requested" });
      return;
    }
    const rows = queryTelemetryBetween(db, parsedCols, fromTs, toTs);

    res.json({ rows });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Histogram — time-binned averages
app.get("/api/histogram", async (req: express.Request, res: express.Response) => {
  try {
    const db = openDatabase();
    const from = req.query.from as string;
    const to = req.query.to as string;
    const columns = req.query.columns as string;
    const binMinutes = parseInt(req.query.binMinutes as string, 10) || 15;

    if (!from || !to || !columns) {
      res.status(400).json({ error: "Missing 'from', 'to', and 'columns' query params" });
      return;
    }

    const colList = columns.split(",").map((c: string) => `"${c.trim()}"`).join(", ");
    const fromTs = `${from} 00:00:00`;
    const toTs = `${to} 23:59:59`;

    const parsedCols = parseColumnsParam(columns);
    if (parsedCols.length === 0) {
      res.status(400).json({ error: "No valid columns requested" });
      return;
    }
    const rows = queryTelemetryBetween(db, parsedCols, fromTs, toTs) as Record<string, unknown>[];

    if (rows.length === 0) {
      res.json({ labels: [], datasets: [], maxValues: {} });
      return;
    }

    const requestedCols = parsedCols;

    // Identify numeric columns (skip non-numeric metadata)
    const numericCols = requestedCols.filter((col) => {
      if (col === "device_timestamp" || col === "inverter_sn" || col === "fetch_timestamp") return false;
      return rows.some((row) => typeof row[col] === "number" && row[col] !== 0);
    });

    if (numericCols.length === 0) {
      res.json({ labels: [], datasets: [], maxValues: {} });
      return;
    }

    // Parse timestamps and group into bins
    const binMap = new Map<string, { sum: Record<string, number>; count: number }>();

    for (const row of rows) {
      const ts = row.device_timestamp;
      let d: Date | null = null;
      if (typeof ts === "number") {
        d = new Date(ts > 1e12 ? ts : ts * 1000);
      } else if (typeof ts === "string" && ts) {
        d = new Date(ts);
        if (isNaN(d.getTime())) d = null;
      }
      if (!d) continue;

      // Floor to bin boundary, normalize to reference day
      const floored = new Date(d);
      floored.setMinutes(Math.floor(floored.getMinutes() / binMinutes) * binMinutes, 0, 0);
      const ref = new Date(2000, 0, 1);
      ref.setHours(floored.getHours(), floored.getMinutes(), 0, 0);
      const key = ref.getTime().toString();

      if (!binMap.has(key)) binMap.set(key, { sum: {}, count: 0 });
      const bin = binMap.get(key)!;
      bin.count++;

      for (const col of numericCols) {
        const val = row[col];
        if (typeof val === "number") bin.sum[col] = (bin.sum[col] || 0) + val;
      }
    }

    const sortedKeys = [...binMap.keys()].map(Number).sort((a, b) => a - b);
    if (sortedKeys.length === 0) {
      res.json({ labels: [], datasets: [], maxValues: {} });
      return;
    }

    // Build labels
    const labels = sortedKeys.map((key) => {
      const d = new Date(key);
      const h = String(d.getHours()).padStart(2, "0");
      const m = String(d.getMinutes()).padStart(2, "0");
      return `${h}:${m}`;
    });

    // Group columns by unit for axis assignment
    const unitToAxis: Record<string, string> = {};
    const unitPosition: Record<string, string> = {};
    let leftCount = 0;
    let rightCount = 0;

    function extractUnit(label: string): string {
      const match = label.match(/\((.+)\)$/);
      return match ? match[1] : "";
    }

    for (const col of numericCols) {
      const label = COLUMN_LABELS[col] ?? col;
      const unit = extractUnit(label);
      if (!(unit in unitToAxis)) {
        unitToAxis[unit] = leftCount < 2 ? `y-${leftCount}` : `yR-${rightCount}`;
        unitPosition[unit] = leftCount < 2 ? "left" : "right";
        if (leftCount < 2) leftCount++; else rightCount++;
      }
    }

    const palette = [
      "#3182ce", "#e53e3e", "#38a169", "#d69e2e", "#805ad5",
      "#dd6b20", "#319795", "#d53f8c", "#2b6cb0", "#c53030",
      "#276749", "#b7791f", "#6b46c1", "#c05621", "#285e61",
    ];

    // Build datasets and compute max values
    const datasets = numericCols.map((col, i) => {
      const label = COLUMN_LABELS[col] ?? col;
      const unit = extractUnit(label);
      const yAxisID = unitToAxis[unit] ?? "y-0";
      const position = unitPosition[unit] ?? "left";
      const color = palette[i % palette.length];
      const binCount = binMap.size;

      const data: (number | null)[] = [];
      let max = -Infinity;
      let maxIdx = -1;

      for (let j = 0; j < sortedKeys.length; j++) {
        const bin = binMap.get(sortedKeys[j].toString())!;
        const val = bin.sum[col];
        const avg = val !== undefined ? val / bin.count : null;
        data.push(avg);
        if (typeof avg === "number" && avg > max) {
          max = avg;
          maxIdx = j;
        }
      }

      return {
        label,
        data,
        color,
        unit,
        yAxisID,
        position,
        max: max !== -Infinity ? max : null,
        maxTimestamp: maxIdx >= 0 ? labels[maxIdx] : null,
      };
    });

    // Build maxValues map: label → { value, timestamp }
    const maxValues: Record<string, { value: number; timestamp: string }> = {};
    for (const ds of datasets) {
      if (ds.max !== null && ds.maxTimestamp !== null) {
        maxValues[ds.label] = { value: ds.max, timestamp: ds.maxTimestamp };
      }
    }

    res.json({ labels, datasets, maxValues });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Refresh database (run deye-logger.py)
app.post("/api/refresh", async (_req: express.Request, res: express.Response) => {
  try {
    const scriptPath = join(__dirname, "..", "deye-cloud", "deye-logger.py");
    const cmd = new Deno.Command("python3", {
      args: [scriptPath],
      stdin: "null",
      stdout: "piped",
      stderr: "piped",
    });
    const { code, success, stdout, stderr } = await cmd.output();

    const output = new TextDecoder().decode(stdout);
    const errOutput = new TextDecoder().decode(stderr);

    // Re-open DB after refresh so new data is visible
    if (success && db) {
      db.close();
      db = null;
      openDatabase();
    }

    res.json({ success, code, output, error: errOutput });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ── Start ────────────────────────────────────────────────────
async function start() {
  try {
    openDatabase();
    console.log(`  ✓ Database loaded — ${DB_PATH}`);
  } catch (err) {
    console.error("  ⚠ Database load warning:", err);
  }

  app.listen(PORT, HOST, () => {
    console.log("═══════════════════════════════════════════");
    console.log("  Deye Logger Viewer");
    console.log(`  http://${HOST}:${PORT}`);
    console.log("═══════════════════════════════════════════\n");
  });
}

start();
