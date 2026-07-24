// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

/// <reference lib="dom" />

export const FRONTEND_VERSION = "1.0.0";

import { ModuleRegistry } from "ag-grid-community";
import { CsvExportModule, ColumnAutoSizeModule, TextFilterModule, NumberFilterModule, DateFilterModule } from "ag-grid-community";
import { Chart, registerables } from "chart.js";

ModuleRegistry.registerModules([CsvExportModule, ColumnAutoSizeModule, TextFilterModule, NumberFilterModule, DateFilterModule]);
Chart.register(...registerables);

import {
  appState,
  dateFromInput,
  dateToInput,
  refreshBtn,
  columnsToggleBtn,
  viewToggleBtn,
  histogramToggleBtn,
  binSizeSelect,
  exportCsvBtn,
  splitBtn,
  versionBadgeEl,
  viewLabelEl,
  rowCountEl,
  waitingView,
  errorView,
  errorViewCloseBtn,
  columnsViewPanel,
  showPanel,
  hideAllDataPanels,
  showSummaryCards,
  hideSummaryCards,
  showHistogramPanel,
  hideHistogramPanel,
  disableAllControls,
  enableAllControls,
  enableControlsExcept,
  isDateRange,
  todayStr,
  updateNavButtonStates,
  buildUrlString,
  getUrlState,
  fetchWithTimeout,
  saveSelectedColumnNames,
  ViewMode,
  RenderOk,
} from "./shared";

import { renderRawDataChart, updateSummaryCards } from "./chart";
import { initRawDataGrid, updateRawDataGrid, initHistogramGrid, updateHistogramGrid, getHistogramGridApi, buildHistogramGridCols } from "./data-grid";
import { renderHistogramChart, histogramMaxAverageValues, fetchHistogramData, showSplitHistogram, isSplitModeActive, cleanupSplitMode, histogramResultToRows } from "./histogram-chart";
import { renderColumnCheckboxes } from "./columns";
import { wireDateNavigation } from "./navigation";

// ------------------------------------------------------------------
// setView options
// ------------------------------------------------------------------
interface SetViewOptions {
  replace?: boolean;   // use replaceState instead of pushState (default: false)
  refresh?: boolean;   // transient — trigger backend refresh before rendering
  columns?: boolean;   // transient — show columns selection panel
  split?: boolean;     // URL-param — split histogram mode
}

// ------------------------------------------------------------------
// Pure data fetcher — no rendering, no control management.
// Returns raw data rows; caller is responsible for lifecycle.
// ------------------------------------------------------------------
async function fetchRawDataRows(updateWaiting: (text: string) => void): Promise<Record<string, unknown>[]> {
  updateWaiting("Fetching raw data…");

  const cols = [...appState.selectedColumnNames];
  if (!cols.includes("device_timestamp")) {
    cols.unshift("device_timestamp");
  }
  if (cols.length === 0) {
    throw new Error("Select at least one column to display.");
  }

  const range = isDateRange();
  const from = appState.dateRangeFrom;
  const to = appState.dateRangeTo;

  if (range && (!from || !to)) {
    throw new Error("Select start and end dates.");
  }

  let url: string;
  if (range) {
    url = `/api/data-range?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&columns=${encodeURIComponent(cols.join(","))}`;
  } else {
    url = `/api/data?date=${encodeURIComponent(to)}&columns=${encodeURIComponent(cols.join(","))}`;
  }

  const res = await fetchWithTimeout(url, 30_000);
  return (await res.json() as { rows: Record<string, unknown>[] }).rows;
}

// ------------------------------------------------------------------
// Renderers — pure render, return RenderOk or throw
// Each renderer calls updateWaiting() before async operations.
// ------------------------------------------------------------------
async function renderRawDataChartView(updateWaiting: (text: string) => void): Promise<RenderOk> {
  const rows = await fetchRawDataRows(updateWaiting);
  appState.rawDataRows = rows;
  rowCountEl.textContent = `${rows.length.toLocaleString()} rows`;

  updateSummaryCards(null);
  updateWaiting("Drawing chart…");
  renderRawDataChart();
  return { ok: true };
}

