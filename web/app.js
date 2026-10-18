"use strict";
const S = { tenant: "northwind", asker: "p_priya", mode: "graph", personas: [], tab: "ask" };
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (n) => n.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

async function api(path, body) {
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.detail?.message || data.detail || r.statusText), { data });
  return data;
}
async function busy(el, fn) { el?.classList.add("spin"); try { return await fn(); } finally { el?.classList.remove("spin"); } }
const nameOf = (id) => S.personas.find((p) => p.id === id)?.name || id;

/* ---------- header ---------- */
async function loadTenants() {
  const ts = await api("/api/tenants");
  $("#tenant").innerHTML = ts.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
  $("#tenant").value = S.tenant;
  S.samples = Object.fromEntries(ts.map((t) => [t.id, t.samples]));
}
async function loadPeople() {
  const r = await api(`/api/people?tenant=${S.tenant}`);
  S.personas = r.personas;
  if (!S.personas.find((p) => p.id === S.asker)) S.asker = S.personas[0]?.id;
  $("#personas").innerHTML = S.personas.map((p) => `
    <button class="persona ${p.kind === "Agent" ? "agent" : ""} ${p.id === S.asker ? "on" : ""}" data-id="${p.id}" title="${esc((p.groups || []).join(", "))}">
      <span class="av">${p.kind === "Agent" ? "AI" : initials(p.name)}</span>
      <span><b>${esc(p.name)}</b><small>${esc(p.title || "")}</small></span>
    </button>`).join("");
  const opts = S.personas.map((p) => `<option value="${p.id}">${esc(p.name)}, ${esc(p.title || "")}</option>`).join("");
  $("#ca").innerHTML = opts; $("#cb").innerHTML = opts; $("#peek-owner").innerHTML = opts;
  if (S.tenant === "northwind") { $("#ca").value = "p_priya"; $("#cb").value = "p_meera"; $("#peek-owner").value = "p_meera"; }
  $("#samples").innerHTML = (S.samples[S.tenant] || []).map((q) => `<button class="chip" type="button">${esc(q)}</button>`).join("");
}
function setMode(m) {
  S.mode = m;
  document.querySelectorAll("#mode button").forEach((b) => { b.classList.toggle("on", b.dataset.mode === m); b.setAttribute("aria-checked", b.dataset.mode === m); });
  const ban = $("#mode-banner");
  if (m === "graph") { ban.hidden = true; return; }
  ban.hidden = false;
  ban.className = `banner ${m}`;
  ban.textContent = m === "off"
    ? "Access check is OFF. This is what a plain document chatbot does: anything it finds, it shows. Leaks are marked in red."
    : "Flat list mode: only direct group memberships count, nested groups are ignored. Watch people lose access they should have.";
}

