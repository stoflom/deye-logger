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

/** 42.5 → "42.5 min/day", 15 → "15 min/day" */
function fmtMinutes(m: number): string {
  return `${Number.isInteger(m) ? m : m.toFixed(1)} min/day`;
}

/** 95 → "95th", 1 → "1st" */
function ordinal(n: number): string {
  return n === 1 ? "1st" : `${n}th`;
}

/** Tooltip description of how the threshold was computed (design §16.2) */
function methodDesc(t: { cutoff: number; method: string }): string {
  return t.method === "percentile"
    ? `the direct ${ordinal(t.cutoff)} percentile of the data (percentage-unit column)`
    : "mean + z·σ";
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
        `Threshold: ${withUnit(high.threshold, unit)} at the ${ordinal(high.cutoff)} percentile. ` +
        `Days with samples but no high readings count as 0.`,
      `High ${fmtMinutes(high.avgDailyMinutes)}`,
      `> ${withUnit(high.threshold, unit)} (${high.cutoff}%)`,
    ),
  );

  card.appendChild(
    statRow(
      `Average time per day the value was below the low threshold (${methodDesc(low)}). ` +
        `Threshold: ${withUnit(low.threshold, unit)} at the ${ordinal(low.cutoff)} percentile. ` +
        `Days with samples but no low readings count as 0.`,
      `Low ${fmtMinutes(low.avgDailyMinutes)}`,
      `< ${withUnit(low.threshold, unit)} (${low.cutoff}%)`,
    ),
  );

  return card;
}

// ------------------------------------------------------------------
// renderStatsView — fetch + build (design §16.5)
// ------------------------------------------------------------------
export async function renderStatsView(
  updateWaiting: (text: string) => void,
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

  updateWaiting("Building stat cards…");
  // map passes (entry, index) — accent color cycles per index
  statsViewPanel.replaceChildren(...result.stats.map(buildStatCard));
  rowCountEl.textContent = result.stats.length === 1
    ? "1 column"
    : `${result.stats.length} columns`;

  return { ok: true };
}