async function renderRawDataGridView(updateWaiting: (text: string) => void): Promise<RenderOk> {
  const rows = await fetchRawDataRows(updateWaiting);
  appState.rawDataRows = rows;
  rowCountEl.textContent = `${rows.length.toLocaleString()} rows`;

  updateSummaryCards(null);
  updateWaiting("Building grid…");
  if (!appState.rawDataGridApi) initRawDataGrid(); else updateRawDataGrid();
  return { ok: true };
}

async function renderHistogramChartView(updateWaiting: (text: string) => void): Promise<RenderOk> {
  await renderHistogramChart(updateWaiting);
  updateSummaryCards(histogramMaxAverageValues ?? null);
  rowCountEl.textContent = `${histogramMaxAverageValues?.size ?? 0} metrics`;
  return { ok: true };
}

async function renderHistogramGridView(updateWaiting: (text: string) => void): Promise<RenderOk> {
  updateWaiting("Fetching histogram data…");
  const result = await fetchHistogramData();
  updateWaiting("Building grid…");

  const rows = histogramResultToRows(result);
  rowCountEl.textContent = `${rows.length.toLocaleString()} bins`;

  updateSummaryCards(histogramMaxAverageValues ?? null);

  const colDefs = buildHistogramGridCols(result.datasets);
  const histogramGridApi = getHistogramGridApi();
  if (!histogramGridApi) {
    initHistogramGrid(colDefs, rows);
  } else {
    updateHistogramGrid(colDefs, rows);
  }
  return { ok: true };
}

async function renderSplitHistogramView(updateWaiting: (text: string) => void): Promise<RenderOk> {
  await renderHistogramChart(updateWaiting);
  updateSummaryCards(histogramMaxAverageValues ?? null);
  updateWaiting("Splitting charts…");
  await showSplitHistogram();
  return { ok: true };
}

async function renderColumnsView(updateWaiting: (text: string) => void): Promise<RenderOk> {
  updateWaiting("Loading column definitions…");
  // Fetch metadata if not yet loaded
  if (appState.columnMetadata.length === 0) {
    const res = await fetchWithTimeout("/api/columns", 10_000);
    appState.columnMetadata = await res.json();
  }
  updateWaiting("Rendering column panel…");
  renderColumnCheckboxes();
  return { ok: true };
}

async function renderRefreshView(updateWaiting: (text: string) => void): Promise<RenderOk> {
  updateWaiting("Querying Deye Cloud…");
  const res = await fetchWithTimeout("/api/refresh", 120_000, { method: "POST" });
  const result: { success: boolean; code: number; output: string; error: string } = await res.json();

  if (!result.success) {
    throw new Error(`Refresh failed (exit ${result.code}): ${result.error || result.output}`);
  }

  updateWaiting("Fetching latest dates…");
  const datesRes = await fetchWithTimeout("/api/dates", 10_000);
  const dates: { min: string; max: string } = await datesRes.json();
  if (dates.min) {
    dateFromInput.min = dates.min;
    dateToInput.min = dates.min;
    appState.minAvailableDate = dates.min;
  }
  if (dates.max) {
    dateFromInput.max = dates.max;
    dateToInput.max = dates.max;
    appState.maxAvailableDate = dates.max;
  }
  return { ok: true };
}