/* ---------- ask ---------- */
function factHTML(f) {
  const w = f.why;
  const chain = w ? w.names.slice(0, -1) : [];
  const path = chain.map((n, i) => `<b>${esc(n)}</b>${i < chain.length - 1 ? " → " : ""}`).join("");
  return `<div class="fact ${f.leak ? "leak" : ""}">
    <div class="row gap"><span class="lab">${esc(f.label)}</span>${f.leak ? '<span class="pill bad">LEAK: not allowed</span>' : ""}${f.restricted && !f.leak ? '<span class="pill dark">restricted · cleared</span>' : ""}</div>
    <p>${esc(f.text)}</p>
    <div class="src"><span>${esc(f.source.title)}</span><span>${esc(f.source.kind)}</span><span>updated ${esc(f.source.updated)}</span>${f.source.owner ? `<span>owner ${esc(f.source.owner)}</span>` : ""}</div>
    ${w ? `<div class="why">Why you can see it: ${path} → <b>${esc(w.target.startsWith("sp_") ? f.source.space : f.label)}</b> · granted by ${esc(w.granted_by)} on ${esc(w.granted_at)}</div>` : ""}
  </div>`;
}
function redactHTML(r) {
  return `<div class="redact">
    <div class="bar"><span>Redacted · ${esc(r.label)}</span><span class="lines"></span></div>
    <div class="need">${esc(r.doc_title)}${r.needs.length ? ` · needs <b>${r.needs.map(esc).join("</b> or <b>")}</b>` : ""}${r.owner ? ` · ask ${esc(r.owner)}` : ""}${r.wrongly_hidden ? ' <span class="pill warn">wrongly hidden: you are allowed</span>' : ""}</div>
  </div>`;
}
function answerHTML(a, title) {
  const dec = a.decisions.map((d) => `<div class="decision"><b>Decision:</b> ${esc(d.summary)}<br><span class="muted small">Made by ${esc(d.made_by)} on ${esc(d.date)} · ${d.source ? `decided in ${esc(d.source)}` : 'source restricted for you'} · written up in ${esc(d.documented_in)}</span></div>`).join("");
  return `<div class="ans">
    <div class="ans-head"><span class="who">${esc(title || "Answer for " + nameOf(a.asker))}</span>
      <span class="row gap">${a.leaks ? `<span class="pill bad">${a.leaks} leak${a.leaks > 1 ? "s" : ""}</span>` : '<span class="pill ok">0 leaks</span>'}<span class="by">${a.answer.by === "llm" ? "phrased by LLM from allowed facts" : "deterministic answer"}</span></span></div>
    <p class="summary">${esc(a.answer.text)}</p>
    ${a.facts.map(factHTML).join("")}
    ${a.redacted.map(redactHTML).join("")}
    ${dec}
  </div>`;
}
async function ask(q) {
  q = (q || $("#q").value).trim();
  if (!q) return;
  $("#q").value = q;
  const a = await busy($("#answer"), () => api("/api/ask", { tenant: S.tenant, asker: S.asker, question: q, mode: S.mode }));
  $("#answer").innerHTML = answerHTML(a);
  drawPath(a);
  const mc = $("#mem-card");
  mc.hidden = !a.memory.length;
  const seenMem = new Set();
  $("#mem-snip").innerHTML = a.memory.filter((m) => !seenMem.has(m.text) && seenMem.add(m.text)).map((m) => `<div class="mem"><time>${esc(m.ts.replace("T", " ").slice(0, 16))}</time>${esc(m.text)}</div>`).join("");
}

/* ---------- access path: one row per chain of memberships ---------- */
function drawPath(a) {
  const box = $("#pathviz");
  const node = (label, kind, cls) => `<span class="node ${cls || ""}"><small>${esc(kind)}</small><span>${esc(label)}</span></span>`;
  const chains = new Map();
  const unchecked = [];
  a.facts.forEach((f) => {
    if (!f.why) { unchecked.push(f); return; }
    const key = f.why.ids.join(">") + "|" + f.why.target;
    if (!chains.has(key)) chains.set(key, { w: f.why, f, out: [] });
    chains.get(key).out.push(f);
  });
  let html = "";
  chains.forEach(({ w, f, out }) => {
    const parts = w.names.slice(0, -1).map((n, i) => node(n, i === 0 ? (w.kinds[i] === "Agent" ? "AI agent" : "you") : "member of", i === 0 ? "person" : ""));
    const tgt = w.target.startsWith("sp_") ? f.source.space : w.target === f.id ? f.label : f.source.title;
    parts.push(node(tgt, "can read", "grant"));
    html += `<div class="chain">${parts.join('<span class="arrow">→</span>')}<span class="arrow">⇒</span>${out.map((x) => node(x.label, x.restricted ? "restricted passage" : "passage", x.leak ? "leak" : "ok")).join("")}</div>`;
  });
  if (unchecked.length) {
    html += `<div class="chain">${node(nameOf(a.asker), "you", "person")}<span class="arrow">→</span>${node("no access check", "mode " + a.mode, "leak")}<span class="arrow">⇒</span>${unchecked.map((x) => node(x.label, x.leak ? "LEAKED" : "passage", x.leak ? "leak" : "ok")).join("")}</div>`;
  }
  if (a.redacted.length) {
    html += `<div class="chain"><span class="small muted">Withheld from you:</span>${a.redacted.map((r) => node(r.label, "redacted", "hidden")).join("")}</div>`;
  }
  box.innerHTML = html || '<p class="muted small">Nothing found.</p>';
}

/* ---------- compare ---------- */
async function compare() {
  const q = $("#cq").value.trim(); if (!q) return;
  const askers = [$("#ca").value, $("#cb").value];
  const res = await busy($("#cmp"), () => api("/api/compare", { tenant: S.tenant, question: q, askers, mode: S.mode }));
  $("#cmp").innerHTML = res.map((a) => `<div class="col">${answerHTML(a, nameOf(a.asker) + " · " + (S.personas.find((p) => p.id === a.asker)?.title || ""))}</div>`).join("");
}

