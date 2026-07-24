# Frontend Design Document — Deye Logger Viewer

> **Status:** Draft v2 — for review and amendment before code rework.
> **Version:** FE 4.3.0 | Single-page application, vanilla TS + Chart.js + AG Grid

---

## 1. Architecture Overview

The application is a single-page app with three vertical regions:

```
┌──────────────────────────────────────────┐
│  TITLE BAR (always visible, persistent)  │
│  — app title + controls bar              │
├──────────────────────────────────────────┤
│  STATE BAR (always visible, persistent)  │
│  — row count, version badge, status      │
├──────────────────────────────────────────┤
│  CONTENT AREA (controlled by setView)    │
│  — exactly one panel is visible at once  │
│    • waiting-view (spinner + text)       │
│    • error-view (modal with Close btn)   │
│    • columns-view (selection panel)      │
│    • data-view (chart/grid/histogram)    │
└──────────────────────────────────────────┘
```

### 1.1 Source Files

| File | Responsibility |
|------|----------------|
| `shared.ts` | Global state object, DOM refs, URL parsing, utility helpers |
| `app.ts` | Entry point, `setView()`, button handlers, init, popstate |
| `chart.ts` | Chart.js line chart rendering, summary cards |
| `data-grid.ts` | AG Grid rendering (raw data + histogram grid) |
| `histogram-chart.ts` | Histogram bar chart, split-mode charts, data fetching |
| `navigation.ts` | Date navigation (prev/next/today/date-picker) |
| `columns.ts` | Column selection panel, checkbox rendering |
| `index.html` | DOM skeleton |
| `style.css` | All styling |

---

## 2. Persistent Always-Visible Objects

These objects are **always rendered and visible** regardless of the current view. They are never hidden by `setView`.

### 2.1 Title Bar (`<div class="header">`)

| Element | ID | Purpose |
|---------|-----|---------|
| `<h1>` | — | App title: "☀️ Deye Logger Viewer" |
| Date inputs | `#date-from`, `#date-to` | Date range selectors |
| Nav buttons | `#prev-day`, `#next-day`, `#today-btn` | Shift dates by ±1 day or go to today |
| Refresh button | `#refresh-btn` | Trigger backend data refresh |
| Columns toggle | `#columns-toggle` | Open/close column selection panel |
| View toggle | `#view-toggle` | Toggle between chart ↔ grid (or histogram ↔ histogram-grid) |
| Histogram button | `#histogram-btn` | Toggle between normal mode and histogram mode |
| CSV export | `#export-btn` | Export current grid as CSV (hidden in chart views) |

### 2.2 Status Bar (`<div class="status-bar">`)

| Element | ID | Purpose |
|---------|-----|---------|
| Row count | `#row-count` | Shows "N rows", "N metrics", or "N bins" |
| Version badge | `#version-badge` | Shows "FE x.x.x / BE y.y.y" |

---

## 3. URL History Stateful Objects

These objects define the **page state** and must be pushed to URL history so that a user can bookmark a page, use browser back/forward, or reload to recreate the exact same state.

### 3.1 URL Query Parameters

| Parameter | Values | Source | Used By |
|-----------|--------|--------|---------|
| `view` | `chart`, `grid`, `histogram`, `histogram-grid` | `setView()` | `getStateFromUrl()`, `setView()` |
| `date` | ISO date string (YYYY-MM-DD) | Date inputs, nav buttons | `getStateFromUrl()` (single day) |
| `from` | ISO date string | Date inputs, nav buttons | `getStateFromUrl()` (range start) |
| `to` | ISO date string | Date inputs, nav buttons | `getStateFromUrl()` (range end) |
| `binSize` | `5`, `10`, `15`, `30`, `60` | `#bin-size-select` | `getStateFromUrl()`, histogram fetch |
| `split` | `1` (presence = true) | Split button | `getStateFromUrl()`, `setView()` |

**Serialization rules** (`buildUrlParams()`):
- Single day: `?view=chart&date=2025-07-20`
- Range: `?view=chart&from=2025-07-18&to=2025-07-20`
- Histogram with custom bin: `?view=histogram&date=2025-07-20&binSize=30`
- Histogram split: `?view=histogram&date=2025-07-20&split=1`
- Default `binSize=15` is omitted from URL

