"""Deterministic synthetic companies for Need-to-Know.

Everything here is made up (rule 6: synthetic data only). The generator is seeded,
so every run produces the same company, and the same planted problems:

* a salary sheet that ~everyone can open through a forgotten "Drive migration 2023" group
* a board deck that external contractors can open through a nested project group
* an engineer who moved teams but kept their old Finance access

`build_spec()` returns a plain-Python description of a company. `load()` writes it
into FalkorDB. `expected_*()` compute access straight from the spec in Python, with no
database, so tests can check FalkorDB's answers against an independent ground truth.
"""

from __future__ import annotations

import argparse
import random
from collections import deque
from datetime import datetime, timedelta, timezone

from . import config, db

FIRST = ["Aarav", "Diya", "Kiran", "Isha", "Rohan", "Sneha", "Vikram", "Ananya", "Farhan", "Tara",
         "Nikhil", "Pooja", "Siddharth", "Leela", "Omar", "Grace", "Daniel", "Sofia", "Liam", "Mei",
         "Jonas", "Amara", "Yusuf", "Elena", "Hugo", "Zara", "Tomas", "Aisha", "Ben", "Chloe",
         "Dev", "Esha", "Felix", "Gauri", "Hari", "Ira", "Jai", "Kavya", "Luca", "Maya",
         "Noor", "Oscar", "Pia", "Qasim", "Riya", "Sam", "Tanvi", "Uma", "Varun", "Wen"]
LAST = ["Sharma", "Patel", "Iyer", "Menon", "Gupta", "Reddy", "Khan", "Das", "Bose", "Joshi",
        "Kapoor", "Singh", "Verma", "Pillai", "Chopra", "Nguyen", "Garcia", "Muller", "Rossi", "Kim",
        "Silva", "Novak", "Haddad", "Okafor", "Larsen", "Tanaka", "Costa", "Ahmed", "Fischer", "Brown"]

TEAMS = {  # team id: (display name, headcount of generated staff)
    "engineering": ("Engineering", 62),
    "support": ("Support", 34),
    "sales": ("Sales", 26),
    "operations": ("Operations", 18),
    "marketing": ("Marketing", 16),
    "product": ("Product", 14),
    "finance": ("Finance", 9),
    "hr": ("People & HR", 6),
    "legal": ("Legal", 4),
}


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_spec(tenant: str = "northwind") -> dict:
    if tenant == "bluefin":
        return _bluefin()
    return _northwind()


# --------------------------------------------------------------------------------------
# Northwind Labs: the main demo company
# --------------------------------------------------------------------------------------

