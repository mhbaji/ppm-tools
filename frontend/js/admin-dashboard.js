"use strict";

const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  year: document.querySelector("#dashboard-year"),
  stage: document.querySelector("#dashboard-stage"),
  status: document.querySelector("#dashboard-status"),
  summary: document.querySelector("#dashboard-summary"),
  taggingTypes: document.querySelector("#dashboard-tagging-types"),
};

const state = { csrfToken: "", year: null, stageId: null, requestId: 0 };

async function fetchJson(url, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = state.csrfToken;
  }
  const response = await fetch(url, { ...options, headers });
  let result = {};
  try {
    result = await response.json();
  } catch {
    if (response.ok) throw new Error("Respons server tidak valid.");
  }
  if (!response.ok) {
    if (response.status === 401) window.location.replace("/login");
    throw new Error(result.error || `Permintaan gagal (${response.status}).`);
  }
  return result;
}

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", isError);
}

function formatNumber(value) {
  return new Intl.NumberFormat("id-ID").format(value ?? 0);
}

function renderSummary(summary) {
  const metrics = [
    ["Jumlah Sub Unit ditagging", summary.sub_unit_count],
    ["Jumlah sub kegiatan ditagging", summary.total_subactivities],
    ["Total sub kegiatan APBD", summary.total_apbd_subactivities],
    [
      "Jenis tagging digunakan",
      summary.tagging_types.filter((item) => item.count > 0).length,
    ],
    ["Total Dana Anggaran", `Rp ${formatNumber(summary.total_budget)}`],
    [
      "Realisasi Anggaran",
      `Rp ${formatNumber(summary.metrics.realization_total)}`,
    ],
    [
      "Persentase Realisasi Anggaran",
      `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(
        summary.metrics.percentage_total,
      )}%`,
    ],
  ];
  const fragment = document.createDocumentFragment();
  for (const [label, value] of metrics) {
    const card = document.createElement("article");
    card.className = "dashboard-metric";
    const title = document.createElement("span");
    title.textContent = label;
    const count = document.createElement("strong");
    count.textContent = typeof value === "number" ? formatNumber(value) : value;
    card.append(title, count);
    fragment.append(card);
  }
  elements.summary.replaceChildren(fragment);

  const rows = document.createDocumentFragment();
  if (summary.tagging_types.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "Belum ada jenis tagging untuk tahun ini.";
    row.append(cell);
    rows.append(row);
  }
  for (const taggingType of summary.tagging_types) {
    const row = document.createElement("tr");
    for (const value of [
      taggingType.name,
      formatNumber(taggingType.sub_unit_count),
      formatNumber(taggingType.subactivity_count),
      formatNumber(taggingType.package_count),
      formatNumber(taggingType.budget),
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    row.lastElementChild.classList.add("numeric-cell");
    rows.append(row);
  }
  elements.taggingTypes.replaceChildren(rows);
}

async function loadSummary() {
  if (state.year === null || state.stageId === null) return;
  const requestId = ++state.requestId;
  setStatus("Memuat ringkasan...");
  try {
    const summary = await fetchJson(
      `/api/tagging-summary?year=${state.year}&tahapan_id=${state.stageId}`,
    );
    if (requestId !== state.requestId) return;
    renderSummary(summary);
    setStatus(`Ringkasan tahun ${state.year} berhasil dimuat.`);
  } catch (error) {
    if (requestId === state.requestId) setStatus(error.message, true);
  }
}

async function loadYear(year) {
  state.year = year ? Number(year) : null;
  state.stageId = null;
  elements.summary.replaceChildren();
  elements.taggingTypes.replaceChildren();
  elements.stage.replaceChildren(new Option("Memuat tahapan...", ""));
  elements.stage.disabled = true;
  if (state.year === null) {
    setStatus("Pilih tahun untuk melihat ringkasan.");
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
      await loadSummary();
    } else {
      setStatus("Belum ada tahapan untuk tahun tersebut.");
    }
  } catch (error) {
    setStatus(error.message, true);
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
    const years = await fetchJson("/api/years");
    elements.year.replaceChildren(new Option("Pilih Tahun", ""));
    for (const year of years.years) {
      elements.year.add(new Option(String(year), String(year)));
    }
    elements.year.disabled = years.years.length === 0;
    const currentYear = new Date().getFullYear();
    if (years.years.includes(currentYear)) {
      elements.year.value = String(currentYear);
      await loadYear(String(currentYear));
    } else {
      setStatus("Pilih tahun untuk melihat ringkasan.");
    }
  } catch (error) {
    setStatus(error.message, true);
  }
}

elements.year.addEventListener("change", () => void loadYear(elements.year.value));
elements.stage.addEventListener("change", () => {
  state.stageId = elements.stage.value ? Number(elements.stage.value) : null;
  void loadSummary();
});
elements.logout.addEventListener("click", async () => {
  elements.logout.disabled = true;
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  } catch (error) {
    elements.logout.disabled = false;
    setStatus(error.message, true);
  }
});

void initialize();
