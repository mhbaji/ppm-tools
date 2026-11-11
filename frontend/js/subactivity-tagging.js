"use strict";

const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  year: document.querySelector("#admin-year"),
  taggingTypeFilter: document.querySelector("#admin-tagging-type"),
  scope: document.querySelector("#admin-tagging-scope"),
  pageSize: document.querySelector("#admin-page-size"),
  importForm: document.querySelector("#tagging-import-form"),
  importYear: document.querySelector("#tagging-import-year"),
  importType: document.querySelector("#tagging-import-type"),
  importFile: document.querySelector("#tagging-import-file"),
  importSubmit: document.querySelector("#tagging-import-submit"),
  importStatus: document.querySelector("#tagging-import-status"),
  searchForm: document.querySelector("#admin-search-form"),
  search: document.querySelector("#admin-search"),
  status: document.querySelector("#admin-status"),
  list: document.querySelector("#tagging-list"),
  previous: document.querySelector("#previous-page"),
  next: document.querySelector("#next-page"),
  pageIndicator: document.querySelector("#page-indicator"),
  exportExcel: document.querySelector("#export-tagging-excel"),
  exportPdf: document.querySelector("#export-tagging-pdf"),
};

const state = {
  csrfToken: "",
  year: null,
  stageId: null,
  offset: 0,
  total: 0,
  pageSize: Number(elements.pageSize.value),
  search: "",
  taggingTypeCode: "",
  scope: elements.scope.value,
  taggingTypes: [],
};
let reloadUploadedFiles = async () => {};