def _northwind() -> dict:
    rnd = random.Random(42)
    people, agents, groups, members = [], [], [], []
    spaces, docs, sections, grants = [], [], [], []
    customers, mentions, decisions, episodes = [], [], [], []

    def person(pid, name, title, team, level="ic", **extra):
        people.append({"id": pid, "name": name, "title": title, "team": team, "level": level,
                       "external": False, **extra})
        return pid

    def group(gid, name, kind, team=None, temporary=False):
        groups.append({"id": gid, "name": name, "kind": kind, "team": team or "", "temporary": temporary})
        return gid

    def member(a, b):
        members.append((a, b))

    def space(sid, name):
        spaces.append({"id": sid, "name": name})
        return sid

    def grant(who, target, label, by, at, reason):
        grants.append({"who": who, "target": target, "label": label, "by": by, "at": at, "reason": reason})

    def doc(did, title, kind, sp, owner, updated, intended=None, body_sections=()):
        docs.append({"id": did, "title": title, "kind": kind, "space": sp, "owner": owner,
                     "updated": updated, "intended": intended or []})
        for i, (label, text, restricted) in enumerate(body_sections):
            sections.append({"id": f"{did}__{i}", "doc": did, "label": label, "text": text,
                             "restricted": restricted})
        return did

    # ---- groups
    group("g_all_staff", "All Staff", "org")
    for t, (tname, _) in TEAMS.items():
        group(f"g_team_{t}", tname, "team", team=t)
        member(f"g_team_{t}", "g_all_staff")
    group("g_leadership", "Leadership", "role")
    group("g_finance_leads", "Finance Leads", "role")
    member("g_finance_leads", "g_team_finance")
    group("g_hr_leads", "HR Leads", "role")
    member("g_hr_leads", "g_team_hr")
    group("g_people_managers", "People Managers", "role")
    member("g_people_managers", "g_all_staff")
    group("g_support_agents", "Support AI agents", "agents")
    member("g_support_agents", "g_team_support")
    group("g_finance_agents", "Finance AI agents", "agents")
    member("g_finance_agents", "g_team_finance")
    group("g_contractors", "External contractors", "external")
    group("g_project_phoenix", "Project Phoenix", "project")
    member("g_contractors", "g_project_phoenix")
    group("g_drive_migration_2023", "Drive migration 2023 (temporary)", "legacy", temporary=True)
    member("g_all_staff", "g_drive_migration_2023")
    member("g_contractors", "g_drive_migration_2023")

    # ---- named people (the cast of the demo)
    person("p_kabir", "Kabir Rao", "Chief Executive Officer", "operations", "exec")
    person("p_meera", "Meera Iyer", "Head of Finance", "finance", "head")
    person("p_neha", "Neha Shah", "Head of People & HR", "hr", "head")
    person("p_arjun", "Arjun Mehta", "Account Manager, Acme Corp", "sales")
    person("p_priya", "Priya Nair", "Support Intern", "support", "intern")
    person("p_ravi", "Ravi Kumar", "Backend Engineer", "engineering",
           moved_from="finance", moved_at="2026-08-10")
    person("p_lena", "Lena Brooks", "Head of Engineering", "engineering", "head")
    person("p_sam", "Sam Okafor", "Head of Support", "support", "head")
    person("p_anika", "Anika Desai", "Finance Analyst", "finance")
    person("p_rahul", "Rahul Bose", "HR Business Partner", "hr")
    for pid, team in [("p_kabir", "operations"), ("p_meera", "finance"), ("p_neha", "hr"),
                      ("p_arjun", "sales"), ("p_priya", "support"), ("p_ravi", "engineering"),
                      ("p_lena", "engineering"), ("p_sam", "support"), ("p_anika", "finance"),
                      ("p_rahul", "hr")]:
        member(pid, f"g_team_{team}")
    for pid in ["p_kabir", "p_meera", "p_neha", "p_lena", "p_sam"]:
        member(pid, "g_leadership")
        member(pid, "g_people_managers")
    member("p_meera", "g_finance_leads")
    member("p_neha", "g_hr_leads")
    member("p_rahul", "g_hr_leads")
    member("p_ravi", "g_team_finance")      # planted drift: moved to Engineering, kept Finance
    member("p_ravi", "g_project_phoenix")
    member("p_lena", "g_project_phoenix")

    # ---- generated staff
    used = {p["name"] for p in people}
    n = 0
    for t, (tname, count) in TEAMS.items():
        for i in range(count):
            while True:
                name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
                if name not in used:
                    used.add(name)
                    break
            n += 1
            pid = f"p_{t}_{i:02d}"
            level = "manager" if i % 9 == 0 else "ic"
            person(pid, name, f"{'Manager' if level == 'manager' else 'Specialist'}, {tname}", t, level)
            member(pid, f"g_team_{t}")
            if level == "manager":
                member(pid, "g_people_managers")
            if t in ("engineering", "product") and i % 5 == 0:
                member(pid, "g_project_phoenix")
    for i in range(12):
        while True:
            name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        pid = f"p_contractor_{i:02d}"
        people.append({"id": pid, "name": name, "title": "Contractor (external agency)",
                       "team": "contractors", "level": "external", "external": True})
        member(pid, "g_contractors")

    # ---- AI agents are principals too
    agents.append({"id": "a_support", "name": "Support Agent", "role": "Answers customer tickets"})
    agents.append({"id": "a_finance", "name": "Finance Agent", "role": "Explains invoices and contracts"})
    agents.append({"id": "a_sales", "name": "Sales Agent", "role": "Prepares account briefs"})
    member("a_support", "g_support_agents")
    member("a_finance", "g_finance_agents")
    member("a_sales", "g_team_sales")

    # ---- spaces and their grants
    space("sp_company", "Company handbook")
    space("sp_support", "Support tickets")
    space("sp_sales", "Sales accounts")
    space("sp_finance", "Finance")
    space("sp_hr_conf", "HR confidential")
    space("sp_leadership", "Leadership")
    space("sp_engineering", "Engineering wiki")
    space("sp_legal", "Legal")
    space("sp_cases", "Customer cases")
    grant("g_all_staff", "sp_company", "Space", "Neha Shah", "2024-01-08", "Company-wide handbook")
    grant("g_contractors", "sp_company", "Space", "Neha Shah", "2024-01-08", "Contractors read the handbook")
    for g_ in ["g_team_support", "g_team_sales"]:
        grant(g_, "sp_support", "Space", "Sam Okafor", "2024-02-01", "Ticket queue access")
    for g_ in ["g_team_sales", "g_team_support", "g_leadership"]:
        grant(g_, "sp_sales", "Space", "Arjun Mehta", "2024-02-01", "Account context for customer-facing teams")
    for g_ in ["g_team_finance", "g_leadership"]:
        grant(g_, "sp_finance", "Space", "Meera Iyer", "2024-01-15", "Finance workspace")
    grant("g_hr_leads", "sp_hr_conf", "Space", "Neha Shah", "2024-01-15", "HR leads only")
    grant("p_kabir", "sp_hr_conf", "Space", "Neha Shah", "2024-01-15", "CEO sees compensation")
    grant("g_leadership", "sp_leadership", "Space", "Kabir Rao", "2024-01-10", "Leadership workspace")
    for g_ in ["g_team_engineering", "g_team_product"]:
        grant(g_, "sp_engineering", "Space", "Lena Brooks", "2024-01-20", "Engineering docs")
    grant("g_team_legal", "sp_legal", "Space", "Kabir Rao", "2024-01-10", "Legal workspace")
    for g_ in ["g_team_support", "g_team_finance", "g_team_sales"]:
        grant(g_, "sp_cases", "Space", "Sam Okafor", "2024-03-01", "Shared customer cases")

    # ---- customers
    for cid, name in [("c_acme", "Acme Corp"), ("c_globex", "Globex"), ("c_initech", "Initech")]:
        customers.append({"id": cid, "name": name})

    # ---- the documents that matter in the demo
    doc("d_acme_overview", "Acme Corp: account overview", "doc", "sp_sales", "p_arjun", "2026-10-05",
        body_sections=[
            ("Renewal date", "Acme Corp's annual contract renews on November 30, 2026. Arjun Mehta in Sales owns the account.", False),
            ("Key contacts", "Key contacts at Acme Corp are Lena Ortiz, VP Operations, and Tom Becker, IT lead.", False),
            ("Contract value and discount", "Acme Corp pays ₹38,00,000 a year. Their 18% loyalty discount ended on September 30, 2026, which is why the October invoice went up.", True),
        ])
    for g_, by, reason in [("g_team_finance", "Meera Iyer", "Finance owns contract values"),
                           ("g_leadership", "Meera Iyer", "Leadership reviews top accounts"),
                           ("p_arjun", "Meera Iyer", "Account owner")]:
        grant(g_, "d_acme_overview__2", "Section", by, "2025-09-28", reason)
    mentions += [("d_acme_overview__0", "c_acme"), ("d_acme_overview__1", "c_acme"), ("d_acme_overview__2", "c_acme")]

    doc("d_ticket_4821", "Ticket #4821: Acme asks why their invoice went up", "ticket", "sp_support", "p_sam", "2026-10-02",
        body_sections=[
            ("Customer message", "On October 2, Acme Corp's IT lead wrote: our October invoice is higher than September. Did the price change?", False),
            ("Ticket status", "Ticket #4821 for Acme Corp is open and assigned to the Support Agent.", False),
        ])
    mentions += [("d_ticket_4821__0", "c_acme"), ("d_ticket_4821__1", "c_acme")]

    doc("d_pricing_policy", "Pricing policy 2026", "policy", "sp_company", "p_meera", "2026-01-12",
        body_sections=[
            ("Loyalty discounts", "Loyalty discounts last 12 months and are not renewed automatically. When one ends, the invoice returns to the standard rate.", False),
            ("Renewal offers", "Account managers may offer a renewal discount of up to 10% with Finance approval.", False),
        ])

    doc("d_finance_chat", "#finance chat: loyalty discount expiry", "chat", "sp_finance", "p_meera", "2025-09-12",
        body_sections=[
            ("Decision", "Meera Iyer, September 12, 2025: from now on loyalty discounts end after 12 months. No silent renewals.", False),
            ("Acme discount approval", "Acme Corp's 18% loyalty discount was approved by Meera Iyer on September 28, 2025, for 12 months.", False),
        ])
    mentions += [("d_finance_chat__1", "c_acme")]
    decisions.append({"id": "dc_loyalty_12m", "summary": "Loyalty discounts end after 12 months and are never renewed silently.",
                      "made_by": "p_meera", "date": "2025-09-12", "source": "d_finance_chat", "documented_in": "d_pricing_policy"})

    doc("d_support_playbook", "Support playbook: billing questions", "playbook", "sp_company", "p_sam", "2026-05-20",
        body_sections=[
            ("Billing questions", "For billing questions, the Support Agent hands the case to the Finance Agent and waits for a customer-safe explanation.", False),
            ("Never share", "Never share a customer's contract value, discount percentage or internal approvals in a customer reply.", False),
        ])

    doc("d_salary_bands", "Salary bands 2026", "spreadsheet", "sp_hr_conf", "p_neha", "2026-04-01",
        intended=["g_hr_leads", "p_kabir"],
        body_sections=[
            ("Engineering bands", "Engineering salary bands 2026: L1 ₹12-18 LPA, L2 ₹18-28 LPA, L3 ₹28-45 LPA, Staff ₹45-70 LPA.", False),
            ("Sales bands", "Sales salary bands 2026: Associate ₹8-12 LPA plus commission, Account Manager ₹14-24 LPA plus commission.", False),
        ])
    grant("g_drive_migration_2023", "d_salary_bands", "Doc", "migration-bot", "2023-04-12",
          "Temporary access during the 2023 Drive migration")

    doc("d_board_q3", "Q3 board update", "deck", "sp_leadership", "p_kabir", "2026-09-30",
        intended=["g_leadership"],
        body_sections=[
            ("Runway", "Runway is 22 months at the current burn rate.", False),
            ("Fundraising plan", "We plan to raise a Series B in Q2 2027.", False),
        ])
    grant("g_project_phoenix", "d_board_q3", "Doc", "Kabir Rao", "2026-06-02", "Shared for the Phoenix launch review")

    doc("d_inc203", "Postmortem INC-203: duplicate payment retries", "postmortem", "sp_engineering", "p_lena", "2026-07-20",
        body_sections=[
            ("What happened", "On July 14, 2026, client-side retries charged 40 customers twice.", False),
            ("Decision", "Decision: never retry payments on the client side. Retries happen once, server-side, with an idempotency key.", False),
        ])
    decisions.append({"id": "dc_no_client_retries", "summary": "Never retry payments on the client side.",
                      "made_by": "p_lena", "date": "2026-07-20", "source": "d_inc203", "documented_in": "d_inc203"})

    doc("d_globex_overview", "Globex: account overview", "doc", "sp_sales", "p_arjun", "2026-09-18",
        body_sections=[
            ("Renewal date", "Globex renews on March 31, 2027.", False),
            ("Contract value", "Globex pays ₹21,50,000 a year with no active discount.", True),
        ])
    grant("g_team_finance", "d_globex_overview__1", "Section", "Meera Iyer", "2025-09-28", "Finance owns contract values")
    grant("g_leadership", "d_globex_overview__1", "Section", "Meera Iyer", "2025-09-28", "Leadership reviews top accounts")
    mentions += [("d_globex_overview__0", "c_globex"), ("d_globex_overview__1", "c_globex")]

    doc("d_legal_acme", "Acme Corp master services agreement", "contract", "sp_legal", "p_kabir", "2025-11-30",
        body_sections=[
            ("Liability cap", "Acme Corp's liability cap is 12 months of fees.", False),
        ])
    mentions += [("d_legal_acme__0", "c_acme")]

    # ---- filler documents so search has something to wade through
    filler = {
        "sp_company": [("Leave policy", "Everyone gets 24 days of paid leave plus public holidays."),
                       ("Expense policy", "Submit expenses within 30 days with a receipt."),
                       ("Security basics", "Use the password manager and turn on two-factor login.")],
        "sp_engineering": [("On-call guide", "On-call engineers acknowledge pages within 10 minutes."),
                           ("Release process", "Releases ship on Tuesdays and Thursdays after review."),
                           ("Service ownership", "The payments service is owned by the Billing Platform team.")],
        "sp_support": [("Ticket #4790: login issue", "Initech reported a login issue that was fixed on September 21."),
                       ("Ticket #4805: export bug", "Globex asked about CSV exports timing out.")],
        "sp_finance": [("Monthly close", "The monthly close finishes on the 5th working day."),
                       ("Invoice runs", "Invoices are generated on the 1st of each month.")],
        "sp_leadership": [("Hiring plan", "We plan to hire 18 engineers in the next two quarters.")],
    }
    k = 0
    for sp, items in filler.items():
        for title, text in items:
            k += 1
            doc(f"d_f{k:02d}", title, "doc", sp, "p_sam", "2026-06-01", body_sections=[(title, text, False)])
    mentions += [("d_f07__0", "c_initech"), ("d_f08__0", "c_globex")]

    # ---- a case two agents will work on
    case = {"id": "case_4821", "title": "Acme invoice question", "customer": "c_acme", "ticket": "d_ticket_4821",
            "space": "sp_cases"}
    grant("g_support_agents", "case_4821", "Case", "Sam Okafor", "2026-10-02", "Assigned to support")
    grant("g_finance_agents", "case_4821", "Case", "Meera Iyer", "2026-10-02", "Finance consults on billing")

    # ---- memory from yesterday, private to each principal
    yday = datetime.now(timezone.utc) - timedelta(days=1)
    episodes += [
        {"owner": "p_priya", "kind": "question", "text": "Asked: When does Acme Corp renew? Answer: November 30, 2026.", "ts": _iso(yday.replace(hour=10, minute=12)), "customers": ["c_acme"]},
        {"owner": "p_meera", "kind": "note", "text": "Reviewed Acme Corp's expiring discount with Arjun. Offer at most 10% on renewal.", "ts": _iso(yday.replace(hour=15, minute=40)), "customers": ["c_acme"]},
        {"owner": "a_support", "kind": "lesson", "text": "Billing questions go to the Finance Agent. Customers must never see contract values.", "ts": _iso(yday.replace(hour=9, minute=5)), "customers": []},
        {"owner": "a_finance", "kind": "lesson", "text": "Explain discount expiry without quoting the contract value to non-finance agents.", "ts": _iso(yday.replace(hour=9, minute=6)), "customers": []},
    ]

    return {"tenant": "northwind", "company": "Northwind Labs", "people": people, "agents": agents,
            "groups": groups, "members": members, "spaces": spaces, "docs": docs, "sections": sections,
            "grants": grants, "customers": customers, "mentions": mentions, "decisions": decisions,
            "episodes": episodes, "case": case}


