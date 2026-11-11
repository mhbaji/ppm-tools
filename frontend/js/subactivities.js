"use strict";

const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  importForm: document.querySelector("#subactivity-import-form"),
  importYear: document.querySelector("#import-year"),
  importStage: document.querySelector("#import-stage"),
  importFile: document.querySelector("#import-file"),
  importSubmit: document.querySelector("#import-submit"),
  importStatus: document.querySelector("#import-status"),
  year: document.querySelector("#subactivity-year"),
  stage: document.querySelector("#subactivity-stage"),
  pageSize: document.querySelector("#subactivity-page-size"),
  summary: document.querySelector("#subactivity-summary"),
  status: document.querySelector("#subactivity-status"),
  rows: document.querySelector("#subactivity-rows"),
  previous: document.querySelector("#subactivity-previous"),
  next: document.querySelector("#subactivity-next"),
  pageIndicator: document.querySelector("#subactivity-page-indicator"),
  importHistory: document.querySelector("#import-history-rows"),
};

const state = {
  csrfToken: "",
  year: null,
  stageId: null,
  page: 0,
  pageSize: Number(elements.pageSize.value),
  total: 0,
  roots: [],
  details: new Map(),
  expanded: new Set(),
  requestId: 0,
};
let reloadUploadedFiles = async () => {};

async function fetchJson(url, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.body instanceof FormData ? {} : options.body ? { "Content-Type": "application/json" } : {}),
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

function setStatus(element, message, kind = "") {
  element.textContent = message;
  element.classList.toggle("is-error", kind === "error");
  element.classList.toggle("is-success", kind === "success");
}

function formatNumber(value) {
  return new Intl.NumberFormat("id-ID").format(value ?? 0);
}

function renderSummary(summary) {
  const labels = [
    ["SKPD", summary.skpd],
    ["Program", summary.program],
    ["Kegiatan", summary.kegiatan],
    ["Sub Kegiatan", summary.sub_kegiatan],
  ];
  const fragment = document.createDocumentFragment();
  for (const [label, value] of labels) {
    const card = document.createElement("div");
    card.className = "subactivity-summary-card";
    const title = document.createElement("span");
    title.textContent = label;
    const count = document.createElement("strong");
    count.textContent = formatNumber(value);
    card.append(title, count);
    fragment.append(card);
  }
  elements.summary.replaceChildren(fragment);
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = value === null || value === undefined || value === ""
    ? "—"
    : String(value);
  row.append(cell);
}

function renderRows() {
  const records = [];
  const childrenByParent = new Map();
  for (const details of state.details.values()) {
    for (const record of details) {
      const children = childrenByParent.get(record.parent_key) || [];
      children.push(record);
      childrenByParent.set(record.parent_key, children);
    }
  }

  function appendVisible(record) {
    records.push(record);
    if (!state.expanded.has(record.row_key)) return;
    for (const child of childrenByParent.get(record.row_key) || []) {
      appendVisible(child);
    }
  }
  for (const root of state.roots) appendVisible(root);

  const labels = {
    skpd: "SKPD",
    program: "PROGRAM",
    kegiatan: "KEGIATAN",
    sub_kegiatan: "SUBKEGIATAN",
    paket: "PAKET/KELOMPOK",
    rekening: "REKENING",
  };
  const fragment = document.createDocumentFragment();
  for (const record of records) {
    const row = document.createElement("tr");
    row.className = `hierarchy-row hierarchy-${record.level}${record.has_children ? " has-children" : ""}`;
    if (record.has_children) {
      row.tabIndex = 0;
      row.setAttribute("aria-expanded", String(state.expanded.has(record.row_key)));
      row.addEventListener("click", () => void toggleRow(record));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          void toggleRow(record);
        }
      });
    }
    appendCell(row, record.code);
    const nameCell = document.createElement("td");
    nameCell.className = "hierarchy-name";
    if (record.has_children) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "hierarchy-toggle";
      toggle.textContent = state.expanded.has(record.row_key) ? "−" : "+";
      toggle.setAttribute("aria-label", `Buka atau tutup rincian ${record.name}`);
      toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        void toggleRow(record);
      });
      nameCell.append(toggle);
    }
    const label = document.createElement("span");
    label.className = "hierarchy-level-label";
    label.textContent = labels[record.level] || record.level;
    const name = document.createElement("span");
    name.textContent = record.name;
    nameCell.append(label, name);
    row.append(nameCell);
    appendCell(row, formatNumber(record.pagu), "numeric-cell");
    appendCell(row, record.sumber_dana);
    fragment.append(row);
  }
  elements.rows.replaceChildren(fragment);
}