async function fetchJson(url, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.body && !(options.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : {}),
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

function setStatus(message, kind = "") {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", kind === "error");
  elements.status.classList.toggle("is-success", kind === "success");
}

function makeTaggingItem(subactivity) {
  const item = document.createElement("article");
  item.className = "tagging-item";
  item.dataset.subUnitId = String(subactivity.sub_unit_id);
  item.dataset.subActivityId = String(subactivity.sub_kegiatan_id);
  item.dataset.packageId = subactivity.paket_kelompok_id === null
    ? ""
    : String(subactivity.paket_kelompok_id);

  const description = document.createElement("div");
  const skpd = document.createElement("span");
  skpd.className = "tagging-item-skpd";
  skpd.textContent = subactivity.sub_unit_name;
  const name = document.createElement("h3");
  name.className = "tagging-item-name";
  name.textContent = `${subactivity.sub_kegiatan_code} — ${subactivity.sub_kegiatan_name}`;
  if (state.scope === "paket_kelompok") {
    const packageName = document.createElement("span");
    packageName.className = "tagging-item-package";
    packageName.textContent = subactivity.paket_kelompok_name;
    description.append(skpd, name, packageName);
  } else {
    description.append(skpd, name);
  }

  const options = document.createElement("div");
  options.className = "tagging-options";
  for (const taggingType of state.taggingTypes) {
    const label = document.createElement("label");
    label.className = "tagging-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = taggingType.code;
    checkbox.checked = subactivity.tagging_codes.includes(String(taggingType.code));
    const text = document.createElement("span");
    text.textContent = taggingType.name;
    label.append(checkbox, text);
    options.append(label);
  }

  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "button button-primary tagging-save";
  saveButton.textContent = "Simpan";
  saveButton.addEventListener("click", () => void saveTagging(item, saveButton));

  const itemStatus = document.createElement("p");
  itemStatus.className = "item-status";
  itemStatus.setAttribute("role", "status");
  item.append(description, options, saveButton, itemStatus);
  return item;
}

async function saveTagging(item, button) {
  const itemStatus = item.querySelector(".item-status");
  const taggingCodes = Array.from(
    item.querySelectorAll(".tagging-option input:checked"),
    (checkbox) => checkbox.value,
  );
  button.disabled = true;
  itemStatus.textContent = "Menyimpan...";
  itemStatus.classList.remove("is-error", "is-success");
  try {
    await fetchJson("/api/admin/tagging-sub-kegiatan", {
      method: "PUT",
      body: JSON.stringify({
        year: state.year,
        scope: state.scope,
        sub_unit_id: Number(item.dataset.subUnitId),
        sub_kegiatan_id: Number(item.dataset.subActivityId),
        paket_kelompok_id: item.dataset.packageId
          ? Number(item.dataset.packageId)
          : null,
        tagging_codes: taggingCodes,
      }),
    });
    itemStatus.textContent = "Perubahan tersimpan.";
    itemStatus.classList.add("is-success");
  } catch (error) {
    itemStatus.textContent = error.message;
    itemStatus.classList.add("is-error");
  } finally {
    button.disabled = false;
  }
  if (state.taggingTypeCode) await loadTagging();
}

async function loadTagging() {
  if (state.year === null || state.stageId === null) return;
  const parameters = new URLSearchParams({
    year: String(state.year),
    tahapan_id: String(state.stageId),
    scope: state.scope,
    limit: String(state.pageSize),
    offset: String(state.offset),
  });
  if (state.search) parameters.set("q", state.search);
  if (state.taggingTypeCode) parameters.set("tagging_code", state.taggingTypeCode);
  elements.list.replaceChildren();
  elements.previous.disabled = true;
  elements.next.disabled = true;
  elements.exportExcel.disabled = true;
  elements.exportPdf.disabled = true;
  setStatus("Memuat data tagging...");

  try {
    const result = await fetchJson(`/api/admin/tagging-sub-kegiatan?${parameters.toString()}`);
    state.total = result.total;
    state.taggingTypes = result.tagging_types;
    const availableCodes = new Set(
      result.tagging_types.map((taggingType) => String(taggingType.code)),
    );
    if (state.taggingTypeCode && !availableCodes.has(state.taggingTypeCode)) {
      state.taggingTypeCode = "";
    }
    elements.taggingTypeFilter.replaceChildren(new Option("Semua jenis tagging", ""));
    elements.importType.replaceChildren(new Option("Pilih jenis tagging", ""));
    for (const taggingType of result.tagging_types) {
      elements.taggingTypeFilter.add(
        new Option(taggingType.name, String(taggingType.code)),
      );
      elements.importType.add(
        new Option(taggingType.name, String(taggingType.code)),
      );
    }
    elements.taggingTypeFilter.disabled = result.tagging_types.length === 0;
    elements.importType.disabled = result.tagging_types.length === 0;
    elements.taggingTypeFilter.value = state.taggingTypeCode;
    if (state.taggingTypeCode && !elements.importType.value) {
      elements.importType.value = state.taggingTypeCode;
    }
    elements.importYear.value = String(state.year);
    const fragment = document.createDocumentFragment();
    for (const subactivity of result.items) {
      fragment.append(makeTaggingItem(subactivity));
    }
    elements.list.replaceChildren(fragment);

    if (state.total === 0) {
      setStatus("Tidak ada subkegiatan yang cocok.");
    } else {
      const firstItem = state.offset + 1;
      const lastItem = Math.min(state.offset + result.items.length, state.total);
      const itemLabel = state.scope === "paket_kelompok"
        ? "Paket/Kelompok"
        : "Sub Kegiatan";
      setStatus(`${state.total} ${itemLabel}. Menampilkan ${firstItem}–${lastItem}.`);
    }
    elements.pageIndicator.textContent = state.total === 0
      ? ""
      : `Halaman ${Math.floor(state.offset / state.pageSize) + 1} dari ${Math.ceil(state.total / state.pageSize)}`;
    elements.previous.disabled = state.offset === 0;
    elements.next.disabled = state.offset + state.pageSize >= state.total;
    elements.exportExcel.disabled = state.total === 0;
    elements.exportPdf.disabled = state.total === 0;
  } catch (error) {
    setStatus(error.message, "error");
    elements.pageIndicator.textContent = "";
  }
}

function taggingExportParameters() {
  const parameters = new URLSearchParams({
    year: String(state.year),
    tahapan_id: String(state.stageId),
    scope: state.scope,
  });
  if (state.search) parameters.set("q", state.search);
  if (state.taggingTypeCode) parameters.set("tagging_code", state.taggingTypeCode);
  return parameters;
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

async function printTagging() {
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    setStatus("Izinkan pop-up untuk mencetak daftar tagging.", "error");
    return;
  }
  elements.exportPdf.disabled = true;
  try {
    const items = [];
    for (let offset = 0; offset < state.total; offset += 200) {
      const parameters = taggingExportParameters();
      parameters.set("limit", "200");
      parameters.set("offset", String(offset));
      const result = await fetchJson(`/api/admin/tagging-sub-kegiatan?${parameters}`);
      items.push(...result.items);
    }
    const packageColumn = state.scope === "paket_kelompok"
      ? "<th>Paket/Kelompok</th>"
      : "";
    const rows = items.map((item, index) => {
      const taggingNames = state.taggingTypes
        .filter((type) => item.tagging_codes.includes(String(type.code)))
        .map((type) => type.name)
        .join(", ");
      return `<tr><td>${index + 1}</td><td>${escapeHtml(item.sub_unit_name)}</td><td>${escapeHtml(item.sub_kegiatan_code)}</td><td>${escapeHtml(item.sub_kegiatan_name)}</td>${state.scope === "paket_kelompok" ? `<td>${escapeHtml(item.paket_kelompok_name)}</td>` : ""}<td>${escapeHtml(taggingNames || "—")}</td></tr>`;
    }).join("");
    printWindow.document.open();
    printWindow.document.write(
      `<!doctype html><html lang="id"><head><meta charset="utf-8"><title>Tagging ${state.year}</title><style>body{font:12px Arial,sans-serif;color:#172b4d}h1{font-size:20px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #bbb;padding:6px;text-align:left}th{background:#edf6ff}@media print{body{margin:12mm}}</style></head><body><h1>Tagging Sub Kegiatan — ${state.year}</h1><p>${items.length} data</p><table><thead><tr><th>No</th><th>Perangkat Daerah</th><th>Kode Sub Kegiatan</th><th>Sub Kegiatan</th>${packageColumn}<th>Jenis Tagging</th></tr></thead><tbody>${rows}</tbody></table></body></html>`,
    );
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  } catch (error) {
    printWindow.close();
    setStatus(error.message, "error");
  } finally {
    elements.exportPdf.disabled = state.total === 0;
  }
}

async function downloadTaggingExcel() {
  const sheetMode = await window.chooseExportSheetMode();
  if (!sheetMode) return;
  elements.exportExcel.disabled = true;
  try {
    const items = [];
    for (let offset = 0; offset < state.total; offset += 500) {
      const parameters = taggingExportParameters();
      parameters.set("limit", "500");
      parameters.set("offset", String(offset));
      const result = await fetchJson(
        `/api/admin/tagging-sub-kegiatan?${parameters.toString()}`,
      );
      items.push(...result.items);
    }
    const headers = [
      "No",
      "Kode Sub Unit",
      "Perangkat Daerah",
      "Kode Sub Kegiatan",
      "Sub Kegiatan",
    ];
    if (state.scope === "paket_kelompok") headers.push("Paket/Kelompok");
    headers.push("Jenis Tagging");
    const rows = items.map((item, index) => {
      const row = [
        index + 1,
        item.sub_unit_code,
        item.skpd_name || item.sub_unit_name,
        item.sub_kegiatan_code,
        item.sub_kegiatan_name,
      ];
      if (state.scope === "paket_kelompok") {
        row.push(item.paket_kelompok_name);
      }
      row.push(
        state.taggingTypes
          .filter((type) => item.tagging_codes.includes(String(type.code)))
          .map((type) => type.name)
          .join(", "),
      );
      return row;
    });
    const sheets = [];
    if (sheetMode === "single") {
      sheets.push({
        name: "Tagging",
        rows: [headers, ...rows],
      });
    } else {
      const groupedRows = new Map();
      for (const [index, item] of items.entries()) {
        const name = item.sub_unit_name || item.sub_unit_code || "Tanpa Sub Unit";
        const row = rows[index];
        if (!groupedRows.has(name)) groupedRows.set(name, []);
        groupedRows.get(name).push(row);
      }
      for (const [name, unitRows] of groupedRows) {
        sheets.push({ name, rows: [headers, ...unitRows] });
      }
      if (sheets.length === 0) sheets.push({ name: "Tagging", rows: [headers] });
    }
    window.downloadXlsx(`tagging-${state.scope}-${state.year}.xlsx`, sheets);
    setStatus("File Excel berhasil diunduh.", "success");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    elements.exportExcel.disabled = state.total === 0;
  }
}

async function loadDefaultTahapan(year) {
  state.year = year === "" ? null : Number(year);
  state.stageId = null;
  state.taggingTypeCode = "";
  state.offset = 0;
  elements.taggingTypeFilter.replaceChildren(new Option("Semua jenis tagging", ""));
  elements.taggingTypeFilter.disabled = true;
  if (state.year === null) {
    elements.list.replaceChildren();
    setStatus("Pilih tahun untuk mengelola tagging.");
    return;
  }
  try {
    const result = await fetchJson(`/api/tahapan?year=${encodeURIComponent(state.year)}`);
    if (result.default_tahapan_id !== null) {
      state.stageId = result.default_tahapan_id;
      await loadTagging();
    } else {
      setStatus("Belum ada tahapan untuk tahun tersebut.");
    }
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function initializeAdmin() {
  try {
    const auth = await fetchJson("/api/auth/session");
    state.csrfToken = auth.csrf_token;
    if (!auth.authenticated) {
      window.location.replace("/login");
      return;
    }
    elements.identity.textContent = `Login sebagai ${auth.username}`;
    reloadUploadedFiles = window.initAdminUploadList({
      kind: "tagging_sub_kegiatan",
      csrfToken: () => state.csrfToken,
      search: "#uploaded-tagging-files-search",
      pageSize: "#uploaded-tagging-files-page-size",
      rows: "#uploaded-tagging-files-rows",
      status: "#uploaded-tagging-files-status",
      previous: "#uploaded-tagging-files-previous",
      next: "#uploaded-tagging-files-next",
      pageIndicator: "#uploaded-tagging-files-page-indicator",
    });

    const years = await fetchJson("/api/years");
    elements.year.replaceChildren(new Option("Pilih tahun", ""));
    elements.importYear.replaceChildren(new Option("Pilih tahun", ""));
    for (const year of years.years) {
      elements.year.add(new Option(String(year), String(year)));
      elements.importYear.add(new Option(String(year), String(year)));
    }
    elements.importYear.disabled = years.years.length === 0;
    elements.year.disabled = years.years.length === 0;
    if (years.years.length > 0) {
      const currentYear = new Date().getFullYear();
      if (years.years.includes(currentYear)) {
        elements.year.value = String(currentYear);
        elements.importYear.value = String(currentYear);
        await loadDefaultTahapan(String(currentYear));
      } else {
        setStatus("Pilih tahun untuk mengelola tagging.");
      }
    } else {
      setStatus("Belum ada data tahun yang tersedia.");
    }
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function importTaggingWorkbook(event) {
  event.preventDefault();
  const file = elements.importFile.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("year", elements.importYear.value);
  formData.append("tagging_code", elements.importType.value);
  formData.append("scope", "both");
  elements.importSubmit.disabled = true;
  elements.importStatus.textContent = "Mengunggah file...";
  elements.importStatus.classList.remove("is-error", "is-success");
  try {
    const result = await fetchJson("/api/admin/tagging-sub-kegiatan/import", {
      method: "POST",
      body: formData,
    });
    const warningSummary = result.warnings.length
      ? ` ${result.warnings.length} peringatan: ${result.warnings.slice(0, 3).join(" ")}`
      : "";
    elements.importStatus.textContent =
      `${result.imported} penandaan ditambahkan/diperbarui, ${result.ignored} duplikat diabaikan.${warningSummary}`;
    elements.importStatus.classList.toggle("is-error", result.warnings.length > 0);
    elements.importStatus.classList.toggle("is-success", result.warnings.length === 0);
    elements.importFile.value = "";
    await Promise.all([loadTagging(), reloadUploadedFiles()]);
  } catch (error) {
    elements.importStatus.textContent = error.message;
    elements.importStatus.classList.remove("is-success");
    elements.importStatus.classList.add("is-error");
  } finally {
    elements.importSubmit.disabled = false;
  }
}

elements.year.addEventListener("change", () => {
  elements.importYear.value = elements.year.value;
  void loadDefaultTahapan(elements.year.value);
});

elements.taggingTypeFilter.addEventListener("change", () => {
  state.taggingTypeCode = elements.taggingTypeFilter.value;
  state.offset = 0;
  void loadTagging();
});

elements.scope.addEventListener("change", () => {
  state.scope = elements.scope.value;
  state.offset = 0;
  void loadTagging();
});

elements.pageSize.addEventListener("change", () => {
  state.pageSize = Number(elements.pageSize.value);
  state.offset = 0;
  void loadTagging();
});

elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.search.value.trim();
  state.offset = 0;
  void loadTagging();
});

elements.importForm.addEventListener("submit", (event) => {
  void importTaggingWorkbook(event);
});

elements.previous.addEventListener("click", () => {
  if (state.offset === 0) return;
  state.offset = Math.max(0, state.offset - state.pageSize);
  void loadTagging();
});

elements.next.addEventListener("click", () => {
  if (state.offset + state.pageSize >= state.total) return;
  state.offset += state.pageSize;
  void loadTagging();
});
elements.exportExcel.addEventListener("click", downloadTaggingExcel);
elements.exportPdf.addEventListener("click", () => void printTagging());

elements.logout.addEventListener("click", async () => {
  elements.logout.disabled = true;
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  } catch (error) {
    elements.logout.disabled = false;
    setStatus(error.message, "error");
  }
});

void initializeAdmin();