### 3.2 History State (pushState payload)

| Property | Type | Purpose |
|----------|------|---------|
| `view` | string | Current view mode |
| `isSplit` | boolean | Whether histogram is in split mode (redundant with URL but available for fast popstate) |
| `error` | boolean | Whether this is an error-state entry |
| `errorMessage` | string | Error message to restore if `error=true` |

The history state payload supplements the URL — the URL is the authoritative source (bookmarkable), the payload is for fast popstate restoration.

### 3.3 State Push Points

**URL is pushed only on successful render completion.** Errors also push (with `error=true` marker). Transient views (columns panel, refresh-in-progress) do **not** push history.

```
Event → setView(view, opts) → renderAsync() → success → pushState → show data-view
                                                → error   → pushState({ error }) → show error-view
```

| Trigger | Pushes History? | Notes |
|---------|----------------|-------|
| `viewToggle` click | Yes (on success) | Full view change |
| `histogramBtn` click | Yes (on success) | Mode toggle |
| Date nav (prev/next/today/picker) | Yes (on success) | Date change triggers full re-render |
| `binSizeSelect` change | Yes (on success) | Re-renders current view |
| Split/Combine toggle | Yes (on success) | `split=1` in URL |
| `popstate` (browser back/forward) | No (`replace`) | Restores view without double-push |
| `popstate` → error state | No (re-shows error) | Detects `{ error: true }` marker |
| Initial load | Yes (on success) | Sets initial history entry |
| Refresh success | Yes (on success) | Re-renders current view (dates unchanged) |
| Open columns panel | **No** | Transient view |
| Close columns panel | Yes (on success) | Full data re-fetch with new columns |
| Any render failure | Yes (with `error` marker) | Shows error-view |

---

## 4. Stateless Actions

These actions produce a side effect but **do not change URL history state**. They cannot be recreated from a URL and are not navigable via back/forward.

| Action | Element | Behavior |
|--------|---------|----------|
| **CSV Export** | `#export-btn` | Calls `gridApi.exportDataAsCsv()`. Browser download only. |
| **Close error** | Button in error-view | Calls `history.back()` to restore previous page. |
| **Column selection** | Checkboxes in `#columns-view` | Updates `state.selectedColumns`, persists to `localStorage`. Not in URL. |
| **Save as Default** | Button in columns-view | Persists current column set to `localStorage`. |
| **Reset Default** | Button in columns-view | Clears custom default, restores hardcoded defaults. |
| **Clear columns** | Button in columns-view | Clears all selections except `device_timestamp`. |
| **Default columns** | Button in columns-view | Restores default column set. |

---

## 5. Content Panels — Mutual Exclusion

Below the title bar and state bar, **exactly one panel is visible at any time**. `setView` controls which panel is shown.

| Panel | DOM ID | Triggered By | Pushes History? |
|-------|--------|-------------|-----------------|
| **Waiting view** | `#waiting-view` | `setView()` step 2 — always shown first | No |
| **Error view** | `#error-view` | Render failure — modal with Close button | Yes (`error: true`) |
| **Columns view** | `#columns-view` | `setView(view, { columns: true })` | No (transient) |
| **Chart view** | `#chart-view` | `setView("chart")` | Yes |
| **Grid view** | `#grid-view` | `setView("grid")` | Yes |
| **Histogram view** | `#histogram-view` | `setView("histogram")` (not split) | Yes |
| **Histogram grid view** | `#histogram-grid-view` | `setView("histogram-grid")` | Yes |
| **Split histogram view** | `#split-histogram-view` | `setView("histogram", { split: true })` | Yes (`split=1`) |

**Invariant:** At any moment, exactly one of `{ waiting, error, columns, chart, grid, histogram, histogram-grid, split-histogram }` is visible. `setView` enforces this.

---

## 6. setView Controller — Unified Lifecycle

### 6.1 Signature

```typescript
interface SetViewOptions {
  replace?: boolean;      // use replaceState instead of pushState (default: false)
  refresh?: boolean;      // transient — trigger backend refresh before rendering
  columns?: boolean;      // transient — show columns selection panel
  split?: boolean;        // URL-param — split histogram mode
}

function setView(
  view: "chart" | "grid" | "histogram" | "histogram-grid",
  opts?: SetViewOptions,
): Promise<void>
```

