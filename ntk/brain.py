"""Answer a question as a specific person or agent.

1. Find candidate passages with FalkorDB's full-text index, plus passages linked to any
   customer named in the question.
2. Resolve the asker's access with one graph traversal (nested groups, spaces, sections).
3. Readable passages become cited facts. The rest become redactions that say what is
   missing and who could grant it, never what it says.
4. Pull the asker's own memories about the same customers, and any decisions behind the facts.
5. Only readable text is handed to the (optional) language model.
"""

from __future__ import annotations

import re

from . import access, db, llm, memory

STOP = set("""a an and are as at be but by can could did do does for from had has have how i if in into is it its
me my of on or our should so than that the their them then there these they this to us was we were what when where
which who whom why will with would you your about any much many tell please give show know need""".split())

SEARCH_Q = """
CALL db.idx.fulltext.queryNodes('Section', $q) YIELD node, score
RETURN node.id, score
ORDER BY score DESC
LIMIT 24
"""

CUSTOMER_SECTIONS_Q = """
MATCH (c:Customer)<-[:MENTIONS]-(s:Section) WHERE c.id IN $customers
RETURN s.id
"""

CUSTOMERS_Q = "MATCH (c:Customer) RETURN c.id, c.name"

DECISIONS_Q = """
MATCH (d:Doc)-[:DOCUMENTS]->(x:Decision)-[:DECIDED_IN]->(src:Doc)
WHERE d.id IN $docs OR src.id IN $docs
MATCH (p:Person)-[:MADE]->(x)
RETURN DISTINCT x.id, x.summary, x.date, p.name, src.id, src.title, d.id, d.title
"""

WHY_WORDS = {"why", "reason", "decided", "decision", "decide", "because", "how come"}


