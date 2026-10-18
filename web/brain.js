/* The brain view: the real company graph drawn inside an anatomical brain (side view, facing left).
   Frontal lobe: leadership and decisions. Parietal lobe: teams and people. Occipital lobe: the
   customer-facing teams. Temporal lobe (memory): spaces, documents and customers. Cerebellum: AI agents.
   Brain stem: FalkorDB. Asking a question sends signals along the exact membership chain FalkorDB used;
   blocked documents get a red signal that stops short and flashes. */
(function () {
  "use strict";
  const C = {
    person: "#F6DCE4", team: "#F59AB2", group: "#D7A6B8", agent: "#C9B8FF", space: "#94E6C4", doc: "#94E6C4",
    customer: "#FFC9A8", me: "#FFD27A", open: "#94E6C4", locked: "#5F4F58", bad: "#FF5C6C",
    member: "245,154,178", grant: "148,230,196", in: "148,230,196", about: "255,201,168",
  };
  const R = { team: 4.8, group: 3.6, person: 2.3, agent: 4.2, space: 4.8, doc: 3, customer: 4.4 };
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let cv, ctx, W = 0, H = 0, dpr = 1, data = null, byId = {}, edges = [], pulses = [], rings = [], focus = null, focusUntil = 0;
  let hover = null, tip, raf, lastSpawn = 0, layoutKey = "", S = 1, OX = 0, OY = 0, texture = null;

  /* ---- anatomy, in a 100 x 74 box, facing left ---- */
  const CEREBRUM = "M9 40 C3 32 4 18 14 11 C22 4 38 1 52 2 C68 3 82 7 90 16 C97 24 98 36 93 43 C90 47 85 49 79 49 C73 49 68 50 64 52 C58 56 50 58 42 57 C33 56 25 55 19 51 C16 49 17 46 21 44 C16 45 11 44 9 40 Z";
  const CEREBELLUM = "M63 53 C66 50 80 49 88 52 C94 55 92 63 84 65 C76 67 67 64 63 58 C62 56 62 54 63 53 Z";
  const STEM = "M58 56 C59 61 60 67 59.5 74 L53 74 C54 68 54 62 51 57 Z";
  const SULCI = [
    "M21 44 C32 40 44 38 56 36 C60 35.5 64 34 67 31",
    "M50 3 C49 10 47 16 46 22 C45 27 44 32 43 36",
    "M44 3.5 C43 10 41 16 40 22 C39 27 38 31 37 36",
    "M57 3 C56 10 54 16 53 22 C52 27 51 31 50 35",
    "M78 7 C77 12 76 17 74 21",
    "M26 49 C36 46 48 45 60 43",
    "M14 22 C22 18 30 16 38 15",
    "M12 31 C20 28 30 27 39 27",
    "M55 18 C62 16 70 17 80 22",
    "M60 28 C67 27 74 29 82 33",
    "M30 52 C40 51 50 50 58 49",
  ];
  const LOBES = {
    frontal: { c: [23, 24], r: [10, 11], label: "LEADERSHIP & DECISIONS", at: [22, 9] },
    parietal: { c: [61, 17], r: [16, 8], label: "TEAMS & PEOPLE", at: [62, 6.5] },
    occipital: { c: [84, 31], r: [7.5, 10], label: "CUSTOMER-FACING", at: [86, 20] },
    temporal: { c: [41, 48.5], r: [17, 4.6], label: "COMPANY MEMORY", at: [40, 55] },
    cerebellum: { c: [77, 58], r: [8.5, 4], label: "AI AGENTS", at: [78, 68.5] },
  };
  const TEAM_LOBE = { finance: "frontal", legal: "frontal", hr: "frontal", engineering: "parietal", product: "parietal",
    operations: "parietal", marketing: "parietal", sales: "occipital", support: "occipital" };
  const P = { cerebrum: new Path2D(CEREBRUM), cerebellum: new Path2D(CEREBELLUM), stem: new Path2D(STEM) };
  const tester = document.createElement("canvas").getContext("2d");

  function rng(seed) { let h = 2166136261; for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return () => { h ^= h << 13; h ^= h >>> 17; h ^= h << 5; return ((h >>> 0) % 10000) / 10000; }; }
  const toPx = (bx, by) => [OX + bx * S, OY + by * S];
  const toBox = (px, py) => [(px - OX) / S, (py - OY) / S];

  function fit() {
    S = Math.min(W / 104, (H - 56) / 76);
    OX = (W - 100 * S) / 2; OY = Math.max(10, (H - 56 - 74 * S) / 2 + 8);
  }

  function inside(path, bx, by) { return tester.isPointInPath(path, bx, by); }

  function place(n, lobe, spread, seedExtra = "") {
    const L = LOBES[lobe], r = rng(n.id + seedExtra);
    for (let k = 0; k < 30; k++) {
      const a = r() * Math.PI * 2, d = Math.sqrt(r()) * spread;
      const bx = L.c[0] + Math.cos(a) * L.r[0] * d, by = L.c[1] + Math.sin(a) * L.r[1] * d;
      const path = lobe === "cerebellum" ? P.cerebellum : P.cerebrum;
      if (inside(path, bx, by)) { n.bx = bx; n.by = by; return; }
    }
    n.bx = L.c[0]; n.by = L.c[1];
  }

  function layout() {
    fit();
    const nodes = data.nodes, parent = {};
    edges.forEach((e) => { if (e.kind === "member") (parent[e.s] ||= []).push(e.t); });
    const teams = nodes.filter((n) => n.kind === "team");
    const byLobe = {};
    teams.forEach((t) => (byLobe[TEAM_LOBE[t.team] || "parietal"] ||= []).push(t));
    Object.entries(byLobe).forEach(([lobe, list]) => list.forEach((t, i) => {
      const L = LOBES[lobe], a = -Math.PI / 2 + (i / list.length) * Math.PI * 2 + 0.4;
      t.bx = L.c[0] + Math.cos(a) * L.r[0] * 0.55; t.by = L.c[1] + Math.sin(a) * L.r[1] * 0.55;
    }));
    const fixed = { g_all_staff: [50, 24], g_drive_migration_2023: [38, 37.5], g_leadership: [20, 15], g_people_managers: [30, 30],
      g_contractors: [90, 38], g_project_phoenix: [70, 25], g_support_agents: [78, 45], g_finance_agents: [72, 46] };
    nodes.filter((n) => n.kind === "group").forEach((n) => {
      if (fixed[n.id]) { [n.bx, n.by] = fixed[n.id]; return; }
      const up = (parent[n.id] || []).map((p) => byId[p]).find((p) => p && p.kind === "team");
      if (up) { n.bx = up.bx + (rng(n.id)() - 0.5) * 6; n.by = up.by + 3; } else place(n, "frontal", 0.8);
    });
    nodes.filter((n) => n.kind === "person").forEach((n) => {
      const t = teams.find((x) => x.team === n.team);
      if (t) { const r = rng(n.id), a = r() * 6.283, d = 1.8 + r() * 4.2; n.bx = t.bx + Math.cos(a) * d * 1.3; n.by = t.by + Math.sin(a) * d; }
      else { const g = byId.g_contractors; const r = rng(n.id); n.bx = g.bx - 3 + r() * 5; n.by = g.by - 4 + r() * 6; }
      if (!inside(P.cerebrum, n.bx, n.by)) place(n, TEAM_LOBE[n.team] || "occipital", 0.9);
    });
    nodes.filter((n) => n.kind === "agent").forEach((n, i, all) => { n.bx = 71 + (i / Math.max(1, all.length - 1)) * 13; n.by = 57.5 + (i % 2 ? 1.6 : -1.2); });
    const spaces = nodes.filter((n) => n.kind === "space");
    spaces.forEach((n, i) => { n.bx = 26 + (i / Math.max(1, spaces.length - 1)) * 34; n.by = 47 + (i % 2 ? 3.2 : -1); });
    nodes.filter((n) => n.kind === "doc").forEach((n) => {
      const s = byId[n.space] || LOBES.temporal, r = rng(n.id), a = r() * 6.283, d = 1.6 + r() * 2.6;
      n.bx = (s.bx ?? 41) + Math.cos(a) * d * 1.4; n.by = (s.by ?? 48) + Math.sin(a) * d * 0.9;
      if (!inside(P.cerebrum, n.bx, n.by)) place(n, "temporal", 0.9);
    });
    nodes.filter((n) => n.kind === "customer").forEach((n, i) => { n.bx = 19 + i * 3.6; n.by = 49 - (i % 2) * 1.4; });
    const min = 1.25;
    for (let it = 0; it < 80; it++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], dx = b.bx - a.bx, dy = b.by - a.by, d = Math.hypot(dx, dy) || 0.01;
        if (d < min) { const k = (min - d) / d / 2; a.bx -= dx * k; a.by -= dy * k; b.bx += dx * k; b.by += dy * k; }
      }
    }
    project();
  }
  function project() { if (!data) return; fit(); data.nodes.forEach((n) => { [n.x, n.y] = toPx(n.bx, n.by); }); texture = null; }

  /* ---- static anatomy, drawn once per size into an offscreen canvas ---- */
  function buildTexture() {
    const c = document.createElement("canvas"); c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext("2d");
    g.setTransform(dpr * S, 0, 0, dpr * S, dpr * OX, dpr * OY);
    const tissue = (path, a, b) => {
      const gr = g.createRadialGradient(45, 26, 4, 50, 34, 60);
      gr.addColorStop(0, `rgba(245,154,178,${a})`); gr.addColorStop(1, `rgba(150,70,100,${b})`);
      g.fillStyle = gr; g.fill(path);
    };
    tissue(P.stem, 0.16, 0.08);
    tissue(P.cerebellum, 0.2, 0.08);
    tissue(P.cerebrum, 0.17, 0.05);
    g.save(); g.clip(P.cerebrum);
    const r = rng("gyri");
    g.lineCap = "round";
    for (let k = 0; k < 70; k++) {
      let x = 6 + r() * 90, y = 2 + r() * 56;
      g.beginPath(); g.moveTo(x, y);
      for (let s = 0; s < 6; s++) { const nx = x + (r() - 0.5) * 9, ny = y + (r() - 0.5) * 7; g.quadraticCurveTo((x + nx) / 2 + (r() - 0.5) * 4, (y + ny) / 2 + (r() - 0.5) * 4, nx, ny); x = nx; y = ny; }
      g.strokeStyle = "rgba(255,214,226,0.07)"; g.lineWidth = 0.9 + r() * 0.8; g.stroke();
    }
    g.restore();
    g.save(); g.clip(P.cerebellum);
    for (let k = 0; k < 9; k++) { g.beginPath(); g.moveTo(62, 51.5 + k * 1.6); g.bezierCurveTo(70, 49.5 + k * 1.9, 82, 50 + k * 1.9, 94, 53 + k * 1.4); g.strokeStyle = "rgba(255,214,226,0.13)"; g.lineWidth = 0.35; g.stroke(); }
    g.restore();
    g.lineCap = "round";
    SULCI.forEach((d, i) => { g.strokeStyle = `rgba(245,154,178,${i < 2 ? 0.3 : 0.15})`; g.lineWidth = i < 2 ? 0.38 : 0.26; g.stroke(new Path2D(d)); });
    g.shadowColor = "rgba(245,154,178,0.6)"; g.shadowBlur = 14;
    g.strokeStyle = "rgba(245,154,178,0.7)"; g.lineWidth = 0.45;
    g.stroke(P.stem); g.stroke(P.cerebellum); g.stroke(P.cerebrum);
    g.shadowBlur = 0;
    // labels in real pixels (tiny scaled fonts get broken letter spacing)
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const fs = Math.max(9, Math.min(12, S * 1.35));
    g.font = `600 ${fs}px Geist, system-ui, sans-serif`; g.textAlign = "center"; g.fillStyle = "rgba(255,226,234,0.6)";
    if ("letterSpacing" in g) g.letterSpacing = "1.5px";
    Object.values(LOBES).forEach((L) => { const [x, y] = toPx(L.at[0], L.at[1]); g.fillText(L.label, x, y); });
    g.textAlign = "right"; const [sx, sy] = toPx(51.5, 71); g.fillText("FALKORDB", sx, sy);
    if ("letterSpacing" in g) g.letterSpacing = "0px";
    texture = c;
  }

  function lit(n) { return !focus || focus.has(n.id); }

  function draw(now) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (!data) return;
    if (!texture) buildTexture();
    ctx.drawImage(texture, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (focus && now > focusUntil) focus = null;
    const breathe = reduce ? 0 : Math.sin(now / 1800) * 0.03;
    edges.forEach((e) => {
      const a = byId[e.s], b = byId[e.t]; if (!a || !b) return;
      const on = !focus || (focus.has(a.id) && focus.has(b.id));
      ctx.strokeStyle = `rgba(${C[e.kind] || C.member},${on ? (e.kind === "grant" ? 0.16 + breathe : 0.1) : 0.025})`;
      ctx.lineWidth = 0.8;
      ctx.beginPath(); ctx.moveTo(a.x, a.y);
      ctx.quadraticCurveTo((a.x + b.x) / 2, (a.y + b.y) / 2 - Math.abs(a.x - b.x) * 0.1, b.x, b.y); ctx.stroke();
    });
    pulses = pulses.filter((p) => now < p.t0 + p.dur || (p.onEnd && !p.done));
    pulses.forEach((p) => {
      const k = (now - p.t0) / p.dur; if (k < 0) return;
      const a = p.a, b = p.b, stop = p.stop || 1, kk = Math.min(k, stop);
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - (p.curve ? Math.abs(a.x - b.x) * 0.1 : 0);
      const pt = (u) => ({ x: (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * mx + u * u * b.x, y: (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * my + u * u * b.y });
      for (let s = 0; s < 7; s++) {
        const u = Math.max(0, kk - s * 0.03), q = pt(u);
        ctx.fillStyle = p.color; ctx.globalAlpha = (1 - s / 7) * (p.strong ? 1 : 0.5);
        ctx.beginPath(); ctx.arc(q.x, q.y, (p.strong ? 2.6 : 1.5) * (1 - s / 10), 0, 7); ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (p.onEnd && k >= stop && !p.done) { p.done = true; p.onEnd(); }
    });
    data.nodes.forEach((n) => {
      const on = lit(n), r = R[n.kind] || 3;
      let col = n.me ? C.me : C[n.kind] || C.person;
      if (n.kind === "doc" && n.state) col = n.state === "locked" ? C.locked : C.open;
      ctx.globalAlpha = on ? 1 : 0.2;
      ctx.shadowBlur = n.me ? 20 : (n.kind === "doc" && n.state !== "locked") || n.kind === "space" || n.kind === "team" || n.kind === "agent" ? 10 : 0;
      ctx.shadowColor = col; ctx.fillStyle = col;
      ctx.beginPath();
      if (n.kind === "agent") ctx.roundRect(n.x - r, n.y - r, r * 2, r * 2, 2.5); else ctx.arc(n.x, n.y, n.me ? 5.5 : r, 0, 7);
      ctx.fill(); ctx.shadowBlur = 0;
      if (n.kind === "doc" && n.state === "partial") { ctx.strokeStyle = C.locked; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(n.x, n.y, r + 2.4, 0, Math.PI); ctx.stroke(); }
      if (n.kind === "doc" && n.state === "locked") { ctx.strokeStyle = "rgba(255,226,234,0.45)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(n.x, n.y - 3.2, 1.7, Math.PI, 0); ctx.stroke(); }
      if (n.me) {
        const k = (now % 2200) / 2200;
        ctx.strokeStyle = `rgba(255,210,122,${0.65 * (1 - k)})`; ctx.lineWidth = 1.5;
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
      if (!(n.me || n === hover || (n.kind === "team" && S > 7))) return;
      ctx.globalAlpha = lit(n) ? (n.me || n === hover ? 1 : 0.55) : 0.15;
      ctx.fillStyle = n.me ? C.me : "#FBE9EF";
      const label = n.me ? `You · ${n.label}` : n.label.length > 24 ? n.label.slice(0, 23) + "…" : n.label;
      ctx.fillText(label, n.x, n.me ? n.y + 20 : n.y - (R[n.kind] || 4) - 6);
      ctx.globalAlpha = 1;
    });
  }

  function spawnAmbient(now) {
    if (reduce || !edges.length || now - lastSpawn < 130) return;
    lastSpawn = now;
    const e = edges[Math.floor(Math.random() * edges.length)], a = byId[e.s], b = byId[e.t];
    if (!a || !b) return;
    const fwd = Math.random() < 0.5;
    pulses.push({ a: fwd ? a : b, b: fwd ? b : a, t0: now, dur: 1500 + Math.random() * 1300, color: `rgb(${C[e.kind] || C.member})`, curve: true });
  }

  function loop(now) { spawnAmbient(now); draw(now); raf = requestAnimationFrame(loop); }

  function resize() {
    const r = cv.parentElement.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = Math.max(320, r.width); H = Math.max(260, r.height);
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
    project();
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
        let best = null, bd = 12;
        data.nodes.forEach((n) => { const d = Math.hypot(n.x - x, n.y - y); if (d < bd) { bd = d; best = n; } });
        hover = best;
        if (best) {
          const kind = { person: "Person", team: "Team", group: "Group", agent: "AI agent", space: "Space", doc: "Document", customer: "Customer" }[best.kind];
          const state = best.state === "locked" ? " · hidden from you" : best.state === "partial" ? " · partly hidden" : best.state === "open" ? " · you can read it" : "";
          tip.textContent = `${kind}: ${best.label}${state}`;
          tip.style.left = Math.min(W - 230, x + 12) + "px"; tip.style.top = y + 12 + "px"; tip.hidden = false;
        } else {
          tip.hidden = true;
          const [bx, by] = toBox(x, y);
          const lobe = inside(P.cerebellum, bx, by) ? "Cerebellum: AI agents coordinate the work" : inside(P.stem, bx, by) ? "Brain stem: FalkorDB, the graph everything runs on" : null;
          if (lobe) { tip.textContent = lobe; tip.style.left = Math.min(W - 280, x + 12) + "px"; tip.style.top = y + 12 + "px"; tip.hidden = false; }
        }
      });
      cv.addEventListener("mouseleave", () => { hover = null; tip.hidden = true; });
      if (!raf) raf = requestAnimationFrame(loop);
    },
    setData(d, key) {
      const keep = data && key === layoutKey ? Object.fromEntries(data.nodes.map((n) => [n.id, [n.bx, n.by]])) : null;
      data = d; byId = {}; d.nodes.forEach((n) => { byId[n.id] = n; }); edges = d.edges; pulses = []; rings = [];
      if (keep && d.nodes.every((n) => keep[n.id])) { d.nodes.forEach((n) => { [n.bx, n.by] = keep[n.id]; }); project(); }
      else layout();
      layoutKey = key;
      const me = d.nodes.find((n) => n.me);
      if (me) rings.push({ n: me, t0: performance.now(), dur: 1200, color: C.me });
    },
    think(answer) {
      if (!data) return Promise.resolve();
      const now = performance.now(), hop = reduce ? 0 : 240, me = data.nodes.find((n) => n.me);
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
