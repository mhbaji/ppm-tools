"use strict";

const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  uploadForm: document.querySelector("#realisasi-upload-form"),
  uploadYear: document.querySelector("#upload-year"),
  uploadPeriod: document.querySelector("#upload-period"),
  uploadFile: document.querySelector("#upload-file"),
  uploadSubmit: document.querySelector("#upload-submit"),
  uploadStatus: document.querySelector("#upload-status"),
  uploadsYear: document.querySelector("#uploads-year"),
  uploadsStatus: document.querySelector("#uploads-status"),
  uploadRows: document.querySelector("#upload-rows"),
  dataYear: document.querySelector("#data-year"),
  dataPeriod: document.querySelector("#data-period"),
  searchForm: document.querySelector("#data-search-form"),
  search: document.querySelector("#data-search"),
  export: document.querySelector("#data-export"),
  dataStatus: document.querySelector("#data-status"),
  dataCount: document.querySelector("#data-count"),
  dataRows: document.querySelector("#data-rows"),
  levelFilter: document.querySelector("#realisasi-level-filter"),
  toggleAll: document.querySelector("#realisasi-toggle-all"),
  pageSizeSelect: document.querySelector("#realisasi-page-size"),
  previous: document.querySelector("#previous-page"),
  next: document.querySelector("#next-page"),
  pageIndicator: document.querySelector("#page-indicator"),
};

const state = {
  csrfToken: "",
  page: 0,
  pageSize: 10,
  search: "",
  total: 0,
  requestId: 0,
  showDetails: true,
  currentRows: [],
};

async function fetchJson(url, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  if (options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = state.csrfToken;
  }
  const response = await fetch(url, { ...options, headers });
  let body = {};
  try {
    body = await response.json();
  } catch {
    if (response.ok) throw new Error("Respons server tidak valid.");
  }
  if (!response.ok) {
    if (response.status === 401) window.location.replace("/login");
    throw new Error(body.error || `Permintaan gagal (${response.status}).`);
  }
  return body;
}

function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
  element.classList.toggle("is-success", Boolean(message) && !isError);
}

function fillSelect(select, items, placeholder, valueKey, labelKey) {
  select.replaceChildren(new Option(placeholder, ""));
  for (const item of items) {
    select.add(new Option(String(item[labelKey]), String(item[valueKey])));
  }
  select.disabled = items.length === 0;
}

function selectedYear() {
  return Number(elements.dataYear.value);
}

function selectedPeriod() {
  return Number(elements.dataPeriod.value);
}

function displayNumber(value) {
  return value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value);
}

function appendTextCell(row, value, numeric = false) {
  const cell = document.createElement("td");
  if (numeric) cell.classList.add("numeric-cell");
  cell.textContent = value === null || value === undefined || value === ""
    ? "—"
    : String(value);
  row.append(cell);
}

function renderRows(rows) {
  const fragment = document.createDocumentFragment();
  if (rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 9;
    cell.textContent = "Tidak ada data untuk filter ini.";
    row.append(cell);
    fragment.append(row);
  }
  const groupedRows = new Map();
  for (const item of rows) {
    const key = item.subunit_code || item.subunit_name;
    if (!groupedRows.has(key)) groupedRows.set(key, []);
    groupedRows.get(key).push(item);
  }
  const selectedLevel = elements.levelFilter.value;
  for (const [key, items] of groupedRows) {
    const unitRow = document.createElement("tr");
    unitRow.className = "realisasi-unit-row";
    const unitCell = document.createElement("td");
    unitCell.colSpan = 9;
    unitCell.textContent = `${items[0].subunit_code || "—"} — ${items[0].subunit_name || "—"}`;
    unitRow.append(unitCell);
    fragment.append(unitRow);
    if (!state.showDetails || selectedLevel === "skpd") continue;
    for (const item of items) {
      const normalizedLevel = String(item.level || "").toLocaleLowerCase("id-ID").replace(/[_-]/g, " ");
      const matchesLevel = selectedLevel === "program"
        ? normalizedLevel === "program"
        : selectedLevel === "sub_kegiatan"
          ? normalizedLevel === "sub kegiatan"
          : true;
      if (!matchesLevel) continue;
      const row = document.createElement("tr");
      row.className = "realisasi-detail-row";
      appendTextCell(row, item.work_code || item.subunit_code);
      appendTextCell(row, `${item.subunit_name || "—"} / ${item.work_name || "—"}`);
      appendTextCell(row, item.indicator);
      appendTextCell(row, item.unit);
      appendTextCell(row, displayNumber(item.target), true);
      appendTextCell(row, displayNumber(item.achievement), true);
      appendTextCell(row, displayNumber(item.achievement_percentage), true);
      appendTextCell(row, displayNumber(item.budget), true);
      appendTextCell(row, displayNumber(item.realization), true);
      fragment.append(row);
    }
  }
  elements.dataRows.replaceChildren(fragment);
  elements.toggleAll.textContent = state.showDetails
    ? "Tutup semua rincian"
    : "Buka semua rincian";
}

