"use strict";

const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  year: document.querySelector("#master-year"),
  status: document.querySelector("#master-status"),
  skpdForm: document.querySelector("#skpd-form"),
  skpdCode: document.querySelector("#skpd-code"),
  skpdName: document.querySelector("#skpd-name"),
  skpdSubmit: document.querySelector("#skpd-submit"),
  skpdCancel: document.querySelector("#skpd-cancel"),
  skpdRows: document.querySelector("#skpd-rows"),
  skpdPageSize: document.querySelector("#skpd-page-size"),
  skpdPrevious: document.querySelector("#skpd-previous"),
  skpdNext: document.querySelector("#skpd-next"),
  skpdPageIndicator: document.querySelector("#skpd-page-indicator"),
  aliasForm: document.querySelector("#alias-form"),
  aliasSkpd: document.querySelector("#alias-skpd"),
  aliasName: document.querySelector("#alias-name"),
  aliasSubmit: document.querySelector("#alias-submit"),
  aliasCancel: document.querySelector("#alias-cancel"),
  subunitForm: document.querySelector("#subunit-form"),
  subunitCode: document.querySelector("#subunit-code"),
  subunitName: document.querySelector("#subunit-name"),
  subunitSubmit: document.querySelector("#subunit-submit"),
  subunitCancel: document.querySelector("#subunit-cancel"),
  subunitRows: document.querySelector("#subunit-rows"),
  subunitPageSize: document.querySelector("#subunit-page-size"),
  subunitPrevious: document.querySelector("#subunit-previous"),
  subunitNext: document.querySelector("#subunit-next"),
  subunitPageIndicator: document.querySelector("#subunit-page-indicator"),
};
const state = {
  csrfToken: "",
  skpd: [],
  subUnits: [],
  editingSkpdId: null,
  editingSubunitId: null,
  editingAliasId: null,
  skpdPage: 0,
  skpdPageSize: 10,
  subunitPage: 0,
  subunitPageSize: 10,
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

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", isError);
  elements.status.classList.toggle("is-success", Boolean(message) && !isError);
}

function makeButton(label, className, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", action);
  return button;
}