### 6.2 Unified Execution Flow

```
setView(view, opts?)
  │
  ├─ STEP 1: disableAllButtons() — debounce protection
  │     All title-bar controls disabled except:
  │     • errorViewCloseBtn (if error-view was visible — shouldn't be here)
  │
  ├─ STEP 2: hide all content panels, show waiting-view
  │     waitingView.show()
  │     waitingView.setText("Loading…")
  │
  ├─ STEP 3: Determine render path from flags + appState.activeView
  │     │
  │     ├─ opts.columns === true
  │     │     → renderColumnsView(updateWaiting)
  │     │       updateWaiting("Loading column definitions…")
  │     │       GET /api/columns (if appState.columnMetadata stale)
  │     │       render checkboxes into columnsViewPanel
  │     │       return { ok: true }
  │     │
  │     ├─ opts.refresh === true
  │     │     → renderRefreshView(updateWaiting)
  │     │       updateWaiting("Querying Deye Cloud…")
  │     │       POST /api/refresh
  │     │       updateWaiting("Fetching latest dates…")
  │     │       GET /api/dates → update minAvailableDate, maxAvailableDate
  │     │       return { ok: true }
  │     │
  │     ├─ view === "chart"
  │     │     → renderRawDataChartView(updateWaiting)
  │     │       updateWaiting("Fetching raw data…")
  │     │       GET /api/data[-range] → appState.rawDataRows
  │     │       updateWaiting("Drawing chart…")
  │     │       draw Chart.js → appState.rawDataChartInstance
  │     │       return { ok: true }
  │     │
  │     ├─ view === "grid"
  │     │     → renderRawDataGridView(updateWaiting)
  │     │       updateWaiting("Fetching raw data…")
  │     │       GET /api/data[-range] → appState.rawDataRows
  │     │       updateWaiting("Building grid…")
  │     │       init/update AG Grid → appState.rawDataGridApi
  │     │       return { ok: true }
  │     │
  │     ├─ view === "histogram" (split from opts or URL)
  │     │     → renderHistogramView(updateWaiting, { split: true/false })
  │     │       updateWaiting("Fetching histogram data…")
  │     │       GET /api/histogram → histogramLastApiResult
  │     │       updateWaiting("Drawing histogram…")
  │     │       draw combined + split charts
  │     │       return { ok: true }
  │     │
  │     └─ view === "histogram-grid"
  │             → renderHistogramGridView(updateWaiting)
  │             updateWaiting("Fetching histogram data…")
  │             GET /api/histogram → histogramLastApiResult
  │             updateWaiting("Building grid…")
  │             init/update histogram AG Grid
  │             return { ok: true }
  │
  ├─ STEP 4: Handle result
  │     │
  │     ├─ { ok: true } AND opts.columns === true
  │     │     → waitingView.hide()
  │     │     → showPanel("columns")
  │     │     → enableButtonsExcept(["refresh", "export", "viewToggle",
  │     │       "histogramToggle", "split", "binSize", "prevDay", "nextDay", "today"])
  │     │     → columnsToggleBtn stays enabled (to close)
  │     │     → NO history push (transient)
  │     │
  │     ├─ { ok: true } AND opts.refresh === true
  │     │     → refresh succeeded — recursive call:
  │     │     → setView(view)  // no refresh flag → falls to normal render
  │     │
  │     ├─ { ok: true } (normal data render)
  │     │     → waitingView.hide()
  │     │     → showPanel(view) — show appropriate data-view
  │     │     → show summary-cards
  │     │     → show/hide histogram-panel based on histogram mode
  │     │     → buildUrlParams() → history.pushState/replaceState
  │     │     → updateButtonLabels(view, split)
  │     │     → enableAllButtons()
  │     │
  │     └─ catch Error
  │             → waitingView.hide()
  │             → history.pushState({ error: true, view, errorMessage: err.message })
  │             → errorView.show(err.message)
  │             → disableAllButtons()
  │             → errorViewCloseBtn stays enabled
  │
  └─ STEP 5: updateButtonLabels(view, split)
        exportCsvBtn.visible          ← grid views only
        histogramToggleBtn.text/title  ← contextual label
        viewToggleBtn.text/title       ← contextual label
        splitBtn.visible               ← histogram view only
        histogramPanel.visible         ← histogram modes only
```