async function loadUploads() {
  const year = elements.uploadsYear.value;
  if (!year) return;
  elements.uploadRows.replaceChildren();
  setStatus(elements.uploadsStatus, "Memuat riwayat...");
  try {
    const result = await fetchJson(
      `/api/admin/realisasi/uploads?year=${encodeURIComponent(year)}`,
    );
    const fragment = document.createDocumentFragment();
    if (result.uploads.length === 0) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 6;
      cell.textContent = "Belum ada file yang diunggah untuk tahun ini.";
      row.append(cell);
      fragment.append(row);
    }
    for (const item of result.uploads) {
      const row = document.createElement("tr");
      appendTextCell(row, item.filename);
      appendTextCell(row, item.uploaded_at);
      appendTextCell(row, item.year);
      appendTextCell(row, item.period);
      appendTextCell(row, item.imported_rows);
      const actionCell = document.createElement("td");
      const link = document.createElement("a");
      link.className = "button button-secondary";
      link.href = item.download_url;
      link.textContent = "Unduh";
      actionCell.append(link);
      row.append(actionCell);
      fragment.append(row);
    }
    elements.uploadRows.replaceChildren(fragment);
    setStatus(elements.uploadsStatus, "");
  } catch (error) {
    setStatus(elements.uploadsStatus, error.message, true);
  }
}

async function loadRows() {
  const year = elements.dataYear.value;
  const period = elements.dataPeriod.value;
  if (!year || !period) return;
  const requestId = ++state.requestId;
  const parameters = new URLSearchParams({
    year,
    period_id: period,
    q: state.search,
    limit: String(state.pageSize),
    offset: String(state.page * state.pageSize),
  });
  setStatus(elements.dataStatus, "Memuat data...");
  try {
    const result = await fetchJson(`/api/admin/realisasi?${parameters}`);
    if (requestId !== state.requestId) return;
    state.total = result.total;
    state.currentRows = result.rows;
    renderRows(result.rows);
    elements.dataCount.textContent = `${result.total.toLocaleString("id-ID")} baris data`;
    const pages = Math.ceil(result.total / state.pageSize);
    elements.pageIndicator.textContent = pages
      ? `Halaman ${state.page + 1} dari ${pages}`
      : "";
    elements.previous.disabled = state.page === 0;
    elements.next.disabled = state.page + 1 >= pages;
    setStatus(elements.dataStatus, "");
  } catch (error) {
    if (requestId !== state.requestId) return;
    setStatus(elements.dataStatus, error.message, true);
    state.currentRows = [];
    renderRows([]);
  }
}

async function exportExcel() {
  const year = elements.dataYear.value;
  const period = elements.dataPeriod.value;
  if (!year || !period) {
    setStatus(elements.dataStatus, "Pilih tahun dan periode sebelum mengekspor.", true);
    return;
  }
  const sheetMode = await window.chooseExportSheetMode();
  if (!sheetMode) return;
  elements.export.disabled = true;
  try {
    const rows = [];
    for (let offset = 0; offset < state.total; offset += 1000) {
      const parameters = new URLSearchParams({
        year,
        period_id: period,
        q: state.search,
        limit: "1000",
        offset: String(offset),
      });
      const result = await fetchJson(`/api/admin/realisasi?${parameters}`);
      rows.push(...result.rows);
    }
    const headers = [
      "Kode",
      "SKPD / Program / Sub Kegiatan",
      "Indikator",
      "Satuan",
      "Target",
      "Capaian",
      "Persentase Capaian",
      "Pagu",
      "Realisasi",
    ];
    const detailRows = rows.map((item) => [
      item.work_code || item.subunit_code,
      `${item.subunit_name || "—"} / ${item.work_name || "—"}`,
      item.indicator,
      item.unit,
      item.target,
      item.achievement,
      item.achievement_percentage,
      item.budget,
      item.realization,
    ]);
    const sheets = [];
    if (sheetMode === "single") {
      sheets.push({ name: "Realisasi", rows: [headers, ...detailRows] });
    } else {
      const groupedRows = new Map();
      rows.forEach((item, index) => {
        const unitName = item.subunit_name || "Tanpa Sub Unit";
        if (!groupedRows.has(unitName)) groupedRows.set(unitName, []);
        groupedRows.get(unitName).push(detailRows[index]);
      });
      for (const [unitName, unitRows] of groupedRows) {
        sheets.push({ name: unitName, rows: [headers, ...unitRows] });
      }
      if (sheets.length === 0) sheets.push({ name: "Realisasi", rows: [headers] });
    }
    window.downloadXlsx(`realization-${year}-period-${period}.xlsx`, sheets);
  } catch (error) {
    setStatus(elements.dataStatus, error.message, true);
  } finally {
    elements.export.disabled = state.total === 0;
  }
}

