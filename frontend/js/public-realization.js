"use strict";

const elements = {
  year: document.querySelector("#realization-year"),
  period: document.querySelector("#realization-period"),
  subunits: document.querySelector("#realization-subunits"),
  subunitsHelp: document.querySelector("#realization-subunits-help"),
  status: document.querySelector("#realization-status"),
  summary: document.querySelector("#realization-summary"),
  count: document.querySelector("#realization-count"),
  searchForm: document.querySelector("#realization-search-form"),
  search: document.querySelector("#realization-search"),
  clearSearch: document.querySelector("#realization-clear-search"),
  rows: document.querySelector("#realization-rows"),
  pageSize: document.querySelector("#realization-page-size"),
  pageIndicator: document.querySelector("#realization-page-indicator"),
  previous: document.querySelector("#realization-previous"),
  next: document.querySelector("#realization-next"),
  excel: document.querySelector("#realization-export-excel"),
  pdf: document.querySelector("#realization-export-pdf"),
};

const state = {
  year: null,
  periodId: null,
  page: 0,
  pageSize: 10,
  search: "",
  sort: "subunit",
  direction: "asc",
  total: 0,
  requestId: 0,
  yearRequestId: 0,
  summary: null,
};

const columns = [
  ["subunit_name", "Subunit"],
  ["level", "Level"],
  ["work_name", "Pekerjaan"],
  ["indicator", "Indikator"],
  ["unit", "Satuan"],
  ["target", "Target"],
  ["achievement", "Capaian"],
  ["achievement_percentage", "Persentase"],
  ["budget", "Pagu"],
  ["realization", "Realisasi"],
];

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  let result = {};
  try {
    result = await response.json();
  } catch {
    if (response.ok) throw new Error("Respons server tidak valid.");
  }
  if (!response.ok) throw new Error(result.error || `Permintaan gagal (${response.status}).`);
  return result;
}

function formatNumber(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value);
}

function formatCurrency(value) {
  if (value === null || value === undefined) return "—";
  return `Rp ${formatNumber(value)}`;
}

function updateSubunitHelp() {
  const count = elements.subunits.selectedOptions.length;
  elements.subunitsHelp.textContent = count
    ? `${count} subunit dipilih. Gunakan Ctrl (Windows/Linux) atau Command (Mac) untuk memilih beberapa.`
    : "Tidak ada pilihan berarti semua subunit. Gunakan Ctrl (Windows/Linux) atau Command (Mac) untuk memilih beberapa.";
}

function parameters(includePaging = true) {
  const result = new URLSearchParams({
    year: String(state.year),
    period_id: String(state.periodId),
    sort: state.sort,
    direction: state.direction,
  });
  if (state.search) result.set("q", state.search);
  for (const option of elements.subunits.selectedOptions) {
    result.append("skpd_code", option.value);
  }
  if (includePaging) {
    result.set("limit", String(state.pageSize));
    result.set("offset", String(state.page * state.pageSize));
  }
  return result;
}

function renderSummary(summary) {
  const entries = [
    ["Total realisasi sub kegiatan", formatCurrency(summary.realization_total)],
    ["Jumlah capaian indikator", formatNumber(summary.achievement_count)],
    ["Rata-rata persentase capaian", `${formatNumber(summary.achievement_percentage_average)}%`],
  ];
  const fragment = document.createDocumentFragment();
  for (const [label, value] of entries) {
    const card = document.createElement("article");
    card.className = "summary-card";
    const title = document.createElement("span");
    title.className = "summary-card-label";
    title.textContent = label;
    const amount = document.createElement("strong");
    amount.className = "summary-card-value";
    amount.textContent = value;
    card.append(title, amount);
    fragment.append(card);
  }
  elements.summary.replaceChildren(fragment);
}

function renderRows(rows) {
  const fragment = document.createDocumentFragment();
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = columns.length;
    cell.textContent = "Tidak ada data untuk filter ini.";
    row.append(cell);
    fragment.append(row);
  }
  for (const item of rows) {
    const row = document.createElement("tr");
    for (const [key] of columns) {
      const cell = document.createElement("td");
      if (["target", "achievement", "achievement_percentage", "budget", "realization"].includes(key)) {
        cell.classList.add("numeric-cell");
      }
      const value = item[key];
      cell.textContent = key === "budget" || key === "realization"
        ? formatCurrency(value)
        : key === "achievement_percentage"
          ? value === null ? "—" : `${formatNumber(value)}%`
          : key === "target" || key === "achievement"
            ? formatNumber(value)
            : value || "—";
      row.append(cell);
    }
    fragment.append(row);
  }
  elements.rows.replaceChildren(fragment);
}