# --------------------------------------------------------------------------------------
# Bluefin Health: a second tenant, to show isolation between companies
# --------------------------------------------------------------------------------------

def _bluefin() -> dict:
    people = [
        {"id": "p_ines", "name": "Ines Moreau", "title": "Chief Operating Officer", "team": "ops", "level": "exec", "external": False},
        {"id": "p_dev", "name": "Dev Malhotra", "title": "Clinic Coordinator", "team": "ops", "level": "ic", "external": False},
        {"id": "p_hana", "name": "Hana Sato", "title": "Billing Specialist", "team": "billing", "level": "ic", "external": False},
    ]
    groups = [{"id": "g_all", "name": "Everyone at Bluefin", "kind": "org", "team": "", "temporary": False},
              {"id": "g_billing", "name": "Billing", "kind": "team", "team": "billing", "temporary": False},
              {"id": "g_ops", "name": "Operations", "kind": "team", "team": "ops", "temporary": False}]
    members = [("g_billing", "g_all"), ("g_ops", "g_all"), ("p_ines", "g_ops"), ("p_dev", "g_ops"), ("p_hana", "g_billing")]
    spaces = [{"id": "sp_bf_all", "name": "Bluefin handbook"}, {"id": "sp_bf_billing", "name": "Billing"}]
    docs = [{"id": "d_bf_hours", "title": "Clinic hours", "kind": "policy", "space": "sp_bf_all", "owner": "p_ines", "updated": "2026-05-01", "intended": []},
            {"id": "d_bf_rates", "title": "Insurer rates 2026", "kind": "spreadsheet", "space": "sp_bf_billing", "owner": "p_hana", "updated": "2026-02-01", "intended": ["g_billing"]}]
    sections = [{"id": "d_bf_hours__0", "doc": "d_bf_hours", "label": "Clinic hours", "text": "Bluefin clinics open 8am to 8pm, Monday to Saturday.", "restricted": False},
                {"id": "d_bf_rates__0", "doc": "d_bf_rates", "label": "Insurer rates", "text": "Bluefin's negotiated insurer rate for a standard visit is ₹1,450.", "restricted": False}]
    grants = [{"who": "g_all", "target": "sp_bf_all", "label": "Space", "by": "Ines Moreau", "at": "2025-01-05", "reason": "Handbook"},
              {"who": "g_billing", "target": "sp_bf_billing", "label": "Space", "by": "Ines Moreau", "at": "2025-01-05", "reason": "Billing team"}]
    return {"tenant": "bluefin", "company": "Bluefin Health", "people": people, "agents": [], "groups": groups,
            "members": members, "spaces": spaces, "docs": docs, "sections": sections, "grants": grants,
            "customers": [], "mentions": [], "decisions": [], "episodes": [], "case": None}