async function uploadFile(event) {
  event.preventDefault();
  if (!elements.uploadFile.files.length) return;
  const formData = new FormData();
  formData.append("file", elements.uploadFile.files[0]);
  formData.append("year", elements.uploadYear.value);
  formData.append("period_id", elements.uploadPeriod.value);
  elements.uploadSubmit.disabled = true;
  setStatus(elements.uploadStatus, "Mengimpor file...");
  try {
    const result = await fetchJson("/api/admin/realisasi/import", {
      method: "POST",
      body: formData,
    });
    const warningText = result.warnings.length
      ? ` ${result.warnings.length} peringatan: ${result.warnings.slice(0, 3).join(" ")}`
      : "";
    setStatus(
      elements.uploadStatus,
      `${result.imported_rows} baris diproses.${warningText}`,
      result.warnings.length > 0,
    );
    elements.uploadFile.value = "";
    elements.uploadsYear.value = String(result.year);
    elements.dataYear.value = String(result.year);
    elements.dataPeriod.value = String(result.period_id);
    state.page = 0;
    await Promise.all([loadUploads(), loadRows()]);
  } catch (error) {
    setStatus(elements.uploadStatus, error.message, true);
  } finally {
    elements.uploadSubmit.disabled = false;
  }
}

async function initialize() {
  try {
    const auth = await fetchJson("/api/auth/session");
    state.csrfToken = auth.csrf_token;
    if (!auth.authenticated) {
      window.location.replace("/login");
      return;
    }
    elements.identity.textContent = `Login sebagai ${auth.username}`;
    const [yearResult, periodResult] = await Promise.all([
      fetchJson("/api/admin/years"),
      fetchJson("/api/admin/catalog/periode"),
    ]);
    fillSelect(elements.uploadYear, yearResult.years, "Pilih tahun", "year", "year");
    fillSelect(elements.uploadsYear, yearResult.years, "Pilih tahun", "year", "year");
    fillSelect(elements.dataYear, yearResult.years, "Pilih tahun", "year", "year");
    const periods = periodResult.items.map((item) => ({
      id: item.id,
      name: item.name,
    }));
    fillSelect(elements.uploadPeriod, periods, "Pilih periode", "id", "name");
    fillSelect(elements.dataPeriod, periods, "Pilih periode", "id", "name");
    if (yearResult.years.length > 0) {
      const currentYear = new Date().getFullYear();
      const currentYearOption = yearResult.years.find(
        (item) => item.year === currentYear,
      );
      const year = currentYearOption?.year ?? yearResult.years[0].year;
      elements.uploadYear.value = String(year);
      elements.uploadsYear.value = String(year);
      elements.dataYear.value = String(year);
      if (periods.length > 0) {
        elements.uploadPeriod.value = String(periods[0].id);
        elements.dataPeriod.value = String(periods[0].id);
      }
      await Promise.all([loadUploads(), loadRows()]);
    }
  } catch (error) {
    setStatus(elements.uploadStatus, error.message, true);
  }
}

elements.uploadForm.addEventListener("submit", (event) => void uploadFile(event));
elements.uploadsYear.addEventListener("change", () => void loadUploads());
elements.dataYear.addEventListener("change", () => {
  state.page = 0;
  void loadRows();
});
elements.dataPeriod.addEventListener("change", () => {
  state.page = 0;
  void loadRows();
});
elements.levelFilter.addEventListener("change", () => {
  state.showDetails = true;
  renderRows(state.currentRows || []);
});
elements.toggleAll.addEventListener("click", () => {
  state.showDetails = !state.showDetails;
  renderRows(state.currentRows || []);
});
elements.pageSizeSelect.addEventListener("change", () => {
  state.pageSize = Number(elements.pageSizeSelect.value);
  state.page = 0;
  void loadRows();
});
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.search.value.trim();
  state.page = 0;
  void loadRows();
});
elements.export.addEventListener("click", exportExcel);
elements.previous.addEventListener("click", () => {
  if (state.page > 0) {
    state.page -= 1;
    void loadRows();
  }
});
elements.next.addEventListener("click", () => {
  if ((state.page + 1) * state.pageSize < state.total) {
    state.page += 1;
    void loadRows();
  }
});
elements.logout.addEventListener("click", async () => {
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  } catch (error) {
    setStatus(elements.uploadStatus, error.message, true);
  }
});

void initialize();
