"use strict";
const S = { tenant: "northwind", viewer: "p_priya", personas: [], view: "ask", samples: {}, lastQ: "" };
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (n) => String(n || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
const MODE_NAME = { graph: "Full graph check", flat: "Simple permission list", off: "No check (plain chatbot)" };

/* ---------- data access: live API, or the static demo built from it in CI ---------- */
let SNAP = null;
const STATIC_AUDIT = [];
let lastCaseMode = "graph";
function sortKeys(o) { return Object.fromEntries(Object.keys(o).sort().map((k) => [k, o[k]])); }
async function staticApi(path, body) {
  if (!SNAP) SNAP = await (await fetch(window.NTK_STATIC)).json();
  const u = new URL(path, location.href), q = (k) => u.searchParams.get(k), p = u.pathname.replace(/^.*\/api\//, "");
  const need = (v, msg) => { if (v === undefined) throw new Error(msg || "That isn't part of the online demo. Run the app locally (one docker command in the README) to try anything."); return v; };
  const ask = (t, a, qq, m) => need(SNAP.ask[[t, a, qq, m].join("|")], "The online demo answers the suggested questions. Run it locally (one docker command in the README) to ask anything.");
  switch (p) {
    case "health": return SNAP.health;
    case "tenants": return SNAP.tenants;
    case "people": return SNAP.people[q("tenant")];
    case "overview": return need(SNAP.overview?.[q("tenant")]?.[q("viewer")]);
    case "ask": return ask(body.tenant, body.asker, body.question, body.mode);
    case "compare": return body.askers.map((a) => ask(body.tenant, a, body.question, body.mode));
    case "memory": return SNAP.memory[q("tenant")]?.[q("asker")] || [];
    case "memory/peek": return need(SNAP.peek[q("tenant")]?.[q("asker")]?.[q("owner")]);
    case "case/run": lastCaseMode = body.mode; return need(SNAP.case[body.mode]);
    case "case/approve": return SNAP.approve[lastCaseMode];
    case "scan": return SNAP.scan[q("tenant")];
    case "scan/test": return need(SNAP.scan_test[JSON.stringify(sortKeys(body.fix))]);
    case "scan/apply": { const r = need(SNAP.scan_apply[JSON.stringify(sortKeys(body.fix))]); STATIC_AUDIT.splice(0, STATIC_AUDIT.length, ...r.audit); return r; }
    case "audit": return STATIC_AUDIT;
    case "eval": return SNAP.eval;
    case "stats": return SNAP.stats[q("tenant")];
    case "reset": STATIC_AUDIT.length = 0; return { ok: true };
  }
  throw new Error("That isn't part of the online demo.");
}
async function api(path, body) {
  if (window.NTK_STATIC) return staticApi(path, body);
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.detail?.message || data.detail || r.statusText), { data });
  return data;
}
async function busy(el, fn) { el?.classList.add("spin"); try { return await fn(); } finally { el?.classList.remove("spin"); } }
const person = (id) => S.personas.find((p) => p.id === id) || { id, name: id, title: "" };
const avatar = (p, cls = "") => `<span class="av ${p.kind === "Agent" ? "bot" : ""} ${cls}">${p.kind === "Agent" ? "AI" : esc(initials(p.name))}</span>`;
const firstName = (id) => person(id).name.split(" ")[0];
const errBox = (e) => `<div class="answer"><p class="a-text">${esc(e.message)}</p></div>`;

/* ---------- viewer ("viewing as") ---------- */
function renderWho() {
  const p = person(S.viewer);
  $("#who").innerHTML = `${avatar(p)}<span><b>${esc(p.name)}</b> <small>${esc(p.title || "")}</small></span>`;
  $("#who-menu").innerHTML = S.personas.map((x) => `<button type="button" role="option" data-id="${x.id}" class="${x.id === S.viewer ? "on" : ""}">${avatar(x)}<span><b>${esc(x.name)}</b><small>${esc(x.title || "")}</small></span></button>`).join("");
}
function setViewer(id) {
  S.viewer = id;
  renderWho();
  $("#who-menu").hidden = true;
  $("#who").setAttribute("aria-expanded", "false");
  if (S.view === "ask" && S.lastQ) { $("#thread").innerHTML = ""; ask(S.lastQ); }
  if (S.view === "company") renderCompany();
}

