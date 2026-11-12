(() => {
"use strict";

const elements = {
  adminMode: document.querySelector("#admin-link-mode"),
  grid: document.querySelector(".link-shortlinks-admin-grid"),
  linkPanel: document.querySelector("#admin-link-panel"),
  shortlinksPanel: document.querySelector("#admin-shortlinks-panel"),
  identity: document.querySelector("#shortlinks-identity"),
  logout: document.querySelector("#logout-button"),
  status: document.querySelector("#shortlinks-status"),
  summary: document.querySelector("#shortlinks-summary"),
  formTitle: document.querySelector("#shortlinks-create-title"),
  createForm: document.querySelector("#shortlinks-create-form"),
  createTarget: document.querySelector("#shortlinks-create-target"),
  createAlias: document.querySelector("#shortlinks-create-alias"),
  createTitle: document.querySelector("#shortlinks-create-title-input"),
  createExpiry: document.querySelector("#shortlinks-create-expiry"),
  createSubmit: document.querySelector("#shortlinks-create-submit"),
  createCancel: document.querySelector("#shortlinks-create-cancel"),
  createResult: document.querySelector("#shortlinks-create-result"),
  createResultLabel: document.querySelector("#shortlinks-create-result-label"),
  createResultLink: document.querySelector("#shortlinks-create-result-link"),
  searchForm: document.querySelector("#shortlinks-search-form"),
  search: document.querySelector("#shortlinks-search"),
  searchClear: document.querySelector("#shortlinks-search-clear"),
  tableBody: document.querySelector("#shortlinks-table-body"),
  pagination: document.querySelector("#shortlinks-pagination"),
  pageIndicator: document.querySelector("#shortlinks-page-indicator"),
  previous: document.querySelector("#shortlinks-previous"),
  next: document.querySelector("#shortlinks-next"),
};
const state = {
  csrfToken: "",
  search: "",
  limit: 25,
  offset: 0,
  total: 0,
  requestId: 0,
  items: [],
  editingId: null,
};

async function fetchJson(url, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
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
    const error = new Error(result.error || `Permintaan gagal (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return result;
}

function formatNumber(value) {
  return new Intl.NumberFormat("id-ID").format(value);
}

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", isError);
}

function renderSummary(summary) {
  const buckets = [
    [`Tahun ini (${summary.year})`, "this_year"],
    [`Tahun N-1 (${summary.year - 1})`, "year_minus_1"],
    [`Tahun N-2 (${summary.year - 2})`, "year_minus_2"],
    [`Sebelum ${summary.year - 2}`, "before_year_minus_2"],
  ];
  const primaryMetrics = [
    ["Total shortlink", summary.total],
    ["Aktif", summary.active],
    ["Nonaktif", summary.inactive],
  ];
  const fragment = document.createDocumentFragment();
  for (const [labelText, value] of primaryMetrics) {
    const card = document.createElement("div");
    card.className = "summary-card";
    const label = document.createElement("span");
    label.className = "summary-card-label";
    label.textContent = labelText;
    const count = document.createElement("strong");
    count.className = "summary-card-value";
    count.textContent = formatNumber(value);
    card.append(label, count);
    fragment.append(card);
  }
  const primaryRow = document.createElement("div");
  primaryRow.className = "summary-total-row";
  primaryRow.append(fragment);

  const periodRow = document.createElement("div");
  periodRow.className = "summary-period-row";
  for (const [labelText, key] of buckets) {
    const card = document.createElement("div");
    card.className = "summary-card shortlinks-summary-year-card";
    const year = document.createElement("span");
    year.className = "shortlinks-summary-year";
    year.textContent = labelText;

    const created = document.createElement("div");
    created.className = "shortlinks-summary-created";
    const createdLabel = document.createElement("span");
    createdLabel.textContent = "Dibuat";
    const createdValue = document.createElement("strong");
    createdValue.textContent = formatNumber(summary.created[key]);
    created.append(createdLabel, createdValue);

    const clicks = document.createElement("div");
    clicks.className = "shortlinks-summary-clicks";
    const clicksLabel = document.createElement("span");
    clicksLabel.textContent = "Diklik";
    const clicksValue = document.createElement("strong");
    clicksValue.textContent = formatNumber(summary.clicks[key]);
    clicks.append(clicksLabel, clicksValue);

    card.append(year, created, clicks);
    periodRow.append(card);
  }
  elements.summary.replaceChildren(primaryRow, periodRow);
}

function formatDateTime(value) {
  if (!value) return "Tanpa batas";
  const date = new Date(`${value.replace(" ", "T")}Z`);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("id-ID", {
      timeZone: "UTC",
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
}

function localDateTimeValue(value) {
  if (!value) return "";
  const date = new Date(`${value.replace(" ", "T")}Z`);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function makeAction(label, action, item) {
  const button = document.createElement("button");
  button.className = "button button-secondary shortlinks-action";
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", () => void action(item));
  return button;
}

function renderTable(items) {
  const fragment = document.createDocumentFragment();
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.textContent = state.search
      ? "Tidak ada shortlink yang cocok dengan pencarian."
      : "Belum ada shortlink.";
    row.append(cell);
    fragment.append(row);
  }
  for (const item of items) {
    const row = document.createElement("tr");
    const titleCell = document.createElement("td");
    const title = document.createElement("strong");
    title.textContent = item.title;
    const alias = document.createElement("div");
    const shortUrl = document.createElement("a");
    shortUrl.href = new URL(item.short_url, window.location.origin).href;
    shortUrl.textContent = item.short_url;
    shortUrl.target = "_blank";
    shortUrl.rel = "noopener noreferrer";
    alias.append(shortUrl);
    titleCell.append(title, alias);

    const targetCell = document.createElement("td");
    const target = document.createElement("a");
    target.href = item.target_url;
    target.textContent = item.target_url;
    target.target = "_blank";
    target.rel = "noopener noreferrer";
    targetCell.append(target);

    const clicks = document.createElement("td");
    clicks.textContent = formatNumber(item.click_count);
    const status = document.createElement("td");
    status.textContent = item.is_active ? "Aktif" : "Nonaktif";
    const expiry = document.createElement("td");
    expiry.textContent = formatDateTime(item.expires_at);
    const created = document.createElement("td");
    created.textContent = formatDateTime(item.created_at);
    const updated = document.createElement("td");
    updated.textContent = formatDateTime(item.updated_at);

    const actions = document.createElement("td");
    actions.className = "shortlinks-row-actions";
    actions.append(
      makeAction("Edit", openEditForm, item),
      makeAction(item.is_active ? "Nonaktifkan" : "Aktifkan", toggleStatus, item),
      makeAction("Hapus", deleteShortlink, item),
    );
    row.append(
      titleCell,
      targetCell,
      clicks,
      status,
      expiry,
      created,
      updated,
      actions,
    );
    fragment.append(row);
  }
  elements.tableBody.replaceChildren(fragment);
}

function renderPagination() {
  const pages = Math.ceil(state.total / state.limit);
  elements.pagination.hidden = pages <= 1;
  elements.pageIndicator.textContent = pages
    ? `Halaman ${Math.floor(state.offset / state.limit) + 1} dari ${pages} · ${formatNumber(state.total)} shortlink`
    : "";
  elements.previous.disabled = state.offset === 0;
  elements.next.disabled = state.offset + state.limit >= state.total;
}

elements.createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.createForm.reportValidity()) return;
  const editingId = state.editingId;
  const isEditing = editingId !== null;
  const expiryValue = elements.createExpiry.value;
  elements.createSubmit.disabled = true;
  elements.createResult.hidden = true;
  setStatus(isEditing ? "Menyimpan perubahan shortlink..." : "Membuat shortlink...");
  try {
    const result = await fetchJson(
      isEditing ? `/api/admin/shortlinks/${editingId}` : "/api/admin/shortlinks",
      {
        method: isEditing ? "PATCH" : "POST",
        body: JSON.stringify({
          alias: elements.createAlias.value.trim(),
          title: elements.createTitle.value.trim(),
          target_url: elements.createTarget.value.trim(),
          expires_at: expiryValue ? new Date(expiryValue).toISOString() : null,
        }),
      },
    );
    if (isEditing) {
      elements.createResultLabel.textContent = "Perubahan shortlink berhasil disimpan.";
      elements.createResultLink.hidden = true;
      closeEditForm();
    } else {
      const shortUrl = new URL(result.shortlink.short_url, window.location.origin);
      elements.createResultLabel.textContent = "Shortlink berhasil dibuat:";
      elements.createResultLink.href = shortUrl.href;
      elements.createResultLink.textContent = shortUrl.href;
      elements.createResultLink.hidden = false;
      elements.createForm.reset();
    }
    elements.createResult.hidden = false;
    state.search = "";
    state.offset = 0;
    elements.search.value = "";
    elements.searchClear.hidden = true;
    await loadData();
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    elements.createSubmit.disabled = false;
  }
});

async function loadData() {
  const requestId = ++state.requestId;
  setStatus("Memuat ringkasan dan daftar shortlink...");
  const params = new URLSearchParams({
    limit: String(state.limit),
    offset: String(state.offset),
  });
  if (state.search) params.set("q", state.search);
  try {
    const [summary, listing] = await Promise.all([
      fetchJson("/api/admin/shortlinks/summary"),
      fetchJson(`/api/admin/shortlinks?${params}`),
    ]);
    if (requestId !== state.requestId) return;
    state.total = listing.total;
    state.items = listing.items;
    renderSummary(summary);
    renderTable(state.items);
    renderPagination();
    setStatus(
      listing.total
        ? `${formatNumber(listing.total)} shortlink ditemukan.`
        : "Belum ada data shortlink.",
    );
  } catch (error) {
    if (requestId === state.requestId) setStatus(error.message, true);
  }
}

function openEditForm(item) {
  state.editingId = item.id;
  elements.formTitle.textContent = "Edit Shortlink";
  elements.createSubmit.textContent = "Simpan perubahan";
  elements.createCancel.hidden = false;
  elements.createAlias.value = item.alias;
  elements.createTitle.value = item.title;
  elements.createTarget.value = item.target_url;
  elements.createExpiry.value = localDateTimeValue(item.expires_at);
  elements.createResult.hidden = true;
  elements.createForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeEditForm() {
  state.editingId = null;
  elements.createForm.reset();
  elements.formTitle.textContent = "Buat shortlink";
  elements.createSubmit.textContent = "Buat shortlink";
  elements.createCancel.hidden = true;
}

async function toggleStatus(item) {
  try {
    await fetchJson(`/api/admin/shortlinks/${item.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !item.is_active }),
    });
    await loadData();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function deleteShortlink(item) {
  const confirmed = await confirmDeletion(
    "Hapus shortlink?",
    `Shortlink "${item.alias}" beserta riwayat kliknya akan dihapus permanen. Tindakan ini tidak dapat dibatalkan.`,
  );
  if (!confirmed) return;
  try {
    await fetchJson(`/api/admin/shortlinks/${item.id}`, {
      method: "DELETE",
    });
    if (state.items.length === 1 && state.offset > 0) {
      state.offset = Math.max(0, state.offset - state.limit);
    }
    await loadData();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function confirmDeletion(title, description) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "export-choice-dialog link-delete-dialog";
    dialog.setAttribute("aria-labelledby", "shortlink-delete-title");
    dialog.setAttribute("aria-describedby", "shortlink-delete-description");

    const icon = document.createElement("div");
    icon.className = "link-delete-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "!";
    const heading = document.createElement("h2");
    heading.id = "shortlink-delete-title";
    heading.textContent = title;
    const message = document.createElement("p");
    message.id = "shortlink-delete-description";
    message.textContent = description;
    const actions = document.createElement("div");
    actions.className = "export-choice-actions";
    const finish = (confirmed) => {
      dialog.close();
      dialog.remove();
      resolve(confirmed);
    };
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "button button-secondary";
    cancel.textContent = "Batal";
    cancel.autofocus = true;
    cancel.addEventListener("click", () => finish(false));
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "button link-delete-confirm";
    confirm.textContent = "Ya, hapus";
    confirm.addEventListener("click", () => finish(true));
    actions.append(cancel, confirm);
    dialog.append(icon, heading, message, actions);
    document.body.append(dialog);
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(false);
    });
    dialog.showModal();
  });
}

