# Frontend Design Document — Deye Logger Viewer

> **Status:** v2.2
> **Scope:** Single-page application, vanilla TS + Chart.js + AG Grid

> **Software Versioning scheme:** Frontend version is `major.minor.sub-minor` in file src/app.ts .
>
> - **major** — major new features, architectural changes, number must agree with this document major version
> - **minor** — design changes to implement new features or fix design issues, number must agree with this document minor version
> - **sub-minor** — bug fixes requiring no design changes

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
│  CONTENT AREA (scrollable, controlled    │
│  by setView)                             │
│  ┌────────────────────────────────────┐ │
│  │ Summary Cards (top, always in pane)│ │
│  ├────────────────────────────────────┤ │
│  │ ONE visible panel at a time:       │ │
│  │ • waiting-view (spinner + text)    │ │
│  │ • error-view (modal with Close btn)│ │
│  │ • info-view (non-modal info msg)   │ │
│  │ • columns-view (selection panel)   │ │
│  │ • data-view (chart/grid/histogram) │ │
│  └────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

### 1.1 Source Files

| File | Responsibility |
| ------ | ---------------- |
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

The title bar contains **all application buttons and controls** in a single horizontal area. When horizontal space runs out, buttons **wrap into additional rows** automatically (CSS `flex-wrap: wrap`). The title bar grows vertically as needed to accommodate wrapped rows, pushing the rest of the page content down. This is different from a fixed-height title bar — the title bar height is **dynamic**.

**Button ordering in wrapped rows:** Buttons are laid out left-to-right in the order listed below. When a row fills, remaining buttons flow to the next row. This means the bin-size and split buttons may appear on a second row when the viewport is narrow.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ☀️ Deye Logger Viewer  │ [date] │ [date] │ ‹ › Today │ ↻ │ ☰ │
│  📋 Data Grid │ 📊 Histogram │ ⬇ CSV │ Bin: 15 ▼ │ Day: All ▼ │ Split │
└──────────────────────────────────────────────────────────────────────────┘
```

| Element | ID | Purpose |
| --------- | ----- | --------- |
| `<h1>` | — | App title: "☀️ Deye Logger Viewer" |
| Date inputs | `#date-from`, `#date-to` | Date range selectors |
| Nav buttons | `#prev-day`, `#next-day`, `#today-btn` | Shift dates by ±1 day or go to today |
| Refresh button | `#refresh-btn` | Trigger backend data refresh |
| Columns toggle | `#columns-toggle` | Open/close column selection panel |
| View toggle | `#view-toggle` | Toggle between chart ↔ grid (or histogram ↔ histogram-grid) |
| Histogram button | `#histogram-btn` | Toggle between normal mode and histogram mode |
| CSV export | `#export-btn` | Export current grid as CSV (hidden in chart views) |
| Bin size | `#bin-size-select` | Histogram bin size dropdown: `5` / `10` / `15` / `30` / `60` (hidden in non-histogram modes) |
| Day filter | `#day-filter-select` | Histogram day-of-week dropdown: `All` / `Sun` / `Mon` / `Tue` / `Wed` / `Thu` / `Fri` / `Sat` (hidden in non-histogram modes) |
| Split button | `#split-btn` | Split/combine histogram buttons (visible only in histogram view) |

### 2.2 Status Bar (`<div class="status-bar">`)

| Element | ID | Purpose |
| --------- | ----- | --------- |
| Row count | `#row-count` | Shows "N rows", "N metrics", or "N bins" |
| Version badge | `#version-badge` | Shows "FE x.x.x / BE y.y.y" |

---

## 3. URL History Stateful Objects

These objects define the **page state** and must be pushed to URL history so that a user can bookmark a page, use browser back/forward, or reload to recreate the exact same state.

### 3.1 URL Query Parameters

| Parameter | Values | Source | Used By |
| ----------- | -------- | -------- | --------- |
| `view` | `chart`, `grid`, `histogram`, `histogram-grid` | `setView()` | `getStateFromUrl()`, `setView()` |
| `date` | ISO date string (YYYY-MM-DD) | Date inputs, nav buttons | `getStateFromUrl()` (single day) |
| `from` | ISO date string | Date inputs, nav buttons | `getStateFromUrl()` (range start) |
| `to` | ISO date string | Date inputs, nav buttons | `getStateFromUrl()` (range end) |
| `binSize` | `5`, `10`, `15`, `30`, `60` | `#bin-size-select` | `getUrlState()`, histogram fetch |
| `split` | `1` (presence = true) | Split button | `getUrlState()`, `setView()` |
| `dayFilter` | `all`, `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat` | `#day-filter-select` | `getUrlState()`, histogram fetch |

**Serialization rules** (`buildUrlParams()`):

- Single day: `?view=chart&date=2025-07-20`
- Range: `?view=chart&from=2025-07-18&to=2025-07-20`
- Histogram with custom bin: `?view=histogram&date=2025-07-20&binSize=30`
- Histogram split: `?view=histogram&date=2025-07-20&split=1`
- Histogram with day filter: `?view=histogram&date=2025-07-20&dayFilter=mon`
- Default `binSize=15` is omitted from URL
- Default `dayFilter=all` is omitted from URL

### 3.2 History State (pushState payload)