### 6.3 Renderer Contract

Every renderer called by `setView` must follow this contract:

```typescript
interface RenderResult {
  ok: true;
}

// Every renderer:
async function renderXxxView(updateWaiting: (text: string) => void): Promise<RenderResult>
// or throws Error
```

| Rule | Detail |
|------|--------|
| **Always update waiting-view before backend call** | `updateWaiting("Fetching data…")` before any `fetch()` |
| **Update waiting-view during long operations** | `updateWaiting("Drawing chart…")` during chart construction |
| **Return `{ ok: true }` on success** | Uniform success indicator |
| **Throw on error** | `setView` catches and routes to error-view |
| **No DOM panel toggling** | Renderers only draw into their target containers; `setView` controls panel visibility |
| **No button enable/disable** | `setView` controls button state exclusively |
| **No URL/history manipulation** | `setView` controls history exclusively |

### 6.4 Call Sites

| Call Site | Trigger | Flags | Notes |
|-----------|---------|-------|-------|
| `init()` → `setView(urlState.view, { split: urlState.isSplit })` | Page load | `split` from URL | Initial render |
| `viewToggleBtn` click | View toggle button | — | Toggles chart↔grid or histogram↔histogram-grid |
| `histogramToggleBtn` click | Histogram mode button | — | Enters/exits histogram mode |
| Date nav buttons/pickers | Date change | — | `setView(appState.activeView)` — re-render with new dates |
| `popstate` | Browser back/forward | `{ replace: true, split: urlState.isSplit }` | Restores from URL state |
| `popstate` → error | Error state detected | — | Shows error-view directly (no render) |
| `binSizeSelect` change | Bin size dropdown | `split` from URL | Re-renders current histogram view |
| `splitBtn` click | Split/combine toggle | `{ split: !histogramIsSplitMode }` | Toggles split mode |
| `refreshBtn` click | Data refresh | `{ refresh: true }` | Refreshes backend then re-renders |
| `columnsToggleBtn` click (open) | Open columns panel | `{ columns: true }` | Transient — no history push |
| `columnsToggleBtn` click (close) | Close columns panel | — | `setView(appState.activeView)` — full re-fetch |
| `errorViewCloseBtn` click | Dismiss error | — | `history.back()` — popstate recreates previous |
| `exportCsvBtn` click | CSV export | — | Stateless — `gridApi.exportDataAsCsv()` |

---

## 7. Error View — Modal with History Integration

### 7.1 Behavior

```
setView("chart", { refresh: true })
  → waiting-view: "Querying Deye Cloud…"
  → POST /api/refresh → TIMEOUT or 500
  → catch Error
  → pushState({ error: true, view: "chart", errorMessage: "Server error 500" })
  → show error-view
  → User clicks Close
  → history.back()
  → popstate fires → setView(previous view)
```

### 7.2 Error State in History

```typescript
// Normal entry:
{ view: "chart", isSplit: false }

// Error entry:
{ error: true, view: "chart", errorMessage: "Query timeout after 30s" }
```

### 7.3 popstate Error Detection

```typescript
window.addEventListener("popstate", () => {
  const historyState = history.state as { error?: boolean; errorMessage?: string } | null;

  if (historyState?.error) {
    // Restore error-view from history state
    waitingView.hide();
    hideAllDataPanels();
    errorView.show(historyState.errorMessage);
    disableAllButtons();
    errorViewCloseBtn.disabled = false;
    return;
  }

  // Normal restoration from URL — no double-push
  const urlState = getStateFromUrl();
  setView(urlState.view, { replace: true, split: urlState.isSplit });
});
```

### 7.4 Timeout Handling

All `fetch()` calls use an AbortController with a timeout (e.g., 30 seconds for data queries, 120 seconds for refresh):

```typescript
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 30_000);
try {
  const res = await fetch(url, { signal: controller.signal });
  // ...
} catch (err) {
  if (err.name === "AbortError") {
    throw new Error("Request timed out — server did not respond in time");
  }
  throw err;
} finally {
  clearTimeout(timeout);
}
```

---

## 8. State Variables — Naming Scheme

All variables use descriptive, non-ambiguous names. Every variable is classified by its persistence scope.

### 8.1 Global State Object (`appState`)