/* ---------- Ask ---------- */
function answerHTML(a, compact) {
  const p = person(a.asker);
  const hidden = a.redacted.length, leaks = a.leaks;
  const badge = leaks ? `<span class="badge bad">${leaks} private item${leaks > 1 ? "s" : ""} leaked</span>`
    : hidden ? `<span class="badge lock"><svg width="12" height="12"><use href="#i-lock"/></svg>${hidden} hidden from ${esc(firstName(a.asker))}</span>`
    : `<span class="badge ok">Everything relevant is visible</span>`;
  const mem = (a.memory || []).filter((m) => m.text !== `Asked: ${a.question}`).slice(0, 1)
    .map((m) => `<p class="note-line">Remembered for ${esc(firstName(a.asker))}: ${esc(m.text.replace(/^Asked: /, "earlier you asked “") + (m.text.startsWith("Asked: ") ? "”" : ""))}</p>`).join("");
  const sources = a.facts.map((f) => `<div class="src ${f.leak ? "leak" : ""}"><svg><use href="#i-doc"/></svg><div>
      <div class="t">${esc(f.label)}${f.leak ? ' <span class="badge bad">not allowed</span>' : ""}</div>
      ${compact ? "" : `<div>${esc(f.text)}</div>`}
      <div class="m">${esc(f.source.title)} · ${esc(f.source.kind)}${f.source.owner ? " · owner " + esc(f.source.owner) : ""} · updated ${esc(f.source.updated)}</div></div></div>`).join("");
  const locked = a.redacted.map((r) => `<div class="locked"><svg><use href="#i-lock"/></svg><div><b>${esc(r.label)}</b> in ${esc(r.doc_title)}${r.needs.length ? `. Needs ${r.needs.map(esc).join(" or ")} access` : ""}${r.owner ? `. Ask ${esc(r.owner)}.` : "."}</div></div>`).join("");
  const decisions = a.decisions.map((d) => `<p class="note-line">Decision by ${esc(d.made_by)} on ${esc(d.date)}: ${esc(d.summary)} ${d.source ? `(decided in ${esc(d.source)})` : "(the original discussion is hidden from you)"}</p>`).join("");
  const helpers = [...new Set([...a.facts.map((f) => f.source.owner), ...a.redacted.map((r) => r.owner)].filter(Boolean))];
  const chains = a.facts.filter((f) => f.why).map((f) => {
    const names = f.why.names.slice(0, -1);
    return `<div class="chain">${names.map((n, i) => `<span>${esc(i === 0 ? n : n)}</span>`).join("<i>→</i>")}<i>→</i><span class="end">${esc(f.label)}</span></div>`;
  }).join("");
  return `<article class="answer">
    <div class="a-head">${avatar(p)}<span>Answer for <b>${esc(p.name)}</b></span><span style="margin-left:auto">${badge}</span></div>
    <p class="a-text">${esc(a.answer.text)}</p>
    ${mem}
    ${sources ? `<div class="block"><h4>Sources</h4>${sources}</div>` : ""}
    ${locked ? `<div class="block"><h4>Hidden from ${esc(firstName(a.asker))}</h4>${locked}</div>` : ""}
    ${decisions}
    ${!compact && helpers.length ? `<div class="block"><h4>People who can help</h4><div class="people">${helpers.map((h) => `<span class="person"><span class="av">${esc(initials(h))}</span>${esc(h)}</span>`).join("")}</div></div>` : ""}
    ${!compact && chains ? `<details class="why"><summary>Why can ${esc(firstName(a.asker))} see this?</summary>${chains}<p class="tiny muted">Each line is a chain of team and group memberships in the company graph. FalkorDB follows it on every question.</p></details>` : ""}
    ${compact ? "" : `<div class="row gap"><span class="tiny muted">See how someone else sees this:</span><select data-compare aria-label="Compare with">${['<option value="">Choose a person…</option>', ...S.personas.filter((x) => x.id !== a.asker).map((x) => `<option value="${x.id}">${esc(x.name)}, ${esc(x.title || "")}</option>`)].join("")}</select></div><div class="cmp-slot"></div>`}
  </article>`;
}
async function ask(q) {
  q = (q ?? $("#q").value).trim();
  if (!q) return;
  S.lastQ = q;
  $("#q").value = "";
  const wrap = document.createElement("div");
  wrap.style.display = "flex"; wrap.style.flexDirection = "column"; wrap.style.gap = "10px";
  wrap.innerHTML = `<div class="qline">${esc(q)}</div><div class="answer spin"><p class="muted">Checking what ${esc(firstName(S.viewer))} can see…</p></div>`;
  $("#thread").prepend(wrap);
  try {
    const a = await api("/api/ask", { tenant: S.tenant, asker: S.viewer, question: q, mode: "graph" });
    wrap.lastElementChild.outerHTML = answerHTML(a);
    const sel = wrap.querySelector("[data-compare]");
    sel.onchange = async () => {
      if (!sel.value) return;
      const slot = wrap.querySelector(".cmp-slot");
      try {
        const [x, y] = await busy(slot, () => api("/api/compare", { tenant: S.tenant, question: q, askers: [a.asker, sel.value], mode: "graph" }));
        slot.innerHTML = `<div class="split">${answerHTML(x, true)}${answerHTML(y, true)}</div>`;
      } catch (e) { slot.innerHTML = errBox(e); }
    };
  } catch (e) { wrap.lastElementChild.outerHTML = errBox(e); }
}

