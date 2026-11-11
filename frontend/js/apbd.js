"use strict";

const elements = {
  yearSelect: document.querySelector("#year-select"),
  tahapanSelect: document.querySelector("#tahapan-select"),
  yearStatus: document.querySelector("#year-status"),
  dataContent: document.querySelector("#data-content"),
  summaryPanel: document.querySelector("#summary-panel"),
  taggingSummaryPanel: document.querySelector("#tagging-summary-panel"),
  summary: document.querySelector("#tagging-summary"),
  summaryDetails: document.querySelector("#tagging-summary-details"),
  summaryYear: document.querySelector("#summary-year"),
  searchForm: document.querySelector("#search-form"),
  searchLevel: document.querySelector("#search-level"),
  searchInput: document.querySelector("#search-input"),
  levelSearchWrap: document.querySelector("#level-search-wrap"),
  levelSearchLabel: document.querySelector("#level-search-label"),
  levelSearchInput: document.querySelector("#level-search-input"),
  searchButton: document.querySelector("#search-button"),
  clearSearch: document.querySelector("#clear-search"),
  exportExcel: document.querySelector("#export-excel"),
  exportPdf: document.querySelector("#export-pdf"),
  exportSubunits: document.querySelector("#export-subunits"),
  resultCount: document.querySelector("#result-count"),
  toggleDetails: document.querySelector("#toggle-details"),
  levelFilter: document.querySelector("#hierarchy-level-filter"),
  tableStatus: document.querySelector("#table-status"),
  tableScroll: document.querySelector("#table-scroll"),
  rows: document.querySelector("#data-rows"),
  pagination: document.querySelector("#pagination"),
  pageSize: document.querySelector("#page-size"),
  pageIndicator: document.querySelector("#page-indicator"),
  previousPage: document.querySelector("#previous-page"),
  nextPage: document.querySelector("#next-page"),
};

const state = {
  year: null,
  tahapanId: null,
  page: 0,
  pageSize: Number(elements.pageSize.value),
  search: "",
  levelSearch: "",
  searchLevel: "skpd",
  requestId: 0,
  selectionId: 0,
  rootRows: [],
  detailRows: new Map(),
  expandedRows: new Set(),
  loadingRoots: new Set(),
  displayLevel: "skpd",
};

const hierarchyLevels = {
  skpd: 0,
  sub_unit: 0,
  program: 1,
  kegiatan: 2,
  sub_kegiatan: 3,
  paket: 4,
  kelompok: 5,
  rekening: 6,
};

function hasActiveSearch() {
  return Boolean(state.search || state.levelSearch);
}

function withoutAccountRows(rows) {
  const visibleRows = rows.filter((row) => row.level !== "rekening");
  const parentKeys = new Set(
    visibleRows.map((row) => row.parent_key).filter(Boolean),
  );
  return visibleRows.map((row) => ({
    ...row,
    has_children: parentKeys.has(row.row_key),
  }));
}

