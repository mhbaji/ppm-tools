"use strict";

window.initAdminUploadList = function initAdminUploadList(options) {
  const elements = {
    search: document.querySelector(options.search),
    pageSize: document.querySelector(options.pageSize),
    rows: document.querySelector(options.rows),
    status: document.querySelector(options.status),
    previous: document.querySelector(options.previous),
    next: document.querySelector(options.next),
    pageIndicator: document.querySelector(options.pageIndicator),
  };
  const state = { offset: 0, limit: 10, total: 0, requestId: 0 };

  function setStatus(message, isError = false) {
    elements.status.textContent = message;
    elements.status.classList.toggle("is-error", isError);
  }

  function formatSize(size) {
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  function appendCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value;
    row.append(cell);
    return cell;
  }

  async function load() {
    const requestId = ++state.requestId;
    const parameters = new URLSearchParams({
      kind: options.kind,
      q: elements.search.value.trim(),
      limit: String(state.limit),
      offset: String(state.offset),
    });
    elements.rows.replaceChildren();
    elements.previous.disabled = true;
    elements.next.disabled = true;
    setStatus("Memuat daftar file...");
    try {
      const response = await fetch(`/api/admin/uploads?${parameters}`, {
        headers: { Accept: "application/json" },
      });
      const result = await response.json();
      if (response.status === 401) window.location.replace("/login");
      if (!response.ok) {
        throw new Error(result.error || `Permintaan gagal (${response.status}).`);
      }
      if (requestId !== state.requestId) return;
      state.total = result.total;
      const fragment = document.createDocumentFragment();
      for (const file of result.items) {
        const row = document.createElement("tr");
        appendCell(row, file.filename);
        appendCell(row, file.file_type);
        appendCell(row, formatSize(file.file_size));
        appendCell(
          row,
          new Date(file.uploaded_at.replace(" ", "T")).toLocaleString("id-ID"),
        );
        const actions = document.createElement("td");
        actions.className = "uploaded-file-actions";
        const download = document.createElement("a");
        download.className = "button button-secondary";
        download.href = file.download_url;
        download.textContent = "Unduh";
        const remove = document.createElement("button");
        remove.className = "button button-secondary";
        remove.type = "button";
        remove.textContent = "Hapus";
        remove.setAttribute("aria-label", `Hapus file ${file.filename}`);
        remove.addEventListener("click", () => void deleteFile(file));
        actions.append(download, remove);
        row.append(actions);
        fragment.append(row);
      }
      elements.rows.replaceChildren(fragment);
      const pageCount = Math.ceil(state.total / state.limit);
      elements.pageIndicator.textContent = state.total
        ? `Halaman ${Math.floor(state.offset / state.limit) + 1} dari ${pageCount}`
        : "";
      elements.previous.disabled = state.offset === 0;
      elements.next.disabled = state.offset + state.limit >= state.total;
      setStatus(
        state.total
          ? `${state.total.toLocaleString("id-ID")} file tersimpan.`
          : "Belum ada file yang cocok.",
      );
    } catch (error) {
      if (requestId !== state.requestId) return;
      elements.pageIndicator.textContent = "";
      setStatus(error.message, true);
    }
  }

  async function deleteFile(file) {
    if (!window.confirm(`Hapus file "${file.filename}" dari storage?`)) return;
    try {
      const response = await fetch(`/api/admin/uploads/${file.id}`, {
        method: "DELETE",
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": options.csrfToken(),
        },
      });
      const result = await response.json();
      if (response.status === 401) window.location.replace("/login");
      if (!response.ok) {
        throw new Error(result.error || `Penghapusan gagal (${response.status}).`);
      }
      state.offset = Math.min(
        state.offset,
        Math.max(0, Math.ceil((state.total - 1) / state.limit) - 1) * state.limit,
      );
      await load();
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  let searchTimer = 0;
  elements.search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.offset = 0;
      void load();
    }, 250);
  });
  elements.pageSize.addEventListener("change", () => {
    state.limit = Number(elements.pageSize.value);
    state.offset = 0;
    void load();
  });
  elements.previous.addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    void load();
  });
  elements.next.addEventListener("click", () => {
    if (state.offset + state.limit < state.total) {
      state.offset += state.limit;
      void load();
    }
  });

  void load();
  return load;
};
