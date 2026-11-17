"""Traceability and impact analysis tests, including the minimality proof."""
import pytest

from specforge.core.impact import ChangeRequest, analyze_impact


def test_traceability_matrix(service):
    service.run_all_tests()
    report = service.traceability()
    assert report.summary["requirements"] == 20
    assert report.summary["tests"] == 60
    assert report.coverage_percent >= 85.0
    assert report.tests_without_requirement == []
    assert report.dead_nodes, "the seed spec intentionally has unused transitions"
    assert any(row.requirement_id == "R-019" and row.status == "covered"
               for row in report.rows)
    assert all(row.nodes for row in report.rows)
    assert all(row.tests for row in report.rows)


def test_latest_run_is_stored(service):
    summary = service.run_all_tests()
    run = service.latest_run()
    assert run is not None
    assert run["passed"] == 60
    assert run["failed"] == 0
    assert run["digest"] == summary.digest
    results = service.repo.run_results(run["id"])
    assert len(results) == 60


@pytest.mark.parametrize("cr_id,expected_failed", [
    ("CR-001", ["T-012", "T-013", "T-028", "T-030"]),
    ("CR-002", ["T-006", "T-022", "T-042", "T-046", "T-047", "T-055"]),
    ("CR-003", ["T-033"]),
])
def test_threshold_change_impact_is_minimal(service, cr_id, expected_failed):
    service.run_all_tests()
    service.reset_spec()
    result = service.apply_change_request(cr_id)
    plan = result["plan"]
    minimality = result["minimality"]
    assert minimality["equal"] is True
    assert minimality["missed"] == []
    assert minimality["subset_failed"] == expected_failed
    assert minimality["full_failed"] == expected_failed
    assert plan["tests"], "impact analysis selected no tests"
    assert len(plan["tests"]) < 60
    assert plan["changed_nodes"]
    assert plan["affected_nodes"]
    assert plan["conflicts"] == []


def test_entity_structure_change_selects_tests_but_keeps_them_green(service):
    service.run_all_tests()
    service.reset_spec()
    result = service.apply_change_request("CR-004")
    minimality = result["minimality"]
    plan = result["plan"]
    assert minimality["equal"] is True
    assert minimality["subset_failed"] == []
    assert minimality["full_failed"] == []
    assert plan["tests"]
    assert any(node.startswith("entity:Rental") or
               node.startswith("field:Rental") for node in plan["affected_nodes"])


def test_requirement_text_only_change_touches_linked_tests(service):
    service.run_all_tests()
    service.reset_spec()
    result = service.apply_change_request("CR-005")
    plan = result["plan"]
    minimality = result["minimality"]
    assert minimality["equal"] is True
    assert minimality["subset_failed"] == []
    assert plan["affected_requirements"] == ["R-003"] or "R-003" in plan["affected_requirements"]
    assert plan["regenerate"] == []
    selected = [case for case in service.tests if case.id in plan["tests"]]
    assert selected
    assert all("R-003" in case.requirements for case in selected)


def test_removed_node_produces_a_conflict():
    from specforge.core.nodes import build_index
    from specforge.core.semantic import analyze
    from specforge.core.parser import parse
    from specforge.core.impact import ChangeRequest
    from specforge.runtime.codegen import TestCase

    old_source = """
spec Old version 1;
entity A { id: Identifier; value: Int; }
rule X {
  when a.value > 0
  then { a.value := 0; }
}
"""
    new_source = """
spec New version 1;
entity A { id: Identifier; value: Int; }
"""
    old_program = parse(old_source, "old").program
    new_program = parse(new_source, "new").program
    old_index = build_index(old_program, analyze(old_program).model)
    new_index = build_index(new_program, analyze(new_program).model)
    case = TestCase(
        id="T-900", kind="scenario", title="touches removed rule",
        requirements=("R-001",), nodes=("rule:X",), setup={}, steps=[],
        expected={}, seed=0,
    )
    cr = ChangeRequest(id="CR-DEL", title="remove rule", kind="rule_threshold",
                       description="removed rule X")
    plan = analyze_impact(old_program, new_program, cr, [case],
                          old_index=old_index, new_index=new_index)
    assert "rule:X" in plan.changed_nodes
    assert any("removed" in conflict for conflict in plan.conflicts)


def test_unchanged_spec_has_empty_impact(program, index, cases):
    cr = ChangeRequest(id="CR-NONE", title="No change", kind="requirement_text",
                       description="nothing")
    plan = analyze_impact(program, program, cr, cases,
                          old_index=index, new_index=index)
    assert plan.changed_nodes == []
    assert plan.affected_nodes == []
    assert plan.tests == []


def test_impact_history_is_persisted(service):
    service.run_all_tests()
    service.reset_spec()
    service.apply_change_request("CR-003")
    history = service.impact_history()
    assert history
    report = history[0]
    assert report["cr_id"] == "CR-003"
    assert report["minimality"]["equal"] is True
    assert report["plan"]["tests"]


def test_spec_versions_are_recorded(service):
    before = len(service.spec_versions())
    service.reset_spec()
    after = len(service.spec_versions())
    assert after == before + 1
    latest = service.repo.latest_spec()
    assert latest["content"]
    nodes = service.repo.spec_nodes(latest["id"])
    assert len(nodes) >= 150
