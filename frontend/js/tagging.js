"use strict";

const elements = {
  year: document.querySelector("#tagging-year"),
  type: document.querySelector("#tagging-name"),
  stage: document.querySelector("#tagging-stage"),
  status: document.querySelector("#tagging-status"),
  summary: document.querySelector("#tagging-summary"),
  count: document.querySelector("#tagging-count"),
  searchForm: document.querySelector("#tagging-search-form"),
  searchInput: document.querySelector("#tagging-search"),
  searchButton: document.querySelector("#tagging-search-button"),
  clearSearch: document.querySelector("#tagging-clear-search"),
  toggleAll: document.querySelector("#tagging-toggle-all"),
  levelFilter: document.querySelector("#tagging-level-filter"),
  rows: document.querySelector("#tagging-rows"),
  pageIndicator: document.querySelector("#tagging-page-indicator"),
  previous: document.querySelector("#tagging-previous"),
  next: document.querySelector("#tagging-next"),
  excel: document.querySelector("#tagging-export-excel"),
  pdf: document.querySelector("#tagging-export-pdf"),
  exportSubunits: document.querySelector("#tagging-export-subunits"),
};

const state = {
  year: null,
  stageId: null,
  typeCode: "",
  search: "",
  pageSize: 10,
  offset: 0,
  total: 0,
  requestId: 0,
  periods: [],
  summary: null,
  items: [],
  rawItems: [],
  expandedRows: new Set(),
  subUnits: [],
};

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  let result = {};
  try {
    result = await response.json();
  } catch {
    if (response.ok) throw new Error("Respons server tidak valid.");
  }
  if (!response.ok) {
    throw new Error(result.error || `Permintaan gagal (${response.status}).`);
  }
  return result;
}

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", isError);
}

function formatNumber(value) {
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value ?? 0);
}

function formatCurrency(value) {
  if (value === null || value === undefined) return "—";
  return `Rp ${formatNumber(value)}`;
}

function makeCell(value, numeric = false) {
  const cell = document.createElement("td");
  if (numeric) cell.classList.add("numeric-cell");
  cell.textContent = value === null || value === undefined || value === ""
    ? "—"
    : String(value);
  return cell;
}

function renderSummary(summary, periods) {
  const fragment = document.createDocumentFragment();
  const countRow = document.createElement("div");
  countRow.className = "tagging-summary-row tagging-summary-counts";
  const totalsRow = document.createElement("div");
  totalsRow.className = "tagging-summary-row tagging-summary-totals";
  const periodRow = document.createElement("div");
  periodRow.className = "tagging-summary-row tagging-summary-periods";
  const addCard = (container, label, value) => {
    const card = document.createElement("article");
    card.className = "tagging-summary-card";
    const title = document.createElement("span");
    title.textContent = label;
    const amount = document.createElement("strong");
    amount.textContent = typeof value === "number" ? formatNumber(value) : String(value);
    card.append(title, amount);
    container.append(card);
  };
  addCard(countRow, "Jumlah Sub Unit", summary.sub_unit_count);
  addCard(countRow, "Jumlah sub kegiatan", summary.subactivity_count);
  addCard(countRow, "Jumlah Paket/Kelompok", summary.package_count);
  addCard(totalsRow, "Anggaran", formatCurrency(summary.budget));
  addCard(totalsRow, "Realisasi Total", formatCurrency(summary.realization_total));
  addCard(totalsRow, "Persentase Realisasi Total", `${formatNumber(summary.realization_percentage)}%`);
  for (const period of periods) {
    const value = Number(summary.realization_by_period[period.name] || 0);
    const card = document.createElement("article");
    card.className = "tagging-summary-card";
    const title = document.createElement("span");
    title.textContent = period.label || `Triwulan ${period.name}`;
    const amount = document.createElement("strong");
    amount.textContent = formatCurrency(value);
    const percentage = document.createElement("small");
    percentage.className = "tagging-period-percentage";
    percentage.textContent = `${formatNumber(summary.budget ? (value / summary.budget) * 100 : 0)}% dari anggaran`;
    card.append(title, amount, percentage);
    periodRow.append(card);
  }
  fragment.append(countRow, totalsRow, periodRow);
  elements.summary.replaceChildren(fragment);
}

function periodForQuarter(quarter) {
  const roman = ["I", "II", "III", "IV"][quarter - 1];
  return state.periods.find((period) => {
    const label = String(period.label || period.name).toLocaleUpperCase("id-ID");
    const token = label.trim().split(/\s+/).pop();
    return token === roman || token === String(quarter);
  });
}