async function loadRows() {
  const requestId = ++state.requestId;
  if (state.year === null || state.periodId === null) {
    elements.rows.replaceChildren();
    elements.summary.replaceChildren();
    elements.count.textContent = "";
    elements.pageIndicator.textContent = "";
    elements.excel.disabled = true;
    elements.pdf.disabled = true;
    return;
  }
  elements.status.textContent = "Memuat rincian realisasi...";
  elements.excel.disabled = true;
  elements.pdf.disabled = true;
  try {
    const result = await fetchJson(`/api/realisasi?${parameters()}`);
    if (requestId !== state.requestId) return;
    state.total = result.total;
    state.summary = result.summary;
    renderSummary(result.summary);
    renderRows(result.rows);
    const pages = Math.ceil(result.total / state.pageSize);
    elements.count.textContent = `${formatNumber(result.total)} data`;
    elements.pageIndicator.textContent = pages
      ? `Halaman ${state.page + 1} dari ${pages}`
      : "";
    elements.previous.disabled = state.page === 0;
    elements.next.disabled = (state.page + 1) * state.pageSize >= result.total;
    elements.excel.disabled = result.total === 0;
    elements.pdf.disabled = result.total === 0;
    elements.status.textContent = result.total
      ? `Data realisasi tahun ${state.year} siap ditampilkan.`
      : "Tidak ada data realisasi untuk filter ini.";
  } catch (error) {
    if (requestId !== state.requestId) return;
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
    renderRows([]);
    elements.previous.disabled = true;
    elements.next.disabled = true;
  }
}