| Variable | Type | Persistence | Description |
|----------|------|-------------|-------------|
| `appState.columnMetadata` | `ColumnMeta[]` | Transient (session) | Column definitions from `/api/columns` (name + label) |
| `appState.selectedColumnNames` | `Set<string>` | localStorage | User-selected column names for data queries |
| `appState.dateRangeFrom` | `string` | URL-stateful | Start date of the query range (ISO) |
| `appState.dateRangeTo` | `string` | URL-stateful | End date of the query range (ISO) |
| `appState.minAvailableDate` | `string` | Transient (session) | Earliest date with data (from `/api/dates`) |
| `appState.maxAvailableDate` | `string` | Transient (session) | Latest date with data (from `/api/dates`) |
| `appState.rawDataRows` | `Row[]` | Transient (render) | Fetched raw inverter data rows (chart/grid views) |
| `appState.binnedDataRows` | `Row[]` | Transient (render) | Transformed histogram bins as rows (histogram-grid view) |
| `appState.rawDataChartInstance` | `Chart \| null` | Transient (render) | Chart.js instance for the raw data line chart |
| `appState.rawDataGridApi` | `GridApi \| null` | Transient (render) | AG Grid API for the raw data grid |
| `appState.activeView` | ViewMode | URL-stateful | Current data view: chart, grid, histogram, histogram-grid |

### 8.2 Histogram Module Variables (`histogram-chart.ts`)

| Variable | Type | Persistence | Description |
|----------|------|-------------|-------------|
| `histogramCombinedChartInstance` | `Chart \| null` | Transient (render) | Chart.js instance for the combined bar chart |
| `histogramSplitChartInstances` | `Chart[]` | Transient (render) | Array of Chart.js instances for split individual charts |
| `histogramIsSplitMode` | `boolean` | URL-stateful (`?split=1`) | Whether histogram is currently in split mode |
| `histogramLastApiResult` | `HistogramResponse \| null` | Transient (cache) | Cached histogram API response for split rendering |
| `histogramLastColumnNames` | `string[]` | Transient (cache) | Column names used in the last histogram API call |
| `histogramMaxAverageValues` | `Map \| null` | Transient (render) | Per-metric max average value + timestamp from histogram |

### 8.3 DOM Panel References (`shared.ts`)

| Variable | DOM ID | Description |
|----------|--------|-------------|
| `waitingViewPanel` | `#waiting-view` | Waiting overlay container |
| `waitingViewTextEl` | `#waiting-text` | Waiting message text element |
| `errorViewPanel` | `#error-view` | Error modal overlay container |
| `errorViewMessageEl` | `#error-message` | Error message text element |
| `errorViewCloseBtn` | `#error-close-btn` | Error modal close button |
| `columnsViewPanel` | `#columns-view` | Column selection panel |
| `histogramPanel` | `#histogram-panel` | Histogram controls (bin-size, split) — always between header and content |
| `rawDataChartView` | `#raw-data-chart-view` | Raw data line chart container |
| `rawDataGridView` | `#raw-data-grid-view` | Raw data grid container |
| `histogramView` | `#histogram-view` | Combined histogram bar chart container |
| `histogramGridView` | `#histogram-grid-view` | Histogram grid table container |
| `splitHistogramView` | `#split-histogram-view` | Split histogram scrollable container |
| `splitHistogramScroll` | `#split-histogram-scroll` | Inner scroll container for split charts |
| `summaryCardsPanel` | `#summary-cards` | Summary cards row |

### 8.4 DOM Button/Control References (`shared.ts`)

| Variable | DOM ID | Description |
|----------|--------|-------------|
| `dateFromInput` | `#date-from` | Start date picker |
| `dateToInput` | `#date-to` | End date picker |
| `prevDayBtn` | `#prev-day` | Previous day button |
| `nextDayBtn` | `#next-day` | Next day button |
| `todayBtn` | `#today-btn` | Go to today button |
| `refreshBtn` | `#refresh-btn` | Refresh data button |
| `columnsToggleBtn` | `#columns-toggle` | Open/close columns panel button |
| `viewToggleBtn` | `#view-toggle` | Toggle view mode button |
| `histogramToggleBtn` | `#histogram-btn` | Toggle histogram mode button |
| `exportCsvBtn` | `#export-btn` | CSV export button |
| `splitBtn` | `#split-btn` | Split/combine histogram button |
| `binSizeSelect` | `#bin-size-select` | Histogram bin size dropdown |
| `rowCountEl` | `#row-count` | Row/metric count display |
| `versionBadgeEl` | `#version-badge` | Version string display |