async function toggleRow(record) {
  if (!state.expanded.has(record.row_key)) {
    if (!state.details.has(record.root_code)) {
      const requestId = state.requestId;
      setStatus(elements.status, `Memuat rincian ${record.name}...`);
      try {
        const parameters = new URLSearchParams({
          year: String(state.year),
          tahapan_id: String(state.stageId),
          skpd_code: record.root_code,
        });
        const result = await fetchJson(`/api/anggaran?${parameters.toString()}`);
        if (requestId !== state.requestId) return;
        state.details.set(
          record.root_code,
          result.rows.filter((row) => row.level !== "skpd"),
        );
        setStatus(elements.status, `${formatNumber(state.total)} SKPD.`);
      } catch (error) {
        setStatus(elements.status, error.message, "error");
        return;
      }
    }
    state.expanded.add(record.row_key);
  } else {
    state.expanded.delete(record.row_key);
  }
  renderRows();
}

function updatePagination() {
  const pages = Math.ceil(state.total / state.pageSize);
  elements.pageIndicator.textContent = state.total
    ? `Halaman ${state.page + 1} dari ${pages}`
    : "";
  elements.previous.disabled = state.page === 0;
  elements.next.disabled = (state.page + 1) * state.pageSize >= state.total;
}

async function loadData() {
  if (state.year === null || state.stageId === null) return;
  const requestId = ++state.requestId;
  const params = new URLSearchParams({
    year: String(state.year),
    tahapan_id: String(state.stageId),
    limit: String(state.pageSize),
    offset: String(state.page * state.pageSize),
  });
  setStatus(elements.status, "Memuat data sub kegiatan...");
  elements.rows.replaceChildren();
  try {
    const [data, summary] = await Promise.all([
      fetchJson(`/api/anggaran?${params.toString()}`),
      fetchJson(`/api/admin/sub-kegiatan/summary?year=${state.year}&tahapan_id=${state.stageId}`),
    ]);
    if (requestId !== state.requestId) return;
    state.roots = data.rows;
    state.total = data.total;
    state.details.clear();
    state.expanded.clear();
    renderSummary(summary);
    renderRows();
    setStatus(elements.status, `${formatNumber(state.total)} SKPD.`);
    updatePagination();
  } catch (error) {
    if (requestId !== state.requestId) return;
    setStatus(elements.status, error.message, "error");
  }
}

async function loadYear(year) {
  state.year = year ? Number(year) : null;
  state.stageId = null;
  state.page = 0;
  state.roots = [];
  state.details.clear();
  state.expanded.clear();
  elements.rows.replaceChildren();
  elements.summary.replaceChildren();
  elements.stage.replaceChildren(new Option("Memuat tahapan...", ""));
  elements.stage.disabled = true;
  if (state.year === null) {
    setStatus(elements.status, "Pilih tahun dan tahapan untuk menampilkan data.");
    return;
  }
  try {
    const result = await fetchJson(`/api/tahapan?year=${state.year}`);
    elements.stage.replaceChildren(new Option("Pilih Tahapan", ""));
    for (const stage of result.tahapan) {
      elements.stage.add(new Option(stage.name, String(stage.id)));
    }
    elements.stage.disabled = result.tahapan.length === 0;
    if (result.default_tahapan_id !== null) {
      state.stageId = result.default_tahapan_id;
      elements.stage.value = String(state.stageId);
      await loadData();
    } else {
      setStatus(elements.status, "Belum ada tahapan untuk tahun tersebut.");
    }
  } catch (error) {
    elements.stage.replaceChildren(new Option("Tahapan tidak dapat dimuat", ""));
    setStatus(elements.status, error.message, "error");
  }
}

async function loadImportStages(year) {
  elements.importStage.replaceChildren(new Option("Memuat tahapan...", ""));
  elements.importStage.disabled = true;
  if (!year) return;
  const result = await fetchJson(
    `/api/admin/tahapan?year=${encodeURIComponent(year)}`,
  );
  elements.importStage.replaceChildren(new Option("Pilih Tahapan", ""));
  for (const stage of result.tahapan) {
    elements.importStage.add(
      new Option(`${stage.code} — ${stage.name}`, String(stage.id)),
    );
  }
  elements.importStage.disabled = result.tahapan.length === 0;
  if (result.tahapan.length > 0) {
    elements.importStage.value = String(result.tahapan[0].id);
  }
}

async function loadImportHistory(year) {
  elements.importHistory.replaceChildren();
  if (!year) return;
  const result = await fetchJson(
    `/api/admin/sub-kegiatan/imports?year=${encodeURIComponent(year)}`,
  );
  const fragment = document.createDocumentFragment();
  if (result.imports.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "Belum ada data untuk tahun ini.";
    row.append(cell);
    fragment.append(row);
  }
  result.imports.forEach((item, index) => {
    const row = document.createElement("tr");
    for (const value of [
      index + 1,
      item.year,
      `${item.code} — ${item.name}`,
      item.updated_at,
    ]) {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      row.append(cell);
    }
    const actionCell = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-danger";
    button.textContent = "Hapus";
    button.addEventListener("click", () => void deleteImport(item, button));
    actionCell.append(button);
    row.append(actionCell);
    fragment.append(row);
  });
  elements.importHistory.replaceChildren(fragment);
}

