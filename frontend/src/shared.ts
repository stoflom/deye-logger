// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// Shared state, DOM refs, URL helpers, panel management
// ============================================================

import { GridApi } from "ag-grid-community";
import { Chart } from "chart.js";

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------
export interface ColumnMeta {
  name: string;
  label: string;
}

export type ViewMode = "chart" | "grid" | "histogram" | "histogram-grid";

// ------------------------------------------------------------------
// Persistence helpers — localStorage
// ------------------------------------------------------------------
const SELECTED_COLUMNS_KEY = "deye_selected_columns";
const CUSTOM_DEFAULT_KEY = "deye_custom_default_columns";

export const DEFAULT_COLUMN_NAMES: string[] = [
  "current_power",
  "total_dc_power",
  "battery_power",
  "grid_power",
  "battery_soc",
];

function parseColumnSet(raw: string | null): Set<string> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as string[];
    if (Array.isArray(parsed) && parsed.length > 0) {
      const set = new Set(parsed);
      set.add("device_timestamp");
      return set;
    }
  } catch {
    // corrupt data — ignore
  }
  return null;
}

export function getDefaultColumnNames(): Set<string> {
  // custom default → session default → hardcoded default
  const custom = parseColumnSet(localStorage.getItem(CUSTOM_DEFAULT_KEY));
  if (custom) return custom;
  const session = parseColumnSet(localStorage.getItem(SELECTED_COLUMNS_KEY));
  if (session) return session;
  const def = new Set(DEFAULT_COLUMN_NAMES);
  def.add("device_timestamp");
  return def;
}

export function saveSelectedColumnNames(columnNames: Set<string>): void {
  try {
    localStorage.setItem(SELECTED_COLUMNS_KEY, JSON.stringify([...columnNames]));
  } catch {
    // quota exceeded — silently ignore
  }
}

export function saveCustomDefaultColumns(columnNames: Set<string>): void {
  try {
    localStorage.setItem(CUSTOM_DEFAULT_KEY, JSON.stringify([...columnNames]));
  } catch {
    // quota exceeded — silently ignore
  }
}

export function resetCustomDefaultColumns(): void {
  localStorage.removeItem(CUSTOM_DEFAULT_KEY);
}

// ------------------------------------------------------------------
// Global application state
// ------------------------------------------------------------------
export const appState = {
  columnMetadata: [] as ColumnMeta[],
  selectedColumnNames: getDefaultColumnNames(),
  dateRangeFrom: "",
  dateRangeTo: "",
  minAvailableDate: "",
  maxAvailableDate: "",
  rawDataRows: [] as Array<Record<string, unknown>>,
  binnedDataRows: [] as Array<Record<string, unknown>>,
  rawDataGridApi: null as GridApi | null,
  rawDataChartInstance: null as Chart | null,
  activeView: "chart" as ViewMode,
};

