"use strict";

const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  status: document.querySelector("#tahapan-status"),
  yearForm: document.querySelector("#year-form"),
  yearInput: document.querySelector("#year-input"),
  yearSubmit: document.querySelector("#year-submit"),
  yearCancel: document.querySelector("#year-cancel"),
  yearRows: document.querySelector("#year-rows"),
  periodForm: document.querySelector("#period-form"),
  periodName: document.querySelector("#period-name"),
  periodSubmit: document.querySelector("#period-submit"),
  periodCancel: document.querySelector("#period-cancel"),
  periodRows: document.querySelector("#period-rows"),
  stageForm: document.querySelector("#stage-form"),
  stageCode: document.querySelector("#stage-code"),
  stageName: document.querySelector("#stage-name"),
  stageYear: document.querySelector("#stage-year"),
  stageSubmit: document.querySelector("#stage-submit"),
  stageCancel: document.querySelector("#stage-cancel"),
  stageRows: document.querySelector("#stage-rows"),
};

const state = {
  csrfToken: "",
  years: [],
  editingYearId: null,
  editingPeriodId: null,
  editingStageId: null,
};

async function fetchJson(url, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };
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

function renderYears() {
  const fragment = document.createDocumentFragment();
  for (const year of state.years) {
    const row = document.createElement("tr");
    for (const value of [year.id, year.year]) {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      row.append(cell);
    }
    const actions = document.createElement("td");
    actions.append(
      makeButton("Edit", "button button-secondary", () => {
        state.editingYearId = year.id;
        elements.yearInput.value = String(year.year);
        elements.yearSubmit.textContent = "Simpan Perubahan";
        elements.yearCancel.hidden = false;
      }),
      makeButton("Hapus", "button button-danger", () => void deleteYear(year)),
    );
    row.append(actions);
    fragment.append(row);
  }
  elements.yearRows.replaceChildren(fragment);
  elements.stageYear.replaceChildren(new Option("Pilih tahun", ""));
  for (const item of state.years) {
    elements.stageYear.add(new Option(String(item.year), String(item.year)));
  }
}

function makeButton(label, className, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", action);
  return button;
}

async function loadStages() {
  const stageSets = await Promise.all(
    state.years.map((item) =>
      fetchJson(`/api/admin/tahapan?year=${encodeURIComponent(item.year)}`),
    ),
  );
  const stages = stageSets.flatMap((result) => result.tahapan);
  const fragment = document.createDocumentFragment();
  for (const stage of stages) {
    const row = document.createElement("tr");
    for (const value of [stage.code, stage.name, stage.year]) {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      row.append(cell);
    }
    const actions = document.createElement("td");
    actions.append(
      makeButton("Edit", "button button-secondary", () => {
        state.editingStageId = stage.id;
        elements.stageCode.value = String(stage.code);
        elements.stageName.value = stage.name;
        elements.stageYear.value = String(stage.year);
        elements.stageSubmit.textContent = "Simpan Perubahan";
        elements.stageCancel.hidden = false;
      }),
      makeButton("Hapus", "button button-danger", () => void deleteStage(stage)),
    );
    row.append(actions);
    fragment.append(row);
  }
  elements.stageRows.replaceChildren(fragment);
}

async function loadPeriods() {
  const result = await fetchJson("/api/admin/catalog/periode");
  const fragment = document.createDocumentFragment();
  for (const period of result.items) {
    const row = document.createElement("tr");
    for (const value of [period.id, period.name]) {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      row.append(cell);
    }
    const actions = document.createElement("td");
    actions.append(
      makeButton("Edit", "button button-secondary", () => {
        state.editingPeriodId = period.id;
        elements.periodName.value = period.name;
        elements.periodSubmit.textContent = "Simpan Perubahan";
        elements.periodCancel.hidden = false;
      }),
      makeButton("Hapus", "button button-danger", () => void deletePeriod(period)),
    );
    row.append(actions);
    fragment.append(row);
  }
  elements.periodRows.replaceChildren(fragment);
}

