"use strict";

const elements = {
  year: document.querySelector("#dynamic-year"),
  subUnit: document.querySelector("#dynamic-sub-unit"),
  levelFilter: document.querySelector("#dynamic-level-filter"),
  toggleAll: document.querySelector("#dynamic-toggle-all"),
  searchForm: document.querySelector("#dynamic-search-form"),
  searchInput: document.querySelector("#dynamic-search"),
  searchButton: document.querySelector("#dynamic-search-button"),
  clearSearch: document.querySelector("#dynamic-clear-search"),
  exportExcel: document.querySelector("#dynamic-export-excel"),
  exportPdf: document.querySelector("#dynamic-export-pdf"),
  status: document.querySelector("#dynamic-status"),
  count: document.querySelector("#dynamic-count"),
  head: document.querySelector("#dynamic-head"),
  rows: document.querySelector("#dynamic-rows"),
  pagination: document.querySelector("#dynamic-pagination"),
  pageIndicator: document.querySelector("#dynamic-page-indicator"),
  previous: document.querySelector("#dynamic-previous"),
  next: document.querySelector("#dynamic-next"),
};

const state = {
  year: null,
  requestId: 0,
  pageSize: 10,
  offset: 0,
  total: 0,
  search: "",
  showAll: false,
};

const levelIndent = {
  sub_unit: 0,
  program: 16,
  kegiatan: 32,
  sub_kegiatan: 48,
  paket: 64,
  rekening: 80,
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

function formatNumber(value) {
  return new Intl.NumberFormat("id-ID").format(value ?? 0);
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = value === null || value === undefined || value === ""
    ? "—"
    : String(value);
  row.append(cell);
}

function renderTable(result) {
  const header = document.createElement("tr");
  for (const label of [
    "Kode",
    "SKPD / Program / Kegiatan / Subkegiatan / Paket / Kelompok / Rekening",
    ...result.stages.map((stage) => stage.name),
    "Sumber Dana",
  ]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    header.append(cell);
  }
  elements.head.replaceChildren(header);

  const fragment = document.createDocumentFragment();
  const levelOrder = {
    sub_unit: 0,
    program: 1,
    kegiatan: 2,
    sub_kegiatan: 3,
    paket: 4,
    kelompok: 5,
    rekening: 6,
  };
  const selectedLevel = state.showAll
    ? "rekening"
    : elements.levelFilter.value;
  const maxLevel = levelOrder[selectedLevel] ?? 0;
  const visibleRows = result.rows.filter((item) =>
    (levelOrder[item.level] ?? 0) <= maxLevel,
  );
  for (const item of visibleRows) {
    const row = document.createElement("tr");
    row.className = `dynamic-budget-row dynamic-budget-${item.level}`;
    appendCell(row, item.code);
    const hierarchy = document.createElement("td");
    hierarchy.className = "dynamic-budget-name";
    hierarchy.style.paddingLeft = `${12 + (levelIndent[item.level] || 0)}px`;
    hierarchy.textContent = item.name;
    row.append(hierarchy);
    for (const stage of result.stages) {
      const amount = item.amounts[String(stage.id)];
      appendCell(
        row,
        amount === undefined ? "—" : formatNumber(amount),
        "numeric-cell",
      );
    }
    appendCell(row, item.source);
    fragment.append(row);
  }
  if (visibleRows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = result.stages.length + 3;
    cell.textContent = "Tidak ada data anggaran untuk filter ini.";
    row.append(cell);
    fragment.append(row);
  }
  elements.rows.replaceChildren(fragment);
  elements.toggleAll.textContent = state.showAll
    ? "Tutup semua rincian"
    : "Buka semua rincian";
  if (state.showAll) elements.levelFilter.value = "rekening";
}

async function loadData() {
  if (state.year === null) return;
  const requestId = ++state.requestId;
  const selectedSubUnit = elements.subUnit.value;
  const parameters = new URLSearchParams({
    year: String(state.year),
    limit: String(state.pageSize),
    offset: String(state.offset),
  });
  if (selectedSubUnit) parameters.set("sub_unit_id", selectedSubUnit);
  if (state.search) parameters.set("q", state.search);
  elements.subUnit.disabled = true;
  elements.rows.replaceChildren();
  elements.head.replaceChildren();
  elements.status.classList.remove("is-error");
  elements.count.textContent = "";
  elements.pagination.hidden = true;
  elements.previous.disabled = true;
  elements.next.disabled = true;
  elements.searchButton.disabled = true;
  elements.exportExcel.disabled = true;
  elements.exportPdf.disabled = true;
  elements.clearSearch.hidden = !state.search;
  elements.status.textContent = "Memuat perkembangan anggaran...";
  try {
    const result = await fetchJson(`/api/dinamisasi-anggaran?${parameters}`);
    if (requestId !== state.requestId) return;
    const currentSelection = selectedSubUnit
      && result.sub_units.some((unit) => String(unit.id) === selectedSubUnit)
      ? selectedSubUnit
      : "";
    elements.subUnit.replaceChildren(new Option("Semua Sub Unit", ""));
    for (const unit of result.sub_units) {
      elements.subUnit.add(
        new Option(`${unit.code} — ${unit.name}`, String(unit.id)),
      );
    }
    elements.subUnit.value = currentSelection;
    elements.subUnit.disabled = result.sub_units.length === 0;
    renderTable(result);
    state.total = result.total;
    const pageCount = Math.ceil(state.total / state.pageSize);
    elements.pagination.hidden = pageCount === 0;
    elements.pageIndicator.textContent = pageCount
      ? `Halaman ${Math.floor(state.offset / state.pageSize) + 1} dari ${pageCount}`
      : "";
    elements.previous.disabled = state.offset === 0;
    elements.next.disabled = state.offset + state.pageSize >= state.total;
    elements.exportExcel.disabled = state.total === 0;
    elements.exportPdf.disabled = state.total === 0;
    elements.count.textContent =
      `${formatNumber(state.total)} sub kegiatan · ${formatNumber(result.rows.length)} baris pada halaman ini`;
    elements.status.textContent =
      `Data tahun ${state.year} menampilkan pagu seluruh tahapan yang tersedia.`;
  } catch (error) {
    if (requestId !== state.requestId) return;
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
    elements.rows.replaceChildren();
    elements.subUnit.disabled = true;
    elements.pagination.hidden = true;
    elements.previous.disabled = true;
    elements.next.disabled = true;
    elements.exportExcel.disabled = true;
    elements.exportPdf.disabled = true;
  } finally {
    if (requestId === state.requestId) elements.searchButton.disabled = false;
  }
}

async function loadYear(year) {
  state.requestId += 1;
  state.year = year ? Number(year) : null;
  state.offset = 0;
  state.search = "";
  elements.searchInput.value = "";
  elements.clearSearch.hidden = true;
  elements.status.classList.remove("is-error");
  if (state.year === null) {
    elements.rows.replaceChildren();
    elements.head.replaceChildren();
    elements.count.textContent = "";
    elements.pagination.hidden = true;
    elements.subUnit.replaceChildren(new Option("Semua Sub Unit", ""));
    elements.subUnit.disabled = true;
    elements.status.textContent = "Pilih tahun untuk menampilkan data.";
    return;
  }
  await loadData();
}

async function initialize() {
  try {
    const result = await fetchJson("/api/years");
    elements.year.replaceChildren(new Option("Pilih tahun", ""));
    for (const year of result.years) {
      elements.year.add(new Option(String(year), String(year)));
    }
    elements.year.disabled = result.years.length === 0;
    if (result.years.length === 0) {
      elements.status.textContent = "Belum ada data tahun yang tersedia.";
      return;
    }
    const currentYear = new Date().getFullYear();
    const initialYear = result.years.includes(currentYear)
      ? currentYear
      : result.years[0];
    elements.year.value = String(initialYear);
    await loadYear(String(initialYear));
  } catch (error) {
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
}

elements.year.addEventListener("change", () => void loadYear(elements.year.value));
elements.levelFilter.addEventListener("change", () => {
  state.showAll = false;
  void loadData();
});
elements.toggleAll.addEventListener("click", () => {
  state.showAll = !state.showAll;
  if (!state.showAll) elements.levelFilter.value = "sub_unit";
  void loadData();
});
elements.subUnit.addEventListener("change", () => {
  state.offset = 0;
  void loadData();
});
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.searchInput.value.trim();
  state.offset = 0;
  void loadData();
});
elements.clearSearch.addEventListener("click", () => {
  elements.searchInput.value = "";
  state.search = "";
  state.offset = 0;
  void loadData();
});
elements.previous.addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.pageSize);
  void loadData();
});
elements.exportExcel.addEventListener("click", async () => {
  const sheetMode = await window.chooseExportSheetMode();
  if (!sheetMode) return;
  const parameters = new URLSearchParams({
    year: String(state.year),
    format: "excel",
    sheet_mode: sheetMode,
  });
  if (elements.subUnit.value) parameters.set("sub_unit_id", elements.subUnit.value);
  if (state.search) parameters.set("q", state.search);
  window.location.assign(`/api/dinamisasi-anggaran?${parameters}`);
});
elements.exportPdf.addEventListener("click", async () => {
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    elements.status.textContent = "Izinkan pop-up untuk mencetak dinamisasi anggaran.";
    elements.status.classList.add("is-error");
    return;
  }
  elements.exportPdf.disabled = true;
  elements.status.classList.remove("is-error");
  try {
    const parameters = new URLSearchParams({
      year: String(state.year),
      format: "all",
      level: state.showAll ? "rekening" : elements.levelFilter.value,
    });
    if (elements.subUnit.value) {
      parameters.set("sub_unit_id", elements.subUnit.value);
    }
    if (state.search) parameters.set("q", state.search);
    const result = await fetchJson(`/api/dinamisasi-anggaran?${parameters}`);
    const items = result.rows;
    const stages = result.stages;
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
    const columns = [
      "Kode",
      "SKPD / Program / Kegiatan / Subkegiatan / Paket / Kelompok / Rekening",
      ...stages.map((stage) => stage.name),
      "Sumber Dana",
    ];
    const body = items.map((item) =>
      `<tr><td>${escapeHtml(item.code)}</td><td style="padding-left:${12 + (levelIndent[item.level] || 0)}px">${escapeHtml(item.name)}</td>${stages.map((stage) =>
        `<td>${escapeHtml(formatNumber(item.amounts[String(stage.id)] ?? 0))}</td>`).join("")}<td>${escapeHtml(item.source)}</td></tr>`,
    ).join("");
    const tableHead = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
    const title = `Dinamisasi Anggaran ${state.year}`;
    printWindow.document.open();
    printWindow.document.write(
      `<!doctype html><html lang="id"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><style>body{font:10px Arial,sans-serif;color:#172b4d}h1{font-size:18px;margin:0 0 6px}.report-meta{margin:0 0 16px;color:#52627a;font-size:11px}table{width:100%;border-collapse:collapse;table-layout:auto}thead{display:table-header-group}th,td{border:1px solid #d5deea;padding:5px 7px;text-align:left;vertical-align:top}th{background:#eaf2fa;color:#233b5d;font-size:9px;text-transform:uppercase}td:nth-child(n+3){text-align:right;white-space:nowrap}tbody tr:nth-child(even){background:#f8fafc}@media print{@page{size:landscape;margin:10mm}tr{break-inside:avoid}body{margin:0}}</style></head><body><h1>${escapeHtml(title)}</h1><p class="report-meta">${formatNumber(items.length)} baris · Rincian hingga ${escapeHtml(elements.levelFilter.selectedOptions[0].textContent)}</p><table><thead><tr>${tableHead}</tr></thead><tbody>${body}</tbody></table></body></html>`,
    );
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  } catch (error) {
    printWindow.close();
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  } finally {
    elements.exportPdf.disabled = state.total === 0;
  }
});
elements.next.addEventListener("click", () => {
  state.offset += state.pageSize;
  void loadData();
});

void initialize();
