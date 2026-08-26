# Frontend Design Document — Deye Logger Viewer

> **Status:** v3.0
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
│  — row count, view label, version badge  │
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
│  │ • stats-view (per-column stat cards)│ │
│  └────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

### 1.1 Source Files

| File | Responsibility |
| ------ | ---------------- |
| `dom-refs.ts` | DOM element references (isolated to break circular dependencies) |
| `shared.ts` | Global state object, URL parsing, utility helpers, re-exports DOM refs |
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
│  📋 Data Grid │ 📊 Histogram │ 📈 Stats │ ⬇ CSV │ Bin: 15 ▼ │ Day: All ▼ │
│  High: 95% ▼ │ Low: 5% ▼ │ Split │
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
| Stats button | `#stats-btn` | Toggle between the Stats view and the chart view |
| CSV export | `#export-btn` | Export current grid as CSV (hidden in chart views) |
| Bin size | `#bin-size-select` | Histogram bin size dropdown: `5` / `10` / `15` / `30` / `60` (hidden in non-histogram modes) |
| Day filter | `#day-filter-select` | Day-of-week dropdown: `All` / `Sun` / `Mon` / `Tue` / `Wed` / `Thu` / `Fri` / `Sat`. Visible in histogram modes **and** the Stats view; limits histogram bins (histogram) or statistics calculations (Stats) to that weekday |
| High cutoff | `#high-cutoff-select` | Stats high-threshold percentile dropdown: `50` / `75` / `90` / `95` / `99` (default `95`); visible only in the Stats view |
| Low cutoff | `#low-cutoff-select` | Stats low-threshold percentile dropdown: `1` / `5` / `10` / `25` / `50` (default `5`); visible only in the Stats view |
| Split button | `#split-btn` | Split/combine histogram buttons (visible only in histogram view) |

### 2.2 Status Bar (`<div class="status-bar">`)

| Element | ID | Purpose |
| --------- | ----- | --------- |
| Row count | `#row-count` | Shows "N rows", "N metrics", or "N bins" |
| View label | `#view-label` | Shows the current view name: Chart / Data Grid / Histogram / Histogram Grid / Stats |
| Range days | `#range-days` | Always visible. Shows the number of days in the selected date range as "N days" (or "1 day"). Count = number of calendar days from `from` to `to` inclusive; any fractional day (e.g. a partial first/last day of the range relative to available data) is **counted as a whole day** (`Math.ceil`). Updated whenever the date range changes, independent of the active view |
| Version badge | `#version-badge` | Shows "FE x.x.x / BE y.y.y" |

### 2.3 Button Active State Styling

Buttons use the `.active` CSS class (blue background `#3182ce`) to indicate the **currently selected view**. The active state is applied via `classList.toggle()` in `updateButtonLabels()`:

| Button | ID | Active when… |
| --------- | ----- | --------- |
| `📋 Data Grid` | `#view-toggle` | **Always active** (blue) when visible — `classList.toggle("active", true)` unconditionally |
| `📊 Histogram` | `#histogram-btn` | **Always active** (blue) when visible — `classList.toggle("active", true)` unconditionally |
| `☰ Select` | `#columns-toggle` | When the **columns panel is open** |

Both view toggle buttons remain blue regardless of which specific view is active, providing consistent visual feedback that the buttons are enabled and functional.

---

## 3. URL History Stateful Objects

These objects define the **page state** and must be pushed to URL history so that a user can bookmark a page, use browser back/forward, or reload to recreate the exact same state.

### 3.1 URL Query Parameters

| Parameter | Values | Source | Used By |
| ----------- | -------- | -------- | --------- |
| `view` | `chart`, `grid`, `histogram`, `histogram-grid`, `stats` | `setView()` | `getUrlState()`, `setView()` |
| `date` | ISO date string (YYYY-MM-DD) | Date inputs, nav buttons | `getUrlState()` (single day) |
| `from` | ISO date string | Date inputs, nav buttons | `getUrlState()` (range start) |
| `to` | ISO date string | Date inputs, nav buttons | `getUrlState()` (range end) |
| `binSize` | `5`, `10`, `15`, `30`, `60` | `#bin-size-select` | `getUrlState()`, histogram fetch |
| `split` | `1` (presence = true) | Split button | `getUrlState()`, `setView()` |
| `dayFilter` | `all`, `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat` | `#day-filter-select` | `getUrlState()`, histogram fetch, stats fetch |
| `highCutoff` | `50`, `75`, `90`, `95`, `99` | `#high-cutoff-select` | `getUrlState()`, stats fetch |
| `lowCutoff` | `1`, `5`, `10`, `25`, `50` | `#low-cutoff-select` | `getUrlState()`, stats fetch |

**Serialization rules** (`buildUrlString()`):

- Single day: `?view=chart&date=2025-07-20`
- Range: `?view=chart&from=2025-07-18&to=2025-07-20`
- Histogram with custom bin: `?view=histogram&date=2025-07-20&binSize=30`
- Histogram split: `?view=histogram&date=2025-07-20&split=1`
- Histogram with day filter: `?view=histogram&date=2025-07-20&dayFilter=mon`
- Stats view: `?view=stats&date=2025-07-20&highCutoff=90&lowCutoff=10&dayFilter=sun`
- Default `binSize=15` is omitted from URL
- Default `dayFilter=all` is omitted from URL
- Default `highCutoff=95` and `lowCutoff=5` are omitted from URL