/* ---------- Company ---------- */
async function renderCompany() {
  const box = $("#v-company");
  let o, mem;
  try {
    [o, mem] = await busy(box, () => Promise.all([api(`/api/overview?tenant=${S.tenant}&viewer=${S.viewer}`), api(`/api/memory?tenant=${S.tenant}&asker=${S.viewer}`)]));
  } catch (e) { box.innerHTML = errBox(e); return; }
  const c = o.counts, me = person(S.viewer);
  const seen = new Set(), memU = mem.filter((m) => !seen.has(m.text) && seen.add(m.text)).slice(0, 6);
  const stat = (n, l) => `<div class="stat"><b>${(n || 0).toLocaleString()}</b><span>${l}</span></div>`;
  box.innerHTML = `
    <div class="hero left"><h1>${esc(o.company)}</h1>
      <p class="muted">Everything the brain has connected: people, teams, documents, chats, tickets, customers and decisions. As ${esc(me.name)} you can open ${o.documents.visible} of ${o.documents.total} documents.</p></div>
    <div class="stats">${stat(c.Person, "people")}${stat(o.teams.length, "teams")}${stat(o.documents.total, "documents and chats")}${stat(c.Customer, "customers")}${stat(c.Decision, "decisions")}${stat(c.Agent, "AI agents")}</div>
    <div class="grid">
      <div class="card"><h3>Teams</h3><div class="list">${o.teams.map((t) => `<div><span>${esc(t.name)}</span><span class="r">${t.people} people</span></div>`).join("")}</div></div>
      <div class="card"><h3>Customers</h3><div class="list">${o.customers.map((x) => `<div><span>${esc(x.name)}</span><span class="r">${x.owner ? "account owner " + esc(x.owner) : ""}</span></div>`).join("") || '<p class="muted tiny">No customers in this company.</p>'}</div>
        <h3>Decisions</h3><div class="list">${o.decisions.map((d) => `<div><span>${esc(d.summary)}</span><span class="r">${esc(d.by)}<br>${esc(d.date)}</span></div>`).join("") || '<p class="muted tiny">None visible to you.</p>'}</div>
        ${o.decisions_hidden ? `<p class="tiny muted"><svg width="12" height="12"><use href="#i-lock"/></svg> ${o.decisions_hidden} more decision${o.decisions_hidden > 1 ? "s" : ""} hidden from you.</p>` : ""}</div>
      <div class="card"><h3>AI agents</h3><div class="list">${o.agents.map((x) => `<div><span>${esc(x.name)}<br><span class="tiny muted">${esc(x.role || "")}</span></span><span class="r">${x.groups.map(esc).join(", ")}</span></div>`).join("") || '<p class="muted tiny">No agents.</p>'}</div>
        <p class="tiny muted">Agents are members of groups, just like people, so they get exactly the access their group has.</p></div>
      <div class="card"><h3>What the brain remembers about ${esc(firstName(S.viewer))}</h3>
        <div class="list">${memU.map((m) => `<div><span>${esc(m.text)}</span><span class="r">${esc(m.ts.slice(0, 10))}</span></div>`).join("") || '<p class="muted tiny">Nothing yet. Ask something on the Ask page.</p>'}</div>
        <p class="tiny muted">Private to ${esc(firstName(S.viewer))}. Try reading someone else's:</p>
        <div class="row gap"><select id="peek-owner" aria-label="Whose memory">${S.personas.filter((x) => x.id !== S.viewer).map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join("")}</select><button id="peek" class="btn" type="button">Try it</button></div>
        <div id="peek-out"></div></div>
    </div>`;
  $("#peek").onclick = async () => {
    const owner = $("#peek-owner").value;
    try {
      const r = await api(`/api/memory/peek?tenant=${S.tenant}&asker=${S.viewer}&owner=${owner}`);
      $("#peek-out").innerHTML = `<div class="result ${r.asker_can_reach ? "fail" : "pass"}"><b>${esc(person(owner).name)} has ${r.owner_has} memories. ${esc(firstName(S.viewer))} can reach ${r.asker_can_reach}.</b><span class="tiny">Memories hang off their owner in the graph, and every memory query starts at your own node, so there is no path to anyone else's.</span></div>`;
    } catch (e) { $("#peek-out").innerHTML = errBox(e); }
  };
}