function setTableStatus(message, isError = false) {
  elements.tableStatus.textContent = message;
  elements.tableStatus.classList.toggle("is-error", isError);
  elements.tableStatus.hidden = !message;
  elements.tableScroll.hidden = Boolean(message);
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `Permintaan gagal (${response.status}).`;
    try {
      const body = await response.json();
      if (body.error) detail = body.error;
    } catch {
      // Keep the HTTP status as the actionable error if the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

function formatNumber(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("id-ID").format(value);
}

function appendCell(row, value, options = {}) {
  const cell = document.createElement("td");
  if (options.numeric) cell.classList.add("numeric-cell");
  if (options.exportType) cell.dataset.exportType = options.exportType;
  if (options.exportValue !== undefined) {
    cell.dataset.exportValue = String(options.exportValue);
  }

  if (options.tags) {
    const tagList = document.createElement("div");
    tagList.className = "tag-list";
    if (Array.isArray(value) && value.length > 0) {
      for (const tag of value) {
        const chip = document.createElement("span");
        chip.className = "tag-chip";
        chip.textContent = String(tag);
        tagList.append(chip);
      }
    } else {
      tagList.textContent = "—";
    }
    cell.append(tagList);
  } else {
    cell.textContent = value === null || value === undefined || value === ""
      ? "—"
      : String(value);
  }
  row.append(cell);
}

function visibleRows() {
  const visible = [];
  const childrenByParent = new Map();
  for (const records of state.detailRows.values()) {
    for (const record of records) {
      const siblings = childrenByParent.get(record.parent_key) || [];
      siblings.push(record);
      childrenByParent.set(record.parent_key, siblings);
    }
  }

  function appendVisible(record) {
    visible.push(record);
    if ((hierarchyLevels[record.level] ?? 0) >= hierarchyLevels[state.displayLevel]) return;
    if (!state.expandedRows.has(record.row_key)) return;
    for (const child of childrenByParent.get(record.row_key) || []) {
      appendVisible(child);
    }
  }

  for (const root of state.rootRows) {
    appendVisible(root);
  }
  return visible;
}

function updateDetailsButton() {
  const expandableRows = [
    ...state.rootRows,
    ...Array.from(state.detailRows.values()).flat(),
  ].filter((row) => row.has_children);
  const allExpanded = expandableRows.length > 0
    && expandableRows.every((row) => state.expandedRows.has(row.row_key));
  elements.toggleDetails.textContent = allExpanded
    ? "Tutup semua rincian"
    : "Buka semua rincian";
  elements.toggleDetails.disabled = expandableRows.length === 0 || state.loadingRoots.size > 0;
  elements.toggleDetails.hidden = hasActiveSearch();
}

function renderRows() {
  const records = visibleRows();
  const levelLabels = {
    skpd: "SKPD",
    program: "PROGRAM",
    kegiatan: "KEGIATAN",
    sub_kegiatan: "SUBKEGIATAN",
    paket: "PAKET/KELOMPOK",
  };
  const fragment = document.createDocumentFragment();
  for (const record of records) {
    const row = document.createElement("tr");
    row.className = `hierarchy-row hierarchy-${record.level}${record.has_children ? " has-children" : ""}`;
    if (record.has_children) {
      row.tabIndex = 0;
      row.setAttribute("aria-expanded", String(state.expandedRows.has(record.row_key)));
      row.setAttribute("aria-label", `${state.expandedRows.has(record.row_key) ? "Tutup" : "Buka"} rincian ${record.name}`);
      row.addEventListener("click", (event) => {
        if (event.target.closest(".hierarchy-toggle")) return;
        void toggleRow(record);
      });
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          void toggleRow(record);
        }
      });
    }
    appendCell(row, record.code);
    const hierarchyCell = document.createElement("td");
    hierarchyCell.className = "hierarchy-name";
    hierarchyCell.dataset.exportValue = record.name;
    if (record.has_children) {
      const toggle = document.createElement("button");
      toggle.className = "hierarchy-toggle";
      toggle.type = "button";
      toggle.disabled = state.loadingRoots.has(record.root_code);
      toggle.textContent = state.expandedRows.has(record.row_key) ? "−" : "+";
      toggle.setAttribute("aria-label", `${state.expandedRows.has(record.row_key) ? "Tutup" : "Buka"} rincian ${record.name}`);
      toggle.addEventListener("click", () => void toggleRow(record));
      hierarchyCell.append(toggle);
    }
    const levelLabel = document.createElement("span");
    levelLabel.className = "hierarchy-level-label";
    levelLabel.textContent = levelLabels[record.level] || record.level;
    const name = document.createElement("span");
    name.textContent = record.name;
    hierarchyCell.append(levelLabel, name);
    row.append(hierarchyCell);
    appendCell(row, record.pagu === null ? null : formatNumber(record.pagu), {
      numeric: true,
      exportType: record.pagu === null ? undefined : "number",
      exportValue: record.pagu === null ? undefined : record.pagu,
    });
    appendCell(row, record.sumber_dana);
    fragment.append(row);
  }
  elements.rows.replaceChildren(fragment);
  const hasRows = records.length > 0;
  elements.exportExcel.disabled = !hasRows;
  elements.exportPdf.disabled = !hasRows;
  updateDetailsButton();
}

