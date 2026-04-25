// Static-data PWA. All prices come from JSON files in ./data/, refreshed
// hourly by a GitHub Actions cron job.

const DATA_DIR = "data";
const RADIUS_KEY = "costcoGas.radius";

const $ = (id) => document.getElementById(id);
const els = {
  form: $("search-form"),
  zip: $("zip"),
  radius: $("radius"),
  fetchBtn: $("fetch-btn"),
  locateBtn: $("locate-btn"),
  status: $("status"),
  dataMeta: $("data-meta"),
  results: $("results"),
  resultsBody: document.querySelector("#results-table tbody"),
  resultsTitle: $("results-title"),
  snapshotMeta: $("snapshot-meta"),
  historySection: $("history-section"),
  historyCount: $("history-count"),
  historyChart: $("history-chart"),
};

let index = null;
let currentSnapshot = null;

// Restore previous radius selection.
const savedRadius = localStorage.getItem(RADIUS_KEY);
if (savedRadius && [...els.radius.options].some((o) => o.value === savedRadius)) {
  els.radius.value = savedRadius;
}

function setStatus(msg, kind = "") {
  els.status.textContent = msg;
  els.status.className = "status" + (kind ? " " + kind : "");
}

function setBusy(busy) {
  els.fetchBtn.disabled = busy || !index;
  els.locateBtn.disabled = busy || !index;
}

async function fetchJSON(path) {
  const resp = await fetch(`${path}?_=${Date.now()}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status}`);
  return resp.json();
}

async function loadIndex() {
  setStatus("Loading available locations…");
  try {
    index = await fetchJSON(`${DATA_DIR}/index.json`);
  } catch (err) {
    setStatus(`Could not load location index: ${err.message}`, "err");
    return;
  }
  if (!index.zips || !index.zips.length) {
    setStatus("No locations configured yet. Add ZIPs to costco_gas/config.json.", "err");
    return;
  }
  els.zip.innerHTML = "";
  for (const z of index.zips) {
    const opt = document.createElement("option");
    opt.value = z.zip;
    opt.textContent = `${z.label} (${z.zip})`;
    opt.dataset.lat = z.lat;
    opt.dataset.lng = z.lng;
    els.zip.appendChild(opt);
  }
  els.zip.disabled = false;
  els.fetchBtn.disabled = false;
  els.locateBtn.disabled = false;
  els.dataMeta.textContent = `Index updated ${formatTs(index.updated)} · radius ${index.radius} mi`;
  setStatus("");
  // Auto-load the first zip
  showZip(index.zips[0].zip);
}

async function showZip(zip) {
  setBusy(true);
  setStatus(`Loading ${zip}…`);
  try {
    const [snap, history] = await Promise.all([
      fetchJSON(`${DATA_DIR}/${zip}.json`),
      fetchJSON(`${DATA_DIR}/${zip}_history.json`).catch(() => []),
    ]);
    currentSnapshot = snap;
    renderSnapshot();
    renderHistory(history);
    setStatus(`Showing ${snap.label}`, "ok");
  } catch (err) {
    setStatus(err.message || "Failed to load", "err");
  } finally {
    setBusy(false);
  }
}

function getRadius() {
  const r = Number(els.radius.value);
  return Number.isFinite(r) && r > 0 ? r : 25;
}