function updateToggleAll() {
  const units = state.items;
  const activities = units.flatMap((unit) => unit.children);
  const allExpanded = units.length > 0
    && units.every((unit) => state.expandedRows.has(unit.id))
    && activities
      .filter((activity) => activity.children.length > 0)
      .every((activity) => state.expandedRows.has(activity.id));
  elements.toggleAll.hidden = units.length === 0;
  elements.toggleAll.disabled = units.length === 0;
  elements.toggleAll.textContent = allExpanded
    ? "Tutup semua rincian"
    : "Buka semua rincian";
}

function renderItems(items, resetExpanded = true) {
  if (resetExpanded) state.expandedRows.clear();
  const fragment = document.createDocumentFragment();
  if (items.length === 0) {
    const row = document.createElement("tr");
    const cell = makeCell("Tidak ada tagging untuk filter ini.");
    cell.colSpan = 8;
    row.append(cell);
    fragment.append(row);
  }

  const bySubUnit = new Map();
  for (const item of items) {
    const unitKey = String(item.sub_unit_id);
    if (!bySubUnit.has(unitKey)) {
      bySubUnit.set(unitKey, {
        id: `sub_unit:${unitKey}`,
        code: item.sub_unit_code,
        name: item.sub_unit_name || item.opd_name,
        sub_unit_id: item.sub_unit_id,
        level: "sub_unit",
        children: [],
        budget: 0,
        realization_total: 0,
        realization_by_period: {},
        activities: new Map(),
      });
    }
    const unit = bySubUnit.get(unitKey);
    const activityKey = `${item.sub_unit_id}:${item.sub_kegiatan_id}`;
    if (!unit.activities.has(activityKey)) {
      unit.activities.set(activityKey, {
        id: `sub_kegiatan:${activityKey}`,
        code: item.sub_kegiatan_code,
        name: item.sub_kegiatan_name,
        level: "sub_kegiatan",
        children: [],
        packages: new Map(),
        budget: 0,
        parentBudget: null,
        realization_total: Number(item.realization_total || 0),
        realization_by_period: item.realization_by_period || {},
      });
    }
    const activity = unit.activities.get(activityKey);
    if (item.paket_kelompok_id === null || item.paket_kelompok_id === undefined) {
      activity.parentBudget = Number(item.budget || 0);
      for (const child of item.children || []) {
        activity.packages.set(String(child.paket_kelompok_id), {
          id: child.id,
          code: "",
          name: child.paket_kelompok_name,
          level: "paket",
          children: [],
          budget: Number(child.budget || 0),
          realization_total: null,
          realization_by_period: {},
        });
      }
    } else {
      activity.packages.set(String(item.paket_kelompok_id), {
        id: `package:${activityKey}:${item.paket_kelompok_id}`,
        code: "",
        name: item.paket_kelompok_name,
        level: "paket",
        children: [],
        budget: Number(item.budget || 0),
        realization_total: null,
        realization_by_period: {},
      });
    }
  }

  state.items = Array.from(bySubUnit.values());
  for (const unit of state.items) {
    unit.children = Array.from(unit.activities.values());
    delete unit.activities;
    for (const activity of unit.children) {
      activity.children = Array.from(activity.packages.values());
      activity.budget = activity.parentBudget
        ?? activity.children.reduce((total, child) => total + child.budget, 0);
      delete activity.packages;
      delete activity.parentBudget;
      unit.budget += activity.budget;
      unit.realization_total += activity.realization_total;
      for (const [periodName, value] of Object.entries(activity.realization_by_period)) {
        unit.realization_by_period[periodName] =
          (unit.realization_by_period[periodName] || 0) + Number(value || 0);
      }
    }
  }

  const levelIndex = { sub_unit: 0, sub_kegiatan: 1, paket: 2 };
  const filterLevel = elements.levelFilter.value || "sub_unit";
  const maxLevel = levelIndex[filterLevel] ?? 2;

  function appendItem(item, container = fragment, isChild = false) {
    const row = document.createElement("tr");
    row.className = `tagging-hierarchy-row tagging-${item.level}`;
    const rowId = String(item.id);
    const hasChildren = Array.isArray(item.children)
      && item.children.length > 0;
    const isExpanded = state.expandedRows.has(rowId);
    if (hasChildren && levelIndex[item.level] < maxLevel) {
      row.tabIndex = 0;
      row.setAttribute("aria-expanded", String(isExpanded));
      row.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        toggleRow(item);
      });
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggleRow(item);
        }
      });
    }

    row.append(makeCell(item.code));
    const hierarchy = document.createElement("td");
    hierarchy.className = "tagging-hierarchy-cell";
    const details = document.createElement("div");
    details.className = `tagging-hierarchy-content tagging-level-${item.level}`;
    if (hasChildren && levelIndex[item.level] < maxLevel) {
      const toggle = document.createElement("button");
      toggle.className = "tagging-hierarchy-toggle";
      toggle.type = "button";
      toggle.textContent = isExpanded ? "−" : "+";
      toggle.setAttribute(
        "aria-label",
        `${isExpanded ? "Tutup" : "Buka"} rincian ${item.name}`,
      );
      toggle.addEventListener("click", () => toggleRow(item));
      details.append(toggle);
    }
    const text = document.createElement("span");
    text.textContent = item.name || "—";
    details.append(text);
    hierarchy.append(details);
    row.append(hierarchy);
    row.append(makeCell(formatCurrency(item.budget), true));
    row.append(makeCell(formatCurrency(item.realization_total), true));
    for (const quarter of [1, 2, 3, 4]) {
      const period = periodForQuarter(quarter);
      row.append(makeCell(
        period && item.level !== "paket"
          ? formatCurrency(item.realization_by_period?.[period.name])
          : null,
        true,
      ));
    }
    container.append(row);
    if (hasChildren && isExpanded && levelIndex[item.level] < maxLevel) {
      for (const child of item.children) appendItem(child, container, true);
    }
  }

  function toggleRow(item) {
    const rowId = String(item.id);
    if (state.expandedRows.has(rowId)) {
      state.expandedRows.delete(rowId);
    } else {
      state.expandedRows.add(rowId);
    }
    renderItems(state.rawItems, false);
  }

  for (const item of bySubUnit.values()) {
    appendItem(item);
  }
  elements.rows.replaceChildren(fragment);
  updateToggleAll();
}

