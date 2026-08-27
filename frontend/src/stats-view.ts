// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

/// <reference lib="dom" />

// ============================================================
// Stats view renderer (design §16)
// Pure renderer: builds the stat card DOM + tooltips.
// No panel visibility, button state, or history manipulation
// (setView contract, §6.3).
// ============================================================

import {
  appState,
  dayFilterSelect,
  highCutoffSelect,
  lowCutoffSelect,
  statsViewPanel,
  rowCountEl,
  fetchWithTimeout,
  isDateRange,
  RenderOk,
  StatsEntry,
  StatsResponse,
  CHART_PALETTE,
} from "./shared";

// ------------------------------------------------------------------
// Formatting helpers
// ------------------------------------------------------------------
function fmtVal(v: number): string {
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function withUnit(v: number, unit: string): string {
  return unit ? `${fmtVal(v)} ${unit}` : fmtVal(v);
}

/** "2025-07-22 13:30:00" → "2025-07-22 13:30" */
function fmtTs(ts: string): string {
  return ts.length >= 16 ? ts.slice(0, 16) : ts;
}

/** 42.5 → "42.5 mins/day", 15 → "15 mins/day" (#61: mins = minutes, distinct from Min = minimum) */
function fmtMinutes(m: number): string {
  return `${Number.isInteger(m) ? m : m.toFixed(1)} mins/day`;
}

/** 95 → "95th", 1 → "1st" */
function ordinal(n: number): string {
  return n === 1 ? "1st" : `${n}th`;
}

/** Tooltip description of how the threshold was computed (design §16.2) */
function methodDesc(t: { cutoff: number; method: string }): string {
  return t.method === "cutoff"
    ? `the selected ${t.cutoff}% limit (percentage-unit column)`
    : "mean + z·σ";
}

/**
 * "at the 95th percentile" for mean-sigma; empty for cutoff (the value
 * already carries the % unit). Design §16.2.
 */
function thresholdDesc(t: { cutoff: number; method: string }): string {
  return t.method === "cutoff" ? "" : ` at the ${ordinal(t.cutoff)} percentile`;
}

const WEEKDAY_NAMES: Record<string, string> = {
  sun: "Sunday",
  mon: "Monday",
  tue: "Tuesday",
  wed: "Wednesday",
  thu: "Thursday",
  fri: "Friday",
  sat: "Saturday",
};

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}


function statRow(
  tooltip: string,
  main: string,
  sub?: string,
): HTMLElement {
  const row = el("div", "stat-row");
  row.tabIndex = 0;
  row.dataset.tooltip = tooltip;
  row.appendChild(el("span", "stat-row-main", main));
  if (sub !== undefined) row.appendChild(el("span", "stat-row-sub", sub));
  return row;
}

// ------------------------------------------------------------------
// Card builder — one card per stats entry (design §16.1 / §16.2)
// `index` selects the per-measurement accent color (same cycle order
// as the line-chart datasets, so colors match across views).
// ------------------------------------------------------------------
function buildStatCard(entry: StatsEntry, index: number): HTMLElement {
  const { label, unit, count, mean, max, min, high, low } = entry;
  const from = appState.dateRangeFrom;
  const to = appState.dateRangeTo;
  const rangeDesc = isDateRange() ? `over ${from} to ${to}` : `over ${from}`;
  const dayName = WEEKDAY_NAMES[dayFilterSelect.value];
  const dayDesc = dayName ? `, weekdays only: ${dayName}` : "";

  const card = el("div", "stat-card");
  card.tabIndex = 0;
  card.style.setProperty("--stat-accent", CHART_PALETTE[index % CHART_PALETTE.length]);
  card.dataset.tooltip = `Statistics for ${label} ${rangeDesc}${dayDesc} — ${count} samples`;

  const header = el("div", "stat-card-header", label);
  card.appendChild(header);

  card.appendChild(
    statRow(
      `Arithmetic mean of all ${count} samples in the selected date range.`,
      `Average ${withUnit(mean, unit)}`,
    ),
  );

  card.appendChild(
    statRow(
      "Maximum value observed; shown with the date-time of its first occurrence.",
      `Max ${withUnit(max.value, unit)}`,
      fmtTs(max.timestamp),
    ),
  );

  card.appendChild(
    statRow(
      "Minimum value observed; shown with the date-time of its first occurrence.",
      `Min ${withUnit(min.value, unit)}`,
      fmtTs(min.timestamp),
    ),
  );

  card.appendChild(
    statRow(
      `Average time per day the value was above the high threshold (${methodDesc(high)}). ` +
        `Threshold: ${withUnit(high.threshold, unit)}${thresholdDesc(high)}. ` +
        `Days with samples but no high readings count as 0.`,
      `High ${fmtMinutes(high.avgDailyMinutes)}`,
      `> ${withUnit(high.threshold, unit)}`,
    ),
  );

  card.appendChild(
    statRow(
      `Average time per day the value was below the low threshold (${methodDesc(low)}). ` +
        `Threshold: ${withUnit(low.threshold, unit)}${thresholdDesc(low)}. ` +
        `Days with samples but no low readings count as 0.`,
      `Low ${fmtMinutes(low.avgDailyMinutes)}`,
      `< ${withUnit(low.threshold, unit)}`,
    ),
  );

  return card;
}