async function deleteImport(item, button) {
  if (!window.confirm(
    `Hapus seluruh data anggaran tahun ${item.year}, tahapan "${item.name}"?`,
  )) return;
  button.disabled = true;
  try {
    await fetchJson(
      `/api/admin/sub-kegiatan/imports/${item.tahapan_id}?year=${item.year}`,
      { method: "DELETE" },
    );
    await Promise.all([
      loadImportHistory(String(item.year)),
      loadYear(String(item.year)),
    ]);
    setStatus(elements.importStatus, "Data anggaran berhasil dihapus.", "success");
  } catch (error) {
    setStatus(elements.importStatus, error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function loadYears() {
  const result = await fetchJson("/api/years");
  const years = result.years;
  for (const select of [elements.year, elements.importYear]) {
    select.replaceChildren(new Option("Pilih Tahun", ""));
    for (const year of years) select.add(new Option(String(year), String(year)));
    select.disabled = years.length === 0;
  }
  const currentYear = new Date().getFullYear();
  const selectedYear = years.includes(currentYear) ? currentYear : years[0];
  if (selectedYear) {
    elements.year.value = String(selectedYear);
    elements.importYear.value = String(selectedYear);
    await Promise.all([
      loadYear(String(selectedYear)),
      loadImportStages(String(selectedYear)),
      loadImportHistory(String(selectedYear)),
    ]);
  } else if (years.length === 0) {
    setStatus(elements.status, "Belum ada data tahun yang tersedia.");
  }
}

async function importWorkbook(event) {
  event.preventDefault();
  const file = elements.importFile.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("year", elements.importYear.value);
  formData.append("tahapan_id", elements.importStage.value);
  elements.importSubmit.disabled = true;
  setStatus(elements.importStatus, "Mengunggah file...");
  try {
    const result = await fetchJson("/api/admin/sub-kegiatan/import", {
      method: "POST",
      body: formData,
    });
    setStatus(
      elements.importStatus,
      `${formatNumber(result.imported)} baris diimpor ke tahapan "${result.tahapan_name}".`,
      "success",
    );
    elements.importForm.reset();
    const year = String(result.year);
    if (![...elements.year.options].some((option) => option.value === year)) {
      for (const select of [elements.year, elements.importYear]) {
        select.add(new Option(year, year));
      }
    }
    elements.importYear.value = year;
    elements.year.value = year;
    await loadImportStages(year);
    elements.importStage.value = String(result.tahapan_id);
    await Promise.all([
      loadYear(year),
      loadImportHistory(year),
      reloadUploadedFiles(),
    ]);
  } catch (error) {
    setStatus(elements.importStatus, error.message, "error");
  } finally {
    elements.importSubmit.disabled = false;
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
    reloadUploadedFiles = window.initAdminUploadList({
      kind: "sub_kegiatan",
      csrfToken: () => state.csrfToken,
      search: "#uploaded-files-search",
      pageSize: "#uploaded-files-page-size",
      rows: "#uploaded-files-rows",
      status: "#uploaded-files-status",
      previous: "#uploaded-files-previous",
      next: "#uploaded-files-next",
      pageIndicator: "#uploaded-files-page-indicator",
    });
    await loadYears();
  } catch (error) {
    setStatus(elements.status, error.message, "error");
  }
}

elements.year.addEventListener("change", () => {
  const year = elements.year.value;
  void Promise.all([loadYear(year), loadImportHistory(year)]).catch((error) => {
    setStatus(elements.status, error.message, "error");
  });
});
elements.importYear.addEventListener("change", () => {
  void Promise.all([
    loadImportStages(elements.importYear.value),
    loadImportHistory(elements.importYear.value),
  ]).catch((error) => setStatus(elements.importStatus, error.message, "error"));
});
elements.stage.addEventListener("change", () => {
  state.stageId = elements.stage.value ? Number(elements.stage.value) : null;
  state.page = 0;
  void loadData();
});
elements.pageSize.addEventListener("change", () => {
  state.pageSize = Number(elements.pageSize.value);
  state.page = 0;
  void loadData();
});
elements.previous.addEventListener("click", () => {
  if (state.page === 0) return;
  state.page -= 1;
  void loadData();
});
elements.next.addEventListener("click", () => {
  if ((state.page + 1) * state.pageSize >= state.total) return;
  state.page += 1;
  void loadData();
});
elements.importForm.addEventListener("submit", (event) => void importWorkbook(event));
elements.logout.addEventListener("click", async () => {
  elements.logout.disabled = true;
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  } catch (error) {
    elements.logout.disabled = false;
    setStatus(elements.status, error.message, "error");
  }
});

void initialize();
