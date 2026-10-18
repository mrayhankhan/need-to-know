"""Two AI agents share one case. Each sees only what its own groups allow.

Case #4821: Acme asks why their invoice went up.
  1. Support Agent claims the case, reads the ticket and its own playbook, hands off to Finance.
  2. Finance Agent reads the contract (restricted to Finance), writes a Finance-only note and a
     customer-safe note, and hands the case back.
  3. Support Agent reads the case again. The Finance-only note is redacted for it, so the
     customer reply it drafts cannot contain the contract value. A person approves the reply.

Shared state lives in the graph: (Note)-[:ON]->(Case), (Agent)-[:HANDED_OFF]->(Agent),
Case.status. Every agent's own memory is an Episode on that agent.
"""

from __future__ import annotations

from . import access, db, memory

CASE_ID = "case_4821"

NOTES_Q = """
MATCH (n:Note)-[:ON]->(c:Case {id:$case})
MATCH (a:Principal)-[:WROTE]->(n)
RETURN n.id, n.text, n.customer_text, n.restricted, n.ts, a.id, a.name
ORDER BY n.ts ASC, n.id ASC
"""

HANDOFFS_Q = """
MATCH (a:Principal)-[h:HANDED_OFF {case:$case}]->(b:Principal)
RETURN a.name, b.name, h.ts, h.reason, h.step
ORDER BY h.step ASC
"""


def _note(g, case, author, nid, text, customer_text, restricted, step, readers=()):
    db.rows(g, "MATCH (c:Case {id:$case}), (a:Principal {id:$author}) "
               "CREATE (a)-[:WROTE]->(n:Note {id:$id, text:$text, customer_text:$ct, restricted:$r, ts:$ts})-[:ON]->(c)",
            {"case": case, "author": author, "id": nid, "text": text, "ct": customer_text, "r": restricted,
             "ts": f"{memory.now_iso()}#{step}"})
    for who in readers:
        db.rows(g, "MATCH (w:Principal {id:$who}), (n:Note {id:$id}) "
                   "CREATE (w)-[:CAN_READ {granted_by:$by, granted_at:$at, reason:'Finance-only note'}]->(n)",
                {"who": who, "id": nid, "by": author, "at": memory.now_iso()[:10]})


def _handoff(g, case, a, b, reason, step):
    db.rows(g, "MATCH (a:Principal {id:$a}), (b:Principal {id:$b}), (c:Case {id:$case}) "
               "CREATE (a)-[:HANDED_OFF {case:$case, ts:$ts, reason:$reason, step:$step}]->(b) "
               "SET c.claimed_by = $b, c.status = 'with ' + b.name",
            {"a": a, "b": b, "case": case, "ts": memory.now_iso(), "reason": reason, "step": step})


def reset(graph_name: str, case: str = CASE_ID) -> None:
    g = db.graph(graph_name)
    db.rows(g, "MATCH (n:Note)-[:ON]->(:Case {id:$case}) DETACH DELETE n", {"case": case})
    db.rows(g, "MATCH ()-[h:HANDED_OFF {case:$case}]->() DELETE h", {"case": case})
    db.rows(g, "MATCH (c:Case {id:$case}) SET c.status = 'new', c.claimed_by = '', c.reply = '', c.reply_leaks = false",
            {"case": case})
    memory.forget_run_artifacts(graph_name, ["case-step"])


def view(graph_name: str, viewer: str, mode: str = "graph", case: str = CASE_ID) -> dict:
    g = db.graph(graph_name)
    held = access.grants(graph_name, viewer, mode)
    truth = access.grants(graph_name, viewer, "graph")
    meta = db.rows(g, "MATCH (c:Case {id:$case})-[:IN]->(sp:Space) RETURN c.title, c.status, c.claimed_by, c.reply, c.reply_leaks, sp.id",
                   {"case": case}, ro=True)
    title, status, claimed, reply, reply_leaks, space = meta[0]

    def can(nid, restricted, held_):
        if mode == "off" and held_ is held:
            return True
        return nid in held_ or (not restricted and (case in held_ or space in held_))

    notes = []
    for nid, text, ctext, restricted, ts, aid, aname in db.rows(g, NOTES_Q, {"case": case}, ro=True):
        visible = can(nid, restricted, held)
        notes.append({"id": nid, "author": aname, "restricted": bool(restricted), "visible": visible,
                      "text": text if visible else None, "leak": visible and not can(nid, restricted, truth)})
    handoffs = [{"from": a, "to": b, "ts": ts, "reason": r, "step": s}
                for a, b, ts, r, s in db.rows(g, HANDOFFS_Q, {"case": case}, ro=True)]
    return {"case": case, "title": title, "status": status, "claimed_by": claimed, "viewer": viewer,
            "mode": mode, "notes": notes, "handoffs": handoffs, "reply": reply or "",
            "reply_leaks": bool(reply_leaks)}


