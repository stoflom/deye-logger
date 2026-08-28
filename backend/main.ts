#!/usr/bin/env -S deno run -A

const BACKEND_VERSION = "4.0.0";

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
function requireDbPath(): string {
  const path = parseArg("--db");
  if (path) return path;
  console.error("Error: --db <path> is required. Use --help for usage.");
  Deno.exit(1);
}

if (args.includes("--help")) {
  console.log(`Usage: deno run -A main.ts [--host <host>] [--port <port>] [--db <db_path>] [--help]

Options:
  --host <host>   Host to bind to (default: localhost)
  --port <port>   Port to listen on (default: 8090)
  --db <db_path>  Path to the SQLite database (required)
  --help          Show this help message`);
  Deno.exit(0);
}

// requireDbPath exits when --db is missing, so this is a plain string
const DB_PATH: string = requireDbPath();

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
  ).all() as Record<string, unknown>[];
  return rows.map((r) => ({
    name: String(r.name),
    label: String(r.label),
    unit: String(r.unit ?? ""),
    is_numeric: Number(r.is_numeric ?? 0),
  }));
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
  if (valid.length === 0) return [];   // no valid columns → 400
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
    // Per bin: total count + per-column sum/min/max/count so each column's
    // stats only reflect rows that actually have a value for that column.
    const binMap = new Map<string, { sum: Record<string, number>; min: Record<string, number>; max: Record<string, number>; count: Record<string, number>; total: number }>();

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

      if (!binMap.has(key)) binMap.set(key, { sum: {}, min: {}, max: {}, count: {}, total: 0 });
      const bin = binMap.get(key)!;
      bin.total++;

      for (const col of numericCols) {
        const val = row[col];
        if (typeof val === "number") {
          bin.sum[col] = (bin.sum[col] || 0) + val;
          bin.min[col] = bin.min[col] === undefined ? val : Math.min(bin.min[col], val);
          bin.max[col] = bin.max[col] === undefined ? val : Math.max(bin.max[col], val);
          bin.count[col] = (bin.count[col] || 0) + 1;
        }
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
    const maxPeaks: { label: string; value: number; timestamp: string }[] = [];
    const datasets = numericCols.map((col) => {
      const cols = getColumns();
      const meta = cols.find((c) => c.name === col);
      const label = meta?.label ?? col;
      const unit = meta?.unit ?? "";

      const data: number[] = [];
      const minData: number[] = [];
      const maxData: number[] = [];
      let peak = -Infinity;
      let peakIdx = -1;

      for (let j = 0; j < sortedKeys.length; j++) {
        const bin = binMap.get(sortedKeys[j].toString())!;
        const binCount = bin.count[col] ?? 0;
        const hasVal = binCount > 0;
        const avg = hasVal ? bin.sum[col] / binCount : 0;
        data.push(avg);
        minData.push(hasVal ? bin.min[col] : 0);
        maxData.push(hasVal ? bin.max[col] : 0);
        if (hasVal && avg > peak) {
          peak = avg;
          peakIdx = j;
        }
      }

      if (peak !== -Infinity && peakIdx >= 0 && peak > 0) {
        maxPeaks.push({ label, value: peak, timestamp: labels[peakIdx] });
      }

      return { label, data, min: minData, max: maxData, unit };
    });

    // Build maxValues map: label → { value, timestamp }
    const maxValues: Record<string, { value: number; timestamp: string }> = {};
    for (const p of maxPeaks) {
      maxValues[p.label] = { value: p.value, timestamp: p.timestamp };
    }

    res.json({ labels, datasets, maxValues });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ── Stats — per-column statistics over a date range ─────────
// Percentile → one-tailed standard-normal deviate z (design §2.7)
const HIGH_CUTOFF_Z: Record<number, number> = { 50: 0, 75: 0.674, 90: 1.282, 95: 1.645, 99: 2.326 };
const LOW_CUTOFF_Z: Record<number, number> = { 1: 2.326, 5: 1.645, 10: 1.282, 25: 0.674, 50: 0 };

// Parse a cutoff param against its allowed table; invalid → default
function parseCutoffParam(raw: string | undefined, table: Record<number, number>, defaultValue: number): number {
  const n = parseInt(raw ?? "", 10);
  return table[n] !== undefined ? n : defaultValue;
}

interface StatSample { ms: number; day: string; v: number; ts: string }

// Average per-day duration (minutes) where test(v) is true.
// An interval between two consecutive samples counts only when BOTH samples
// qualify. Intervals crossing midnight are split and attributed to the start
// and end day. Averaged over days that have ≥1 sample (zero-duration days
// stay in the denominator).
function avgDailyMinutes(samples: StatSample[], test: (v: number) => boolean): number {
  const daysWithSamples = new Set(samples.map((s) => s.day));
  if (daysWithSamples.size === 0) return 0;

  const perDay = new Map<string, number>();
  const add = (day: string, ms: number) => perDay.set(day, (perDay.get(day) ?? 0) + ms);

  for (let i = 0; i + 1 < samples.length; i++) {
    const a = samples[i];
    const b = samples[i + 1];
    if (!test(a.v) || !test(b.v)) continue;
    if (a.day === b.day) {
      add(a.day, b.ms - a.ms);
    } else {
      // Split at midnight of day a (DST-aware via hour=24 normalization)
      const [y, m, d] = a.day.split("-").map(Number);
      const endOfDayA = new Date(y, m - 1, d, 24, 0, 0, 0).getTime();
      if (endOfDayA > a.ms) add(a.day, endOfDayA - a.ms);
      const [y2, m2, d2] = b.day.split("-").map(Number);
      const startOfDayB = new Date(y2, m2 - 1, d2).getTime();
      if (b.ms > startOfDayB) add(b.day, b.ms - startOfDayB);
    }
  }

  let total = 0;
  for (const day of daysWithSamples) total += perDay.get(day) ?? 0;
  return Math.round((total / daysWithSamples.size / 60000) * 10) / 10;
}

app.get("/api/stats", async (req: express.Request, res: express.Response) => {
  try {
    const db = openDatabase();
    const from = req.query.from as string;
    const to = req.query.to as string;
    const columns = req.query.columns as string;

    if (!from || !to || !columns) {
      res.status(400).json({ error: "Missing 'from', 'to', and 'columns' query params" });
      return;
    }

    const parsedCols = parseColumnsParam(columns);
    if (parsedCols.length === 0) {
      res.status(400).json({ error: "No valid columns requested" });
      return;
    }

    const dayFilter = (req.query.dayFilter as string)?.toLowerCase() ?? "all";
    const validDays = ["all", "sun", "mon", "tue", "wed", "thu", "fri", "sat"];
    const targetDay = validDays.includes(dayFilter) ? dayFilter : "all";
    const dayIndex = targetDay === "all" ? -1 : ["sun", "mon", "tue", "wed", "thu", "fri", "sat"].indexOf(targetDay);

    const highCutoff = parseCutoffParam(req.query.highCutoff as string, HIGH_CUTOFF_Z, 95);
    const lowCutoff = parseCutoffParam(req.query.lowCutoff as string, LOW_CUTOFF_Z, 5);

    const fromTs = `${from} 00:00:00`;
    const toTs = `${to} 23:59:59`;

    // Day-of-week filter pushed into SQLite (same pattern as /api/histogram)
    const dayWhereClause = targetDay !== "all"
      ? ` AND strftime('%w', device_timestamp) = ?`
      : "";
    const queryArgs: (string | number)[] = [fromTs, toTs];
    if (targetDay !== "all") queryArgs.push(String(dayIndex));

    const stmt = db.prepare(
      `SELECT ${colListFromArray(parsedCols)} FROM inverter_telemetry
       WHERE device_timestamp >= ? AND device_timestamp <= ?${dayWhereClause}
       ORDER BY device_timestamp ASC`,
    );
    const rows = stmt.all(...queryArgs) as Record<string, unknown>[];

    if (rows.length === 0) {
      res.json({ stats: [] });
      return;
    }

    const meta = getColumns();
    const stats: Record<string, unknown>[] = [];

    for (const col of parsedCols) {
      const m = meta.find((c) => c.name === col);
      if (!m || !m.is_numeric) continue;

      // Collect non-null samples in timestamp order
      const samples: StatSample[] = [];
      for (const row of rows) {
        const v = row[col];
        if (typeof v !== "number" || Number.isNaN(v)) continue;
        const ts = row.device_timestamp as string;
        const d = new Date(ts);
        if (isNaN(d.getTime())) continue;
        samples.push({ ms: d.getTime(), day: ts.slice(0, 10), v, ts });
      }
      const n = samples.length;
      if (n === 0) continue;

      let sum = 0;
      let max = -Infinity, maxTs = "";
      let min = Infinity, minTs = "";
      for (const s of samples) {
        sum += s.v;
        if (s.v > max) { max = s.v; maxTs = s.ts; }   // strict > keeps first occurrence
        if (s.v < min) { min = s.v; minTs = s.ts; }
      }
      const mean = sum / n;
      let sq = 0;
      for (const s of samples) sq += (s.v - mean) ** 2;
      const stdDev = n > 1 ? Math.sqrt(sq / n) : 0;

      // Percentage-unit columns (e.g. SOC) use the selected cutoff value
      // directly as the threshold, in percent — mean ± z·σ can leave the
      // 0–100% bounds (design §2.7). High cutoff 95 → threshold 95% (95),
      // low cutoff 5 → threshold 5% (5).
      const isPct = (m.unit ?? "") === "%";
      const highThreshold = isPct ? highCutoff : mean + HIGH_CUTOFF_Z[highCutoff] * stdDev;
      const lowThreshold = isPct ? lowCutoff : mean - LOW_CUTOFF_Z[lowCutoff] * stdDev;
      const method = isPct ? "cutoff" : "mean-sigma";

      stats.push({
        column: col,
        label: m.label,
        unit: m.unit ?? "",
        count: n,
        mean,
        stdDev,
        max: { value: max, timestamp: maxTs },
        min: { value: min, timestamp: minTs },
        high: { cutoff: highCutoff, threshold: highThreshold, avgDailyMinutes: avgDailyMinutes(samples, (v) => v > highThreshold), method },
        low: { cutoff: lowCutoff, threshold: lowThreshold, avgDailyMinutes: avgDailyMinutes(samples, (v) => v < lowThreshold), method },
      });
    }

    res.json({ stats });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Refresh database (run deye-logger.py)
// Lock management is delegated to the Python script — it owns deye_refresh.lock
app.post("/api/refresh", async (_req: express.Request, res: express.Response) => {
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
