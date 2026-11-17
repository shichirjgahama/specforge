"""Performance checks required by section 8.7."""
import time

from specforge.core.impact import ChangeRequest, analyze_impact
from specforge.core.parser import parse
from specforge.runtime.runner import run_tests


def build_large_spec(lines: int = 1000) -> str:
    parts = ["spec Large version 1;"]
    parts.append("const minBattery: Int = 20;")
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


def test_parse_1000_lines_under_100_ms():
    source = build_large_spec(1000)
    assert len(source.splitlines()) >= 1000
    parse(source, "large.sforge")  # warm up
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        parsed = parse(source, "large.sforge")
        timings.append((time.perf_counter() - started) * 1000)
    assert parsed.ok
    assert min(timings) < 100.0, timings


def test_impact_analysis_under_one_second(program, index, cases):
    cr = ChangeRequest(id="CR-PERF", title="perf", kind="rule_threshold",
                       description="perf",
                       spec_edits=[{"find": "const minBattery: Int = 20;",
                                    "replace": "const minBattery: Int = 25;"}],
                       target_nodes=("const:minBattery",))
    source = program.source.replace("const minBattery: Int = 20;",
                                    "const minBattery: Int = 25;")
    new_program = parse(source, "perf").program
    started = time.perf_counter()
    plan = analyze_impact(program, new_program, cr, cases)
    elapsed = (time.perf_counter() - started) * 1000
    assert plan.changed_nodes
    assert elapsed < 1000.0, elapsed


def test_full_suite_under_ten_seconds(program, cases):
    started = time.perf_counter()
    summary = run_tests(program, cases)
    elapsed = time.perf_counter() - started
    assert summary.failed == 0
    assert elapsed < 10.0, elapsed
