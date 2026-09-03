# Frontend Design Document — Deye Logger Viewer

> **Status:** v8.0
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
│  │ • stats-view (stat cards / stats table) │ │
│  └────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

### 1.1 Source Files

| File | Responsibility |
| ------ | ---------------- |
| `dom-refs.ts` | DOM element references (isolated to break circular dependencies) |
| `shared.ts` | Global state object, URL parsing, utility helpers, shared chart palette (`CHART_PALETTE`), stats API types, re-exports DOM refs |
| `app.ts` | Entry point, `setView()`, button handlers, init, popstate |
| `chart.ts` | Chart.js line chart rendering, summary cards |
| `data-grid.ts` | AG Grid rendering (raw data + histogram grid) |
| `histogram-chart.ts` | Histogram per-column bar charts, data fetching |
| `stats-view.ts` | Stats view renderer — stat cards (§16.1) and stats-grid table (§16.6), CSS tooltips (§16.2) |
| `navigation.ts` | Date navigation (prev/next/today/date-picker) |
| `columns.ts` | Column selection panel, checkbox rendering |
| `index.html` | DOM skeleton |
| `style.css` | All styling (stat cards, stats grid table, CSS tooltips) |

Source files are bundled by **esbuild** (`npm run build` → `public/app.js`, ESM, single entry `src/app.ts`); the served `app.js` is a build artifact and is gitignored. Browser tests live in `test/` (Selenium + Firefox; `test_stats_view.py` covers the Stats view, design §16).

---

## 2. Persistent Always-Visible Objects

These objects are **always rendered and visible** regardless of the current view. They are never hidden by `setView`.

### 2.1 Title Bar (`<div class="header">`)

The title bar consists of **two rows**, each of which **wraps into additional lines** automatically when horizontal space runs out (CSS `flex-wrap: wrap`). The title bar grows vertically as needed to accommodate wrapped lines, pushing the rest of the page content down. This is different from a fixed-height title bar — the title bar height is **dynamic**.

