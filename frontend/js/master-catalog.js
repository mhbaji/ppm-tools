"use strict";

const state = { csrfToken: "" };
const singlePage = window.location.pathname === "/admin/level-pekerjaan";

function createCatalog(catalog, label, prefix = "catalog") {
  return {
    catalog,
    label,
    form: document.querySelector(`#${prefix}-form`),
    name: document.querySelector(`#${prefix}-name`),
    submit: prefix === "catalog"
      ? document.querySelector("#catalog-submit")
      : document.querySelector(`#${prefix}-form button[type="submit"]`),
    cancel: document.querySelector(`#${prefix}-cancel`),
    status: document.querySelector(`#${prefix}-status`),
    rows: document.querySelector(`#${prefix}-rows`),
    pageSizeSelect: document.querySelector(`#${prefix}-page-size`),
    previous: document.querySelector(`#${prefix}-previous`),
    next: document.querySelector(`#${prefix}-next`),
    pageIndicator: document.querySelector(`#${prefix}-page-indicator`),
    search: document.querySelector(`#${prefix}-search`),
    editingId: null,
    items: [],
    page: 0,
    pageSize: 10,
    searchTerm: "",
  };
}

const catalogs = singlePage
  ? [createCatalog("level-pekerjaan", "Level Pekerjaan")]
  : [
    createCatalog("indikator", "Indikator", "indikator"),
    createCatalog("satuan", "Satuan", "satuan"),
  ];

