"""Who can read what. Every decision here is a FalkorDB traversal, not an LLM guess.

Rules (the same rules `seed.expected_readable_sections` implements in plain Python):

* A principal (person, agent or group) holds every grant of every group it belongs to,
  following nested groups up to MAX_HOPS deep.
* A document is readable if it, or the space it lives in, is granted.
* A section inherits its document's access unless it is marked `restricted`; a
  restricted section needs its own grant.

Modes exist only to prove the graph matters:
  graph  - full nested traversal (the product)
  flat   - only direct group memberships (what a simple ACL list would do)
  off    - no access check at all (what a plain document chatbot does)
"""

from __future__ import annotations

import time

from . import config, db

MODES = ("graph", "flat", "off")

GRANTS_Q = f"""
MATCH (p:Principal {{id:$pid}})-[:MEMBER_OF*0..{config.MAX_HOPS}]->(g:Principal)-[:CAN_READ]->(t)
RETURN DISTINCT t.id
"""

GRANTS_FLAT_Q = """
MATCH (p:Principal {id:$pid})-[:MEMBER_OF*0..1]->(g:Principal)-[:CAN_READ]->(t)
RETURN DISTINCT t.id
"""

EXPLAIN_Q = f"""
MATCH path = (p:Principal {{id:$pid}})-[:MEMBER_OF*0..{config.MAX_HOPS}]->(g:Principal)-[r:CAN_READ]->(t)
WHERE t.id IN $targets
RETURN [n IN nodes(path) | n.name] AS names, [n IN nodes(path) | [l IN labels(n) WHERE l <> 'Principal'][0]] AS kinds,
       [n IN nodes(path) | n.id] AS ids, t.id AS target, r.granted_by AS by, r.granted_at AS at,
       r.reason AS reason, length(path) AS hops
ORDER BY hops ASC
LIMIT 1
"""

GRANTEES_Q = """
MATCH (g:Principal)-[r:CAN_READ]->(t) WHERE t.id IN $targets
RETURN DISTINCT g.id, g.name, [l IN labels(g) WHERE l <> 'Principal'][0]
"""

READERS_Q = f"""
MATCH (p:Person)-[:MEMBER_OF*0..{config.MAX_HOPS}]->(g:Principal)-[:CAN_READ]->(t)
WHERE t.id IN $targets
RETURN DISTINCT p.id
"""

CATALOG_Q = """
MATCH (s:Section)-[:PART_OF]->(d:Doc)-[:IN]->(sp:Space)
OPTIONAL MATCH (o:Person)-[:OWNS]->(d)
RETURN s.id, s.label, s.text, s.restricted, d.id, d.title, d.kind, d.updated, sp.id, sp.name, o.name, o.id
"""


class Catalog:
    """Static document structure, cached per graph (it only changes on reseed)."""

    def __init__(self, graph_name: str):
        g = db.graph(graph_name)
        self.sections: dict[str, dict] = {}
        self.docs: dict[str, dict] = {}
        for sid, label, text, restricted, did, title, kind, updated, spid, spname, owner, owner_id in db.rows(g, CATALOG_Q, ro=True):
            self.sections[sid] = {"id": sid, "label": label, "text": text, "restricted": bool(restricted), "doc": did}
            self.docs[did] = {"id": did, "title": title, "kind": kind, "updated": updated, "space": spid,
                              "space_name": spname, "owner": owner, "owner_id": owner_id}
        self.mentions: dict[str, set[str]] = {}
        for sid, cid in db.rows(g, "MATCH (s:Section)-[:MENTIONS]->(c:Customer) RETURN s.id, c.id", ro=True):
            self.mentions.setdefault(sid, set()).add(cid)

    def targets_for(self, sid: str) -> list[str]:
        """Grant targets that would make this section readable."""
        s = self.sections[sid]
        if s["restricted"]:
            return [sid]
        d = self.docs[s["doc"]]
        return [sid, d["id"], d["space"]]


_catalogs: dict[str, Catalog] = {}


def catalog(graph_name: str) -> Catalog:
    if graph_name not in _catalogs:
        _catalogs[graph_name] = Catalog(graph_name)
    return _catalogs[graph_name]


def reset_cache(graph_name: str | None = None) -> None:
    if graph_name:
        _catalogs.pop(graph_name, None)
    else:
        _catalogs.clear()


def grants(graph_name: str, pid: str, mode: str = "graph") -> set[str]:
    """Every resource id this principal holds a grant on (directly or through groups)."""
    if mode == "off":
        return set()
    q = GRANTS_FLAT_Q if mode == "flat" else GRANTS_Q
    return {r[0] for r in db.rows(db.graph(graph_name), q, {"pid": pid}, ro=True)}


def readable(cat: Catalog, held: set[str], sid: str, mode: str = "graph") -> bool:
    if mode == "off":
        return True
    s = cat.sections[sid]
    if sid in held:
        return True
    if s["restricted"]:
        return False
    d = cat.docs[s["doc"]]
    return d["id"] in held or d["space"] in held


def readable_set(graph_name: str, pid: str, mode: str = "graph") -> set[str]:
    cat = catalog(graph_name)
    held = grants(graph_name, pid, mode)
    return {sid for sid in cat.sections if readable(cat, held, sid, mode)}


def explain(graph_name: str, pid: str, targets: list[str]) -> dict | None:
    """The shortest chain of memberships that grants this principal one of the targets."""
    r = db.rows(db.graph(graph_name), EXPLAIN_Q, {"pid": pid, "targets": targets}, ro=True)
    if not r:
        return None
    names, kinds, ids, target, by, at, reason, hops = r[0]
    return {"names": names, "kinds": kinds, "ids": ids, "target": target, "granted_by": by,
            "granted_at": at, "reason": reason, "hops": hops}


def who_grants(graph_name: str, targets: list[str]) -> list[dict]:
    rows_ = db.rows(db.graph(graph_name), GRANTEES_Q, {"targets": targets}, ro=True)
    return [{"id": i, "name": n, "kind": k} for i, n, k in rows_]


def readers(graph_name: str, targets: list[str]) -> set[str]:
    return {r[0] for r in db.rows(db.graph(graph_name), READERS_Q, {"targets": targets}, ro=True)}


def can_read(graph_name: str, pid: str, sid: str, mode: str = "graph") -> bool:
    cat = catalog(graph_name)
    return readable(cat, grants(graph_name, pid, mode), sid, mode)


def timed_grants(graph_name: str, pid: str) -> float:
    t0 = time.perf_counter()
    grants(graph_name, pid)
    return (time.perf_counter() - t0) * 1000
