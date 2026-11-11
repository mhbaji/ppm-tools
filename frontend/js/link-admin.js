"use strict";

const elements = {
  status: document.querySelector("#link-admin-status"),
  login: document.querySelector("#link-admin-login"),
  content: document.querySelector("#link-admin-content"),
  summary: document.querySelector("#link-admin-summary"),
  categoryForm: document.querySelector("#category-form"),
  categoryId: document.querySelector("#category-id"),
  categoryName: document.querySelector("#category-name"),
  categoryParent: document.querySelector("#category-parent"),
  categoryDescription: document.querySelector("#category-description"),
  categoryCancel: document.querySelector("#category-cancel"),
  linkForm: document.querySelector("#link-form"),
  linkId: document.querySelector("#link-id"),
  linkYear: document.querySelector("#link-year"),
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

const state = { csrfToken: "", categories: [], links: [], years: [], search: "" };

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
  if (!response.ok) throw new Error(result.error || `Permintaan gagal (${response.status}).`);
  return result;
}

function showStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("is-error", isError);
}

function resetCategoryForm() {
  elements.categoryForm.reset();
  elements.categoryId.value = "";
  elements.categoryCancel.hidden = true;
}

function resetLinkForm() {
  elements.linkForm.reset();
  elements.linkId.value = "";
  elements.linkCancel.hidden = true;
}

function renderCategories() {
  const roots = state.categories.filter((category) => category.parent_id === null);
  elements.categoryParent.replaceChildren(new Option("Topik utama", ""));
  for (const root of roots) {
    elements.categoryParent.add(new Option(root.name, String(root.id)));
  }
  elements.linkCategory.replaceChildren(new Option("Pilih topik rincian", ""));
  for (const category of state.categories.filter((item) => item.parent_id !== null)) {
    const parent = state.categories.find((item) => item.id === category.parent_id);
    elements.linkCategory.add(
      new Option(`${parent?.name || "Topik"} / ${category.name}`, String(category.id)),
    );
  }
  elements.linkYear.replaceChildren(
    new Option(state.years.length ? "Pilih tahun" : "Tahun belum tersedia", ""),
  );
  for (const year of state.years) {
    elements.linkYear.add(new Option(String(year), String(year)));
  }
  elements.linkYear.disabled = state.years.length === 0;
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
  elements.categoryId.value = String(category.id);
  elements.categoryName.value = category.name;
  elements.categoryParent.value = category.parent_id ? String(category.parent_id) : "";
  elements.categoryDescription.value = category.description;
  elements.categoryCancel.hidden = false;
  elements.categoryName.focus();
}

async function deleteCategory(category) {
  if (!window.confirm(`Hapus topik “${category.name}”?`)) return;
  try {
    await requestJson(`/api/admin/link-categories/${category.id}`, { method: "DELETE" });
    await loadData();
    showStatus("Topik berhasil dihapus.");
  } catch (error) {
    showStatus(error.message, true);
  }
}

function categoryActions(category) {
  const actions = document.createElement("span");
  actions.className = "link-admin-tree-actions";
  actions.append(
    actionButton("Edit", () => editCategory(category), true),
    actionButton("Hapus", () => deleteCategory(category), true),
  );
  return actions;
}

async function changeLinkStatus(link) {
  try {
    await requestJson(`/api/admin/links/${link.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !link.is_active }),
    });
    await loadData();
    showStatus("Status tautan diperbarui.");
  } catch (error) {
    showStatus(error.message, true);
  }
}

function editLink(link) {
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
  if (!window.confirm(`Hapus tautan “${link.title}”?`)) return;
  try {
    await requestJson(`/api/admin/links/${link.id}`, { method: "DELETE" });
    await loadData();
    showStatus("Tautan berhasil dihapus.");
  } catch (error) {
    showStatus(error.message, true);
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
    rootCount.textContent = `${visibleChildren.length} topik rincian`;
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
      detailCount.textContent = `${categoryLinks.length} tautan`;
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
          link.is_active ? "Aktif" : "Nonaktif",
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
  const [categoryResult, linkResult, yearResult] = await Promise.all([
    requestJson("/api/admin/link-categories"),
    requestJson("/api/admin/links"),
    requestJson("/api/years"),
  ]);
  state.categories = categoryResult.categories;
  state.links = linkResult.links;
  state.years = yearResult.years;
  renderCategories();
  renderSummary();
  const visible = renderDirectory();
  elements.searchStatus.textContent = state.search
    ? `${visible.rootCount} topik utama, ${visible.detailCount} topik rincian, dan ${visible.linkCount} tautan cocok.`
    : `${visible.rootCount} topik utama, ${visible.detailCount} topik rincian, dan ${visible.linkCount} tautan tersedia.`;
}

elements.categoryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = elements.categoryId.value;
  const parentId = elements.categoryParent.value;
  const body = {
    name: elements.categoryName.value,
    description: elements.categoryDescription.value,
    parent_id: parentId ? Number(parentId) : null,
  };
  try {
    await requestJson(
      id ? `/api/admin/link-categories/${id}` : "/api/admin/link-categories",
      { method: id ? "PATCH" : "POST", body: JSON.stringify(body) },
    );
    resetCategoryForm();
    await loadData();
    showStatus("Topik berhasil disimpan.");
  } catch (error) {
    showStatus(error.message, true);
  }
});

elements.linkForm.addEventListener("submit", async (event) => {
  event.preventDefault();
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
    await loadData();
    showStatus(isEditing
      ? "Tautan berhasil diperbarui."
      : "Tautan berhasil disimpan. Tautan baru berstatus nonaktif.");
  } catch (error) {
    showStatus(error.message, true);
  }
});

elements.categoryCancel.addEventListener("click", resetCategoryForm);
elements.linkCancel.addEventListener("click", resetLinkForm);
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
      elements.login.hidden = false;
      showStatus("Sesi admin belum aktif.");
      return;
    }
    elements.content.hidden = false;
    await loadData();
    showStatus(`Login sebagai ${session.username}.`);
  } catch (error) {
    showStatus(error.message, true);
  }
}

void initialize();
