// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// Date navigation — prev/next/today, date picker events
// ============================================================

import {
  appState,
  dateFromInput,
  dateToInput,
  todayStr,
  updateNavButtonStates,
} from "./shared";

// ------------------------------------------------------------------
// Shift both date inputs by delta days
// ------------------------------------------------------------------
export function shiftDay(delta: number, onLoad: () => void): void {
  function shiftDate(iso: string, delta: number): string {
    const [y, m, d] = iso.split("-").map(Number);
    const date = new Date(y, m - 1, d + delta);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  appState.dateRangeFrom = shiftDate(appState.dateRangeFrom, delta);
  appState.dateRangeTo = shiftDate(appState.dateRangeTo, delta);
  dateFromInput.value = appState.dateRangeFrom;
  dateToInput.value = appState.dateRangeTo;
  updateNavButtonStates();
  onLoad();
}

// ------------------------------------------------------------------
// Wire date pickers and navigation buttons
// ------------------------------------------------------------------
export function wireDateNavigation(onLoad: () => void): void {
  prevDayBtnRef.addEventListener("click", () => shiftDay(-1, onLoad));
  nextDayBtnRef.addEventListener("click", () => shiftDay(1, onLoad));

  todayBtnRef.addEventListener("click", () => {
    const t = todayStr();
    appState.dateRangeFrom = t;
    appState.dateRangeTo = t;
    dateFromInput.value = t;
    dateToInput.value = t;
    updateNavButtonStates();
    onLoad();
  });

  dateFromInput.addEventListener("change", () => {
    appState.dateRangeFrom = dateFromInput.value;
    if (appState.dateRangeTo && appState.dateRangeFrom && appState.dateRangeFrom > appState.dateRangeTo) {
      appState.dateRangeTo = appState.dateRangeFrom;
      dateToInput.value = appState.dateRangeTo;
    }
    updateNavButtonStates();
    onLoad();
  });

  dateToInput.addEventListener("change", () => {
    appState.dateRangeTo = dateToInput.value;
    if (appState.dateRangeFrom && appState.dateRangeTo && appState.dateRangeFrom > appState.dateRangeTo) {
      appState.dateRangeFrom = appState.dateRangeTo;
      dateFromInput.value = appState.dateRangeFrom;
    }
    updateNavButtonStates();
    onLoad();
  });
}

// Import button refs at end to avoid circular issues
import { prevDayBtn, nextDayBtn, todayBtn } from "./shared";
const prevDayBtnRef = prevDayBtn;
const nextDayBtnRef = nextDayBtn;
const todayBtnRef = todayBtn;
