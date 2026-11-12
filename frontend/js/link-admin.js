(() => {
"use strict";

const elements = {
  adminMode: document.querySelector("#admin-link-mode"),
  status: document.querySelector("#link-admin-status"),
  login: document.querySelector("#link-admin-login"),
  retry: document.querySelector("#link-admin-retry"),
  content: document.querySelector("#link-admin-content"),
  summary: document.querySelector("#link-admin-summary"),
  categoryForm: document.querySelector("#category-form"),
  categoryId: document.querySelector("#category-id"),
  categoryName: document.querySelector("#category-name"),
  categoryParent: document.querySelector("#category-parent"),
  categoryDescription: document.querySelector("#category-description"),
  categoryAlias: document.querySelector("#category-custom-alias"),
  categoryCancel: document.querySelector("#category-cancel"),
  linkForm: document.querySelector("#link-form"),
  linkId: document.querySelector("#link-id"),
  linkYear: document.querySelector("#link-year"),
  yearHelp: document.querySelector("#link-year-help"),
  selectionWarning: document.querySelector("#link-admin-selection-warning"),
  linkCategory: document.querySelector("#link-category"),
  linkTitle: document.querySelector("#link-title"),
  linkUrl: document.querySelector("#link-url"),
  linkImageUrl: document.querySelector("#link-image-url"),
  linkIcon: document.querySelector("#link-icon"),
  linkDescription: document.querySelector("#link-description"),
  linkTags: document.querySelector("#link-tags"),
  linkCancel: document.querySelector("#link-cancel"),
  directory: document.querySelector("#link-admin-directory"),
  searchForm: document.querySelector("#link-admin-search-form"),
  search: document.querySelector("#link-admin-search"),
  searchClear: document.querySelector("#link-admin-search-clear"),
  searchStatus: document.querySelector("#link-admin-search-status"),
};

const state = {
  csrfToken: "", categories: [], links: [], years: [], search: "", requestId: 0,
  mutationEnabled: false, missingSelections: new Set(),
};

function matchesSearch(values) {
  if (!state.search) return true;
  const query = state.search.toLocaleLowerCase("id-ID");
  return values.some((value) =>
    String(value || "").toLocaleLowerCase("id-ID").includes(query)
  );
}

function filteredCategories() {
  return state.categories.filter((category) => {
    const parent = state.categories.find((item) => item.id === category.parent_id);
    return matchesSearch([category.name, category.description, parent?.name]);
  });
}

function filteredLinks() {
  return state.links.filter((link) => {
    const category = state.categories.find((item) => item.id === link.category_id);
    const parent = state.categories.find((item) => item.id === category?.parent_id);
    return matchesSearch([
      link.title,
      link.url,
      link.description,
      link.year,
      ...link.tags,
      category?.name,
      parent?.name,
    ]);
  });
}

async function requestJson(url, options = {}) {
  const headers = { Accept: "application/json", ...options.headers };
  if (options.body) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = state.csrfToken;
  const response = await fetch(url, { ...options, headers });
  let result = {};
  try {
    result = await response.json();
  } catch {
    if (response.ok) throw new Error("Respons server tidak valid.");
  }
  if (!response.ok) {
    const error = new Error(result.error || `Permintaan gagal (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return result;
}

function showStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", isError);
}

function setMutationEnabled(enabled) {
  state.mutationEnabled = enabled;
  document.querySelectorAll(
    "#category-form button[type=submit], #category-custom-alias, #link-form button[type=submit], #link-admin-directory button",
  ).forEach((button) => { button.disabled = !enabled; });
}

function showError(error, prefix = "", disableActions = false) {
  if (disableActions || error.status === 401) setMutationEnabled(false);
  if (error.status === 401) {
    elements.login.hidden = false;
    elements.retry.hidden = false;
    showStatus(`${prefix}Sesi admin berakhir. Silakan login kembali.`, true);
    return;
  }
  elements.retry.hidden = false;
  showStatus(`${prefix}${error.message}`, true);
}

function updateSelectionWarning() {
  const missing = [...state.missingSelections];
  elements.selectionWarning.hidden = missing.length === 0;
  elements.selectionWarning.textContent = missing.length
    ? `Pilihan ${missing.join(", ")} tidak lagi tersedia; pilih kembali.`
    : "";
}

function resetCategoryForm() {
  elements.categoryForm.reset();
  elements.categoryParent.setCustomValidity("");
  elements.categoryId.value = "";
  elements.categoryCancel.hidden = true;
  state.missingSelections.delete("topik utama");
  updateSelectionWarning();
}

function resetLinkForm() {
  elements.linkForm.reset();
  elements.linkId.value = "";
  elements.linkCancel.hidden = true;
  state.missingSelections.delete("topik rincian");
  state.missingSelections.delete("tahun");
  updateSelectionWarning();
}

function renderCategories() {
  const selectedParent = elements.categoryParent.value;
  const selectedCategory = elements.linkCategory.value;
  const selectedYear = elements.linkYear.value;
  const roots = state.categories.filter((category) => category.parent_id === null);
  elements.categoryParent.replaceChildren(new Option("Topik utama", ""));
  for (const root of roots) {
    const label = root.is_active ? root.name : `${root.name} (nonaktif)`;
    elements.categoryParent.add(new Option(label, String(root.id)));
  }
  elements.linkCategory.replaceChildren(new Option("Pilih topik rincian", ""));
  for (const category of state.categories.filter((item) => item.parent_id !== null)) {
    const parent = state.categories.find((item) => item.id === category.parent_id);
    const parentName = parent?.name || "Topik";
    const parentLabel = parent?.is_active ? parentName : `${parentName} (nonaktif)`;
    const categoryLabel = category.is_active ? category.name : `${category.name} (nonaktif)`;
    elements.linkCategory.add(
      new Option(`${parentLabel} / ${categoryLabel}`, String(category.id)),
    );
  }
  elements.linkYear.replaceChildren(
    new Option(state.years.length ? "Pilih tahun" : "Tahun belum tersedia", ""),
  );
  for (const year of state.years) {
    elements.linkYear.add(new Option(String(year), String(year)));
  }
  elements.categoryParent.value = selectedParent;
  elements.linkCategory.value = selectedCategory;
  elements.linkYear.value = selectedYear;
  const missingParent = Boolean(selectedParent && elements.categoryParent.value !== selectedParent);
  if (missingParent) {
    elements.categoryParent.setCustomValidity("Topik utama tidak lagi tersedia; pilih kembali.");
    state.missingSelections.add("topik utama");
  }
  elements.linkYear.disabled = state.years.length === 0;
  elements.yearHelp.hidden = state.years.length !== 0;
  if (selectedCategory && elements.linkCategory.value !== selectedCategory) {
    state.missingSelections.add("topik rincian");
  }
  if (selectedYear && elements.linkYear.value !== selectedYear) {
    state.missingSelections.add("tahun");
  }
  updateSelectionWarning();
}

function renderSummary() {
  const counts = [
    ["Topik Utama", state.categories.filter((item) => item.parent_id === null).length],
    ["Topik Rincian", state.categories.filter((item) => item.parent_id !== null).length],
    ["Tautan", state.links.length],
  ];
  const fragment = document.createDocumentFragment();
  for (const [labelText, value] of counts) {
    const card = document.createElement("div");
    card.className = "summary-card";
    const label = document.createElement("span");
    label.className = "summary-card-label";
    label.textContent = labelText;
    const count = document.createElement("strong");
    count.className = "summary-card-value";
    count.textContent = new Intl.NumberFormat("id-ID").format(value);
    card.append(label, count);
    fragment.append(card);
  }
  elements.summary.replaceChildren(fragment);
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value.replace(" ", "T"));
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

function actionButton(label, callback, inSummary = false) {
  const button = document.createElement("button");
  button.className = "button button-secondary";
  button.type = "button";
  button.disabled = !state.mutationEnabled;
  button.textContent = label;
  button.addEventListener("click", async (event) => {
    if (inSummary) {
      event.preventDefault();
      event.stopPropagation();
    }
    await callback();
  });
  return button;
}

function editCategory(category) {
  elements.categoryParent.setCustomValidity("");
  state.missingSelections.delete("topik utama");
  updateSelectionWarning();
  elements.categoryId.value = String(category.id);
  elements.categoryName.value = category.name;
  elements.categoryParent.value = category.parent_id ? String(category.parent_id) : "";
  elements.categoryDescription.value = category.description;
  elements.categoryAlias.value = category.custom_alias || "";
  elements.categoryCancel.hidden = false;
  elements.categoryName.focus();
}

function confirmDeletion(title, description, blocked = false) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "export-choice-dialog link-delete-dialog";
    dialog.setAttribute("aria-labelledby", "link-delete-title");
    dialog.setAttribute("aria-describedby", "link-delete-description");

    const icon = document.createElement("div");
    icon.className = "link-delete-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "!";
    const heading = document.createElement("h2");
    heading.id = "link-delete-title";
    heading.textContent = title;
    const message = document.createElement("p");
    message.id = "link-delete-description";
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
    cancel.textContent = blocked ? "Tutup" : "Batal";
    cancel.autofocus = true;
    cancel.addEventListener("click", () => finish(false));
    actions.append(cancel);
    if (!blocked) {
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.className = "button link-delete-confirm";
      confirm.textContent = "Ya, hapus";
      confirm.addEventListener("click", () => finish(true));
      actions.append(confirm);
    }
    dialog.append(icon, heading, message, actions);
    document.body.append(dialog);
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(false);
    });
    dialog.showModal();
  });
}

async function deleteCategory(category) {
  try {
    if (!await loadData()) return;
  } catch (error) {
    showError(error, "Data terbaru belum berhasil dimuat. ", true);
    return;
  }
  const currentCategory = state.categories.find((item) => item.id === category.id);
  if (!currentCategory) {
    showStatus("Topik sudah tidak tersedia. Daftar telah diperbarui.", true);
    return;
  }
  const children = state.categories.filter((item) => item.parent_id === currentCategory.id);
  const categoryIds = new Set([currentCategory.id, ...children.map((item) => item.id)]);
  const links = state.links.filter((item) => categoryIds.has(item.category_id));
  const hasOtherAdminLinks = links.some((item) => !item.can_edit);
  const type = currentCategory.parent_id === null ? "topik utama" : "topik rincian";
  const description = hasOtherAdminLinks
    ? `“${currentCategory.name}” berisi tautan milik admin lain. Tautan tersebut harus dihapus oleh pembuatnya terlebih dahulu.`
    : `Hapus ${type} “${currentCategory.name}”? Seluruh topik rincian dan tautan di dalamnya juga akan dihapus permanen, termasuk yang tidak terlihat dalam pencarian. Data terakhir: ${children.length} topik rincian dan ${links.length} tautan.`;
  if (!await confirmDeletion(
    hasOtherAdminLinks ? "Topik belum bisa dihapus" : "Hapus topik?",
    description,
    hasOtherAdminLinks,
  )) return;
  try {
    await requestJson(`/api/admin/link-categories/${currentCategory.id}`, {
      method: "DELETE",
      body: JSON.stringify({ confirm_contents: true }),
    });
    await refreshAfterMutation("Topik berhasil dihapus.");
  } catch (error) {
    showError(error);
  }
}

function categoryActions(category) {
  const actions = document.createElement("span");
  actions.className = "link-admin-tree-actions";
  const statusLabel = category.is_active ? "Nonaktifkan" : "Aktifkan";
  const statusButton = actionButton(statusLabel, () => changeCategoryStatus(category), true);
  statusButton.setAttribute("aria-label", `${statusLabel} topik ${category.name}`);
  actions.append(
    statusButton,
    actionButton("Edit", () => editCategory(category), true),
    actionButton("Hapus", () => deleteCategory(category), true),
  );
  return actions;
}

async function changeCategoryStatus(category) {
  try {
    await requestJson(`/api/admin/link-categories/${category.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !category.is_active }),
    });
    await refreshAfterMutation("Status topik diperbarui.");
  } catch (error) {
    showError(error);
  }
}