elements.createCancel.addEventListener("click", closeEditForm);
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.search.value.trim();
  state.offset = 0;
  elements.searchClear.hidden = !state.search;
  void loadData();
});
elements.searchClear.addEventListener("click", () => {
  elements.search.value = "";
  state.search = "";
  state.offset = 0;
  elements.searchClear.hidden = true;
  void loadData();
});
elements.previous.addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.limit);
  void loadData();
});
elements.next.addEventListener("click", () => {
  if (state.offset + state.limit < state.total) {
    state.offset += state.limit;
    void loadData();
  }
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

async function initialize() {
  try {
    const auth = await fetchJson("/api/auth/session");
    state.csrfToken = auth.csrf_token;
    if (!auth.authenticated) {
      window.location.replace("/login");
      return;
    }
    elements.identity.textContent = `Login sebagai ${auth.username}`;
    await loadData();
  } catch (error) {
    setStatus(error.message, true);
  }
}

function updateAdminMode() {
  const isShortlinkMode = elements.adminMode.value === "shortlink";
  elements.linkPanel.hidden = isShortlinkMode;
  elements.shortlinksPanel.hidden = !isShortlinkMode;
  elements.grid.style.gridTemplateColumns = "minmax(0, 1fr)";
}

elements.adminMode.addEventListener("change", () => {
  updateAdminMode();
  if (elements.adminMode.value === "shortlink") void initialize();
});

elements.adminMode.value = location.pathname === "/admin/shortlinks"
  ? "shortlink"
  : "tautan";
updateAdminMode();
if (elements.adminMode.value === "shortlink") void initialize();
})();