def keywords(question: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    out, seen = [], set()
    for w in words:
        if len(w) < 3 or w in STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out[:12]


def _customers_in(graph_name: str, question: str) -> list[tuple[str, str]]:
    ql = question.lower()
    found = []
    for cid, name in db.rows(db.graph(graph_name), CUSTOMERS_Q, ro=True):
        first = name.lower().split()[0]
        if name.lower() in ql or re.search(rf"\b{re.escape(first)}\b", ql):
            found.append((cid, name))
    return found


def retrieve(graph_name: str, question: str, limit: int = 7) -> tuple[list[str], list[tuple[str, str]]]:
    """Rank passages: FalkorDB full-text score, plus term overlap, plus a boost for named customers."""
    g = db.graph(graph_name)
    cat = access.catalog(graph_name)
    terms = keywords(question)
    ft: dict[str, float] = {}
    if terms:
        q = "|".join(f"{t}*" if len(t) > 4 else t for t in terms)
        for sid, score in db.rows(g, SEARCH_Q, {"q": q}, ro=True):
            ft[sid] = max(ft.get(sid, 0.0), float(score or 0))
    customers = _customers_in(graph_name, question)
    linked: set[str] = set()
    if customers:
        linked = {r[0] for r in db.rows(g, CUSTOMER_SECTIONS_Q, {"customers": [c for c, _ in customers]}, ro=True)}
    top_ft = max(ft.values(), default=0.0) or 1.0
    scored = {}
    for sid in set(ft) | linked:
        s = cat.sections.get(sid)
        if not s:
            continue
        words = set(re.findall(r"[a-z0-9]+", (s["label"] + " " + s["text"] + " " + cat.docs[s["doc"]]["title"]).lower()))
        overlap = sum(1 for t in terms if any(w.startswith(t[:5]) for w in words)) / max(1, len(terms))
        scored[sid] = ft.get(sid, 0.0) / top_ft + overlap + (0.5 if sid in linked else 0.0)
    ranked = sorted(scored, key=lambda x: (-scored[x], x))
    return [x for x in ranked if scored[x] >= 0.34][:limit], customers


def _fact(cat, sid):
    s = cat.sections[sid]
    d = cat.docs[s["doc"]]
    return {"id": sid, "label": s["label"], "text": s["text"], "restricted": s["restricted"],
            "source": {"doc": d["id"], "title": d["title"], "kind": d["kind"], "updated": d["updated"],
                       "space": d["space_name"], "owner": d["owner"]}}


def ask(graph_name: str, asker: str, question: str, mode: str = "graph", remember: bool = True,
        use_llm: bool = True) -> dict:
    cat = access.catalog(graph_name)
    hits, customers = retrieve(graph_name, question)
    held = access.grants(graph_name, asker, mode)
    truth = held if mode == "graph" else access.grants(graph_name, asker, "graph")

    facts, redacted = [], []
    for sid in hits:
        allowed_now = access.readable(cat, held, sid, mode)
        allowed_truly = access.readable(cat, truth, sid, "graph")
        if allowed_now:
            f = _fact(cat, sid)
            f["leak"] = not allowed_truly
            if allowed_truly:
                f["why"] = access.explain(graph_name, asker, cat.targets_for(sid))
            facts.append(f)
        else:
            s = cat.sections[sid]
            d = cat.docs[s["doc"]]
            grantees = access.who_grants(graph_name, cat.targets_for(sid))
            redacted.append({"id": sid, "label": s["label"], "doc_title": d["title"], "owner": d["owner"],
                             "needs": [x["name"] for x in grantees if x["kind"] == "Group"][:3],
                             "wrongly_hidden": allowed_truly})

    decisions = []
    if any(w in question.lower() for w in WHY_WORDS) or facts:
        docs = list({f["source"]["doc"] for f in facts})
        if docs:
            for xid, summary, date, who, src_id, src_title, doc_id, doc_title in db.rows(
                    db.graph(graph_name), DECISIONS_Q, {"docs": docs}, ro=True):
                src_sections = [sid for sid, s in cat.sections.items() if s["doc"] == src_id]
                src_visible = any(access.readable(cat, truth, sid, "graph") for sid in src_sections)
                decisions.append({"id": xid, "summary": summary, "date": date, "made_by": who,
                                  "source": src_title if src_visible else None,
                                  "documented_in": doc_title})

    cust_ids = [c for c, _ in customers]
    remembered = memory.recall(graph_name, asker, cust_ids, limit=3) if cust_ids else []

    answer = _summarise(question, facts, redacted, decisions, remembered, use_llm)
    if remember:
        memory.remember(graph_name, asker, "question", f"Asked: {question}", cust_ids)

    return {"question": question, "asker": asker, "mode": mode, "answer": answer, "facts": facts,
            "redacted": redacted, "decisions": decisions, "memory": remembered,
            "customers": [n for _, n in customers], "leaks": sum(1 for f in facts if f["leak"]),
            "graph": _access_graph(graph_name, asker, facts, redacted)}


def _summarise(question, facts, redacted, decisions, remembered, use_llm) -> dict:
    hidden = len(redacted)
    if use_llm and llm.available() and facts:
        context = "\n".join(f"- {f['text']} (source: {f['source']['title']})" for f in facts[:6])
        text = llm.complete(
            "You answer employee questions using ONLY the facts given. Two short sentences at most. "
            "Never guess or add numbers that are not in the facts.",
            f"Question: {question}\nFacts the employee may see:\n{context}")
        if text:
            return {"text": text, "by": "llm", "hidden": hidden}
    if not facts:
        text = "Nothing you are allowed to read answers this."
        if hidden:
            text += f" {hidden} relevant item{'s are' if hidden > 1 else ' is'} restricted."
        return {"text": text, "by": "template", "hidden": hidden}
    lead = facts[0]["text"]
    extra = f" {facts[1]['text']}" if len(facts) > 1 and len(lead) < 160 else ""
    text = lead + extra
    if hidden:
        text += f" {hidden} more item{'s are' if hidden > 1 else ' is'} restricted for you."
    return {"text": text, "by": "template", "hidden": hidden}


def _access_graph(graph_name, asker, facts, redacted) -> dict:
    """A small graph for the UI: the asker, the membership chain, and each fact or redaction."""
    nodes, edges, seen = [], [], set()

    def add(nid, label, kind, state="ok"):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": label, "kind": kind, "state": state})

    for f in facts:
        w = f.get("why")
        if w:
            for i, (nid, name, kind) in enumerate(zip(w["ids"], w["names"], w["kinds"])):
                add(nid, name, kind)
                if i:
                    edges.append({"from": w["ids"][i - 1], "to": nid, "kind": "MEMBER_OF"})
            tgt = f"t::{w['target']}"
            add(tgt, _target_label(graph_name, w["target"], f), "Grant")
            edges.append({"from": w["ids"][-1], "to": tgt, "kind": "CAN_READ"})
            add(f["id"], f["label"], "Section", "leak" if f["leak"] else "ok")
            if tgt != f"t::{f['id']}":
                edges.append({"from": tgt, "to": f["id"], "kind": "CONTAINS"})
        else:
            add(asker, asker, "Person")
            add(f["id"], f["label"], "Section", "leak" if f["leak"] else "ok")
            edges.append({"from": asker, "to": f["id"], "kind": "NO_CHECK"})
    for r in redacted:
        add(r["id"], r["label"], "Section", "hidden")
    return {"nodes": nodes, "edges": edges}


def _target_label(graph_name, target, fact):
    cat = access.catalog(graph_name)
    if target in cat.sections:
        return cat.sections[target]["label"]
    if target in cat.docs:
        return cat.docs[target]["title"]
    return fact["source"]["space"] if target.startswith("sp_") else target
