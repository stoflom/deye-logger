// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// DOM Element References — isolated module to break circular
// dependencies. All DOM refs are gathered here so that other
// modules can import without creating circular import chains.
// ============================================================

// ------------------------------------------------------------------
// Helper — throws if element is missing
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
export const dayFilterSelect = getRequiredEl<HTMLSelectElement>("day-filter-select", "#day-filter-select");

// --- Panels ---
export const waitingViewPanel = getRequiredEl<HTMLElement>("waiting-view", "#waiting-view");
export const waitingViewTextEl = getRequiredEl<HTMLElement>("waiting-text", "#waiting-text");
export const errorViewPanel = getRequiredEl<HTMLElement>("error-view", "#error-view");
export const errorViewMessageEl = getRequiredEl<HTMLElement>("error-message", "#error-message");
export const errorViewCloseBtn = getRequiredEl<HTMLButtonElement>("error-close-btn", "#error-close-btn");
export const infoViewPanel = getRequiredEl<HTMLElement>("info-view", "#info-view");
export const infoViewMessageEl = getRequiredEl<HTMLElement>("info-message", "#info-message");
export const columnsViewPanel = getRequiredEl<HTMLElement>("columns-view", "#columns-view");
export const columnsViewInner = getRequiredEl<HTMLElement>("columns-view-inner", "#columns-view-inner");
export const histogramControls = getRequiredEl<HTMLElement>("histogram-controls", "#histogram-controls");
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
