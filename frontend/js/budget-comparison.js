"use strict";

const elements = {
  status: document.querySelector("#comparison-status"),
  selections: document.querySelector("#comparison-selections"),
  add: document.querySelector("#comparison-add"),
  submit: document.querySelector("#comparison-submit"),
  searchForm: document.querySelector("#comparison-search-form"),
  search: document.querySelector("#comparison-search"),
  searchButton: document.querySelector("#comparison-search-button"),
  clearSearch: document.querySelector("#comparison-clear-search"),
  exportExcel: document.querySelector("#comparison-export-excel"),
  exportPdf: document.querySelector("#comparison-export-pdf"),
  count: document.querySelector("#comparison-count"),
  tableStatus: document.querySelector("#comparison-table-status"),
  tableWrap: document.querySelector("#comparison-table-wrap"),
  head: document.querySelector("#comparison-head"),
  rows: document.querySelector("#comparison-rows"),
  pagination: document.querySelector("#comparison-pagination"),
  pageIndicator: document.querySelector("#comparison-page-indicator"),
  previous: document.querySelector("#comparison-previous"),
  next: document.querySelector("#comparison-next"),
  toggleAll: document.querySelector("#comparison-toggle-all"),
  levelFilter: document.querySelector("#comparison-level-filter"),
};

const state = {
  years: [],
  optionsByYear: new Map(),
  sources: [],
  submittedSources: [],
  search: "",
  pageSize: 10,
  offset: 0,
  requestId: 0,
  result: null,
  showAll: false,
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
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value ?? 0);
}

function formatCurrency(value) {
  return `Rp ${formatNumber(value)}`;
}

function optionsForYear(year) {
  if (year && year !== "*") return state.optionsByYear.get(year) || [];
  if (!year) return [];
  const options = new Map();
  for (const items of state.optionsByYear.values()) {
    for (const item of items) {
      const key = `${item.kind}:${item.label}`;
      if (!options.has(key)) {
        options.set(key, {
          value: `${item.kind}:*:${encodeURIComponent(item.name)}`,
          label: item.label,
          kind: item.kind,
          name: item.name,
          id: item.kind === "stage" ? item.name : "",
        });
      }
    }
  }
  return Array.from(options.values());
}

function defaultOptionForYear(year) {
  const options = optionsForYear(year);
  return options.find((option) => option.kind === "stage") || options[0];
}

