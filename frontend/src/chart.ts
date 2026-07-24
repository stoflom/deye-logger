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

  const palette = [
    "#3182ce", "#e53e3e", "#38a169", "#d69e2e", "#805ad5",
    "#dd6b20", "#319795", "#d53f8c", "#2b6cb0", "#c53030",
    "#276749", "#b7791f", "#6b46c1", "#c05621", "#285e61",
    "#97266d",
  ];

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
    const color = palette[i % palette.length];

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
    const card = document.createElement("div");
    card.className = "summary-card";
    card.innerHTML = `
      <div class="label">${prefix} ${meta ? meta.label : col}</div>
      <div class="value" style="color:${color}">${fmtNum(max)}</div>
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
export function renderRawDataChart(): void {
  // Destroy existing chart
  if (appState.rawDataChartInstance) {
    appState.rawDataChartInstance.destroy();
    appState.rawDataChartInstance = null;
  }

  if (appState.rawDataRows.length === 0) {
    return;
  }

  // Helper: accept ISO strings or numeric epoch (seconds or ms)
  function formatTimestamp(ts: unknown): string {
    if (ts === null || ts === undefined || ts === "") return "";
    if (typeof ts === "number") {
      const ms = ts > 1e12 ? ts : ts * 1000;
      const d = new Date(ms).toISOString();
      if (d.length > 16) {
        const day = d.slice(5, 10);
        const time = d.slice(11, 16);
        return isDateRange() ? `${day} ${time}` : time;
      }
      return d;
    }
    const s = String(ts);
    if (s.length > 10) {
      const day = s.slice(5, 10);
      const time = s.slice(11, 16);
      return isDateRange() ? `${day} ${time}` : time;
    }
    return s;
  }

  const labels = appState.rawDataRows.map((row: Record<string, unknown>) => formatTimestamp(row.device_timestamp));

  const numericCols = getNumericColumnNames(appState.selectedColumnNames, appState.rawDataRows, appState.columnMetadata, null);

  const palette = [
    "#3182ce", "#e53e3e", "#38a169", "#d69e2e", "#805ad5",
    "#dd6b20", "#319795", "#d53f8c", "#2b6cb0", "#c53030",
    "#276749", "#b7791f", "#6b46c1", "#c05621", "#285e61",
    "#97266d",
  ];

  // Step 1: Collect unique units in order of first appearance
  const unitAxisMap: Record<string, string> = {};
  const unitPosition: Record<string, string> = {};
  let leftCount = 0;
  let rightCount = 0;

  for (const col of numericCols) {
    const meta = appState.columnMetadata.find((c: ColumnMeta) => c.name === col);
    const unit = extractUnit(meta ? meta.label : col);
    if (!(unit in unitAxisMap)) {
      const axisId = leftCount < 2 ? `y-${leftCount}` : `yR-${rightCount}`;
      const position = leftCount < 2 ? "left" : "right";
      unitAxisMap[unit] = axisId;
      unitPosition[unit] = position;
      if (leftCount < 2) leftCount++; else rightCount++;
    }
  }

  // Step 2: Build scale configs (always include x)
  // deno-lint-ignore no-explicit-any
  const scales: Record<string, any> = {
    x: {
      display: true,
      ticks: {
        color: "#4a5568",
        maxTicksLimit: isDateRange() ? 14 : 12,
        font: { size: 11 },
        maxRotation: 0,
      },
      grid: { display: false, drawBorder: true, color: "#e2e8f0" },
    },
  };
  for (const [unit, axisId] of Object.entries(unitAxisMap)) {
    const position = unitPosition[unit];
    scales[axisId] = {
      position,
      title: {
        display: !!unit,
        text: unit,
        font: { size: 11, weight: "bold" },
      },
      ticks: { font: { size: 10 } },
      grid: { color: position === "left" ? "#e2e8f0" : "rgba(0,0,0,0.08)" },
      border: {
        color: position === "left" ? "#94a3b8" : "rgba(0,0,0,0.08)",
      },
    };
  }

  // Step 3: Build datasets referencing the pre-created axes
  const datasets = numericCols.map((col, i) => {
    const meta = appState.columnMetadata.find((c: ColumnMeta) => c.name === col);
    const unit = extractUnit(meta ? meta.label : col);
    const yAxisId = unitAxisMap[unit] ?? "y-0";

    return {
      label: meta ? meta.label : col,
      data: appState.rawDataRows.map((row: Record<string, unknown>) => row[col] as number),
      borderColor: palette[i % palette.length],
      backgroundColor: palette[i % palette.length] + "20",
      borderWidth: 1.5,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
      yAxisID: yAxisId,
    };
  });

  appState.rawDataChartInstance = new Chart(rawDataChartCanvas, {
    type: "line",
    data: { labels, datasets },
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
          labels: { boxWidth: 12, padding: 12, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            title: (items) => {
              const idx = items[0].dataIndex;
              const ts = appState.rawDataRows[idx]?.device_timestamp;
              return typeof ts === "string" ? ts : "";
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
}
