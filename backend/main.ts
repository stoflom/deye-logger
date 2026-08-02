#!/usr/bin/env -S deno run -A

const BACKEND_VERSION = "2.3.1";

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

// Column metadata type — populated from column_metadata table
interface ColumnRecord {
  name: string;
  label: string;
  unit: string;
  is_numeric: number;
}

function buildColumns(): ColumnRecord[] {
  const db = openDatabase();
  const rows = db.prepare(
    `SELECT column_name as name, display_label as label, unit, is_numeric
     FROM column_metadata ORDER BY sort_order ASC`,
  ).all() as ColumnRecord[];
  return rows;
}

// In-memory cache built from column_metadata
let _columnCache: ColumnRecord[] | null = null;

function getColumns(): ColumnRecord[] {
  if (!_columnCache) {
    _columnCache = buildColumns();
  }
  return _columnCache;
}

function getColumnLabels(): Record<string, string> {
  const cols = getColumns();
  const labels: Record<string, string> = {};
  for (const c of cols) labels[c.name] = c.label;
  return labels;
}

function getColumnUnits(): Record<string, string> {
  const cols = getColumns();
  const units: Record<string, string> = {};
  for (const c of cols) units[c.name] = c.unit;
  return units;
}

function getColumnNameSet(): Set<string> {
  const cols = getColumns();
  return new Set(cols.map((c) => c.name));
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

// Validate and parse the incoming columns query param against known column_metadata entries
function parseColumnsParam(columnsParam: string | undefined): string[] {
  if (!columnsParam) return [];
  const requested = columnsParam.split(",").map((c) => c.trim()).filter(Boolean);
  const allowed = getColumnNameSet();
  const valid = requested.filter((c) => allowed.has(c));
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
    const dayFilter = (req.query.dayFilter as string)?.toLowerCase() ?? "all";

    // Validate dayFilter against allowed values
    const validDays = ["all", "sun", "mon", "tue", "wed", "thu", "fri", "sat"];
    const targetDay = validDays.includes(dayFilter) ? dayFilter : "all";
    const dayIndex = dayFilter === "all" ? -1 : ["sun", "mon", "tue", "wed", "thu", "fri", "sat"].indexOf(dayFilter);

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

    // Build SQL with optional day-of-week filter pushed into SQLite
    const dayWhereClause = targetDay !== "all"
      ? ` AND strftime('%w', device_timestamp) = ?`
      : "";
    const queryArgs: (string | number)[] = [fromTs, toTs];
    if (targetDay !== "all") {
      queryArgs.push(String(dayIndex));
    }
    const colListForQuery = colListFromArray(parsedCols);
    const stmt = db.prepare(
      `SELECT ${colListForQuery} FROM inverter_telemetry WHERE device_timestamp >= ? AND device_timestamp <= ?${dayWhereClause} ORDER BY device_timestamp ASC`,
    );
    const rows = stmt.all(...queryArgs) as Record<string, unknown>[];

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

    // Build datasets and compute max values
    // Backend only serves data + label + unit.
    // Display fields (color, yAxisID, position) are computed by the frontend.
    const datasets = numericCols.map((col) => {
      const cols = getColumns();
      const meta = cols.find((c) => c.name === col);
      const label = meta?.label ?? col;
      const unit = meta?.unit ?? "";
      const binCount = binMap.size;

      const data: number[] = [];
      let max = -Infinity;
      let maxIdx = -1;

      for (let j = 0; j < sortedKeys.length; j++) {
        const bin = binMap.get(sortedKeys[j].toString())!;
        const val = bin.sum[col];
        const avg = val !== undefined ? val / bin.count : 0;
        data.push(avg);
        if (avg > max) {
          max = avg;
          maxIdx = j;
        }
      }

      return {
        label,
        data,
        unit,
        max: max !== -Infinity ? max : 0,
        maxTimestamp: maxIdx >= 0 ? labels[maxIdx] : "",
      };
    });

    // Build maxValues map: label → { value, timestamp }
    const maxValues: Record<string, { value: number; timestamp: string }> = {};
    for (const ds of datasets) {
      if (ds.max > 0 && ds.maxTimestamp) {
        maxValues[ds.label] = { value: ds.max, timestamp: ds.maxTimestamp };
      }
    }

    res.json({ labels, datasets, maxValues });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// In-flight guard: prevent concurrent refresh requests
let refreshInProgress = false;

// Refresh database (run deye-logger.py)
app.post("/api/refresh", async (_req: express.Request, res: express.Response) => {
  if (refreshInProgress) {
    res.status(409).json({ error: "Refresh already in progress" });
    return;
  }

  refreshInProgress = true;
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

    // Invalidate column cache so new columns are picked up
    _columnCache = null;

    res.json({ success, code, output, error: errOutput });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    refreshInProgress = false;
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
    console.log(`  Deye Logger Viewer v${BACKEND_VERSION}`);
    console.log(`  http://${HOST}:${PORT}`);
    console.log("═══════════════════════════════════════════\n");
  });
}

start();