// ------------------------------------------------------------------
// DOM refs — runtime-guarded
// ------------------------------------------------------------------
function getRequiredEl<T extends HTMLElement>(id: string, selector: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Required DOM element not found: ${selector}`);
  return el as T;
}

// --- Inputs ---
export const dateFromInput = getRequiredEl<HTMLInputElement>("date-from", "#date-from");
export const dateToInput = getRequiredEl<HTMLInputElement>("date-to", "#date-to");

// --- Navigation buttons ---
export const prevDayBtn = getRequiredEl<HTMLButtonElement>("prev-day", "#prev-day");
export const nextDayBtn = getRequiredEl<HTMLButtonElement>("next-day", "#next-day");
export const todayBtn = getRequiredEl<HTMLButtonElement>("today-btn", "#today-btn");

// --- Control buttons ---
export const refreshBtn = getRequiredEl<HTMLButtonElement>("refresh-btn", "#refresh-btn");
export const columnsToggleBtn = getRequiredEl<HTMLButtonElement>("columns-toggle", "#columns-toggle");
export const viewToggleBtn = getRequiredEl<HTMLButtonElement>("view-toggle", "#view-toggle");
export const histogramToggleBtn = getRequiredEl<HTMLButtonElement>("histogram-btn", "#histogram-btn");
export const exportCsvBtn = getRequiredEl<HTMLButtonElement>("export-btn", "#export-btn");
export const splitBtn = getRequiredEl<HTMLButtonElement>("split-btn", "#split-btn");
export const binSizeSelect = getRequiredEl<HTMLSelectElement>("bin-size-select", "#bin-size-select");

// --- Panels ---
export const waitingViewPanel = getRequiredEl<HTMLElement>("waiting-view", "#waiting-view");
export const waitingViewTextEl = getRequiredEl<HTMLElement>("waiting-text", "#waiting-text");
export const errorViewPanel = getRequiredEl<HTMLElement>("error-view", "#error-view");
export const errorViewMessageEl = getRequiredEl<HTMLElement>("error-message", "#error-message");
export const errorViewCloseBtn = getRequiredEl<HTMLButtonElement>("error-close-btn", "#error-close-btn");
export const columnsViewPanel = getRequiredEl<HTMLElement>("columns-view", "#columns-view");
export const columnsViewInner = getRequiredEl<HTMLElement>("columns-view-inner", "#columns-view-inner");
export const histogramPanel = getRequiredEl<HTMLElement>("histogram-panel", "#histogram-panel");
export const summaryCardsPanel = getRequiredEl<HTMLElement>("summary-cards", "#summary-cards");

// --- Data views ---
export const rawDataChartView = getRequiredEl<HTMLElement>("raw-data-chart-view", "#raw-data-chart-view");
export const rawDataGridView = getRequiredEl<HTMLElement>("raw-data-grid-view", "#raw-data-grid-view");
export const histogramView = getRequiredEl<HTMLElement>("histogram-view", "#histogram-view");
export const histogramGridView = getRequiredEl<HTMLElement>("histogram-grid-view", "#histogram-grid-view");
export const splitHistogramView = getRequiredEl<HTMLElement>("split-histogram-view", "#split-histogram-view");
export const splitHistogramScroll = getRequiredEl<HTMLElement>("split-histogram-scroll", "#split-histogram-scroll");

// --- Grid containers ---
export const rawDataGridContainer = getRequiredEl<HTMLElement>("grid-container", "#grid-container");
export const histogramGridContainer = getRequiredEl<HTMLElement>("histogram-grid-container", "#histogram-grid-container");

// --- Canvas elements ---
export const rawDataChartCanvas = getRequiredEl<HTMLCanvasElement>("chart-canvas", "#chart-canvas");
export const histogramChartCanvas = getRequiredEl<HTMLCanvasElement>("histogram-canvas", "#histogram-canvas");

// --- Status bar ---
export const rowCountEl = getRequiredEl<HTMLElement>("row-count", "#row-count");
export const versionBadgeEl = getRequiredEl<HTMLElement>("version-badge", "#version-badge");
export const viewLabelEl = getRequiredEl<HTMLElement>("view-label", "#view-label");

// ------------------------------------------------------------------
// Waiting view API
// ------------------------------------------------------------------
export const waitingView = {
  show(): void {
    waitingViewPanel.classList.add("visible");
  },
  hide(): void {
    waitingViewPanel.classList.remove("visible");
  },
  setText(text: string): void {
    waitingViewTextEl.textContent = text;
  },
};

// ------------------------------------------------------------------
// Error view API
// ------------------------------------------------------------------
export const errorView = {
  show(message: string): void {
    errorViewMessageEl.textContent = message;
    errorViewPanel.classList.add("visible");
  },
  hide(): void {
    errorViewPanel.classList.remove("visible");
  },
};

// ------------------------------------------------------------------
// Panel visibility — mutual exclusion
// Exactly one content panel is visible at a time.
// Called by setView at step 2 and step 4.
// ------------------------------------------------------------------
const ALL_PANELS = [
  waitingViewPanel,
  errorViewPanel,
  columnsViewPanel,
  rawDataChartView,
  rawDataGridView,
  histogramView,
  histogramGridView,
  splitHistogramView,
];

const PANEL_ID_MAP: Record<string, HTMLElement> = {
  waiting: waitingViewPanel,
  error: errorViewPanel,
  columns: columnsViewPanel,
  "raw-data-chart": rawDataChartView,
  "raw-data-grid": rawDataGridView,
  histogram: histogramView,
  "histogram-grid": histogramGridView,
  "split-histogram": splitHistogramView,
};

/** Hide all content panels and show only the specified one */
export function showPanel(panelId: string): void {
  ALL_PANELS.forEach((panel) => panel.classList.remove("visible"));
  const target = PANEL_ID_MAP[panelId];
  if (target) target.classList.add("visible");
}

/** Hide all data view panels (keep waiting/error visible if needed) */
export function hideAllDataPanels(): void {
  [
    columnsViewPanel,
    rawDataChartView,
    rawDataGridView,
    histogramView,
    histogramGridView,
    splitHistogramView,
  ].forEach((panel) => panel.classList.remove("visible"));
}

// ------------------------------------------------------------------
// Button disable/enable — managed exclusively by setView
// ------------------------------------------------------------------
const ALL_CONTROLS: (HTMLElement | null)[] = [
  dateFromInput,
  dateToInput,
  prevDayBtn,
  nextDayBtn,
  todayBtn,
  refreshBtn,
  columnsToggleBtn,
  viewToggleBtn,
  histogramToggleBtn,
  exportCsvBtn,
  binSizeSelect,
  splitBtn,
];

function setElementDisabled(el: HTMLElement | null, disabled: boolean): void {
  if (!el) return;
  try {
    (el as HTMLButtonElement | HTMLInputElement | HTMLSelectElement).disabled = disabled;
  } catch {
    // ignore
  }
}

export function disableAllControls(): void {
  ALL_CONTROLS.forEach((el) => setElementDisabled(el, true));
}

export function enableAllControls(): void {
  ALL_CONTROLS.forEach((el) => setElementDisabled(el, false));
}

/**
 * Enable all controls except those listed by their variable name key.
 * Used for columns-view where columnsToggleBtn must stay enabled.
 */
export function enableControlsExcept(exceptKeys: string[]): void {
  const controlMap: Record<string, HTMLElement | null> = {
    dateFrom: dateFromInput,
    dateTo: dateToInput,
    prevDay: prevDayBtn,
    nextDay: nextDayBtn,
    today: todayBtn,
    refresh: refreshBtn,
    columnsToggle: columnsToggleBtn,
    viewToggle: viewToggleBtn,
    histogramToggle: histogramToggleBtn,
    export: exportCsvBtn,
    binSize: binSizeSelect,
    split: splitBtn,
  };

  ALL_CONTROLS.forEach((el) => {
    const key = Object.entries(controlMap).find(([, v]) => v === el)?.[0];
    if (key && exceptKeys.includes(key)) {
      setElementDisabled(el, false);
    } else {
      setElementDisabled(el, true);
    }
  });
}

// ------------------------------------------------------------------
// Summary cards visibility
// ------------------------------------------------------------------
export function showSummaryCards(): void {
  summaryCardsPanel.classList.add("visible");
}

export function hideSummaryCards(): void {
  summaryCardsPanel.classList.remove("visible");
}

// ------------------------------------------------------------------
// Histogram panel visibility
// ------------------------------------------------------------------
export function showHistogramPanel(): void {
  histogramPanel.classList.add("visible");
  document.body.classList.add("has-histogram-panel");
}

export function hideHistogramPanel(): void {
  histogramPanel.classList.remove("visible");
  document.body.classList.remove("has-histogram-panel");
}

// ------------------------------------------------------------------
// Utility helpers
// ------------------------------------------------------------------
export function fmtNum(v: unknown): string {
  if (v === null || v === undefined || typeof v !== "number") return "\u2014";
  return v.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export function isDateRange(): boolean {
  return appState.dateRangeFrom !== appState.dateRangeTo;
}

export function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function updateNavButtonStates(): void {
  prevDayBtn.disabled = !appState.minAvailableDate || appState.dateRangeFrom <= appState.minAvailableDate;
  // allow navigating to today even if maxAvailableDate is in the past (no data yet)
  const effectiveMax = appState.maxAvailableDate > todayStr() ? appState.maxAvailableDate : todayStr();
  nextDayBtn.disabled = !appState.maxAvailableDate || appState.dateRangeTo >= effectiveMax;
}

export function extractUnit(label: string): string {
  const match = label.match(/\((.+)\)$/);
  return match ? match[1] : "";
}

export function getNumericColumnNames(
  selectedNames: Set<string>,
  dataRows: Array<Record<string, unknown>>,
  metadata: ColumnMeta[],
  binnedMaxValues?: Map<string, { value: number; timestamp: string }> | null,
): string[] {
  const cols = [...selectedNames];
  return cols.filter((col) => {
    if (col === "device_timestamp" || col === "inverter_sn" || col === "fetch_timestamp") return false;
    if (binnedMaxValues) {
      const meta = metadata.find((c) => c.name === col);
      return binnedMaxValues.has(meta?.label ?? col);
    }
    return dataRows.some((row) => typeof row[col] === "number" && row[col] !== 0);
  });
}

// ------------------------------------------------------------------
// URL state — parse and serialize view parameters
// ------------------------------------------------------------------
export interface ParsedUrlState {
  view: ViewMode;
  dateFrom: string;
  dateTo: string;
  binSize: string;
  isSplit: boolean;
}

export function getUrlState(): ParsedUrlState {
  const params = new URLSearchParams(window.location.search);

  const validViews: ViewMode[] = ["chart", "grid", "histogram", "histogram-grid"];
  const rawView = params.get("view");
  const view = (rawView as ViewMode) ?? "chart";
  if (!validViews.includes(view)) {
    const today = todayStr();
    return { view: "chart", dateFrom: appState.dateRangeFrom || today, dateTo: appState.dateRangeTo || today, binSize: "15", isSplit: false };
  }

  const dateFrom = params.get("from") || params.get("date") || appState.dateRangeFrom || todayStr();
  const dateTo = params.get("to") || params.get("date") || appState.dateRangeTo || todayStr();
  const binSize = params.get("binSize") || "15";
  const isSplit = params.get("split") === "1";

  return { view, dateFrom, dateTo, binSize, isSplit };
}

export function buildUrlString(
  view: string,
  from: string,
  to: string,
  opts?: { binSize?: string; isSplit?: boolean },
): string {
  const params = new URLSearchParams();
  params.set("view", view);

  if (from !== to) {
    params.set("from", from);
    params.set("to", to);
  } else {
    params.set("date", from);
  }

  const binSize = opts?.binSize;
  if (binSize && binSize !== "15") {
    params.set("binSize", binSize);
  }

  if (opts?.isSplit) {
    params.set("split", "1");
  }

  const query = params.toString();
  return query ? `?${query}` : window.location.pathname;
}

// ------------------------------------------------------------------
// Fetch helper with timeout
// ------------------------------------------------------------------
export async function fetchWithTimeout(url: string, timeoutMs: number, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const signal = controller.signal;
    const res = await fetch(url, { ...init, signal });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.error || `Server error ${res.status}`);
    }
    return res;
  } catch (err) {
    if (err && typeof err === "object" && "name" in err && err.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ------------------------------------------------------------------
// Renderer result type
// ------------------------------------------------------------------
export interface RenderOk {
  ok: true;
}