// ------------------------------------------------------------------
// Button label updater — called by setView at step 5
// ------------------------------------------------------------------
function updateButtonLabels(view: ViewMode, isSplit: boolean): void {
  const isAnyGrid = view === "grid" || view === "histogram-grid";
  const isHistogramMode = view === "histogram" || view === "histogram-grid";

  // Export button — visible only in grid views
  exportCsvBtn.style.display = isAnyGrid ? "" : "none";

  // Histogram toggle button
  histogramToggleBtn.style.display = "";
  histogramToggleBtn.classList.toggle("active", isHistogramMode);

  if (isHistogramMode) {
    histogramToggleBtn.textContent = "\uD83D\uDCAB Raw Data";
    histogramToggleBtn.title = "Switch back to raw data view";
  } else {
    histogramToggleBtn.textContent = "\uD83D\uDCCA Histogram";
    histogramToggleBtn.title = "Show binned average histogram";
  }

  // View toggle button
  if (isHistogramMode) {
    viewToggleBtn.classList.toggle("active", true);
    viewToggleBtn.textContent = view === "histogram" ? "\uD83D\uDCCA Histogram Grid" : "\uD83D\uDCC8 Histogram Chart";
    viewToggleBtn.title = view === "histogram" ? "Switch to histogram grid" : "Switch to histogram chart";
  } else {
    viewToggleBtn.classList.toggle("active", isAnyGrid);
    viewToggleBtn.textContent = view === "chart" ? "\uD83D\uDCAB Data Grid" : "\uD83D\uDCC8 Chart";
    viewToggleBtn.title = view === "chart" ? "Switch to data grid" : "Switch to chart";
  }

  // Split button — visible only in histogram (not histogram-grid)
  splitBtn.style.display = view === "histogram" ? "" : "none";
  splitBtn.textContent = isSplit ? "Combine" : "Split";
  splitBtn.title = isSplit ? "Combine into single chart" : "Split into individual charts";

  // Histogram panel — visible in histogram modes
  if (isHistogramMode) {
    showHistogramPanel();
  } else {
    hideHistogramPanel();
  }

  // Update bin size from state
  // (handled by caller setting binSizeSelect.value)
}