def run(graph_name: str, mode: str = "graph", case: str = CASE_ID) -> dict:
    """Play the whole case. `mode` applies to what the Support Agent can see in step 3."""
    reset(graph_name, case)
    g = db.graph(graph_name)
    cat = access.catalog(graph_name)
    steps = []

    # Step 1: Support Agent
    sup_held = access.grants(graph_name, "a_support")
    ticket_ok = access.readable(cat, sup_held, "d_ticket_4821__0")
    playbook_ok = access.readable(cat, sup_held, "d_support_playbook__0")
    db.rows(g, "MATCH (c:Case {id:$case}) SET c.status = 'with Support Agent', c.claimed_by = 'a_support'", {"case": case})
    _note(g, case, "a_support", "n1",
          "Acme Corp asks why the October invoice is higher than September.",
          "", False, 1)
    memory.remember(graph_name, "a_support", "case-step", "Claimed case #4821 (Acme invoice). Playbook says: hand billing questions to the Finance Agent.", ["c_acme"])
    _handoff(g, case, "a_support", "a_finance", "Billing question: playbook says Finance explains invoices", 1)
    steps.append({"step": 1, "actor": "Support Agent", "did": "Read the ticket and the billing playbook, wrote a note, handed the case to the Finance Agent.",
                  "checks": [{"what": "Ticket #4821", "ok": ticket_ok}, {"what": "Support playbook", "ok": playbook_ok}]})

    # Step 2: Finance Agent
    fin_held = access.grants(graph_name, "a_finance")
    contract_ok = access.readable(cat, fin_held, "d_acme_overview__2")
    approval_ok = access.readable(cat, fin_held, "d_finance_chat__1")
    _note(g, case, "a_finance", "n2",
          "Finance only: Acme pays ₹38,00,000 a year. Their 18% loyalty discount (approved by Meera Iyer on Sept 28, 2025) ended on Sept 30, 2026.",
          "For reference, your contract value is ₹38,00,000 a year and your discount was 18%.",
          True, 2, readers=["g_team_finance", "g_leadership"])
    _note(g, case, "a_finance", "n3",
          "Customer-safe: the price did not change. A 12-month loyalty discount ended on Sept 30, so the invoice returned to the standard rate. Arjun Mehta can discuss a renewal offer.",
          "The price of your plan did not change. Your 12-month loyalty discount ended on September 30, 2026, so the October invoice returned to the standard rate. Arjun Mehta, your account manager, can talk you through renewal options.",
          False, 3)
    memory.remember(graph_name, "a_finance", "case-step", "Explained Acme's discount expiry. Kept the contract value in a Finance-only note.", ["c_acme"])
    _handoff(g, case, "a_finance", "a_support", "Explanation ready; contract details kept Finance-only", 2)
    steps.append({"step": 2, "actor": "Finance Agent", "did": "Read the contract and the discount approval, wrote one Finance-only note and one customer-safe note, handed the case back.",
                  "checks": [{"what": "Acme contract value (restricted)", "ok": contract_ok},
                             {"what": "Discount approval in #finance", "ok": approval_ok}]})

    # Step 3: Support Agent drafts the reply from what it can see
    seen = view(graph_name, "a_support", mode, case)
    texts = {}
    for nid, ctext in db.rows(g, "MATCH (n:Note)-[:ON]->(:Case {id:$case}) RETURN n.id, n.customer_text", {"case": case}, ro=True):
        texts[nid] = ctext
    visible_ids = [n["id"] for n in seen["notes"] if n["visible"]]
    body = " ".join(texts[i] for i in ["n3", "n2"] if i in visible_ids and texts.get(i))
    reply = f"Hi Tom, thanks for asking. {body} Best, Northwind Support"
    leaks = "38,00,000" in reply
    db.rows(g, "MATCH (c:Case {id:$case}) SET c.reply = $reply, c.reply_leaks = $leaks, c.status = 'reply waiting for approval'",
            {"case": case, "reply": reply, "leaks": leaks})
    memory.remember(graph_name, "a_support", "case-step", "Drafted the Acme reply from the notes I am allowed to see. Waiting for a person to approve.", ["c_acme"])
    steps.append({"step": 3, "actor": "Support Agent",
                  "did": "Read the case again and drafted the customer reply from the notes it may see. A person must approve it.",
                  "checks": [{"what": n["author"] + (" (Finance-only note)" if n["restricted"] else " note"), "ok": n["visible"]}
                             for n in seen["notes"]]})

    return {"mode": mode, "steps": steps, "view": view(graph_name, "a_support", mode, case), "reply": reply, "leaks": leaks}


def approve(graph_name: str, approver: str, case: str = CASE_ID) -> dict:
    g = db.graph(graph_name)
    r = db.rows(g, "MATCH (c:Case {id:$case}) RETURN c.reply_leaks", {"case": case}, ro=True)
    if r and r[0][0]:
        return {"ok": False, "reason": "This reply contains Finance-only information. Fix access before sending."}
    db.rows(g, "MATCH (c:Case {id:$case}) SET c.status = 'reply approved by ' + $who", {"case": case, "who": approver})
    return {"ok": True}
