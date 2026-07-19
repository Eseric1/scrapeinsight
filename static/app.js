/* ScrapeInsight frontend. No frameworks; all untrusted text rendered via textContent. */
"use strict";

const $ = (id) => document.getElementById(id);

const INK = "#17191d";
const INK2 = "#5c5f66";
const GRID = "#e7e7de";
const BLUE = "#2d62c1";

let chartInstances = [];
let running = false;

/* ---------- boot ---------- */

if (window.Chart) {
  Chart.defaults.font.family = '"Plex Mono", monospace';
  Chart.defaults.font.size = 10;
  Chart.defaults.color = INK2;
}

async function loadTargets() {
  const r = await fetch("/api/targets");
  const j = await r.json();
  for (const t of j.targets) {
    const o = document.createElement("option");
    o.value = t.id;
    o.textContent = t.label;
    $("target").appendChild(o);
  }
}

async function refreshStatus() {
  try {
    const j = await (await fetch("/api/health")).json();
    $("status-dot").className = "pulse " + (j.ok ? "ok" : "bad");
    $("status-text").textContent = j.ok ? j.chat_model : "backend offline";
  } catch {
    $("status-dot").className = "pulse bad";
    $("status-text").textContent = "backend offline";
  }
}

async function refreshLimits() {
  try {
    const j = await (await fetch("/api/limits")).json();
    $("limits-line").textContent =
      `${j.analyses_left} runs left this window · ${j.daily_budget_left} calls in today's shared budget`;
  } catch {
    $("limits-line").textContent = "";
  }
}

/* ---------- run ---------- */

$("ticket").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (running) return;
  await run({ target: $("target").value });
});

function setStage(stage) {
  const items = document.querySelectorAll(".progress li");
  let reached = false;
  items.forEach((li) => {
    li.classList.remove("active", "done");
    if (li.dataset.stage === stage) {
      li.classList.add("active");
      reached = true;
    } else if (!reached) {
      li.classList.add("done");
    }
  });
}

async function run(body) {
  running = true;
  $("run-btn").disabled = true;
  $("errbar").hidden = true;
  $("results").hidden = true;
  $("progress").hidden = false;
  setStage("fetching");

  try {
    const r = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(typeof j.detail === "string" ? j.detail : `Request failed (${r.status}).`);
    }
    let got = false;
    for await (const ev of sseEvents(r.body)) {
      if (ev.event === "progress") setStage(ev.data.stage);
      else if (ev.event === "error") throw new Error(ev.data);
      else if (ev.event === "result") {
        got = true;
        renderResult(ev.data);
      }
    }
    if (!got) throw new Error("The run ended without a result.");
  } catch (err) {
    showError(err.message || "Something went wrong.");
  } finally {
    running = false;
    $("run-btn").disabled = false;
    $("progress").hidden = true;
    refreshLimits();
  }
}

async function* sseEvents(bodyStream) {
  const reader = bodyStream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) yield { event, data: JSON.parse(data) };
    }
  }
}

/* ---------- rendering ---------- */

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function showError(msg) {
  const bar = $("errbar");
  bar.textContent = msg;
  bar.hidden = false;
}

