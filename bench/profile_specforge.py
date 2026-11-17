"""Profiling and before/after proofs for two optimizations.

Run: python bench/profile_specforge.py
Writes bench/results.json and bench/profile.txt.
"""
from __future__ import annotations

import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from specforge.core.impact import ChangeRequest, analyze_impact
from specforge.core.lexer import tokenize
from specforge.core.nodes import build_index
from specforge.core.parser import parse
from specforge.core.semantic import analyze
from specforge.runtime.codegen import generate_tests
from specforge.runtime.runner import run_tests


def build_large_spec(lines: int = 1000) -> str:
    parts = ["spec Large version 1;", "const minBattery: Int = 20;"]
    index = 0
    while len("\n".join(parts).splitlines()) < lines:
        index += 1
        parts.append(f"""
enum E{index} {{ a, b, c }}
entity X{index} {{
  id: Identifier;
  state: State<E{index}> = a;
  battery: Int [0..100] = 50;
}}
rule R{index} {{
  when x{index}.battery >= minBattery
  then {{ x{index}.state := b; }}
  else {{ x{index}.state := a; }}
  ensures x{index}.battery >= 0;
}}
""")
    return "\n".join(parts)


MULTI = ("->", ":=", "==", "!=", "<=", ">=", "&&", "||", "..")


def naive_lex(source: str):
    """Baseline lexer: char by char scanning and position recount per token.

    This is the straightforward implementation the optimized lexer replaces:
    no compiled identifier/number regex and no incremental line/column
    counters, so every token pays a full string scan for its position.
    """
    tokens = []
    index = 0
    length = len(source)
    while index < length:
        ch = source[index]
        if ch in " \t\r\n":
            index += 1
            continue
        start = index
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = length if end < 0 else end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue
        if ch == '"':
            index += 1
            while index < length and source[index] != '"':
                if source[index] == "\\" and index + 1 < length:
                    index += 2
                else:
                    index += 1
            index += 1
        elif ch.isalpha() or ch == "_":
            while index < length and (source[index].isalnum() or source[index] == "_"):
                index += 1
        elif ch.isdigit():
            while index < length and source[index].isdigit():
                index += 1
        else:
            for symbol in MULTI:
                if source.startswith(symbol, index):
                    index += len(symbol)
                    break
            else:
                index += 1
        text = source[start:index]
        line = source.count("\n", 0, start) + 1
        col = start - source.rfind("\n", 0, start)
        tokens.append((text, line, col))
    return tokens


def bench(label, function, repeats=5):
    function()  # warm up
    timings = []
    last = None
    for _ in range(repeats):
        started = time.perf_counter()
        last = function()
        timings.append((time.perf_counter() - started) * 1000.0)
    return {"label": label, "best_ms": round(min(timings), 3),
            "average_ms": round(sum(timings) / len(timings), 3),
            "result": last}


