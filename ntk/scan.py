"""Oversharing and access drift, found by traversing the access graph backwards.

For every document with an intended audience we compare who *should* read it with who
*can* read it, attribute the gap to the grant that causes it, and test the smallest fix
on a GRAPH.COPY fork of the company before anyone touches the real graph. Applying a fix
records a Decision node, so "who removed this access, and why?" stays answerable.
"""

from __future__ import annotations

import uuid

from . import access, config, db, memory

INTENDED_DOCS_Q = "MATCH (d:Doc) WHERE size(d.intended) > 0 RETURN d.id, d.title, d.space, d.intended"

GRANT_REACH_Q = f"""
MATCH (g:Principal)-[r:CAN_READ]->(t) WHERE t.id IN $targets
OPTIONAL MATCH (p:Person)-[:MEMBER_OF*0..{config.MAX_HOPS}]->(g)
RETURN g.id, g.name, labels(g)[0], t.id, r.granted_by, r.granted_at, r.reason, collect(DISTINCT p.id)
"""

INTENDED_READERS_Q = f"""
MATCH (p:Person)-[:MEMBER_OF*0..{config.MAX_HOPS}]->(g:Principal) WHERE g.id IN $intended
RETURN DISTINCT p.id
"""

EXTERNAL_Q = "MATCH (p:Person) WHERE p.id IN $ids AND p.external = true RETURN count(p)"

DRIFT_Q = """
MATCH (p:Person)-[:MEMBER_OF]->(g:Group {kind:'team'})
WHERE g.team <> p.team AND p.moved_from IS NOT NULL
RETURN p.id, p.name, p.title, p.team, p.moved_from, p.moved_at, g.id, g.name
"""

DELETE_GRANT_Q = "MATCH (g:Principal {id:$gid})-[r:CAN_READ]->(t {id:$tid}) DELETE r"
DELETE_MEMBERSHIP_Q = "MATCH (p:Principal {id:$pid})-[m:MEMBER_OF]->(g:Group {id:$gid}) DELETE m"


def _doc_findings(graph_name: str) -> list[dict]:
    g = db.graph(graph_name)
    out = []
    for did, title, space, intended in db.rows(g, INTENDED_DOCS_Q, ro=True):
        targets = [did, space]
        intended_ids = {r[0] for r in db.rows(g, INTENDED_READERS_Q, {"intended": intended}, ro=True)}
        grants_ = []
        actual = set()
        for gid, gname, kind, tid, by, at, reason, readers in db.rows(g, GRANT_REACH_Q, {"targets": targets}, ro=True):
            readers = set(readers)
            actual |= readers
            grants_.append({"grantee": gid, "grantee_name": gname, "kind": kind, "target": tid,
                            "granted_by": by, "granted_at": at, "reason": reason, "reach": len(readers),
                            "extra": len(readers - intended_ids)})
        extra = actual - intended_ids
        if not extra:
            continue
        culprit = max(grants_, key=lambda x: x["extra"])
        externals = db.rows(g, EXTERNAL_Q, {"ids": list(extra)}, ro=True)[0][0]
        out.append({"type": "overshared", "doc": did, "title": title, "intended_readers": len(intended_ids),
                    "actual_readers": len(actual), "extra_readers": len(extra), "external_readers": externals,
                    "culprit": culprit, "grants": sorted(grants_, key=lambda x: -x["extra"]),
                    "fix": {"action": "remove_grant", "grantee": culprit["grantee"], "target": culprit["target"],
                            "summary": f"Remove '{culprit['grantee_name']}' from {title}"}})
    return out


def _drift_findings(graph_name: str) -> list[dict]:
    g = db.graph(graph_name)
    cat = access.catalog(graph_name)
    out = []
    for pid, name, title, team, moved_from, moved_at, gid, gname in db.rows(g, DRIFT_Q, ro=True):
        with_ = access.readable_set(graph_name, pid)
        group_targets = {r[0] for r in db.rows(g, "MATCH (g:Principal {id:$gid})-[:MEMBER_OF*0..8]->(x:Principal)-[:CAN_READ]->(t) RETURN DISTINCT t.id",
                                               {"gid": gid}, ro=True)}
        via_group = sorted({cat.docs[cat.sections[s]["doc"]]["title"] for s in with_
                            if s in group_targets or cat.sections[s]["doc"] in group_targets
                            or cat.docs[cat.sections[s]["doc"]]["space"] in group_targets})
        out.append({"type": "drift", "person": pid, "name": name, "title": title, "team": team,
                    "moved_from": moved_from, "moved_at": moved_at, "group": gid, "group_name": gname,
                    "docs_via_old_team": via_group[:8], "docs_count": len(via_group),
                    "fix": {"action": "remove_membership", "person": pid, "group": gid,
                            "summary": f"Remove {name} from {gname} (moved to {team.title()} on {moved_at})"}})
    return out