function renderResult(data) {
  const src = $("source-line");
  src.textContent = "";
  const time = (data.fetched_at || "").replace("T", " ").replace("+00:00", " UTC");
  src.append("live pull · ");
  src.appendChild(el("b", null, data.source.label));
  src.append(
    ` · ${time} · ${data.total_found} products found — showing ${data.records.length}` +
    (data.extraction === "structured" ? " · structured-data extraction" : " · LLM extraction")
  );

  renderShowcase(data.showcase, data.source);
  renderTiles(data.stats);
  renderInsights(data.insights);
  renderCharts(data.stats.charts);
  renderTable(data.records, data.total_found);

  $("results").hidden = false;
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderShowcase(p, source) {
  const box = $("showcase");
  box.textContent = "";
  if (!p) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.appendChild(el("span", "sc-badge", "LIVE PULL · random product from this run"));
  const row = el("div", "sc-row");
  if (p.image) {
    const img = document.createElement("img");
    img.src = p.image;
    img.alt = p.name;
    img.loading = "lazy";
    img.className = "sc-img";
    row.appendChild(img);
  }
  const info = el("div", "sc-info");
  info.appendChild(el("p", "sc-name", p.name));
  const bits = [];
  if (p.price != null) bits.push(`$${fmt(p.price)}`);
  if (p.rating != null) bits.push(`rated ${fmt(p.rating)}`);
  bits.push(source.category);
  info.appendChild(el("p", "sc-meta", bits.join(" · ")));
  if (p.url) {
    const a = document.createElement("a");
    a.href = p.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.className = "sc-link";
    a.textContent = "view it on the site ↗";
    info.appendChild(a);
  }
  row.appendChild(info);
  box.appendChild(row);
}

function renderTiles(stats) {
  const wrap = $("tiles");
  wrap.textContent = "";
  const mk = (label, value, sub) => {
    const t = el("div", "tile");
    t.append(el("p", "t-label", label), el("p", "t-value", value));
    if (sub) t.append(el("p", "t-sub", sub));
    wrap.appendChild(t);
  };
  mk("records", String(stats.row_count));
  for (const [col, s] of Object.entries(stats.numeric)) {
    mk(`${col} · mean`, fmt(s.mean), `min ${fmt(s.min)} · max ${fmt(s.max)}`);
    mk(`${col} · median`, fmt(s.median), `${s.count} values`);
  }
}

function fmt(n) {
  return typeof n === "number" ? n.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—";
}

function renderInsights(insights) {
  const wrap = $("insights");
  wrap.textContent = "";
  if (!insights.length) return;
  wrap.appendChild(el("p", "section-label", "What the numbers say"));
  insights.forEach((text, i) => {
    const row = el("div", "insight");
    row.append(el("span", "n", `0${i + 1}`), el("span", null, text));
    wrap.appendChild(row);
  });
}

function renderCharts(charts) {
  const wrap = $("charts");
  chartInstances.forEach((c) => c.destroy());
  chartInstances = [];
  wrap.textContent = "";
  if (!window.Chart) return;

  for (const spec of charts) {
    const card = el("div", "chart-card");
    card.appendChild(el("h3", null, spec.title));
    const box = el("div", "chart-box");
    const canvas = document.createElement("canvas");
    box.appendChild(canvas);
    card.appendChild(box);
    wrap.appendChild(card);

    const grid = { color: GRID };
    let cfg;
    if (spec.type === "scatter") {
      cfg = {
        type: "scatter",
        data: {
          datasets: [{
            data: spec.points,
            backgroundColor: BLUE,
            borderColor: "#ffffff",
            borderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
          }],
        },
        options: {
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid, title: { display: true, text: spec.x_label } },
            y: { grid, title: { display: true, text: spec.y_label } },
          },
        },
      };
    } else {
      cfg = {
        type: "bar",
        data: {
          labels: spec.labels,
          datasets: [{
            data: spec.values,
            backgroundColor: BLUE,
            borderRadius: 4,
            borderSkipped: "start",
            maxBarThickness: 34,
          }],
        },
        options: {
          indexAxis: spec.horizontal ? "y" : "x",
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: spec.horizontal ? grid : { display: false }, ticks: { autoSkip: true } },
            y: { grid: spec.horizontal ? { display: false } : grid, beginAtZero: true },
          },
        },
      };
    }
    chartInstances.push(new Chart(canvas, cfg));
  }
}

function renderTable(records, totalFound) {
  const table = $("records");
  table.textContent = "";
  const note = document.querySelector(".table-note");
  if (note) note.remove();
  if (!records.length) return;
  const cols = ["name", "price", "rating", "category"].filter((c) =>
    records.some((r) => r[c] != null)
  );
  const thead = el("thead");
  const hr = el("tr");
  cols.forEach((c) => hr.appendChild(el("th", null, c)));
  thead.appendChild(hr);
  const tbody = el("tbody");
  for (const r of records) {
    const tr = el("tr");
    for (const c of cols) {
      const v = r[c];
      const td = el("td", typeof v === "number" ? "num" : null,
        v === null || v === undefined ? "—" : String(v));
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  if (totalFound > records.length) {
    const n = el("p", "table-note",
      `Demo cap: showing ${records.length} of ${totalFound} products extracted — the full set (and full catalogs) comes with a client build.`);
    table.closest(".table-card").appendChild(n);
  }
}

/* ---------- go ---------- */

loadTargets();
refreshStatus();
refreshLimits();
setInterval(refreshStatus, 30000);