1. **Title row (`.header-top`)** — the app title `<h1>` on the left, and the three **major-view buttons** (`📈 Series`, `📊 Histogram`, `📈 Stats`) on the **top right, on the same line as the logo** (v7.0 — #84). When the viewport is too narrow, the title row wraps: the button group drops below the title.
2. **Controls row (`.controls`)** — all other buttons and controls in a single horizontal area: date inputs + `‹`/`›`/`Today`, `↻ Refresh`, `☰ Select`, `📋 Grid`, `⬇ Download (CSV)`, histogram `Bin size`, `Day` day-of-week selector, stats `High`/`Low` cutoffs. When space runs out, the controls row wraps into additional rows.

**Compact buttons:** the title-bar buttons (`.btn-view`, `.btn-export`, `.columns-toggle`) use compact horizontal padding (`8px 10px`) to save width; button labels are short (`Series`, `Histogram`, `Stats`, `Grid`, `Select`, `Back`) with tooltips providing the full description.

**Button groups (v5.0 — fixes #62):** the title-bar buttons are organized into three clearly-segmented groups:

1. **Major views (blue)** — `Series` (line chart; the name references *Time Series*, replacing the too-general "Chart"), `Histogram`, `Stats`. Placed in a `.major-view-buttons` container on the **top right of the title row**, same line as the logo (v7.0 — #84). Always visible on the three major views; the **active** view's button is **disabled (grey)** (see §2.3) and the **other two** are **blue** and clickable to switch major views. These buttons are **hidden** in all grid views and in the Select (columns) view.
2. **Utilities (grey, always visible)** — date inputs + `Today` + `‹`/`›`, `↻ Refresh`, `Select`, `Grid`. Exception: the `Grid` button becomes **blue (`.active`)** while inside a grid view, when it reads `Back` (v5.1 — #76).
3. **Contextual controls** — `Bin size` (histogram view only), `Day` day-of-week selector, `High`/`Low` cutoffs (stats views), `⬇ Download (CSV)` (grid views only).

**Grid utility button:** `#view-toggle` is no longer a major-view toggle. It **opens the data grid for the data of the currently-selected view** (chart → grid, histogram → histogram-grid, stats → stats-grid). Inside a grid view it reads **`Back`**, is styled **blue (`.active`)** to emphasize the way back (v5.1 — #76, mirroring `#columns-toggle` in the Select view), and **automatically returns to the view that opened the grid**. Grid views show no major-view switching buttons — they only go back. `Day` + `Today`/`‹`/`›` and `⬇ Download (CSV)` remain available on the grids.

**Button ordering in wrapped rows:** Within each row, buttons are laid out left-to-right in the order listed below. When a row fills, remaining buttons flow to the next line. This means the bin-size control may appear on a second line of the controls row when the viewport is narrow, and the major-view buttons may wrap below the title on the title row.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ☀️ Deye Logger Viewer                    │ 📈 Series │ 📊 Histogram │ 📈 Stats │
│  [date] │ [date] │ ‹ › Today │ ↻ │ ☰ Select │ 📋 Grid │
│  ⬇ Download │ Bin: 15 ▼ │ Day: All ▼ │ High: 95% ▼ │ Low: 5% ▼ │
└──────────────────────────────────────────────────────────────────────────┘
```

(Contextual rows show only the controls relevant to the active view — see the table below and §9.3.)

| Element | ID | Purpose |
| --------- | ----- | --------- |
| `<h1>` | — | App title: "☀️ Deye Logger Viewer" |
| Date inputs | `#date-from`, `#date-to` | Date range selectors |
| Nav buttons | `#prev-day`, `#next-day`, `#today-btn` | Shift dates by ±1 day or go to today |
| Refresh button | `#refresh-btn` | Trigger backend data refresh |
| Series button | `#chart-btn` | Major-view button: shows the line (time-series) chart. Active (disabled grey) in chart/grid views, blue in the other major views, hidden in grid/Select views |
| Histogram button | `#histogram-btn` | Major-view button: shows the binned-average histogram. Active (disabled grey) in histogram/histogram-grid views, blue in the other major views, hidden in grid/Select views |
| Stats button | `#stats-btn` | Major-view button: shows per-column statistics. Active (disabled grey) in stats/stats-grid views, blue in the other major views, hidden in grid/Select views. All three major-view buttons sit in the `.major-view-buttons` container on the top right of the title row (§2.1) |
| Grid button (utility) | `#view-toggle` | `📋 Grid` — opens the data grid for the currently-selected view (chart→grid, histogram→histogram-grid, stats→stats-grid). In grid views reads **`Back`** (blue, `.active`) and returns automatically to the view that opened the grid |
| Columns button (utility) | `#columns-toggle` | `☰ Select` — opens the column selection panel. While the panel is open reads **`Back`**; closing returns to the view that opened it |
| CSV export | `#export-btn` | `⬇ Download (CSV)` — export current grid as CSV (visible in grid views only) |
| Bin size | `#bin-size-select` | Histogram bin size dropdown: `5` / `10` / `15` / `30` / `60` (hidden in non-histogram modes) |
| Day filter | `#day-filter-select` | Day-of-week dropdown: `All` / `Sun` / `Mon` / `Tue` / `Wed` / `Thu` / `Fri` / `Sat`. Visible in histogram modes, the Stats view **and their grid views**; limits histogram bins or statistics calculations to that weekday |
| High cutoff | `#high-cutoff-select` | Stats high-threshold cutoff dropdown: `50` / `75` / `90` / `95` / `99` (default `95`); ordinary units: threshold = `max − (100−x)%` of the observed max–min range, %-unit columns: `x%` directly (backend design §2.7); visible only in the Stats views |
| Low cutoff | `#low-cutoff-select` | Stats low-threshold cutoff dropdown: `1` / `5` / `10` / `25` / `50` (default `5`); ordinary units: threshold = `min + x%` of the observed max–min range, %-unit columns: `x%` directly (backend design §2.7); visible only in the Stats views |

### 2.2 Status Bar (`<div class="status-bar">`)

| Element | ID | Purpose |
| --------- | ----- | --------- |
| Row count | `#row-count` | Shows "N rows", "N metrics", or "N bins" |
| View label | `#view-label` | Shows the current view name: Series / Data Grid / Histogram / Histogram Grid / Stats / Stats Grid |
| Refresh indicator | `#refresh-status` | Hidden by default. Shows **"↻ refreshing ..."** while a background database refresh is running; cleared when the refresh completes or fails (v8.0 — #89) |
| Range days | `#range-days` | Always visible. Shows the number of days in the selected date range as "N days" (or "1 day"). Count = number of calendar days from `from` to `to` inclusive; any fractional day (e.g. a partial first/last day of the range relative to available data) is **counted as a whole day** (`Math.ceil`). Updated whenever the date range changes, independent of the active view |
| Version badge | `#version-badge` | Shows "FE x.x.x / BE y.y.y" |

### 2.3 Button Active State Styling

Buttons are color-coded by group (v5.0 — fixes #62). The state is applied via `classList`/`disabled` updates in `updateButtonLabels()`:

| Button | ID | Appearance |
| --------- | ----- | --------- |
| `📈 Series` / `📊 Histogram` / `📈 Stats` (major views) | `#chart-btn` / `#histogram-btn` / `#stats-btn` | **Blue** when the view is *not* the current one (clickable, switches major view). **Disabled (grey)** when it is the active view — the current view is already shown, so the button is not clickable. Hidden in all grid views and in the columns (Select) view. |
| Utilities (`Grid`, `Select`, date nav, refresh) | `#view-toggle`, `#columns-toggle`, `#prev-day`, `#next-day`, `#today-btn`, `#refresh-btn` | **Grey**, always enabled where visible — except the two overlay-return buttons below. |
| `☰ Select` / `Back` (columns) | `#columns-toggle` | **Blue (`.active`)** while the **columns panel is open** — clickable, it closes the panel. |
| `📋 Grid` / `Back` (grid) | `#view-toggle` | **Blue (`.active`)** while **inside a grid view** — clickable, it returns to the view that opened the grid (v5.1 — #76). |

The **active major-view button is disabled (grey)**, while the **other two major-view buttons stay blue** and switch the major view. Utility buttons remain grey, except `#columns-toggle` (Select view open) and `#view-toggle` (grid views), which turn blue (`.active`) as overlay-return buttons.

---

## 3. URL History Stateful Objects

These objects define the **page state** and must be pushed to URL history so that a user can bookmark a page, use browser back/forward, or reload to recreate the exact same state.

### 3.1 URL Query Parameters

| Parameter | Values | Source | Used By |
| ----------- | -------- | -------- | --------- |
| `view` | `chart`, `grid`, `histogram`, `histogram-grid`, `stats`, `stats-grid` | `setView()` | `getUrlState()`, `setView()` |
| `date` | ISO date string (YYYY-MM-DD) | Date inputs, nav buttons | `getUrlState()` (single day) |
| `from` | ISO date string | Date inputs, nav buttons | `getUrlState()` (range start) |
| `to` | ISO date string | Date inputs, nav buttons | `getUrlState()` (range end) |
| `binSize` | `5`, `10`, `15`, `30`, `60` | `#bin-size-select` | `getUrlState()`, histogram fetch |
| `dayFilter` | `all`, `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat` | `#day-filter-select` | `getUrlState()`, histogram fetch, stats fetch |
| `highCutoff` | `50`, `75`, `90`, `95`, `99` | `#high-cutoff-select` | `getUrlState()`, stats fetch |
| `lowCutoff` | `1`, `5`, `10`, `25`, `50` | `#low-cutoff-select` | `getUrlState()`, stats fetch |

**Serialization rules** (`buildUrlString()`):

- Single day: `?view=chart&date=2025-07-20`
- Range: `?view=chart&from=2025-07-18&to=2025-07-20`
- Histogram with custom bin: `?view=histogram&date=2025-07-20&binSize=30`
- Histogram with day filter: `?view=histogram&date=2025-07-20&dayFilter=mon`
- Stats view: `?view=stats&date=2025-07-20&highCutoff=90&lowCutoff=10&dayFilter=sun`
- Stats grid variant: `?view=stats-grid&date=2025-07-20` (same params, table layout instead of cards)
- Default `binSize=15` is omitted from URL
- Default `dayFilter=all` is omitted from URL
- Default `highCutoff=95` and `lowCutoff=5` are omitted from URL

### 3.2 History State (pushState payload)

| Property | Type | Purpose |
| ---------- | ------ | --------- |
| `view` | string | Current view mode |
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
| Grid button click (utility) | Yes (on success) | Opens the grid for the current view; in a grid view the button reads `Back` and auto-returns to the view that opened the grid |
| `histogramBtn` click | Yes (on success) | Switches major view to histogram (major-view buttons are hidden in grid and Select views, so no switching happens from there) |
| Date nav (prev/next/today/picker) | Yes (on success) | Date change triggers full re-render |
| `binSizeSelect` change | Yes (on success) | Re-renders current view |
| `dayFilterSelect` change | Yes (on success) | Re-renders current view (histogram or stats) |
| `highCutoffSelect` / `lowCutoffSelect` change | Yes (on success) | Re-renders stats view with new cutoffs |
| Stats button click | Yes (on success) | Enters `stats` view (the button is disabled/hidden in stats views — returns happen via the grid `Back` button) |
| `popstate` (browser back/forward) | No (`replace`) | Restores view without double-push |
| `popstate` → error state | No (re-shows error) | Detects `{ error: true }` marker |
| `popstate` → columns state | No (`replace`) | Detects `{ columns: true }` marker — re-shows columns panel |
| Initial load | Yes (on success) | Sets initial history entry |
| Refresh success (background) | Yes (via the re-render) | Background refresh completes → `setView(activeView)` re-renders the current view (dates unchanged) (v8.0 — #89) |
| Refresh failure (background) | Yes (with `error` marker) | Single error entry pushed; `Close` → `history.back()` → popstate re-renders the current view (v8.0 — #89) |
| Open columns panel | **Yes** | Same URL, payload `{ columns: true }` — browser back returns to previous data view |
| Close columns panel (`Back`) | Yes (on success) | Full data re-fetch with new columns |
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
| **Default columns** | Button in columns-view | Restores default column set. |
| **Refresh (background)** | `#refresh-btn` | Runs `POST /api/refresh` + `GET /api/dates` asynchronously — the current view stays visible and interactive with a **"refreshing ..."** status-bar indicator; on completion the current view is re-rendered via `setView(activeView)` (v8.0 — #89) |

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
| **Histogram view** | `#histogram-view` | `setView("histogram")` — one bar chart per selected column (§9.2) | Yes |
| **Histogram grid view** | `#histogram-grid-view` | `setView("histogram-grid")` | Yes |
| **Stats view** | `#stats-view` | `setView("stats")` | Yes |
| **Stats grid view** | `#stats-view` (same panel, table layout) | `setView("stats-grid")` | Yes |

**Invariant:** At any moment, exactly one of `{ waiting, error, info, columns, chart, grid, histogram, histogram-grid, stats }` is visible (`stats-grid` reuses the `stats` panel). `setView` enforces this.

---

## 6. setView Controller — Unified Lifecycle

### 6.1 Signature

```typescript
interface SetViewOptions {
  replace?: boolean;      // use replaceState instead of pushState (default: false)
  columns?: boolean;      // show columns selection panel (pushes history entry with columns marker)
}
// NOTE (v8.0 — #89): the `refresh` option is removed — refresh is a background
// operation (runBackgroundRefresh(), §10.3) that no longer routes through setView.

function setView(
  view: "chart" | "grid" | "histogram" | "histogram-grid" | "stats" | "stats-grid",
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
  │     ├─ view === "histogram"
  │     │     → renderHistogramView(updateWaiting)
  │     │       updateWaiting("Fetching histogram data…")
  │     │       GET /api/histogram → histogramLastApiResult (via fetchHistogramData())
  │     │       updateWaiting("Drawing histograms…")
  │     │       draw one bar chart per selected column → histogramChartInstances
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
  │     └─ view === "stats" / "stats-grid"
  │             → renderStatsView(updateWaiting, view === "stats-grid")
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
  │     │     → pushState({ view, columns: true }) with current URL unchanged
  │     │       (replaceState when called with replace: true, e.g. from popstate)
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
  │     │     → updateButtonLabels(view)
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
  └─ STEP 5: updateButtonLabels(view)
        chartBtn/histogramBtn/statsBtn.visible  ← major views only — hidden in grid views and the columns (Select) view
        chartBtn/histogramBtn/statsBtn.disabled ← the ACTIVE major view is disabled (grey); the other two are blue and enabled (see §2.3)
        viewToggleBtn.label             ← `Grid` on major views / `Back` in grid views
        columnsToggleBtn.label          ← `Select` (closed) / `Back` (columns view)
        exportCsvBtn.visible          ← grid views only
        binSizeSelect.visible           ← histogram modes only
        dayFilterSelect.visible          ← histogram modes, stats views and their grid views
        highCutoffSelect.visible        ← stats views only
        lowCutoffSelect.visible         ← stats views only
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
| `init()` → `setView(urlState.view, { replace: true })` | Page load | — | Initial render |
| `viewToggleBtn` click (Grid utility) | Grid button | — | Major view: `setView(<grid variant>)` — chart→grid, histogram→histogram-grid, stats→stats-grid. Grid view: button reads `Back` → `setView(<view that opened the grid>)` — the opener is derived from the grid variant (grid→chart, histogram-grid→histogram, stats-grid→stats, preserving the stats cards↔table state) |
| `histogramBtn` click | Histogram major-view button | — | From chart or grid → `setView("histogram")`. Disabled (grey) in histogram/histogram-grid views; hidden in grid and Select views |
| Date nav buttons/pickers | Date change | — | `setView(appState.activeView)` — re-render with new dates |
| `popstate` | Browser back/forward | `{ replace: true }` | Restores from URL state |
| `popstate` → error | Error state detected | — | Shows error-view directly (no render) |
| `popstate` → columns | `{ columns: true }` marker detected | `{ columns: true, replace: true }` | Re-shows columns panel (no data fetch) |
| `binSizeSelect` change | Bin size dropdown | — | Re-renders current histogram view |
| `dayFilterSelect` change | Day filter dropdown | — | Re-renders current histogram or stats view |
| `highCutoffSelect` / `lowCutoffSelect` change | Cutoff dropdowns (stats views) | — | `setView(current)` (stats or stats-grid) — re-renders with new thresholds |
| `statsBtn` click | Stats major-view button | — | From chart or histogram → `setView("stats")`. Disabled (grey) in stats views; hidden in grid and Select views |
| `refreshBtn` click | Data refresh | — | Not via `setView` — triggers `runBackgroundRefresh()` (§10.3): background `POST /api/refresh` with a "refreshing ..." status-bar indicator while the view stays active; re-renders the current view on completion (v8.0 — #89) |
| `columnsToggleBtn` click (open) | Open columns panel | `{ columns: true }` | Pushes history entry with `columns: true` marker (URL unchanged) |
| `columnsToggleBtn` click (close) | Close columns panel (label `Back`) | — | `setView(appState.activeView)` — full re-fetch, returns to the view that opened the panel |
| `errorViewCloseBtn` click | Dismiss error | — | `history.back()` — popstate recreates previous |
| `exportCsvBtn` click | CSV export | — | Stateless — `gridApi.exportDataAsCsv()` |

---

## 7. Error View — Modal with History Integration

### 7.1 Behavior

#### 7.1.1 Refresh Failure (background refresh — v8.0, #89)

```
refreshBtn click → runBackgroundRefresh()
  → current view stays visible and interactive; "refreshing ..." in status bar
  → POST /api/refresh → TIMEOUT or 500
  → catch Error
  → pushState({ error: true, view, errorMessage: "Server error 500" }) ← single error entry
  → show error-view (modal overlay)
  → User clicks Close
  → history.back()                                       ← pops error entry
  → popstate fires → setView(current view, { replace: true }) ← re-renders view
```

**Key invariant (v8.0):** The URL does not change while a refresh runs, so only the error entry is pushed on failure. A single `history.back()` from the error-view returns to the current view entry, which popstate re-renders.

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
{ view: "chart" }

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
  setView(urlState.view, { replace: true });
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
| `appState.activeView` | ViewMode | URL-stateful | Current data view: chart, grid, histogram, histogram-grid, stats, stats-grid |
| `appState.refreshing` | `boolean` | Transient (operation) | True while a background database refresh is in flight; `#refresh-btn` is disabled and "refreshing ..." is shown in the status bar (v8.0 — #89) |

### 8.2 Histogram Module Variables (`histogram-chart.ts`)

| Variable | Type | Persistence | Description |
| ---------- | ------ | ------------- | ------------- |
| `histogramChartInstances` | `Chart[]` | Transient (render) | Array of Chart.js instances — one bar chart per selected column |
| `histogramLastApiResult` | `HistogramResponse \| null` | Transient (cache) | Cached histogram API response |
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
| `histogramView` | `#histogram-view` | Histogram container — one bar chart per selected column |
| `histogramGridView` | `#histogram-grid-view` | Histogram grid table container |
| `histogramScroll` | `#histogram-scroll` | Container for the per-column charts (no inner scroll — single scroll pane on `#content-area`) |
| `statsViewPanel` | `#stats-view` | Stats view container — stat cards (stats) or stats table (stats-grid, `.stats-grid-mode`) (direct child of `#content-area`) |
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
| `binSizeSelect` | `#bin-size-select` | Histogram bin size dropdown |
| `dayFilterSelect` | `#day-filter-select` | Day-of-week filter dropdown (histogram modes and stats view) |
| `histogramControls` | `#histogram-controls` | Histogram-only control group (bin size) |
| `dayFilterGroup` | `#day-filter-group` | Day-filter control group (visible in histogram modes **and** stats views) |
| `statsCutoffs` | `#stats-cutoffs` | Stats high/low cutoff group (stats views only) |
| `highCutoffSelect` | `#high-cutoff-select` | Stats high-threshold cutoff dropdown (stats view only) |
| `lowCutoffSelect` | `#low-cutoff-select` | Stats low-threshold cutoff dropdown (stats view only) |
| `statsBtn` | `#stats-btn` | Stats view toggle button |
| `rowCountEl` | `#row-count` | Row/metric count display |
| `viewLabelEl` | `#view-label` | Current view name display |
| `rangeDaysEl` | `#range-days` | Selected date range day count display (always visible) |
| `versionBadgeEl` | `#version-badge` | Version string display |

---

## 9. View Modes and Transitions

### 9.1 View Transitions

The three major views — **Series** (`chart`), **Histogram**, **Stats** — are cross-switched by the three blue major-view buttons; the button of the active view is disabled (grey). Each major view opens its **corresponding grid view** with the grey `Grid` utility button; `Back` inside the grid (blue, `.active`) **automatically returns to the view that opened it**. The `Select` button opens the **columns view** from any data view; `Back` returns to the view that opened it. **No major-view buttons are shown in grid views or in the columns view** — they only go back.

```
Major views — the blue buttons switch between them (active one disabled, grey):

        Series ──────────────▶ Histogram ─────────────▶ Stats
           ▲  ▲                     ▲  ▲                   ▲  ▲
           │  └──── Series ─────────┘  └──── Series ────────┘  │
           └───────── Histogram ───────────────────────────────┘

Overlay navigation — grey utility buttons; the blue `Back` (`.active`) returns to the view that opened it:

        Series ──Grid──▶ Grid (grid) ──────────Back──▶ Series
        Histogram ─Grid─▶ Histogram Grid ──────Back──▶ Histogram
        Stats ──Grid──▶ Stats Grid ────────────Back──▶ Stats
        any data view ─Select─▶ Columns view ───Back──▶ the view that opened it
```

### 9.2 Histogram View

The histogram view (`setView("histogram")`) renders **one bar chart per selected column** — each chart shows that column's binned averages with the per-bin min/max range band behind the average bar (§10.2.1).

The previous combined view (all columns in one chart) and the Split/Combine sub-mode (`?split=1`, `#split-btn`) were **removed** in v7.0 (#82): the per-column layout is the only histogram view, and no split state exists in the URL or history.

### 9.3 Button Specification Table

Every button in the title bar is documented with its text, visibility, toggle/action behavior, state variables, and statefulness.

| Button | Variable | Text / Label | Visibility | Type | Reads State | Writes State | Stateful? |
| -------- | ---------- | ------------- | ------------ | ------ | ------------- | ------------- | ----------- |
| Prev Day | `prevDayBtn` | `‹` | Always | Action (shift -1 day) | `appState.dateRangeFrom`, `appState.dateRangeTo`, `appState.minAvailableDate` | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`/`from`/`to`) |
| Next Day | `nextDayBtn` | `›` | Always | Action (shift +1 day) | `appState.dateRangeFrom`, `appState.dateRangeTo`, `appState.maxAvailableDate` | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`/`from`/`to`) |
| Today | `todayBtn` | `Today` | Always | Action (set to today) | — | `appState.dateRangeFrom`, `appState.dateRangeTo` (URL) | URL-stateful (via `date`) |
| Refresh | `refreshBtn` | `↻ Refresh` | Always | Action (debounced) | — | Triggers `runBackgroundRefresh()` — background `POST /api/refresh` with "refreshing ..." status-bar indicator; the view stays active; the current view re-renders on completion (v8.0 — #89) | URL-stateful (error entry only on failure) |
| Series (major view) | `chartBtn` | `📈 Series` | Major views only — hidden in grid and Select views; disabled (grey) when active | Action (switch to Series) | — | `appState.activeView` (URL) | URL-stateful (via `view`) |
| Histogram (major view) | `histogramToggleBtn` | `📊 Histogram` | Major views only — hidden in grid and Select views; disabled (grey) when active | Action (switch to Histogram) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| Stats (major view) | `statsBtn` | `📈 Stats` | Major views only — hidden in grid and Select views; disabled (grey) when active | Action (switch to Stats) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| Grid (utility) | `viewToggleBtn` | `📋 Grid` (major views, grey) / `Back` (grid views, blue `.active`) | Always | Action (open grid for current view / auto-return) | `appState.activeView` | `appState.activeView` (URL) | URL-stateful (via `view`) |
| Columns (utility) | `columnsToggleBtn` | `☰ Select` (closed) / `Back` (open) | Always | Toggle (open↔close columns-view) | — | Controls columns-view visibility (opening pushes history entry) | Stateless (columns persist to localStorage) |
| CSV Export | `exportCsvBtn` | `⬇ Download (CSV)` | Grid views only | Stateless action | `appState.rawDataGridApi` or `histogramGridApi` | — | Stateless action |
| Bin Size | `binSizeSelect` | `5` / `10` / `15` / `30` / `60` | Histogram mode (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?binSize=N` | URL-stateful (via `binSize`) |
| Day Filter | `dayFilterSelect` | `All` / `Sun` / `Mon` / `Tue` / `Wed` / `Thu` / `Fri` / `Sat` | Histogram mode **and** stats view (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?dayFilter=X` | URL-stateful (via `dayFilter`) |
| High Cutoff | `highCutoffSelect` | `50` / `75` / `90` / `95` / `99` (default `95`) | Stats view only (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?highCutoff=N` | URL-stateful (via `highCutoff`) |
| Low Cutoff | `lowCutoffSelect` | `1` / `5` / `10` / `25` / `50` (default `5`) | Stats view only (in title bar) | Stateless action (triggers re-render) | Current selection | URL `?lowCutoff=N` | URL-stateful (via `lowCutoff`) |


#### Major View Button States (`chartBtn` / `histogramToggleBtn` / `statsBtn`)

| `appState.activeView` | `📈 Series` | `📊 Histogram` | `📈 Stats` |
| ---------------------- | ------------- | --------------- | ----------- |
| `chart` / `grid` | Disabled (grey, active) | Blue — `setView("histogram")` | Blue — `setView("stats")` |
| `histogram` / `histogram-grid` | Blue — `setView("chart")` | Disabled (grey, active) | Blue — `setView("stats")` |
| `stats` / `stats-grid` | Blue — `setView("chart")` | Blue — `setView("histogram")` | Disabled (grey, active) |
| Grid views / Columns view | Hidden | Hidden | Hidden |

Titles: Series — "Show the time-series line chart"; Histogram — "Show binned average histogram"; Stats — "Show per-column statistics for the selected range".

In the stats views, the Stats button is disabled (grey) and the other two major buttons are blue. No major-view switching happens from grid views or the columns view — they return only via `Back`. Date nav, refresh, `Select`, the day filter (histogram/stats views) and the cutoff selects (stats views) remain visible; `⬇ Download (CSV)` is available on the grid views.

#### Grid Button Labels (`viewToggleBtn`)

| `appState.activeView` | Button Text | Button Title | Action |
| ---------------------- | ------------ | ------------- | -------- |
| `chart` | `📋 Grid` | "Show the chart data as a grid" | `setView("grid")` |
| `grid` | `Back` | "Return to the Series view" | `setView("chart")` |
| `histogram` | `📋 Grid` | "Show the histogram data as a grid" | `setView("histogram-grid")` |
| `histogram-grid` | `Back` | "Return to the Histogram view" | `setView("histogram")` |
| `stats` | `📋 Grid` | "Show the statistics as a grid (table)" | `setView("stats-grid")` |
| `stats-grid` | `Back` | "Return to the Stats view" | `setView("stats")` |

The grid views show **no** major-view-switching buttons — only `Back` (blue, `.active`), which automatically returns to the view that opened the grid. The Stats cards↔table sub-toggle is exactly `stats` ↔ `stats-grid` via `Grid` / `Back`.

#### Columns Button Labels (`columnsToggleBtn`)

| columns-view State | Button Text | Button Title | Action |
| ------------------- | ------------ | ------------- | -------- |
| Closed | `☰ Select` | "Select columns to display" | `setView(activeView, { columns: true })` |
| Open | `Back` | "Close the panel and return to the view that opened it" | `setView(appState.activeView)` |

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
setView("histogram")
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → renderHistogramView(updateWaiting)
      → updateWaiting("Fetching histogram data…")
      → GET /api/histogram?from=X&to=Y&columns=...&binMinutes=N&dayFilter=X
      → histogramLastApiResult = response
      → histogramMaxAverageValues = maxValues
      → updateWaiting("Drawing histograms…")
      → draw one bar chart per selected column → histogramChartInstances
      → return { ok: true }
  → hidePanel("waiting")
  → showPanel("histogram")
  → show summary-cards (add .visible class to #summary-cards)
  → push URL history
  → enableAllControls()
```

#### 10.2.1 Per-Bin Value Range Rendering

Each histogram dataset carries per-bin `min[]` and `max[]` arrays (parallel to the average `data[]`) from the backend. Each per-column chart renders the bin's value range as follows (v7.0 — #83):

- **Shaded range band (background):** a **full-width** translucent bar per bin, drawn as a Chart.js **floating bar** (`[min, max]`), spanning the whole category slot (`barPercentage: 1`, `categoryPercentage: 1`), in the dataset color at low opacity (≈20% fill, no border), behind the average bar (`order: 1`). Skipped for bins where `min === max` (zero spread) to avoid visual noise.
- **Average bar (foreground):** superimposed on top of the range band, **centred within it** at **~60% of the band's width** (`barPercentage: 0.6`, `categoryPercentage: 1`, `order: 0`).
- **Centre alignment:** both datasets use **`grouped: false`** — without it Chart.js lays the two bar datasets out **side-by-side** within the category slot (the range band ends up offset to one side of the average bar instead of behind it). With `grouped: false` both bars centre on the category; `barPercentage` alone then controls relative widths.
- **Tooltip:** the `label` callback appends the range, e.g. `Daily Energy (kWh): 10.5 (range 9.8–10.7)`; omitted when `min === max`. Range datasets are filtered out of the tooltip and the legend (the legend stays on the averages).
- Missing/absent `min`/`max` arrays are treated as not available (no range rendered) — the renderer degrades gracefully to averages only.

### 10.3 Refresh Flow (background — v8.0, #89)

Refresh no longer routes through `setView`. Clicking `↻ Refresh` starts
`runBackgroundRefresh()` while the current view stays visible and interactive —
the waiting view (spinner) is **not** used for refresh (it remains the loading
view for all data-fetching `setView()` paths):

```
refreshBtn click → runBackgroundRefresh()
  → guard: appState.refreshing === true → ignore (button is disabled while in flight)
  → appState.refreshing = true
  → disable #refresh-btn only — all other controls stay enabled
  → show "↻ refreshing ..." in the status bar (#refresh-status)
  → POST /api/refresh (120s timeout)
  → GET /api/dates → update appState.minAvailableDate, appState.maxAvailableDate
      (and #date-from/#date-to min/max bounds)
  → appState.refreshing = false
  → clear #refresh-status, re-enable #refresh-btn
  → setView(appState.activeView)  ← re-render current view so the new data is shown

Refresh failure path:
  → POST /api/refresh throws (timeout / HTTP error / non-zero exit code)
  → appState.refreshing = false
  → clear #refresh-status, re-enable #refresh-btn
  → pushState({ error: true, view, errorMessage })     ← single error entry
  → show error-view
  → User clicks Close → history.back() → popstate re-renders current view
```

**Invariants:**
- The screen stays active for the whole refresh: no waiting view, no control disabling beyond `#refresh-btn`.
- The URL does not change while the refresh runs; history is pushed only on completion (via the re-render) or on failure (the single error entry).
- The waiting view (spinner) is unchanged — still used by all data-loading `setView()` paths.

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
  → pushState({ view, columns: true }) with current URL unchanged

Browser back from columns panel → pops columns entry → popstate on previous data-view entry
  → setView(previous view, { replace: true }) — restores data view (fixes #47)

User clicks columnsToggleBtn (close, label `Back`) → setView(appState.activeView)
  // While the columns panel is open the major-view buttons (Series / Histogram / Stats)
  // are hidden; the panel returns only via `Back` to the view that opened it.
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
statsBtn click → setView("stats")          (viewToggle in stats → setView("stats-grid"))
  → disableAllControls()
  → showPanel("waiting") → waitingView.show()
  → renderStatsView(updateWaiting, asGrid)
      → updateWaiting("Fetching statistics…")
      → GET /api/stats?from=X&to=Y&columns=...&dayFilter=X&highCutoff=N&lowCutoff=M
      → appState.statsResult = response
      → updateWaiting("Building stat cards…" | "Building stats grid…")
      → clear #stats-view, build stat cards (§16.1) or stats table (§16.6);
        stats-grid toggles the .stats-grid-mode class on the panel
      → return { ok: true }
  → setView detects response.stats.length === 0 → info-view (transient)
  → otherwise: waitingView.hide()
  → showPanel("stats")            ← #stats-view (both variants)
  → hide #summary-cards           ← stat cards/table ARE the content
  → push URL history (?view=stats|stats-grid[&dayFilter][&highCutoff][&lowCutoff])
  → enableAllControls()
  → updateRangeDays()

cutoff/dayFilter change while in a stats view → setView(current stats view)
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

User clicks Refresh from info-view (background — v8.0, #89):
  → runBackgroundRefresh() — current screen stays as-is; "refreshing ..." in status bar
  → POST /api/refresh → success
  → GET /api/dates (update min/max bounds)
  → setView("chart") → renderRawDataChartView → data now present
  → showPanel("raw-data-chart")
  → push URL history
  → enableAllControls()
```

---

## 11. API Endpoints Used

| Endpoint | Method | Used By | Timeout | Purpose |
| ---------- | -------- | --------- | --------- | --------- |
| `/api/columns` | GET | init(), renderColumnsView() | 10s | Column metadata (name + label); sourced from `column_metadata` database table via backend |
| `/api/dates` | GET | runBackgroundRefresh(), init() | 10s | Min/max available data dates |
| `/api/data` | GET | renderRawDataChartView(), renderRawDataGridView() | 30s | Raw data rows (single day) |
| `/api/data-range` | GET | renderRawDataChartView(), renderRawDataGridView() | 30s | Raw data rows (range) |
| `/api/histogram` | GET | fetchHistogramData() (histogram renderers) | 30s | Time-binned average + per-bin min/max data |
| `/api/stats` | GET | renderStatsView() | 30s | Per-column statistics (mean, max/min + first occurrence, high/low avg daily durations) |
| `/api/refresh` | POST | runBackgroundRefresh() | 120s | Trigger inverter data sync (background, #89) |
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
  → Parse URL parameters → appState (view, dates, binSize, dayFilter)
  → Synchronously: show waiting-view with text "Loading…"
  → Title bar is already rendered (in HTML) — always visible
  → Status bar is already rendered (in HTML) — always visible (empty state OK)
  → Immediately: call setView(view, { replace: true })
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
  → call setView(view, { replace: true })  ← §14.3 step 3 (immediately)
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
  → call setView(urlState.view, { replace: true })  ← §14.3 step 3 (immediately)
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
| **Summary Cards Bar** (`#summary-cards`) | Per-metric max (or max average) value + timestamp | Renderers (`renderRawDataChartView`, `renderRawDataGridView`, `renderHistogramView`, `renderHistogramGridView`) |
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
  → updateButtonLabels(view)
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

### 15.6 Histogram View Display Panel

The histogram panel (`#histogram-view`) contains **one chart per selected column**. The bin-size control is in the **title bar** (not in the display panel), so it is always visible regardless of scroll position.

```
┌──────────────────────────────────────────┐
│  #content-area (single scrollable pane)  │
│  ┌──────────────────────────────────────┐│
│  │ Summary Cards Bar (#summary-cards)   ││
│  │ ┌──────┐ ┌──────┐ ┌──────┐ …        ││
│  ├──────────────────────────────────────┤│
│  │ #histogram-view                      ││
│  │  ┌───────────────────────────────┐   ││
│  │  │ #histogram-scroll            │   ││  ← no inner scroll
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

- Summary cards behave identically to other views.
- The bin-size control is in the **title bar** (`#bin-size-select`) — always visible regardless of scroll position.
- The chart area contains **multiple charts** (one per metric).
- There is **no inner scroll** on `#histogram-scroll`. The single scroll pane is `#content-area`, which contains both the summary cards and all charts. Users scroll the entire content area to view charts below the summary cards.
- Responsive behavior (scaling, vertical stacking, scroll) applies the same way as other views.

### 15.7 Grid Column Labels

Both the raw data grid and histogram grid display units in column header labels. The `extractUnit()` helper is used to extract the unit from column metadata, consistent with chart axis labels.

| Grid Type | Header Format | Example |
|-----------|---------------|---------|
| Raw data grid | `label (unit)` | `Grid Power (W)`, `Battery SOC (%)` |
| Histogram grid | `label (unit)` | `Grid Power (W)`, `Battery SOC (%)` |

If no unit is defined in the metadata, the label is shown without parentheses (e.g. `Time`). The `device_timestamp` column is always labeled "Time" without a unit.

### 15.8 Chart Axis Rules (Full-Day Axes)

Charts must not scale their axes to the available data only (v7.2 — #85):

- **Series x-axis (full-range time axis):** the x-axis **always spans the entire selected range** — single day: 00:00 to 24:00; multi-day: 00:00 of `from` to 24:00 of `to` — as a linear time axis with tick/grid marks at a fixed step: **5 min** (1 day), **30 min** (2–7 days), **60 min** (>7 days). The fixed step governs **tick placement only** — it is never used to bin or downsample the data; missing data is revealed by the absence of plotted points against the full axis extent, not by a shrunken axis. Tick label format: single day `HH:MM`; range `MM-DD HH:MM`.
- **Series data (raw points, no smoothing):** the series plots **every raw data row** — one point per row at its actual `device_timestamp`. There is **no binning, downsampling, or curve smoothing** — binning is a histogram-only concept (v7.4, #88; the v7.2 bucket flooring of the series data was a misinterpretation of #85). Line segments are straight between consecutive samples (`tension: 0`), so data peaks are preserved and visible. Tooltip titles resolve the timestamp from the hovered row's own `device_timestamp`.
- **Percentage y-axis (0–100%):** any y-axis whose unit is `%` (e.g. SOC) is **always drawn from 0 to 100** in both the series chart and the per-column histogram charts. Other units continue to auto-scale.
- **Histogram x-axis (full-day bins):** the `/api/histogram` response **always contains the full 00:00–24:00 bin grid** (1440/binMinutes bins; rows from multiple days are binned together by time-of-day) — empty bins carry `null` in `data`/`min`/`max` and render as gaps (no bar, no range band). The frontend does not pad; the backend owns the grid (backend design v4.1, §2.6).

---

## 16. Stats View

The Stats view (`setView("stats")`) replaces the chart/grid area with a grid of **stat cards** — one per selected numeric column. The `stats-grid` variant (`setView("stats-grid")`, §16.6) shows the same data as a table. All computation is done by the backend (`GET /api/stats`); the frontend only formats and renders the response. The summary-cards bar (`#summary-cards`) is **hidden** in these views — the stat cards/table *are* the view content.

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
| **High avg duration** | `high.avgDailyMinutes` per day + threshold | `High 42.5 mins/day` / `> 1.24 kW` (ordinary units) or `> 95%` (percentage-unit, e.g. SOC) |
| **Low avg duration** | `low.avgDailyMinutes` per day + threshold | `Low 6 mins/day` / `< -997.8 W` (ordinary units) or `< 5%` (percentage-unit, e.g. SOC) |

Duration labels use the abbreviation **`mins`** (minutes), never `min`, to keep them distinct from the `Min` (minimum value) row.

Formatting rules:

- Units come from the response (`unit`, `""` if none); number formatting reuses the existing value/unit helpers (`extractUnit()`-style spacing, up to 2 decimals, unit-aware magnitude where already applied to other views).
- Threshold rows are secondary/muted text and show the *effective* threshold used by the backend (from the response `high.threshold` / `low.threshold`): for ordinary units the observed-range-based value (e.g. `> 1.24 kW`), for percentage-unit columns the selected cutoff in percent (e.g. `> 95%` for SOC). The cutoff is **not** repeated in braces on the card (the earlier `(95%)` suffix is dropped), since it is already shown in the top bar where it is selected.
- The card grid is recreated from scratch on every render (same contract as `#summary-cards`: clear container, rebuild elements).

**Per-measurement accent color:** each stat card carries the same accent color its measurement uses in the line chart, so the grid is not monochrome (the summary cards pattern). The palette is a single shared 16-color array (`CHART_PALETTE`, moved from `chart.ts` into `shared.ts`; `chart.ts` imports it) and cycles in dataset order (`CHART_PALETTE[i % CHART_PALETTE.length]`). The accent is applied via a `--stat-accent` CSS variable on the card: it colors the card's 3px top border and the header text; all other card text keeps the neutral palette.

### 16.2 Card Tooltips

Every card and every stat row carries a **tooltip explaining its content** (custom CSS tooltips — `data-tooltip` attribute rendered via `::after`, no JS library; tooltip text is truncated with ellipsis only where it exceeds the card width). Tooltip texts:

| Element | Tooltip text |
| ------- | ------------ |
| Card (header) | `Statistics for {label} over {from} to {to}{, weekdays only: {Day}} — N samples` |
| Mean row | `Arithmetic mean of all N samples in the selected date range.` |
| Max row | `Maximum value observed; shown with the date-time of its first occurrence.` |
| Min row | `Minimum value observed; shown with the date-time of its first occurrence.` |
| High row | `Average time per day the value was above the high threshold ({method}). Threshold: {value} {unit}{threshold-desc}. Days with samples but no high readings count as 0.` |
| Low row | `Average time per day the value was below the low threshold ({method}). Threshold: {value} {unit}{threshold-desc}. Days with samples but no low readings count as 0.` |

`{method}` echoes the response `high.method` / `low.method` (backend design §2.7): `based on the observed max/min range` for ordinary units (`method === "range"`); `the selected {cutoff}% limit (percentage-unit column)` when `method === "cutoff"` (e.g. SOC — the 0–100% range is absolute, so the selected cutoff is used directly as a percent limit). `{threshold-desc}` is `top {100−cutoff}% of the observed range` on high rows and `bottom {cutoff}% of the observed range` on low rows when `method === "range"`, and empty for `cutoff` (the value already carries the `%` unit).

Placeholders are filled from the response data and current date range at render time. Tooltips must also be keyboard-accessible (rows are focusable, `:focus-visible` shows the same tooltip as hover).

### 16.3 Controls Interaction

| Control | Effect in stats view |
| -------- | -------------------- |
| Date inputs / prev / next / Today | Re-fetch stats for the new range; `#range-days` updates |
| Day filter | Restricts *all* statistics (mean, max, min, durations) to that weekday (backend-side) |
| High cutoff | Changes the high-threshold cutoff → backend re-computes `high` from the observed range |
| Low cutoff | Changes the low-threshold cutoff → backend re-computes `low` from the observed range |
| Columns (☰ Select) | Cards are rendered for the selected numeric columns only; non-numeric columns never produce a card |
| Refresh | Re-syncs data, then re-fetches stats |

### 16.4 Responsive Behavior

The stats card grid follows the same CSS grid approach as the summary cards (auto-fit columns, `--card-scale` breakpoints at 1200/900/600/400 px — see §15.3), with one difference: stat cards are taller (multi-row content), so at narrow viewports the grid naturally collapses to fewer columns and the content area scrolls. Cards keep equal heights within a row (`align-items: stretch`).

### 16.5 Renderer

`renderStatsView(updateWaiting)` (module `stats-view.ts`) owns:

- Building the card DOM (one element tree per stat object), including the `--stat-accent` variable from `CHART_PALETTE` (§16.1)
- Populating tooltip attributes (§16.2)
- No panel visibility, button state, or history manipulation (setView contract, §6.3)

### 16.6 Stats Grid Variant (`stats-grid`)

A table layout of the same `/api/stats` data, toggled via `viewToggleBtn` (`?view=stats-grid`). Rows are measurements; columns are statistics. It reuses the `#stats-view` panel (plain HTML table, `.stats-grid-table`), the same fetch, the same day filter and cutoff controls, and the same accent color per row (first column text + row hover tint from `CHART_PALETTE`).

| Column | Content | Header tooltip |
| -------- | ------- | -------------- |
| Measurement | `label` (accent color) | "Statistics per measurement over the selected range" |
| Samples | `count` | "Number of non-null samples in the range" |
| Average | `mean` + unit | §16.2 mean-row text |
| Max | `max.value` + unit | §16.2 max-row text |
| Max first seen | `max.timestamp` (ISO, seconds omitted) | "Date-time of the first occurrence of the maximum" |
| Min | `min.value` + unit | §16.2 min-row text |
| Min first seen | `min.timestamp` | "Date-time of the first occurrence of the minimum" |
| High mins/day | `high.avgDailyMinutes` + sub `> {threshold} {unit}` | §16.2 high-row text |
| Low mins/day | `low.avgDailyMinutes` + sub `< {threshold} {unit}` | §16.2 low-row text |

Cell tooltips: the High/Low cells carry the §16.2 high/low tooltips (method-aware); the Measurement cell carries the card-level tooltip ("Statistics for {label} … — N samples"). Rows are keyboard-focusable with the same CSS tooltip behavior as the cards. Empty range → same info-view message as the card view.

---

## 17. Change Management

This section tracks changes to the design document itself. Every modification to this document must be recorded below.

| Version | Date | Section Changed | Description |
|---------|------|----------------|-------------|
| 3.0 | 2026-08-26 | §1–§16, new | New Stats view — per-column stat cards (mean, max/min + first occurrence, high/low average daily durations) computed by new backend `GET /api/stats`; new `#stats-btn`, `#high-cutoff-select`, `#low-cutoff-select` controls; day filter now shared with stats view; status bar always shows selected-range day count (`#range-days`); CSS tooltips on all stat cards; new `stats` view mode in setView/URL state |
| 3.1 | 2026-08-26 | §16.1, §16.5 | Stat cards get a per-measurement accent color (`--stat-accent`: 3px top border + header text) using a shared `CHART_PALETTE` moved to `shared.ts` so stats and chart colors match; cutoff abbreviation in card sub-lines changes from `(95th pct)` to `(95%)` (#55) |
| 3.2 | 2026-08-26 | §16.2 | High/low row tooltips echo the response `method` field: percentage-unit columns (e.g. SOC) use the direct data percentile as threshold instead of `mean ± z·σ` (backend design v3.1, #56) |
| 3.3 | 2026-08-26 | §2.1, §2.3, §6.x button tables | Title-bar buttons compacted: horizontal padding `8px 16px` → `8px 10px`; grid button labels shortened — `📋 Data Grid` and `📊 Histogram Grid` both become `📋 Grid`, tooltips clarify which graph's data the grid shows (chart data / histogram binned averages) (#57) |
| 4.0 | 2026-08-26 | §3.1, §8.1, §9.1, §9.3, new §16.6 | New `stats-grid` view mode — table variant of the Stats view (rows = measurements, columns = statistics: samples, average, max/min + first-occurrence, high/low min-day), toggled via `viewToggleBtn` in the stats views; `?view=stats-grid` URL state (#58) |
| 4.2 | 2026-08-26 | §16.1, §16.2, §16.6 | High/low threshold sub-lines drop the `(N%)` cutoff suffix (shown in the top bar); percentage-unit columns now show the selected cutoff as an absolute percent limit (e.g. SOC `> 95%` / `< 5%`) with method text `the selected N% limit`; tooltip `{threshold-desc}` is method-aware (#60) |
| 4.1 | 2026-08-26 | §1.1, §2.2, §6.1, §7, §8.3, §8.4, §10.5 | Design review against implementation (#59): added `stats-view.ts` to source files + esbuild/test notes; status-bar label list gains Stats Grid; `setView` union and `renderStatsView(updateWaiting, asGrid)` signatures updated; DOM refs table gains `histogramControls`/`dayFilterGroup`/`statsCutoffs`; stats flow reflects both variants; fixed stats-grid cutoff/dayFilter re-render handlers (kept current stats view) |
| 5.2 | 2026-08-28 | §2.2 | Status bar view label for the `chart` view corrected from `Chart` to `Series`, matching the major-view name rename ("Chart" removed as too general); `FRONTEND_VERSION` → 5.2.0 (#80) |
| 6.0 | 2026-08-28 | §10.2, §11 | Histogram per-bin value range: datasets carry per-bin `min[]`/`max[]` from `/api/histogram`; combined and split renderers draw a low-opacity floating-bar shaded range (`[min,max]`) behind each average bar and append the range to the tooltip (§10.2.1); `FRONTEND_VERSION` → 6.0.0 (#81) |
| 7.1 | 2026-08-30 | §10.2.1 | Histogram range-band fix: both bar datasets use `grouped: false` so the average bar centres on top of the full-width range band instead of rendering side-by-side with it (#83) |
| 7.2 | 2026-08-29 | §15.8, new | Full-day chart axes (#85): series x-axis always spans the whole selected range (single day 00:00–24:00) at a fixed grid step (5/30/60 min) with `null` gaps for empty buckets; percentage-unit (SOC) y-axes fixed to 0–100 in series and histogram charts; histogram x-axis always shows the full 00:00–24:00 bin grid (backend v4.1) with empty bins as gaps; raw-data chart exposes `__chartInstance` on its canvas for UI tests; `FRONTEND_VERSION` → 7.2.0 |
| 8.0 | 2026-09-12 | §2.2, §3.3, §4, §6, §7.1.1, §8.1, §9.3, §10.3, §10.6, §11 | Background database refresh (#89): `↻ Refresh` no longer routes through `setView` — `runBackgroundRefresh()` runs `POST /api/refresh` + `GET /api/dates` while the current view stays visible and interactive (only `#refresh-btn` is disabled); a **"refreshing ..."** indicator (`#refresh-status`) is shown in the status bar while the update runs; on completion the current view is re-rendered; the `SetViewOptions.refresh` flag and `renderRefreshView()` are removed; refresh failure pushes a single error entry (Close → back → re-render); the waiting view (spinner) is kept for all data-loading `setView()` paths; `FRONTEND_VERSION` → 8.0.0 |
| 7.4 | 2026-08-30 | §15.8 | Series chart renders **raw data** (#88): every row is plotted as a point at its actual timestamp on a linear full-range time axis (fixed 5/30/60-min ticks govern tick placement only — the v7.2 bucket flooring that dropped most points is removed; binning remains histogram-only); line segments are straight (`tension: 0`, no curve smoothing) so peaks are visible; tooltip titles use the hovered row's own timestamp; `FRONTEND_VERSION` → 7.4.0 |
| 7.3 | 2026-08-30 | §2.1, §8.4, §16.1, §16.2, §16.3 | High/low thresholds for ordinary units are now based on the **observed range** (backend v4.2, #87): cutoff dropdowns re-described (high: `max − (100−x)%` of the max–min range, low: `min + x%`); tooltip `{method}` text `mean + z·σ` → `based on the observed max/min range` and `{threshold-desc}` `at the {cutoff}th percentile` → `top {100−cutoff}% of the observed range` (high rows) / `bottom {cutoff}% of the observed range` (low rows); percentage-unit columns (SOC) unchanged; `FRONTEND_VERSION` → 7.3.0 |
| 7.0 | 2026-08-29 | §1.1, §2.1, §3, §5, §6, §8, §9, §10, §14, §15, §17 | Histogram: the combined view (all columns in one chart) and the Split/Combine sub-mode are **removed** — the histogram view renders one bar chart per selected column; `#split-btn`, the `?split` URL parameter and the `isSplit` history payload are gone (#82); the average bar is drawn centred on top of a full-width shaded range band at ~60% of its width (§10.2.1) (#83); the three major-view buttons move to the top right of the new title row (`.header-top`), same line as the logo, wrapping below the title on narrow viewports — all other controls stay in the controls row (#84); `FRONTEND_VERSION` → 7.0.0 |
