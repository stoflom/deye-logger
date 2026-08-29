// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// Histogram — time-binned averages via backend API
// One bar chart per selected column (design §9.2, v7.0).
// ============================================================

import { Chart, type TooltipItem } from "chart.js";

import {
  appState,
  binSizeSelect,
  dayFilterSelect,
  histogramScroll,
  fetchWithTimeout,
  RenderOk,
} from "./shared";

// ------------------------------------------------------------------
// Module-level state
// ------------------------------------------------------------------
let histogramChartInstances: Chart[] = [];
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
// First unique unit → left axis (y-0), second → right axis (yR-0), remaining → more right axes.
// In per-column charts each chart has a single axis (design §10.2.1).
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
// The shaded range band is a FULL-WIDTH floating bar [min,max] drawn
// behind the average bar; the average bar sits centred on top at
// ~60% of the band's width.
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
  grouped: boolean;
  order: number;
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
 * Build Chart.js datasets for ONE column's chart: the average bar
 * (centred, ~60% width) plus, when the backend provided min/max and at
 * least one bin has spread, a full-width translucent floating bar
 * showing the per-bin value range behind it (design §10.2.1).
 */
function buildHistogramDatasets(ds: EnrichedDataset): HistogramBarDataset[] {
  const label = ds.unit ? `${ds.label} (${ds.unit})` : ds.label;
  const out: HistogramBarDataset[] = [];

  if (ds.min && ds.max && hasAnySpread(ds.min, ds.max)) {
    out.push({
      label: `${label} (range)`,
      data: buildRangeData(ds.min, ds.max),
      backgroundColor: ds.color + "33",
      borderWidth: 0,
      borderRadius: 2,
      // Full-width band spanning the whole category slot, behind the average bar.
      // grouped:false — centre on the category (not side-by-side with the avg bar)
      barPercentage: 1,
      categoryPercentage: 1,
      grouped: false,
      order: 1,
      yAxisID: ds.yAxisID,
      _isRange: true,
    });
  }

  out.push({
    label,
    data: ds.data,
    backgroundColor: ds.color + "80",
    borderColor: ds.color,
    borderWidth: 1,
    borderRadius: 2,
    // ~60% of the range band's width, centred on the same category.
    // grouped:false — centres on the range band instead of sitting beside it
    barPercentage: 0.6,
    categoryPercentage: 1,
    grouped: false,
    order: 0,
    yAxisID: ds.yAxisID,
    _min: ds.min,
    _max: ds.max,
  });

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
// Fetch histogram data and render one bar chart per selected column.
// Pure async renderer — caller owns lifecycle (waiting-view, buttons).
// ------------------------------------------------------------------
export async function renderHistogramCharts(updateWaiting: (text: string) => void): Promise<RenderOk> {
  destroyHistogramCharts();

  updateWaiting("Fetching histogram data…");
  const result = await fetchHistogramData();

  if (result.datasets.length === 0) {
    return { ok: true };
  }

  updateWaiting("Drawing histograms…");

  // Clear container
  histogramScroll.innerHTML = "";

  // Build a lookup from raw column name to enriched dataset
  const enriched = enrichDatasets(result.datasets);
  const colDatasetMap = new Map<string, EnrichedDataset>();
  for (let i = 0; i < histogramLastColumnNames.length && i < enriched.length; i++) {
    colDatasetMap.set(histogramLastColumnNames[i], enriched[i]);
  }

  // Create one chart per column (selected columns, excluding timestamp)
  const columns = [...appState.selectedColumnNames].filter((c) => c !== "device_timestamp");

  const chartPromises: Promise<Chart>[] = [];

  columns.forEach((colName, idx) => {
    const dataset = colDatasetMap.get(colName);
    if (!dataset) return;

    // Create container for this histogram
    const item = document.createElement("div");
    item.className = "histogram-chart-item";

    const title = document.createElement("div");
    title.className = "histogram-chart-title";
    title.textContent = dataset.label;
    item.appendChild(title);

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "histogram-chart-canvas-wrap";

    const canvas = document.createElement("canvas");
    canvas.id = `histogram-chart-canvas-${idx}`;
    canvasWrap.appendChild(canvas);
    item.appendChild(canvasWrap);
    histogramScroll.appendChild(item);

    // Single axis for this single-column chart
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
            datasets: buildHistogramDatasets(dataset) as any[],
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

  histogramChartInstances = await Promise.all(chartPromises);
  // Test hook: expose the live instances on their canvases for UI tests
  for (const c of histogramChartInstances) {
    (c.canvas as unknown as { __chartInstance?: Chart | null }).__chartInstance = c;
  }
  return { ok: true };
}

// ------------------------------------------------------------------
// Destroy all per-column charts
// ------------------------------------------------------------------
export function destroyHistogramCharts(): void {
  for (const chart of histogramChartInstances) {
    chart.destroy();
  }
  histogramChartInstances = [];
}
