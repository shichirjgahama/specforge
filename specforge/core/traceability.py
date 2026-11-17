"""Traceability matrix and coverage diagnostics.

Requirement -> spec node -> test case -> latest result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .nodes import SpecIndex


BEHAVIORAL_KINDS = {"rule", "transition", "invariant"}


@dataclass
class RequirementCoverage:
    requirement_id: str
    title: str = ""
    nodes: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    uncovered_nodes: list[str] = field(default_factory=list)
    status: str = "uncovered"
    last_result: str = ""
    total_runs: int = 0

    def to_dict(self) -> dict:
        return {
            "requirement_id": self.requirement_id, "title": self.title,
            "nodes": self.nodes, "tests": self.tests,
            "uncovered_nodes": self.uncovered_nodes, "status": self.status,
            "last_result": self.last_result, "total_runs": self.total_runs,
        }


@dataclass
class TraceabilityReport:
    rows: list[RequirementCoverage]
    orphan_tests: list[str]
    dead_nodes: list[str]
    tests_without_requirement: list[str]
    tests_with_unknown_requirement: list[str]
    tests_with_unknown_node: list[str]
    coverage_percent: float
    summary: dict = field(default_factory=dict)

    @property
    def issues(self) -> list[str]:
        result = []
        if self.tests_without_requirement:
            result.append("tests without requirements: " +
                          ", ".join(self.tests_without_requirement))
        if self.tests_with_unknown_requirement:
            result.append("tests referencing unknown requirements: " +
                          ", ".join(self.tests_with_unknown_requirement))
        if self.dead_nodes:
            result.append("spec nodes not covered by tests: " +
                          ", ".join(self.dead_nodes[:12]))
        partial = [row.requirement_id for row in self.rows
                   if row.status in ("partial", "no_spec", "uncovered")]
        if partial:
            result.append("requirements with incomplete coverage: " +
                          ", ".join(partial))
        return result

    def to_dict(self) -> dict:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "orphan_tests": self.orphan_tests,
            "dead_nodes": self.dead_nodes,
            "tests_without_requirement": self.tests_without_requirement,
            "tests_with_unknown_requirement": self.tests_with_unknown_requirement,
            "tests_with_unknown_node": self.tests_with_unknown_node,
            "coverage_percent": round(self.coverage_percent, 2),
            "summary": self.summary,
            "issues": self.issues,
        }


def build_traceability(index: SpecIndex, requirements: Iterable[dict],
                       tests: Iterable, latest_results: Optional[dict] = None
                       ) -> TraceabilityReport:
    requirements = list(requirements)
    tests = list(tests)
    latest_results = latest_results or {}
    requirement_ids = {item["id"] for item in requirements}

    node_to_tests: dict[str, list[str]] = {}
    for test in tests:
        for node_id in test.nodes:
            node_to_tests.setdefault(node_id, []).append(test.id)
    test_by_id = {test.id: test for test in tests}

    rows: list[RequirementCoverage] = []
    covered_requirements = 0
    for requirement in requirements:
        requirement_id = requirement["id"]
        nodes = sorted(index.requirements.get(requirement_id, []))
        behavioral = [node_id for node_id in nodes
                      if index.nodes[node_id].kind in BEHAVIORAL_KINDS]
        direct_tests = sorted(test.id for test in tests
                              if requirement_id in test.requirements)
        via_nodes = sorted({test_id for node_id in nodes
                            for test_id in node_to_tests.get(node_id, [])})
        test_ids = sorted(set(direct_tests) | set(via_nodes))
        uncovered_nodes = sorted(node_id for node_id in behavioral
                                 if not node_to_tests.get(node_id))
        if not nodes:
            status = "no_spec"
        elif not test_ids:
            status = "uncovered"
        elif uncovered_nodes:
            status = "partial"
        else:
            status = "covered"
        if status == "covered":
            covered_requirements += 1
        last_result = ""
        total_runs = 0
        for test_id in test_ids:
            result = latest_results.get(test_id)
            if result:
                total_runs += 1
                if result.get("status") == "failed":
                    last_result = "failed"
                elif last_result != "failed":
                    last_result = "passed"
        rows.append(RequirementCoverage(
            requirement_id=requirement_id,
            title=requirement.get("title", ""),
            nodes=nodes, tests=test_ids,
            uncovered_nodes=uncovered_nodes, status=status,
            last_result=last_result, total_runs=total_runs,
        ))

    orphan_tests = sorted(test.id for test in tests if not test.requirements)
    unknown_requirement = sorted(
        {requirement_id for test in tests for requirement_id in test.requirements
         if requirement_id not in requirement_ids})
    unknown_nodes = sorted(
        {node_id for test in tests for node_id in test.nodes
         if node_id not in index.nodes})
    dead_nodes = sorted(
        node_id for node_id in index.nodes
        if index.nodes[node_id].kind in BEHAVIORAL_KINDS
        and not node_to_tests.get(node_id)
        and not (index.nodes[node_id].requirements))

    coverage = 100.0 * covered_requirements / max(1, len(requirements))
    summary = {
        "requirements": len(requirements),
        "covered": covered_requirements,
        "partial": sum(1 for row in rows if row.status == "partial"),
        "uncovered": sum(1 for row in rows if row.status == "uncovered"),
        "no_spec": sum(1 for row in rows if row.status == "no_spec"),
        "tests": len(tests),
        "spec_nodes": len(index.nodes),
        "dead_nodes": len(dead_nodes),
        "orphan_tests": len(orphan_tests),
        "coverage_percent": round(coverage, 2),
    }
    return TraceabilityReport(
        rows=rows, orphan_tests=orphan_tests, dead_nodes=dead_nodes,
        tests_without_requirement=orphan_tests,
        tests_with_unknown_requirement=unknown_requirement,
        tests_with_unknown_node=unknown_nodes,
        coverage_percent=coverage, summary=summary,
    )
