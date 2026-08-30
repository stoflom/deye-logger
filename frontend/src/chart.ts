// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// Chart rendering — Chart.js line chart for raw data
// ============================================================

import { Chart } from "chart.js";
import {
  appState,
  CHART_PALETTE,
  summaryCardsPanel,
  rawDataChartCanvas,
  extractUnit,
  isDateRange,
  fmtNum,
  getNumericColumnNames,
  ColumnMeta,
} from "./shared";

// ------------------------------------------------------------------
// Summary cards — supports raw data (default) or binned histogram data
// ------------------------------------------------------------------
export function updateSummaryCards(binnedMaxValues?: Map<string, { value: number; timestamp: string }> | null): void {
  summaryCardsPanel.innerHTML = "";

  if (appState.rawDataRows.length === 0 && !binnedMaxValues) {
    summaryCardsPanel.classList.remove("visible");
    return;
  }


  const isHistogramView = binnedMaxValues !== undefined && binnedMaxValues !== null;
  const dataRows = appState.rawDataRows;

  const numericCols = getNumericColumnNames(
    appState.selectedColumnNames,
    dataRows,
    appState.columnMetadata,
    isHistogramView ? binnedMaxValues : null,
  );

  if (numericCols.length === 0) {
    summaryCardsPanel.classList.remove("visible");
    return;
  }

  summaryCardsPanel.classList.add("visible");

  for (let i = 0; i < numericCols.length; i++) {
    const col = numericCols[i];
    const meta = appState.columnMetadata.find((c: ColumnMeta) => c.name === col);
    const color = CHART_PALETTE[i % CHART_PALETTE.length];

    let max: number;
    let ts = "";

    if (isHistogramView && binnedMaxValues.has(meta?.label ?? col)) {
      const rec = binnedMaxValues.get(meta?.label ?? col)!;
      max = rec.value;
      ts = rec.timestamp;
    } else {
      let m = -Infinity;
      for (const row of dataRows) {
        const v = row[col] as number;
        if (typeof v === "number" && v > m) {
          m = v;
          ts = row.device_timestamp as string;
        }
      }
      max = m;
    }

    const prefix = isHistogramView ? "Max Average" : "Max";
    const unit = extractUnit(meta, col);
    const valueStr = unit ? `${fmtNum(max)} ${unit}` : fmtNum(max);
    const card = document.createElement("div");
    card.className = "summary-card";
    card.innerHTML = `
      <div class="label">${prefix} ${meta ? meta.label : col}</div>
      <div class="value" style="color:${color}">${valueStr}</div>
      <div style="font-size:10px;color:#a0aec0;margin-top:2px">${ts}</div>
    `;
    summaryCardsPanel.appendChild(card);
  }
}

// ------------------------------------------------------------------
// Resize handling for chart
// ------------------------------------------------------------------
function onChartResize(): void {
  if (appState.rawDataChartInstance) {
    appState.rawDataChartInstance.resize();
  }
}

const resizeObserver = new ResizeObserver(onChartResize);
resizeObserver.observe(rawDataChartCanvas.parentElement as HTMLElement);
globalThis.addEventListener("resize", onChartResize);

// ------------------------------------------------------------------
// Chart.js rendering — pure renderer.
// Caller owns the lifecycle (waiting-view, button control).
// ------------------------------------------------------------------
// ------------------------------------------------------------------
// Full-range x-axis extent (design §15.8, #85, #88)
// The x-axis always spans the whole selected range (single day: 00:00–24:00)
// at a fixed tick step — 5 min (1 day), 30 min (2–7 days), 60 min (>7 days).
// The step governs TICK PLACEMENT ONLY: the series plots every raw row at
// its actual timestamp — no bucketing, no smoothing (#88).
// ------------------------------------------------------------------
interface RowPoint {
  x: number; // epoch ms
  y: number;
  ts: string; // device_timestamp, for tooltips
}

function rowTimestampMs(row: Record<string, unknown>): number {
  const ts = row.device_timestamp;
  const t = typeof ts === "number" ? (ts > 1e12 ? ts : ts * 1000) : new Date(String(ts)).getTime();
  return t;
}