/* ---------- Agents at work ---------- */
async function runCase(mode) {
  const out = $("#case-out");
  let r;
  try { r = await busy(out, () => api("/api/case/run", { tenant: S.tenant, mode })); } catch (e) { out.innerHTML = errBox(e); return; }
  const steps = r.steps.map((s) => `<div class="step"><span class="num">${s.step}</span><div><b>${esc(s.actor)}</b><p>${esc(s.did)}</p>
      <div class="checks">${s.checks.map((c) => `<span class="badge ${c.ok ? "ok" : "lock"}">${c.ok ? "can see" : "hidden"}: ${esc(c.what)}</span>`).join("")}</div></div></div>`).join("");
  const notes = r.view.notes.map((n) => n.visible
    ? `<div class="note ${n.leak ? "leak" : ""}"><span class="who-line">${esc(n.author)}${n.restricted ? " · Finance only" : ""}${n.leak ? ' · <b style="color:var(--bad)">leaked</b>' : ""}</span>${esc(n.text)}</div>`
    : `<div class="locked"><svg><use href="#i-lock"/></svg><div><b>Finance-only note</b> from ${esc(n.author)} is hidden from the Support Agent.</div></div>`).join("");
  out.innerHTML = `
    <div class="card"><h3>${mode === "off" ? "Without access checks" : "With the graph checking access"}</h3><div class="steps">${steps}</div></div>
    <div class="card"><h3>The shared case, as the Support Agent sees it</h3>${notes}
      <p class="tiny muted">Handoffs: ${r.view.handoffs.map((h) => `${esc(h.from)} → ${esc(h.to)}`).join(", ")}</p></div>
    <div class="card"><div class="row gap"><h3>Draft reply to Acme</h3>${r.leaks ? '<span class="badge bad">contains private Finance data</span>' : '<span class="badge ok">safe to send</span>'}</div>
      <div class="reply ${r.leaks ? "leak" : ""}">${esc(r.reply)}</div>
      <div class="row gap"><button id="approve" class="btn good" type="button">Approve and send</button><span id="approve-out" class="tiny"></span></div></div>`;
  $("#approve").onclick = async () => {
    const a = await api("/api/case/approve", { tenant: S.tenant, approver: "p_sam" });
    $("#approve-out").innerHTML = a.ok ? '<span class="badge ok">Approved by Sam Okafor, Head of Support (simulated send)</span>' : `<span class="badge bad">${esc(a.reason)}</span>`;
  };
}