function filters(includeExportSubunits = false) {
  const parameters = new URLSearchParams({
    year: String(state.year),
    tahapan_id: String(state.stageId),
  });
  if (state.typeCode) parameters.set("tagging_code", state.typeCode);
  if (state.search) parameters.set("q", state.search);
  if (includeExportSubunits) {
    for (const option of elements.exportSubunits.selectedOptions) {
      parameters.append("skpd_code", option.value);
    }
  }
  return parameters;
}

async function loadTagging() {
  if (state.year === null || state.stageId === null) return;
  const requestId = ++state.requestId;
  const parameters = filters();
  parameters.set("limit", String(state.pageSize));
  parameters.set("offset", String(state.offset));
  setStatus("Memuat daftar tagging...");
  elements.rows.replaceChildren();
  elements.searchButton.disabled = true;
  elements.clearSearch.hidden = !state.search;
  state.expandedRows.clear();
  state.items = [];
  state.rawItems = [];
  updateToggleAll();
  elements.excel.disabled = true;
  elements.pdf.disabled = true;
  try {
    const result = await fetchJson(`/api/tagging?${parameters}`);
    if (requestId !== state.requestId) return;
    state.total = result.total;
    state.periods = result.periods;
    state.summary = result.summary;
    renderSummary(result.summary, result.periods);
    state.rawItems = result.items;
    renderItems(result.items);
    elements.count.textContent = `${formatNumber(result.total)} data`;
    const pageCount = Math.ceil(result.total / state.pageSize);
    elements.pageIndicator.textContent = pageCount
      ? `Halaman ${Math.floor(state.offset / state.pageSize) + 1} dari ${pageCount}`
      : "";
    elements.previous.disabled = state.offset === 0;
    elements.next.disabled = state.offset + state.pageSize >= state.total;
    elements.excel.disabled = result.total === 0;
    elements.pdf.disabled = result.total === 0;
    setStatus(
      result.total
        ? `Daftar tagging tahun ${state.year}${state.search ? ` untuk “${state.search}”` : ""}.`
        : "Tidak ada data tagging.",
    );
  } catch (error) {
    if (requestId !== state.requestId) return;
    setStatus(error.message, true);
    elements.rows.replaceChildren();
    elements.previous.disabled = true;
    elements.next.disabled = true;
  } finally {
    if (requestId === state.requestId) elements.searchButton.disabled = false;
  }
}