/* ---------- agents ---------- */
async function runCase(mode) {
  const out = $("#case-out");
  const r = await busy(out, () => api("/api/case/run", { tenant: S.tenant, mode }));
  const steps = r.steps.map((s) => `<div class="step"><span class="n">STEP ${s.step} · ${esc(s.actor)}</span><p>${esc(s.did)}</p>
    <div class="checks">${s.checks.map((c) => `<span>${c.ok ? '<span class="pill ok">can read</span>' : '<span class="pill dark">redacted</span>'} ${esc(c.what)}</span>`).join("")}</div></div>`).join("");
  const notes = r.view.notes.map((n) => n.visible
    ? `<div class="note ${n.leak ? "leak" : ""}"><span class="who">${esc(n.author)}${n.restricted ? " · Finance-only" : ""}${n.leak ? ' <span class="pill bad">LEAK</span>' : ""}</span>${esc(n.text)}</div>`
    : `<div class="note"><span class="who">${esc(n.author)} · Finance-only note</span><div class="bar"><span>Redacted for the Support Agent</span><span class="lines"></span></div></div>`).join("");
  const hand = r.view.handoffs.map((h) => `<li><b>${esc(h.from)}</b> → <b>${esc(h.to)}</b>: ${esc(h.reason)}</li>`).join("");
  out.innerHTML = `<div class="steps">${steps}</div>
    <div class="grid2">
      <div class="card"><div class="card-h"><h3>The case, as the Support Agent sees it</h3>${mode === "off" ? '<span class="pill bad">access checks off</span>' : '<span class="pill ok">graph access checks</span>'}</div>${notes}<h4>Handoffs</h4><ul class="small">${hand}</ul></div>
      <div class="card"><div class="card-h"><h3>Draft reply to Acme</h3>${r.leaks ? '<span class="pill bad">contains Finance-only data</span>' : '<span class="pill ok">customer-safe</span>'}</div>
        <div class="reply ${r.leaks ? "leak" : ""}">${esc(r.reply)}</div>
        <div class="row gap"><button id="approve-reply" class="ok-btn">Approve and send (simulated)</button><span id="approve-out" class="small"></span></div></div>
    </div>`;
  $("#approve-reply").onclick = async () => {
    const a = await api("/api/case/approve", { tenant: S.tenant, approver: "p_sam" });
    $("#approve-out").innerHTML = a.ok ? '<span class="pill ok">Approved by Sam Okafor, Head of Support</span>' : `<span class="pill bad">${esc(a.reason)}</span>`;
  };
}

/* ---------- memory ---------- */
async function loadMemory() {
  $("#mem-who").textContent = nameOf(S.asker);
  const m = await api(`/api/memory?tenant=${S.tenant}&asker=${S.asker}`);
  const seen = new Set();
  const uniq = m.filter((e) => !seen.has(e.text) && seen.add(e.text));
  $("#mem-list").innerHTML = uniq.length ? uniq.map((e) => `<div class="mem"><time>${esc(e.ts.replace("T", " ").slice(0, 16))} · ${esc(e.kind)}${e.about.length ? " · " + esc(e.about.join(", ")) : ""}</time>${esc(e.text)}</div>`).join("") : '<p class="muted small">No memories yet. Ask something on the Ask tab.</p>';
}
async function peek() {
  const owner = $("#peek-owner").value;
  const r = await api(`/api/memory/peek?tenant=${S.tenant}&asker=${S.asker}&owner=${owner}`);
  $("#peek-out").innerHTML = `<div class="result ${r.asker_can_reach ? "fail" : "pass"}">
    <b>${esc(nameOf(owner))} has ${r.owner_has} memories. ${esc(nameOf(S.asker))} can reach ${r.asker_can_reach} of them.</b>
    <span class="small">The query has to start at your own node, and no path leads from you to another person's memories:</span>
    <pre class="small" style="white-space:pre-wrap;margin:0;font-family:var(--mono)">${esc(r.query)}</pre></div>`;
}

