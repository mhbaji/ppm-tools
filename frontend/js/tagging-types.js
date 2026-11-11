"use strict";

(() => {
const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  form: document.querySelector("#tagging-type-form"),
  name: document.querySelector("#tagging-type-name"),
  year: document.querySelector("#tagging-type-year"),
  submit: document.querySelector("#tagging-type-submit"),
  cancel: document.querySelector("#tagging-type-cancel"),
  status: document.querySelector("#tagging-type-status"),
  tableBody: document.querySelector("#tagging-type-table-body"),
};

const state = {
  csrfToken: "",
  editingCode: null,
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

function setStatus(message, kind = "") {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", kind === "error");
  elements.status.classList.toggle("is-success", kind === "success");
}

function showTableMessage(message, isError = false) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.className = `tagging-type-empty${isError ? " is-error" : ""}`;
  cell.colSpan = 4;
  cell.textContent = message;
  row.append(cell);
  elements.tableBody.replaceChildren(row);
}

function renderTaggingTypes(taggingTypes) {
  const fragment = document.createDocumentFragment();
  if (taggingTypes.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "tagging-type-empty";
    cell.colSpan = 4;
    cell.textContent = "Belum ada jenis tagging untuk tahun ini.";
    row.append(cell);
    fragment.append(row);
  }

  for (const taggingType of taggingTypes) {
    const row = document.createElement("tr");
    for (const value of [taggingType.code, taggingType.name, String(taggingType.year)]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }

    const actionCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "tagging-type-actions";
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "button button-secondary";
    editButton.textContent = "Edit";
    editButton.setAttribute("aria-label", `Edit ${taggingType.name}`);
    editButton.addEventListener("click", () => editTaggingType(taggingType));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "button button-danger";
    deleteButton.textContent = "Hapus";
    deleteButton.setAttribute("aria-label", `Hapus ${taggingType.name}`);
    deleteButton.addEventListener("click", () => void deleteTaggingType(taggingType, deleteButton));
    actions.append(editButton, deleteButton);
    actionCell.append(actions);
    row.append(actionCell);
    fragment.append(row);
  }
  elements.tableBody.replaceChildren(fragment);
}

async function loadTaggingTypes(preserveStatus = false) {
  const year = elements.year.value;
  const query = year ? `?year=${encodeURIComponent(year)}` : "";
  showTableMessage("Memuat data...");
  try {
    const result = await fetchJson(`/api/admin/tagging-types${query}`);
    renderTaggingTypes(result.tagging_types);
    if (!preserveStatus) setStatus("");
    return true;
  } catch (error) {
    setStatus(error.message, "error");
    showTableMessage("Daftar jenis tagging tidak dapat dimuat.", true);
    return false;
  }
}

function editTaggingType(taggingType) {
  state.editingCode = taggingType.code;
  elements.name.value = taggingType.name;
  if (!Array.from(elements.year.options).some(
    (option) => option.value === String(taggingType.year),
  )) {
    elements.year.add(new Option(String(taggingType.year), String(taggingType.year)));
  }
  elements.year.value = String(taggingType.year);
  elements.submit.textContent = "Simpan perubahan";
  elements.cancel.hidden = false;
  void loadTaggingTypes();
  elements.name.focus();
}

function resetForm() {
  const selectedYear = elements.year.value;
  state.editingCode = null;
  elements.form.reset();
  if (selectedYear) elements.year.value = selectedYear;
  elements.submit.textContent = "Tambah jenis tagging";
  elements.cancel.hidden = true;
}

async function saveTaggingType(event) {
  event.preventDefault();
  const isEditing = state.editingCode !== null;
  const body = {
    name: elements.name.value.trim(),
    year: Number(elements.year.value),
  };
  elements.submit.disabled = true;
  setStatus(isEditing ? "Menyimpan perubahan..." : "Menambahkan jenis tagging...");
  try {
    const url = isEditing
      ? `/api/admin/tagging-types/${encodeURIComponent(state.editingCode)}`
      : "/api/admin/tagging-types";
    const saved = await fetchJson(url, {
      method: isEditing ? "PATCH" : "POST",
      body: JSON.stringify(body),
    });
    resetForm();
    const loaded = await loadTaggingTypes(true);
    if (loaded) {
      setStatus(
        isEditing
          ? "Jenis tagging berhasil diperbarui."
          : `Jenis tagging berhasil ditambahkan dengan kode ${saved.code}.`,
        "success",
      );
    }
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    elements.submit.disabled = false;
  }
}

async function deleteTaggingType(taggingType, button) {
  if (!window.confirm(`Hapus jenis tagging "${taggingType.name}" (${taggingType.code})?`)) {
    return;
  }
  button.disabled = true;
  setStatus("Menghapus jenis tagging...");
  try {
    await fetchJson(`/api/admin/tagging-types/${encodeURIComponent(taggingType.code)}`, {
      method: "DELETE",
    });
    if (state.editingCode === taggingType.code) resetForm();
    const loaded = await loadTaggingTypes(true);
    if (loaded) setStatus("Jenis tagging berhasil dihapus.", "success");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    button.disabled = false;
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
    elements.year.replaceChildren(new Option("Pilih tahun", ""));
    for (const year of years.years) {
      elements.year.add(new Option(String(year), String(year)));
    }
    elements.year.disabled = years.years.length === 0;
    if (years.years.length > 0) {
      elements.year.value = String(years.years[0]);
    } else {
      setStatus("Belum ada data tahun yang tersedia.");
    }
    await loadTaggingTypes();
  } catch (error) {
    setStatus(error.message, "error");
    showTableMessage("Daftar jenis tagging tidak dapat dimuat.", true);
  }
}

elements.form.addEventListener("submit", (event) => {
  void saveTaggingType(event);
});

elements.year.addEventListener("change", () => {
  void loadTaggingTypes();
});

elements.cancel.addEventListener("click", () => {
  resetForm();
  setStatus("");
});

if (!document.querySelector("#year-form")) {
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
}

void initialize();
})();
