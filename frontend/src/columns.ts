// ============================================================
// NOTE: All changes MUST conform to frontend/frontend-design.md.
// Changes to the design document must be approved before implementation.
// ============================================================

// ============================================================
// Column selection — checkboxes, panel rendering
// ============================================================

import {
  appState,
  saveSelectedColumnNames,
  saveCustomDefaultColumns,
  resetCustomDefaultColumns,
  getDefaultColumnNames,
  DEFAULT_COLUMN_NAMES,
  columnsViewInner,
  ColumnMeta,
} from "./shared";

// ------------------------------------------------------------------
// Render checkboxes inside the columns panel
// ------------------------------------------------------------------
export function renderColumnCheckboxes(): void {
  columnsViewInner.innerHTML = "";

  // Header with action buttons
  const header = document.createElement("div");
  header.className = "columns-view-header";

  const title = document.createElement("h2");
  title.textContent = "Select columns to display";
  header.appendChild(title);

  const actions = document.createElement("div");
  actions.className = "columns-view-actions";

  const clearBtn = document.createElement("button");
  clearBtn.textContent = "Clear";
  clearBtn.onclick = () => {
    appState.selectedColumnNames.clear();
    appState.selectedColumnNames.add("device_timestamp");
    saveSelectedColumnNames(appState.selectedColumnNames);
    renderColumnCheckboxes();
  };

  const defaultBtn = document.createElement("button");
  defaultBtn.textContent = "Default";
  defaultBtn.onclick = () => {
    appState.selectedColumnNames.clear();
    appState.selectedColumnNames.add("device_timestamp");
    getDefaultColumnNames().forEach((c) => appState.selectedColumnNames.add(c));
    saveSelectedColumnNames(appState.selectedColumnNames);
    renderColumnCheckboxes();
  };

  const saveDefaultBtn = document.createElement("button");
  saveDefaultBtn.textContent = "Save as Default";
  saveDefaultBtn.onclick = () => {
    saveCustomDefaultColumns(appState.selectedColumnNames);
    saveSelectedColumnNames(appState.selectedColumnNames);
  };

  const resetDefaultBtn = document.createElement("button");
  resetDefaultBtn.textContent = "Reset Default";
  resetDefaultBtn.onclick = () => {
    resetCustomDefaultColumns();
    appState.selectedColumnNames.clear();
    appState.selectedColumnNames.add("device_timestamp");
    DEFAULT_COLUMN_NAMES.forEach((c) => appState.selectedColumnNames.add(c));
    saveSelectedColumnNames(appState.selectedColumnNames);
    renderColumnCheckboxes();
  };

  actions.appendChild(clearBtn);
  actions.appendChild(defaultBtn);
  actions.appendChild(saveDefaultBtn);
  actions.appendChild(resetDefaultBtn);
  header.appendChild(actions);
  columnsViewInner.appendChild(header);

  // Checkbox grid
  const grid = document.createElement("div");
  grid.className = "columns-view-grid";

  appState.columnMetadata.forEach((col: ColumnMeta) => {
    const label = document.createElement("label");
    const isTimestamp = col.name === "device_timestamp";

    if (isTimestamp) {
      label.classList.add("disabled-label");
    }

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = appState.selectedColumnNames.has(col.name) || isTimestamp;
    if (isTimestamp) {
      cb.disabled = true;
    }

    cb.addEventListener("change", () => {
      if (cb.checked) {
        appState.selectedColumnNames.add(col.name);
      } else {
        appState.selectedColumnNames.delete(col.name);
      }
      appState.selectedColumnNames.add("device_timestamp");
      saveSelectedColumnNames(appState.selectedColumnNames);
    });

    label.appendChild(cb);
    label.appendChild(document.createTextNode(col.label));
    grid.appendChild(label);
  });

  columnsViewInner.appendChild(grid);
}
