"""MCP server: lets any MCP client (Claude Code, Cursor, an agent framework) use Need-to-Know as a tool.

Run:  pip install -r requirements-mcp.txt && python mcp_server.py
Every tool takes the principal it acts for. In production that identity would come from the
authenticated session, never from the model; here it is a parameter so the demo can switch people.
"""

from mcp.server.fastmcp import FastMCP

from ntk import access, brain, db, memory, scan, seed

mcp = FastMCP("need-to-know")


@mcp.tool()
def ask(question: str, principal: str, tenant: str = "northwind") -> dict:
    """Answer a question about the company using only what `principal` is allowed to read.
    Returns cited facts, redactions (what is withheld and who could grant it) and related decisions."""
    a = brain.ask(tenant, principal, question)
    return {k: a[k] for k in ("answer", "facts", "redacted", "decisions", "memory", "leaks")}


@mcp.tool()
def can_read(principal: str, section_id: str, tenant: str = "northwind") -> dict:
    """Check one passage, and return the chain of group memberships that grants access."""
    cat = access.catalog(tenant)
    ok = access.can_read(tenant, principal, section_id)
    return {"allowed": ok, "why": access.explain(tenant, principal, cat.targets_for(section_id)) if ok else None}


@mcp.tool()
def who_can_read(doc_id: str, tenant: str = "northwind") -> dict:
    """Everyone who can open a document, through any chain of groups."""
    d = db.rows(db.graph(tenant), "MATCH (d:Doc {id:$d}) RETURN d.space", {"d": doc_id}, ro=True)
    if not d:
        return {"error": "unknown document"}
    readers = access.readers(tenant, [doc_id, d[0][0]])
    return {"count": len(readers), "sample": sorted(readers)[:20]}


@mcp.tool()
def recall(principal: str, tenant: str = "northwind") -> list:
    """The principal's own private memories (nobody else's are reachable)."""
    return memory.recall(tenant, principal, limit=20)


@mcp.tool()
def remember(principal: str, text: str, tenant: str = "northwind") -> str:
    """Save a private memory for this principal."""
    return memory.remember(tenant, principal, "note", text)


@mcp.tool()
def oversharing_report(tenant: str = "northwind") -> dict:
    """Documents more people can open than intended, and people who kept access after changing teams."""
    return scan.scan(tenant)


if __name__ == "__main__":
    seed.ensure_loaded()
    mcp.run()