function buildFullRangeExtent(): {
  min: number;
  max: number;
  stepMs: number;
  tickFormat: (v: number) => string;
} {
  const start = new Date(`${appState.dateRangeFrom}T00:00:00`);
  // Inclusive calendar-day count (single day: from === to → 1 full day),
  // same convention as updateRangeDays()
  const days = Math.ceil((new Date(`${appState.dateRangeTo}T00:00:00`).getTime() - start.getTime()) / 86_400_000) + 1;

  const stepMinutes = days <= 1 ? 5 : days <= 7 ? 30 : 60;

  const fmtDay = (d: Date): string =>
    `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  const tickFormat = (v: number): string => {
    const d = new Date(v);
    const hhmm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    return isDateRange() ? `${fmtDay(d)} ${hhmm}` : hhmm;
  };

  return {
    min: start.getTime(),
    max: start.getTime() + days * 1440 * 60_000,
    stepMs: stepMinutes * 60_000,
    tickFormat,
  };
}

// ------------------------------------------------------------------
// Chart.js rendering — pure renderer.
// Caller owns the lifecycle (waiting-view, button control).
// ------------------------------------------------------------------
export function renderRawDataChart(): void {
  // Destroy existing chart
  if (appState.rawDataChartInstance) {
    appState.rawDataChartInstance.destroy();
    appState.rawDataChartInstance = null;
  }

  if (appState.rawDataRows.length === 0) {
    return;
  }

  // Full-range x-axis — axis always spans the whole selected range
  // (single day: 00:00–24:00); every raw row is plotted at its actual
  // timestamp — no bucketing, no smoothing (design §15.8, #85, #88)
  const extent = buildFullRangeExtent();

  const numericCols = getNumericColumnNames(appState.selectedColumnNames, appState.rawDataRows, appState.columnMetadata, null);

  // Step 1: Collect unique units in order of first appearance.
  // All units are collected first, then axes are split roughly equally
  // between left and right sides to support more than 4 unique units.
  const uniqueUnits: string[] = [];
  for (const col of numericCols) {
    const meta = appState.columnMetadata.find((c: ColumnMeta) => c.name === col);
    const unit = extractUnit(meta, col);
    if (unit && !uniqueUnits.includes(unit)) {
      uniqueUnits.push(unit);
    }
  }

  const mid = Math.ceil(uniqueUnits.length / 2);
  const unitAxisMap: Record<string, string> = {};
  const unitPosition: Record<string, string> = {};
  for (let i = 0; i < uniqueUnits.length; i++) {
    const unit = uniqueUnits[i];
    const position: "left" | "right" = i < mid ? "left" : "right";
    const idx = position === "left" ? i : i - mid;
    unitAxisMap[unit] = position === "left" ? `y-${idx}` : `yR-${idx}`;
    unitPosition[unit] = position;
  }

  // Step 2: Build scale configs — x is a linear time axis with the full
  // range extent and a fixed tick step; ticks govern placement only (#88)
  // deno-lint-ignore no-explicit-any
  const scales: Record<string, any> = {
    x: {
      display: true,
      type: "linear",
      min: extent.min,
      max: extent.max,
      ticks: {
        color: "#4a5568",
        stepSize: extent.stepMs,
        maxTicksLimit: isDateRange() ? 14 : 12,
        font: { size: 11 },
        maxRotation: 0,
        callback: (value: unknown) => extent.tickFormat(Number(value)),
      },
      grid: { display: false, drawBorder: true, color: "#e2e8f0" },
    },
  };
  for (const [unit, axisId] of Object.entries(unitAxisMap)) {
    const position = unitPosition[unit];
    const axisCfg: Record<string, unknown> = {
      position,
      title: {
        display: !!unit,
        text: unit,
        font: { size: 11, weight: "bold" },
      },
      ticks: { font: { size: 10 } },
      // Percentage units (SOC) always span 0–100 (design §15.8, #85)
      ...(unit === "%" ? { min: 0, max: 100 } : {}),
      grid: { color: position === "left" ? "#e2e8f0" : "rgba(0,0,0,0.08)" },
      border: {
        color: position === "left" ? "#94a3b8" : "rgba(0,0,0,0.08)",
      },
    };
    scales[axisId] = axisCfg;
  }

  // Step 3: Build datasets referencing the pre-created axes — one point per
  // raw data row at its actual timestamp; straight segments, no smoothing
  // (design §15.8, #88)
  const pointsByCol = new Map<string, RowPoint[]>();
  for (const col of numericCols) {
    const pts: RowPoint[] = [];
    for (const row of appState.rawDataRows) {
      const v = row[col];
      if (typeof v !== "number") continue;
      pts.push({ x: rowTimestampMs(row), y: v, ts: String(row.device_timestamp ?? "") });
    }
    pts.sort((a, b) => a.x - b.x);
    pointsByCol.set(col, pts);
  }

  const datasets = numericCols.map((col, i) => {
    const meta = appState.columnMetadata.find((c: ColumnMeta) => c.name === col);
    const unit = extractUnit(meta, col);
    const yAxisId = unitAxisMap[unit] ?? "y-0";

    return {
      label: unit ? `${meta ? meta.label : col} (${unit})` : meta ? meta.label : col,
      data: pointsByCol.get(col) ?? [],
      borderColor: CHART_PALETTE[i % CHART_PALETTE.length],
      backgroundColor: CHART_PALETTE[i % CHART_PALETTE.length] + "20",
      borderWidth: 1.5,
      showLine: true,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0, // straight segments — data peaks must be visible (#88)
      yAxisID: yAxisId,
    };
  });

  appState.rawDataChartInstance = new Chart(rawDataChartCanvas, {
    type: "line",
    // No category labels: points carry their own x (epoch ms) on the
    // linear time axis; the full-range extent comes from scales.x (#88)
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { bottom: 10 } },
      interaction: {
        mode: "nearest",
        axis: "x",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, padding: 12, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            title: (items) => {
              // Tooltip title: the hovered row's own device_timestamp (#88)
              const raw = items[0]?.raw as RowPoint | undefined;
              return raw && typeof raw.ts === "string" ? raw.ts : "";
            },
            label: (item) => ` ${item.dataset.label}: ${item.formattedValue}`,
          },
        },
      },
      scales,
    },
  });

  // Ensure chart renders at correct size after DOM paint
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (appState.rawDataChartInstance) appState.rawDataChartInstance.resize();
    });
  });

  (rawDataChartCanvas as unknown as { __chartInstance?: unknown }).__chartInstance = appState.rawDataChartInstance;
}
