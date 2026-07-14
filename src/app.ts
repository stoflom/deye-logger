/// <reference lib="dom" />

// ============================================================
// Deye Logger Viewer — Browser-side SQLite viewer using sql.js
// ============================================================

// sql.js types (minimal)
interface SQLJsDatabase {
  exec(sql: string): { columns: string[]; values: unknown[][] }[];
  close(): void;
}

declare const initSqlJs: (
  opts: { locateFile: (file: string) => string },
) => Promise<{
  Database: new (buffer: Uint8Array) => SQLJsDatabase;
}>;


interface Database {
  exec(sql: string): unknown[][];
  select(sql: string): Record<string, unknown>[];
  close(): void;
}

// ------------------------------------------------------------------
// Column metadata
// ------------------------------------------------------------------
interface ColumnMeta {
  name: string;
  label: string;
}

// ------------------------------------------------------------------
// Persistence helpers
// ------------------------------------------------------------------
const COLUMNS_KEY = "deye_selected_columns";

const DEFAULT_COLUMNS = [
  "device_timestamp",
  "daily_energy",
  "total_energy",
  "current_power",
  "battery_soc",
  "battery_voltage",
  "battery_current",
  "grid_power",
  "grid_voltage",
  "pv1_voltage",
  "pv1_current",
  "pv1_power",
  "pv2_voltage",
  "pv2_current",
  "pv2_power",
];

function loadSelectedColumns(): Set<string> {
  try {
    const stored = localStorage.getItem(COLUMNS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as string[];
      if (Array.isArray(parsed) && parsed.length > 0) {
        return new Set(parsed);
      }
    }
  } catch {
    // corrupt data — fall through to defaults
  }
  return new Set(DEFAULT_COLUMNS);
}

function saveSelectedColumns() {
  try {
    localStorage.setItem(COLUMNS_KEY, JSON.stringify([...state.selectedColumns]));
  } catch {
    // quota exceeded — silently ignore
  }
}

// ------------------------------------------------------------------
// State
// ------------------------------------------------------------------
const state = {
  db: null as Database | null,
  columns: [] as ColumnMeta[],
  selectedColumns: loadSelectedColumns(),
  selectedDate: new Date().toISOString().slice(0, 10),
  data: [] as Array<Record<string, unknown>>,
};

// ------------------------------------------------------------------
// DOM refs
// ------------------------------------------------------------------
const dateInput = document.getElementById("date-input") as HTMLInputElement;
const loadBtn = document.getElementById("load-btn") as HTMLButtonElement;
const refreshBtn = document.getElementById("refresh-btn") as HTMLButtonElement;
const columnsPanel = document.getElementById("columns-panel") as HTMLElement;
const tableBody = document.getElementById(
  "table-body",
) as HTMLTableSectionElement;
const rowCount = document.getElementById("row-count") as HTMLElement;
const loadingEl = document.getElementById("loading") as HTMLElement;
const errorEl = document.getElementById("error") as HTMLElement;
const tableWrap = document.getElementById("table-wrap") as HTMLElement;
const selectAllBtn = document.getElementById(
  "select-all-btn",
) as HTMLButtonElement;
const deselectAllBtn = document.getElementById(
  "deselect-all-btn",
) as HTMLButtonElement;
const columnsToggle = document.getElementById(
  "columns-toggle",
) as HTMLButtonElement;
const tableHead = document.getElementById(
  "table-head",
) as HTMLTableSectionElement;

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------
function setVisibility(el: HTMLElement, show: boolean) {
  el.style.display = show ? "block" : "none";
}