/* ---------- oversharing ---------- */
function meter(label, n, max, ok) {
  return `<div class="meter"><span>${esc(label)}</span><span class="track"><span class="fill ${ok ? "ok" : ""}" style="display:block;width:${Math.max(2, Math.round(100 * n / max))}%"></span></span><b>${n}</b></div>`;
}
async function runScan() {
  const r = await busy($("#scan-out"), () => api(`/api/scan?tenant=${S.tenant}`));
  const over = r.overshared.map((f, i) => {
    const max = Math.max(f.actual_readers, 1);
    return `<div class="find" id="find-o${i}">
      <div class="card-h"><h3>${esc(f.title)}</h3><span class="pill bad">${f.extra_readers} people too many${f.external_readers ? ` · ${f.external_readers} external` : ""}</span></div>
      ${meter("Should read", f.intended_readers, max, true)}${meter("Can read", f.actual_readers, max, false)}
      <dl class="kv"><dt>Cause</dt><dd>Grant to <b>${esc(f.culprit.grantee_name)}</b> (${f.culprit.extra} extra people through nested groups)</dd>
        <dt>Granted by</dt><dd>${esc(f.culprit.granted_by)} on ${esc(f.culprit.granted_at)}</dd><dt>Reason given</dt><dd>${esc(f.culprit.reason)}</dd>
        <dt>Proposed fix</dt><dd>${esc(f.fix.summary)}</dd></dl>
      <div class="row gap"><button class="ghost" data-test="o${i}">Test the fix on a copy of the graph</button></div><div class="test-out"></div></div>`;
  }).join("");
  const drift = r.drift.map((f, i) => `<div class="find" id="find-d${i}">
      <div class="card-h"><h3>${esc(f.name)} changed teams but kept old access</h3><span class="pill warn">access drift</span></div>
      <dl class="kv"><dt>Now</dt><dd>${esc(f.title)} (${esc(f.team)})</dd><dt>Moved</dt><dd>from ${esc(f.moved_from)} on ${esc(f.moved_at)}</dd>
        <dt>Still in</dt><dd>${esc(f.group_name)}, which opens ${f.docs_count} documents: ${f.docs_via_old_team.map(esc).join(", ")}</dd><dt>Proposed fix</dt><dd>${esc(f.fix.summary)}</dd></dl>
      <div class="row gap"><button class="ghost" data-test="d${i}">Test the fix on a copy of the graph</button></div><div class="test-out"></div></div>`).join("");
  $("#scan-out").innerHTML = over + drift || '<div class="card"><p>No oversharing found.</p></div>';
  S.findings = { o: r.overshared, d: r.drift };
  document.querySelectorAll("[data-test]").forEach((b) => b.onclick = () => testFix(b.dataset.test));
  loadAudit();
}
async function testFix(key) {
  const f = S.findings[key[0]][Number(key.slice(1))];
  const card = $(`#find-${key}`), out = card.querySelector(".test-out");
  const t = await busy(card, () => api("/api/scan/test", { tenant: S.tenant, fix: f.fix, doc: f.doc || null }));
  const lines = f.doc
    ? `Readers ${t.readers_before} → <b>${t.readers_after}</b>. Everyone who should keep access still has it: ${t.intended_kept ? "yes" : "NO (" + t.intended_lost.length + " lose access)"}.`
    : `${esc(f.name)} can read ${t.sections_before} → <b>${t.sections_after}</b> passages.`;
  out.innerHTML = `<div class="result ${t.passed ? "pass" : "fail"}"><b>${t.passed ? "Test passed" : "Test failed"} on fork <code>${esc(t.fork)}</code></b><span>${lines}</span>
    <span class="small muted">The fork was made with GRAPH.COPY and deleted after the test. The live company was not touched.</span>
    ${t.passed ? `<div class="row gap"><button class="ok-btn" data-apply="${key}">Approve and apply</button><span class="small muted">as ${f.doc ? "Neha Shah, Head of People" : "Lena Brooks, Head of Engineering"}</span></div>` : ""}</div>`;
  const ab = out.querySelector("[data-apply]");
  if (ab) ab.onclick = async () => {
    const approver = f.doc ? "p_neha" : "p_lena";
    const a = await busy(card, () => api("/api/scan/apply", { tenant: S.tenant, fix: f.fix, doc: f.doc || null, approver, reason: "Approved after testing on a copy of the graph" }));
    out.insertAdjacentHTML("beforeend", `<div class="result pass"><b>Applied.</b> Recorded as decision <code>${esc(a.decision)}</code>, so anyone can later ask who changed this access and why.</div>`);
    ab.disabled = true;
    loadAudit();
  };
}
async function loadAudit() {
  const a = await api(`/api/audit?tenant=${S.tenant}`);
  $("#audit-out").innerHTML = a.length ? `<div class="card"><h3>Access decisions</h3>${a.map((d) => `<div class="decision"><b>${esc(d.summary)}</b><br><span class="muted small">by ${esc(d.by)} · ${esc(d.date)} · ${esc(d.reason)}</span></div>`).join("")}</div>` : "";
}