| Property | Type | Purpose |
| ---------- | ------ | --------- |
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
| --------- | ---------------- | ------- |
| `viewToggle` click | Yes (on success) | Full view change |
| `histogramBtn` click | Yes (on success) | Mode toggle |
| Date nav (prev/next/today/picker) | Yes (on success) | Date change triggers full re-render |
| `binSizeSelect` change | Yes (on success) | Re-renders current view |
| `dayFilterSelect` change | Yes (on success) | Re-renders current view |
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
| -------- | --------- | ---------- |
| **CSV Export** | `#export-btn` | Calls `gridApi.exportDataAsCsv()`. Browser download only. |
| **Close error** | Button in error-view | Calls `history.back()` to restore previous page. |
| **Column selection** | Checkboxes in `#columns-view` | Updates `state.selectedColumns`, persists to `localStorage`. Not in URL. |
| **Save as Default** | Button in columns-view | Persists current column set to `localStorage`. |
| **Reset Default** | Button in columns-view | Clears custom default, restores hardcoded defaults. |
| **Clear columns** | Button in columns-view | Clears all selections except `device_timestamp`. |
| **Default columns** | Button in columns-view | Restores default column set.

---

## 5. Content Panels — Mutual Exclusion

Below the title bar and state bar, **exactly one panel is visible at any time**. `setView` controls which panel is shown.

| Panel | DOM ID | Triggered By | Pushes History? |
| ------- | -------- | ------------- | ----------------- |
| **Waiting view** | `#waiting-view` | `setView()` step 2 — always shown first | No |
| **Error view** | `#error-view` | Render failure — modal with Close button | Yes (`error: true`) |
| **Info view** | `#info-view` | Data fetch returned zero rows, or general info message | No (transient) |
| **Columns view** | `#columns-view` | `setView(view, { columns: true })` | No (transient) |
| **Chart view** | `#chart-view` | `setView("chart")` | Yes |
| **Grid view** | `#grid-view` | `setView("grid")` | Yes |
| **Histogram view** | `#histogram-view` | `setView("histogram")` (not split) | Yes |
| **Histogram grid view** | `#histogram-grid-view` | `setView("histogram-grid")` | Yes |
| **Split histogram view** | `#split-histogram-view` | `setView("histogram", { split: true })` | Yes (`split=1`) |