function renderSelections() {
  elements.selections.replaceChildren();
  state.sources.forEach((source, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "comparison-selection";
    const yearLabel = document.createElement("label");
    yearLabel.className = "field-label";
    yearLabel.textContent = `Tahun perbandingan ${index + 1}`;
    const yearSelect = document.createElement("select");
    yearSelect.className = "select-control comparison-source-year";
    yearSelect.dataset.index = String(index);
    yearSelect.setAttribute("aria-label", `Tahun perbandingan ${index + 1}`);
    yearSelect.add(new Option("Pilih tahun", ""));
    for (const year of state.years) {
      yearSelect.add(new Option(String(year), String(year)));
    }
    yearSelect.value = source.year;
    const sourceLabel = document.createElement("label");
    sourceLabel.className = "field-label";
    sourceLabel.textContent = "Sumber perbandingan";
    const select = document.createElement("select");
    select.className = "select-control comparison-source";
    select.dataset.index = String(index);
    select.setAttribute("aria-label", `Tahapan atau Tagging Anggaran${index + 1}`);
    select.add(new Option("Pilih tahapan atau tagging", ""));
    const options = optionsForYear(source.year);
    for (const option of options) {
      select.add(new Option(option.label, option.value));
    }
    select.value = options.some((option) => option.value === source.value)
      ? source.value
      : "";
    select.disabled = options.length === 0;
    source.value = select.value;
    wrapper.append(yearLabel, yearSelect, sourceLabel, select);
    if (source.value.startsWith("tagging:")) {
      const stageLabel = document.createElement("label");
      stageLabel.className = "field-label";
      stageLabel.textContent = "Tahapan";
      const stageSelect = document.createElement("select");
      stageSelect.className = "select-control comparison-tagging-stage";
      stageSelect.dataset.index = String(index);
      stageSelect.id = `comparison-tagging-stage-${index}`;
      stageLabel.htmlFor = stageSelect.id;
      stageSelect.setAttribute("aria-label", `Tahapan untuk tagging ${index + 1}`);
      stageSelect.add(new Option("Pilih tahapan", ""));
      const stages = optionsForYear(source.year)
        .filter((option) => option.kind === "stage");
      for (const stage of stages) {
        stageSelect.add(new Option(
          stage.name,
          source.year === "*" ? stage.name : stage.id,
        ));
      }
      if (!stages.some((stage) =>
        (source.year === "*" ? stage.name : stage.id) === source.stageId
      )) {
        source.stageId = source.year === "*"
          ? stages[0]?.name || ""
          : stages[0]?.id || "";
      }
      stageSelect.value = source.stageId;
      stageSelect.disabled = stages.length === 0;
      wrapper.append(stageLabel, stageSelect);
    } else {
      source.stageId = "";
    }
    if (state.sources.length > 1) {
      const remove = document.createElement("button");
      remove.className = "button button-secondary comparison-remove";
      remove.type = "button";
      remove.dataset.index = String(index);
      remove.textContent = "Hapus";
      remove.setAttribute("aria-label", `Hapus Anggaran${index + 1}`);
      wrapper.append(remove);
    }
    elements.selections.append(wrapper);
  });
  elements.add.disabled = state.years.length === 0;
  elements.submit.disabled = !state.sources.length || state.sources.some((source) =>
    !source.value || (source.value.startsWith("tagging:") && !source.stageId)
  );
}

function setTableStatus(message, isError = false) {
  elements.tableStatus.textContent = message;
  elements.tableStatus.classList.toggle("is-error", isError);
  elements.tableStatus.hidden = !message;
  elements.tableWrap.hidden = Boolean(message);
}

function renderResult(result) {
  const header = document.createElement("tr");
  for (const label of [
    "Kode",
    "SKPD / Program / Kegiatan / Subkegiatan / Paket/Kelompok",
    ...result.columns,
  ]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    header.append(cell);
  }
  elements.head.replaceChildren(header);

  const hierarchyRows = [];
  function appendVisibleRows(nodes) {
    for (const node of nodes) {
      if (node.depth <= maxDepth) hierarchyRows.push(node);
      if (node.depth < maxDepth) appendVisibleRows(node.children);
    }
  }
  const levelDepth = {
    skpd: 0,
    program: 1,
    kegiatan: 2,
    sub_kegiatan: 3,
    kelompok: 4,
  };
  const maxDepth = state.showAll
    ? levelDepth.kelompok
    : levelDepth[elements.levelFilter.value] ?? 0;
  appendVisibleRows(result.rows);
  const fragment = document.createDocumentFragment();
  if (hierarchyRows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = result.columns.length + 2;
    cell.textContent = "Tidak ada data yang cocok untuk pilihan ini.";
    row.append(cell);
    fragment.append(row);
  }
  for (const item of hierarchyRows) {
    const row = document.createElement("tr");
    row.className = `comparison-level-${item.level}`;
    const code = document.createElement("td");
    code.textContent = item.code || "—";
    row.append(code);
    const hierarchy = document.createElement("td");
    hierarchy.className = "comparison-hierarchy-name";
    hierarchy.style.paddingLeft = `${12 + item.depth * 18}px`;
    hierarchy.textContent = item.name || "—";
    row.append(hierarchy);
    for (const amount of item.amounts) {
      const cell = document.createElement("td");
      cell.className = "numeric-cell";
      cell.textContent = formatCurrency(amount);
      row.append(cell);
    }
    fragment.append(row);
  }
  elements.rows.replaceChildren(fragment);
  elements.count.textContent = `${formatNumber(result.total)} Sub Unit`;
  const pageCount = Math.ceil(result.total / state.pageSize);
  elements.pagination.hidden = pageCount <= 1;
  elements.pageIndicator.textContent = pageCount
    ? `Halaman ${Math.floor(state.offset / state.pageSize) + 1} dari ${pageCount}`
    : "";
  elements.previous.disabled = state.offset === 0;
  elements.next.disabled = state.offset + state.pageSize >= result.total;
  elements.tableWrap.hidden = false;
  elements.exportExcel.disabled = result.total === 0;
  elements.exportPdf.disabled = result.total === 0;
  elements.toggleAll.disabled = result.total === 0;
  elements.toggleAll.textContent = state.showAll
    ? "Tutup semua rincian"
    : "Buka semua rincian";
}