---

## 9. View Modes and Transitions

### 9.1 Normal Mode (chart / grid)

```
chart  ←─viewToggle─→  grid
  │                       │
  └────histogramBtn───────┘
         │
         ▼
  histogram ←─viewToggle─→ histogram-grid
```

### 9.2 Histogram Sub-Mode (split)

```
histogram (combined)  ←─splitBtn─→  histogram (split charts)
                                  │
                              ?split=1 in URL (bookmarkable)
```

Split mode is now a URL parameter (`?split=1`). It is bookmarkable and navigable via back/forward.

### 9.3 Button Specification Table

Every button in the title bar is documented with its text, visibility, toggle/action behavior, state variables, and statefulness.

| Button | Variable | Text / Label | Visibility | Type | Reads State | Writes State | Stateful? |
|--------|----------|-------------|------------|------|-------------|-------------|-----------|
| Prev Day | `prevDayBtn` | `‹` | Always | Action (shift -1 day) | `appState.dateRangeFrom`, `appState.dateRangeTo`, `appState.minAvailableDate` | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`/`from`/`to`) |
| Next Day | `nextDayBtn` | `›` | Always | Action (shift +1 day) | `appState.dateRangeFrom`, `appState.dateRangeTo`, `appState.maxAvailableDate` | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`/`from`/`to`) |
| Today | `todayBtn` | `Today` | Always | Action (set to today) | — | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`) |
| Refresh | `refreshBtn` | `↻ Refresh` / `⟳ Fetching…` | Always | Action (debounced) | — | Triggers `setView(activeView, { refresh: true })` | Stateless action |
| Columns Toggle | `columnsToggleBtn` | `☰ Select` (closed) / `↻ Load Data` (open) | Always | Toggle (open↔close columns-view) | — | Controls columns-view visibility (transient) | Stateless (columns persist to localStorage) |
| View Toggle | `viewToggleBtn` | See labels below | Always | Toggle (within mode) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| Histogram Toggle | `histogramToggleBtn` | See labels below | Always | Toggle (normal↔histogram mode) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| CSV Export | `exportCsvBtn` | `⬇ CSV` | Grid views only | Stateless action | `appState.rawDataGridApi` or `histogramGridApi` | — | Stateless action |
| Split | `splitBtn` | `Split` / `Combine` | Histogram view only | Toggle (combined↔split) | `histogramIsSplitMode`, URL `?split=1` | `histogramIsSplitMode`, URL `?split=1` | URL-stateful (via `split`) |
| Bin Size | `binSizeSelect` | `5` / `10` / `15` / `30` / `60` | Histogram mode (in histogram-panel) | Stateless action (triggers re-render) | Current selection | URL `?binSize=N` | URL-stateful (via `binSize`) |

#### View Toggle Button Labels (`viewToggleBtn`)

| `appState.activeView` | Button Text | Button Title | Toggles To |
|----------------------|------------|-------------|------------|
| `chart` | `📋 Data Grid` | "Switch to data grid" | `grid` |
| `grid` | `📈 Chart` | "Switch to chart" | `chart` |
| `histogram` | `📊 Histogram Grid` | "Switch to histogram grid" | `histogram-grid` |
| `histogram-grid` | `📈 Histogram Chart` | "Switch to histogram chart" | `histogram` |

#### Histogram Toggle Button Labels (`histogramToggleBtn`)

| `appState.activeView` | Button Text | Button Title | Toggles To |
|----------------------|------------|-------------|------------|
| `chart` | `📊 Histogram` | "Show binned average histogram" | `histogram` |
| `grid` | `📊 Histogram` | "Show binned average histogram" | `histogram-grid` |
| `histogram` | `📋 Raw Data` | "Switch back to raw data view" | `chart` |
| `histogram-grid` | `📋 Raw Data` | "Switch back to raw data view" | `grid` |

#### Columns Toggle Button Labels (`columnsToggleBtn`)

| columns-view State | Button Text | Button Title | Action |
|-------------------|------------|-------------|--------|
| Closed | `☰ Select` | "Select columns to display" | `setView(activeView, { columns: true })` |
| Open | `↻ Load Data` | "Close panel and load data" | `setView(appState.activeView)` |

#### Split Button Labels (`splitBtn`)

| `histogramIsSplitMode` | Button Text | Button Title | Action |
|----------------------|------------|-------------|--------|
| `false` | `Split` | "Split into individual charts" | `setView("histogram", { split: true })` |
| `true` | `Combine` | "Combine into single chart" | `setView("histogram", { split: false })` |

---

## 10. Data Flow

### 10.1 Normal Data Views (chart / grid)

```
setView("chart")
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → renderRawDataChartView(updateWaiting)
      → updateWaiting("Fetching raw data…")
      → GET /api/data-range?from=X&to=Y&columns=...  (or single day)
      → appState.rawDataRows = rows
      → updateSummaryCards(null)  // null = use rawDataRows
      → updateWaiting("Drawing chart…")
      → draw Chart.js into appState.rawDataChartInstance
      → return { ok: true }
  → hidePanel("waiting") → waitingView.hide()
  → showPanel("raw-data-chart")
  → show summary-cards
  → push URL history
  → enableAllButtons()