async function changeLinkStatus(link) {
  try {
    await requestJson(`/api/admin/links/${link.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !link.is_active }),
    });
    await refreshAfterMutation("Status tautan diperbarui.");
  } catch (error) {
    showError(error);
  }
}

function editLink(link) {
  state.missingSelections.delete("topik rincian");
  state.missingSelections.delete("tahun");
  updateSelectionWarning();
  elements.linkId.value = String(link.id);
  elements.linkYear.value = link.year === null || link.year === undefined
    ? ""
    : String(link.year);
  elements.linkCategory.value = String(link.category_id);
  elements.linkTitle.value = link.title;
  elements.linkUrl.value = link.url;
  elements.linkImageUrl.value = link.image_url || "";
  elements.linkIcon.value = link.icon || "";
  elements.linkDescription.value = link.description;
  elements.linkTags.value = link.tags.join(", ");
  elements.linkCancel.hidden = false;
  elements.linkTitle.focus();
}

async function deleteLink(link) {
  if (!await confirmDeletion(
    "Hapus tautan?",
    `Tautan “${link.title}” akan dihapus permanen dan tidak dapat dikembalikan.`,
  )) return;
  try {
    await requestJson(`/api/admin/links/${link.id}`, { method: "DELETE" });
    await refreshAfterMutation("Tautan berhasil dihapus.");
  } catch (error) {
    showError(error);
  }
}

function renderDirectory() {
  const matchingCategories = new Set(filteredCategories().map((category) => category.id));
  const visibleLinks = filteredLinks();
  const linksByCategory = new Map();
  for (const link of visibleLinks) {
    const categoryLinks = linksByCategory.get(link.category_id) || [];
    categoryLinks.push(link);
    linksByCategory.set(link.category_id, categoryLinks);
  }
  const fragment = document.createDocumentFragment();
  let visibleRootCount = 0;
  let visibleDetailCount = 0;
  for (const root of state.categories.filter((category) => category.parent_id === null)) {
    const rootMatches = matchingCategories.has(root.id);
    const children = state.categories.filter((category) => category.parent_id === root.id);
    const visibleChildren = children.filter((category) =>
      rootMatches
      || matchingCategories.has(category.id)
      || linksByCategory.has(category.id)
    );
    if (!rootMatches && visibleChildren.length === 0) continue;

    visibleRootCount += 1;
    visibleDetailCount += visibleChildren.length;
    const rootFolder = document.createElement("details");
    rootFolder.className = "link-admin-tree-folder link-admin-tree-folder-root";
    rootFolder.open = true;
    const rootHeading = document.createElement("summary");
    const rootName = document.createElement("span");
    rootName.className = "link-admin-tree-name";
    rootName.append(document.createTextNode("📁 "));
    rootName.append(document.createTextNode(root.name));
    const rootCount = document.createElement("small");
    rootCount.className = "link-admin-tree-count";
    rootCount.textContent = `${root.is_active ? "Aktif" : "Nonaktif"} · ${visibleChildren.length} topik rincian`;
    rootHeading.append(rootName, rootCount, categoryActions(root));
    rootFolder.append(rootHeading);

    const childList = document.createElement("div");
    childList.className = "link-admin-tree-children";
    if (visibleChildren.length === 0) {
      const empty = document.createElement("p");
      empty.className = "helper-text";
      empty.textContent = "Belum ada topik rincian.";
      childList.append(empty);
    }
    for (const category of visibleChildren) {
      const categoryLinks = linksByCategory.get(category.id) || [];
      const detailFolder = document.createElement("details");
      detailFolder.className = "link-admin-tree-folder link-admin-tree-folder-detail";
      detailFolder.open = Boolean(state.search);
      const detailHeading = document.createElement("summary");
      const detailName = document.createElement("span");
      detailName.className = "link-admin-tree-name";
      detailName.append(document.createTextNode("📁 "));
      detailName.append(document.createTextNode(category.name));
      const detailCount = document.createElement("small");
      detailCount.className = "link-admin-tree-count";
      const visibility = category.is_active && !root.is_active
        ? "Aktif (topik utama nonaktif)"
        : category.is_active ? "Aktif" : "Nonaktif";
      detailCount.textContent = `${visibility} · ${categoryLinks.length} tautan`;
      detailHeading.append(detailName, detailCount, categoryActions(category));
      detailFolder.append(detailHeading);

      const linkList = document.createElement("div");
      linkList.className = "link-admin-tree-links";
      if (categoryLinks.length === 0) {
        const empty = document.createElement("p");
        empty.className = "helper-text";
        empty.textContent = "Belum ada tautan.";
        linkList.append(empty);
      }
      for (const link of categoryLinks) {
        const row = document.createElement("article");
        row.className = "link-admin-tree-link";
        const details = document.createElement("div");
        const title = document.createElement("a");
        title.href = link.url;
        title.target = "_blank";
        title.rel = "noopener noreferrer";
        title.textContent = `🔗 ${link.title}`;
        const meta = document.createElement("p");
        meta.textContent = [
          `Tahun ${link.year || "belum ditentukan"}`,
          link.is_active && (!root.is_active || !category.is_active)
            ? "Aktif (topik nonaktif)"
            : link.is_active ? "Aktif" : "Nonaktif",
          link.can_edit ? "Dibuat oleh Anda" : "Dibuat admin lain",
        ].join(" · ");
        const timestamps = document.createElement("small");
        timestamps.textContent =
          `Waktu input: ${formatDateTime(link.created_at)} · Waktu update: ${formatDateTime(link.updated_at)}`;
        details.append(title, meta, timestamps);
        row.append(details, actionButton(
          link.is_active ? "Nonaktifkan" : "Aktifkan",
          () => changeLinkStatus(link),
        ));
        if (link.can_edit) {
          row.append(
            actionButton("Edit", () => editLink(link)),
            actionButton("Hapus", () => deleteLink(link)),
          );
        }
        linkList.append(row);
      }
      detailFolder.append(linkList);
      childList.append(detailFolder);
    }
    rootFolder.append(childList);
    fragment.append(rootFolder);
  }
  if (visibleRootCount === 0) {
    const empty = document.createElement("p");
    empty.className = "helper-text";
    empty.textContent = state.search
      ? "Tidak ada topik atau tautan yang cocok."
      : "Belum ada topik atau tautan.";
    fragment.append(empty);
  }
  elements.directory.replaceChildren(fragment);
  return {
    rootCount: visibleRootCount,
    detailCount: visibleDetailCount,
    linkCount: visibleLinks.length,
  };
}

async function loadData() {
  const requestId = ++state.requestId;
  let results;
  try {
    results = await Promise.all([
      requestJson("/api/admin/link-categories"),
      requestJson("/api/admin/links"),
      requestJson("/api/years"),
    ]);
  } catch (error) {
    if (requestId !== state.requestId) return false;
    throw error;
  }
  if (requestId !== state.requestId) return false;
  const [categoryResult, linkResult, yearResult] = results;
  if (!Array.isArray(categoryResult.categories)
      || categoryResult.categories.some((category) => typeof category.is_active !== "boolean")) {
    throw new Error("Status topik tidak tersedia. Perbarui backend dan mulai ulang layanan.");
  }
  state.categories = categoryResult.categories;
  state.links = linkResult.links;
  state.years = yearResult.years;
  renderCategories();
  renderSummary();
  const visible = renderDirectory();
  elements.searchStatus.textContent = state.search
    ? `${visible.rootCount} topik utama, ${visible.detailCount} topik rincian, dan ${visible.linkCount} tautan cocok.`
    : `${visible.rootCount} topik utama, ${visible.detailCount} topik rincian, dan ${visible.linkCount} tautan tersedia.`;
  elements.retry.hidden = true;
  elements.content.hidden = false;
  setMutationEnabled(true);
  return true;
}

async function refreshAfterMutation(message) {
  try {
    if (await loadData()) {
      showStatus(message);
      return true;
    }
    return false;
  } catch (error) {
    showError(error, `${message} Data belum berhasil dimuat ulang. `, true);
    return false;
  }
}

elements.categoryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = elements.categoryId.value;
  const isEditing = Boolean(id);
  const parentId = elements.categoryParent.value;
  const body = {
    name: elements.categoryName.value,
    description: elements.categoryDescription.value,
    parent_id: parentId ? Number(parentId) : null,
    custom_alias: elements.categoryAlias.value.trim(),
  };
  try {
    await requestJson(
      id ? `/api/admin/link-categories/${id}` : "/api/admin/link-categories",
      { method: id ? "PATCH" : "POST", body: JSON.stringify(body) },
    );
    resetCategoryForm();
    if (!await refreshAfterMutation("Topik berhasil disimpan.") || isEditing) return;
  } catch (error) {
    showError(error);
  }
});

elements.linkForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.linkYear.value) {
    showStatus("Pilih tahun yang tersedia sebelum menyimpan tautan.", true);
    return;
  }
  const id = elements.linkId.value;
  const isEditing = Boolean(id);
  const body = {
    year: Number(elements.linkYear.value),
    category_id: Number(elements.linkCategory.value),
    title: elements.linkTitle.value,
    url: elements.linkUrl.value,
    image_url: elements.linkImageUrl.value,
    icon: elements.linkIcon.value,
    description: elements.linkDescription.value,
    tags: elements.linkTags.value.split(",").map((tag) => tag.trim()).filter(Boolean),
  };
  try {
    await requestJson(
      id ? `/api/admin/links/${id}` : "/api/admin/links",
      { method: id ? "PATCH" : "POST", body: JSON.stringify(body) },
    );
    resetLinkForm();
    await refreshAfterMutation(isEditing
      ? "Tautan berhasil diperbarui."
      : "Tautan berhasil disimpan. Tautan baru berstatus nonaktif.");
  } catch (error) {
    showError(error);
  }
});

elements.categoryCancel.addEventListener("click", resetCategoryForm);
elements.linkCancel.addEventListener("click", resetLinkForm);
elements.categoryParent.addEventListener("change", () => {
  elements.categoryParent.setCustomValidity("");
  state.missingSelections.delete("topik utama");
  updateSelectionWarning();
});
elements.linkCategory.addEventListener("change", () => {
  state.missingSelections.delete("topik rincian");
  updateSelectionWarning();
});
elements.linkYear.addEventListener("change", () => {
  state.missingSelections.delete("tahun");
  updateSelectionWarning();
});
elements.retry.addEventListener("click", () => { void initialize(); });
elements.adminMode.addEventListener("change", () => {
  if (elements.adminMode.value === "tautan") void initialize();
});
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.search.value.trim();
  elements.searchClear.hidden = !state.search;
  const visible = renderDirectory();
  elements.searchStatus.textContent = `${visible.rootCount} topik utama, ${visible.detailCount} topik rincian, dan ${visible.linkCount} tautan cocok.`;
});
elements.searchClear.addEventListener("click", () => {
  elements.search.value = "";
  state.search = "";
  elements.searchClear.hidden = true;
  const visible = renderDirectory();
  elements.searchStatus.textContent = `${visible.rootCount} topik utama, ${visible.detailCount} topik rincian, dan ${visible.linkCount} tautan tersedia.`;
});

async function initialize() {
  try {
    const session = await requestJson("/api/auth/session");
    state.csrfToken = session.csrf_token;
    if (!session.authenticated) {
      setMutationEnabled(false);
      elements.login.hidden = false;
      elements.retry.hidden = false;
      showStatus("Sesi admin belum aktif.");
      return;
    }
    if (await loadData()) {
      elements.login.hidden = true;
      showStatus(`Login sebagai ${session.username}.`);
    }
  } catch (error) {
    showError(error, "", true);
  }
}

if (elements.adminMode.value === "tautan") void initialize();
})();