function requestParameters() {
  const parameters = new URLSearchParams();
  for (const source of state.submittedSources) {
    if (source.value) parameters.append("selection", source.value);
    parameters.append(
      "tagging_tahapan",
      source.value.startsWith("tagging:") ? source.stageId : "",
    );
  }
  if (state.search) parameters.set("q", state.search);
  parameters.set("limit", String(state.pageSize));
  parameters.set("offset", String(state.offset));
  return parameters;
}

async function loadComparison() {
  if (
    state.submittedSources.length === 0
    || state.submittedSources.some((source) =>
      !source.value || (source.value.startsWith("tagging:") && !source.stageId))
  ) {
    state.requestId += 1;
    state.result = null;
    elements.exportExcel.disabled = true;
    elements.exportPdf.disabled = true;
    elements.toggleAll.disabled = true;
    elements.count.textContent = "";
    elements.pagination.hidden = true;
    elements.head.replaceChildren();
    elements.rows.replaceChildren();
    setTableStatus("Pilih tahun dan tahapan/tagging untuk setiap sumber perbandingan.");
    elements.status.textContent = "Pilih sumber perbandingan.";
    return;
  }
  const requestId = ++state.requestId;
  elements.searchButton.disabled = true;
  elements.clearSearch.hidden = !state.search;
  elements.exportExcel.disabled = true;
  elements.exportPdf.disabled = true;
  elements.count.textContent = "";
  elements.pagination.hidden = true;
  state.result = null;
  setTableStatus("Memuat perbandingan anggaran...");
  try {
    const result = await fetchJson(`/api/perbandingan-anggaran?${requestParameters()}`);
    if (requestId !== state.requestId) return;
    state.result = result;
    renderResult(result);
    setTableStatus("");
    elements.status.textContent = "Perbandingan anggaran siap ditampilkan.";
  } catch (error) {
    if (requestId !== state.requestId) return;
    setTableStatus(error.message, true);
    elements.status.textContent = "Perbandingan tidak dapat dimuat.";
  } finally {
    if (requestId === state.requestId) elements.searchButton.disabled = false;
  }
}

function markPendingComparison() {
  state.requestId += 1;
  state.submittedSources = [];
  state.result = null;
  state.showAll = false;
  elements.exportExcel.disabled = true;
  elements.exportPdf.disabled = true;
  elements.toggleAll.disabled = true;
  elements.count.textContent = "";
  elements.pagination.hidden = true;
  elements.head.replaceChildren();
  elements.rows.replaceChildren();
  elements.status.textContent = "Pilihan berubah. Klik Tampilkan perbandingan untuk memuat hasil.";
  setTableStatus("Terapkan pilihan tahun dan sumber untuk melihat hasil perbandingan.");
}

function submitComparison() {
  if (elements.submit.disabled) return;
  state.submittedSources = state.sources.map((source) => ({ ...source }));
  state.offset = 0;
  state.showAll = false;
  void loadComparison();
}