### 3.2 History State (pushState payload)

| Property | Type | Purpose |
| ---------- | ------ | --------- |
| `view` | string | Current view mode |
| `isSplit` | boolean | Whether histogram is in split mode (redundant with URL but available for fast popstate) |
| `error` | boolean | Whether this is an error-state entry |
| `errorMessage` | string | Error message to restore if `error=true` |
| `columns` | boolean | Whether this entry shows the columns selection panel (URL unchanged — panel is not bookmarkable) |

The history state payload supplements the URL — the URL is the authoritative source (bookmarkable), the payload is for fast popstate restoration.

### 3.3 State Push Points

**URL is pushed only on successful render completion.** Errors also push (with `error=true` marker). Transient views (info panel, refresh-in-progress) do **not** push history. Opening the columns panel **does** push a history entry: the current URL is kept unchanged, but the payload carries a `columns: true` marker so browser back/forward can restore the panel (v2.8 — fixes #47).

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
| `dayFilterSelect` change | Yes (on success) | Re-renders current view (histogram or stats) |
| `highCutoffSelect` / `lowCutoffSelect` change | Yes (on success) | Re-renders stats view with new cutoffs |
| Stats button click | Yes (on success) | Enters `stats` view / returns to `chart` |
| Split/Combine toggle | Yes (on success) | `split=1` in URL |
| `popstate` (browser back/forward) | No (`replace`) | Restores view without double-push |
| `popstate` → error state | No (re-shows error) | Detects `{ error: true }` marker |
| `popstate` → columns state | No (`replace`) | Detects `{ columns: true }` marker — re-shows columns panel |
| Initial load | Yes (on success) | Sets initial history entry |
| Refresh success | Yes (on success) | Re-renders current view (dates unchanged) |
| Refresh failure | — | History pushed *before* refresh so `history.back()` restores pre-refresh state |
| Open columns panel | **Yes** | Same URL, payload `{ columns: true }` — browser back returns to previous data view |
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
| **Columns view** | `#columns-view` | `setView(view, { columns: true })` | Yes (`columns: true` marker, URL unchanged) |
| **Chart view** | `#raw-data-chart-view` | `setView("chart")` | Yes |
| **Grid view** | `#raw-data-grid-view` | `setView("grid")` | Yes |
| **Histogram view** | `#histogram-view` | `setView("histogram")` (not split) | Yes |
| **Histogram grid view** | `#histogram-grid-view` | `setView("histogram-grid")` | Yes |
| **Split histogram view** | `#split-histogram-view` | `setView("histogram", { split: true })` | Yes (`split=1`) |
| **Stats view** | `#stats-view` | `setView("stats")` | Yes |

**Invariant:** At any moment, exactly one of `{ waiting, error, info, columns, chart, grid, histogram, histogram-grid, split-histogram, stats }` is visible. `setView` enforces this.

---

## 6. setView Controller — Unified Lifecycle

### 6.1 Signature

```typescript
interface SetViewOptions {
  replace?: boolean;      // use replaceState instead of pushState (default: false)
  refresh?: boolean;      // transient — trigger backend refresh before rendering
  columns?: boolean;      // show columns selection panel (pushes history entry with columns marker)
  split?: boolean;        // URL-param — split histogram mode
}

function setView(
  view: "chart" | "grid" | "histogram" | "histogram-grid" | "stats",
  opts?: SetViewOptions,
): Promise<void>
```

### 6.2 Unified Execution Flow

```
setView(view, opts?)
  │
  ├─ STEP 1: disableAllControls() — debounce protection
  │     All title-bar controls disabled (prevents double-clicks during render)
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
  │     │       appState.columnMetadata loaded in init (background) —
  │     │       lazy-fetched from /api/columns here if not yet available
  │     │       render checkboxes into columnsViewPanel
  │     │       return { ok: true }
  │     │
  │     ├─ opts.refresh === true
  │     │     → push current view state to history (so `history.back()` restores pre-refresh state on error)
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
  │     │     → non-split: renderHistogramChartView(updateWaiting)
  │     │     → split:    renderSplitHistogramView(updateWaiting)
  │     │       updateWaiting("Fetching histogram data…")
  │     │       GET /api/histogram → histogramLastApiResult (via fetchHistogramData())
  │     │       updateWaiting("Drawing histogram…")
  │     │       draw combined chart; split mode also draws individual charts
  │     │       return { ok: true }
  │     │
  │     ├─ view === "histogram-grid"
  │             → renderHistogramGridView(updateWaiting)
  │             updateWaiting("Fetching histogram data…")
  │             GET /api/histogram → histogramLastApiResult
  │             updateWaiting("Building grid…")
  │             init/update histogram AG Grid
  │             return { ok: true }
  │     │
  │     └─ view === "stats"
  │             → renderStatsView(updateWaiting)
  │             updateWaiting("Fetching statistics…")
  │             GET /api/stats?from&to&columns&dayFilter&highCutoff&lowCutoff
  │               → appState.statsResult (per-column stat objects, see §16)
  │             updateWaiting("Building stat cards…")
  │             build one stat card per numeric column into #stats-view
  │             return { ok: true }
  │
  ├─ STEP 4: Handle result
  │     │
  │     ├─ { ok: true } AND opts.columns === true
  │     │     → waitingView.hide()
  │     │     → showPanel("columns")
  │     │     → enableOnlyControls(["columnsToggle"])
  │     │     → pushState({ view, isSplit: false, columns: true }) with current URL unchanged
  │     │       (replaceState when called with replace: true, e.g. from popstate)
  │     │
  │     ├─ { ok: true } AND opts.refresh === true
  │     │     → refresh succeeded — fall through to normal render (no recursive call)
  │     │     → (normal render succeeds) → pushState with same URL → show data-view
  │     │     → (refresh fails / normal render fails) → catch Error → pushState({ error: true }) → show error-view
  │     │     → User clicks Close → history.back() → pops error entry → pops pre-refresh entry → popstate restores pre-refresh view
  │     │
  │     ├─ { ok: true } (normal data render)
  │     │     → Check for empty data result:
  │     │     │
  │     │     │  ┌─ rawDataRows.length === 0 (chart/grid views)
  │     │     │  ├─ → waitingView.hide()
  │     │     │  ├─ → infoView.show(noDataMessage)
  │     │     │  ├─ → showPanel("info")
  │     │     │  ├─ → enableAllControls()
  │     │     │  ├─ → NO history push (transient)
  │     │     │  └─ → return (await user action)
  │     │     │
  │     │     │  ┌─ histogram data empty (histogram/histogram-grid views)
  │     │     │  ├─ → waitingView.hide()
  │     │     │  ├─ → infoView.show(noDataMessage)
  │     │     │  ├─ → showPanel("info")
  │     │     │  ├─ → enableAllControls()
  │     │     │  ├─ → NO history push (transient)
  │     │     │  └─ → return
  │     │
  │     │  ┌─ stats result empty (stats view: `stats: []`)
  │     │  ├─ → waitingView.hide()
  │     │  ├─ → infoView.show(noDataMessage)
  │     │  ├─ → showPanel("info")
  │     │  ├─ → enableAllControls()
  │     │  ├─ → NO history push (transient)
  │     │  └─ → return
  │     │     │
  │     │     → (data present — normal path)
  │     │     → waitingView.hide()
  │     │     → showPanel(view) — show appropriate data-view
  │     │     → show summary-cards (add .visible class to #summary-cards)
  │     │     → updateButtonLabels(view, split)
  │     │     → update view label (#view-label)
  │     │     → buildUrlString() → history.pushState/replaceState
  │     │     → enableAllControls()
  │     │     → updateNavButtonStates()
  │     │
  │     └─ catch Error
  │             → waitingView.hide()
  │             → history.pushState({ error: true, view, errorMessage: err.message })
  │             → errorView.show(err.message)
  │             → enableOnlyControls([])
  │             → errorViewCloseBtn.disabled = false
  │
  └─ STEP 5: updateButtonLabels(view, split)
        exportCsvBtn.visible          ← grid views only
        histogramToggleBtn.visible    ← all views except stats
        histogramToggleBtn.text/title  ← contextual label
        viewToggleBtn.visible          ← all views except stats
        viewToggleBtn.text/title       ← contextual label
        statsBtn.text/title            ← contextual label (see §9.3)
        splitBtn.visible               ← histogram view only
        binSizeSelect.visible           ← histogram modes only
        dayFilterSelect.visible          ← histogram modes OR stats view
        highCutoffSelect.visible        ← stats view only
        lowCutoffSelect.visible         ← stats view only
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
| `popstate` → columns | `{ columns: true }` marker detected | `{ columns: true, replace: true }` | Re-shows columns panel (no data fetch) |
| `binSizeSelect` change | Bin size dropdown | `split` from URL | Re-renders current histogram view |
| `dayFilterSelect` change | Day filter dropdown | `split` from URL | Re-renders current histogram or stats view |
| `highCutoffSelect` / `lowCutoffSelect` change | Cutoff dropdowns (stats view) | — | `setView("stats")` — re-renders with new thresholds |
| `statsBtn` click | Stats view button | — | In stats view → `setView("chart")`; otherwise → `setView("stats")` |
| `splitBtn` click | Split/combine toggle | `{ split: !histogramIsSplitMode }` | Toggles split mode |
| `refreshBtn` click | Data refresh | `{ refresh: true }` | Refreshes backend then re-renders |
| `columnsToggleBtn` click (open) | Open columns panel | `{ columns: true }` | Pushes history entry with `columns: true` marker (URL unchanged) |
| `columnsToggleBtn` click (close) | Close columns panel | — | `setView(appState.activeView)` — full re-fetch |
| `errorViewCloseBtn` click | Dismiss error | — | `history.back()` — popstate recreates previous |
| `exportCsvBtn` click | CSV export | — | Stateless — `gridApi.exportDataAsCsv()` |

---

## 7. Error View — Modal with History Integration

### 7.1 Behavior

#### 7.1.1 Refresh Failure

```
setView("chart", { refresh: true })
  → pushState({ view: "chart", isSplit: false })          ← pre-refresh snapshot
  → waiting-view: "Querying Deye Cloud…"
  → POST /api/refresh → TIMEOUT or 500
  → catch Error
  → pushState({ error: true, view: "chart", errorMessage: "Server error 500" })
  → show error-view
  → User clicks Close
  → history.back()                                       ← pops error entry
  → history.back()                                       ← pops pre-refresh entry
  → popstate fires → setView("chart", { replace: true }) ← restores pre-refresh view
```

**Key invariant:** A pre-refresh state is always pushed to history *before* `renderRefreshView()` runs. This ensures that `history.back()` from the error-view has a valid entry to restore. The refresh operation itself does not change the URL (the same view is re-rendered), so the pre-push and post-refresh URL are identical.

#### 7.1.2 Normal Render Failure (non-refresh)

```
setView("chart")
  → renderRawDataChartView()
      → GET /api/data → TIMEOUT or 500
      → throw Error
  → catch Error
  → pushState({ error: true, view: "chart", errorMessage: "Request timed out" })
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
  const historyState = history.state as { error?: boolean; errorMessage?: string; columns?: boolean; view?: string } | null;

  if (historyState?.columns) {
    // Restore columns panel from history state — no data fetch
    setView(historyState.view ?? appState.activeView, { columns: true, replace: true });
    return;
  }

  if (historyState?.error) {
    // Restore error-view from history state
    waitingView.hide();
    hideAllDataPanels();
    errorView.show(historyState.errorMessage);
    enableOnlyControls([]);
    errorViewCloseBtn.disabled = false;
    return;
  }

  // Normal restoration from URL — no double-push
  const urlState = getUrlState();
  setView(urlState.view, { replace: true, split: urlState.isSplit });
});
```

### 7.4 Timeout Handling

All `fetch()` calls use an AbortController with a timeout (e.g., 30 seconds for data queries, 120 seconds for refresh). The `setView` error path (and the popstate error-restore path) appends a hint to timeout messages: *"This is likely a network timeout. Try clicking the browser's refresh button to retry."*:

```typescript
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 30_000);
try {
  const res = await fetch(url, { signal: controller.signal });
  // ...
} catch (err) {
  if (err.name === "AbortError") {
    throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
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
| `appState.binnedDataRows` | `Row[]` | Transient (render) | Declared but currently unused (reserved) — histogram-grid rows are built locally in the renderer via `histogramResultToRows()` |
| `appState.rawDataChartInstance` | `Chart \| null` | Transient (render) | Chart.js instance for the raw data line chart |
| `appState.rawDataGridApi` | `GridApi \| null` | Transient (render) | AG Grid API for the raw data grid |
| `appState.statsResult` | `StatsResponse \| null` | Transient (render) | Last `/api/stats` response (per-column stat objects) for the stats view |
| `appState.activeView` | ViewMode | URL-stateful | Current data view: chart, grid, histogram, histogram-grid, stats |

### 8.2 Histogram Module Variables (`histogram-chart.ts`)

| Variable | Type | Persistence | Description |
| ---------- | ------ | ------------- | ------------- |
| `histogramCombinedChartInstance` | `Chart \| null` | Transient (render) | Chart.js instance for the combined bar chart |
| `histogramSplitChartInstances` | `Chart[]` | Transient (render) | Array of Chart.js instances for split individual charts |
| `histogramIsSplitMode` | `boolean` | URL-stateful (`?split=1`) | Whether histogram is currently in split mode |
| `histogramLastApiResult` | `HistogramResponse \| null` | Transient (cache) | Cached histogram API response for split rendering |
| `histogramLastColumnNames` | `string[]` | Transient (cache) | Column names used in the last histogram API call |
| `histogramMaxAverageValues` | `Map \| null` | Transient (render) | Per-metric max average value + timestamp from histogram |
| — | — | — | The day-of-week filter is **not** stored in module state — `fetchHistogramData()` reads `#day-filter-select` directly at fetch time; the URL parameter `?dayFilter=X` is the stateful source |

### 8.2.1 DOM References Module (`dom-refs.ts`)

All DOM element references are consolidated in `dom-refs.ts` to break circular dependencies. This module has no internal dependencies and is imported by other modules as needed.

**Import graph:**
```
dom-refs.ts (no internal deps)
    ↑
shared.ts → dom-refs.ts (re-exports for backward compatibility)
    ↑
other modules → shared.ts + dom-refs.ts
```

**Rules:**
- `dom-refs.ts` must never import from other application modules
- `shared.ts` re-exports all DOM refs for backward compatibility
- New modules should import directly from `dom-refs.ts` when they need DOM refs
- Existing imports from `shared.ts` continue to work

### 8.3 DOM Panel References (`dom-refs.ts`)

| Variable | DOM ID | Description |
| ---------- | -------- | ------------- |
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
| `statsViewPanel` | `#stats-view` | Stats view container — grid of per-column stat cards (direct child of `#content-area`) |
| `summaryCardsPanel` | `#summary-cards` | Summary cards container (direct child of `#content-area`; **hidden** in stats view) |

### 8.4 DOM Button/Control References (`dom-refs.ts`)

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
| `dayFilterSelect` | `#day-filter-select` | Day-of-week filter dropdown (histogram modes and stats view) |
| `highCutoffSelect` | `#high-cutoff-select` | Stats high-threshold percentile dropdown (stats view only) |
| `lowCutoffSelect` | `#low-cutoff-select` | Stats low-threshold percentile dropdown (stats view only) |
| `statsBtn` | `#stats-btn` | Stats view toggle button |
| `rowCountEl` | `#row-count` | Row/metric count display |
| `viewLabelEl` | `#view-label` | Current view name display |
| `rangeDaysEl` | `#range-days` | Selected date range day count display (always visible) |
| `versionBadgeEl` | `#version-badge` | Version string display |

---

## 9. View Modes and Transitions

### 9.1 Normal Mode (chart / grid) and Stats

```
chart  ←─viewToggle─→  grid
  │                       │
  ├──histogramBtn─────────┤
  │                       │
  │     statsBtn (from chart or grid or any histogram view)
  ▼                       ▼
  stats            histogram ←─viewToggle─→ histogram-grid
   │
   └──statsBtn──→ chart   (no grid/histogram counterpart of stats;
                          viewToggle and histogramBtn are hidden in stats view)
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
| Refresh | `refreshBtn` | `↻ Refresh` | Always | Action (debounced) | — | Triggers `setView(activeView, { refresh: true })`; pushes pre-refresh snapshot to history for error recovery | URL-stateful (pre-refresh snapshot) |
| Columns Toggle | `columnsToggleBtn` | `☰ Select` (closed) / `↻ Load Data` (open) | Always | Toggle (open↔close columns-view) | — | Controls columns-view visibility (opening pushes history entry) | Stateless (columns persist to localStorage) |
| View Toggle | `viewToggleBtn` | See labels below | Always | Toggle (within mode) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| Histogram Toggle | `histogramToggleBtn` | See labels below | Always | Toggle (normal↔histogram mode) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| CSV Export | `exportCsvBtn` | `⬇ CSV` | Grid views only | Stateless action | `appState.rawDataGridApi` or `histogramGridApi` | — | Stateless action |
| Split | `splitBtn` | `Split` / `Combine` | Histogram view only | Toggle (combined↔split) | `histogramIsSplitMode`, URL `?split=1` | `histogramIsSplitMode`, URL `?split=1` | URL-stateful (via `split`) |
| Bin Size | `binSizeSelect` | `5` / `10` / `15` / `30` / `60` | Histogram mode (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?binSize=N` | URL-stateful (via `binSize`) |
| Day Filter | `dayFilterSelect` | `All` / `Sun` / `Mon` / `Tue` / `Wed` / `Thu` / `Fri` / `Sat` | Histogram mode **and** stats view (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?dayFilter=X` | URL-stateful (via `dayFilter`) |
| High Cutoff | `highCutoffSelect` | `50` / `75` / `90` / `95` / `99` (default `95`) | Stats view only (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?highCutoff=N` | URL-stateful (via `highCutoff`) |
| Low Cutoff | `lowCutoffSelect` | `1` / `5` / `10` / `25` / `50` (default `5`) | Stats view only (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?lowCutoff=N` | URL-stateful (via `lowCutoff`) |
| Stats Toggle | `statsBtn` | See labels below | All views (in title bar) | Toggle (stats↔chart) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |

#### Stats Button Labels (`statsBtn`)

| `appState.activeView` | Button Text | Button Title | Action |
| ---------------------- | ------------ | ------------- | -------- |
| `chart` / `grid` / `histogram` / `histogram-grid` | `📈 Stats` | "Show per-column statistics for the selected range" | `setView("stats")` |
| `stats` | `📊 Back to Chart` | "Return to the chart view" | `setView("chart")` |

In the stats view, `viewToggleBtn` and `histogramToggleBtn` are **hidden** (stats has no grid/histogram counterpart). Date nav, refresh, columns toggle, day filter, and both cutoff selects remain visible.

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

### 10.0 Status Bar Range-Days Display

`#range-days` is updated by `setView` (STEP 5) on **every** successful render and on every date-range change, regardless of view:

```typescript
function updateRangeDays(): void {
  const from = new Date(appState.dateRangeFrom);
  const to = new Date(appState.dateRangeTo);
  // inclusive calendar-day count; fractional days count as whole days
  const days = Math.ceil((to.getTime() - from.getTime()) / 86_400_000) + 1;
  rangeDaysEl.textContent = days === 1 ? "1 day" : `${days} days`;
}
```

The element is always visible in the status bar (like the view label and version badge) and is not toggled by `setView`.


### 10.1 Normal Data Views (chart / grid)

```
setView("chart")
  → disableAllControls()
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
  → enableAllControls()
```

### 10.2 Histogram Data Views

```
setView("histogram", { split: true })
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → renderSplitHistogramView(updateWaiting)
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
  → enableAllControls()
```

### 10.3 Refresh Flow

```
refreshBtn click → setView(appState.activeView, { refresh: true })
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → pushState({ view: activeView, isSplit: false })     ← pre-refresh snapshot (for error recovery)
  → renderRefreshView(updateWaiting)
      → updateWaiting("Querying Deye Cloud…")
      → POST /api/refresh
      → updateWaiting("Fetching latest dates…")
      → GET /api/dates → update appState.minAvailableDate, appState.maxAvailableDate
      → return { ok: true }
  → refresh succeeded — fall through to normal render:
  → renderRawDataChartView(updateWaiting)
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("raw-data-chart")
  → push URL history
  → enableAllControls()

Refresh failure path:
  → renderRefreshView throws Error
  → catch Error
  → pushState({ error: true, view, errorMessage })
  → show error-view
  → User clicks Close → history.back() → pops error → pops pre-refresh → popstate restores view
```

### 10.4 Columns Flow

```
columnsToggleBtn click (open) → setView(appState.activeView, { columns: true })
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → renderColumnsView(updateWaiting)
      → updateWaiting("Loading column definitions…")
      → appState.columnMetadata populated by init (background) —
        lazy-fetched from /api/columns if still empty
      → render checkboxes into columnsViewPanel
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("columns")
  → enableOnlyControls(["columnsToggle"])
  → pushState({ view, isSplit: false, columns: true }) with current URL unchanged

Browser back from columns panel → pops columns entry → popstate on previous data-view entry
  → setView(previous view, { replace: true }) — restores data view (fixes #47)

User clicks columnsToggleBtn (close/"Load Data") → setView(appState.activeView)
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → renderRawDataChartView(updateWaiting)  // with appState.selectedColumnNames
  → hidePanel("waiting")
  → showPanel("raw-data-chart")
  → push URL history
  → enableAllControls()
```

#### 10.5 Stats View Data Flow

```
statsBtn click → setView("stats")
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → renderStatsView(updateWaiting)
      → updateWaiting("Fetching statistics…")
      → GET /api/stats?from=X&to=Y&columns=...&dayFilter=X&highCutoff=N&lowCutoff=M
      → appState.statsResult = response
      → updateWaiting("Building stat cards…")
      → clear #stats-view, build one stat card per entry in response.stats (§16)
      → return { ok: true }
  → setView detects response.stats.length === 0 → info-view (transient)
  → otherwise: waitingView.hide()
  → showPanel("stats")            ← #stats-view
  → hide #summary-cards           ← stats cards ARE the content
  → push URL history (?view=stats[&dayFilter][&highCutoff][&lowCutoff])
  → enableAllControls()
  → updateRangeDays()

cutoff/dayFilter change while in stats view → setView("stats")
  → same flow with the new parameter values (URL carries them)
```

### 10.6 Empty Data Flow (Info View)

```
setView("chart")
  → disableAllControls()
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
  → enableAllControls()
  → NO history push (transient)

User clicks Refresh from info-view:
  → setView("chart", { refresh: true })
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → pushState({ view: "chart" })                        ← pre-refresh snapshot
  → renderRefreshView → POST /api/refresh → success
  → fall through to renderRawDataChartView → data now present
  → showPanel("raw-data-chart")
  → push URL history
  → enableAllControls()
```

---

## 11. API Endpoints Used

| Endpoint | Method | Used By | Timeout | Purpose |
| ---------- | -------- | --------- | --------- | --------- |
| `/api/columns` | GET | init(), renderColumnsView() | 10s | Column metadata (name + label); sourced from `column_metadata` database table via backend |
| `/api/dates` | GET | renderRefreshView(), init() | 10s | Min/max available data dates |
| `/api/data` | GET | renderRawDataChartView(), renderRawDataGridView() | 30s | Raw data rows (single day) |
| `/api/data-range` | GET | renderRawDataChartView(), renderRawDataGridView() | 30s | Raw data rows (range) |
| `/api/histogram` | GET | fetchHistogramData() (histogram renderers) | 30s | Time-binned average data |
| `/api/stats` | GET | renderStatsView() | 30s | Per-column statistics (mean, max/min + first occurrence, high/low avg daily durations) |
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
  → enableAllControls() — user can interact with all controls
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
| stats | any | "No statistics available for the selected date range. Click **Refresh** to sync from the inverter, or select a different date range." |

### 14.3 Init Procedure — Immediate Waiting View

On initial page load the browser must show visual feedback **before** any async metadata is fetched. The init procedure follows this exact sequence:

```
Page loaded
  → document ready (module evaluated)
  → Parse URL parameters → appState (view, dates, binSize, dayFilter, split)
  → Synchronously: show waiting-view with text "Loading…"
  → Title bar is already rendered (in HTML) — always visible
  → Status bar is already rendered (in HTML) — always visible (empty state OK)
  → Immediately: call setView(view, { replace: true, split })
    → setView's step 2: waiting-view already visible → show() is idempotent
    → Normal render path (fetch data, draw chart/grid, etc.)
    → On success: waiting-view hidden, data view shown
    → On error: waiting-view hidden, error-view shown
  → Concurrent background fetches (fired, NOT awaited — do not block the initial render):
    ├─ GET /api/version → versionBadgeEl
    ├─ GET /api/columns → appState.columnMetadata (lazy re-fetched by the columns view if still empty)
    └─ GET /api/dates → min/max available dates, updateNavButtonStates()
```

**Key properties:**

- The waiting-view is shown **synchronously** (no `await`), before any `fetch()` calls. This ensures the user never sees a blank page.
- Title bar and status bar are **already in the HTML** and rendered immediately by the browser — no JS needed.
- The initial `setView()` is called **immediately** — it does not wait for metadata. The three metadata fetches run in the background in parallel with the initial render.
- `setView()`'s step 2 (`waitingView.show()`) is called again after URL parameters are parsed. This call is **idempotent** — if the waiting-view is already visible, showing it again is a no-op.
- The waiting-view text during `init()` is the default "Loading…". During `setView()` rendering, it transitions to "Fetching data…", "Drawing chart…", etc.

**Error handling during init:**

- If any metadata fetch fails (version, columns, dates), the fetch is **silently skipped** (try/catch). The app continues to `setView()` with available data.
- If the final `setView()` call fails (data fetch error), the normal error-view path is followed.

#### 14.3.1 Init Flow Summary

| Phase | Action | Waiting View? | Async? |
| ------- | -------- | --------------- | -------- |
| 1 | Parse URL parameters | No | Sync |
| 2 | Show waiting-view ("Loading…") | **Yes** | Sync |
| 3 | Call `setView(view, opts)` — initial render starts immediately | Yes (idempotent show) | Async |
| 4a | Load `/api/version` (background, non-blocking, in parallel with render) | — | Async |
| 4b | Load `/api/columns` (background, non-blocking, in parallel with render) | — | Async |
| 4c | Load `/api/dates` (background, non-blocking, in parallel with render) | — | Async |
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
  → call setView(view, { replace: true, split })  ← §14.3 step 3 (immediately)
  → load /api/version, /api/columns, /api/dates in background  ← §14.3 step 4 (non-blocking)
      → setView step 2: waiting-view.show() (idempotent)
      → fetch data → 0 rows
      → infoView.show(noDataMessage)
      → showPanel("info")
      → enableAllControls()
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
  → call setView(urlState.view, { replace: true, split: urlState.isSplit })  ← §14.3 step 3 (immediately)
      → Normal render flow (see setView() lifecycle in §10.1–10.3)
      → waiting-view.text updates: "Fetching data…" → "Drawing chart…"
      → Data renders using appState.selectedColumnNames (from localStorage)
  → background metadata fetches (non-blocking, in parallel with the render):
    ├─ /api/version → versionBadgeEl
    ├─ /api/columns → appState.columnMetadata
    └─ /api/dates → min/max available dates, updateNavButtonStates()
      → If column metadata is still not loaded when the user opens the columns panel,
        renderColumnsView() fetches it lazily
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
| **Summary Cards Bar** (`#summary-cards`) | Per-metric max (or max average) value + timestamp | Renderers (`renderRawDataChartView`, `renderRawDataGridView`, `renderHistogramChartView`/`renderSplitHistogramView`, `renderHistogramGridView`) |
| **Chart / Grid Area** | The primary visualisation — Chart.js chart or AG Grid data table | Renderers |

**Order invariant:** Summary cards are **always** rendered above the chart/grid area. The DOM order never changes.

### 15.2 Summary Cards

Summary cards are rendered inside the `#summary-cards` container. They display aggregate information about the current dataset. The specific cards shown depend on the view mode:

| View | Cards Shown |
|------|-------------|
| `chart` / `grid` | One card per numeric column: `Max {label}` + maximum value (with unit) + timestamp of the max reading |
| `histogram` / `histogram-grid` | One card per metric: `Max Average {label}` + maximum average value (with unit) + timestamp |

Row/bin counts are shown in the status bar (`#row-count`), not in the summary cards. All numeric columns get a card (no cap).

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
- **Medium viewports (901–1200px):** Cards display at full size; only header padding tightens.
- **Narrow viewports (601–900px):** Cards shrink proportionally — reduced padding, smaller font sizes, tighter spacing. `--card-scale: 0.85`. Cards arrange in **3 columns**.
- **Small viewports (401–600px):** Cards reach a further reduced scale (`--card-scale: 0.7`). Cards arrange in **2 columns**.
- **Very small viewports (≤ 400px):** Cards reach minimum scale (`--card-scale: 0.6`). Auto-fit arrangement (effectively single column at typical widths).

The column-count and scale transitions are triggered by CSS media queries at `900px`, `600px`, and `400px` (see §15.4).

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
  → updateButtonLabels(view, split)
  → update #view-label
  → buildUrlString() → pushState
  → enableAllControls()
  → updateNavButtonStates()
```

**Key contract for renderers regarding the display panel:**

| Rule | Detail |
| ------ | -------- |
| **Render cards into existing container** | Cards are rendered into `#summary-cards` which is a direct child of `#content-area` (sibling of all content panels). On each data render the container is **cleared and the card elements are recreated** with the current dataset. |
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

## 16. Stats View

The Stats view (`setView("stats")`) replaces the chart/grid area with a grid of **stat cards** — one per selected numeric column. All computation is done by the backend (`GET /api/stats`); the frontend only formats and renders the response. The summary-cards bar (`#summary-cards`) is **hidden** in this view — the stat cards *are* the view content.

```
┌──────────────────────────────────────────┐
│  #content-area (single scrollable pane)  │
│  ┌──────────────────────────────────────┐│
│  │ #stats-view                          ││
│  │ ┌────────────┐ ┌────────────┐ …      ││
│  │ │ Grid Power │ │ Battery SOC│ …      ││
│  │ │ Mean 123 W │ │ Mean 55 %  │        ││
│  │ │ Max 5.1 kW │ │ Max 100 %  │        ││
│  │ │  07-22 …   │ │  07-20 …   │        ││
│  │ │ Min -310 W │ │ Min 0 %    │        ││
│  │ │  07-20 …   │ │  07-21 …   │        ││
│  │ │ High 42m/d │ │ High 0m/d  │        ││
│  │ │ Low  6m/d  │ │ Low  12m/d │        ││
│  │ └────────────┘ └────────────┘        ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

### 16.1 Card Content

Each card (one per entry in the `/api/stats` response `stats` array, in request order) displays:

| Row | Content | Formatting |
| ----- | ------- | ---------- |
| **Header** | `label` (e.g. "Grid Power (W)") | Bold, card title |
| **Mean** | `mean` + unit | `Average 123.4 W` |
| **Max** | `max.value` + unit, with `max.timestamp` (first occurrence) on a second line (small, muted) | `Max 5.12 kW` / `2025-07-22 13:30` |
| **Min** | `min.value` + unit, with `min.timestamp` (first occurrence) on a second line (small, muted) | `Min -310 W` / `2025-07-20 01:05` |
| **High avg duration** | `high.avgDailyMinutes` per day + threshold + cutoff | `High 42.5 min/day` / `> 1.24 kW (95th pct)` |
| **Low avg duration** | `low.avgDailyMinutes` per day + threshold + cutoff | `Low 6 min/day` / `< -997.8 W (5th pct)` |

Formatting rules:

- Units come from the response (`unit`, `""` if none); number formatting reuses the existing value/unit helpers (`extractUnit()`-style spacing, up to 2 decimals, unit-aware magnitude where already applied to other views).
- Threshold rows are secondary/muted text and echo the *effective* cutoff used (from the response `high.cutoff` / `low.cutoff`), so the card always describes exactly what the backend computed — even after a popstate restore with URL-supplied cutoffs.
- The card grid is recreated from scratch on every render (same contract as `#summary-cards`: clear container, rebuild elements).

### 16.2 Card Tooltips

Every card and every stat row carries a **tooltip explaining its content** (custom CSS tooltips — `data-tooltip` attribute rendered via `::after`, no JS library; tooltip text is truncated with ellipsis only where it exceeds the card width). Tooltip texts:

| Element | Tooltip text |
| ------- | ------------ |
| Card (header) | `Statistics for {label} over {from} to {to}{, weekdays only: {Day}} — N samples` |
| Mean row | `Arithmetic mean of all N samples in the selected date range.` |
| Max row | `Maximum value observed; shown with the date-time of its first occurrence.` |
| Min row | `Minimum value observed; shown with the date-time of its first occurrence.` |
| High row | `Average time per day the value was above the high threshold (mean + z·σ). Threshold: {value} {unit} at the {cutoff}th percentile. Days with samples but no high readings count as 0.` |
| Low row | `Average time per day the value was below the low threshold (mean − z·σ). Threshold: {value} {unit} at the {cutoff}th percentile. Days with samples but no low readings count as 0.` |

Placeholders are filled from the response data and current date range at render time. Tooltips must also be keyboard-accessible (rows are focusable, `:focus-visible` shows the same tooltip as hover).

### 16.3 Controls Interaction

| Control | Effect in stats view |
| -------- | -------------------- |
| Date inputs / prev / next / Today | Re-fetch stats for the new range; `#range-days` updates |
| Day filter | Restricts *all* statistics (mean, max, min, durations) to that weekday (backend-side) |
| High cutoff | Changes the high threshold percentile → backend re-computes `high` |
| Low cutoff | Changes the low threshold percentile → backend re-computes `low` |
| Columns (☰ Select) | Cards are rendered for the selected numeric columns only; non-numeric columns never produce a card |
| Refresh | Re-syncs data, then re-fetches stats |

### 16.4 Responsive Behavior

The stats card grid follows the same CSS grid approach as the summary cards (auto-fit columns, `--card-scale` breakpoints at 1200/900/600/400 px — see §15.3), with one difference: stat cards are taller (multi-row content), so at narrow viewports the grid naturally collapses to fewer columns and the content area scrolls. Cards keep equal heights within a row (`align-items: stretch`).

### 16.5 Renderer

`renderStatsView(updateWaiting)` (new module `stats-view.ts` or added to an existing view module) owns:

- Building the card DOM (one element tree per stat object)
- Populating tooltip attributes (§16.2)
- No panel visibility, button state, or history manipulation (setView contract, §6.3)

---

## 17. Change Management

This section tracks changes to the design document itself. Every modification to this document must be recorded below.

| Version | Date | Section Changed | Description |
|---------|------|----------------|-------------|
| 3.0 | 2026-08-26 | §1–§16, new | New Stats view — per-column stat cards (mean, max/min + first occurrence, high/low average daily durations) computed by new backend `GET /api/stats`; new `#stats-btn`, `#high-cutoff-select`, `#low-cutoff-select` controls; day filter now shared with stats view; status bar always shows selected-range day count (`#range-days`); CSS tooltips on all stat cards; new `stats` view mode in setView/URL state |