// ------------------------------------------------------------------
// setView — single entry point with unified lifecycle
// ------------------------------------------------------------------
async function setView(
  view: ViewMode,
  opts: SetViewOptions = {},
): Promise<void> {
  const { replace = false, refresh: doRefresh = false, columns: showColumns = false, split: optSplit } = opts;

  // STEP 1: Disable all buttons (debounce protection)
  disableAllControls();

  // STEP 2: Show waiting-view, hide all other panels
  hideAllDataPanels();
  hideSummaryCards();
  waitingView.show();
  waitingView.setText("Loading…");

  // Update state
  appState.activeView = view;

  try {
    // STEP 3: Determine render path from flags + state
    if (showColumns) {
      // --- Columns view (transient — no history push) ---
      await renderColumnsView((text) => waitingView.setText(text));

      // STEP 4a: Columns success
      waitingView.hide();
      showPanel("columns");
      columnsToggleBtn.textContent = "\u21BB Load Data";
      columnsToggleBtn.classList.add("active");
      enableControlsExcept(["refresh", "export", "viewToggle", "histogramToggle", "split", "binSize", "prevDay", "nextDay", "today"]);
      columnsToggleBtn.disabled = false;
      return;
    }

    if (doRefresh) {
      // --- Refresh view ---
      await renderRefreshView((text) => waitingView.setText(text));

      // Refresh succeeded — recursive call to render actual data view
      return setView(view, { replace });
    }

    // --- Normal data render ---
    const isHistogramMode = view === "histogram" || view === "histogram-grid";
    const split = optSplit ?? false;

    // Sync date inputs with state
    dateFromInput.value = appState.dateRangeFrom;
    dateToInput.value = appState.dateRangeTo;

    // Sync bin size select
    if (isHistogramMode) {
      // bin size is already synced from URL state by caller
    }

    // Dispatch to appropriate renderer
    if (view === "chart") {
      await renderRawDataChartView((text) => waitingView.setText(text));
    } else if (view === "grid") {
      await renderRawDataGridView((text) => waitingView.setText(text));
    } else if (view === "histogram-grid") {
      await renderHistogramGridView((text) => waitingView.setText(text));
    } else if (view === "histogram") {
      // Clean up split mode if coming from split
      if (isSplitModeActive()) {
        cleanupSplitMode();
      }
      if (split) {
        await renderSplitHistogramView((text) => waitingView.setText(text));
      } else {
        await renderHistogramChartView((text) => waitingView.setText(text));
      }
    }

    // No data warning for single-day non-range queries
    if (view === "chart" || view === "grid") {
      if (appState.rawDataRows.length === 0 && !isDateRange()) {
        // Show info via waiting view text briefly, but still succeed
      }
    }

    // STEP 4c: Normal data success
    waitingView.hide();

    // Show appropriate panel
    if (view === "chart") {
      showPanel("raw-data-chart");
    } else if (view === "grid") {
      showPanel("raw-data-grid");
    } else if (view === "histogram-grid") {
      showPanel("histogram-grid");
    } else if (view === "histogram" && split) {
      showPanel("split-histogram");
    } else if (view === "histogram") {
      showPanel("histogram");
    }

    showSummaryCards();

    // STEP 5: Update button labels and visibility
    updateButtonLabels(view, split);

    // Update view label in status bar
    const viewLabels: Record<ViewMode, string> = {
      chart: "Chart",
      grid: "Data Grid",
      histogram: "Histogram",
      "histogram-grid": "Histogram Grid",
    };
    viewLabelEl.textContent = viewLabels[view] ?? view;

    // Push URL history
    const url = buildUrlString(
      view,
      appState.dateRangeFrom,
      appState.dateRangeTo,
      {
        binSize: isHistogramMode ? binSizeSelect.value : undefined,
        isSplit: split,
      },
    );
    const historyMethod = replace ? history.replaceState : history.pushState;
    historyMethod.call(history, { view, isSplit: split }, "", url);

    // Re-enable all controls
    enableAllControls();
    updateNavButtonStates();

  } catch (err) {
    // STEP 4d: Error — show error-view
    waitingView.hide();
    hideAllDataPanels();
    hideSummaryCards();

    const message = err instanceof Error ? err.message : String(err);

    // Push error to history
    history.pushState(
      { error: true, errorMessage: message, view },
      "",
      window.location.pathname,
    );

    errorView.show(message);
    disableAllControls();
    errorViewCloseBtn.disabled = false;
  }
}

// ------------------------------------------------------------------
// Button handlers — all route through setView
// ------------------------------------------------------------------

// View toggle: chart <-> grid, histogram <-> histogram-grid
viewToggleBtn.addEventListener("click", () => {
  const v = appState.activeView;
  if (v === "chart") setView("grid");
  else if (v === "grid") setView("chart");
  else if (v === "histogram") setView("histogram-grid");
  else if (v === "histogram-grid") setView("histogram");
});

// Histogram toggle: normal mode <-> histogram mode
histogramToggleBtn.addEventListener("click", () => {
  const v = appState.activeView;
  if (v === "chart" || v === "histogram") {
    setView(v === "chart" ? "histogram" : "chart");
  } else {
    setView(v === "grid" ? "histogram-grid" : "grid");
  }
});

// Split/combine toggle (histogram only)
splitBtn.addEventListener("click", () => {
  if (appState.activeView === "histogram") {
    const params = new URLSearchParams(window.location.search);
    const currentSplit = params.get("split") === "1";
    setView("histogram", { split: !currentSplit });
  }
});

// Bin size change — re-render current histogram view
binSizeSelect.addEventListener("change", () => {
  if (appState.activeView === "histogram" || appState.activeView === "histogram-grid") {
    const params = new URLSearchParams(window.location.search);
    const currentSplit = params.get("split") === "1";
    setView(appState.activeView, { split: currentSplit });
  }
});