function renderSnapshot() {
  if (!currentSnapshot) return;
  const snap = currentSnapshot;
  const radius = getRadius();
  const filtered = snap.warehouses.filter((w) => (w.distance ?? 999) <= radius);

  els.resultsTitle.textContent = `${snap.label} — latest snapshot`;
  els.snapshotMeta.textContent =
    `Updated ${formatTs(snap.updated)} · ${filtered.length} of ${snap.warehouses.length} station(s) within ${radius} mi`;
  els.resultsBody.innerHTML = "";
  for (let i = 0; i < filtered.length; i++) {
    const w = filtered[i];
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>
        <div class="name">${escapeHtml(w.name)}</div>
        <div class="addr">${escapeHtml(w.address)}</div>
      </td>
      <td>${(w.distance ?? 0).toFixed(1)}</td>
      <td>${fmtPrice(w.regular)}</td>
      <td>${fmtPrice(w.premium)}</td>
    `;
    els.resultsBody.appendChild(tr);
  }
  els.results.hidden = false;
}

function renderHistory(history) {
  els.historyCount.textContent = String(history.length);
  els.historySection.hidden = history.length === 0;
  drawChart(history);
}

function fmtPrice(p) {
  return p === null || p === undefined ? "—" : `$${Number(p).toFixed(3)}`;
}

function formatTs(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[c]));
}

function drawChart(history) {
  const svg = els.historyChart;
  svg.innerHTML = "";
  if (history.length < 2) return;

  const W = 600, H = 280, P = 36;
  const series = history.map((h) => {
    const regs = [], pres = [];
    for (const p of Object.values(h.prices || {})) {
      if (p.regular !== null && p.regular !== undefined) regs.push(p.regular);
      if (p.premium !== null && p.premium !== undefined) pres.push(p.premium);
    }
    const avg = (xs) => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
    return { t: h.timestamp, reg: avg(regs), pre: avg(pres) };
  });

  const all = series.flatMap((s) => [s.reg, s.pre]).filter((v) => v !== null);
  if (!all.length) return;
  const yMin = Math.max(0, Math.min(...all) - 0.15);
  const yMax = Math.max(...all) + 0.15;

  const x = (i) => P + (i * (W - 2 * P)) / (series.length - 1);
  const y = (v) => H - P - ((v - yMin) / (yMax - yMin)) * (H - 2 * P);

  const ax = (x1, y1, x2, y2) =>
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#888" stroke-width="1"/>`;
  let svgInner = ax(P, P, P, H - P) + ax(P, H - P, W - P, H - P);

  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const v = yMin + ((yMax - yMin) * i) / ticks;
    const yy = y(v);
    svgInner += `<line x1="${P}" y1="${yy}" x2="${W - P}" y2="${yy}" stroke="#eee"/>`;
    svgInner += `<text x="${P - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="#666">$${v.toFixed(2)}</text>`;
  }

  const labelIdx = series.length === 1 ? [0] : [0, Math.floor(series.length / 2), series.length - 1];
  for (const i of labelIdx) {
    const t = new Date(series[i].t);
    const lbl = `${t.getMonth() + 1}/${t.getDate()} ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
    svgInner += `<text x="${x(i)}" y="${H - P + 14}" text-anchor="middle" font-size="10" fill="#666">${lbl}</text>`;
  }

  const buildPath = (key, color) => {
    const pts = series.map((s, i) => s[key] === null ? null : [x(i), y(s[key])]);
    let d = "";
    let pen = false;
    for (const p of pts) {
      if (p === null) { pen = false; continue; }
      d += (pen ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1) + " ";
      pen = true;
    }
    return `<path d="${d.trim()}" fill="none" stroke="${color}" stroke-width="2"/>`;
  };
  svgInner += buildPath("reg", "#0b3d91");
  svgInner += buildPath("pre", "#c0392b");

  svgInner += `<g font-size="11" fill="#333">
    <rect x="${W - P - 110}" y="${P - 4}" width="10" height="10" fill="#0b3d91"/>
    <text x="${W - P - 96}" y="${P + 5}">Regular avg</text>
    <rect x="${W - P - 110}" y="${P + 12}" width="10" height="10" fill="#c0392b"/>
    <text x="${W - P - 96}" y="${P + 21}">Premium avg</text>
  </g>`;

  svg.innerHTML = svgInner;
}

function haversineMi(a, b) {
  const toRad = (d) => (d * Math.PI) / 180;
  const R = 3958.8;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat), lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const zip = els.zip.value;
  if (zip) showZip(zip);
});

els.radius.addEventListener("change", () => {
  localStorage.setItem(RADIUS_KEY, els.radius.value);
  renderSnapshot();
});

els.locateBtn.addEventListener("click", () => {
  if (!index || !index.zips.length) return;
  if (!navigator.geolocation) {
    setStatus("Geolocation not available", "err");
    return;
  }
  setStatus("Locating you…");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const me = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      let best = null, bestD = Infinity;
      for (const z of index.zips) {
        const d = haversineMi(me, { lat: z.lat, lng: z.lng });
        if (d < bestD) { bestD = d; best = z; }
      }
      if (best) {
        els.zip.value = best.zip;
        showZip(best.zip);
      }
    },
    (err) => setStatus(`Location: ${err.message}`, "err"),
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
  );
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}

loadIndex();
