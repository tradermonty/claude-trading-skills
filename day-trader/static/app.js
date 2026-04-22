// Day Trading Agent — dashboard UI
const $ = (id) => document.getElementById(id);

const state = {
  selectedMode: "medium",
  running: false,
  riskModes: {},
};

// ---------------------- api ----------------------
async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

// ---------------------- formatting ----------------------
const fmtMoney = (v) =>
  v == null ? "—" : (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = (v) => v == null ? "—" : (v > 0 ? "+" : "") + (v * 100).toFixed(2) + "%";
const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString();
const fmtQty = (v) => v == null ? "—" : Number(v).toFixed(2).replace(/\.00$/, "");

// ---------------------- risk mode panel ----------------------
function renderRiskModes() {
  const modesDiv = $("risk-modes");
  modesDiv.innerHTML = "";
  for (const [name, m] of Object.entries(state.riskModes)) {
    const btn = document.createElement("button");
    btn.className = `risk-btn ${name}${state.selectedMode === name ? " active" : ""}`;
    btn.innerHTML = `<b>${name.toUpperCase()}</b><small>${m.description.split("—")[0].trim()}</small>`;
    btn.onclick = () => {
      if (state.running) return alert("Stop trading before changing risk mode.");
      state.selectedMode = name;
      renderRiskModes();
      renderRiskTable();
      $("mode-badge").textContent = name;
      $("mode-badge").className = `tag ${name}`;
    };
    modesDiv.appendChild(btn);
  }
}

function renderRiskTable() {
  const m = state.riskModes[state.selectedMode];
  if (!m) return;
  const rows = [
    ["Max position (raw)",     (m.max_position_pct * 100).toFixed(0) + "% of equity"],
    ["Max position (leveraged)", (m.max_position_pct * m.max_leverage * 100).toFixed(1) + "% of equity"],
    ["Confidence scaling",     "conf 0.5 → 40% · 0.75 → 70% · 1.0 → 100%"],
    ["Max concurrent",         m.max_concurrent_positions],
    ["Min trade size",         "$" + (m.min_trade_dollars || 0).toLocaleString()],
    ["Stop loss",              (m.stop_loss_pct * 100).toFixed(1) + "%"],
    ["Take profit",            (m.take_profit_pct * 100).toFixed(1) + "%"],
    ["Trailing stop arms at",  "+" + (m.trailing_activation_pct * 100).toFixed(1) + "%"],
    ["Trailing stop retrace",  (m.trailing_retrace_pct * 100).toFixed(1) + "%"],
    ["Stagnation timeout",     (m.stagnation_minutes) + " min (if |PnL| < 0.3%)"],
    ["EOD flatten",            (m.eod_flatten_minutes) + " min before close"],
    ["Daily loss cap",         (m.max_daily_loss_pct * 100).toFixed(0) + "%"],
    ["Shorts allowed",         m.allow_shorts ? "Yes" : "No"],
    ["Leverage",               m.max_leverage + "x"],
    ["Margin call threshold",  m.margin_call_threshold > 0 ? (m.margin_call_threshold * 100).toFixed(0) + "%" : "—"],
    ["Strategies",             m.allowed_strategies.join(", ")],
    ["Universe size",          m.universe_size + " symbols"],
    ["Scan interval",          m.scan_interval_sec + "s"],
  ];
  $("risk-table").innerHTML = "<tbody>" +
    rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("") +
    "</tbody>";
}

// ---------------------- status ----------------------
function renderAccount(s) {
  const a = s.account;
  if (!a) return;
  $("equity").textContent = fmtMoney(a.equity);
  $("cash").textContent = fmtMoney(a.cash);
  $("bp").textContent = fmtMoney(a.buying_power);
  $("long-mv").textContent = fmtMoney(a.long_market_value);
  $("short-mv").textContent = fmtMoney(a.short_market_value);
  $("maint").textContent = fmtMoney(a.maintenance_margin);
  const pnl = s.starting_equity ? a.equity - s.starting_equity : null;
  const el = $("pnl-today");
  if (pnl == null) { el.textContent = "—"; el.className = ""; }
  else {
    const pct = pnl / s.starting_equity;
    el.textContent = `${fmtMoney(pnl)} (${fmtPct(pct)})`;
    el.className = pnl >= 0 ? "pnl-pos" : "pnl-neg";
  }
}

function renderMarket(s) {
  const m = s.market || {};
  const open = m.is_open;
  const label = open ? "OPEN" : (m.next_open ? `CLOSED (next open: ${new Date(m.next_open).toLocaleString()})` : "CLOSED");
  $("market-status").innerHTML = `market: <span style="color:${open ? "var(--good)" : "var(--muted)"}">${label}</span>`;
}

function renderPositions(s) {
  const tbody = $("positions-body");
  const posCount = $("pos-count");
  const ps = s.positions || [];
  posCount.textContent = ps.length ? `(${ps.length})` : "";
  if (!ps.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="muted">No open positions.</td></tr>`;
    return;
  }
  tbody.innerHTML = ps.map((p) => `
    <tr>
      <td><b>${p.symbol}</b></td>
      <td class="side-${p.side}">${p.side.toUpperCase()}</td>
      <td>${fmtQty(p.qty)}</td>
      <td>${fmtMoney(p.avg_entry_price)}</td>
      <td>${fmtMoney(p.current_price)}</td>
      <td>${fmtMoney(p.market_value)}</td>
      <td class="${p.unrealized_pl >= 0 ? "pnl-pos" : "pnl-neg"}">${fmtMoney(p.unrealized_pl)}</td>
      <td class="${p.unrealized_plpc >= 0 ? "pnl-pos" : "pnl-neg"}">${fmtPct(p.unrealized_plpc)}</td>
      <td class="muted">${p.strategy || "—"}</td>
    </tr>
  `).join("");
}

function renderHalt(s) {
  const banner = $("halt-banner");
  if (s.halted_reason) {
    banner.textContent = `⚠ HALTED: ${s.halted_reason}`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

function renderButtons(s) {
  const running = !!s.running;
  state.running = running;
  $("start-btn").disabled = running;
  $("stop-btn").disabled = !running;
  $("stop-liquidate-btn").disabled = !running;
}

// ---------------------- trades ----------------------
function renderTrades(data) {
  const tbody = $("trades-body");
  const trades = data.trades || [];
  const stats = data.stats || {};
  const statsEl = $("trades-stats");
  if (stats.total_trades) {
    const win = stats.winners || 0, lose = stats.losers || 0;
    const wr = (win + lose) > 0 ? (win / (win + lose) * 100).toFixed(1) : "—";
    statsEl.textContent = `— ${stats.total_trades} closed · ${win}W/${lose}L · win rate ${wr}% · total ${fmtMoney(stats.total_pnl)}`;
  } else {
    statsEl.textContent = "";
  }
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="muted">No trades yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = trades.map((t) => {
    const sideClass = (t.side === "sell" || t.side === "short" || t.side === "cover") ? "side-short" : "side-long";
    const pnlClass = t.pnl > 0 ? "pnl-pos" : (t.pnl < 0 ? "pnl-neg" : "");
    return `
      <tr>
        <td class="muted">${t.ts.replace("T", " ").slice(0, 19)}</td>
        <td><b>${t.symbol}</b></td>
        <td class="${sideClass}">${t.side.toUpperCase()}</td>
        <td>${fmtQty(t.qty)}</td>
        <td>${fmtMoney(t.price)}</td>
        <td class="${pnlClass}">${t.pnl ? fmtMoney(t.pnl) : "—"}</td>
        <td class="muted">${t.strategy || "—"}</td>
        <td class="muted">${t.risk_mode || "—"}</td>
        <td class="muted" style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(t.notes || "").replace(/"/g,"&quot;")}">${t.notes || ""}</td>
      </tr>
    `;
  }).join("");
}

// ---------------------- events ----------------------
function renderEvents(data) {
  const list = $("events-list");
  const events = data.events || [];
  if (!events.length) {
    list.innerHTML = `<div class="muted">No events yet.</div>`;
    return;
  }
  list.innerHTML = events.map((e) => `
    <div class="event ${e.kind}">
      <span class="ts">${e.ts.replace("T"," ").slice(0,19)}</span>
      ${e.symbol ? `<span class="sym">${e.symbol}</span>` : ""}
      ${e.message}
    </div>
  `).join("");
}

// ---------------------- polling ----------------------
async function poll() {
  try {
    const [s, t, ev] = await Promise.all([
      api("/api/status"),
      api("/api/trades?limit=200"),
      api("/api/events?limit=300"),
    ]);
    renderAccount(s);
    renderMarket(s);
    renderPositions(s);
    renderHalt(s);
    renderButtons(s);
    renderTrades(t);
    renderEvents(ev);
    if (s.risk_mode && s.risk_mode !== state.selectedMode && s.running) {
      state.selectedMode = s.risk_mode;
      $("mode-badge").textContent = s.risk_mode;
      $("mode-badge").className = `tag ${s.risk_mode}`;
      renderRiskModes();
      renderRiskTable();
    }
  } catch (e) {
    console.warn("poll err", e);
  }
}

// ---------------------- wiring ----------------------
async function init() {
  try {
    state.riskModes = await api("/api/risk-modes");
  } catch (e) {
    alert("Failed to load risk modes: " + e.message);
    return;
  }
  $("mode-badge").textContent = state.selectedMode;
  $("mode-badge").className = `tag ${state.selectedMode}`;
  renderRiskModes();
  renderRiskTable();

  $("start-btn").onclick = async () => {
    try {
      await api("/api/start", { method: "POST", body: JSON.stringify({ risk_mode: state.selectedMode }) });
    } catch (e) { alert("Start failed: " + e.message); }
    poll();
  };
  $("stop-btn").onclick = async () => {
    try { await api("/api/stop", { method: "POST", body: JSON.stringify({ liquidate: false }) }); }
    catch (e) { alert("Stop failed: " + e.message); }
    poll();
  };
  $("stop-liquidate-btn").onclick = async () => {
    if (!confirm("Stop and close ALL positions?")) return;
    try { await api("/api/stop", { method: "POST", body: JSON.stringify({ liquidate: true }) }); }
    catch (e) { alert("Stop+liquidate failed: " + e.message); }
    poll();
  };
  $("panic-btn").onclick = async () => {
    if (!confirm("Emergency liquidate all positions?")) return;
    try { await api("/api/liquidate-all", { method: "POST" }); }
    catch (e) { alert("Panic failed: " + e.message); }
    poll();
  };

  poll();
  setInterval(poll, 5000);
}

init();