async function loadYear(year) {
  const requestId = ++state.requestId;
  state.year = year ? Number(year) : null;
  state.stageId = null;
  state.typeCode = "";
  state.search = "";
  state.offset = 0;
  state.total = 0;
  elements.rows.replaceChildren();
  elements.summary.replaceChildren();
  elements.searchInput.value = "";
  elements.clearSearch.hidden = true;
  elements.toggleAll.hidden = true;
  elements.count.textContent = "";
  elements.pageIndicator.textContent = "";
  elements.previous.disabled = true;
  elements.next.disabled = true;
  elements.excel.disabled = true;
  elements.pdf.disabled = true;
  elements.stage.replaceChildren(new Option("Memuat tahapan...", ""));
  elements.type.replaceChildren(new Option("Semua jenis tagging", ""));
  elements.stage.disabled = true;
  elements.type.disabled = true;
  if (state.year === null) {
    setStatus("Pilih tahun untuk menampilkan daftar.");
    return;
  }
  try {
    const [stageResult, typeResult, subUnitResult] = await Promise.all([
      fetchJson(`/api/tahapan?year=${encodeURIComponent(state.year)}`),
      fetchJson(`/api/tagging-types?year=${encodeURIComponent(state.year)}`),
      fetchJson(`/api/sub-units?year=${encodeURIComponent(state.year)}`),
    ]);
    if (requestId !== state.requestId) return;
    elements.stage.replaceChildren(new Option("Pilih tahapan", ""));
    for (const stage of stageResult.tahapan) {
      elements.stage.add(new Option(stage.name, String(stage.id)));
    }
    elements.type.replaceChildren(new Option("Semua jenis tagging", ""));
    for (const type of typeResult.tagging_types) {
      elements.type.add(new Option(type.name, String(type.code)));
    }
    elements.stage.disabled = stageResult.tahapan.length === 0;
    elements.type.disabled = typeResult.tagging_types.length === 0;
    elements.exportSubunits.replaceChildren();
    state.subUnits = subUnitResult.sub_units;
    for (const subUnit of state.subUnits) {
      elements.exportSubunits.add(new Option(`${subUnit.name} (${subUnit.code})`, subUnit.code));
    }
    elements.exportSubunits.disabled = state.subUnits.length === 0;
    if (stageResult.default_tahapan_id !== null) {
      state.stageId = stageResult.default_tahapan_id;
      elements.stage.value = String(state.stageId);
      await loadTagging();
    } else {
      setStatus("Belum ada tahapan untuk tahun tersebut.", true);
    }
  } catch (error) {
    if (requestId !== state.requestId) return;
    setStatus(error.message, true);
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

async function exportExcel() {
  const sheetMode = await window.chooseExportSheetMode();
  if (!sheetMode) return;
  elements.excel.disabled = true;
  try {
    const exportFilters = filters(true);
    const summaryParameters = new URLSearchParams(exportFilters);
    summaryParameters.set("limit", "1");
    summaryParameters.set("offset", "0");
    const summaryResult = await fetchJson(`/api/tagging?${summaryParameters}`);
    const filteredTotal = summaryResult.total;
    const items = [];
    for (let offset = 0; offset < filteredTotal; offset += 200) {
      const parameters = new URLSearchParams(exportFilters);
      parameters.set("limit", "200");
      parameters.set("offset", String(offset));
      const result = await fetchJson(`/api/tagging?${parameters}`);
      items.push(...result.items);
    }
    const headers = [
      "No",
      "Perangkat Daerah",
      "Kode Sub Kegiatan",
      "Sub Kegiatan",
      "Paket/Kelompok",
      "Anggaran",
      "Realisasi Total",
      ...state.periods.map((period) => period.label),
    ];
    const detailRows = items.map((item, index) => [
      index + 1,
      item.perangkat_daerah_name,
      item.sub_kegiatan_code,
      item.sub_kegiatan_name,
      item.paket_kelompok_name,
      item.budget,
      item.realization_total,
      ...state.periods.map(
        (period) => item.realization_by_period[period.name] ?? 0,
      ),
    ]);
    const summaryRows = [
      ["Ringkasan Tagging", state.year],
      ["Jumlah Sub Unit", summaryResult.summary.sub_unit_count],
      ["Jumlah sub kegiatan", summaryResult.summary.subactivity_count],
      ["Jumlah paket pekerjaan", summaryResult.summary.package_count],
      ["Anggaran", summaryResult.summary.budget],
      ["Realisasi total", summaryResult.summary.realization_total],
      ["Persentase Realisasi Total", summaryResult.summary.realization_percentage],
      ...state.periods.map((period) => [
        period.label,
        summaryResult.summary.realization_by_period[period.name] ?? 0,
      ]),
    ];
    const sheets = [];
    if (sheetMode === "single") {
      sheets.push({
        name: "Daftar Tagging",
        rows: [...summaryRows, [], headers, ...detailRows],
      });
    } else {
      sheets.push({ name: "Ringkasan", rows: summaryRows });
      const groupedRows = new Map();
      items.forEach((item, index) => {
        const unitName = item.sub_unit_name || item.perangkat_daerah_name || "Tanpa Sub Unit";
        if (!groupedRows.has(unitName)) groupedRows.set(unitName, []);
        groupedRows.get(unitName).push(detailRows[index]);
      });
      for (const [unitName, unitRows] of groupedRows) {
        sheets.push({ name: unitName, rows: [headers, ...unitRows] });
      }
    }
    window.downloadXlsx(`tagging-${state.year}.xlsx`, sheets);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    elements.excel.disabled = state.total === 0;
  }
}

async function exportPdf() {
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    setStatus("Izinkan pop-up untuk mencetak daftar tagging.", true);
    return;
  }
  elements.pdf.disabled = true;
  try {
    const exportFilters = filters(true);
    const summaryParameters = new URLSearchParams(exportFilters);
    summaryParameters.set("limit", "1");
    summaryParameters.set("offset", "0");
    const filteredSummary = await fetchJson(`/api/tagging?${summaryParameters}`);
    const filteredTotal = filteredSummary.total;
    const items = [];
    for (let offset = 0; offset < filteredTotal; offset += 200) {
      const parameters = new URLSearchParams(exportFilters);
      parameters.set("limit", "200");
      parameters.set("offset", String(offset));
      const result = await fetchJson(`/api/tagging?${parameters}`);
      items.push(...result.items);
    }
    const rows = items.map((item, index) => {
      const quarters = [1, 2, 3, 4].map((quarter) => {
        const period = periodForQuarter(quarter);
        const value = period
          ? formatCurrency(item.realization_by_period[period.name])
          : "—";
        return `<td>${escapeHtml(value)}</td>`;
      }).join("");
      return `<tr><td>${index + 1}</td><td>${escapeHtml(item.perangkat_daerah_name || item.sub_unit_name)}</td><td>${escapeHtml(item.sub_kegiatan_code)} — ${escapeHtml(item.sub_kegiatan_name)}</td><td>${escapeHtml(item.paket_kelompok_name || "—")}</td><td>${escapeHtml(formatCurrency(item.budget))}</td><td>${escapeHtml(formatCurrency(item.realization_total))}</td>${quarters}</tr>`;
    }).join("");
    const summaryRows = [
      ["Jumlah Sub Unit", filteredSummary.summary.sub_unit_count],
      ["Jumlah sub kegiatan", filteredSummary.summary.subactivity_count],
      ["Jumlah paket pekerjaan", filteredSummary.summary.package_count],
    ].map(([label, value]) => [label, formatNumber(value)]);
    summaryRows.push(
      ["Anggaran", formatCurrency(filteredSummary.summary.budget)],
      ["Realisasi total", formatCurrency(filteredSummary.summary.realization_total)],
      ["Persentase Realisasi Total", `${formatNumber(filteredSummary.summary.realization_percentage)}%`],
      ...state.periods.map((period) => [
        period.label || `Triwulan ${period.name}`,
        `${formatCurrency(filteredSummary.summary.realization_by_period[period.name] ?? 0)} (${formatNumber(
          filteredSummary.summary.budget
            ? ((filteredSummary.summary.realization_by_period[period.name] ?? 0) / filteredSummary.summary.budget) * 100
            : 0,
        )}%)`,
      ]),
    );
    const summaryTableRows = summaryRows.map(([label, value]) =>
      `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`,
    ).join("");
    const selectedType = elements.type.selectedOptions[0]?.textContent
      || "Semua Jenis";
    const title = `Tagging '${selectedType}' - '${state.year}'`;
    printWindow.document.open();
    printWindow.document.write(
      `<!doctype html><html lang="id"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><style>body{font:12px Arial,sans-serif;color:#172b4d}h1{font-size:20px}table{width:100%;border-collapse:collapse;margin-bottom:18px}th,td{border:1px solid #bbb;padding:6px;text-align:left}th{background:#edf6ff}.summary{width:auto;min-width:320px}.summary th{text-align:left}@media print{body{margin:12mm}}</style></head><body><h1>${escapeHtml(title)}</h1><h2>Ringkasan Tagging</h2><table class="summary"><tbody>${summaryTableRows}</tbody></table><p>${items.length} data</p><table><thead><tr><th>No</th><th>Perangkat Daerah</th><th>Sub Kegiatan</th><th>Paket/Kelompok</th><th>Anggaran</th><th>Realisasi Total</th><th>Triwulan I</th><th>Triwulan II</th><th>Triwulan III</th><th>Triwulan IV</th></tr></thead><tbody>${rows}</tbody></table></body></html>`,
    );
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  } catch (error) {
    printWindow.close();
    setStatus(error.message, true);
  } finally {
    elements.pdf.disabled = state.total === 0;
  }
}

async function initialize() {
  try {
    const result = await fetchJson("/api/years");
    elements.year.replaceChildren(new Option("Pilih tahun", ""));
    for (const year of result.years) {
      elements.year.add(new Option(String(year), String(year)));
    }
    elements.year.disabled = result.years.length === 0;
    const currentYear = new Date().getFullYear();
    const initialYear = result.years.includes(currentYear)
      ? currentYear
      : result.years[0];
    if (initialYear !== undefined) {
      elements.year.value = String(initialYear);
      await loadYear(String(initialYear));
    } else {
      setStatus("Belum ada data tahun yang tersedia.", true);
    }
  } catch (error) {
    setStatus(error.message, true);
  }
}

elements.year.addEventListener("change", () => void loadYear(elements.year.value));
elements.type.addEventListener("change", () => {
  state.typeCode = elements.type.value;
  state.offset = 0;
  void loadTagging();
});
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.searchInput.value.trim();
  state.offset = 0;
  void loadTagging();
});
elements.clearSearch.addEventListener("click", () => {
  elements.searchInput.value = "";
  state.search = "";
  state.offset = 0;
  void loadTagging();
});
elements.toggleAll.addEventListener("click", () => {
  const activities = state.items.flatMap((unit) => unit.children);
  const allExpanded = state.items.length > 0
    && state.items.every((unit) => state.expandedRows.has(unit.id))
    && activities
      .filter((activity) => activity.children.length > 0)
      .every((activity) => state.expandedRows.has(activity.id));
  state.expandedRows.clear();
  if (!allExpanded) {
    for (const unit of state.items) {
      state.expandedRows.add(unit.id);
      for (const activity of unit.children) {
        if (activity.children.length > 0) state.expandedRows.add(activity.id);
      }
    }
    elements.levelFilter.value = "paket";
  } else {
    elements.levelFilter.value = "sub_unit";
  }
  renderItems(state.rawItems, false);
});
elements.levelFilter.addEventListener("change", () => {
  state.expandedRows.clear();
  const maxLevel = { sub_unit: 0, sub_kegiatan: 1, paket: 2 }[elements.levelFilter.value];
  if (maxLevel >= 1) {
    for (const unit of state.items) state.expandedRows.add(unit.id);
  }
  if (maxLevel >= 2) {
    for (const unit of state.items) {
      for (const activity of unit.children) {
        if (activity.children.length > 0) state.expandedRows.add(activity.id);
      }
    }
  }
  renderItems(state.rawItems, false);
});
elements.stage.addEventListener("change", () => {
  state.stageId = elements.stage.value ? Number(elements.stage.value) : null;
  state.offset = 0;
  if (state.stageId === null) {
    state.requestId += 1;
    state.total = 0;
    elements.rows.replaceChildren();
    elements.summary.replaceChildren();
    elements.count.textContent = "";
    elements.pageIndicator.textContent = "";
    elements.previous.disabled = true;
    elements.next.disabled = true;
    elements.excel.disabled = true;
    elements.pdf.disabled = true;
    setStatus("Pilih tahapan untuk menampilkan daftar.");
  } else {
    void loadTagging();
  }
});
elements.previous.addEventListener("click", () => {
  if (state.offset > 0) {
    state.offset = Math.max(0, state.offset - state.pageSize);
    void loadTagging();
  }
});
elements.next.addEventListener("click", () => {
  if (state.offset + state.pageSize < state.total) {
    state.offset += state.pageSize;
    void loadTagging();
  }
});
elements.excel.addEventListener("click", exportExcel);
elements.pdf.addEventListener("click", () => void exportPdf());

void initialize();
