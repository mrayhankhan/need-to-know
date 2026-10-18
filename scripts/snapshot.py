"""Build the static demo: run every demo interaction against the real FalkorDB backend and save
the responses next to a copy of the web app. GitHub Pages serves the result, so anyone can click
through the demo without hosting a database. Everything in it was computed by FalkorDB in CI.

Usage:  python scripts/snapshot.py site/
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from ntk import access, seed  # noqa: E402
from ntk.api import PERSONAS, SAMPLES, app  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
MODES = ["graph", "flat", "off"]


def key(*parts):
    return "|".join(parts)


def reset_all():
    seed.load_all()
    access.reset_cache()


def main():
    reset_all()
    c = TestClient(app)
    snap = {"ask": {}, "memory": {}, "peek": {}, "case": {}, "approve": {}, "scan": {}, "scan_test": {},
            "scan_apply": {}, "people": {}, "stats": {}, "overview": {}, "brain": {}}
    snap["health"] = {**c.get("/api/health").json(), "llm": False}
    snap["tenants"] = c.get("/api/tenants").json()
    for t in PERSONAS:
        snap["people"][t] = c.get(f"/api/people?tenant={t}").json()

    for t, people in PERSONAS.items():
        snap["overview"][t] = {who: c.get(f"/api/overview?tenant={t}&viewer={who}").json() for who in people}
        snap["brain"][t] = {who: c.get(f"/api/brain?tenant={t}&viewer={who}").json() for who in people}

    # Every persona x sample question x access mode
    for t, people in PERSONAS.items():
        for q in SAMPLES[t]:
            for who in people:
                for m in MODES:
                    r = c.post("/api/ask", json={"tenant": t, "asker": who, "question": q, "mode": m}).json()
                    snap["ask"][key(t, who, q, m)] = r

    # Agents sharing a case, with and without access checks
    for m in ["off", "graph"]:
        snap["case"][m] = c.post("/api/case/run", json={"tenant": "northwind", "mode": m}).json()
        snap["approve"][m] = c.post("/api/case/approve", json={"tenant": "northwind", "approver": "p_sam"}).json()

    # Private memory, after the questions above were asked
    for t, people in PERSONAS.items():
        snap["memory"][t] = {who: c.get(f"/api/memory?tenant={t}&asker={who}").json() for who in people}
        snap["peek"][t] = {a: {o: c.get(f"/api/memory/peek?tenant={t}&asker={a}&owner={o}").json() for o in people}
                           for a in people}

    # Oversharing: scan, test every fix on a fork, then apply each one on a fresh company
    reset_all()
    s = c.get("/api/scan?tenant=northwind").json()
    snap["scan"]["northwind"] = s
    snap["scan"]["bluefin"] = c.get("/api/scan?tenant=bluefin").json()
    findings = [(f["fix"], f.get("doc")) for f in s["overshared"]] + [(f["fix"], None) for f in s["drift"]]
    for fix, doc in findings:
        k = json.dumps(fix, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        snap["scan_test"][k] = c.post("/api/scan/test", json={"tenant": "northwind", "fix": fix, "doc": doc}).json()
    for fix, doc in findings:
        reset_all()
        k = json.dumps(fix, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        approver = "p_neha" if doc else "p_lena"
        applied = c.post("/api/scan/apply", json={"tenant": "northwind", "fix": fix, "doc": doc, "approver": approver,
                                                  "reason": "Approved after testing on a copy of the graph"}).json()
        applied["audit"] = c.get("/api/audit?tenant=northwind").json()
        snap["scan_apply"][k] = applied
    reset_all()

    snap["eval"] = c.get("/api/eval?refresh=true").json()
    for t in PERSONAS:
        snap["stats"][t] = c.get(f"/api/stats?tenant={t}").json()
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        sha = os.getenv("GITHUB_SHA", "")[:7]
    snap["built_from"] = sha

    # Copy the web app and point it at the snapshot
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "web", OUT / "static")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    html = html.replace('<script src="static/app.js"></script>',
                        '<script>window.NTK_STATIC = "demo-data.json";</script>\n<script src="static/app.js"></script>')
    (OUT / "index.html").write_text(html, encoding="utf-8")
    (OUT / "demo-data.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"static demo in {OUT}: {len(snap['ask'])} answers, {(OUT / 'demo-data.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