# --------------------------------------------------------------------------------------
# Loading into FalkorDB
# --------------------------------------------------------------------------------------

def _chunks(items, n=200):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def load(spec: dict, graph_name: str | None = None) -> None:
    name = graph_name or spec["tenant"]
    g = db.graph(name)
    if name in db.graph_names():
        g.delete()
        g = db.graph(name)

    # Indexes first, so the MATCHes below use them.
    for label in ["Principal", "Space", "Doc", "Section", "Customer", "Case", "Decision", "Episode", "Note"]:
        g.create_node_range_index(label, "id")
    g.create_node_fulltext_index("Section", "text", "label")

    q = db.rows
    for chunk in _chunks(spec["people"]):
        q(g, "UNWIND $rows AS r CREATE (:Person:Principal {id:r.id, name:r.name, title:r.title, team:r.team, "
             "level:r.level, external:r.external, moved_from:r.moved_from, moved_at:r.moved_at})",
          {"rows": [{**{"moved_from": None, "moved_at": None}, **p} for p in chunk]})
    if spec["agents"]:
        q(g, "UNWIND $rows AS r CREATE (:Agent:Principal {id:r.id, name:r.name, role:r.role})", {"rows": spec["agents"]})
    q(g, "UNWIND $rows AS r CREATE (:Group:Principal {id:r.id, name:r.name, kind:r.kind, team:r.team, temporary:r.temporary})",
      {"rows": spec["groups"]})
    q(g, "UNWIND $rows AS r CREATE (:Space {id:r.id, name:r.name})", {"rows": spec["spaces"]})
    q(g, "UNWIND $rows AS r CREATE (:Customer {id:r.id, name:r.name})", {"rows": spec["customers"]}) if spec["customers"] else None

    for chunk in _chunks([{"a": a, "b": b} for a, b in spec["members"]]):
        q(g, "UNWIND $rows AS r MATCH (a:Principal {id:r.a}), (b:Principal {id:r.b}) CREATE (a)-[:MEMBER_OF]->(b)",
          {"rows": chunk})

    q(g, "UNWIND $rows AS r MATCH (s:Space {id:r.space}) "
         "CREATE (d:Doc {id:r.id, title:r.title, kind:r.kind, space:r.space, owner:r.owner, updated:r.updated, intended:r.intended})-[:IN]->(s)",
      {"rows": spec["docs"]})
    q(g, "UNWIND $rows AS r MATCH (d:Doc {id:r.id}), (p:Person {id:r.owner}) CREATE (p)-[:OWNS]->(d)", {"rows": spec["docs"]})
    for chunk in _chunks(spec["sections"]):
        q(g, "UNWIND $rows AS r MATCH (d:Doc {id:r.doc}) "
             "CREATE (:Section {id:r.id, doc:r.doc, label:r.label, text:r.text, restricted:r.restricted})-[:PART_OF]->(d)",
          {"rows": chunk})
    if spec["mentions"]:
        q(g, "UNWIND $rows AS r MATCH (s:Section {id:r.s}), (c:Customer {id:r.c}) CREATE (s)-[:MENTIONS]->(c)",
          {"rows": [{"s": s, "c": c} for s, c in spec["mentions"]]})

    case = spec.get("case")
    if case:
        q(g, "MATCH (sp:Space {id:$space}), (c:Customer {id:$customer}), (t:Doc {id:$ticket}) "
             "CREATE (k:Case {id:$id, title:$title, status:'new', claimed_by:''})-[:IN]->(sp), (k)-[:ABOUT]->(c), (k)-[:FROM_TICKET]->(t)",
          case)

    by_label = {}
    for gr in spec["grants"]:
        by_label.setdefault(gr["label"], []).append(gr)
    for label, items in by_label.items():
        q(g, f"UNWIND $rows AS r MATCH (w:Principal {{id:r.who}}), (t:{label} {{id:r.target}}) "
             "CREATE (w)-[:CAN_READ {granted_by:r.by, granted_at:r.at, reason:r.reason}]->(t)",
          {"rows": items})

    for d in spec["decisions"]:
        q(g, "MATCH (p:Person {id:$made_by}), (src:Doc {id:$source}), (doc:Doc {id:$documented_in}) "
             "CREATE (p)-[:MADE]->(x:Decision {id:$id, summary:$summary, date:$date})-[:DECIDED_IN]->(src), (doc)-[:DOCUMENTS]->(x)",
          d)

    for i, e in enumerate(spec["episodes"]):
        q(g, "MATCH (o:Principal {id:$owner}) CREATE (o)-[:REMEMBERS]->(e:Episode {id:$id, kind:$kind, text:$text, ts:$ts}) "
             "WITH e UNWIND $customers AS cid MATCH (c:Customer {id:cid}) CREATE (e)-[:MENTIONS]->(c)",
          {**e, "id": f"ep_seed_{i}"})


