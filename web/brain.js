/* The brain view: the real company graph drawn as a brain.
   Left hemisphere: people, teams, groups and AI agents. Right hemisphere: spaces, documents, customers.
   Grants cross the middle like nerve fibres. Asking a question sends signals along the exact
   membership chain FalkorDB used; blocked documents flash and lock. */
(function () {
  "use strict";
  const C = {
    person: "#C7D2FE", team: "#8EA2FF", group: "#7C8DB5", agent: "#C4A7FF", space: "#5EEAD4",
    doc: "#7DDCCB", customer: "#F9A8D4", me: "#FFB547", open: "#5EEAD4", locked: "#4B5263", bad: "#FF6B7A",
    member: "142,162,255", grant: "94,234,212", in: "125,220,203", about: "249,168,212",
  };
  const R = { team: 5.2, group: 3.8, person: 2.4, agent: 4, space: 5.4, doc: 3.2, customer: 4.6 };
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let cv, ctx, W = 0, H = 0, dpr = 1, data = null, byId = {}, edges = [], pulses = [], rings = [], focus = null, focusUntil = 0;
  let hover = null, tip, raf, lastSpawn = 0, layoutKey = "";

  function rng(seed) { let h = 2166136261; for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return () => { h ^= h << 13; h ^= h >>> 17; h ^= h << 5; return ((h >>> 0) % 10000) / 10000; }; }

  function hemis() {
    const rx = Math.min(W * 0.22, H * 0.62), ry = H * 0.40, cx = W / 2, cy = H / 2 + 6;
    return { rx, ry, L: { x: cx - rx * 1.06, y: cy }, Rt: { x: cx + rx * 1.06, y: cy }, cx, cy };
  }

  function layout() {
    const h = hemis(), nodes = data.nodes, parent = {};
    edges.forEach((e) => { if (e.kind === "member") (parent[e.s] ||= []).push(e.t); });
    const ring = (list, c, fx, fy, a0 = -Math.PI / 2) => list.forEach((n, i) => {
      const a = a0 + (i / list.length) * Math.PI * 2;
      n.x = c.x + Math.cos(a) * h.rx * fx; n.y = c.y + Math.sin(a) * h.ry * fy;
    });
    const near = (n, anchor, spread) => {
      const r = rng(n.id), a = r() * Math.PI * 2, d = (0.35 + r() * 0.65) * spread;
      n.x = anchor.x + Math.cos(a) * d * h.rx; n.y = anchor.y + Math.sin(a) * d * h.ry;
    };
    const teams = nodes.filter((n) => n.kind === "team");
    ring(teams, h.L, 0.58, 0.6, -Math.PI * 0.85);
    const teamOf = (t) => teams.find((x) => x.team === t);
    nodes.filter((n) => n.kind === "group").forEach((n) => {
      const up = (parent[n.id] || []).map((p) => byId[p]).find((p) => p && p.kind === "team");
      if (n.sub === "org") { n.x = h.L.x + h.rx * 0.05; n.y = h.L.y; }
      else if (n.sub === "legacy") { n.x = h.cx; n.y = h.cy + h.ry * 0.62; }
      else if (n.sub === "external") { n.x = h.L.x - h.rx * 0.78; n.y = h.L.y + h.ry * 0.7; }
      else if (n.sub === "project") { n.x = h.L.x + h.rx * 0.55; n.y = h.L.y + h.ry * 0.78; }
      else if (n.id === "g_leadership") { n.x = h.L.x + h.rx * 0.2; n.y = h.L.y - h.ry * 0.86; }
      else if (up) near(n, up, 0.2);
      else near(n, h.L, 0.4);
    });
    nodes.filter((n) => n.kind === "person").forEach((n) => {
      const t = teamOf(n.team);
      if (t) near(n, t, 0.24);
      else near(n, byId.g_contractors || h.L, 0.16);
    });
    nodes.filter((n) => n.kind === "agent").forEach((n) => {
      const g = (parent[n.id] || []).map((p) => byId[p]).find(Boolean);
      near(n, g || h.L, 0.12);
    });
    const spaces = nodes.filter((n) => n.kind === "space");
    ring(spaces, h.Rt, 0.56, 0.58, -Math.PI * 0.6);
    nodes.filter((n) => n.kind === "doc").forEach((n) => near(n, byId[n.space] || h.Rt, 0.2));
    const cust = nodes.filter((n) => n.kind === "customer");
    cust.forEach((n, i) => { const a = Math.PI * 0.12 + i * 0.32; n.x = h.Rt.x + Math.cos(a) * h.rx * 0.95; n.y = h.Rt.y + Math.sin(a) * h.ry * 0.88; });
    for (let it = 0; it < 60; it++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 0.01, min = 13;
        if (d < min) { const k = (min - d) / d / 2; a.x -= dx * k; a.y -= dy * k; b.x += dx * k; b.y += dy * k; }
      }
    }
  }

  function brainPath(c, h, side) {
    ctx.beginPath();
    for (let i = 0; i <= 120; i++) {
      const t = (i / 120) * Math.PI * 2, wob = 1 + 0.035 * Math.sin(7 * t + side) + 0.02 * Math.sin(13 * t + 1.7 * side);
      const flat = Math.cos(t) * side < 0 ? 0.9 : 1;
      const x = c.x + Math.cos(t) * h.rx * 1.12 * wob * flat, y = c.y + Math.sin(t) * h.ry * 1.13 * wob;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
  }

  function drawBrain(now) {
    const h = hemis();
    [[h.L, -1], [h.Rt, 1]].forEach(([c, side]) => {
      const g = ctx.createRadialGradient(c.x, c.y, 10, c.x, c.y, h.rx * 1.3);
      g.addColorStop(0, side < 0 ? "rgba(142,162,255,0.10)" : "rgba(94,234,212,0.09)");
      g.addColorStop(1, "rgba(0,0,0,0)");
      brainPath(c, h, side); ctx.fillStyle = g; ctx.fill();
      ctx.lineWidth = 1.2; ctx.strokeStyle = side < 0 ? "rgba(142,162,255,0.28)" : "rgba(94,234,212,0.26)"; ctx.stroke();
      ctx.lineWidth = 1; ctx.strokeStyle = "rgba(255,255,255,0.05)";
      for (let k = 0; k < 5; k++) {
        const r = rng("gyri" + side + k);
        ctx.beginPath();
        const y0 = c.y - h.ry * 0.7 + k * h.ry * 0.35, x0 = c.x - h.rx * 0.8;
        ctx.moveTo(x0, y0);
        for (let s = 1; s <= 8; s++) ctx.quadraticCurveTo(x0 + s * h.rx * 0.2 - h.rx * 0.1, y0 + (r() - 0.5) * 26, x0 + s * h.rx * 0.2, y0 + Math.sin(now / 2400 + k + s) * 3);
        ctx.stroke();
      }
    });
    ctx.font = "600 10px Geist, system-ui, sans-serif"; ctx.letterSpacing = "1.5px";
    ctx.fillStyle = "rgba(199,210,254,0.55)"; ctx.textAlign = "center";
    ctx.fillText("PEOPLE · TEAMS · AGENTS", h.L.x, h.cy - h.ry * 1.13 - 8);
    ctx.fillStyle = "rgba(94,234,212,0.55)";
    ctx.fillText("KNOWLEDGE · DOCUMENTS · CUSTOMERS", h.Rt.x, h.cy - h.ry * 1.13 - 8);
    ctx.letterSpacing = "0px";
  }

  function lit(n) { return !focus || focus.has(n.id); }

  function draw(now) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (!data) return;
    if (focus && now > focusUntil) focus = null;
    drawBrain(now);
    edges.forEach((e) => {
      const a = byId[e.s], b = byId[e.t]; if (!a || !b) return;
      const on = !focus || (focus.has(a.id) && focus.has(b.id));
      ctx.strokeStyle = `rgba(${C[e.kind] || C.member},${on ? (e.kind === "grant" ? 0.13 : 0.09) : 0.025})`;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y);
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - Math.abs(a.x - b.x) * 0.08;
      ctx.quadraticCurveTo(mx, my, b.x, b.y); ctx.stroke();
    });
    pulses = pulses.filter((p) => now < p.t0 + p.dur || (p.onEnd && !p.done));
    pulses.forEach((p) => {
      const k = (now - p.t0) / p.dur; if (k < 0) return;
      const a = p.a, b = p.b, stop = p.stop || 1, kk = Math.min(k, stop);
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - (p.curve ? Math.abs(a.x - b.x) * 0.08 : 0);
      const pt = (u) => ({ x: (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * mx + u * u * b.x, y: (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * my + u * u * b.y });
      for (let s = 0; s < 6; s++) {
        const u = Math.max(0, kk - s * 0.035), q = pt(u);
        ctx.fillStyle = p.color; ctx.globalAlpha = (1 - s / 6) * (p.strong ? 1 : 0.55);
        ctx.beginPath(); ctx.arc(q.x, q.y, (p.strong ? 2.6 : 1.6) * (1 - s / 9), 0, 7); ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (p.onEnd && k >= stop && !p.done) { p.done = true; p.onEnd(); }
    });
    data.nodes.forEach((n) => {
      const on = lit(n), r = R[n.kind] || 3;
      let col = n.me ? C.me : C[n.kind] || C.person;
      if (n.kind === "doc" && n.state) col = n.state === "locked" ? C.locked : C.open;
      ctx.globalAlpha = on ? 1 : 0.18;
      ctx.shadowBlur = n.me ? 18 : (n.kind === "doc" && n.state !== "locked") || n.kind === "space" || n.kind === "team" ? 9 : 0;
      ctx.shadowColor = col; ctx.fillStyle = col;
      ctx.beginPath();
      if (n.kind === "agent") ctx.roundRect(n.x - r, n.y - r, r * 2, r * 2, 2); else ctx.arc(n.x, n.y, n.me ? 5.5 : r, 0, 7);
      ctx.fill(); ctx.shadowBlur = 0;
      if (n.kind === "doc" && n.state === "partial") { ctx.strokeStyle = C.locked; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(n.x, n.y, r + 2.6, 0, Math.PI); ctx.stroke(); }
      if (n.kind === "doc" && n.state === "locked") { ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(n.x, n.y - 3.4, 1.8, Math.PI, 0); ctx.stroke(); }
      if (n.me) {
        const k = (now % 2200) / 2200;
        ctx.strokeStyle = `rgba(255,181,71,${0.6 * (1 - k)})`; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(n.x, n.y, 6 + k * 16, 0, 7); ctx.stroke();
      }
      ctx.globalAlpha = 1;
    });
    rings = rings.filter((g) => now < g.t0 + g.dur);
    rings.forEach((g) => {
      const k = (now - g.t0) / g.dur; if (k < 0) return;
      ctx.strokeStyle = g.color; ctx.globalAlpha = 1 - k; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(g.n.x, g.n.y, 4 + k * 20, 0, 7); ctx.stroke(); ctx.globalAlpha = 1;
    });
    ctx.font = "500 11px Geist, system-ui, sans-serif"; ctx.textAlign = "center";
    data.nodes.forEach((n) => {
      if (!(n.me || n.kind === "team" || n.kind === "space" || n.kind === "customer" || n === hover)) return;
      ctx.globalAlpha = lit(n) ? (n.me || n === hover ? 1 : 0.62) : 0.15;
      ctx.fillStyle = n.me ? C.me : "#DCE3F2";
      const label = n.me ? `You · ${n.label}` : n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label;
      ctx.fillText(label, n.x, n.y - (R[n.kind] || 4) - 7);
      ctx.globalAlpha = 1;
    });
  }

  function spawnAmbient(now) {
    if (reduce || !edges.length || now - lastSpawn < 140) return;
    lastSpawn = now;
    const e = edges[Math.floor(Math.random() * edges.length)], a = byId[e.s], b = byId[e.t];
    if (!a || !b) return;
    const fwd = Math.random() < 0.5;
    pulses.push({ a: fwd ? a : b, b: fwd ? b : a, t0: now, dur: 1400 + Math.random() * 1200, color: `rgb(${C[e.kind] || C.member})`, curve: true });
  }

  function loop(now) {
    spawnAmbient(now);
    draw(now);
    raf = requestAnimationFrame(loop);
  }

  function resize() {
    const r = cv.parentElement.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = Math.max(320, r.width); H = Math.max(260, r.height);
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
    if (data) layout();
  }

  function docOf(id) { return id && id.includes("__") ? id.split("__")[0] : id; }

  window.Brain = {
    mount(el) {
      cv = document.createElement("canvas"); el.appendChild(cv); ctx = cv.getContext("2d");
      tip = document.createElement("div"); tip.className = "brain-tip"; tip.hidden = true; el.appendChild(tip);
      new ResizeObserver(resize).observe(el); resize();
      cv.addEventListener("mousemove", (ev) => {
        if (!data) return;
        const b = cv.getBoundingClientRect(), x = ev.clientX - b.left, y = ev.clientY - b.top;
        let best = null, bd = 14;
        data.nodes.forEach((n) => { const d = Math.hypot(n.x - x, n.y - y); if (d < bd) { bd = d; best = n; } });
        hover = best;
        if (best) {
          const kind = { person: "Person", team: "Team", group: "Group", agent: "AI agent", space: "Space", doc: "Document", customer: "Customer" }[best.kind];
          const state = best.state === "locked" ? " · hidden from you" : best.state === "partial" ? " · partly hidden" : best.state === "open" ? " · you can read it" : "";
          tip.textContent = `${kind}: ${best.label}${state}`;
          tip.style.left = Math.min(W - 220, x + 12) + "px"; tip.style.top = y + 12 + "px"; tip.hidden = false;
        } else tip.hidden = true;
      });
      cv.addEventListener("mouseleave", () => { hover = null; tip.hidden = true; });
      if (!raf) raf = requestAnimationFrame(loop);
    },
    setData(d, key) {
      const keepPos = data && key === layoutKey ? Object.fromEntries(data.nodes.map((n) => [n.id, [n.x, n.y]])) : null;
      data = d; byId = {}; d.nodes.forEach((n) => { byId[n.id] = n; }); edges = d.edges; pulses = []; rings = [];
      if (keepPos) d.nodes.forEach((n) => { const p = keepPos[n.id]; if (p) { n.x = p[0]; n.y = p[1]; } });
      else layout();
      layoutKey = key;
      const me = d.nodes.find((n) => n.me);
      if (me) rings.push({ n: me, t0: performance.now(), dur: 1200, color: C.me });
    },
    think(answer) {
      if (!data) return Promise.resolve();
      const now = performance.now(), hop = reduce ? 0 : 230, me = data.nodes.find((n) => n.me);
      const involved = new Set(me ? [me.id] : []);
      let end = now;
      answer.facts.forEach((f, fi) => {
        const ids = (f.why ? f.why.ids.slice() : []).map(docOf);
        if (f.why && ids[ids.length - 1] !== f.source.doc) ids.push(f.source.doc);
        if (!f.why && me) ids.splice(0, ids.length, me.id, f.source.doc);
        const path = ids.map((i) => byId[i]).filter(Boolean);
        path.forEach((n) => involved.add(n.id));
        path.slice(1).forEach((n, i) => {
          const t0 = now + fi * 140 + i * hop, last = i === path.length - 2;
          pulses.push({ a: path[i], b: n, t0, dur: hop || 1, color: f.leak ? C.bad : i === 0 ? C.me : C.open, strong: true, curve: true,
            onEnd: last ? () => rings.push({ n, t0: performance.now(), dur: 900, color: f.leak ? C.bad : C.open }) : null });
          end = Math.max(end, t0 + hop);
        });
      });
      answer.redacted.forEach((r, ri) => {
        const d = byId[docOf(r.id)]; if (!d || !me) return;
        involved.add(d.id);
        const t0 = now + 220 + ri * 160;
        pulses.push({ a: me, b: d, t0, dur: 900, stop: 0.72, color: C.bad, strong: true,
          onEnd: () => rings.push({ n: d, t0: performance.now(), dur: 800, color: C.bad }) });
        end = Math.max(end, t0 + 700);
      });
      focus = involved; focusUntil = end + 2600;
      return new Promise((res) => setTimeout(res, Math.max(0, Math.min(1600, end - now))));
    },
  };
})();
