/* ReviewPulse dashboard logic: fetches from the review pipeline API,
   renders Chart.js charts, filters, table, upload, live analyze, free-tier. */
"use strict";

/* ---------- API base: same origin when served, configurable otherwise ---------- */
const params = new URLSearchParams(location.search);
const API_BASE = (params.get("apiBase") || localStorage.getItem("rp_api_base") ||
  (location.protocol === "file:" ? "http://127.0.0.1:8000" : "")).replace(/\/$/, "");
if (params.get("apiBase")) localStorage.setItem("rp_api_base", API_BASE);

const state = {
  filters: {},
  period: "day",
  page: 0,
  pageSize: 15,
  charts: {},
  summary: null,
};

/* ---------- tiny helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const fmtPct = (x) => (x == null ? "–" : (x * 100).toFixed(1) + "%");
const fmtNum = (x, d = 0) => (x == null ? "–" : Number(x).toFixed(d));

async function api(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let payload = null;
  try { payload = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) {
    const msg = payload && payload.message ? payload.message : `HTTP ${res.status}`;
    throw new Error(`${options.method || "GET"} ${path}: ${msg}`);
  }
  return payload;
}

function qs(filters, extra = {}) {
  const q = new URLSearchParams();
  Object.entries({ ...filters, ...extra }).forEach(([k, v]) => {
    if (v !== "" && v != null) q.set(k, v);
  });
  const s = q.toString();
  return s ? "?" + s : "";
}

/* ---------- theme ---------- */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("rp_theme", theme);
  Chart.defaults.color = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim();
  Chart.defaults.borderColor = getComputedStyle(document.documentElement).getPropertyValue("--border").trim();
  if (state.summary) drawCharts(); // re-render with new colors
}
$("#themeBtn").addEventListener("click", () =>
  applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));

/* ---------- charts ---------- */
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function drawCharts() {
  const s = state.summary;
  if (!s) return;
  Object.values(state.charts).forEach((c) => c.destroy());
  state.charts = {};

  const counts = s.sentiment_counts;
  state.charts.sentiment = new Chart($("#sentimentChart"), {
    type: "doughnut",
    data: {
      labels: ["Positive", "Neutral", "Negative"],
      datasets: [{
        data: [counts.positive, counts.neutral, counts.negative],
        backgroundColor: [cssVar("--pos"), cssVar("--neu"), cssVar("--neg")],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      plugins: { legend: { position: "bottom" } },
    },
  });

  api(`/trends${qs(state.filters, { period: state.period })}`).then((t) => {
    const labels = t.trends.map((b) => b.period);
    state.charts.trend = new Chart($("#trendChart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Positive", data: t.trends.map((b) => b.positive), borderColor: cssVar("--pos"), backgroundColor: cssVar("--pos") + "33", fill: true, tension: .3, pointRadius: 0 },
          { label: "Neutral", data: t.trends.map((b) => b.neutral), borderColor: cssVar("--neu"), backgroundColor: cssVar("--neu") + "33", fill: true, tension: .3, pointRadius: 0 },
          { label: "Negative", data: t.trends.map((b) => b.negative), borderColor: cssVar("--neg"), backgroundColor: cssVar("--neg") + "33", fill: true, tension: .3, pointRadius: 0 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 12 } }, y: { beginAtZero: true, stacked: false } },
        plugins: { legend: { position: "bottom" } },
      },
    });
  }).catch(showError);

  api(`/keywords${qs(state.filters, { sentiment: "positive", top_n: 10 })}`).then((k) => {
    state.charts.posKw = barChart($("#posKeywordsChart"), k.keywords, cssVar("--pos"));
  }).catch(showError);
  api(`/keywords${qs(state.filters, { sentiment: "negative", top_n: 10 })}`).then((k) => {
    state.charts.negKw = barChart($("#negKeywordsChart"), k.keywords, cssVar("--neg"));
  }).catch(showError);
}

function barChart(canvas, rows, color) {
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.keyword),
      datasets: [{ label: "Reviews mentioning", data: rows.map((r) => r.reviews), backgroundColor: color, borderRadius: 6 }],
    },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      plugins: { legend: { display: false } },
    },
  });
}

/* ---------- KPIs + free tier ---------- */
function renderKpis(s) {
  $("#kpiTotal").textContent = s.total_reviews.toLocaleString();
  $("#kpiProcessed").textContent = s.processed_reviews.toLocaleString();
  $("#kpiPositive").textContent = fmtPct(s.sentiment_share.positive);
  $("#kpiNegative").textContent = fmtPct(s.sentiment_share.negative);
  $("#kpiRating").textContent = fmtNum(s.avg_rating, 2) + " ★";
  $("#kpiConfidence").textContent = fmtPct(s.avg_confidence);
  $("#sentimentCaption").textContent = s.date_range
    ? `${s.total_reviews.toLocaleString()} reviews · ${s.date_range.from} → ${s.date_range.to}`
    : "";
  const types = Object.keys(s.by_business_type || {}).sort();
  const sel = document.querySelector('select[name="business_type"]');
  if (sel.options.length <= 1) {
    types.forEach((t) => sel.add(new Option(t[0].toUpperCase() + t.slice(1), t)));
  }
}

