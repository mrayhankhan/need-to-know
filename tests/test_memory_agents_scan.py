from ntk import access, agents, memory, scan

G = "northwind"


def test_memory_is_private_by_graph_shape():
    memory.remember(G, "p_meera", "note", "secret test memory", ["c_acme"])
    mine = memory.recall(G, "p_meera", limit=50)
    assert any(m["text"] == "secret test memory" for m in mine)
    theirs = memory.recall(G, "p_priya", limit=50)
    assert all(m["text"] != "secret test memory" for m in theirs)
    p = memory.peek(G, "p_priya", "p_meera")
    assert p["owner_has"] >= 1 and p["asker_can_reach"] == 0


def test_handoff_keeps_finance_note_out_of_reply():
    r = agents.run(G, "graph")
    assert not r["leaks"]
    notes = {n["id"]: n for n in r["view"]["notes"]}
    assert notes["n2"]["visible"] is False and notes["n3"]["visible"] is True
    fin = agents.view(G, "a_finance")
    assert {n["id"] for n in fin["notes"] if n["visible"]} == {"n1", "n2", "n3"}
    assert agents.approve(G, "p_sam")["ok"]


def test_handoff_without_access_checks_leaks():
    r = agents.run(G, "off")
    assert r["leaks"]
    assert not agents.approve(G, "p_sam")["ok"]
    agents.run(G, "graph")


def test_scan_finds_planted_problems():
    s = scan.scan(G)
    titles = {f["title"] for f in s["overshared"]}
    assert "Salary bands 2026" in titles and "Q3 board update" in titles
    salary = next(f for f in s["overshared"] if f["title"] == "Salary bands 2026")
    assert salary["culprit"]["grantee"] == "g_drive_migration_2023"
    assert salary["actual_readers"] > 200 and salary["intended_readers"] <= 5
    assert any(d["person"] == "p_ravi" for d in s["drift"])


def test_fix_is_tested_on_a_fork_then_applied(fresh):
    s = scan.scan(G)
    salary = next(f for f in s["overshared"] if f["title"] == "Salary bands 2026")
    t = scan.test_fix(G, salary["fix"], salary["doc"])
    assert t["passed"] and t["intended_kept"] and t["readers_after"] < 10
    # the fork changed nothing live
    assert access.can_read(G, "p_priya", "d_salary_bands__0")
    out = scan.apply_fix(G, salary["fix"], "p_neha", "test")
    access.reset_cache(G)
    assert out["changed_edges"] == 1
    assert not access.can_read(G, "p_priya", "d_salary_bands__0")
    assert access.can_read(G, "p_neha", "d_salary_bands__0")
    assert scan.audit(G)[0]["by"] == "Neha Shah"