async function loadOptionsForYear(year) {
  const [stageResult, taggingResult] = await Promise.all([
    fetchJson(`/api/tahapan?year=${encodeURIComponent(year)}`),
    fetchJson(`/api/tagging-types?year=${encodeURIComponent(year)}`),
  ]);
  const options = [
    ...stageResult.tahapan.map((stage) => ({
      value: `stage:${year}:${stage.id}`,
      label: `Tahapan — ${stage.name}`,
      kind: "stage",
      name: stage.name,
      id: String(stage.id),
    })),
    ...taggingResult.tagging_types.map((tagging) => ({
      value: `tagging:${year}:${tagging.code}`,
      label: `Tagging — ${tagging.name}`,
      kind: "tagging",
      name: tagging.name,
    })),
  ];
  state.optionsByYear.set(String(year), options);
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

elements.selections.addEventListener("change", (event) => {
  const index = Number(event.target.dataset.index);
  if (event.target.matches(".comparison-source-year")) {
    const source = state.sources[index];
    source.year = event.target.value;
    source.value = defaultOptionForYear(source.year)?.value || "";
    source.stageId = optionsForYear(source.year)
      .find((option) => option.kind === "stage")?.id || "";
    renderSelections();
  } else if (event.target.matches(".comparison-tagging-stage")) {
    state.sources[index].stageId = event.target.value;
  } else if (event.target.matches(".comparison-source")) {
    state.sources[index].value = event.target.value;
    state.sources[index].stageId = optionsForYear(state.sources[index].year)
      .find((option) => option.kind === "stage")?.id || "";
    renderSelections();
  } else {
    return;
  }
  state.offset = 0;
  markPendingComparison();
});
elements.selections.addEventListener("click", (event) => {
  const button = event.target.closest(".comparison-remove");
  if (!button) return;
  state.sources.splice(Number(button.dataset.index), 1);
  state.offset = 0;
  renderSelections();
  markPendingComparison();
});
elements.add.addEventListener("click", () => {
  state.sources.push({ year: "", value: "", stageId: "" });
  state.offset = 0;
  renderSelections();
  markPendingComparison();
});
elements.submit.addEventListener("click", submitComparison);
elements.levelFilter.addEventListener("change", () => {
  state.showAll = false;
  if (state.result) renderResult(state.result);
});
elements.toggleAll.addEventListener("click", () => {
  state.showAll = !state.showAll;
  if (state.showAll) elements.levelFilter.value = "kelompok";
  else elements.levelFilter.value = "skpd";
  if (state.result) renderResult(state.result);
});
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.search.value.trim();
  state.offset = 0;
  void loadComparison();
});
elements.clearSearch.addEventListener("click", () => {
  elements.search.value = "";
  state.search = "";
  state.offset = 0;
  void loadComparison();
});
elements.previous.addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.pageSize);
  void loadComparison();
});
elements.next.addEventListener("click", () => {
  state.offset += state.pageSize;
  void loadComparison();
});
elements.exportExcel.addEventListener("click", async () => {
  const sheetMode = await window.chooseExportSheetMode();
  if (!sheetMode) return;
  elements.exportExcel.disabled = true;
  const parameters = requestParameters();
  parameters.set("format", "all");
  try {
    const result = await fetchJson(`/api/perbandingan-anggaran?${parameters}`);
    const headers = [
      "Kode",
      "SKPD / Program / Kegiatan / Subkegiatan / Paket/Kelompok",
      ...result.columns,
    ];
    const visibleRows = result.rows.filter((item) => item.depth <= 4);
    const rows = visibleRows.map((item) => [
      item.code,
      `${" ".repeat(item.depth * 2)}${item.name}`,
      ...item.amounts,
    ]);
    const sheets = [];
    if (sheetMode === "single") {
      sheets.push({ name: "Perbandingan Anggaran", rows: [headers, ...rows] });
    } else {
      const groupedRows = new Map();
      visibleRows.forEach((item, index) => {
        const unitName = item.sub_unit_name || "Tanpa Sub Unit";
        if (!groupedRows.has(unitName)) groupedRows.set(unitName, []);
        groupedRows.get(unitName).push(rows[index]);
      });
      for (const [unitName, unitRows] of groupedRows) {
        sheets.push({ name: unitName, rows: [headers, ...unitRows] });
      }
      if (sheets.length === 0) {
        sheets.push({ name: "Perbandingan Anggaran", rows: [headers] });
      }
    }
    window.downloadXlsx("budget-comparison.xlsx", sheets);
  } catch (error) {
    setTableStatus(error.message, true);
  } finally {
    elements.exportExcel.disabled = !state.result || state.result.total === 0;
  }
});
elements.exportPdf.addEventListener("click", async () => {
  if (!state.result) return;
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    setTableStatus("Izinkan pop-up untuk mencetak perbandingan anggaran.", true);
    return;
  }
  const result = state.result;
  const title = "Perbandingan Anggaran";
  const columns = [
    "Kode",
    "SKPD / Program / Kegiatan / Subkegiatan / Paket/Kelompok",
    ...result.columns,
  ];
  const headings = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  try {
    const parameters = requestParameters();
    parameters.set("format", "all");
    const fullResult = await fetchJson(`/api/perbandingan-anggaran?${parameters}`);
    const items = fullResult.rows.filter((item) => item.depth <= 4);
    const body = items.map((item) =>
      `<tr class="${item.has_children ? "comparison-export-parent" : ""}"><td>${escapeHtml(item.code)}</td><td style="padding-left:${8 + item.depth * 14}px">${escapeHtml(item.name)}</td>${item.amounts.map((amount) =>
        `<td>${escapeHtml(formatCurrency(amount))}</td>`).join("")}</tr>`,
    ).join("");
    printWindow.document.open();
    printWindow.document.write(
      `<!doctype html><html lang="id"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><style>body{font:10px Arial,sans-serif;color:#172b4d}h1{font-size:18px;margin:0 0 6px}.report-meta{margin:0 0 16px;color:#52627a;font-size:11px}table{width:100%;border-collapse:collapse;table-layout:auto}thead{display:table-header-group}th,td{border:1px solid #d5deea;padding:5px 7px;text-align:left;vertical-align:top}th{background:#eaf2fa;color:#233b5d;font-size:9px;text-transform:uppercase}td:nth-child(n+3){text-align:right;white-space:nowrap}tbody tr:nth-child(even){background:#f8fafc}.comparison-export-parent{background:#f0f6fc;font-weight:700}@media print{@page{size:landscape;margin:10mm}tr{break-inside:avoid}body{margin:0}}</style></head><body><h1>${escapeHtml(title)}</h1><p class="report-meta">${escapeHtml(result.year)} · ${formatNumber(items.length)} baris</p><table><thead><tr>${headings}</tr></thead><tbody>${body}</tbody></table></body></html>`,
    );
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  } catch (error) {
    printWindow.close();
    setTableStatus(error.message, true);
  }
});

async function initialize() {
  try {
    const result = await fetchJson("/api/years");
    if (result.years.length === 0) {
      setTableStatus("Belum ada data tahun yang tersedia.");
      return;
    }
    state.years = result.years;
    elements.status.textContent = "Memuat pilihan tahapan dan tagging...";
    await Promise.all(state.years.map((year) => loadOptionsForYear(year)));
    state.sources = Array.from(
      { length: 2 },
      () => ({ year: "", value: "", stageId: "" }),
    );
    renderSelections();
    setTableStatus("Pilih tahun dan tahapan/tagging untuk setiap sumber perbandingan.");
    elements.status.textContent = "Pilih sumber perbandingan.";
  } catch (error) {
    elements.status.textContent = error.message;
    setTableStatus(error.message, true);
  }
}

void initialize();
