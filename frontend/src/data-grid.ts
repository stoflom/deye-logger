// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// AG Grid — data grid rendering (raw data + histogram grid)
// ============================================================

import { createGrid, ColDef } from "ag-grid-community";
import {
  appState,
  rawDataGridContainer,
  histogramGridContainer,
  ColumnMeta,
  extractUnit,
} from "./shared";

// ------------------------------------------------------------------
// Column definitions — raw data grid
// ------------------------------------------------------------------
function buildRawDataGridCols(): ColDef[] {
  return [...appState.selectedColumnNames].map((colName) => {
    const meta = appState.columnMetadata.find((c: ColumnMeta) => c.name === colName);
    const unit = extractUnit(meta, colName);
    const displayName = meta ? meta.label : colName;
    const headerName = unit ? `${displayName} (${unit})` : displayName;
    return {
      field: colName,
      headerName,
      sortable: true,
      filter: true,
      resizable: true,
      flex: 1,
      minWidth: colName === "device_timestamp" ? 180 : 100,
      valueFormatter: (params: { value: unknown }) => {
        if (params.value === null || params.value === undefined) return "\u2014";
        if (typeof params.value === "number") {
          return Number.isInteger(params.value)
            ? params.value.toLocaleString()
            : params.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
        }
        return String(params.value);
      },
    };
  });
}

// ------------------------------------------------------------------
// Grid init / update — raw data
// ------------------------------------------------------------------
export function initRawDataGrid(): void {
  if (appState.rawDataGridApi) {
    appState.rawDataGridApi.destroy();
  }

  appState.rawDataGridApi = createGrid(rawDataGridContainer, {
    columnDefs: buildRawDataGridCols(),
    rowData: appState.rawDataRows,
    animateRows: true,
    suppressCellFocus: true,
    suppressRowClickSelection: true,
    suppressCopyRowsToClipboard: true,
    suppressClipboardApi: true,
    headerHeight: 36,
    rowHeight: 32,
    onGridReady: () => resizeRawDataGrid(),
  });
}

export function updateRawDataGrid(): void {
  if (!appState.rawDataGridApi) return;

  appState.rawDataGridApi.setGridOption("columnDefs", buildRawDataGridCols());
  appState.rawDataGridApi.setGridOption("rowData", appState.rawDataRows);
  resizeRawDataGrid();
}

function resizeRawDataGrid(): void {
  if (appState.rawDataGridApi) {
    requestAnimationFrame(() => appState.rawDataGridApi!.sizeColumnsToFit());
  }
}

// ------------------------------------------------------------------
// Column definitions — histogram grid
// Three columns per measurement — Avg / Min / Max (design §10.2.2,
// v8.3, #95) — fed from the /api/histogram data/min/max arrays.
// ------------------------------------------------------------------
interface HistogramGridDataset {
  label: string;
  min?: number[];
  max?: number[];
}

export function buildHistogramGridCols(datasets: HistogramGridDataset[]): ColDef[] {
  const valueFormatter = (params: { value: unknown }) => {
    if (params.value === null || params.value === undefined) return "\u2014";
    if (typeof params.value === "number") {
      return params.value.toLocaleString(undefined, { maximumFractionDigits: 1 });
    }
    return String(params.value);
  };

  const cols: ColDef[] = [
    {
      field: "device_timestamp",
      headerName: "Time",
      sortable: true,
      filter: true,
      resizable: true,
      minWidth: 80,
      flex: 0,
    },
  ];
  for (const ds of datasets) {
    const meta = appState.columnMetadata.find((c: ColumnMeta) => c.label === ds.label);
    const unit = extractUnit(meta, ds.label);
    const base = unit ? `${ds.label} (${unit})` : ds.label;
    const common = { sortable: true, filter: true, resizable: true, flex: 1, minWidth: 100 };
    cols.push({ field: ds.label, headerName: `${base} Avg`, ...common, valueFormatter });
    if (ds.min) cols.push({ field: `${ds.label}::min`, headerName: `${base} Min`, ...common, valueFormatter });
    if (ds.max) cols.push({ field: `${ds.label}::max`, headerName: `${base} Max`, ...common, valueFormatter });
  }
  return cols;
}

// ------------------------------------------------------------------
// Grid init / update — histogram grid
// ------------------------------------------------------------------
let histogramGridApi: ReturnType<typeof createGrid> | null = null;

export function getHistogramGridApi() {
  return histogramGridApi;
}

export function initHistogramGrid(
  columnDefs: ColDef[],
  rowData: Record<string, unknown>[],
): void {
  if (histogramGridApi) {
    histogramGridApi.destroy();
  }

  histogramGridApi = createGrid(histogramGridContainer, {
    columnDefs,
    rowData,
    animateRows: true,
    suppressCellFocus: true,
    suppressRowClickSelection: true,
    suppressCopyRowsToClipboard: true,
    suppressClipboardApi: true,
    headerHeight: 36,
    rowHeight: 32,
    onGridReady: () => resizeHistogramGrid(),
  });
}

export function updateHistogramGrid(
  columnDefs: ColDef[],
  rowData: Record<string, unknown>[],
): void {
  if (!histogramGridApi) return;

  histogramGridApi.setGridOption("columnDefs", columnDefs);
  histogramGridApi.setGridOption("rowData", rowData);
  resizeHistogramGrid();
}

function resizeHistogramGrid(): void {
  if (histogramGridApi) {
    requestAnimationFrame(() => histogramGridApi!.sizeColumnsToFit());
  }
}