async function reload() {
  const result = await fetchJson("/api/admin/years");
  state.years = result.years;
  renderYears();
  await Promise.all([loadStages(), loadPeriods()]);
}

function resetYearForm() {
  state.editingYearId = null;
  elements.yearForm.reset();
  elements.yearSubmit.textContent = "Tambah Tahun";
  elements.yearCancel.hidden = true;
}

function resetStageForm() {
  state.editingStageId = null;
  elements.stageForm.reset();
  elements.stageSubmit.textContent = "Tambah Tahapan";
  elements.stageCancel.hidden = true;
}

function resetPeriodForm() {
  state.editingPeriodId = null;
  elements.periodForm.reset();
  elements.periodSubmit.textContent = "Tambah Periode";
  elements.periodCancel.hidden = true;
}

async function saveYear(event) {
  event.preventDefault();
  const editing = state.editingYearId !== null;
  const url = editing
    ? `/api/admin/years/${state.editingYearId}`
    : "/api/admin/years";
  try {
    await fetchJson(url, {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify({ year: Number(elements.yearInput.value) }),
    });
    resetYearForm();
    await reload();
    setStatus(editing ? "Tahun berhasil diubah." : "Tahun berhasil ditambahkan.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function saveStage(event) {
  event.preventDefault();
  const editing = state.editingStageId !== null;
  const url = editing
    ? `/api/admin/tahapan/${state.editingStageId}`
    : "/api/admin/tahapan";
  try {
    await fetchJson(url, {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify({
        code: Number(elements.stageCode.value),
        name: elements.stageName.value.trim(),
        year: Number(elements.stageYear.value),
      }),
    });
    resetStageForm();
    await reload();
    setStatus(editing ? "Tahapan berhasil diubah." : "Tahapan berhasil ditambahkan.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function savePeriod(event) {
  event.preventDefault();
  const editing = state.editingPeriodId !== null;
  const url = editing
    ? `/api/admin/catalog/periode/${state.editingPeriodId}`
    : "/api/admin/catalog/periode";
  try {
    await fetchJson(url, {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify({ name: elements.periodName.value.trim() }),
    });
    resetPeriodForm();
    await loadPeriods();
    setStatus(editing ? "Periode berhasil diubah." : "Periode berhasil ditambahkan.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function deleteYear(year) {
  if (!window.confirm(`Hapus tahun ${year.year}?`)) return;
  try {
    await fetchJson(`/api/admin/years/${year.id}`, { method: "DELETE" });
    await reload();
    setStatus("Tahun berhasil dihapus.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function deleteStage(stage) {
  if (!window.confirm(`Hapus tahapan "${stage.name}" (${stage.year})?`)) return;
  try {
    await fetchJson(`/api/admin/tahapan/${stage.id}`, { method: "DELETE" });
    await reload();
    setStatus("Tahapan berhasil dihapus.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function deletePeriod(period) {
  if (!window.confirm(`Hapus periode "${period.name}"?`)) return;
  try {
    await fetchJson(`/api/admin/catalog/periode/${period.id}`, { method: "DELETE" });
    await loadPeriods();
    setStatus("Periode berhasil dihapus.");
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
    await reload();
  } catch (error) {
    setStatus(error.message, true);
  }
}

elements.yearForm.addEventListener("submit", (event) => void saveYear(event));
elements.stageForm.addEventListener("submit", (event) => void saveStage(event));
elements.periodForm.addEventListener("submit", (event) => void savePeriod(event));
elements.yearCancel.addEventListener("click", resetYearForm);
elements.stageCancel.addEventListener("click", resetStageForm);
elements.periodCancel.addEventListener("click", resetPeriodForm);
elements.logout.addEventListener("click", async () => {
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  } catch (error) {
    setStatus(error.message, true);
  }
});

void initialize();
