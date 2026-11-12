(() => {
"use strict";

const elements = {
  mode: document.querySelector("#link-mode-select"),
  directoryContent: document.querySelector("#link-directory-content"),
  shortlinkContent: document.querySelector("#public-shortlink-content"),
  title: document.querySelector("#link-page-title"),
  description: document.querySelector("#link-page-description"),
  breadcrumb: document.querySelector("#link-breadcrumb"),
  summaryPanel: document.querySelector("#link-summary-panel"),
  summary: document.querySelector("#link-summary"),
  status: document.querySelector("#link-directory-status"),
  topics: document.querySelector("#link-topics"),
  cards: document.querySelector("#link-cards"),
  searchForm: document.querySelector("#link-search-form"),
  search: document.querySelector("#link-search"),
  searchClear: document.querySelector("#link-search-clear"),
  pagination: document.querySelector("#link-pagination"),
  pageIndicator: document.querySelector("#link-page-indicator"),
  previous: document.querySelector("#link-previous"),
  next: document.querySelector("#link-next"),
};
const initialParams = new URLSearchParams(location.search);
const categoryId = initialParams.get("category_id");
const topicId = initialParams.get("topic_id");
const customAliasPrefix = location.pathname.startsWith("/t/")
  ? "/t/"
  : location.pathname.startsWith("/tautan/")
    ? "/tautan/"
    : "";
const customAlias = customAliasPrefix
  ? location.pathname.slice(customAliasPrefix.length)
  : "";
const isShortlinkMode = location.pathname === "/shortlink";
const requestedOffset = Number(initialParams.get("offset") || 0);
const state = {
  offset: Number.isSafeInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0,
  limit: 50,
  total: 0,
  requestId: 0,
  search: new URLSearchParams(location.search).get("q") || "",
};
elements.mode.value = isShortlinkMode ? "/shortlink" : "/tautan";
elements.directoryContent.hidden = isShortlinkMode;
elements.shortlinkContent.hidden = !isShortlinkMode;
document.querySelector("[data-link-hub]").setAttribute("aria-current", "page");
elements.search.value = state.search;
elements.searchClear.hidden = !state.search;

function updateDirectoryUrl() {
  const params = new URLSearchParams(location.search);
  if (state.search) params.set("q", state.search);
  else params.delete("q");
  if (state.offset) params.set("offset", String(state.offset));
  else params.delete("offset");
  const query = params.toString();
  history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}`);
}

function renderBreadcrumb(items) {
  const fragment = document.createDocumentFragment();
  items.forEach((item, index) => {
    if (index) fragment.append(document.createTextNode(" / "));
    if (!item.href) {
      fragment.append(document.createTextNode(item.name));
      return;
    }
    const link = document.createElement("a");
    link.href = item.href;
    link.textContent = item.name;
    if (item.current) link.setAttribute("aria-current", "page");
    fragment.append(link);
  });
  elements.breadcrumb.replaceChildren(fragment);
}

function topicHref(topic) {
  return topic.custom_alias
    ? `/t/${encodeURIComponent(topic.custom_alias)}`
    : `/tautan?topic_id=${encodeURIComponent(topic.id)}`;
}

function categoryHref(category) {
  return category.custom_alias
    ? `/t/${encodeURIComponent(category.custom_alias)}`
    : `/tautan?category_id=${encodeURIComponent(category.id)}`;
}

function topicBreadcrumb(topic, category = null) {
  const items = [{ name: "Tautan", href: "/tautan" }];
  if (topic) {
    items.push({
      name: topic.name,
      href: topicHref(topic),
      current: !category,
    });
  }
  if (category) {
    items.push({
      name: category.name,
      href: categoryHref(category),
      current: true,
    });
  }
  return items;
}

function setPageTitle(title) {
  elements.title.textContent = title;
  document.title = title === "Topik dan Tautan" || title === "Hasil pencarian"
    ? "Tautan dan Pendekin | PPM Tools"
    : `${title} | Tautan dan Pendekin | PPM Tools`;
}

function renderSummary(summary) {
  const entries = [
    ["Topik Utama", summary.main_topics],
    ["Topik Rincian", summary.detail_topics],
    ["Tautan", summary.links],
  ];
  const fragment = document.createDocumentFragment();
  for (const [labelText, value] of entries) {
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
  elements.summaryPanel.hidden = false;
}

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

function cardLink(link, options = {}) {
  const card = document.createElement("article");
  card.className = `link-card${options.compact ? " link-card-compact" : ""}`;
  const date = document.createElement("small");
  date.className = "link-card-date";
  date.textContent = new Date(
    link.published_at.replace(" ", "T"),
  ).toLocaleDateString("id-ID");
  if (link.icon) {
    const icon = document.createElement("span");
    icon.className = "link-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = link.icon;
    card.append(icon);
  }
  if (link.image_url) {
    const image = document.createElement("img");
    image.src = link.image_url;
    image.alt = "";
    image.loading = "lazy";
    card.append(image);
  }
  const title = document.createElement("h3");
  const anchor = document.createElement("a");
  anchor.href = link.url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  anchor.textContent = link.title;
  title.append(anchor);
  const description = document.createElement("p");
  description.textContent = link.description || "";
  const tagList = document.createElement("div");
  tagList.className = "link-tags";
  for (const tag of link.tags || []) {
    const chip = document.createElement("span");
    chip.className = "tag-chip";
    chip.textContent = tag;
    tagList.append(chip);
  }
  card.append(date, title, description, tagList);
  if (options.showPath && link.topic && link.category) {
    const path = document.createElement("small");
    path.className = "link-card-path";
    path.textContent = `${link.topic.name} / ${link.category.name}`;
    card.append(path);
  }
  return card;
}

function renderDirectory(topics) {
  const fragment = document.createDocumentFragment();
  for (const topic of topics) {
    const card = document.createElement("article");
    card.className = "link-topic-card";
    const title = document.createElement("h2");
    const titleLink = document.createElement("a");
    titleLink.href = topicHref(topic);
    titleLink.textContent = topic.name;
    title.append(titleLink);
    const description = document.createElement("p");
    description.className = "link-topic-summary";
    description.textContent = topic.description || "";
    const detailList = document.createElement("div");
    detailList.className = "link-subtopics";
    for (const subtopic of topic.subtopics) {
      const detail = document.createElement("article");
      detail.className = "link-subtopic-card";
      const heading = document.createElement("h3");
      const link = document.createElement("a");
      link.href = categoryHref(subtopic);
      link.textContent = subtopic.name;
      heading.append(link);
      detail.append(heading);
      if (subtopic.description) {
        const detailDescription = document.createElement("p");
        detailDescription.textContent = subtopic.description;
        detail.append(detailDescription);
      }
      detailList.append(detail);
    }
    const summaryHeading = document.createElement("h3");
    summaryHeading.className = "link-topic-summary-heading";
    summaryHeading.textContent = "Ringkasan topik utama";
    card.append(title, summaryHeading, description, detailList);
    fragment.append(card);
  }
  elements.topics.replaceChildren(fragment);
}

function renderPagination() {
  const pageCount = Math.ceil(state.total / state.limit);
  elements.pagination.hidden = pageCount <= 1;
  elements.pageIndicator.textContent = pageCount
    ? `Halaman ${Math.floor(state.offset / state.limit) + 1} dari ${pageCount}`
    : "";
  elements.previous.disabled = state.offset === 0;
  elements.next.disabled = state.offset + state.limit >= state.total;
}

async function load() {
  const requestId = ++state.requestId;
  elements.status.classList.remove("is-error");
  elements.status.textContent = "Memuat tautan...";
  try {
    if (categoryId || customAlias) {
      const params = customAlias
        ? new URLSearchParams({ alias: customAlias })
        : new URLSearchParams({ category_id: categoryId });
      params.set("limit", String(state.limit));
      params.set("offset", String(state.offset));
      if (state.search) params.set("q", state.search);
      const result = await fetchJson(`/api/link-directory?${params}`);
      if (requestId !== state.requestId) return;
      elements.summaryPanel.hidden = true;
      elements.topics.replaceChildren();
      if (result.category) {
        setPageTitle(result.category.name);
        elements.description.textContent = result.category.description || "";
        renderBreadcrumb(topicBreadcrumb(result.category.parent, result.category));
        const cards = document.createDocumentFragment();
        for (const link of result.links) cards.append(cardLink(link));
        elements.cards.replaceChildren(cards);
        state.total = result.total;
        renderPagination();
        elements.status.textContent = result.total
          ? `${result.total} tautan tersedia.`
          : state.search
            ? "Tidak ada tautan yang cocok dengan pencarian."
            : "Belum ada tautan aktif pada topik ini.";
      } else if (result.selected_topic) {
        setPageTitle(result.selected_topic.name);
        elements.description.textContent = "Hasil pada topik utama yang dipilih.";
        renderBreadcrumb(topicBreadcrumb(result.selected_topic));
        const cards = document.createDocumentFragment();
        for (const link of result.links) cards.append(cardLink(link, { showPath: true }));
        elements.cards.replaceChildren(cards);
        state.total = result.total;
        renderPagination();
        elements.status.textContent = result.total
          ? `${result.total} hasil ditemukan.`
          : "Tidak ada tautan yang cocok dengan pencarian.";
      } else if (result.topics) {
        const topic = result.topics[0];
        if (!topic) throw new Error("Topik utama tidak ditemukan.");
        renderDirectory(result.topics);
        elements.cards.replaceChildren();
        setPageTitle(topic.name);
        elements.description.textContent = topic.description || "";
        renderBreadcrumb(topicBreadcrumb(topic));
        elements.pagination.hidden = true;
        elements.status.textContent = "Pilih subtopik untuk melihat seluruh tautan.";
      } else {
        throw new Error("Respons topik tidak valid.");
      }
    } else if (state.search) {
      const params = new URLSearchParams({
        q: state.search,
        limit: String(state.limit),
        offset: String(state.offset),
      });
      if (topicId) params.set("topic_id", topicId);
      const result = await fetchJson(`/api/link-directory?${params}`);
      if (requestId !== state.requestId) return;
      elements.summaryPanel.hidden = true;
      const selectedTopic = result.selected_topic;
      setPageTitle(selectedTopic?.name || "Hasil pencarian");
      elements.description.textContent = selectedTopic
        ? "Hasil pada topik utama yang dipilih."
        : "Tautan aktif yang cocok pada semua topik.";
      renderBreadcrumb(selectedTopic
        ? topicBreadcrumb(selectedTopic)
        : [{ name: "Tautan", href: "/tautan" }, { name: "Hasil pencarian", current: true }]);
      elements.topics.replaceChildren();
      const cards = document.createDocumentFragment();
      for (const link of result.links) {
        cards.append(cardLink(link, { showPath: true }));
      }
      elements.cards.replaceChildren(cards);
      state.total = result.total;
      renderPagination();
      elements.status.textContent = result.total
        ? `${result.total} hasil ditemukan.`
        : "Tidak ada tautan yang cocok dengan pencarian.";
    } else {
      elements.pagination.hidden = true;
      const params = topicId ? `?${new URLSearchParams({ topic_id: topicId })}` : "";
      const result = await fetchJson(`/api/link-directory${params}`);
      if (requestId !== state.requestId) return;
      const topics = topicId
        ? result.topics.filter((topic) => String(topic.id) === topicId)
        : result.topics;
      if (topicId && !topics.length) throw new Error("Topik utama tidak ditemukan.");
      if (topicId) elements.summaryPanel.hidden = true;
      else renderSummary(result.summary);
      renderDirectory(topics);
      elements.cards.replaceChildren();
      if (topicId && topics.length) {
        setPageTitle(topics[0].name);
        renderBreadcrumb(topicBreadcrumb(topics[0]));
        elements.description.textContent = topics[0].description || "";
      } else {
        setPageTitle("Topik dan Tautan");
        renderBreadcrumb([]);
        elements.description.textContent = "Jelajahi topik utama dan topik rincian.";
      }
      elements.status.textContent = topics.length
        ? topicId
          ? "Pilih subtopik untuk melihat seluruh tautan."
          : "Pilih topik atau subtopik untuk melihat rincian tautan."
        : "Belum ada topik publik.";
    }
  } catch (error) {
    if (requestId !== state.requestId) return;
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
}

elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = elements.search.value.trim();
  state.offset = 0;
  updateDirectoryUrl();
  elements.searchClear.hidden = !state.search;
  void load();
});
elements.searchClear.addEventListener("click", () => {
  elements.search.value = "";
  state.search = "";
  state.offset = 0;
  updateDirectoryUrl();
  elements.searchClear.hidden = true;
  void load();
});
elements.previous.addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.limit);
  updateDirectoryUrl();
  void load();
});
elements.next.addEventListener("click", () => {
  if (state.offset + state.limit < state.total) {
    state.offset += state.limit;
    updateDirectoryUrl();
    void load();
  }
});
elements.mode.addEventListener("change", () => {
  window.location.assign(`${elements.mode.value}${location.search}`);
});
if (!isShortlinkMode) void load();
})();
