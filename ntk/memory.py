"""Private, persistent memory for every person and agent.

Each memory is an Episode node hanging off its owner: (owner)-[:REMEMBERS]->(Episode).
Every read starts from the requesting principal's own node, so there is no query path
from one person to another person's memories. Privacy comes from the shape of the graph,
not from a filter someone could forget to apply.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import db

RECALL_Q = """
MATCH (me:Principal {id:$pid})-[:REMEMBERS]->(e:Episode)
OPTIONAL MATCH (e)-[:MENTIONS]->(c:Customer)
WITH e, collect(c.name) AS about, collect(c.id) AS cids
WHERE size($customers) = 0 OR any(x IN cids WHERE x IN $customers)
RETURN e.id, e.kind, e.text, e.ts, about
ORDER BY e.ts DESC
LIMIT $limit
"""

# The privacy proof: try to reach someone else's memory starting from yourself.
PEEK_Q = """
MATCH (me:Principal {id:$asker})-[:REMEMBERS]->(e:Episode)<-[:REMEMBERS]-(owner:Principal {id:$owner})
RETURN count(e)
"""

COUNT_Q = "MATCH (o:Principal {id:$owner})-[:REMEMBERS]->(e:Episode) RETURN count(e)"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def remember(graph_name: str, pid: str, kind: str, text: str, customers: list[str] | None = None) -> str:
    eid = f"ep_{uuid.uuid4().hex[:12]}"
    db.rows(db.graph(graph_name),
            "MATCH (o:Principal {id:$pid}) CREATE (o)-[:REMEMBERS]->(e:Episode {id:$id, kind:$kind, text:$text, ts:$ts}) "
            "WITH e UNWIND $customers AS cid MATCH (c:Customer {id:cid}) CREATE (e)-[:MENTIONS]->(c)",
            {"pid": pid, "id": eid, "kind": kind, "text": text, "ts": now_iso(), "customers": customers or []})
    return eid


def recall(graph_name: str, pid: str, customers: list[str] | None = None, limit: int = 8) -> list[dict]:
    rows_ = db.rows(db.graph(graph_name), RECALL_Q,
                    {"pid": pid, "customers": customers or [], "limit": limit}, ro=True)
    return [{"id": i, "kind": k, "text": t, "ts": ts, "about": about} for i, k, t, ts, about in rows_]


def peek(graph_name: str, asker: str, owner: str) -> dict:
    g = db.graph(graph_name)
    reachable = db.rows(g, PEEK_Q, {"asker": asker, "owner": owner}, ro=True)[0][0]
    exists = db.rows(g, COUNT_Q, {"owner": owner}, ro=True)[0][0]
    return {"owner_has": exists, "asker_can_reach": reachable, "query": PEEK_Q.strip()}


def forget_run_artifacts(graph_name: str, kinds: list[str]) -> None:
    db.rows(db.graph(graph_name), "MATCH (e:Episode) WHERE e.kind IN $kinds DETACH DELETE e", {"kinds": kinds})