def scan(graph_name: str) -> dict:
    return {"overshared": _doc_findings(graph_name), "drift": _drift_findings(graph_name)}


def _apply(g, fix: dict) -> int:
    if fix["action"] == "remove_grant":
        return g.query(DELETE_GRANT_Q, {"gid": fix["grantee"], "tid": fix["target"]}).relationships_deleted
    if fix["action"] == "remove_membership":
        return g.query(DELETE_MEMBERSHIP_Q, {"pid": fix["person"], "gid": fix["group"]}).relationships_deleted
    raise ValueError("unknown fix")


def test_fix(graph_name: str, fix: dict, doc: str | None = None) -> dict:
    """Apply the fix to a GRAPH.COPY fork, measure, and throw the fork away."""
    live = db.graph(graph_name)
    fork_name = f"{graph_name}__fork__{uuid.uuid4().hex[:8]}"
    fork = live.copy(fork_name)
    try:
        changed = _apply(fork, fix)
        result = {"fork": fork_name, "changed_edges": changed}
        if doc:
            space = db.rows(live, "MATCH (d:Doc {id:$d}) RETURN d.space, d.intended", {"d": doc}, ro=True)[0]
            targets = [doc, space[0]]
            intended = space[1]
            before = {r[0] for r in db.rows(live, access.READERS_Q, {"targets": targets}, ro=True)}
            after = {r[0] for r in db.rows(fork, access.READERS_Q, {"targets": targets}, ro=True)}
            must_keep = {r[0] for r in db.rows(live, INTENDED_READERS_Q, {"intended": intended}, ro=True)}
            lost = sorted(must_keep - after)
            result.update({"readers_before": len(before), "readers_after": len(after),
                           "intended_kept": not lost, "intended_lost": lost})
        if fix["action"] == "remove_membership":
            before = access.readable_set(graph_name, fix["person"])
            after = access.readable_set(fork_name, fix["person"])
            access.reset_cache(fork_name)
            result.update({"sections_before": len(before), "sections_after": len(after),
                           "removed": len(before - after)})
        result["passed"] = changed > 0 and result.get("intended_kept", True)
        return result
    finally:
        fork.delete()
        access.reset_cache(fork_name)


def apply_fix(graph_name: str, fix: dict, approver: str, reason: str) -> dict:
    """A person approved it: change the live graph and record the decision."""
    g = db.graph(graph_name)
    changed = _apply(g, fix)
    did = f"dc_{uuid.uuid4().hex[:8]}"
    target = fix.get("target") or fix.get("group")
    db.rows(g, "MATCH (p:Principal {id:$approver}) "
               "CREATE (p)-[:MADE]->(x:Decision {id:$id, summary:$summary, date:$date, kind:'access-change', reason:$reason}) "
               "WITH x MATCH (t {id:$target}) CREATE (x)-[:CHANGED]->(t)",
            {"approver": approver, "id": did, "summary": fix["summary"], "date": memory.now_iso(),
             "reason": reason, "target": target})
    memory.remember(graph_name, approver, "note", f"Approved access change: {fix['summary']}", [])
    return {"changed_edges": changed, "decision": did}


def audit(graph_name: str) -> list[dict]:
    rows_ = db.rows(db.graph(graph_name),
                    "MATCH (p:Principal)-[:MADE]->(x:Decision {kind:'access-change'}) "
                    "RETURN x.id, x.summary, x.date, x.reason, p.name ORDER BY x.date DESC", ro=True)
    return [{"id": i, "summary": s, "date": d, "reason": r, "by": who} for i, s, d, r, who in rows_]