/* ---------- Health check ---------- */
function meter(label, n, max, ok) {
  return `<div class="meter"><span>${esc(label)}</span><span class="track"><span class="fill ${ok ? "ok" : ""}" style="width:${Math.max(2, Math.round(100 * n / max))}%"></span></span><b>${n}</b></div>`;
}
async function runScan() {
  let r;
  try { r = await busy($("#scan-out"), () => api(`/api/scan?tenant=${S.tenant}`)); } catch (e) { $("#scan-out").innerHTML = errBox(e); return; }
  const over = r.overshared.map((f, i) => `<div class="card" id="find-o${i}">
      <div class="row gap"><h3>${esc(f.title)}</h3><span class="badge bad">${f.extra_readers} people too many${f.external_readers ? `, ${f.external_readers} outside the company` : ""}</span></div>
      ${meter("Should open it", f.intended_readers, f.actual_readers, true)}${meter("Can open it", f.actual_readers, f.actual_readers, false)}
      <p class="tiny">Why: it was shared with <b>${esc(f.culprit.grantee_name)}</b> by ${esc(f.culprit.granted_by)} on ${esc(f.culprit.granted_at)} ("${esc(f.culprit.reason)}"). That group contains other groups, which adds ${f.culprit.extra} people.</p>
      <p class="tiny"><b>Suggested fix:</b> ${esc(f.fix.summary)}</p>
      <div class="row gap"><button class="btn" type="button" data-test="o${i}">Test the fix on a copy</button></div><div class="test-out"></div></div>`).join("");
  const drift = r.drift.map((f, i) => `<div class="card" id="find-d${i}">
      <div class="row gap"><h3>${esc(f.name)} changed teams but kept old access</h3><span class="badge warn">out of date</span></div>
      <p class="tiny">${esc(f.name)} moved from ${esc(f.moved_from)} to ${esc(f.team)} on ${esc(f.moved_at)} but is still in <b>${esc(f.group_name)}</b>. That alone lets them open ${f.docs_count} things: ${f.docs_via_old_team.map(esc).join(", ")}.</p>
      <p class="tiny"><b>Suggested fix:</b> ${esc(f.fix.summary)}</p>
      <div class="row gap"><button class="btn" type="button" data-test="d${i}">Test the fix on a copy</button></div><div class="test-out"></div></div>`).join("");
  $("#scan-out").innerHTML = (over + drift) || '<div class="card"><p>Everything looks healthy.</p></div>';
  S.findings = { o: r.overshared, d: r.drift };
  document.querySelectorAll("[data-test]").forEach((b) => b.onclick = () => testFix(b.dataset.test));
  loadAudit();
}
async function testFix(key) {
  const f = S.findings[key[0]][Number(key.slice(1))];
  const card = $(`#find-${key}`), out = card.querySelector(".test-out");
  let t;
  try { t = await busy(card, () => api("/api/scan/test", { tenant: S.tenant, fix: f.fix, doc: f.doc || null })); } catch (e) { out.innerHTML = errBox(e); return; }
  const line = f.doc ? `People who can open it: ${t.readers_before} → <b>${t.readers_after}</b>. Everyone who should keep access still has it: <b>${t.intended_kept ? "yes" : "no"}</b>.`
    : `${esc(f.name)} could open ${t.sections_before} passages; after the fix ${t.sections_after}.`;
  out.innerHTML = `<div class="result ${t.passed ? "pass" : "fail"}"><b>${t.passed ? "The fix works" : "The fix would break something"}</b><span>${line}</span>
    <span class="tiny muted">Tested on a full copy of the company (FalkorDB GRAPH.COPY), then the copy was deleted. Nothing real changed yet.</span>
    ${t.passed ? `<div class="row gap"><button class="btn good" type="button" data-apply>Approve and apply</button><span class="tiny muted">as ${f.doc ? "Neha Shah, Head of People" : "Lena Brooks, Head of Engineering"}</span></div>` : ""}</div>`;
  const ab = out.querySelector("[data-apply]");
  if (ab) ab.onclick = async () => {
    try {
      const a = await busy(card, () => api("/api/scan/apply", { tenant: S.tenant, fix: f.fix, doc: f.doc || null, approver: f.doc ? "p_neha" : "p_lena", reason: "Approved after testing on a copy" }));
      out.insertAdjacentHTML("beforeend", `<div class="result pass"><b>Done.</b> The change is saved as a decision, so anyone can later ask who changed this access and why.</div>`);
      ab.disabled = true;
      loadAudit();
    } catch (e) { out.insertAdjacentHTML("beforeend", errBox(e)); }
  };
}
async function loadAudit() {
  const a = await api(`/api/audit?tenant=${S.tenant}`);
  $("#audit-out").innerHTML = a.length ? `<div class="card"><h3>Access changes</h3><div class="list">${a.map((d) => `<div><span>${esc(d.summary)}</span><span class="r">${esc(d.by)}<br>${esc(String(d.date).slice(0, 10))}</span></div>`).join("")}</div></div>` : "";
}