```

### 10.2 Histogram Data Views

```
setView("histogram", { split: true })
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → show histogram-panel (histogram controls)
  → renderHistogramView(updateWaiting, { split: true })
      → updateWaiting("Fetching histogram data…")
      → GET /api/histogram?from=X&to=Y&columns=...&binMinutes=N
      → histogramLastApiResult = response
      → histogramMaxAverageValues = maxValues
      → updateWaiting("Drawing histogram…")
      → draw combined bar chart → histogramCombinedChartInstance
      → if split: draw individual charts → histogramSplitChartInstances
      → histogramIsSplitMode = true
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("split-histogram")
  → show summary-cards
  → push URL history (?split=1)
  → enableAllButtons()
```

### 10.3 Refresh Flow

```
refreshBtn click → setView(appState.activeView, { refresh: true })
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → renderRefreshView(updateWaiting)
      → updateWaiting("Querying Deye Cloud…")
      → POST /api/refresh
      → updateWaiting("Fetching latest dates…")
      → GET /api/dates → update appState.minAvailableDate, appState.maxAvailableDate
      → return { ok: true }
  → refresh succeeded — recursive call:
  → setView(appState.activeView)
      → showPanel("waiting") → waitingView.show()
      → renderRawDataChartView(updateWaiting)
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("raw-data-chart")
  → push URL history
  → enableAllButtons()
```

### 10.4 Columns Flow

```
columnsToggleBtn click (open) → setView(appState.activeView, { columns: true })
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → renderColumnsView(updateWaiting)
      → updateWaiting("Loading column definitions…")
      → GET /api/columns (if appState.columnMetadata empty)
      → render checkboxes into columnsViewPanel
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("columns")
  → enableButtonsExcept(["refresh", "export", "viewToggle", "histogramToggle", "split", "binSize"])
  → columnsToggleBtn stays enabled (to close)
  → NO history push (transient)

User clicks columnsToggleBtn (close/"Load Data") → setView(appState.activeView)
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → renderRawDataChartView(updateWaiting)  // with appState.selectedColumnNames
  → hidePanel("waiting")
  → showPanel("raw-data-chart")
  → push URL history
  → enableAllButtons()
```

---

## 11. API Endpoints Used

| Endpoint | Method | Used By | Timeout | Purpose |
|----------|--------|---------|---------|---------|
| `/api/columns` | GET | renderColumnsView() | 10s | Column metadata (name + label) |
| `/api/dates` | GET | renderRefreshView(), init() | 10s | Min/max available data dates |
| `/api/data` | GET | renderChartView(), renderGridView() | 30s | Raw data rows (single day) |
| `/api/data-range` | GET | renderChartView(), renderGridView() | 30s | Raw data rows (range) |
| `/api/histogram` | GET | renderHistogramView() | 30s | Time-binned average data |
| `/api/refresh` | POST | renderRefreshView() | 120s | Trigger inverter data sync |
| `/api/version` | GET | init() | 5s | Backend version string |

---

## 12. Waiting View

### 12.1 Structure

```html
<div id="waiting-view" class="waiting-overlay">
  <div class="spinner"></div>
  <div id="waiting-text">Loading…</div>