def main() -> int:
    source = build_large_spec(1000)
    line_count = len(source.splitlines())

    # ---------------------------------------------------------- optimization 1
    naive_lexer_bench = bench("naive char lexer", lambda: naive_lex(source))
    optimized_lexer_bench = bench("optimized lexer", lambda: tokenize(source, "large"))
    lex_speedup = (naive_lexer_bench["best_ms"] /
                   max(0.0001, optimized_lexer_bench["best_ms"]))
    if naive_lexer_bench["result"] and optimized_lexer_bench["result"]:
        optimized_tokens = optimized_lexer_bench["result"][0]
        assert len(naive_lexer_bench["result"]) == len(optimized_tokens) - 1

    parse_result = bench("parse 1000 lines", lambda: parse(source, "large"))
    parsed = parse(source, "large")
    if not parsed.ok:
        print("large spec has parse errors; benchmark aborted", file=sys.stderr)
        return 1

    # ---------------------------------------------------------- optimization 2
    spec_source = (ROOT / "specs" / "scooter_share.sforge").read_text(encoding="utf-8")
    program = parse(spec_source, "scooter_share.sforge").program
    semantic = analyze(program)
    index = build_index(program, semantic.model)
    cases = generate_tests(program, index)

    requirements = [{"id": f"R-{n:03d}"} for n in range(1, 101)]
    for requirement in requirements[20:]:
        index.requirements.setdefault(requirement["id"], [])

    cr = ChangeRequest(
        id="CR-BENCH", title="benchmark", kind="rule_threshold", description="",
        spec_edits=[{"find": "const minBattery: Int = 20;",
                     "replace": "const minBattery: Int = 25;"}],
        target_nodes=("const:minBattery",),
    )
    changed_source = spec_source.replace("const minBattery: Int = 20;",
                                         "const minBattery: Int = 25;")
    changed_program = parse(changed_source, "changed").program
    changed_index = build_index(changed_program, analyze(changed_program).model)

    impact_bench = bench(
        "impact on 174 nodes, 60 tests",
        lambda: analyze_impact(program, changed_program, cr, cases,
                               old_index=index, new_index=changed_index))
    impact_plan = impact_bench["result"]
    impact_ms = impact_bench["best_ms"]

    probes = [{"const:minBattery"}, {"const:graceMinutes"}, {"rule:BRI-04"},
              {"entity:Scooter"}, {"field:Rental.state"}]
    probes = (probes * 20)[:100]

    def cached_queries():
        return [index.dependents(probe) for probe in probes]

    def naive_queries():
        results = []
        for probe in probes:
            reverse: dict[str, set[str]] = {nid: set() for nid in index.nodes}
            for node in index.nodes.values():
                for dep in node.deps:
                    if dep in reverse:
                        reverse[dep].add(node.id)
            affected = set()
            stack = list(probe)
            while stack:
                node_id = stack.pop()
                if node_id in affected:
                    continue
                affected.add(node_id)
                stack.extend(reverse.get(node_id, ()))
            results.append(affected)
        return results

    cached_bench = bench("100 closure queries, cached reverse index",
                         cached_queries, repeats=20)
    naive_bench = bench("100 closure queries, reverse rebuilt per query",
                        naive_queries, repeats=20)
    assert cached_bench["result"] == naive_bench["result"]
    closure_speedup = naive_bench["best_ms"] / max(0.0001, cached_bench["best_ms"])

    # ------------------------------------------------------------- test suite
    suite_bench = bench("60 tests", lambda: run_tests(program, cases), repeats=3)
    summary = suite_bench["result"]

    # -------------------------------------------------------------- cProfile
    profiler = cProfile.Profile()
    profiler.enable()
    run_tests(program, cases)
    parse(source, "large")
    analyze(program)
    profiler.disable()
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
    stats.print_stats(25)
    (ROOT / "bench" / "profile.txt").write_text(stream.getvalue(), encoding="utf-8")

    results = {
        "lines": line_count,
        "optimization_1_lexer": {
            "naive_ms": naive_lexer_bench["best_ms"],
            "optimized_ms": optimized_lexer_bench["best_ms"],
            "speedup": round(lex_speedup, 2),
            "tokens": len(naive_lexer_bench["result"]),
        },
        "parse_1000_lines_ms": parse_result["best_ms"],
        "optimization_2_reverse_index": {
            "naive_queries_ms": naive_bench["best_ms"],
            "cached_queries_ms": cached_bench["best_ms"],
            "speedup": round(closure_speedup, 2),
            "queries": len(probes),
            "requirements": len(requirements),
            "tests": len(cases),
            "nodes": len(changed_index.nodes),
        },
        "impact": {
            "single_impact_ms": round(impact_ms, 3),
            "selected_tests": len(impact_plan.tests),
            "changed_nodes": len(impact_plan.changed_nodes),
            "affected_nodes": len(impact_plan.affected_nodes),
        },
        "suite": {
            "passed": summary.passed,
            "failed": summary.failed,
            "duration_ms": round(suite_bench["best_ms"], 3),
            "digest": summary.digest,
        },
        "limits": {
            "parse_under_100_ms": parse_result["best_ms"] < 100.0,
            "impact_under_1_s": impact_ms < 1000.0,
            "suite_under_10_s": suite_bench["best_ms"] < 10_000.0,
        },
    }
    (ROOT / "bench" / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