function formatValue(_col: ColumnMeta, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    // Keep some precision for voltage/power etc
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function showLoading(show: boolean) {
  setVisibility(loadingEl, show);
}

function showError(msg: string) {
  errorEl.textContent = msg;
  setVisibility(errorEl, true);
  setVisibility(loadingEl, false);
}

function hideError() {
  setVisibility(errorEl, false);
}

// ------------------------------------------------------------------
// Column checkboxes
// ------------------------------------------------------------------
function renderColumnCheckboxes() {
  columnsPanel.innerHTML = "";
  const grid = document.createElement("div");
  grid.style.cssText =
    "display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:4px;max-height:280px;overflow-y:auto;padding:4px;";

  state.columns.forEach((col) => {
    const label = document.createElement("label");
    label.style.cssText =
      "display:flex;align-items:center;gap:6px;padding:4px 8px;border-radius:4px;cursor:pointer;font-size:13px;user-select:none;";
    label.onmouseover = () => (label.style.background = "#e8edf2");
    label.onmouseout = () => (label.style.background = "transparent");

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = state.selectedColumns.has(col.name);
    cb.style.cursor = "pointer";
    cb.onchange = () => {
      if (cb.checked) {
        state.selectedColumns.add(col.name);
      } else {
        state.selectedColumns.delete(col.name);
      }
      saveSelectedColumns();
    };

    label.appendChild(cb);
    label.appendChild(document.createTextNode(col.label));
    grid.appendChild(label);
  });

  columnsPanel.appendChild(grid);
}

selectAllBtn.onclick = () => {
  state.selectedColumns = new Set(state.columns.map((c) => c.name));
  saveSelectedColumns();
  renderColumnCheckboxes();
};

deselectAllBtn.onclick = () => {
  state.selectedColumns.clear();
  saveSelectedColumns();
  renderColumnCheckboxes();
};

columnsToggle.addEventListener("click", () => {
  const isVisible = columnsPanel.classList.toggle("visible");
  columnsToggle.classList.toggle("active", isVisible);
  columnsToggle.textContent = isVisible ? "✕ Columns" : "☰ Columns";
});

// ------------------------------------------------------------------
// Load DB
// ------------------------------------------------------------------
async function loadColumns() {
  const res = await fetch("/api/columns");
  state.columns = await res.json();
  renderColumnCheckboxes();
}

async function openDatabase() {
  showLoading(true);
  hideError();

  // Close previous in-memory DB to avoid leaking ~25MB per refresh
  if (state.db) {
    state.db.close();
    state.db = null;
  }

  try {
    // Initialize sql.js
    const SQLModule = await initSqlJs({
      locateFile: (file: string) => `/node_modules/sql.js/dist/${file}`,
    });

    // Fetch the DB file
    const dbRes = await fetch("/db");
    if (!dbRes.ok) throw new Error("Failed to download database");
    const dbBuffer = await dbRes.arrayBuffer();

    const sqlDb = new SQLModule.Database(new Uint8Array(dbBuffer));

    // Wrap in our simple interface
    state.db = {
      exec: (sql: string) => {
        const results = sqlDb.exec(sql);
        return results.map(
          (r: { values: unknown[][] }) => r.values,
        );
      },
      select: (sql: string) => {
        const results = sqlDb.exec(sql);
        if (!results || results.length === 0) return [];
        const first = results[0];
        const columns = first.columns.slice();
        return first.values.map((row: unknown[]) => {
          const obj: Record<string, unknown> = {};
          columns.forEach((col: string, i: number) => {
            obj[col] = row[i];
          });
          return obj;
        });
      },
      close: () => sqlDb.close(),
    } as unknown as Database;
  } catch (err) {
    showError(`Failed to open database: ${err}`);
  }
}

// ------------------------------------------------------------------
// Query and render
// ------------------------------------------------------------------
async function loadData(refreshDb = false) {
  if (!state.db || refreshDb) {
    await openDatabase();
    if (!state.db) return;
  }

  const from = `${state.selectedDate} 00:00:00`;
  const to = `${state.selectedDate} 23:59:59`;
  const cols = [...state.selectedColumns];
  if (cols.length === 0) {
    showError("Select at least one column to display.");
    return;
  }

  const colList = cols.map((c) => `"${c}"`).join(", ");
  const sql =
    `SELECT ${colList} FROM inverter_telemetry WHERE device_timestamp >= '${from}' AND device_timestamp <= '${to}' ORDER BY device_timestamp ASC;`;

  showLoading(true);

  try {
    state.data = state.db.select(sql);
    tableBody.innerHTML = "";
    tableHead.innerHTML = "";
    if (state.data.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = cols.length;
      td.style.cssText = "text-align:center;padding:24px;color:#666;";
      td.textContent = `No data for ${state.selectedDate}`;
      tr.appendChild(td);
      tableBody.appendChild(tr);
    } else {
      const headerRow = document.createElement("tr");
      headerRow.style.cssText =
        "position:sticky;top:0;z-index:10;background:#2d374e;";
      cols.forEach((colName) => {
        const meta = state.columns.find((c) => c.name === colName);
        const th = document.createElement("th");
        th.textContent = meta ? meta.label : colName;
        th.style.cssText =
          "padding:10px 12px;text-align:right;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.03em;color:#a0aec0;white-space:nowrap;";
        headerRow.appendChild(th);
      });
      tableHead.appendChild(headerRow);

      // Body
      state.data.forEach((row, idx) => {
        const tr = document.createElement("tr");
        tr.style.cssText = idx % 2 === 0
          ? "background:#f7fafc;"
          : "background:#ffffff;";
        tr.onmouseover = () => (tr.style.background = "#edf2f7");
        tr.onmouseout =
          () => (tr.style.background = idx % 2 === 0 ? "#f7fafc" : "#ffffff");

        cols.forEach((colName) => {
          const td = document.createElement("td");
          td.textContent = formatValue(
            state.columns.find((c) => c.name === colName)!,
            row[colName],
          );
          td.style.cssText =
            "padding:8px 12px;text-align:right;font-variant-numeric:tabular-nums;font-size:13px;white-space:nowrap;";
          tr.appendChild(td);
        });
        tableBody.appendChild(tr);
      });

      // Update count
      rowCount.textContent = `${state.data.length.toLocaleString()} rows`;
    }

    setVisibility(tableWrap, true);
  } catch (err) {
    showError(`Query error: ${err}`);
  }

  showLoading(false);
}

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------
async function init() {
  dateInput.value = state.selectedDate;
  dateInput.addEventListener("change", () => {
    state.selectedDate = dateInput.value;
  });
  loadBtn.disabled = true;
  loadBtn.textContent = "Initializing...";

  try {
    // Fetch date range for picker validation
    const datesRes = await fetch("/api/dates");
    const dates: { min: string; max: string } = await datesRes.json();
    if (dates.min) dateInput.min = dates.min;
    if (dates.max) dateInput.max = dates.max;

    await loadColumns();
    await openDatabase();
    loadBtn.disabled = false;
    loadBtn.textContent = "Load Data";
    loadData();
  } catch (err) {
    showError(`Initialization error: ${err}`);
  }
}

// Bind buttons
loadBtn.addEventListener("click", loadData);

refreshBtn.addEventListener("click", async () => {
  refreshBtn.disabled = true;
  refreshBtn.textContent = "⟳";
  hideError();
  try {
    const res = await fetch("/api/refresh", { method: "POST" });
    const result: { success: boolean; code: number; output: string; error: string } = await res.json();
    if (result.success) {
      console.log("Refresh output:", result.output);
      errorEl.textContent = "";
      errorEl.style.display = "none";
      // Re-load data automatically
      await loadData(true);
    } else {
      showError(`Refresh failed (exit ${result.code}): ${result.error || result.output}`);
    }
  } catch (err) {
    showError(`Refresh error: ${err}`);
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.textContent = "↻ Refresh";
  }
});

init();
