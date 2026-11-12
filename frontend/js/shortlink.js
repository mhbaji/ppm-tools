(() => {
"use strict";

const elements = {
  form: document.querySelector("#shortlink-form"),
  target: document.querySelector("#shortlink-target"),
  alias: document.querySelector("#shortlink-alias"),
  title: document.querySelector("#shortlink-title"),
  website: document.querySelector("#shortlink-website"),
  submit: document.querySelector("#shortlink-submit"),
  status: document.querySelector("#shortlink-status"),
  result: document.querySelector("#shortlink-result"),
  resultLink: document.querySelector("#shortlink-result-link"),
};
let formToken = "";
let formTimer;

async function fetchJson(url, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
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

async function prepareForm() {
  elements.submit.disabled = true;
  elements.status.classList.remove("is-error");
  elements.status.textContent = "Menyiapkan pemeriksaan anti-bot...";
  try {
    const result = await fetchJson("/api/shortlinks/form-token");
    formToken = result.form_token;
    elements.status.textContent = "Form siap. Pengiriman tersedia beberapa detik setelah halaman dibuka.";
    window.clearTimeout(formTimer);
    formTimer = window.setTimeout(() => {
      elements.submit.disabled = false;
      elements.status.textContent = "Form siap digunakan.";
    }, 2100);
  } catch (error) {
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.form.reportValidity() || !formToken) return;
  elements.submit.disabled = true;
  elements.status.classList.remove("is-error");
  elements.status.textContent = "Membuat shortlink...";
  elements.result.hidden = true;
  try {
    const result = await fetchJson("/api/shortlinks", {
      method: "POST",
      body: JSON.stringify({
        target_url: elements.target.value.trim(),
        alias: elements.alias.value.trim(),
        title: elements.title.value.trim(),
        website: elements.website.value,
        form_token: formToken,
      }),
    });
    const shortUrl = new URL(result.shortlink.short_url, window.location.origin);
    elements.resultLink.href = shortUrl.href;
    elements.resultLink.textContent = shortUrl.href;
    elements.result.hidden = false;
    elements.status.textContent = "Shortlink berhasil dibuat.";
    elements.form.reset();
    formToken = "";
    await prepareForm();
  } catch (error) {
    elements.submit.disabled = false;
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
});

const shortlinkContent = document.querySelector("#public-shortlink-content");
if (!shortlinkContent || !shortlinkContent.hidden) void prepareForm();
})();