/* ---------- How it works ---------- */
function renderHow() {
  const qs = S.samples[S.tenant] || [];
  $("#v-how").innerHTML = `
    <div class="hero left"><h1>How it works</h1><p class="muted">A company brain is only useful if people can trust it with private things. Need-to-Know does that with a graph.</p></div>
    <div class="grid">
      <div class="card"><span class="num">1</span><h3>Everything becomes a graph</h3><p class="muted">People, teams, groups, AI agents, documents, tickets, chats, customers and decisions are nodes in FalkorDB. Who can open what is stored as connections.</p></div>
      <div class="card"><span class="num">2</span><h3>Every question follows your path</h3><p class="muted">Access often comes through groups inside groups. One FalkorDB query follows every chain from you to each document, in about 0.3 milliseconds.</p></div>
      <div class="card"><span class="num">3</span><h3>The AI only sees what you can</h3><p class="muted">The graph decides what you may see. Hidden text is never sent to an AI model, so it cannot leak it.</p></div>
    </div>
    <div class="card"><h3>Try it without the graph</h3>
      <p class="muted tiny">Ask the same question three ways and compare.</p>
      <div class="row gap"><select id="try-q" aria-label="Question">${qs.map((q) => `<option>${esc(q)}</option>`).join("")}</select>
        <select id="try-who" aria-label="Person">${S.personas.map((x) => `<option value="${x.id}" ${x.id === S.viewer ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
        <button id="try-run" class="btn primary" type="button">Compare</button></div>
      <div id="try-out"></div></div>
    <div class="card"><h3>Measured</h3><p class="muted tiny">Every person and agent, every suggested question, checked against an independent answer key.</p><div id="eval-out"><button id="load-eval" class="btn" type="button">Show results</button></div></div>
    <div class="card"><h3>Built on FalkorDB</h3><div class="list">
      <div><span>Nested group traversal for every access check</span><span class="r">MATCH (p)-[:MEMBER_OF*0..8]->(g)-[:CAN_READ]->(t)</span></div>
      <div><span>Full-text search over documents and chats</span><span class="r">db.idx.fulltext</span></div>
      <div><span>Safe "what if" testing of fixes</span><span class="r">GRAPH.COPY</span></div>
      <div><span>One private graph per company</span><span class="r">multi-graph</span></div>
      <div><span>Tools for other AI apps</span><span class="r">MCP server</span></div></div>
      <p class="tiny"><a href="https://github.com/mrayhankhan/need-to-know">Code, data model and every query on GitHub</a></p></div>`;
  $("#try-run").onclick = async () => {
    const q = $("#try-q").value, who = $("#try-who").value, out = $("#try-out");
    try {
      const res = await busy(out, () => Promise.all(["graph", "flat", "off"].map((m) => api("/api/ask", { tenant: S.tenant, asker: who, question: q, mode: m }))));
      out.innerHTML = `<div class="grid" style="margin-top:8px">${res.map((a) => `<div class="card"><h3>${MODE_NAME[a.mode]}</h3>
        ${a.leaks ? `<span class="badge bad">${a.leaks} leaked</span>` : '<span class="badge ok">no leaks</span>'}
        ${a.redacted.some((r) => r.wrongly_hidden) ? `<span class="badge warn">${a.redacted.filter((r) => r.wrongly_hidden).length} wrongly hidden</span>` : ""}
        <div class="list">${a.facts.map((f) => `<div><span>${esc(f.label)}</span><span class="r">${f.leak ? '<span class="badge bad">leak</span>' : "shown"}</span></div>`).join("")}
        ${a.redacted.map((r) => `<div><span>${esc(r.label)}</span><span class="r">${r.wrongly_hidden ? '<span class="badge warn">should show</span>' : "hidden"}</span></div>`).join("")}</div></div>`).join("")}</div>`;
    } catch (e) { out.innerHTML = errBox(e); }
  };
  $("#load-eval").onclick = loadEval;
}
async function loadEval() {
  const box = $("#eval-out");
  let r;
  try { r = await busy(box, () => api("/api/eval")); } catch (e) { box.innerHTML = errBox(e); return; }
  const m = r.modes, row = (k) => `<tr><td>${MODE_NAME[k]}</td><td class="n">${m[k].leaks}</td><td class="n">${m[k].wrong_denials}</td></tr>`;
  box.innerHTML = `<div class="tbl"><table class="t"><thead><tr><th>Access check</th><th>Private items leaked</th><th>Allowed items wrongly hidden</th></tr></thead><tbody>${row("graph")}${row("flat")}${row("off")}</tbody></table></div>
    <p class="tiny muted">${r.askers} people and agents × ${r.questions} questions. The graph matches the answer key on ${r.agreement_with_ground_truth_pct}% of ${r.checked_pairs.toLocaleString()} checks. Median access check ${r.latency_ms.p50} ms.</p>`;
}

/* ---------- navigation and boot ---------- */
const TITLES = { ask: "Ask", company: "Company", agents: "Agents at work", health: "Health check", how: "How it works" };
function showView(v) {
  S.view = v;
  document.querySelectorAll(".nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  document.querySelectorAll(".view").forEach((s) => s.hidden = s.id !== `v-${v}`);
  $("#view-title").textContent = TITLES[v];
  if (v === "company") renderCompany();
  if (v === "how") renderHow();
}
async function loadTenants() {
  const ts = await api("/api/tenants");
  $("#tenant").innerHTML = ts.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
  $("#tenant").value = S.tenant;
  S.samples = Object.fromEntries(ts.map((t) => [t.id, t.samples]));
  S.company = Object.fromEntries(ts.map((t) => [t.id, t.name]));
}
async function loadPeople() {
  const r = await api(`/api/people?tenant=${S.tenant}`);
  S.personas = r.personas;
  if (!S.personas.find((p) => p.id === S.viewer)) S.viewer = S.personas[0]?.id;
  renderWho();
  $("#hero-title").textContent = `Ask ${S.company[S.tenant].split(" ")[0]} anything`;
  $("#chips").innerHTML = (S.samples[S.tenant] || []).map((q) => `<button class="chip" type="button">${esc(q)}</button>`).join("");
}
document.addEventListener("click", (e) => {
  const nav = e.target.closest(".nav button"); if (nav) showView(nav.dataset.view);
  const chip = e.target.closest(".chip"); if (chip) ask(chip.textContent);
  const opt = e.target.closest("#who-menu button"); if (opt) setViewer(opt.dataset.id);
  if (e.target.closest("#who")) { const m = $("#who-menu"); m.hidden = !m.hidden; $("#who").setAttribute("aria-expanded", String(!m.hidden)); }
  else if (!e.target.closest("#who-menu")) $("#who-menu").hidden = true;
});
$("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask(); });
$("#run-case").onclick = () => runCase("graph");
$("#run-case-off").onclick = () => runCase("off");
$("#run-scan").onclick = runScan;
$("#reset-demo").onclick = async () => { await api("/api/reset", { tenant: S.tenant }); location.reload(); };
$("#tenant").onchange = async (e) => { S.tenant = e.target.value; $("#thread").innerHTML = ""; S.lastQ = ""; await loadPeople(); showView(S.view); };

(async function boot() {
  try {
    const h = await api("/api/health");
    $("#status").textContent = window.NTK_STATIC ? "Online demo" : `FalkorDB ${h.ok ? "connected" : "unreachable"}`;
  } catch { $("#status").textContent = "Server unreachable"; }
  if (window.NTK_STATIC) {
    $("#notice").innerHTML = `<div class="notice">Online demo: every answer here was computed by the real FalkorDB backend${SNAP?.built_from ? " (commit " + esc(SNAP.built_from) + ")" : ""}. Use the suggested questions and switch people with “Viewing as”. To ask anything, run it locally: <a href="https://github.com/mrayhankhan/need-to-know">GitHub</a>.</div>`;
  }
  await loadTenants();
  await loadPeople();
  const hash = location.hash.slice(1);
  showView(TITLES[hash] ? hash : "ask");
  if (S.tenant === "northwind") ask(S.samples.northwind[0]);
})();