**Invariant:** At any moment, exactly one of `{ waiting, error, info, columns, chart, grid, histogram, histogram-grid, split-histogram }` is visible. `setView` enforces this.

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
  │     │       appState.columnMetadata already loaded (in init)
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
  │     │       "histogramToggle", "split", "binSize", "dayFilter", "prevDay", "nextDay", "today"])
  │     │     → columnsToggleBtn stays enabled (to close)
  │     │     → NO history push (transient)
  │     │
  │     ├─ { ok: true } AND opts.refresh === true
  │     │     → refresh succeeded — recursive call:
  │     │     → setView(view)  // no refresh flag → falls to normal render
  │     │
  │     ├─ { ok: true } (normal data render)
  │     │     → Check for empty data result:
  │     │     │
  │     │     │  ┌─ rawDataRows.length === 0 (chart/grid views)
  │     │     │  ├─ → waitingView.hide()
  │     │     │  ├─ → infoView.show(noDataMessage)
  │     │     │  ├─ → showPanel("info")
  │     │     │  ├─ → enableAllButtons()
  │     │     │  ├─ → NO history push (transient)
  │     │     │  └─ → return (await user action)
  │     │     │
  │     │     │  ┌─ histogram data empty (histogram/histogram-grid views)
  │     │     │  ├─ → waitingView.hide()
  │     │     │  ├─ → infoView.show(noDataMessage)
  │     │     │  ├─ → showPanel("info")
  │     │     │  ├─ → enableAllButtons()
  │     │     │  ├─ → NO history push (transient)
  │     │     │  └─ → return
  │     │     │
  │     │     → (data present — normal path)
  │     │     → waitingView.hide()
  │     │     → show summary-cards (add .visible class to #summary-cards)
  │     │     → hide non-data panels (waiting, error, info, columns)
  │     │     → showPanel(view) — show appropriate data-view
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
        binSizeSelect.visible           ← histogram modes only
        dayFilterSelect.visible          ← histogram modes only
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
| ------ | -------- |
| **Always update waiting-view before backend call** | `updateWaiting("Fetching data…")` before any `fetch()` |
| **Update waiting-view during long operations** | `updateWaiting("Drawing chart…")` during chart construction |
| **Return `{ ok: true }` on success** | Uniform success indicator |
| **Throw on error** | `setView` catches and routes to error-view |
| **No DOM panel toggling** | Renderers only draw into their target containers; `setView` controls panel visibility |
| **No button enable/disable** | `setView` controls button state exclusively |
| **No URL/history manipulation** | `setView` controls history exclusively |

### 6.4 Call Sites

| Call Site | Trigger | Flags | Notes |
| ----------- | --------- | ------- | ------- |
| `init()` → `setView(urlState.view, { split: urlState.isSplit })` | Page load | `split` from URL | Initial render |
| `viewToggleBtn` click | View toggle button | — | Toggles chart↔grid or histogram↔histogram-grid |
| `histogramToggleBtn` click | Histogram mode button | — | Enters/exits histogram mode |
| Date nav buttons/pickers | Date change | — | `setView(appState.activeView)` — re-render with new dates |
| `popstate` | Browser back/forward | `{ replace: true, split: urlState.isSplit }` | Restores from URL state |
| `popstate` → error | Error state detected | — | Shows error-view directly (no render) |
| `binSizeSelect` change | Bin size dropdown | `split` from URL | Re-renders current histogram view |
| `dayFilterSelect` change | Day filter dropdown | `split` from URL | Re-renders current histogram view |
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

### 8.1 Global State Object (`appState`)

| Variable | Type | Persistence | Description |
| ---------- | ------ | ------------- | ------------- |
| `appState.columnMetadata` | `ColumnMeta[]` | Transient (session) | Column definitions from `/api/columns` (name + label); data sourced from backend which reads from `column_metadata` database table populated by deye-logger from DeyeCloud API |
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
| ---------- | ------ | ------------- | ------------- |
| `histogramCombinedChartInstance` | `Chart \| null` | Transient (render) | Chart.js instance for the combined bar chart |
| `histogramSplitChartInstances` | `Chart[]` | Transient (render) | Array of Chart.js instances for split individual charts |
| `histogramIsSplitMode` | `boolean` | URL-stateful (`?split=1`) | Whether histogram is currently in split mode |
| `histogramLastApiResult` | `HistogramResponse \| null` | Transient (cache) | Cached histogram API response for split rendering |
| `histogramLastColumnNames` | `string[]` | Transient (cache) | Column names used in the last histogram API call |
| `histogramMaxAverageValues` | `Map \| null` | Transient (render) | Per-metric max average value + timestamp from histogram |
| `histogramDayFilter` | `string` | URL-stateful (`?dayFilter=X`) | Current day-of-week filter: `all`, `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat` |

### 8.3 DOM Panel References (`shared.ts`)

| Variable | DOM ID | Description |
| ---------- | -------- | ------------- |
| `contentArea` | `#content-area` | Single scrollable content container (wraps summary cards + content panels) |
| `waitingViewPanel` | `#waiting-view` | Waiting overlay container |
| `waitingViewTextEl` | `#waiting-text` | Waiting message text element |
| `errorViewPanel` | `#error-view` | Error modal overlay container |
| `errorViewMessageEl` | `#error-message` | Error message text element |
| `errorViewCloseBtn` | `#error-close-btn` | Error modal close button |
| `infoViewPanel` | `#info-view` | Info message panel container |
| `infoViewMessageEl` | `#info-message` | Info message content element |
| `columnsViewPanel` | `#columns-view` | Column selection panel |
| `rawDataChartView` | `#raw-data-chart-view` | Raw data line chart container |
| `rawDataGridView` | `#raw-data-grid-view` | Raw data grid container |
| `histogramView` | `#histogram-view` | Combined histogram bar chart container |
| `histogramGridView` | `#histogram-grid-view` | Histogram grid table container |
| `splitHistogramView` | `#split-histogram-view` | Split histogram container |
| `splitHistogramScroll` | `#split-histogram-scroll` | Container for split charts (no inner scroll — single scroll pane on `#content-area`) |
| `summaryCardsPanel` | `#summary-cards` | Summary cards container (direct child of `#content-area`) |

### 8.4 DOM Button/Control References (`shared.ts`)

| Variable | DOM ID | Description |
| ---------- | -------- | ------------- |
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
| `dayFilterSelect` | `#day-filter-select` | Histogram day-of-week filter dropdown |
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
| -------- | ---------- | ------------- | ------------ | ------ | ------------- | ------------- | ----------- |
| Prev Day | `prevDayBtn` | `‹` | Always | Action (shift -1 day) | `appState.dateRangeFrom`, `appState.dateRangeTo`, `appState.minAvailableDate` | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`/`from`/`to`) |
| Next Day | `nextDayBtn` | `›` | Always | Action (shift +1 day) | `appState.dateRangeFrom`, `appState.dateRangeTo`, `appState.maxAvailableDate` | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`/`from`/`to`) |
| Today | `todayBtn` | `Today` | Always | Action (set to today) | — | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`) |
| Refresh | `refreshBtn` | `↻ Refresh` | Always | Action (debounced) | — | Triggers `setView(activeView, { refresh: true })` | Stateless action |
| Columns Toggle | `columnsToggleBtn` | `☰ Select` (closed) / `↻ Load Data` (open) | Always | Toggle (open↔close columns-view) | — | Controls columns-view visibility (transient) | Stateless (columns persist to localStorage) |
| View Toggle | `viewToggleBtn` | See labels below | Always | Toggle (within mode) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| Histogram Toggle | `histogramToggleBtn` | See labels below | Always | Toggle (normal↔histogram mode) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| CSV Export | `exportCsvBtn` | `⬇ CSV` | Grid views only | Stateless action | `appState.rawDataGridApi` or `histogramGridApi` | — | Stateless action |
| Split | `splitBtn` | `Split` / `Combine` | Histogram view only | Toggle (combined↔split) | `histogramIsSplitMode`, URL `?split=1` | `histogramIsSplitMode`, URL `?split=1` | URL-stateful (via `split`) |
| Bin Size | `binSizeSelect` | `5` / `10` / `15` / `30` / `60` | Histogram mode (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?binSize=N` | URL-stateful (via `binSize`) |
| Day Filter | `dayFilterSelect` | `All` / `Sun` / `Mon` / `Tue` / `Wed` / `Thu` / `Fri` / `Sat` | Histogram mode (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?dayFilter=X` | URL-stateful (via `dayFilter`) |

#### View Toggle Button Labels (`viewToggleBtn`)

| `appState.activeView` | Button Text | Button Title | Toggles To |
| ---------------------- | ------------ | ------------- | ------------ |
| `chart` | `📋 Data Grid` | "Switch to data grid" | `grid` |
| `grid` | `📈 Chart` | "Switch to chart" | `chart` |
| `histogram` | `📊 Histogram Grid` | "Switch to histogram grid" | `histogram-grid` |
| `histogram-grid` | `📈 Histogram Chart` | "Switch to histogram chart" | `histogram` |

#### Histogram Toggle Button Labels (`histogramToggleBtn`)

| `appState.activeView` | Button Text | Button Title | Toggles To |
| ---------------------- | ------------ | ------------- | ------------ |
| `chart` | `📊 Histogram` | "Show binned average histogram" | `histogram` |
| `grid` | `📊 Histogram Grid` | "Show binned average histogram grid" | `histogram-grid` |
| `histogram` | `📋 Raw Chart` | "Switch back to raw data chart" | `chart` |
| `histogram-grid` | `📋 Raw Grid` | "Switch back to raw data grid" | `grid` |

#### Columns Toggle Button Labels (`columnsToggleBtn`)

| columns-view State | Button Text | Button Title | Action |
| ------------------- | ------------ | ------------- | -------- |
| Closed | `☰ Select` | "Select columns to display" | `setView(activeView, { columns: true })` |
| Open | `↻ Load Data` | "Close panel and load selected data" | `setView(appState.activeView)` |

#### Split Button Labels (`splitBtn`)

| `histogramIsSplitMode` | Button Text | Button Title | Action |
| ---------------------- | ------------ | ------------- | -------- |
| `false` | `Split` | "Split columns into individual charts" | `setView("histogram", { split: true })` |
| `true` | `Combine` | "Combine columns into single chart" | `setView("histogram", { split: false })` |

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
  → show summary-cards (add .visible class to #summary-cards)
  → push URL history
  → enableAllButtons()
```

### 10.2 Histogram Data Views

```
setView("histogram", { split: true })
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → renderHistogramView(updateWaiting, { split: true })
      → updateWaiting("Fetching histogram data…")
      → GET /api/histogram?from=X&to=Y&columns=...&binMinutes=N&dayFilter=X
      → histogramLastApiResult = response
      → histogramMaxAverageValues = maxValues
      → updateWaiting("Drawing histogram…")
      → draw combined bar chart → histogramCombinedChartInstance
      → if split: draw individual charts → histogramSplitChartInstances
      → histogramIsSplitMode = true
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("split-histogram")
  → show summary-cards (add .visible class to #summary-cards)
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
      → appState.columnMetadata already populated (loaded in init)
      → render checkboxes into columnsViewPanel
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("columns")
  → enableButtonsExcept(["refresh", "export", "viewToggle", "histogramToggle", "split", "binSize", "dayFilter"])
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

### 10.5 Empty Data Flow (Info View)

```
setView("chart")
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → renderRawDataChartView(updateWaiting)
      → updateWaiting("Fetching raw data…")
      → GET /api/data → { rows: [] }
      → appState.rawDataRows = []
      → return { ok: true }
  → setView detects rawDataRows.length === 0
  → waitingView.hide()
  → infoView.show("No data found for 2025-07-20. ...")
  → showPanel("info")
  → enableAllButtons()
  → NO history push (transient)

User clicks Refresh from info-view:
  → setView("chart", { refresh: true })
  → disableAllButtons()
  → showPanel("waiting") → waitingView.show()
  → renderRefreshView → POST /api/refresh → success
  → recursive setView("chart")
  → renderRawDataChartView → data now present
  → showPanel("raw-data-chart")
  → push URL history
  → enableAllButtons()
```

---

## 11. API Endpoints Used

| Endpoint | Method | Used By | Timeout | Purpose |
| ---------- | -------- | --------- | --------- | --------- |
| `/api/columns` | GET | init(), renderColumnsView() | 10s | Column metadata (name + label); sourced from `column_metadata` database table via backend |
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

## 14. Info View — Non-Modal General-Purpose Message Panel

The info view is a non-modal panel for displaying informational messages. It is currently used for "no data" scenarios but is designed as a general-purpose info display that can show any informational content (e.g. About dialog, usage tips, empty-state guidance).

### 14.1 Behavior

```
setView("chart")
  → waiting-view shown
  → renderRawDataChartView()
      → GET /api/data → { rows: [] }
      → return { ok: true }  (no error — server responded correctly)
  → setView detects rawDataRows.length === 0
  → infoView.show("No data found for the selected date.")
  → showPanel("info")
  → enableAllButtons() — user can interact with all controls
  → NO history push (info is transient)
```

**Key properties:**

- **Non-modal:** Unlike error-view, the info-view does **not** block user interaction. All title-bar controls remain enabled.
- **No Back button:** Unlike error-view, the info-view has **no** Close button. The user dismisses it implicitly by interacting with any control (date nav, refresh, view toggle, columns).
- **No history push:** The info-view is transient — it is never pushed to URL history. It simply sits in the content area until the user does something.
- **Not popped:** The info-view is never "closed" explicitly. It is replaced by the waiting-view on the next `setView()` call.

### 14.2 Empty Data Messages

When a data renderer succeeds but returns zero rows, the following messages are displayed:

| View | Date context | Message |
| ------ | ------------- | --------- |
| chart/grid | single day | "No data found for **{date}**. Click **Refresh** to sync from the inverter, or select a different date." |
| chart/grid | range | "No data found for **{from}** to **{to}**. Click **Refresh** to sync from the inverter, or select a different date range." |
| histogram | any | "No histogram data available for the selected date range. Click **Refresh** to sync from the inverter, or select a different date." |
| histogram-grid | any | Same as histogram |

### 14.3 Init Procedure — Immediate Waiting View

On initial page load the browser must show visual feedback **before** any async metadata is fetched. The init procedure follows this exact sequence:

```
Page loaded
  → document ready (DOMContentLoaded or module evaluated)
  → Synchronously: show waiting-view with text "Loading…"
  → Title bar is already rendered (in HTML) — always visible
  → Status bar is already rendered (in HTML) — always visible (empty state OK)
  → Concurrent async fetches:
    ├─ GET /api/version → versionBadgeEl
    ├─ GET /api/columns → appState.columnMetadata
    └─ GET /api/dates → min/max available dates, updateNavButtonStates()
  → All metadata fetched → call setView(view, { replace: true, split })
    → setView's step 2: waiting-view already visible → show() is idempotent
    → Normal render path (fetch data, draw chart/grid, etc.)
    → On success: waiting-view hidden, data view shown
    → On error: waiting-view hidden, error-view shown
```

**Key properties:**

- The waiting-view is shown **synchronously** (no `await`), before any `fetch()` calls. This ensures the user never sees a blank page.
- Title bar and status bar are **already in the HTML** and rendered immediately by the browser — no JS needed.
- `setView()`'s step 2 (`waitingView.show()`) is called again after metadata loads. This call is **idempotent** — if the waiting-view is already visible, showing it again is a no-op.
- The waiting-view text during `init()` is the default "Loading…". During `setView()` rendering, it transitions to "Fetching data…", "Drawing chart…", etc.

**Error handling during init:**

- If any metadata fetch fails (version, columns, dates), the fetch is **silently skipped** (try/catch). The app continues to `setView()` with available data.
- If the final `setView()` call fails (data fetch error), the normal error-view path is followed.

#### 14.3.1 Init Flow Summary

| Phase | Action | Waiting View? | Async? |
| ------- | -------- | --------------- | -------- |
| 1 | Parse URL parameters | No | Sync |
| 2 | Show waiting-view ("Loading…") | **Yes** | Sync |
| 3a | Load `/api/version` | Yes (still) | Async |
| 3b | Load `/api/columns` | Yes (still) | Async |
| 3c | Load `/api/dates` | Yes (still) | Async |
| 4 | Call `setView(view, opts)` | Yes (idempotent show) | Async |
| 5a | Fetch data + render | Yes (updates text) | Async |
| 5b | Success → hide waiting, show data | No | Async |
| 5c | Error → hide waiting, show error | No | Async |

### 14.4 Future Use Cases

The info-view is intentionally general-purpose. Planned future uses include:

- **About dialog:** Application version, credits, usage info
- **Welcome message:** First-time user guidance
- **Feature announcements:** New feature descriptions
- **Configuration info:** System status, connection details

Any caller can invoke `infoView.show(message)` to display content. The panel is controlled via `setView()` using a sentinel view value or a dedicated `info` option.

### 14.5 Integration with setView

The info-view is shown by `setView` step 4 when data is empty. It can also be shown programmatically via:

```typescript
// From any caller:
infoView.show(messageHtml: string);
showPanel("info");
```

When the user interacts with any title-bar control while info-view is shown, `setView()` runs its normal lifecycle (waiting-view → render → result) and replaces the info-view.

### 14.6 Initial Load with No Data

When `init()` (see §14.3) finishes loading metadata and calls `setView()`, the normal empty-data flow applies. The only difference from the normal case is that the waiting-view is **already visible** from init (step 2 of §14.3), so `setView()`'s step 2 (`waitingView.show()`) is idempotent.

```
init() (§14.3)
  → parse URL parameters
  → show waiting-view ("Loading…")    ← §14.3 step 2
  → load /api/version, /api/columns, /api/dates  ← §14.3 step 3
  → call setView(view, { replace: true, split })  ← §14.3 step 4
      → setView step 2: waiting-view.show() (idempotent)
      → fetch data → 0 rows
      → infoView.show(noDataMessage)
      → showPanel("info")
      → enableAllButtons()
      → NO history push
```

The URL is **not** changed or pushed. The user sees the info message and can:

1. Click **Refresh** to sync from inverter
2. Change dates via nav buttons or date pickers
3. Toggle view mode (useless but harmless — will re-fetch)

### 14.7 Normal Initial Load

```
init() (§14.3)
  → parse URL parameters
  → show waiting-view ("Loading…")    ← §14.3 step 2
  → load /api/version → versionBadgeEl
  → load /api/columns → appState.columnMetadata (ensures columnMetadata available for all UI operations)
  → load /api/dates → min/max available dates, updateNavButtonStates()
  → call setView(urlState.view, { replace: true, split: urlState.isSplit })  ← §14.3 step 4
      → Normal render flow (see setView() lifecycle in §10.1–10.3)
      → waiting-view.text updates: "Fetching data…" → "Drawing chart…"
      → Data renders using appState.selectedColumnNames (from localStorage)
      → Columns panel will have metadata available if user clicks Select
```

---

## 15. Display Panel — Summary Cards + Chart/Grid

Each data view (`chart`, `grid`, `histogram`, `histogram-grid`) renders a **display panel** inside the single scrollable content area (`#content-area`). The summary cards are **always at the top** of the scrollable area, followed by exactly one visible content panel (chart, grid, histogram, etc.) below it.

```
┌──────────────────────────────────────────┐
│  #content-area (single scrollable pane)  │
│  ┌──────────────────────────────────────┐│
│  │ Summary Cards Bar (#summary-cards)   ││  ← at top, scrolls with pane
│  │ ┌──────┐ ┌──────┐ ┌──────┐ …        ││
│  │ │Card 1│ │Card 2│ │Card 3│ …        ││
│  │ └──────┘ └──────┘ └──────┘          ││
│  ├──────────────────────────────────────┤│
│  │ ONE visible content panel below:     ││
│  │                                      ││
│  │   ┌──────────────────────────────┐   ││
│  │   │   Chart.js chart or AG Grid  │   ││
│  │   │                              │   ││
│  │   │                              │   ││
│  │   └──────────────────────────────┘   ││
│  │                                      ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

### 15.1 Structure

The display panel is the content area shown inside the respective view containers:

| Sub-section | Purpose | Rendered By |
|-------------|---------|-------------|
| **Summary Cards Bar** (`#summary-cards`) | Row count, metric summary, time range, max/average values | Renderers (`renderRawDataChartView`, `renderRawDataGridView`, `renderHistogramView`, `renderHistogramGridView`) |
| **Chart / Grid Area** | The primary visualisation — Chart.js chart or AG Grid data table | Renderers |

**Order invariant:** Summary cards are **always** rendered above the chart/grid area. The DOM order never changes.

### 15.2 Summary Cards

Summary cards are rendered inside the `#summary-cards` container. They display aggregate information about the current dataset. The specific cards shown depend on the view mode:

| View | Cards Shown |
|------|-------------|
| `chart` / `grid` | Row count, time range, metric count, per-metric min/max/average (first few metrics) |
| `histogram` / `histogram-grid` | Bin count, time range, per-metric max average value + timestamp |

Cards are arranged **horizontally** (side by side) when sufficient horizontal space is available. When the viewport narrows, cards **switch to a vertical arrangement** (stacked, full-width).

Each card displays:
- **Label:** The metric name (e.g. "Max Grid Power")
- **Value:** The numeric value followed by its unit with a space separator (e.g. `1245.6 W`, `85 %`). The unit is extracted from column metadata via `extractUnit()`; if no unit is defined, only the bare number is shown.
- **Timestamp:** The timestamp of the max/average reading (small, muted text)

### 15.3 Responsive Behavior

The display panel is inside the **single scrollable content area** (`#content-area`). The summary cards are **always at the top** of the scroll pane, and the chart/grid area follows below. On all viewport sizes the entire content area is vertically scrollable.

#### 15.3.1 Cards Reduce Actual Dimensions to Save Vertical Space

When the viewport is narrow and the title bar wraps into multiple rows, less vertical space remains for the content area. The summary cards **reduce their actual layout dimensions** (padding, font-size, gap) via `calc()` multiplied by `--card-scale`. This is NOT `transform: scale()` which would leave invisible layout gaps that overlap the chart area:

- **Wide viewports (> 1200px):** Cards display at full size. The content area is large enough that cards + chart fit without scrolling.
- **Medium viewports (800–1200px):** Cards shrink proportionally — reduced padding, smaller font sizes, tighter spacing. `--card-scale: 0.85`. Cards arrange in **3 columns**.
- **Small viewports (500–800px):** Cards reach a further reduced scale (`--card-scale: 0.7`). Cards arrange in **2 columns**.
- **Very small viewports (< 500px):** Cards reach minimum scale (`--card-scale: 0.6`). Stacked full-width arrangement.

The transition between horizontal and vertical card arrangements is triggered by CSS media queries (at `600px`).

#### 15.3.2 Single Scroll Pane

The **entire content area** (`#content-area`) is vertically scrollable (`overflow-y: auto`). It contains the summary cards at the top and the active content panel below:

- The summary cards are **not sticky or fixed** — they are part of the scroll flow at the very top.
- To view the chart/grid, the user scrolls the entire content area downward.
- The chart/grid area always fills the remaining height inside its content panel.
- Content panels have `min-height: 300px` which forces `#content-area` to show a scrollbar when the viewport is too small.
- No view has its own nested scrollbar — there is exactly one scroll pane (`#content-area`).
- Scroll position is **not** preserved across view changes or re-renders.

```css
/* Structure */
#content-area {          /* single scrollable container */
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

#summary-cards {         /* top of scroll, reduced dimensions via calc() */
  flex-shrink: 0;
  padding: calc(12px * var(--card-scale, 1)) calc(24px * var(--card-scale, 1));
  gap: calc(12px * var(--card-scale, 1));
}

.content-panel {         /* fills remaining space, min-height forces scroll */
  flex: 1;
  min-height: 300px;
}
```

### 15.4 Viewport Breakpoints

| Breakpoint | Cards Layout | Scroll | Chart/Grid Visibility |
| ----------- | ------------- | -------- | ---------------------- |
| `> 1200px` | Horizontal, full size, auto-fit | No (fits) | Always visible |
| `901px – 1200px` | Horizontal, full size, auto-fit | No (fits) | Always visible |
| `601px – 900px` | Horizontal, scaled down (`--card-scale: 0.85`), 3 columns | Conditional | Visible |
| `401px – 600px` | Horizontal, scaled down (`--card-scale: 0.7`), 2 columns | Yes | Hidden by scroll |
| `≤ 400px` | Grid auto-fit, min scale (`--card-scale: 0.6`) | Yes | Hidden by scroll |

### 15.5 setView Integration

The display panel is rendered by every data-view renderer. The `setView` lifecycle integrates with it as follows:

```typescript
// In setView step 4c (normal render success):
  → waitingView.hide()
  → showPanel(view)                    // show chart/grid/histogram/histogram-grid container
  → show #summary-cards (add .visible class)
  → render/update cards into #summary-cards
  → buildUrlParams() → pushState
  → updateButtonLabels(view, split)
  → enableAllButtons()
```

**Key contract for renderers regarding the display panel:**

| Rule | Detail |
| ------ | -------- |
| **Render cards into existing container** | Cards are rendered into `#summary-cards` which is a direct child of `#content-area` (sibling of all content panels). Cards are **updated** (not recreated from scratch) — existing card elements are reused and their content/visibility adjusted. |
| **Cards shown/hidden by setView** | `setView` shows `#summary-cards` (via `.visible` class) before entering chart/grid/histogram views, and hides it before entering waiting/error/info/columns views. |
| **No manual scroll control** | Renderers must **not** manipulate scroll position. Scroll behavior is purely CSS-driven (`overflow-y: auto` on `#content-area`). |
| **No panel visibility toggling** | Renderers draw into their container; `setView` controls which content panel is visible (via `.visible` class). |
| **Charts/grids fill remaining space** | Content panels have `flex: 1` and `min-height: 300px` so they maintain a usable minimum height and force `#content-area` to scroll when vertical space is tight. Chart.js and AG Grid are initialized with dimensions from `getBoundingClientRect()`. |

### 15.6 Histogram Split Mode Display Panel

In split histogram mode (`?split=1`), the display panel structure is the same as other histogram views. Bin-size and split/combine controls are in the **title bar** (not in the display panel), so they are always visible regardless of scroll position.

```
┌──────────────────────────────────────────┐
│  #content-area (single scrollable pane)  │
│  ┌──────────────────────────────────────┐│
│  │ Summary Cards Bar (#summary-cards)   ││
│  │ ┌──────┐ ┌──────┐ ┌──────┐ …        ││
│  ├──────────────────────────────────────┤│
│  │ #split-histogram-view                ││
│  │  ┌───────────────────────────────┐   ││
│  │  │ #split-histogram-scroll      │   ││  ← no inner scroll
│  │  │ ┌───────────────────────────┐ │   ││
│  │  │ │  Chart 1                  │ │   ││
│  │  │ ├───────────────────────────┤ │   ││
│  │  │ │  Chart 2                  │ │   ││
│  │  │ ├───────────────────────────┤ │   ││
│  │  │ │  Chart 3                  │ │   ││
│  │  │ └───────────────────────────┘ │   ││
│  │  └───────────────────────────────┘   ││
│  │                                      ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

- Summary cards behave identically to non-split mode.
- Bin-size and split/combine controls are in the **title bar** (`#bin-size-select`, `#split-btn`) — always visible regardless of scroll position.
- The chart area contains **multiple charts** (one per metric) instead of a single chart.
- There is **no inner scroll** on `#split-histogram-scroll`. The single scroll pane is `#content-area`, which contains both the summary cards and all charts. Users scroll the entire content area to view charts below the summary cards.
- Responsive behavior (scaling, vertical stacking, scroll) applies the same way as other views.

### 15.7 Grid Column Labels

Both the raw data grid and histogram grid display units in column header labels. The `extractUnit()` helper is used to extract the unit from column metadata, consistent with chart axis labels.

| Grid Type | Header Format | Example |
|-----------|---------------|---------|
| Raw data grid | `label (unit)` | `Grid Power (W)`, `Battery SOC (%)` |
| Histogram grid | `label (unit)` | `Grid Power (W)`, `Battery SOC (%)` |

If no unit is defined in the metadata, the label is shown without parentheses (e.g. `Time`). The `device_timestamp` column is always labeled "Time" without a unit.

---

## 16. Issues to Consider

### 16.1 cleanupSplitMode() DOM Manipulation

**Current behavior:** `cleanupSplitMode()` calls `splitHistogramView.classList.remove("visible")` inside `histogram-chart.ts`.

**Design conflict:** §6.3 says "No DOM panel toggling — Renderers only draw into their target containers; setView controls panel visibility."

**Risk:** `cleanupSplitMode()` is called from inside `setView` before the render path. `setView` already calls `hideAllDataPanels()` in step 2, which hides `splitHistogramView`. So the class removal in `cleanupSplitMode()` is redundant — it operates on an already-hidden panel. **No functional change needed.** The class removal is a no-op that could be safely removed, but doing so risks breaking if the call order in `setView` ever changes.

**Recommendation:** Keep current behavior. The redundant class removal is harmless and acts as defensive cleanup. If future work removes the call from `setView`, `cleanupSplitMode()` already handles visibility correctly.

### 16.2 Chart.js Instance Destruction Timing

**Current behavior:** `cleanupSplitMode()` destroys Chart.js instances (`histogramSplitChartInstances`) before `setView` hides the panel in step 2.

**Design conflict:** §6.3 says renderers should not manipulate DOM visibility. `cleanupSplitMode()` destroys canvas-backed charts that may still be visible.

**Risk:** Destroying Chart.js instances while the canvas is still rendered could cause a brief visual flicker (blank canvas) before `setView` hides the panel in step 2.

**Mitigation:** `setView` step 2 calls `waitingView.show()` which overlays the canvas. The waiting-view has `position: fixed` and `z-index: 1000`, so it visually covers the canvas before `cleanupSplitMode()` runs in step 3. **No flicker observed.**

**Recommendation:** Keep current behavior. The waiting-view overlay prevents visible flicker. If future work changes the z-index or timing, consider deferring chart destruction to after `hideAllDataPanels()`.

### 16.3 updateNavButtonStates() in renderRefreshView

**Current behavior:** `renderRefreshView()` calls `updateNavButtonStates()` after fetching new date bounds, before the recursive `setView` call.

**Design conflict:** §6.3 says "No button enable/disable — setView controls button state exclusively."

**Risk:** `updateNavButtonStates()` sets `prevDayBtn.disabled` and `nextDayBtn.disabled`. This is a button-state mutation inside a renderer.

**Mitigation:** The recursive `setView` call re-enables all controls in step 4c, which includes calling `updateNavButtonStates()`. So the call in `renderRefreshView` is redundant. **Removing it is safe** as long as `setView` always calls `updateNavButtonStates()` in step 4c.

**Recommendation:** Currently removed from `renderRefreshView` in favor of `setView` handling it. Monitor for any edge cases where date bounds update but `setView` doesn't run (e.g., error path after successful refresh).

---

## 17. Change Management

This section tracks changes to the design document itself. Every modification to this document must be recorded below.

| Version | Date | Section Changed | Description |
| --------- | ------ | ---------------- | ------------- |
| 1.5 | 2025-07-28 | §1, §2, §3, §6, §8, §9, §10, §15 | Initial — full SPA architecture, URL state, setView lifecycle, responsive layout |
| 1.6 | 2025-07-28 | §4, §11 | Moved histogram display concerns (color, axis assignment, yAxisID, position) from backend to frontend — backend only serves data + unit; frontend computes display fields locally |
| 1.7 | 2025-07-28 | §15.3.1, §15.4, style.css | Summary cards use 3 columns at 800–1200px and 2 columns at 500–800px instead of 2 columns and stacked layout — prevents cards from growing to 100% horizontal width on small displays |
| 1.8 | 2025-07-28 | §14.3, §14.6, §14.7 | Init procedure: show waiting-view synchronously before metadata fetches (title bar, status bar, and waiting-view all visible immediately), then recursively call setView() after metadata loaded — eliminates blank-page period during init |
| 1.9 | 2026-07-29 | §9.3, §15.4 | Fix viewport breakpoints in 15.4 (actual CSS: 900px/600px/400px) and button emoji in 9.3 (💫 not 📋 for Data Grid/Raw Chart/Raw Grid); remove non-existent Refresh `⟳ Fetching…` alternate text |
| 1.10 | 2026-07-29 | §15.6, §8.3 | Correct §15.6 — no inner scroll on `#split-histogram-scroll`; entire content area including summary cards scrolls together via `#content-area` |
| 2.0 | 2025-07-30 | §2.1, §3.1, §3.3, §6.4, §8.2, §8.4, §9.3, §10.2, §17 | Day-of-week filter for histogram — new `dayFilter` URL parameter, `#day-filter-select` dropdown in title bar (visible in histogram modes), `histogramDayFilter` module variable, backend passes `dayFilter` to `/api/histogram`. Version bumped to 2.0. |
| 2.1 | 2026-07-30 | §8.1, §11 | Column metadata sourced exclusively from backend `/api/columns` which reads from `column_metadata` database table — no hardcoded column structures in frontend; backend reads column data from database populated by deye-logger from DeyeCloud API |
| 2.2 | 2026-07-30 | §15.2 | Summary cards and grid column labels display units — summary card values show `value unit` (e.g. `1245.6 W`), grid headers show `label (unit)` (e.g. `Grid Power (W)`) when a unit is defined in column metadata; raw data grid and histogram grid both use `extractUnit()` for consistency with chart axis labels |