def load_all() -> None:
    for t in config.TENANTS:
        load(build_spec(t))


def ensure_loaded() -> None:
    names = set(db.graph_names())
    for t in config.TENANTS:
        if t not in names:
            load(build_spec(t))


# --------------------------------------------------------------------------------------
# Ground truth computed in plain Python (no database), used by tests and the benchmark
# --------------------------------------------------------------------------------------

def principal_closure(spec: dict, pid: str, max_hops: int = config.MAX_HOPS) -> set[str]:
    parents = {}
    for a, b in spec["members"]:
        parents.setdefault(a, []).append(b)
    seen, frontier = {pid}, deque([(pid, 0)])
    while frontier:
        node, d = frontier.popleft()
        if d >= max_hops:
            continue
        for p in parents.get(node, []):
            if p not in seen:
                seen.add(p)
                frontier.append((p, d + 1))
    return seen


def expected_targets(spec: dict, pid: str, flat: bool = False) -> set[str]:
    principals = principal_closure(spec, pid, max_hops=1 if flat else config.MAX_HOPS)
    return {gr["target"] for gr in spec["grants"] if gr["who"] in principals}


def expected_readable_sections(spec: dict, pid: str) -> set[str]:
    targets = expected_targets(spec, pid)
    doc_space = {d["id"]: d["space"] for d in spec["docs"]}
    out = set()
    for s in spec["sections"]:
        doc_ok = s["doc"] in targets or doc_space[s["doc"]] in targets
        if s["id"] in targets or (not s["restricted"] and doc_ok):
            out.add(s["id"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Load the synthetic companies into FalkorDB")
    ap.add_argument("--tenant", choices=list(config.TENANTS), help="load one tenant (default: all)")
    args = ap.parse_args()
    if args.tenant:
        load(build_spec(args.tenant))
    else:
        load_all()
    for t in ([args.tenant] if args.tenant else config.TENANTS):
        n = db.rows(db.graph(t), "MATCH (n) RETURN count(n)", ro=True)[0][0]
        print(f"{t}: {n} nodes")


if __name__ == "__main__":
    main()
