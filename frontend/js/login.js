"use strict";

const form = document.querySelector("#login-form");
const statusMessage = document.querySelector("#login-status");
const submitButton = document.querySelector("#login-button");
let csrfToken = "";

function showStatus(message, isError = false) {
  statusMessage.textContent = message;
  statusMessage.classList.toggle("is-error", isError);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  let body = {};
  try {
    body = await response.json();
  } catch {
    if (response.ok) throw new Error("Respons server tidak valid.");
  }
  if (!response.ok) throw new Error(body.error || `Permintaan gagal (${response.status}).`);
  return body;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  showStatus("");
  try {
    const formData = new FormData(form);
    const result = await fetchJson("/api/auth/login", {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken },
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password"),
      }),
    });
    csrfToken = result.csrf_token;
    window.location.assign("/admin/dashboard");
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    submitButton.disabled = false;
  }
});

async function initializeLogin() {
  try {
    const result = await fetchJson("/api/auth/session");
    csrfToken = result.csrf_token;
    if (result.authenticated) {
      window.location.replace("/admin/dashboard");
      return;
    }
    submitButton.disabled = false;
  } catch (error) {
    showStatus(error.message, true);
    submitButton.disabled = true;
  }
}

void initializeLogin();
