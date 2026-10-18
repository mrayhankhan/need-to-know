from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import access, agents, brain, config, db, eval as bench, llm, memory, scan, seed

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

app = FastAPI(title="Need-to-Know", version="1.0.0")

PERSONAS = {
    "northwind": ["p_priya", "p_meera", "p_arjun", "p_ravi", "p_kabir", "p_neha", "p_contractor_00", "a_support", "a_finance"],
    "bluefin": ["p_ines", "p_dev", "p_hana"],
}
SAMPLES = {
    "northwind": ["Why did Acme Corp's invoice go up in October?",
                  "Who owns the Acme Corp account?",
                  "What does Acme Corp pay us and when do they renew?",
                  "Who decided that loyalty discounts end after 12 months?",
                  "What are the engineering salary bands?",
                  "How much runway do we have?",
                  "Why don't we retry payments on the client side?"],
    "bluefin": ["What are the clinic hours?", "What is the insurer rate for a standard visit?",
                "Why did Acme Corp's invoice go up?"],
}

_eval_cache: dict = {}
_eval_lock = threading.Lock()


@app.on_event("startup")
def _startup() -> None:
    seed.ensure_loaded()


def _tenant(t: str) -> str:
    if t not in config.TENANTS:
        raise HTTPException(404, f"unknown tenant {t}")
    return t


def _mode(m: str) -> str:
    if m not in access.MODES:
        raise HTTPException(400, f"mode must be one of {access.MODES}")
    return m


class AskBody(BaseModel):
    tenant: str = "northwind"
    asker: str
    question: str
    mode: str = "graph"


class CompareBody(BaseModel):
    tenant: str = "northwind"
    question: str
    askers: list[str]
    mode: str = "graph"


class CaseBody(BaseModel):
    tenant: str = "northwind"
    mode: str = "graph"
    approver: str = "p_sam"


class FixBody(BaseModel):
    tenant: str = "northwind"
    fix: dict
    doc: str | None = None
    approver: str = "p_neha"
    reason: str = "Approved after testing on a copy of the graph"


class TenantBody(BaseModel):
    tenant: str = "northwind"


@app.get("/api/health")
def health():
    return {"ok": db.ping(), "llm": llm.available(), "tenants": list(config.TENANTS)}


@app.get("/api/tenants")
def tenants():
    names = set(db.graph_names())
    return [{"id": t, "name": n, "loaded": t in names, "samples": SAMPLES[t]} for t, n in config.TENANTS.items()]


@app.get("/api/people")
def people(tenant: str = "northwind"):
    t = _tenant(tenant)
    rows_ = db.rows(db.graph(t),
                    "MATCH (p:Principal) WHERE p.id IN $ids "
                    "OPTIONAL MATCH (p)-[:MEMBER_OF]->(g:Group) "
                    "RETURN p.id, p.name, [l IN labels(p) WHERE l <> 'Principal'][0], coalesce(p.title, p.role), collect(g.name)",
                    {"ids": PERSONAS[t]}, ro=True)
    by_id = {i: {"id": i, "name": n, "kind": k, "title": ti, "groups": gs} for i, n, k, ti, gs in rows_}
    total = db.rows(db.graph(t), "MATCH (p:Person) RETURN count(p)", ro=True)[0][0]
    return {"personas": [by_id[i] for i in PERSONAS[t] if i in by_id], "people_total": total}


@app.post("/api/ask")
def ask(b: AskBody):
    return brain.ask(_tenant(b.tenant), b.asker, b.question, _mode(b.mode))


@app.post("/api/compare")
def compare(b: CompareBody):
    t = _tenant(b.tenant)
    return [brain.ask(t, a, b.question, _mode(b.mode)) for a in b.askers[:3]]


