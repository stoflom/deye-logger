// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// Histogram — time-binned averages via backend API
// ============================================================

import { Chart, registerables } from "chart.js";

Chart.register(...registerables);

import {
  appState,
  histogramChartCanvas,
  binSizeSelect,
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
  data: (number | null)[];
  color: string;
  unit: string;
  yAxisID: string;
  position: string;
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
// Fetch histogram data from backend. Pure data fetcher — no rendering.
// Caches the result for reuse by other consumers.
// ------------------------------------------------------------------
export async function fetchHistogramData(): Promise<HistogramResponse> {
  const cols = [...appState.selectedColumnNames];
  if (!cols.includes("device_timestamp")) cols.unshift("device_timestamp");

  const binMinutes = parseInt(binSizeSelect.value, 10) || 15;
  const params = new URLSearchParams({
    from: appState.dateRangeFrom,
    to: appState.dateRangeTo,
    columns: cols.join(","),
    binMinutes: String(binMinutes),
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

  for (const ds of result.datasets) {
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
  histogramCombinedChartInstance = new Chart(histogramChartCanvas, {
    type: "bar",
    data: {
      labels: result.labels,
      datasets: result.datasets.map((ds) => ({
        label: ds.label,
        data: ds.data,
        backgroundColor: ds.color + "80",
        borderColor: ds.color,
        borderWidth: 1,
        borderRadius: 2,
        barPercentage: 0.9,
        categoryPercentage: 0.85,
        yAxisID: ds.yAxisID,
      })),
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
          },
        },
        tooltip: {
          callbacks: {
            title: (items) => `Time: ${items[0].label}`,
            label: (item) => ` ${item.dataset.label}: ${item.formattedValue}`,
          },
        },
      },
      scales,
    },
  });
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
async function destroySplitCharts(): Promise<void> {
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
  await destroySplitCharts();

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

  // Build a lookup from raw column name to dataset
  const colDatasetMap = new Map<string, HistogramDataset>();
  for (let i = 0; i < histogramLastColumnNames.length && i < result.datasets.length; i++) {
    colDatasetMap.set(histogramLastColumnNames[i], result.datasets[i]);
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
        return new Chart(canvas, {
          type: "bar",
          data: {
            labels: result!.labels,
            datasets: [
              {
                label: dataset.label,
                data: dataset.data,
                backgroundColor: dataset.color + "80",
                borderColor: dataset.color,
                borderWidth: 1,
                borderRadius: 2,
                barPercentage: 0.9,
                categoryPercentage: 0.85,
                yAxisID: dataset.yAxisID,
              },
            ],
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
                callbacks: {
                  title: (items) => `Time: ${items[0].label}`,
                  label: (item) => ` ${item.dataset.label}: ${item.formattedValue}`,
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
  histogramIsSplitMode = true;
  // Button text/title handled by setView's updateButtonLabels
  return { ok: true };
}
