"use strict";

const elements = {
  period: document.querySelector("#statistics-period"),
  status: document.querySelector("#statistics-status"),
  range: document.querySelector("#statistics-range"),
  identity: document.querySelector("#statistics-identity"),
  logout: document.querySelector("#logout-button"),
  webTotal: document.querySelector("#web-statistics-total"),
  webLine: document.querySelector("#web-statistics-line"),
  webStart: document.querySelector("#web-statistics-start"),
  webEnd: document.querySelector("#web-statistics-end"),
  webTop: document.querySelector("#web-statistics-top"),
  apiTotal: document.querySelector("#api-statistics-total"),
  apiLine: document.querySelector("#api-statistics-line"),
  apiStart: document.querySelector("#api-statistics-start"),
  apiEnd: document.querySelector("#api-statistics-end"),
  apiTop: document.querySelector("#api-statistics-top"),
};
const state = { csrfToken: "", requestId: 0 };

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
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

function formatNumber(value) {
  return new Intl.NumberFormat("id-ID").format(value);
}

function formatBucket(value, resolution) {
  if (!value) return "";
  const normalized = resolution === "day"
    ? `${value}T00:00:00Z`
    : resolution === "hour"
      ? `${value}:00Z`
      : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("id-ID", {
      timeZone: "UTC",
      dateStyle: resolution === "day" ? "medium" : undefined,
      timeStyle: resolution === "day" ? undefined : "short",
    }).format(date);
}

function drawChart(line, points, resolution, title) {
  const values = points.map((point) => point.count);
  const max = Math.max(1, ...values);
  const coordinates = values.map((value, index) => {
    const x = values.length < 2 ? 500 : 20 + (index / (values.length - 1)) * 960;
    const y = 200 - (value / max) * 180;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  line.setAttribute("points", coordinates.join(" "));
  const chart = line.closest("svg");
  chart.setAttribute(
    "aria-label",
    `${title}: ${formatNumber(values.reduce((sum, value) => sum + value, 0))} request; ${points.length} interval UTC.`,
  );
  return {
    start: formatBucket(points[0]?.bucket, resolution),
    end: formatBucket(points[points.length - 1]?.bucket, resolution),
  };
}

function renderTopList(container, routes) {
  const fragment = document.createDocumentFragment();
  for (const item of routes) {
    const row = document.createElement("li");
    const route = document.createElement("code");
    route.textContent = item.route;
    const count = document.createElement("strong");
    count.textContent = formatNumber(item.count);
    row.append(route, count);
    fragment.append(row);
  }
  if (!routes.length) {
    const empty = document.createElement("li");
    empty.textContent = "Belum ada request pada periode ini.";
    fragment.append(empty);
  }
  container.replaceChildren(fragment);
}

function renderReport(prefix, report, resolution) {
  const isWeb = prefix === "web";
  const line = isWeb ? elements.webLine : elements.apiLine;
  const total = isWeb ? elements.webTotal : elements.apiTotal;
  const start = isWeb ? elements.webStart : elements.apiStart;
  const end = isWeb ? elements.webEnd : elements.apiEnd;
  const top = isWeb ? elements.webTop : elements.apiTop;
  total.textContent = formatNumber(report.total);
  const axis = drawChart(
    line,
    report.series,
    resolution,
    isWeb ? "Request halaman web" : "Request API",
  );
  start.textContent = axis.start;
  end.textContent = axis.end;
  renderTopList(top, report.top_routes);
}

async function loadStatistics() {
  const currentRequestId = ++state.requestId;
  elements.status.classList.remove("is-error");
  elements.status.textContent = "Memuat statistik...";
  try {
    const result = await fetchJson(
      `/api/admin/statistics?period=${encodeURIComponent(elements.period.value)}`,
    );
    if (currentRequestId !== state.requestId) return;
    renderReport("web", result.web, result.resolution);
    renderReport("api", result.api, result.resolution);
    elements.range.textContent =
      `Rentang ${result.since} hingga ${result.until} (${result.timezone}).`;
    elements.status.textContent = "Statistik berhasil dimuat.";
  } catch (error) {
    if (currentRequestId !== state.requestId) return;
    elements.status.textContent = error.status === 401
      ? "Sesi admin berakhir. Silakan login kembali."
      : error.message;
    elements.status.classList.add("is-error");
  }
}

elements.period.addEventListener("change", () => void loadStatistics());
async function initialize() {
  try {
    const auth = await fetchJson("/api/auth/session");
    state.csrfToken = auth.csrf_token;
    if (!auth.authenticated) {
      window.location.replace("/login");
      return;
    }
    elements.identity.textContent = `Login sebagai ${auth.username}`;
    await loadStatistics();
  } catch (error) {
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
}

elements.logout.addEventListener("click", async () => {
  elements.logout.disabled = true;
  try {
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "X-CSRF-Token": state.csrfToken, Accept: "application/json" },
    });
    if (!response.ok) throw new Error("Gagal keluar dari sesi admin.");
    window.location.replace("/login");
  } catch (error) {
    elements.logout.disabled = false;
    elements.status.textContent = error.message;
    elements.status.classList.add("is-error");
  }
});
void initialize();