async function loadDetailsForSkpd(skpdCodes) {
  const missingCodes = skpdCodes.filter((code) => !state.detailRows.has(code));
  if (missingCodes.length === 0) return;

  const requestId = state.requestId;
  const selectionId = state.selectionId;
  for (const code of missingCodes) state.loadingRoots.add(code);
  renderRows();

  try {
    const parameters = new URLSearchParams({
      year: String(state.year),
      tahapan_id: String(state.tahapanId),
    });
    for (const code of missingCodes) parameters.append("skpd_code", code);
    const result = await fetchJson(`/api/anggaran?${parameters.toString()}`);
    if (requestId !== state.requestId || selectionId !== state.selectionId) return;

    const visibleRows = withoutAccountRows(result.rows);
    const rowsByRoot = new Map(missingCodes.map((code) => [code, []]));
    for (const row of visibleRows) {
      if (row.level !== "skpd") rowsByRoot.get(row.root_code)?.push(row);
    }
    for (const [code, rows] of rowsByRoot) state.detailRows.set(code, rows);
    const loadedRoots = new Set(missingCodes);
    state.rootRows = state.rootRows.map((root) => (
      loadedRoots.has(root.root_code)
        ? {
          ...root,
          has_children: visibleRows.some((row) => row.parent_key === root.row_key),
        }
        : root
    ));
  } finally {
    for (const code of missingCodes) state.loadingRoots.delete(code);
    if (requestId === state.requestId && selectionId === state.selectionId) renderRows();
  }
}

async function toggleRow(record) {
  if (state.expandedRows.has(record.row_key)) {
    state.expandedRows.delete(record.row_key);
    renderRows();
    return;
  }
  if (hasActiveSearch()) {
    state.expandedRows.add(record.row_key);
    renderRows();
    return;
  }

  try {
    await loadDetailsForSkpd([record.root_code]);
    if (state.detailRows.has(record.root_code)) {
      state.expandedRows.add(record.row_key);
      renderRows();
    }
  } catch (error) {
    elements.yearStatus.textContent = error.message;
    elements.yearStatus.setAttribute("aria-live", "assertive");
  }
}

async function toggleAllDetails() {
  const expandableRows = [
    ...state.rootRows,
    ...Array.from(state.detailRows.values()).flat(),
  ].filter((row) => row.has_children);
  const allExpanded = expandableRows.length > 0
    && expandableRows.every((row) => state.expandedRows.has(row.row_key));
  if (allExpanded) {
    state.expandedRows.clear();
    state.displayLevel = "skpd";
    elements.levelFilter.value = "skpd";
    renderRows();
    return;
  }

  try {
    await loadDetailsForSkpd(state.rootRows.map((row) => row.root_code));
    for (const row of state.rootRows) {
      if (row.has_children) state.expandedRows.add(row.row_key);
    }
    for (const rows of state.detailRows.values()) {
      for (const row of rows) {
        if (row.has_children) state.expandedRows.add(row.row_key);
      }
    }
    state.displayLevel = "kelompok";
    elements.levelFilter.value = "kelompok";
    renderRows();
  } catch (error) {
    elements.yearStatus.textContent = error.message;
    elements.yearStatus.setAttribute("aria-live", "assertive");
  }
}