@app.get("/api/overview")
def overview(tenant: str = "northwind", viewer: str = ""):
    """What the brain knows, at a glance, from the viewer's point of view."""
    t = _tenant(tenant)
    g = db.graph(t)
    counts = {k: v for k, v in db.rows(g, "MATCH (n) RETURN [l IN labels(n) WHERE l <> 'Principal'][0], count(n)", ro=True)}
    teams = db.rows(g, "MATCH (gr:Group {kind:'team'}) OPTIONAL MATCH (p:Person)-[:MEMBER_OF]->(gr) "
                       "RETURN gr.name, count(p) AS n ORDER BY n DESC", ro=True)
    customers = db.rows(g, "MATCH (c:Customer) OPTIONAL MATCH (c)<-[:MENTIONS]-(:Section)-[:PART_OF]->(d:Doc {kind:'doc'})<-[:OWNS]-(o:Person) "
                           "RETURN c.name, collect(DISTINCT o.name)", ro=True)
    readable = access.readable_set(t, viewer) if viewer else set()
    cat = access.catalog(t)
    decisions, hidden = [], 0
    for summary, who, date, doc_id, kind in db.rows(
            g, "MATCH (p:Person)-[:MADE]->(x:Decision) OPTIONAL MATCH (d:Doc)-[:DOCUMENTS]->(x) "
               "RETURN x.summary, p.name, x.date, d.id, x.kind ORDER BY x.date DESC", ro=True):
        visible = kind == "access-change" or any(cat.sections[s]["doc"] == doc_id for s in readable)
        if visible:
            decisions.append({"summary": summary, "by": who, "date": (date or "")[:10]})
        else:
            hidden += 1
    bots = db.rows(g, "MATCH (a:Agent) OPTIONAL MATCH (a)-[:MEMBER_OF]->(gr:Group) RETURN a.name, a.role, collect(gr.name)", ro=True)
    docs_total = len(cat.docs)
    docs_visible = len({cat.sections[s]["doc"] for s in readable})
    return {"company": config.TENANTS[t], "counts": counts,
            "teams": [{"name": n, "people": c} for n, c in teams],
            "customers": [{"name": n, "owner": (o or [None])[0]} for n, o in customers],
            "decisions": decisions, "decisions_hidden": hidden,
            "agents": [{"name": n, "role": r, "groups": gs} for n, r, gs in bots],
            "documents": {"total": docs_total, "visible": docs_visible}}


@app.get("/api/brain")
def brain_map(tenant: str = "northwind", viewer: str = ""):
    """A compact picture of the company graph for the animated brain view, coloured for one viewer."""
    t = _tenant(tenant)
    g = db.graph(t)
    cat = access.catalog(t)
    nodes, keep = [], set()

    def add(nid, label, kind, **extra):
        if nid not in keep:
            keep.add(nid)
            nodes.append({"id": nid, "label": label, "kind": kind, **extra})

    for gid, name, kind, team in db.rows(g, "MATCH (x:Group) RETURN x.id, x.name, x.kind, x.team", ro=True):
        add(gid, name, "team" if kind == "team" else "group", team=team or "", sub=kind)
    per_team: dict[str, int] = {}
    for pid, name, team, ext in db.rows(g, "MATCH (p:Person) RETURN p.id, p.name, p.team, p.external ORDER BY p.id", ro=True):
        if pid in PERSONAS[t] or per_team.get(team, 0) < (2 if ext else 4):
            per_team[team] = per_team.get(team, 0) + (0 if pid in PERSONAS[t] else 1)
            add(pid, name, "person", team=team or "", me=pid == viewer)
    for aid, name in db.rows(g, "MATCH (a:Agent) RETURN a.id, a.name", ro=True):
        add(aid, name, "agent", me=aid == viewer)
    for sid, name in db.rows(g, "MATCH (s:Space) RETURN s.id, s.name", ro=True):
        add(sid, name, "space")
    readable = access.readable_set(t, viewer) if viewer else set()
    for did, d in cat.docs.items():
        secs = [s for s, v in cat.sections.items() if v["doc"] == did]
        seen = sum(1 for s in secs if s in readable)
        state = "open" if seen == len(secs) else ("partial" if seen else "locked")
        add(did, d["title"], "doc", space=d["space"], state=state if viewer else "")
    for cid, name in db.rows(g, "MATCH (c:Customer) RETURN c.id, c.name", ro=True):
        add(cid, name, "customer")

    edges = set()
    for a, b in db.rows(g, "MATCH (a:Principal)-[:MEMBER_OF]->(b:Group) RETURN a.id, b.id", ro=True):
        if a in keep and b in keep:
            edges.add((a, b, "member"))
    for a, tgt in db.rows(g, "MATCH (a:Principal)-[:CAN_READ]->(x) WHERE x:Space OR x:Doc OR x:Section RETURN a.id, x.id", ro=True):
        tgt = cat.sections[tgt]["doc"] if tgt in cat.sections else tgt
        if a in keep and tgt in keep:
            edges.add((a, tgt, "grant"))
    for did, d in cat.docs.items():
        edges.add((did, d["space"], "in"))
    for did, cid in db.rows(g, "MATCH (s:Section)-[:MENTIONS]->(c:Customer) RETURN DISTINCT s.doc, c.id", ro=True):
        if did in keep and cid in keep:
            edges.add((did, cid, "about"))
    return {"nodes": nodes, "edges": [{"s": a, "t": b, "kind": k} for a, b, k in sorted(edges)]}