// ------------------------------------------------------------------
// Stats grid variant — table layout (design §16.6)
// Rows = measurements, columns = statistics.
// ------------------------------------------------------------------
function buildStatsGrid(result: StatsResponse): HTMLElement {
  const { stats } = result;
  const from = appState.dateRangeFrom;
  const to = appState.dateRangeTo;
  const rangeDesc = isDateRange() ? `over ${from} to ${to}` : `over ${from}`;
  const dayName = WEEKDAY_NAMES[dayFilterSelect.value];
  const dayDesc = dayName ? `, weekdays only: ${dayName}` : "";

  const table = el("table", "stats-grid-table");

  const headers: [string, string][] = [
    ["Measurement", "Statistics per measurement over the selected range"],
    ["Samples", "Number of non-null samples in the range"],
    ["Average", "Arithmetic mean of all samples in the selected date range."],
    ["Max", "Maximum value observed."],
    ["Max first seen", "Date-time of the first occurrence of the maximum."],
    ["Min", "Minimum value observed."],
    ["Min first seen", "Date-time of the first occurrence of the minimum."],
    ["High mins/day", "Average time per day above the high threshold."],
    ["Low mins/day", "Average time per day below the low threshold."],
  ];
  const thead = el("thead");
  const htr = el("tr");
  for (const [text, tip] of headers) {
    const th = el("th");
    th.textContent = text;
    th.dataset.tooltip = tip;
    htr.appendChild(th);
  }
  thead.appendChild(htr);
  table.appendChild(thead);

  const tbody = el("tbody");
  stats.forEach((entry, i) => {
    const { label, unit, count, mean, max, min, high, low } = entry;
    const tr = el("tr");
    tr.tabIndex = 0;
    tr.style.setProperty("--stat-accent", CHART_PALETTE[i % CHART_PALETTE.length]);

    const nameTd = el("td", "stats-grid-name");
    nameTd.textContent = label;
    nameTd.dataset.tooltip = `Statistics for ${label} ${rangeDesc}${dayDesc} — ${count} samples`;
    tr.appendChild(nameTd);

    const plain = (text: string) => {
      const td = el("td", "stats-grid-num");
      td.textContent = text;
      tr.appendChild(td);
    };
    plain(String(count));
    plain(withUnit(mean, unit));
    plain(withUnit(max.value, unit));
    plain(fmtTs(max.timestamp));
    plain(withUnit(min.value, unit));
    plain(fmtTs(min.timestamp));

    const dur = (t: StatsEntry["high"], sign: string) => {
      const td = el("td", "stats-grid-num");
      td.appendChild(el("span", "stat-row-main", fmtMinutes(t.avgDailyMinutes)));
      td.appendChild(el("span", "stat-row-sub", `${sign} ${withUnit(t.threshold, unit)}`));
      td.dataset.tooltip =
        `Average time per day the value was ${sign === ">" ? "above the high" : "below the low"} ` +
        `threshold (${methodDesc(t)}). ` +
        `Threshold: ${withUnit(t.threshold, unit)}${thresholdDesc(t)}. ` +
        `Days with samples but no readings on that side count as 0.`;
      tr.appendChild(td);
    };
    dur(high, ">");
    dur(low, "<");

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  return table;
}

// ------------------------------------------------------------------
// renderStatsView — fetch + build (design §16.5 / §16.6)
// ------------------------------------------------------------------
export async function renderStatsView(
  updateWaiting: (text: string) => void,
  asGrid: boolean = false,
): Promise<RenderOk> {
  updateWaiting("Fetching statistics…");

  const cols = [...appState.selectedColumnNames];
  if (cols.length === 0) {
    throw new Error("Select at least one column to display.");
  }

  const from = appState.dateRangeFrom;
  const to = appState.dateRangeTo;
  const url =
    `/api/stats?from=${encodeURIComponent(from)}` +
    `&to=${encodeURIComponent(to)}` +
    `&columns=${encodeURIComponent(cols.join(","))}` +
    `&dayFilter=${encodeURIComponent(dayFilterSelect.value)}` +
    `&highCutoff=${encodeURIComponent(highCutoffSelect.value)}` +
    `&lowCutoff=${encodeURIComponent(lowCutoffSelect.value)}`;

  const res = await fetchWithTimeout(url, 30_000);
  const result = (await res.json()) as StatsResponse;
  appState.statsResult = result;

  updateWaiting(asGrid ? "Building stats grid…" : "Building stat cards…");
  statsViewPanel.classList.toggle("stats-grid-mode", asGrid);
  if (asGrid) {
    statsViewPanel.replaceChildren(buildStatsGrid(result));
  } else {
    // map passes (entry, index) — accent color cycles per index
    statsViewPanel.replaceChildren(...result.stats.map(buildStatCard));
  }
  rowCountEl.textContent = result.stats.length === 1
    ? "1 column"
    : `${result.stats.length} columns`;

  return { ok: true };
}
