from ntk import access, brain, seed

G = "northwind"


def test_traversal_matches_python_ground_truth(spec):
    principals = [p["id"] for p in spec["people"]] + [a["id"] for a in spec["agents"]]
    for pid in principals:
        assert access.readable_set(G, pid) == seed.expected_readable_sections(spec, pid), pid


def test_intern_cannot_read_contract_value():
    assert not access.can_read(G, "p_priya", "d_acme_overview__2")
    assert access.can_read(G, "p_priya", "d_acme_overview__0")


def test_finance_head_reads_contract_value_through_nested_groups():
    assert access.can_read(G, "p_meera", "d_acme_overview__2")
    why = access.explain(G, "p_meera", ["d_acme_overview__2"])
    assert why and why["names"][0] == "Meera Iyer"


def test_agent_inherits_through_two_levels():
    # Finance Agent -> Finance AI agents -> Finance, which holds the grant.
    assert access.can_read(G, "a_finance", "d_acme_overview__2")
    assert not access.can_read(G, "a_finance", "d_acme_overview__2", mode="flat")
    assert not access.can_read(G, "a_support", "d_acme_overview__2")


def test_off_mode_leaks_and_graph_mode_does_not():
    q = "What does Acme Corp pay us and when do they renew?"
    safe = brain.ask(G, "p_priya", q, remember=False, use_llm=False)
    assert safe["leaks"] == 0
    assert any(r["id"] == "d_acme_overview__2" for r in safe["redacted"])
    unsafe = brain.ask(G, "p_priya", q, mode="off", remember=False, use_llm=False)
    assert unsafe["leaks"] >= 1


def test_same_question_two_people_two_answers():
    q = "Why did Acme Corp's invoice go up in October?"
    a = brain.ask(G, "p_priya", q, remember=False, use_llm=False)
    b = brain.ask(G, "p_meera", q, remember=False, use_llm=False)
    seen_a = {f["id"] for f in a["facts"]}
    seen_b = {f["id"] for f in b["facts"]}
    assert "d_acme_overview__2" in seen_b and "d_acme_overview__2" not in seen_a


def test_tenants_are_isolated():
    a = brain.ask("bluefin", "p_hana", "Why did Acme Corp's invoice go up?", remember=False, use_llm=False)
    assert not a["facts"]


def test_contractor_reads_board_deck_only_because_of_overshare():
    assert access.can_read(G, "p_contractor_00", "d_board_q3__0")