const elements = {
  identity: document.querySelector("#admin-identity"),
  logout: document.querySelector("#logout-button"),
  title: document.querySelector("#catalog-title"),
  singlePanel: document.querySelector("#single-catalog-panel"),
  combinedGrid: document.querySelector("#combined-catalog-grid"),
  nameLabel: document.querySelector("#catalog-name-label"),
  nameHeading: document.querySelector("#catalog-name-heading"),
  year: document.querySelector("#catalog-year"),
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

function setStatus(context, message, isError = false) {
  context.status.textContent = message;
  context.status.classList.toggle("is-error", isError);
  context.status.classList.toggle("is-success", Boolean(message) && !isError);
}

function makeButton(label, className, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", action);
  return button;
}

async function loadItems(context) {
  const parameters = new URLSearchParams();
  if (!singlePage && context.catalog !== "level-pekerjaan" && elements.year.value) {
    parameters.set("year", elements.year.value);
  }
  const suffix = parameters.size ? `?${parameters}` : "";
  const result = await fetchJson(`/api/admin/catalog/${context.catalog}${suffix}`);
  context.items = result.items;
  renderItems(context);
}

function renderItems(context) {
  const fragment = document.createDocumentFragment();
  const filteredItems = context.items.filter((item) =>
    item.name.toLocaleLowerCase().includes(context.searchTerm.toLocaleLowerCase()),
  );
  const start = context.page * context.pageSize;
  const pageItems = filteredItems.slice(start, start + context.pageSize);
  if (filteredItems.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 3;
    cell.textContent = `Belum ada data ${context.label}.`;
    row.append(cell);
    fragment.append(row);
  }
  for (const item of pageItems) {
    const row = document.createElement("tr");
    for (const value of [item.id, item.name]) {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      row.append(cell);
    }
    const actions = document.createElement("td");
    actions.append(
      makeButton("Edit", "button button-secondary", () => {
        context.editingId = item.id;
        context.name.value = item.name;
        context.submit.textContent = "Simpan Perubahan";
        context.cancel.hidden = false;
        context.name.focus();
      }),
      makeButton("Hapus", "button button-danger", () => void deleteItem(context, item)),
    );
    row.append(actions);
    fragment.append(row);
  }
  context.rows.replaceChildren(fragment);
  if (context.pageIndicator) {
    const pageCount = Math.ceil(filteredItems.length / context.pageSize);
    context.pageIndicator.textContent = pageCount
      ? `Halaman ${context.page + 1} dari ${pageCount}`
      : "Belum ada data";
    context.previous.disabled = context.page === 0;
    context.next.disabled = context.page + 1 >= pageCount;
  }
}

function resetForm(context) {
  context.editingId = null;
  context.form.reset();
  context.submit.textContent = "Tambah";
  context.cancel.hidden = true;
}

async function saveItem(context, event) {
  event.preventDefault();
  const editing = context.editingId !== null;
  const url = editing
    ? `/api/admin/catalog/${context.catalog}/${context.editingId}`
    : `/api/admin/catalog/${context.catalog}`;
  try {
    await fetchJson(url, {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify({ name: context.name.value.trim() }),
    });
    resetForm(context);
    await loadItems(context);
    setStatus(
      context,
      editing ? "Data berhasil diperbarui." : "Data berhasil ditambahkan.",
    );
  } catch (error) {
    setStatus(context, error.message, true);
  }
}

async function deleteItem(context, item) {
  if (!window.confirm(`Hapus "${item.name}"?`)) return;
  try {
    await fetchJson(
      `/api/admin/catalog/${context.catalog}/${item.id}`,
      { method: "DELETE" },
    );
    await loadItems(context);
    setStatus(context, "Data berhasil dihapus.");
  } catch (error) {
    setStatus(context, error.message, true);
  }
}

async function initialize() {
  if (singlePage) {
    elements.singlePanel.hidden = false;
    elements.combinedGrid.hidden = true;
    elements.title.textContent = "Level Pekerjaan";
    elements.nameLabel.textContent = "Nama level pekerjaan";
    elements.nameHeading.textContent = "Nama Level Pekerjaan";
    document.title = "Level Pekerjaan | PPM Tools";
  } else {
    elements.singlePanel.hidden = true;
    elements.combinedGrid.hidden = false;
    elements.title.textContent = "Indikator dan Satuan";
    document.title = "Indikator dan Satuan | PPM Tools";
  }
  for (const link of document.querySelectorAll(".admin-navigation a")) {
    const href = link.getAttribute("href");
    if (
      (singlePage && href === "/admin/level-pekerjaan")
      || (!singlePage && href === "/admin/referensi")
    ) {
      link.setAttribute("aria-current", "page");
    }
  }
  try {
    const auth = await fetchJson("/api/auth/session");
    state.csrfToken = auth.csrf_token;
    if (!auth.authenticated) {
      window.location.replace("/login");
      return;
    }
    elements.identity.textContent = `Login sebagai ${auth.username}`;
    if (!singlePage) {
      const years = await fetchJson("/api/admin/years");
      elements.year.replaceChildren(new Option("Pilih tahun", ""));
      for (const item of years.years) {
        elements.year.add(new Option(String(item.year), String(item.year)));
      }
      const currentYear = new Date().getFullYear();
      const selectedYear = years.years.find((item) => item.year === currentYear)
        || years.years[0];
      elements.year.disabled = years.years.length === 0;
      if (selectedYear) elements.year.value = String(selectedYear.year);
    }
    await Promise.all(catalogs.map((context) => loadItems(context)));
  } catch (error) {
    for (const context of catalogs) setStatus(context, error.message, true);
  }
}

for (const context of catalogs) {
  context.form.addEventListener("submit", (event) => void saveItem(context, event));
  context.cancel.addEventListener("click", () => resetForm(context));
  if (context.search) {
    context.search.addEventListener("input", () => {
      context.searchTerm = context.search.value.trim();
      context.page = 0;
      renderItems(context);
    });
  }
  if (context.pageSizeSelect) {
    context.pageSizeSelect.addEventListener("change", () => {
      context.pageSize = Number(context.pageSizeSelect.value);
      context.page = 0;
      renderItems(context);
    });
    context.previous.addEventListener("click", () => {
      context.page = Math.max(0, context.page - 1);
      renderItems(context);
    });
    context.next.addEventListener("click", () => {
      const filteredCount = context.items.filter((item) =>
        item.name.toLocaleLowerCase().includes(context.searchTerm.toLocaleLowerCase()),
      ).length;
      if ((context.page + 1) * context.pageSize < filteredCount) {
        context.page += 1;
        renderItems(context);
      }
    });
  }
}
if (elements.year) {
  elements.year.addEventListener("change", () => {
    for (const context of catalogs) {
      context.page = 0;
      void loadItems(context).catch((error) => setStatus(context, error.message, true));
    }
  });
}
elements.logout.addEventListener("click", async () => {
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.replace("/login");
  } catch (error) {
    for (const context of catalogs) setStatus(context, error.message, true);
  }
});

void initialize();
