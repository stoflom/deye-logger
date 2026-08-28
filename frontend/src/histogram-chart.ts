// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// Histogram — time-binned averages via backend API
// ============================================================

import { Chart, type TooltipItem } from "chart.js";

import {
  appState,
  histogramChartCanvas,
  binSizeSelect,
  dayFilterSelect,
  splitHistogramView,
  splitHistogramScroll,
  fetchWithTimeout,
  RenderOk,
} from "./shared";

// ------------------------------------------------------------------
// Module-level state
// ------------------------------------------------------------------
let histogramCombinedChartInstance: Chart | null = null;
let histogramSplitChartInstances: Chart[] = [];
let histogramIsSplitMode = false;
let histogramLastApiResult: HistogramResponse | null = null;
let histogramLastColumnNames: string[] = [];

export let histogramMaxAverageValues: Map<string, { value: number; timestamp: string }> | null = null;

// ------------------------------------------------------------------
// API response types
// ------------------------------------------------------------------
interface HistogramDataset {
  label: string;
  data: number[];
  /** Per-bin minimum values, parallel to `data` (design §10.2.1) */
  min?: number[];
  /** Per-bin maximum values, parallel to `data` (design §10.2.1) */
  max?: number[];
  unit: string;
}

export interface HistogramResponse {
  labels: string[];
  datasets: HistogramDataset[];
  maxValues: Record<string, { value: number; timestamp: string }>;
}

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------
function waitForFrame(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

export const isSplitModeActive = () => histogramIsSplitMode;

// ------------------------------------------------------------------
// Color palette — shared with chart.ts for consistent rendering
// ------------------------------------------------------------------
const PALETTE = [
  "#3182ce", "#e53e3e", "#38a169", "#d69e2e", "#805ad5",
  "#dd6b20", "#319795", "#d53f8c", "#2b6cb0", "#c53030",
  "#276749", "#b7791f", "#6b46c1", "#c05621", "#285e61",
  "#97266d",
];

// ------------------------------------------------------------------
// Build unit-to-axis mapping from datasets
// First two unique units → left axes (y-0, y-1), remaining → right axes (yR-0, yR-1, …)
// ------------------------------------------------------------------
function buildUnitAxisMap(datasets: HistogramDataset[]): { yAxisID: Record<string, string>; position: Record<string, string>; } {
  const yAxisID: Record<string, string> = {};
  const position: Record<string, string> = {};
  let leftCount = 0;
  let rightCount = 0;

  for (const ds of datasets) {
    const unit = ds.unit;
    if (!(unit in yAxisID)) {
      const axisId = leftCount < 2 ? `y-${leftCount}` : `yR-${rightCount}`;
      const pos = leftCount < 2 ? "left" : "right";
      yAxisID[unit] = axisId;
      position[unit] = pos;
      if (leftCount < 2) leftCount++; else rightCount++;
    }
  }
  return { yAxisID, position };
}

// ------------------------------------------------------------------
// Enrich datasets with display fields (color, yAxisID, position)
// computed locally from unit — backend only provides data + unit.
// ------------------------------------------------------------------
type EnrichedDataset = HistogramDataset & { color: string; yAxisID: string; position: string; };

function enrichDatasets(datasets: HistogramDataset[]): EnrichedDataset[] {
  const { yAxisID, position } = buildUnitAxisMap(datasets);
  return datasets.map((ds, i) => ({
    ...ds,
    color: PALETTE[i % PALETTE.length],
    yAxisID: yAxisID[ds.unit] ?? "y-0",
    position: position[ds.unit] ?? "left",
  }));
}

// ------------------------------------------------------------------
// Per-bin value range rendering (design §10.2.1)
// Each column gets its average bar plus a translucent floating bar
// spanning [min, max]. Bins with zero spread (min === max) are skipped.
// ------------------------------------------------------------------

type HistogramBarDataset = {
  label: string;
  data: (number | [number, number] | null)[];
  backgroundColor: string;
  borderColor?: string;
  borderWidth: number;
  borderRadius: number;
  barPercentage: number;
  categoryPercentage: number;
  yAxisID: string;
  /** Custom marker for range datasets (excluded from legend/tooltip) */
  _isRange?: boolean;
  /** Raw per-bin arrays carried for the tooltip (average datasets only) */
  _min?: number[];
  _max?: number[];
};

function hasAnySpread(min: number[], max: number[]): boolean {
  return min.some((mn, j) => mn !== max[j]);
}

/** [min, max] per bin, null for zero-spread bins (not drawn) */
function buildRangeData(min: number[], max: number[]): (number | [number, number] | null)[] {
  return min.map((mn, j) => (mn === max[j] ? null : [mn, max[j]]));
}

/**
 * Build Chart.js datasets: for each column, the average bar; plus a
 * translucent floating bar showing the per-bin value range when the
 * backend provided min/max and at least one bin has spread.
 */
function buildHistogramDatasets(enriched: EnrichedDataset[]): HistogramBarDataset[] {
  const out: HistogramBarDataset[] = [];
  for (const ds of enriched) {
    const label = ds.unit ? `${ds.label} (${ds.unit})` : ds.label;
    out.push({
      label,
      data: ds.data,
      backgroundColor: ds.color + "80",
      borderColor: ds.color,
      borderWidth: 1,
      borderRadius: 2,
      barPercentage: 0.9,
      categoryPercentage: 0.85,
      yAxisID: ds.yAxisID,
      _min: ds.min,
      _max: ds.max,
    });
    if (ds.min && ds.max && hasAnySpread(ds.min, ds.max)) {
      out.push({
        label: `${label} (range)`,
        data: buildRangeData(ds.min, ds.max),
        backgroundColor: ds.color + "33",
        borderWidth: 0,
        borderRadius: 2,
        barPercentage: 0.9,
        categoryPercentage: 0.85,
        yAxisID: ds.yAxisID,
        _isRange: true,
      });
    }
  }
  return out;
}

/** Range datasets are not legend/tooltip entries */
function isRangeDataset(item: { dataset: unknown }): boolean {
  return Boolean((item.dataset as HistogramBarDataset)._isRange);
}

function formatRangeValue(v: number): string {
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** Tooltip label: `Label: avg (range min–max)`; range omitted when min === max */
function histogramTooltipLabel(item: TooltipItem<"bar">): string {
  const ds = item.dataset as unknown as HistogramBarDataset;
  const value = typeof item.parsed?.y === "number" ? item.parsed.y : Number(item.formattedValue);
  let text = ` ${item.dataset.label}: ${formatRangeValue(value)}`;
  const mn = ds._min?.[item.dataIndex];
  const mx = ds._max?.[item.dataIndex];
  if (mn !== undefined && mx !== undefined && mn !== mx) {
    text += ` (range ${formatRangeValue(mn)}–${formatRangeValue(mx)})`;
  }
  return text;
}

// ------------------------------------------------------------------
// Fetch histogram data from backend. Pure data fetcher — no rendering.
// Caches the result for reuse by other consumers.
// ------------------------------------------------------------------
export async function fetchHistogramData(): Promise<HistogramResponse> {
  const cols = [...appState.selectedColumnNames];
  if (!cols.includes("device_timestamp")) cols.unshift("device_timestamp");

  const binMinutes = parseInt(binSizeSelect.value, 10) || 15;
  const dayFilter = dayFilterSelect.value || "all";
  const params = new URLSearchParams({
    from: appState.dateRangeFrom,
    to: appState.dateRangeTo,
    columns: cols.join(","),
    binMinutes: String(binMinutes),
    dayFilter,
  });

  const res = await fetchWithTimeout(`/api/histogram?${params}`, 30_000);
  const result: HistogramResponse = await res.json();

  // Cache for reuse
  histogramLastApiResult = result;
  histogramLastColumnNames = cols.filter((c) => c !== "device_timestamp");

  // Store max values for summary cards
  histogramMaxAverageValues = Object.keys(result.maxValues).length > 0
    ? new Map(Object.entries(result.maxValues))
    : null;

  return result;
}

// ------------------------------------------------------------------
// Transform histogram API response into grid-compatible rows.
// ------------------------------------------------------------------
export function histogramResultToRows(result: HistogramResponse): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [];
  for (let i = 0; i < result.labels.length; i++) {
    const row: Record<string, unknown> = { device_timestamp: result.labels[i] };
    for (const ds of result.datasets) {
      row[ds.label] = ds.data[i] ?? null;
    }
    rows.push(row);
  }
  return rows;
}

// ------------------------------------------------------------------
// Fetch histogram data and render the combined chart.
// Pure async renderer — caller owns lifecycle (waiting-view, buttons).
// ------------------------------------------------------------------
export async function renderHistogramChart(updateWaiting: (text: string) => void): Promise<RenderOk> {
  // Destroy existing chart
  if (histogramCombinedChartInstance) {
    histogramCombinedChartInstance.destroy();
    histogramCombinedChartInstance = null;
  }

  updateWaiting("Fetching histogram data…");
  const result = await fetchHistogramData();

  if (result.datasets.length === 0) {
    return { ok: true };
  }

  updateWaiting("Drawing histogram…");

  // Build scale configs with unit-based axes
  // deno-lint-ignore no-explicit-any
  const scales: Record<string, any> = {
    x: {
      display: true,
      title: {
        display: true,
        text: "Time",
        font: { size: 12, weight: "bold" },
      },
      ticks: {
        color: "#4a5568",
        maxTicksLimit: 24,
        maxRotation: 45,
        font: { size: 10 },
      },
      grid: { display: false, color: "#e2e8f0" },
    },
  };

  // Enrich datasets with display fields computed from unit
  const enriched = enrichDatasets(result.datasets);

  for (const ds of enriched) {
    if (!(ds.yAxisID in scales)) {
      scales[ds.yAxisID] = {
        position: ds.position,
        title: {
          display: true,
          text: ds.unit,
          font: { size: 11, weight: "bold" },
        },
        ticks: {
          color: "#4a5568",
          font: { size: 10 },
          callback: (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }),
        },
        grid: {
          color: ds.position === "left" ? "#e2e8f0" : "rgba(0,0,0,0.08)",
        },
        border: {
          color: ds.position === "left" ? "#94a3b8" : "rgba(0,0,0,0.08)",
        },
      };
    }
  }

  // Build the chart — wait for canvas to have dimensions
  await waitForFrame();
  // Test hook: expose the live instance on the canvas for UI tests
  (histogramChartCanvas as unknown as { __chartInstance?: Chart | null }).__chartInstance = null;
  histogramCombinedChartInstance = new Chart(histogramChartCanvas, {
    type: "bar",
    data: {
      labels: result.labels,
      // deno-lint-ignore no-explicit-any
      datasets: buildHistogramDatasets(enriched) as any[],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { bottom: 10 } },
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 12,
            padding: 12,
            font: { size: 11 },
            // Per-bin range datasets are auxiliary — keep the legend on the averages
            filter: (item, data) => !isRangeDataset({ dataset: data.datasets[item.datasetIndex ?? -1] }),
          },
        },
        tooltip: {
          // Range datasets are hidden from the tooltip; their min/max is
          // appended to the average's label instead (design §10.2.1)
          filter: (item) => !isRangeDataset(item),
          callbacks: {
            title: (items: TooltipItem<'bar'>[]) => `Time: ${items[0].label}`,
            label: histogramTooltipLabel,
          },
        },
      },
      scales,
    },
  });
  (histogramChartCanvas as unknown as { __chartInstance?: Chart | null }).__chartInstance = histogramCombinedChartInstance;
  return { ok: true };
}