// CSV export — stateless action
exportCsvBtn.addEventListener("click", () => {
  const api = appState.activeView === "histogram-grid" ? getHistogramGridApi() : appState.rawDataGridApi;
  if (api) {
    const label = isDateRange() ? `${appState.dateRangeFrom}_to_${appState.dateRangeTo}` : appState.dateRangeTo;
    const prefix = appState.activeView === "histogram-grid" ? "deye-histogram-" : "deye-data-";
    api.exportDataAsCsv({
      fileName: `${prefix}${label}.csv`,
    });
  }
});

// Refresh button — routes through setView with refresh flag
refreshBtn.addEventListener("click", () => {
  setView(appState.activeView, { refresh: true });
});

// Columns toggle — open (transient) or close (triggers data re-render)
columnsToggleBtn.addEventListener("click", () => {
  if (columnsViewPanel.classList.contains("visible")) {
    // Close columns panel — re-render with new column selection
    columnsToggleBtn.textContent = "\u2630 Select";
    columnsToggleBtn.classList.remove("active");
    saveSelectedColumnNames(appState.selectedColumnNames);
    setView(appState.activeView);
  } else {
    // Open columns panel — transient
    setView(appState.activeView, { columns: true });
  }
});

// Error close button — stateless, goes back in history
errorViewCloseBtn.addEventListener("click", () => {
  history.back();
});

// ------------------------------------------------------------------
// Handle browser back/forward
// ------------------------------------------------------------------
window.addEventListener("popstate", () => {
  const historyState = history.state as { error?: boolean; errorMessage?: string; view?: string } | null;

  if (historyState?.error) {
    // Restore error-view from history state
    waitingView.hide();
    hideAllDataPanels();
    hideSummaryCards();
    errorView.show(historyState.errorMessage ?? "An unknown error occurred.");
    disableAllControls();
    errorViewCloseBtn.disabled = false;
    return;
  }

  // Normal restoration from URL — no double-push
  const urlState = getUrlState();
  appState.dateRangeFrom = urlState.dateFrom;
  appState.dateRangeTo = urlState.dateTo;
  dateFromInput.value = urlState.dateFrom;
  dateToInput.value = urlState.dateTo;
  if (urlState.binSize) {
    binSizeSelect.value = urlState.binSize;
  }
  updateNavButtonStates();

  setView(urlState.view, { replace: true, split: urlState.isSplit });
});

// ------------------------------------------------------------------
// Wire date navigation and column toggle
// ------------------------------------------------------------------
wireDateNavigation(() => setView(appState.activeView));

// ------------------------------------------------------------------
// Initialization
// ------------------------------------------------------------------
async function init(): Promise<void> {
  // Parse URL parameters
  const urlState = getUrlState();
  appState.activeView = urlState.view;
  appState.dateRangeFrom = urlState.dateFrom;
  appState.dateRangeTo = urlState.dateTo;
  dateFromInput.value = urlState.dateFrom;
  dateToInput.value = urlState.dateTo;
  if (urlState.binSize) {
    binSizeSelect.value = urlState.binSize;
  }

  // Version badge
  try {
    const verRes = await fetchWithTimeout("/api/version", 5_000);
    const ver: { version: string } = await verRes.json();
    versionBadgeEl.textContent = `FE ${FRONTEND_VERSION} / BE ${ver.version}`;
  } catch {
    versionBadgeEl.textContent = `FE ${FRONTEND_VERSION} / BE ?`;
  }

  // Load date bounds
  try {
    const datesRes = await fetchWithTimeout("/api/dates", 10_000);
    const dates: { min: string; max: string } = await datesRes.json();
    if (dates.min) {
      dateFromInput.min = dates.min;
      dateToInput.min = dates.min;
      appState.minAvailableDate = dates.min;
    }
    if (dates.max) {
      dateFromInput.max = dates.max;
      dateToInput.max = dates.max;
      appState.maxAvailableDate = dates.max;
    }
    updateNavButtonStates();
  } catch {
    // Continue without date bounds
  }

  // Render initial view from URL
  await setView(urlState.view, { replace: true, split: urlState.isSplit });
}

init();