async function exportExcel() {
  const sheetMode = await window.chooseExportSheetMode();
  if (!sheetMode) return;
  const parameters = new URLSearchParams({
    year: String(state.year),
    tahapan_id: String(state.tahapanId),
    format: "excel",
    sheet_mode: sheetMode,
  });
  if (state.search) parameters.set("q", state.search);
  if (state.levelSearch) parameters.set("level_q", state.levelSearch);
  parameters.set("search_level", state.searchLevel);
  for (const option of elements.exportSubunits.selectedOptions) {
    parameters.append("skpd_code", option.value);
  }
  elements.exportExcel.disabled = true;
  elements.yearStatus.textContent = "Menyiapkan file Excel...";
  elements.yearStatus.classList.remove("is-error");
  try {
    const response = await fetch(`/api/anggaran?${parameters}`, {
      headers: {
        Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
    });
    if (!response.ok) {
      let detail = `Unduhan gagal (${response.status}).`;
      try {
        const body = await response.json();
        if (body.error) detail = body.error;
      } catch {
        // Keep the HTTP status as the actionable error if the response is not JSON.
      }
      throw new Error(detail);
    }

    const blob = await response.blob();
    if (blob.size === 0) throw new Error("File Excel yang diterima kosong.");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `anggaran-apbd-${state.year}.xlsx`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    elements.yearStatus.textContent = "File Excel berhasil diunduh.";
  } catch (error) {
    elements.yearStatus.textContent = error.message;
    elements.yearStatus.classList.add("is-error");
  } finally {
    elements.exportExcel.disabled = false;
  }
}

async function exportPdf() {
  if (state.year === null || state.tahapanId === null) return;
  const parameters = new URLSearchParams({
    year: String(state.year),
    tahapan_id: String(state.tahapanId),
    format: "all",
    search_level: state.searchLevel,
  });
  if (state.search) parameters.set("q", state.search);
  if (state.levelSearch) parameters.set("level_q", state.levelSearch);
  for (const option of elements.exportSubunits.selectedOptions) {
    parameters.append("skpd_code", option.value);
  }
  elements.exportPdf.disabled = true;
  const previousDisplayLevel = state.displayLevel;
  elements.yearStatus.textContent = "Menyiapkan data PDF...";
  try {
    const result = await fetchJson(`/api/anggaran?${parameters}`);
    state.rootRows = result.paginated
      ? result.rows
      : withoutAccountRows(result.rows);
    state.detailRows.clear();
    state.expandedRows.clear();
    state.displayLevel = "kelompok";
    elements.levelFilter.value = "kelompok";
    renderRows();
    window.print();
  } catch (error) {
    elements.yearStatus.textContent = error.message;
    elements.yearStatus.classList.add("is-error");
  } finally {
    state.displayLevel = previousDisplayLevel;
    elements.levelFilter.value = previousDisplayLevel;
    elements.exportPdf.disabled = false;
    void loadData();
  }
}

function renderSummary(summary) {
  const metrics = summary.metrics;
  const formatCurrency = (value) => `Rp ${formatNumber(value)}`;
  const formatPercentage = (value) =>
    `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value ?? 0)}%`;
  const countCards = [
    { name: "Sub Unit", value: metrics.sub_units },
    { name: "Urusan", value: metrics.urusan },
    { name: "Bidang Urusan", value: metrics.bidang_urusan },
    { name: "Program", value: metrics.program },
    { name: "Kegiatan", value: metrics.kegiatan },
    { name: "Sub Kegiatan", value: metrics.subactivities },
  ];
  const fragment = document.createDocumentFragment();
  const appendCard = (container, labelText, valueText, className = "") => {
    const card = document.createElement("div");
    card.className = `summary-card${className ? ` ${className}` : ""}`;
    const label = document.createElement("span");
    label.className = "summary-card-label";
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.className = "summary-card-value";
    value.textContent = String(valueText);
    card.append(label, value);
    container.append(card);
  };
  const countRow = document.createElement("div");
  countRow.className = "summary-count-row";
  for (const item of countCards) {
    appendCard(
      countRow,
      item.name,
      typeof item.value === "number" ? formatNumber(item.value) : item.value,
    );
  }
  fragment.append(countRow);

  const totalRow = document.createElement("div");
  totalRow.className = "summary-total-row";
  appendCard(totalRow, "Total Anggaran", formatCurrency(metrics.total_budget));
  appendCard(totalRow, "Realisasi Total", formatCurrency(metrics.realization_total));
  appendCard(totalRow, "Persentase Total", formatPercentage(metrics.percentage_total));
  fragment.append(totalRow);

  const periodRow = document.createElement("div");
  periodRow.className = "summary-period-row";
  for (const period of Object.values(metrics.period_metrics)) {
    const card = document.createElement("article");
    card.className = "summary-card summary-period-card";
    const label = document.createElement("span");
    label.className = "summary-card-label";
    label.textContent = period.label;
    const realization = document.createElement("strong");
    realization.className = "summary-card-value";
    realization.textContent = formatCurrency(period.realization);
    const percentage = document.createElement("span");
    percentage.className = "summary-period-percentage";
    percentage.textContent = formatPercentage(period.percentage);
    card.append(label, realization, percentage);
    periodRow.append(card);
  }
  fragment.append(periodRow);
  elements.summary.replaceChildren(fragment);
  elements.summaryPanel.hidden = false;

  const details = document.createDocumentFragment();
  const taggingTypes = summary.tagging_types;
  if (taggingTypes.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "Belum ada jenis tagging untuk tahun ini.";
    row.append(cell);
    details.append(row);
  }
  for (const type of taggingTypes) {
    const row = document.createElement("tr");
    for (const value of [
      type.name,
      formatNumber(type.sub_unit_count),
      formatNumber(type.subactivity_count),
      formatNumber(type.package_count),
      formatCurrency(type.budget),
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    for (const cell of row.querySelectorAll("td:nth-child(n + 2)")) {
      cell.classList.add("numeric-cell");
    }
    details.append(row);
  }
  elements.summaryDetails.replaceChildren(details);
  elements.taggingSummaryPanel.hidden = false;
}

function updatePagination(total) {
  const pageCount = Math.max(1, Math.ceil(total / state.pageSize));
  elements.pagination.hidden = hasActiveSearch() || total === 0;
  elements.pageIndicator.textContent = `Halaman ${state.page + 1} dari ${pageCount}`;
  elements.previousPage.disabled = state.page === 0;
  elements.nextPage.disabled = state.page + 1 >= pageCount;
}

async function loadData() {
  if (state.year === null || state.tahapanId === null) return;

  const requestId = ++state.requestId;
  setTableStatus("Memuat data anggaran...");
  elements.resultCount.textContent = "Memuat data...";
  elements.searchButton.disabled = true;
  elements.exportExcel.disabled = true;
  elements.exportPdf.disabled = true;
  elements.clearSearch.hidden = !hasActiveSearch();

  const parameters = new URLSearchParams({
    year: String(state.year),
    tahapan_id: String(state.tahapanId),
  });
  if (state.search) parameters.set("q", state.search);
  if (state.levelSearch) parameters.set("level_q", state.levelSearch);
  parameters.set("search_level", state.searchLevel);
  if (!hasActiveSearch()) {
    parameters.set("limit", String(state.pageSize));
    parameters.set("offset", String(state.page * state.pageSize));
  }

  try {
    const result = await fetchJson(`/api/anggaran?${parameters.toString()}`);
    if (requestId !== state.requestId) return;
    state.rootRows = result.paginated
      ? result.rows
      : withoutAccountRows(result.rows);
    state.detailRows.clear();
    state.expandedRows.clear();
    state.loadingRoots.clear();
    if (hasActiveSearch()) {
      for (const row of state.rootRows) {
        if (row.has_children) state.expandedRows.add(row.row_key);
      }
    }
    renderRows();
    setTableStatus(result.rows.length === 0 ? "Tidak ada data yang cocok." : "");
    elements.resultCount.textContent = hasActiveSearch()
      ? `${formatNumber(result.total)} rincian cocok untuk pencarian.`
      : `${formatNumber(result.total)} SKPD.`;
    updatePagination(result.total);
  } catch (error) {
    if (requestId !== state.requestId) return;
    elements.rows.replaceChildren();
    setTableStatus(error.message, true);
    elements.resultCount.textContent = "Data tidak dapat dimuat.";
    elements.pagination.hidden = true;
  } finally {
    if (requestId === state.requestId) elements.searchButton.disabled = false;
  }
}

async function loadTahapan(tahapanId) {
  if (state.year === null) return;

  const selectionId = ++state.selectionId;
  state.tahapanId = tahapanId;
  state.page = 0;
  state.search = "";
  state.levelSearch = "";
  elements.levelSearchInput.value = "";
  elements.searchInput.value = "";
  elements.dataContent.hidden = true;
  elements.summaryPanel.hidden = true;
  elements.taggingSummaryPanel.hidden = true;
  if (tahapanId === null) {
    elements.yearStatus.textContent = "Pilih tahapan untuk menampilkan data.";
    return;
  }
  const selectedTahapan = elements.tahapanSelect.selectedOptions[0]?.textContent;
  elements.yearStatus.textContent = `Memuat data tahapan ${selectedTahapan}...`;
  elements.summaryYear.textContent = `${state.year} · ${selectedTahapan}`;
  elements.dataContent.hidden = false;
  const summaryPromise = fetchJson(
    `/api/tagging-summary?year=${encodeURIComponent(state.year)}&tahapan_id=${encodeURIComponent(tahapanId)}`,
  )
    .then((summary) => {
      if (selectionId !== state.selectionId) return;
      renderSummary(summary);
      elements.yearStatus.textContent = `Data tahun ${state.year}, tahapan ${selectedTahapan} siap ditampilkan.`;
    })
    .catch((error) => {
      if (selectionId !== state.selectionId) return;
      elements.yearStatus.textContent = `Ringkasan tidak dapat dimuat: ${error.message}`;
      elements.yearStatus.setAttribute("aria-live", "assertive");
    });
  const dataPromise = loadData();
  await Promise.all([summaryPromise, dataPromise]);
}

async function loadYear(year) {
  const selectionId = ++state.selectionId;
  state.year = year;
  state.tahapanId = null;
  state.page = 0;
  state.search = "";
  state.levelSearch = "";
  elements.levelSearchInput.value = "";
  elements.searchInput.value = "";
  elements.dataContent.hidden = true;
  elements.summaryPanel.hidden = true;
  elements.taggingSummaryPanel.hidden = true;
  elements.tahapanSelect.replaceChildren(new Option("Memuat tahapan...", ""));
  elements.tahapanSelect.disabled = true;
  elements.exportSubunits.replaceChildren();
  elements.exportSubunits.disabled = true;
  if (year === null) {
    elements.yearStatus.textContent = "Pilih tahun untuk menampilkan data.";
    return;
  }

  elements.yearStatus.textContent = `Memuat tahapan tahun ${year}...`;
  try {
    const [result, subUnitResult] = await Promise.all([
      fetchJson(`/api/tahapan?year=${encodeURIComponent(year)}`),
      fetchJson(`/api/sub-units?year=${encodeURIComponent(year)}`),
    ]);
    if (selectionId !== state.selectionId) return;
    for (const subUnit of subUnitResult.sub_units) {
      elements.exportSubunits.add(new Option(`${subUnit.name} (${subUnit.code})`, subUnit.code));
    }
    elements.exportSubunits.disabled = subUnitResult.sub_units.length === 0;
    elements.tahapanSelect.replaceChildren(new Option("Pilih tahapan", ""));
    for (const tahapan of result.tahapan) {
      elements.tahapanSelect.add(new Option(tahapan.name, String(tahapan.id)));
    }
    elements.tahapanSelect.disabled = result.tahapan.length === 0;
    if (result.default_tahapan_id !== null) {
      elements.tahapanSelect.value = String(result.default_tahapan_id);
      await loadTahapan(result.default_tahapan_id);
    } else {
      elements.yearStatus.textContent = `Belum ada tahapan untuk tahun ${year}.`;
    }
  } catch (error) {
    if (selectionId !== state.selectionId) return;
    elements.tahapanSelect.replaceChildren(new Option("Tahapan tidak dapat dimuat", ""));
    elements.yearStatus.textContent = error.message;
    elements.yearStatus.setAttribute("aria-live", "assertive");
  }
}

async function loadYears() {
  try {
    const result = await fetchJson("/api/years");
    elements.yearSelect.replaceChildren(new Option("Pilih tahun", ""));
    for (const year of result.years) {
      elements.yearSelect.add(new Option(String(year), String(year)));
    }
    elements.yearSelect.disabled = result.years.length === 0;
    if (result.years.length > 0) {
      const currentYear = new Date().getFullYear();
      const defaultYear = result.years.includes(currentYear)
        ? currentYear
        : result.years[0];
      elements.yearSelect.value = String(defaultYear);
      await loadYear(defaultYear);
    } else {
      elements.yearStatus.textContent = "Belum ada data tahun yang tersedia.";
    }
  } catch (error) {
    elements.yearSelect.replaceChildren(new Option("Tahun tidak dapat dimuat", ""));
    elements.yearSelect.disabled = true;
    elements.yearStatus.textContent = error.message;
    elements.yearStatus.setAttribute("aria-live", "assertive");
  }
}

elements.yearSelect.addEventListener("change", () => {
  const value = elements.yearSelect.value;
  void loadYear(value === "" ? null : Number(value));
});

elements.tahapanSelect.addEventListener("change", () => {
  const value = elements.tahapanSelect.value;
  void loadTahapan(value === "" ? null : Number(value));
});

elements.toggleDetails.addEventListener("click", () => {
  void toggleAllDetails();
});
elements.levelFilter.addEventListener("change", async () => {
  state.displayLevel = elements.levelFilter.value;
  state.expandedRows.clear();
  if (hierarchyLevels[state.displayLevel] > 0) {
    try {
      await loadDetailsForSkpd(state.rootRows.map((row) => row.root_code));
      const expandableRows = [
        ...state.rootRows,
        ...Array.from(state.detailRows.values()).flat(),
      ];
      for (const row of expandableRows) {
        if (
          row.has_children
          && (hierarchyLevels[row.level] ?? 0) < hierarchyLevels[state.displayLevel]
        ) {
          state.expandedRows.add(row.row_key);
        }
      }
    } catch (error) {
      elements.yearStatus.textContent = error.message;
      elements.yearStatus.setAttribute("aria-live", "assertive");
    }
  }
  renderRows();
});

elements.exportExcel.addEventListener("click", exportExcel);
elements.exportPdf.addEventListener("click", exportPdf);

elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.searchLevel = elements.searchLevel.value;
  const searchValue = elements.searchInput.value.trim();
  if (state.searchLevel === "skpd") {
    state.search = "";
    state.levelSearch = searchValue;
  } else {
    state.search = searchValue;
    state.levelSearch = elements.levelSearchInput.value.trim();
  }
  state.page = 0;
  void loadData();
});

elements.clearSearch.addEventListener("click", () => {
  elements.searchInput.value = "";
  elements.levelSearchInput.value = "";
  state.search = "";
  state.levelSearch = "";
  state.page = 0;
  void loadData();
});

elements.searchLevel.addEventListener("change", () => {
  const selected = elements.searchLevel.selectedOptions[0];
  const isSkpd = elements.searchLevel.value === "skpd";
  elements.levelSearchWrap.hidden = isSkpd;
  elements.levelSearchLabel.textContent = `Cari ${selected.textContent}`;
  elements.searchInput.placeholder = isSkpd
    ? "Cari SKPD"
    : "Pencarian umum (opsional)";
  elements.searchInput.value = "";
  elements.levelSearchInput.value = "";
  state.search = "";
  state.levelSearch = "";
  state.searchLevel = elements.searchLevel.value;
  state.page = 0;
  void loadData();
});

elements.pageSize.addEventListener("change", () => {
  state.pageSize = Number(elements.pageSize.value);
  state.page = 0;
  void loadData();
});

elements.previousPage.addEventListener("click", () => {
  if (state.page === 0) return;
  state.page -= 1;
  void loadData();
});

elements.nextPage.addEventListener("click", () => {
  state.page += 1;
  void loadData();
});

void loadYears();