/* ---------- proof ---------- */
async function loadEval() {
  const r = await busy($("#eval-out"), () => api("/api/eval"));
  const st = await api(`/api/stats?tenant=${S.tenant}`);
  const m = r.modes, row = (name, x, cls) => `<tr><td>${name}</td><td class="num ${cls}">${x.leaks}</td><td class="num">${x.wrong_denials}</td><td class="num">${x.helpfulness}%</td></tr>`;
  const nodes = Object.values(st.nodes).reduce((a, b) => a + b, 0), edges = Object.values(st.edges).reduce((a, b) => a + b, 0);
  $("#eval-out").innerHTML = `<div class="card"><div class="tbl"><table class="t"><thead><tr><th>Access check</th><th>Leaks</th><th>Wrong denials</th><th>Helpfulness</th></tr></thead><tbody>
      ${row("Graph traversal (Need-to-Know)", m.graph)}${row("Flat list: direct groups only", m.flat)}${row("Off: plain document chatbot", m.off)}</tbody></table></div>
      <p class="muted small">${r.askers} people and agents × ${r.questions} questions, every passage the search returned. FalkorDB's traversal matches an independent Python ground truth on ${r.agreement_with_ground_truth_pct}% of ${r.checked_pairs.toLocaleString()} (principal, passage) pairs.</p></div>
    <div class="stats">
      <div class="stat"><b>${r.latency_ms.p50} ms</b><span>median access check (one traversal)</span></div>
      <div class="stat"><b>${r.latency_ms.p95} ms</b><span>95th percentile</span></div>
      <div class="stat"><b>${r.latency_ms.concurrent_checks_per_sec}</b><span>checks per second, 8 threads</span></div>
      <div class="stat"><b>${r.memory_writes_per_sec}</b><span>concurrent memory writes per second</span></div>
      <div class="stat"><b>${nodes.toLocaleString()}</b><span>nodes in ${esc(st.tenant)}</span></div>
      <div class="stat"><b>${edges.toLocaleString()}</b><span>edges in ${esc(st.tenant)}</span></div>
    </div>
    <div class="card"><h3>One FalkorDB instance, one graph per company</h3><p class="small">Graphs right now: ${st.graphs.map((g) => `<code>${esc(g)}</code>`).join(", ")}. Forks created to test fixes are deleted straight after.</p></div>`;
}

/* ---------- wiring ---------- */
function showTab(t) {
  S.tab = t;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".panel").forEach((p) => p.hidden = p.id !== `tab-${t}`);
  if (t === "memory") loadMemory();
}
document.addEventListener("click", (e) => {
  const p = e.target.closest(".persona");
  if (p) { S.asker = p.dataset.id; document.querySelectorAll(".persona").forEach((x) => x.classList.toggle("on", x === p)); if (S.tab === "memory") loadMemory(); if ($("#q").value && S.tab === "ask") ask(); }
  const c = e.target.closest("#samples .chip");
  if (c) ask(c.textContent);
  const tb = e.target.closest(".tab");
  if (tb) showTab(tb.dataset.tab);
  const mb = e.target.closest("#mode button");
  if (mb) { setMode(mb.dataset.mode); if (S.tab === "ask" && $("#q").value) ask(); if (S.tab === "compare") compare(); }
});
$("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask(); });
$("#cmp-form").addEventListener("submit", (e) => { e.preventDefault(); compare(); });
$("#run-case").onclick = () => runCase("graph");
$("#run-case-off").onclick = () => runCase("off");
$("#peek").onclick = peek;
$("#run-scan").onclick = runScan;
$("#run-eval").onclick = loadEval;
$("#tenant").onchange = async (e) => { S.tenant = e.target.value; await loadPeople(); $("#answer").innerHTML = ""; $("#pathviz").innerHTML = ""; };

(async function boot() {
  try {
    const h = await api("/api/health");
    $("#health").textContent = `FalkorDB ${h.ok ? "connected" : "unreachable"} · language model ${h.llm ? "on" : "off (deterministic answers)"}`;
  } catch { $("#health").textContent = "API unreachable"; }
  await loadTenants();
  await loadPeople();
  const hash = location.hash.slice(1);
  if (["ask", "compare", "agents", "memory", "scan", "proof"].includes(hash)) showTab(hash);
  if (S.tenant === "northwind") ask(S.samples.northwind[0]);
})();
