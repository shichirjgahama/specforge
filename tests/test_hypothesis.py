"""Hypothesis tests with three custom, DSL aware strategies."""
from pathlib import Path

from hypothesis import HealthCheck, given, settings

from specforge.core.nodes import build_index
from specforge.core.parser import parse
from specforge.core.properties import check_all
from specforge.core.semantic import analyze
from specforge.core.strategies import st_cr, st_dsl_program, st_invalid_transition

ROOT = Path(__file__).resolve().parent.parent
SPEC = (ROOT / "specs" / "scooter_share.sforge").read_text(encoding="utf-8")
SETTINGS = settings(max_examples=12, deadline=None,
                    suppress_health_check=[HealthCheck.too_slow])


@SETTINGS
@given(st_dsl_program())
def test_generated_dsl_programs_are_valid(source: str):
    parsed = parse(source, "generated.sforge")
    assert parsed.ok, [(d.code, d.message) for d in parsed.diagnostics]
    semantic = analyze(parsed.program)
    assert semantic.ok, [(d.code, d.message) for d in semantic.diagnostics
                         if d.severity == "error"]
    index = build_index(parsed.program, semantic.model)
    assert any(node.kind == "rule" for node in index.nodes.values())
    assert any(node.kind == "transition" for node in index.nodes.values())


@SETTINGS
@given(st_invalid_transition())
def test_generated_invalid_transitions_are_detected(transition: dict):
    source = f"""
spec Bad version 1;
enum S {{ available, reserved, rented }}
entity E {{
  id: Identifier;
  state: State<S> = available;
}}
state S {{
  initial available;
  available -> reserved : reserve;
  reserved -> rented : rent;
  {transition['source']} -> {transition['target']} : {transition['event']};
}}
"""
    parsed = parse(source, "bad_transition.sforge")
    assert parsed.ok
    semantic = analyze(parsed.program)
    codes = {d.code for d in semantic.diagnostics}
    assert "E106" in codes or "E117" in codes


@SETTINGS
@given(st_cr())
def test_generated_change_requests_keep_all_properties(cr):
    assert 1 <= len(cr.target_nodes) <= 3
    new_source = cr.apply_to_source(SPEC)
    parsed = parse(new_source, "after_cr.sforge")
    assert parsed.ok, [(d.code, d.message) for d in parsed.diagnostics]
    semantic = analyze(parsed.program)
    assert semantic.ok, [(d.code, d.message) for d in semantic.diagnostics
                         if d.severity == "error"]
    report = check_all(parsed.program)
    assert report["ok"], [item for item in report["results"] if not item["ok"]]