function renderSkpd() {
  const fragment = document.createDocumentFragment();
  const pageItems = state.skpd.slice(
    state.skpdPage * state.skpdPageSize,
    (state.skpdPage + 1) * state.skpdPageSize,
  );
  if (state.skpd.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = "Belum ada data SKPD untuk tahun ini.";
    row.append(cell);
    fragment.append(row);
  }
  for (const item of pageItems) {
    const row = document.createElement("tr");
    for (const value of [item.code, item.name]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const aliases = document.createElement("td");
    if (item.aliases.length === 0) {
      aliases.textContent = "—";
    } else {
      for (const alias of item.aliases) {
        const line = document.createElement("div");
        line.className = "alias-row";
        const name = document.createElement("span");
        name.textContent = alias.name;
        line.append(
          name,
          makeButton("Edit", "button button-secondary", () => {
            state.editingAliasId = alias.id;
            elements.aliasSkpd.value = String(item.id);
            elements.aliasSkpd.disabled = true;
            elements.aliasName.value = alias.name;
            elements.aliasSubmit.textContent = "Simpan alias";
            elements.aliasCancel.hidden = false;
          }),
          makeButton("Hapus", "button button-danger", () => void deleteAlias(alias)),
        );
        aliases.append(line);
      }
    }
    row.append(aliases);
    const actions = document.createElement("td");
    const actionButtons = document.createElement("div");
    actionButtons.className = "device-table-actions";
    actionButtons.append(
      makeButton("Edit", "button button-secondary", () => {
        state.editingSkpdId = item.id;
        elements.skpdCode.value = item.code;
        elements.skpdName.value = item.name;
        elements.skpdSubmit.textContent = "Simpan SKPD";
        elements.skpdCancel.hidden = false;
      }),
      makeButton("Hapus", "button button-danger", () => void deleteMaster("skpd", item)),
    );
    actions.append(actionButtons);
    row.append(actions);
    fragment.append(row);
  }
  elements.skpdRows.replaceChildren(fragment);
  updatePagination(
    state.skpd.length,
    state.skpdPage,
    state.skpdPageSize,
    elements.skpdPageIndicator,
    elements.skpdPrevious,
    elements.skpdNext,
  );
  elements.aliasSkpd.replaceChildren(new Option("Pilih SKPD", ""));
  for (const item of state.skpd) {
    elements.aliasSkpd.add(new Option(`${item.code} — ${item.name}`, String(item.id)));
  }
  elements.aliasSkpd.disabled = state.skpd.length === 0 || state.editingAliasId !== null;
  elements.aliasSubmit.disabled = state.skpd.length === 0 && state.editingAliasId === null;
}

function renderSubUnits() {
  const fragment = document.createDocumentFragment();
  const pageItems = state.subUnits.slice(
    state.subunitPage * state.subunitPageSize,
    (state.subunitPage + 1) * state.subunitPageSize,
  );
  if (state.subUnits.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 3;
    cell.textContent = "Belum ada data sub unit untuk tahun ini.";
    row.append(cell);
    fragment.append(row);
  }
  for (const item of pageItems) {
    const row = document.createElement("tr");
    for (const value of [item.code, item.name]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const actions = document.createElement("td");
    const actionButtons = document.createElement("div");
    actionButtons.className = "device-table-actions";
    actionButtons.append(
      makeButton("Edit", "button button-secondary", () => {
        state.editingSubunitId = item.id;
        elements.subunitCode.value = item.code;
        elements.subunitName.value = item.name;
        elements.subunitSubmit.textContent = "Simpan sub unit";
        elements.subunitCancel.hidden = false;
      }),
      makeButton("Hapus", "button button-danger", () => void deleteMaster("sub-unit", item)),
    );
    actions.append(actionButtons);
    row.append(actions);
    fragment.append(row);
  }
  elements.subunitRows.replaceChildren(fragment);
  updatePagination(
    state.subUnits.length,
    state.subunitPage,
    state.subunitPageSize,
    elements.subunitPageIndicator,
    elements.subunitPrevious,
    elements.subunitNext,
  );
}

function updatePagination(total, page, pageSize, indicator, previous, next) {
  const pageCount = Math.ceil(total / pageSize);
  indicator.textContent = pageCount ? `Halaman ${page + 1} dari ${pageCount}` : "Belum ada data";
  previous.disabled = page === 0;
  next.disabled = page + 1 >= pageCount;
}

async function loadData() {
  const result = await fetchJson(
    `/api/admin/perangkat-daerah?year=${encodeURIComponent(elements.year.value)}`,
  );
  state.skpd = result.skpd;
  state.subUnits = result.sub_units;
  state.skpdPage = Math.min(
    state.skpdPage,
    Math.max(0, Math.ceil(state.skpd.length / state.skpdPageSize) - 1),
  );
  state.subunitPage = Math.min(
    state.subunitPage,
    Math.max(0, Math.ceil(state.subUnits.length / state.subunitPageSize) - 1),
  );
  renderSkpd();
  renderSubUnits();
}

function resetSkpdForm() {
  state.editingSkpdId = null;
  elements.skpdForm.reset();
  elements.skpdSubmit.textContent = "Tambah SKPD";
  elements.skpdCancel.hidden = true;
}

function resetSubunitForm() {
  state.editingSubunitId = null;
  elements.subunitForm.reset();
  elements.subunitSubmit.textContent = "Tambah sub unit";
  elements.subunitCancel.hidden = true;
}

function resetAliasForm() {
  state.editingAliasId = null;
  elements.aliasForm.reset();
  elements.aliasSkpd.disabled = state.skpd.length === 0;
  elements.aliasSubmit.textContent = "Tambah alias";
  elements.aliasCancel.hidden = true;
}

async function saveMaster(event, resource, codeInput, nameInput) {
  event.preventDefault();
  const editingId = resource === "skpd" ? state.editingSkpdId : state.editingSubunitId;
  const url = editingId === null
    ? `/api/admin/perangkat-daerah/${resource}`
    : `/api/admin/perangkat-daerah/${resource}/${editingId}`;
  try {
    await fetchJson(url, {
      method: editingId === null ? "POST" : "PATCH",
      body: JSON.stringify({
        code: codeInput.value.trim(),
        name: nameInput.value.trim(),
        year: Number(elements.year.value),
      }),
    });
    if (resource === "skpd") resetSkpdForm();
    else resetSubunitForm();
    await loadData();
    setStatus("Data perangkat daerah berhasil disimpan.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function saveAlias(event) {
  event.preventDefault();
  const editing = state.editingAliasId !== null;
  const url = editing
    ? `/api/admin/skpd-aliases/${state.editingAliasId}`
    : `/api/admin/skpd/${elements.aliasSkpd.value}/aliases`;
  try {
    await fetchJson(url, {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify({ name: elements.aliasName.value.trim() }),
    });
    resetAliasForm();
    await loadData();
    setStatus(editing ? "Alias berhasil diperbarui." : "Alias berhasil ditambahkan.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function deleteMaster(resource, item) {
  if (!window.confirm(`Hapus "${item.name}" (${item.code})?`)) return;
  try {
    await fetchJson(
      `/api/admin/perangkat-daerah/${resource}/${item.id}`,
      { method: "DELETE" },
    );
    await loadData();
    setStatus("Data berhasil dihapus.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function deleteAlias(alias) {
  if (!window.confirm(`Hapus alias "${alias.name}"?`)) return;
  try {
    await fetchJson(`/api/admin/skpd-aliases/${alias.id}`, { method: "DELETE" });
    await loadData();
    setStatus("Alias berhasil dihapus.");
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
    const result = await fetchJson("/api/admin/years");
    elements.year.replaceChildren(new Option("Pilih tahun", ""));
    for (const year of result.years) {
      elements.year.add(new Option(String(year.year), String(year.year)));
    }
    elements.year.disabled = result.years.length === 0;
    elements.skpdSubmit.disabled = result.years.length === 0;
    elements.subunitSubmit.disabled = result.years.length === 0;
    if (result.years.length > 0) {
      elements.year.value = String(result.years[0].year);
      await loadData();
    } else {
      setStatus("Belum ada tahun yang tersedia.", true);
    }
  } catch (error) {
    setStatus(error.message, true);
  }
}

elements.year.addEventListener("change", () => {
  state.skpdPage = 0;
  state.subunitPage = 0;
  resetSkpdForm();
  resetSubunitForm();
  resetAliasForm();
  void loadData().catch((error) => setStatus(error.message, true));
});
elements.skpdPageSize.addEventListener("change", () => {
  state.skpdPageSize = Number(elements.skpdPageSize.value);
  state.skpdPage = 0;
  renderSkpd();
});
elements.skpdPrevious.addEventListener("click", () => {
  state.skpdPage = Math.max(0, state.skpdPage - 1);
  renderSkpd();
});
elements.skpdNext.addEventListener("click", () => {
  if ((state.skpdPage + 1) * state.skpdPageSize < state.skpd.length) {
    state.skpdPage += 1;
    renderSkpd();
  }
});
elements.subunitPageSize.addEventListener("change", () => {
  state.subunitPageSize = Number(elements.subunitPageSize.value);
  state.subunitPage = 0;
  renderSubUnits();
});
elements.subunitPrevious.addEventListener("click", () => {
  state.subunitPage = Math.max(0, state.subunitPage - 1);
  renderSubUnits();
});
elements.subunitNext.addEventListener("click", () => {
  if ((state.subunitPage + 1) * state.subunitPageSize < state.subUnits.length) {
    state.subunitPage += 1;
    renderSubUnits();
  }
});
elements.skpdForm.addEventListener("submit", (event) => {
  void saveMaster(event, "skpd", elements.skpdCode, elements.skpdName);
});
elements.subunitForm.addEventListener("submit", (event) => {
  void saveMaster(event, "sub-unit", elements.subunitCode, elements.subunitName);
});
elements.aliasForm.addEventListener("submit", (event) => void saveAlias(event));
elements.skpdCancel.addEventListener("click", resetSkpdForm);
elements.subunitCancel.addEventListener("click", resetSubunitForm);
elements.aliasCancel.addEventListener("click", resetAliasForm);
elements.logout.addEventListener("click", async () => {
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  } catch (error) {
    setStatus(error.message, true);
  }
});

void initialize();
