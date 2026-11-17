"""Language tests: lexer, parser recovery, semantic checker, validator, graph."""
from pathlib import Path

import pytest

from specforge.core import ast_nodes as A
from specforge.core.diagnostics import Diagnostic
from specforge.core.lexer import tokenize
from specforge.core.parser import parse
from specforge.core.semantic import analyze
from specforge.core.state_machine import build_state_graph, render_svg
from specforge.core.validator import validate
from specforge.core.nodes import build_index
from specforge.domain import counts as requirement_counts, load_requirements

ROOT = Path(__file__).resolve().parent.parent


def test_requirement_catalogue_meets_the_brief():
    counts = requirement_counts()
    assert counts["total"] >= 20
    assert counts["exceptions"] >= 6
    assert counts["boundary"] >= 4
    ids = [item.id for item in load_requirements()]
    assert len(ids) == len(set(ids))


def test_spec_parses_without_errors(program):
    parsed = parse(program.source, "spec")
    assert parsed.ok
    assert len(program.entities) >= 10
    assert len(program.rules) >= 12
    assert len(program.states) >= 2
    assert len(program.roles) >= 3
    assert len(program.consts) >= 5
    assert len(program.invariants) >= 8
    assert len(program.scenarios) >= 6


def test_time_dependent_rules_exist(program):
    time_names = {"BRI-02", "BRI-04", "BRI-05", "BRI-06", "BRI-08", "BRI-09", "BRI-10"}
    assert time_names <= {rule.name for rule in program.rules}


def test_parser_collects_exactly_five_errors():
    source = (ROOT / "specs" / "broken5.sforge").read_text(encoding="utf-8")
    parsed = parse(source, "broken5.sforge")
    errors = [d for d in parsed.diagnostics if d.severity == "error"]
    assert len(errors) == 5
    # every diagnostic has a usable source position
    for diagnostic in errors:
        assert diagnostic.line >= 1 and diagnostic.col >= 1
        assert "broken5.sforge:" in diagnostic.format()


def test_parser_recovers_and_keeps_later_declarations():
    source = (ROOT / "specs" / "broken5.sforge").read_text(encoding="utf-8")
    parsed = parse(source, "broken5.sforge")
    # the invalid `widget` declaration is followed by a valid state machine
    assert parsed.program.state("S") is not None
    assert parsed.program.entity("A") is not None


def test_lexer_reports_position_of_unexpected_character():
    tokens, diagnostics = tokenize("spec X version 1;\nentity A { id: @; }", "x")
    assert diagnostics
    assert diagnostics[0].code == "E002"
    assert diagnostics[0].line == 2
    assert diagnostics[0].col == 16


def test_lexer_requirement_and_rule_identifiers_are_single_tokens():
    tokens, diagnostics = tokenize("link R-001, BRI-04, CR-012, T-060;", "x")
    values = [token.value for token in tokens]
    assert "R-001" in values
    assert "BRI-04" in values
    assert "CR-012" in values
    assert "T-060" in values
    assert not diagnostics


def test_semantic_checker_returns_three_errors():
    source = (ROOT / "specs" / "semantic3.sforge").read_text(encoding="utf-8")
    parsed = parse(source, "semantic3.sforge")
    assert parsed.ok
    semantic = analyze(parsed.program)
    errors = [d for d in semantic.diagnostics if d.severity == "error"]
    assert len(errors) == 3
    codes = {d.code for d in errors}
    assert {"E101", "E105", "E104"} <= codes


def test_validator_detects_conflicting_rules():
    source = """
spec Conflict version 1;
entity A { id: Identifier; value: Int; }
rule X priority 5 {
  when a.value > 0
  then { a.value := 1; }
}
rule Y priority 5 {
  when a.value > 0
  then { a.value := 2; }
}
"""
    parsed = parse(source, "conflict")
    semantic = analyze(parsed.program)
    index = build_index(parsed.program, semantic.model)
    report = validate(semantic, index)
    codes = {d.code for d in report.diagnostics}
    assert "E131" in codes


def test_validator_detects_impossible_literal_assignment():
    source = """
spec Bad version 1;
entity A { id: Identifier; battery: Int [0..100]; }
rule X {
  when a.battery >= 0
  then { a.battery := 200; }
}
"""
    parsed = parse(source, "bad")
    semantic = analyze(parsed.program)
    index = build_index(parsed.program, semantic.model)
    report = validate(semantic, index)
    assert any(d.code == "E132" for d in report.diagnostics)


def test_semantic_reports_unreachable_state():
    source = """
spec Unreachable version 1;
enum S { a, b, ghost }
entity E { id: Identifier; state: State<S> = a; }
state S {
  initial a;
  a -> b : go;
}
"""
    parsed = parse(source, "unreachable")
    semantic = analyze(parsed.program)
    warnings = [d for d in semantic.diagnostics if d.code == "W001"]
    assert any("ghost" in d.message for d in warnings)


def test_semantic_detects_rule_dependency_cycle():
    source = """
spec Cycle version 1;
entity A { id: Identifier; value: Int; }
rule A1 {
  when a.value > 0
  then { apply A2; }
}
rule A2 {
  when a.value > 0
  then { apply A1; }
}
"""
    parsed = parse(source, "cycle")
    assert parsed.ok
    semantic = analyze(parsed.program)
    assert any(d.code == "E118" for d in semantic.diagnostics)


def test_state_machine_layout_and_cycles(program, semantic):
    state = next(item for item in program.states if item.name == "RentalState")
    graph = build_state_graph(state, semantic.model.enums["RentalState"])
    assert graph.initial == "draft"
    assert graph.cycles
    assert all(0 <= node.x <= graph.width for node in graph.nodes)
    assert all(0 <= node.y <= graph.height for node in graph.nodes)
    svg = render_svg(graph, "RentalState")
    assert svg.startswith("<svg")
    assert "closed" in svg


def test_state_machine_marks_unreachable_states(program, semantic):
    state = next(item for item in program.states if item.name == "ScooterState")
    graph = build_state_graph(state, list(semantic.model.enums["ScooterState"]))
    assert graph.unreachable == []
    # add a member that no edge points to
    members = list(semantic.model.enums["ScooterState"]) + ["ghost"]
    graph = build_state_graph(state, members)
    assert "ghost" in graph.unreachable
    ghost = graph.node("ghost")
    assert ghost is not None and not ghost.reachable


def test_validation_stats(validation):
    assert validation.ok
    assert validation.stats["entities"] >= 10
    assert validation.stats["nodes"] >= 150
    assert validation.stats["transitions"] >= 15
    assert validation.stats["errors"] == 0


def test_node_index_has_dependencies_and_hashes(index):
    rule = index.get("rule:BRI-04")
    assert rule is not None
    assert rule.deps
    assert "field:Rental.minutesLate" in rule.deps
    assert "const:graceMinutes" in rule.deps
    assert len(rule.content_hash) == 64
    assert index.get("transition:ScooterState:available:reserve") is not None
    assert index.dependents({"const:graceMinutes"}) >= {"rule:BRI-04"}


def test_requirements_are_linked_to_spec_nodes(index):
    for number in range(1, 21):
        requirement_id = f"R-{number:03d}"
        assert index.requirements.get(requirement_id), requirement_id