function renderFreeTier(s) {
  const n = s.total_reviews;
  const processed = s.processed_reviews;
  const storageMB = (n * 1200) / 1e6; // ~1.2 KB per review document (text + scores + keywords)
  const lambdaGBs = processed * 0.1 * 0.5; // 100 ms × 512 MB per processed review (estimate)
  const apiCalls = n + processed + 8; // ingest + process + dashboard queries (estimate)
  const rows = [
    ["Streamlit Community Cloud (dashboard)", "Free hosting for public apps", "1 static app", true],
    ["Hugging Face Inference API", "Free tier (rate-limited)", "VADER used locally — 0 API calls", true],
    ["Firebase Firestore — Spark plan", "50K reads / 20K writes per day", `${n.toLocaleString()} reads (one-off seed)`, true],
    ["Amazon S3 (cloud mode)", "5 GB storage", `${storageMB.toFixed(2)} MB (uploads + static site)`, true],
    ["AWS Lambda (cloud mode)", "1M requests + 400K GB-s per month", `≈${apiCalls.toLocaleString()} reqs · ${lambdaGBs.toFixed(1)} GB-s`, true],
    ["Amazon API Gateway (cloud mode)", "1M HTTP requests per month", `≈${apiCalls.toLocaleString()} requests`, true],
    ["Amazon DynamoDB (cloud mode)", "25 WCU + 25 RCU (on-demand)", `${n.toLocaleString()} items · burst reads only`, true],
    ["Amazon CloudWatch (cloud mode)", "5 GB logs ingested", "≈0.1 GB per full pipeline run", true],
  ];
  const tbody = $("#freeTierTable tbody");
  tbody.innerHTML = "";
  rows.forEach(([service, allowance, usage, ok]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${service}</td><td>${allowance}</td><td>${usage}</td>
      <td><span class="badge ${ok ? "badge-ok" : "badge-bad"}">${ok ? "$0.00 · within free tier" : "over free tier"}</span></td>`;
    tbody.appendChild(tr);
  });
  $("#freeTierNote").textContent =
    `Estimate basis: ${n.toLocaleString()} reviews (~${storageMB.toFixed(2)} MB), ` +
    `${processed.toLocaleString()} sentiment computations (≈100 ms each on 512 MB Lambda). ` +
    `Local mode (this demo) runs on your PC and costs $0 by construction.`;
}

/* ---------- reviews table ---------- */
function stars(rating) {
  return "★".repeat(rating) + "☆".repeat(5 - rating);
}
function badge(sentiment) {
  if (!sentiment) return '<span class="badge badge-muted">unprocessed</span>';
  const cls = sentiment === "positive" ? "badge-pos" : sentiment === "negative" ? "badge-neg" : "badge-neu";
  return `<span class="badge ${cls}">${sentiment}</span>`;
}
function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

async function loadReviews() {
  const offset = state.page * state.pageSize;
  const data = await api(`/reviews${qs(state.filters, { limit: state.pageSize, offset })}`);
  const tbody = $("#reviewsTable tbody");
  tbody.innerHTML = "";
  data.reviews.forEach((r) => {
    const tr = document.createElement("tr");
    const kws = (r.keywords || []).slice(0, 5).map((k) => `<span class="chip">${esc(k)}</span>`).join(" ");
    tr.innerHTML = `
      <td>${esc(r.date)}</td>
      <td class="stars" title="${r.rating}/5">${stars(r.rating)}</td>
      <td class="review-text" title="${esc(r.text)}">${esc(r.text.length > 180 ? r.text.slice(0, 180) + "…" : r.text)}</td>
      <td>${badge(r.sentiment)}</td>
      <td>${r.confidence == null ? "–" : fmtPct(r.confidence)}</td>
      <td><div class="chips">${kws}</div></td>
      <td>${esc(r.business_type || "–")}</td>`;
    tbody.appendChild(tr);
  });
  const first = data.total_matches === 0 ? 0 : offset + 1;
  $("#tableMeta").textContent = `(${data.total_matches.toLocaleString()} matching)`;
  $("#pageInfo").textContent = `${first}–${offset + data.returned} of ${data.total_matches.toLocaleString()}`;
  $("#prevPage").disabled = state.page === 0;
  $("#nextPage").disabled = offset + data.returned >= data.total_matches;
}

/* ---------- orchestrators ---------- */
function showError(err) {
  console.error(err);
  let banner = $("#errorBanner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "errorBanner";
    banner.className = "error-banner";
    document.querySelector("main").prepend(banner);
  }
  banner.textContent = "⚠ " + err.message;
  setTimeout(() => banner.remove(), 6000);
}

async function loadAll() {
  try {
    const [health, summary] = await Promise.all([api("/health"), api(`/summary${qs(state.filters)}`)]);
    state.summary = summary.summary;
    const hb = $("#healthBadge");
    hb.textContent = `${health.status} · ${health.storage.backend} · ${health.engine}`;
    hb.className = "badge " + (health.status === "ok" ? "badge-ok" : "badge-bad");
    renderKpis(summary.summary);
    renderFreeTier(summary.summary);
    drawCharts();
    await loadReviews();
  } catch (err) { showError(err); }
}

/* ---------- events ---------- */
$("#filterForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  state.filters = Object.fromEntries([...fd.entries()].filter(([, v]) => v !== ""));
  state.page = 0;
  loadAll();
});
$("#resetFiltersBtn").addEventListener("click", () => {
  $("#filterForm").reset();
  state.filters = {};
  state.page = 0;
  loadAll();
});
$("#periodToggle").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg");
  if (!btn) return;
  state.period = btn.dataset.period;
  document.querySelectorAll("#periodToggle .seg").forEach((b) => b.classList.toggle("active", b === btn));
  drawCharts();
});
$("#prevPage").addEventListener("click", () => { state.page--; loadReviews().catch(showError); });
$("#nextPage").addEventListener("click", () => { state.page++; loadReviews().catch(showError); });
$("#refreshBtn").addEventListener("click", loadAll);

/* ---------- live analyze ---------- */
$("#analyzeDate").value = new Date().toISOString().slice(0, 10);
$("#analyzeBtn").addEventListener("click", async () => {
  const text = $("#analyzeText").value.trim();
  const box = $("#analyzeResult");
  box.hidden = false;
  if (text.length < 2) { box.textContent = "Please paste a review first."; return; }
  $("#analyzeBtn").disabled = true;
  box.textContent = "Analyzing…";
  try {
    const stored = await api("/reviews", {
      method: "POST",
      body: JSON.stringify({
        text,
        rating: Number($("#analyzeRating").value),
        date: $("#analyzeDate").value,
        source: "dashboard",
        business_type: "dashboard-submitted",
      }),
    });
    const id = stored.review.review_id;
    const result = await api("/process", { method: "POST", body: JSON.stringify({ review_ids: [id] }) });
    const r = result.results[0];
    const kws = (r.keywords || []).map((k) => `<span class="chip">${esc(k)}</span>`).join(" ");
    box.innerHTML = `
      <div><strong>Review <code>${esc(id)}</code> →</strong> ${badge(r.sentiment)}
        confidence <strong>${fmtPct(r.confidence)}</strong> · engine <code>${esc(r.engine)}</code></div>
      <div class="chips">${kws}</div>
      <div class="muted small">Stored in the database — charts pick it up on Refresh.</div>`;
  } catch (err) { box.textContent = "⚠ " + err.message; }
  finally { $("#analyzeBtn").disabled = false; }
});

/* ---------- upload ---------- */
$("#uploadBtn").addEventListener("click", async () => {
  const file = $("#uploadFile").files[0];
  const box = $("#uploadResult");
  box.hidden = false;
  if (!file) { box.textContent = "Choose a CSV or JSON file first."; return; }
  if (file.size > 1_000_000) { box.textContent = "⚠ File too large for this prototype (max 1 MB)."; return; }
  $("#uploadBtn").disabled = true;
  box.textContent = "Uploading…";
  try {
    const content = await file.text();
    const res = await api("/ingest", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content }),
    });
    const st = res.stored;
    box.innerHTML = `
      <div><strong>${esc(res.file)}</strong> — ${res.total_rows} rows:
        ${res.valid_records} valid, ${res.duplicates_in_file} duplicates, ${res.invalid_rows} invalid.
        Stored: ${st.inserted} new, ${st.updated} updated, ${st.skipped} kept (already processed).</div>
      ${res.invalid_rows ? `<details><summary class="muted small">invalid row samples</summary><pre>${esc(JSON.stringify(res.invalid_samples, null, 2))}</pre></details>` : ""}
      <div class="muted small">Run <code>POST /process</code> (or Refresh after processing) to classify them.</div>`;
    loadAll();
  } catch (err) { box.textContent = "⚠ " + err.message; }
  finally { $("#uploadBtn").disabled = false; }
});

$("#templateBtn").addEventListener("click", () => {
  const csv = 'date,rating,text\n2024-05-01,5,"Great service and friendly staff!"\n2024-05-02,2,"Waited 40 minutes for cold food."\n';
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url; a.download = "reviews_template.csv"; a.click();
  URL.revokeObjectURL(url);
});

/* ---------- boot ---------- */
applyTheme(localStorage.getItem("rp_theme") || "light");
$("#analyzeEngine").textContent = "engine: …";
api("/engines").then((e) => {
  const active = e.engines.find((x) => x.available);
  $("#analyzeEngine").textContent = `engine: ${active ? active.name : "none"}`;
}).catch(() => { $("#analyzeEngine").textContent = "engine: ?"; });
loadAll();
setInterval(() => {
  api("/health").then((h) => {
    const hb = $("#healthBadge");
    hb.textContent = `${h.status} · ${h.storage.backend} · ${h.engine}`;
    hb.className = "badge " + (h.status === "ok" ? "badge-ok" : "badge-bad");
  }).catch(() => {
    const hb = $("#healthBadge");
    hb.textContent = "API offline";
    hb.className = "badge badge-bad";
  });
}, 15000);