async function loadYear(year) {
  const yearRequestId = ++state.yearRequestId;
  state.requestId += 1;
  state.year = year ? Number(year) : null;
  state.periodId = null;
  state.page = 0;
  elements.period.replaceChildren(new Option("Memuat periode...", ""));
  elements.period.disabled = true;
  elements.subunits.replaceChildren();
  elements.subunits.disabled = true;
  updateSubunitHelp();
  if (state.year === null) return;
  try {
    const [periodResult, unitResult] = await Promise.all([
      fetchJson(`/api/realisasi/periods?year=${encodeURIComponent(state.year)}`),
      fetchJson(`/api/sub-units?year=${encodeURIComponent(state.year)}`),
    ]);
    if (yearRequestId !== state.yearRequestId) return;
    elements.period.replaceChildren(new Option("Pilih periode", ""));
    for (const period of periodResult.periods) {
      elements.period.add(new Option(period.name, String(period.id)));
    }
    elements.period.disabled = periodResult.periods.length === 0;
    for (const unit of unitResult.sub_units) {
      elements.subunits.add(new Option(`${unit.name} (${unit.code})`, unit.code));
    }
    elements.subunits.disabled = unitResult.sub_units.length === 0;
    updateSubunitHelp();
    if (periodResult.periods.length) {
      state.periodId = periodResult.periods[0].id;
      elements.period.value = String(state.periodId);
      await loadRows();
    } else {
      elements.status.textContent = "Belum ada periode realisasi untuk tahun tersebut.";
      elements.rows.replaceChildren();
    }
  } catch (error) {
    if (yearRequestId !== state.yearRequestId) return;
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
}

async function loadAllForExport() {
  const allRows = [];
  let exportSummary = null;
  let exportTotal = 0;
  const exportFilters = parameters(false);
  const expectedTotal = state.total;
  for (let offset = 0; offset < expectedTotal; offset += 100) {
    const query = new URLSearchParams(exportFilters);
    query.set("limit", "100");
    query.set("offset", String(offset));
    const result = await fetchJson(`/api/realisasi?${query}`);
    exportSummary = result.summary;
    exportTotal = result.total;
    allRows.push(...result.rows);
  }
  if (!exportSummary) {
    const query = new URLSearchParams(exportFilters);
    query.set("limit", "1");
    query.set("offset", "0");
    const result = await fetchJson(`/api/realisasi?${query}`);
    exportSummary = result.summary;
    exportTotal = result.total;
  }
  while (allRows.length < exportTotal) {
    const query = new URLSearchParams(exportFilters);
    query.set("limit", "100");
    query.set("offset", String(allRows.length));
    const result = await fetchJson(`/api/realisasi?${query}`);
    if (!result.rows.length) break;
    allRows.push(...result.rows);
  }
  return { rows: allRows, summary: exportSummary };
}

async function exportExcel() {
  elements.excel.disabled = true;
  elements.status.textContent = "Menyiapkan file Excel...";
  try {
    const query = parameters(false);
    query.set("format", "excel");
    const response = await fetch(`/api/realisasi?${query}`, {
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
    if (!blob.size) throw new Error("File Excel yang diterima kosong.");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `realisasi-${state.year}.xlsx`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    elements.status.textContent = "File Excel berhasil diunduh.";
  } catch (error) {
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  } finally {
    elements.excel.disabled = state.total === 0;
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

async function exportPdf() {
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    elements.status.textContent = "Izinkan pop-up untuk mencetak data realisasi.";
    elements.status.classList.add("is-error");
    return;
  }
  elements.pdf.disabled = true;
  try {
    const { rows, summary } = await loadAllForExport();
    const tableRows = rows.map((item) => `<tr>${columns.map(([key]) => {
      const value = ["budget", "realization"].includes(key)
        ? formatCurrency(item[key])
        : key === "achievement_percentage"
          ? item[key] === null ? "—" : `${formatNumber(item[key])}%`
          : key === "target" || key === "achievement"
            ? formatNumber(item[key])
            : item[key];
      return `<td>${escapeHtml(value)}</td>`;
    }).join("")}</tr>`).join("");
    const summaryHtml = [
      ["Total realisasi sub kegiatan", formatCurrency(summary.realization_total)],
      ["Jumlah capaian indikator", formatNumber(summary.achievement_count)],
      ["Rata-rata persentase capaian", `${formatNumber(summary.achievement_percentage_average)}%`],
    ].map(([label, value]) => `<p><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</p>`).join("");
    const headerHtml = columns.map(([, label]) => `<th>${escapeHtml(label)}</th>`).join("");
    printWindow.document.open();
    printWindow.document.write(
      `<!doctype html><html lang="id"><head><meta charset="utf-8"><title>Realisasi ${state.year}</title><style>body{font:11px Arial,sans-serif;color:#172b4d}table{width:100%;border-collapse:collapse}th,td{border:1px solid #bbb;padding:5px;text-align:left}th{background:#edf6ff}@media print{body{margin:10mm}}</style></head><body><h1>Realisasi dan Capaian ${state.year}</h1><p>Periode: ${escapeHtml(elements.period.selectedOptions[0]?.textContent || "")}</p>${summaryHtml}<table><thead><tr>${headerHtml}</tr></thead><tbody>${tableRows}</tbody></table></body></html>`,
    );
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  } catch (error) {
    printWindow.close();
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  } finally {
    elements.pdf.disabled = state.total === 0;
  }
}

elements.year.addEventListener("change", () => void loadYear(elements.year.value));
elements.period.addEventListener("change", () => {
  state.periodId = elements.period.value ? Number(elements.period.value) : null;
  state.page = 0;
  void loadRows();
});
elements.subunits.addEventListener("change", () => {
  updateSubunitHelp();
  state.page = 0;
  void loadRows();
});
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.search.value.trim();
  state.page = 0;
  elements.clearSearch.hidden = !state.search;
  void loadRows();
});
elements.clearSearch.addEventListener("click", () => {
  elements.search.value = "";
  state.search = "";
  state.page = 0;
  elements.clearSearch.hidden = true;
  void loadRows();
});
elements.pageSize.addEventListener("change", () => {
  state.pageSize = Number(elements.pageSize.value);
  state.page = 0;
  void loadRows();
});
elements.previous.addEventListener("click", () => {
  if (state.page > 0) {
    state.page -= 1;
    void loadRows();
  }
});
elements.next.addEventListener("click", () => {
  state.page += 1;
  void loadRows();
});
for (const button of document.querySelectorAll(".sort-button")) {
  button.addEventListener("click", () => {
    const key = button.dataset.sort;
    state.direction = state.sort === key && state.direction === "asc" ? "desc" : "asc";
    state.sort = key;
    state.page = 0;
    void loadRows();
  });
}
elements.excel.addEventListener("click", () => void exportExcel());
elements.pdf.addEventListener("click", () => void exportPdf());
updateSubunitHelp();

async function initialize() {
  try {
    const result = await fetchJson("/api/years");
    elements.year.replaceChildren(new Option("Pilih tahun", ""));
    for (const year of result.years) elements.year.add(new Option(String(year), String(year)));
    elements.year.disabled = result.years.length === 0;
    const initialYear = result.years.includes(new Date().getFullYear())
      ? new Date().getFullYear()
      : result.years[0];
    if (initialYear !== undefined) {
      elements.year.value = String(initialYear);
      await loadYear(initialYear);
    } else {
      elements.status.textContent = "Belum ada data tahun yang tersedia.";
    }
  } catch (error) {
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
}

void initialize();