</div>
```

### 12.2 Interface

```typescript
// Called by setView at step 2:
waitingView.show();

// Called by renderers before each async operation:
waitingView.setText("Fetching data from server…");
waitingView.setText("Drawing chart…");

// Called by setView on completion:
waitingView.hide();
```

### 12.3 Rules

1. `setView` always shows waiting-view as step 2, before any render path.
2. Every renderer receives `updateWaiting: (text: string) => void` callback.
3. Every renderer **must** call `updateWaiting()` before any `fetch()` or long operation.
4. `setView` hides waiting-view only after receiving `{ ok: true }` or catching an error.

---

## 13. Error View

### 13.1 Structure

```html
<div id="error-view" class="error-overlay">
  <div class="error-content">
    <h2>⚠️ Error</h2>
    <p id="error-message"></p>
    <button id="error-close-btn">Close</button>
  </div>
</div>
```

### 13.2 Behavior

- **Shown by:** `setView` catch block — after hiding waiting-view.
- **Pushes history:** Yes — `{ error: true, view, errorMessage }`.
- **Close button:** Stateless — calls `history.back()` only.
- **Buttons disabled:** All title bar buttons disabled while error-view is shown.
- **popstate restoration:** If `history.state.error === true`, popstate handler re-shows error-view instead of rendering data.

---

## 14. Issues to Consider

### 14.1 cleanupSplitMode() DOM Manipulation

**Current behavior:** `cleanupSplitMode()` calls `splitHistogramView.classList.remove("visible")` inside `histogram-chart.ts`.

**Design conflict:** §6.3 says "No DOM panel toggling — Renderers only draw into their target containers; setView controls panel visibility."

**Risk:** `cleanupSplitMode()` is called from inside `setView` before the render path. `setView` already calls `hideAllDataPanels()` in step 2, which hides `splitHistogramView`. So the class removal in `cleanupSplitMode()` is redundant — it operates on an already-hidden panel. **No functional change needed.** The class removal is a no-op that could be safely removed, but doing so risks breaking if the call order in `setView` ever changes.

**Recommendation:** Keep current behavior. The redundant class removal is harmless and acts as defensive cleanup. If future work removes the call from `setView`, `cleanupSplitMode()` already handles visibility correctly.

### 14.2 Chart.js Instance Destruction Timing

**Current behavior:** `cleanupSplitMode()` destroys Chart.js instances (`histogramSplitChartInstances`) before `setView` hides the panel in step 2.

**Design conflict:** §6.3 says renderers should not manipulate DOM visibility. `cleanupSplitMode()` destroys canvas-backed charts that may still be visible.

**Risk:** Destroying Chart.js instances while the canvas is still rendered could cause a brief visual flicker (blank canvas) before `setView` hides the panel in step 2.

**Mitigation:** `setView` step 2 calls `waitingView.show()` which overlays the canvas. The waiting-view has `position: fixed` and `z-index: 1000`, so it visually covers the canvas before `cleanupSplitMode()` runs in step 3. **No flicker observed.**

**Recommendation:** Keep current behavior. The waiting-view overlay prevents visible flicker. If future work changes the z-index or timing, consider deferring chart destruction to after `hideAllDataPanels()`.

### 14.3 updateNavButtonStates() in renderRefreshView

**Current behavior:** `renderRefreshView()` calls `updateNavButtonStates()` after fetching new date bounds, before the recursive `setView` call.

**Design conflict:** §6.3 says "No button enable/disable — setView controls button state exclusively."

**Risk:** `updateNavButtonStates()` sets `prevDayBtn.disabled` and `nextDayBtn.disabled`. This is a button-state mutation inside a renderer.

**Mitigation:** The recursive `setView` call re-enables all controls in step 4c, which includes calling `updateNavButtonStates()`. So the call in `renderRefreshView` is redundant. **Removing it is safe** as long as `setView` always calls `updateNavButtonStates()` in step 4c.

**Recommendation:** Currently removed from `renderRefreshView` in favor of `setView` handling it. Monitor for any edge cases where date bounds update but `setView` doesn't run (e.g., error path after successful refresh).