@app.get("/api/memory")
def my_memory(asker: str, tenant: str = "northwind"):
    return memory.recall(_tenant(tenant), asker, limit=20)


@app.get("/api/memory/peek")
def peek(asker: str, owner: str, tenant: str = "northwind"):
    return memory.peek(_tenant(tenant), asker, owner)


@app.post("/api/case/run")
def case_run(b: CaseBody):
    return agents.run(_tenant(b.tenant), _mode(b.mode))


@app.get("/api/case")
def case_view(viewer: str = "a_support", mode: str = "graph", tenant: str = "northwind"):
    return agents.view(_tenant(tenant), viewer, _mode(mode))


@app.post("/api/case/approve")
def case_approve(b: CaseBody):
    return agents.approve(_tenant(b.tenant), b.approver)


@app.get("/api/scan")
def scan_(tenant: str = "northwind"):
    return scan.scan(_tenant(tenant))


@app.post("/api/scan/test")
def scan_test(b: FixBody):
    return scan.test_fix(_tenant(b.tenant), b.fix, b.doc)


@app.post("/api/scan/apply")
def scan_apply(b: FixBody):
    t = _tenant(b.tenant)
    test = scan.test_fix(t, b.fix, b.doc)
    if not test["passed"]:
        raise HTTPException(409, {"message": "The fix failed its test on the copy, so it was not applied.", "test": test})
    out = scan.apply_fix(t, b.fix, b.approver, b.reason)
    access.reset_cache(t)
    return {"test": test, **out}


@app.get("/api/audit")
def audit(tenant: str = "northwind"):
    return scan.audit(_tenant(tenant))


@app.get("/api/eval")
def eval_(refresh: bool = False):
    with _eval_lock:
        if refresh or not _eval_cache:
            cached = ROOT / "results" / "eval.json"
            if cached.exists() and not refresh:
                _eval_cache.update(json.loads(cached.read_text(encoding="utf-8")))
            else:
                _eval_cache.clear()
                _eval_cache.update(bench.run("northwind"))
        return _eval_cache


@app.get("/api/stats")
def stats(tenant: str = "northwind"):
    g = db.graph(_tenant(tenant))
    labels = db.rows(g, "MATCH (n) RETURN [l IN labels(n) WHERE l <> 'Principal'][0] AS l, count(n) ORDER BY l", ro=True)
    rels = db.rows(g, "MATCH ()-[r]->() RETURN type(r) AS t, count(r) ORDER BY t", ro=True)
    return {"tenant": tenant, "graphs": db.graph_names(), "nodes": dict(labels), "edges": dict(rels)}


@app.post("/api/reset")
def reset(b: TenantBody):
    t = _tenant(b.tenant)
    seed.load(seed.build_spec(t))
    access.reset_cache(t)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
