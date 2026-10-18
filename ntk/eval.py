"""The proof: switch the graph off and watch what breaks.

For every (asker, question) pair we compare what each access mode shows against ground
truth computed in plain Python from the company spec (seed.expected_readable_sections).

  leak   = shown, but the asker is not allowed to read it
  denial = the asker is allowed and search found it, but it was hidden

Also measured: agreement between FalkorDB's traversal and the Python ground truth over
every principal and section, and latency of the access check under concurrent load.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import access, brain, memory, seed

QUESTIONS = [
    "Why did Acme Corp's invoice go up in October?",
    "What does Acme Corp pay us and when do they renew?",
    "What are the engineering salary bands?",
    "How much runway do we have and are we fundraising?",
    "What is the Globex contract value?",
    "Why don't we retry payments on the client side?",
    "What is our loyalty discount policy?",
    "Who are the key contacts at Acme Corp?",
]


def askers(spec: dict, n_random: int = 40) -> list[str]:
    named = ["p_priya", "p_meera", "p_arjun", "p_ravi", "p_kabir", "p_neha", "p_lena", "p_sam", "p_anika",
             "a_support", "a_finance", "a_sales", "p_contractor_00", "p_contractor_05"]
    rnd = random.Random(7)
    pool = [p["id"] for p in spec["people"] if p["id"] not in named]
    return named + rnd.sample(pool, n_random)


def run(graph_name: str = "northwind", out: str | None = None) -> dict:
    spec = seed.build_spec(graph_name)
    who = askers(spec)
    truth = {pid: seed.expected_readable_sections(spec, pid) for pid in who}
    retrieved = {q: brain.retrieve(graph_name, q)[0] for q in QUESTIONS}
    cat = access.catalog(graph_name)

    results = {}
    for mode in access.MODES:
        leaks = denials = shown = allowed = 0
        for pid in who:
            held = access.grants(graph_name, pid, mode)
            for q in QUESTIONS:
                for sid in retrieved[q]:
                    ok_truth = sid in truth[pid]
                    ok_mode = access.readable(cat, held, sid, mode)
                    shown += ok_mode
                    allowed += ok_truth
                    leaks += ok_mode and not ok_truth
                    denials += ok_truth and not ok_mode
        pairs = len(who) * len(QUESTIONS)
        results[mode] = {"pairs": pairs, "passages_shown": shown, "leaks": leaks, "wrong_denials": denials,
                         "helpfulness": round(100 * (allowed - denials) / allowed, 1) if allowed else 100.0}

    # FalkorDB traversal vs Python ground truth, for every principal and every section.
    principals = [p["id"] for p in spec["people"]] + [a["id"] for a in spec["agents"]]
    agree = total = 0
    for pid in principals:
        got = access.readable_set(graph_name, pid)
        want = seed.expected_readable_sections(spec, pid)
        for sid in cat.sections:
            total += 1
            agree += (sid in got) == (sid in want)
    agreement = round(100 * agree / total, 3)

    # Latency of the full access check (one traversal), sequential and under 8 threads.
    sample = [random.Random(3).choice(principals) for _ in range(300)]
    seq = [access.timed_grants(graph_name, p) for p in sample]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(8) as ex:
        par = list(ex.map(lambda p: access.timed_grants(graph_name, p), sample))
    wall = time.perf_counter() - t0

    # Concurrent memory writes from many agents at once.
    t1 = time.perf_counter()
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda i: memory.remember(graph_name, principals[i % len(principals)], "bench", f"bench write {i}"), range(200)))
    writes_wall = time.perf_counter() - t1
    memory.forget_run_artifacts(graph_name, ["bench"])

    report = {
        "graph": graph_name,
        "askers": len(who), "questions": len(QUESTIONS),
        "modes": results,
        "agreement_with_ground_truth_pct": agreement, "checked_pairs": total,
        "latency_ms": {"p50": round(statistics.median(seq), 2), "p95": round(sorted(seq)[int(len(seq) * 0.95)], 2),
                       "concurrent_p50": round(statistics.median(par), 2),
                       "concurrent_checks_per_sec": round(len(sample) / wall, 1)},
        "memory_writes_per_sec": round(200 / writes_wall, 1),
    }
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def markdown(report: dict) -> str:
    m = report["modes"]
    rows = [("Graph traversal (Need-to-Know)", m["graph"]), ("Flat list (direct groups only)", m["flat"]),
            ("No access check (plain chatbot)", m["off"])]
    lines = ["| Access check | Leaks | Wrong denials | Helpfulness |", "|---|---|---|---|"]
    for name, r in rows:
        lines.append(f"| {name} | {r['leaks']} | {r['wrong_denials']} | {r['helpfulness']}% |")
    lat = report["latency_ms"]
    lines += ["", f"{report['askers']} askers × {report['questions']} questions. "
              f"Traversal agrees with the independent Python ground truth on "
              f"{report['agreement_with_ground_truth_pct']}% of {report['checked_pairs']} (principal, passage) pairs.",
              f"Access check latency: p50 {lat['p50']} ms, p95 {lat['p95']} ms; "
              f"{lat['concurrent_checks_per_sec']} checks/s across 8 threads; "
              f"{report['memory_writes_per_sec']} concurrent memory writes/s."]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="northwind")
    ap.add_argument("--out", default="results/eval.json")
    args = ap.parse_args()
    seed.ensure_loaded()
    report = run(args.graph, args.out)
    md = markdown(report)
    Path(args.out).with_suffix(".md").write_text(md + "\n", encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