// ------------------------------------------------------------------
// Resize handler for combined histogram chart
// ------------------------------------------------------------------
function onHistogramResize(): void {
  if (histogramCombinedChartInstance) {
    histogramCombinedChartInstance.resize();
  }
}

const resizeObserver = new ResizeObserver(onHistogramResize);
resizeObserver.observe(histogramChartCanvas.parentElement as HTMLElement);
globalThis.addEventListener("resize", onHistogramResize);

// ------------------------------------------------------------------
// Cleanup split mode — called when switching away from histogram view
// ------------------------------------------------------------------
export function cleanupSplitMode(): void {
  destroySplitCharts();
  histogramIsSplitMode = false;
  splitHistogramView.classList.remove("visible");
  // Button text/title handled by setView's updateButtonLabels
}

// ------------------------------------------------------------------
// Destroy all split charts
// ------------------------------------------------------------------
function destroySplitCharts(): void {
  for (const chart of histogramSplitChartInstances) {
    chart.destroy();
  }
  histogramSplitChartInstances = [];
}

// ------------------------------------------------------------------
// Show split histogram — one chart per selected column
// ------------------------------------------------------------------
export async function showSplitHistogram(): Promise<RenderOk> {
  // Hide the combined histogram, show split view
  // (setView handles panel visibility; this just prepares the content)

  // Destroy any existing split charts
  destroySplitCharts();

  // Get selected columns (exclude timestamp)
  const columns = [...appState.selectedColumnNames].filter((c) => c !== "device_timestamp");
  if (columns.length === 0) return { ok: true };

  // Use cached result if available
  let result = histogramLastApiResult;
  if (!result || result.datasets.length === 0) {
    return { ok: true };
  }

  // Clear scroll container
  splitHistogramScroll.innerHTML = "";

  // Build a lookup from raw column name to enriched dataset
  const enriched = enrichDatasets(result.datasets);
  const colDatasetMap = new Map<string, EnrichedDataset>();
  for (let i = 0; i < histogramLastColumnNames.length && i < enriched.length; i++) {
    colDatasetMap.set(histogramLastColumnNames[i], enriched[i]);
  }

  // Create one chart per column
  const chartPromises: Promise<Chart>[] = [];

  columns.forEach((colName, idx) => {
    const dataset = colDatasetMap.get(colName);
    if (!dataset) return;

    // Create container for this histogram
    const item = document.createElement("div");
    item.className = "split-histogram-item";

    const title = document.createElement("div");
    title.className = "split-histogram-title";
    title.textContent = dataset.label;
    item.appendChild(title);

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "split-histogram-canvas-wrap";

    const canvas = document.createElement("canvas");
    canvas.id = `split-histogram-canvas-${idx}`;
    canvasWrap.appendChild(canvas);
    item.appendChild(canvasWrap);
    splitHistogramScroll.appendChild(item);

    // Build scales for this single-column chart
    // deno-lint-ignore no-explicit-any
    const scales: Record<string, any> = {
      x: {
        display: true,
        title: {
          display: true,
          text: "Time",
          font: { size: 11, weight: "bold" },
        },
        ticks: {
          color: "#4a5568",
          maxTicksLimit: 24,
          maxRotation: 45,
          font: { size: 9 },
        },
        grid: { display: false, color: "#e2e8f0" },
      },
      [dataset.yAxisID]: {
        position: dataset.position as "left" | "right",
        title: {
          display: true,
          text: dataset.unit,
          font: { size: 10, weight: "bold" },
        },
        ticks: {
          color: "#4a5568",
          font: { size: 9 },
          callback: (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }),
        },
        grid: {
          color: dataset.position === "left" ? "#e2e8f0" : "rgba(0,0,0,0.08)",
        },
        border: {
          color: dataset.position === "left" ? "#94a3b8" : "rgba(0,0,0,0.08)",
        },
      },
    };

    chartPromises.push(
      waitForFrame().then(() => {
        // Test hook: expose the live instance on the canvas for UI tests
        (canvas as unknown as { __chartInstance?: Chart | null }).__chartInstance = null;
        return new Chart(canvas, {
          type: "bar",
          data: {
            labels: result.labels,
            // deno-lint-ignore no-explicit-any
            datasets: buildHistogramDatasets([dataset]) as any[],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { bottom: 10 } },
            interaction: {
              mode: "index",
              intersect: false,
            },
            plugins: {
              legend: { display: false },
              tooltip: {
                // Range datasets hidden; min/max appended to the average label (design §10.2.1)
                filter: (item) => !isRangeDataset(item),
                callbacks: {
                  title: (items: TooltipItem<'bar'>[]) => `Time: ${items[0].label}`,
                  label: histogramTooltipLabel,
                },
              },
            },
            scales,
          },
        });
      }),
    );
  });

  histogramSplitChartInstances = await Promise.all(chartPromises);
  // Test hook: expose the live instances on their canvases for UI tests
  for (const c of histogramSplitChartInstances) {
    (c.canvas as unknown as { __chartInstance?: Chart | null }).__chartInstance = c;
  }
  histogramIsSplitMode = true;
  // Button text/title handled by setView's updateButtonLabels
  return { ok: true };
}
