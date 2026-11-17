"""Change requests and provably minimal impact analysis.

Algorithm
---------
1. Apply the CR edits to the specification source and re-parse it.
2. Compute content hashes for every spec node. Nodes whose hash changed,
   disappeared or appeared are the seeds.
3. Expand the seeds through the reverse dependency graph (a node is affected
   when a node it depends on changed). This is a graph closure, not a text
   search over field names.
4. Requirements edited by the CR are added as documentation seeds; their
   linked nodes and linked tests are selected for review.
5. Select tests whose declared specification nodes intersect the affected
   closure, or whose requirements intersect the affected requirements.
6. Verification runs the selected tests and the full suite on the new
   specification and compares the sets of failed tests. Selection is correct
   when the failed sets are equal.

Step 6 is what makes the claim falsifiable: a noisy analysis that misses a
failing test fails the comparison, an over-selecting one still passes the
failed set equality but is reported with the extra passing tests.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .ast_nodes import Program
from .nodes import SpecIndex, build_index, canonical
from .semantic import analyze


class ChangeRequestError(Exception):
    pass


@dataclass
class ChangeRequest:
    id: str
    title: str
    kind: str
    description: str
    spec_edits: list[dict] = field(default_factory=list)
    requirement_edits: list[dict] = field(default_factory=list)
    target_nodes: tuple[str, ...] = ()
    created_at: str = ""
    status: str = "open"

    def apply_to_source(self, source: str) -> str:
        result = source
        for index, edit in enumerate(self.spec_edits):
            find = edit.get("find", "")
            replace = edit.get("replace", "")
            if not find:
                raise ChangeRequestError(f"edit {index} has no find pattern")
            count = result.count(find)
            if count != 1:
                raise ChangeRequestError(
                    f"edit {index} of {self.id}: pattern occurs {count} times, expected 1")
            result = result.replace(find, replace, 1)
        return result

    def edited_requirement_ids(self) -> list[str]:
        return sorted({edit.get("id", "") for edit in self.requirement_edits
                       if edit.get("id")})

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "kind": self.kind,
            "description": self.description, "spec_edits": self.spec_edits,
            "requirement_edits": self.requirement_edits,
            "target_nodes": list(self.target_nodes),
            "created_at": self.created_at, "status": self.status,
        }

    @staticmethod
    def from_dict(data: dict) -> "ChangeRequest":
        return ChangeRequest(
            id=data["id"], title=data["title"], kind=data.get("kind", "mixed"),
            description=data.get("description", ""),
            spec_edits=data.get("spec_edits", []),
            requirement_edits=data.get("requirement_edits", []),
            target_nodes=tuple(data.get("target_nodes", ())),
            created_at=data.get("created_at", ""),
            status=data.get("status", "open"),
        )


def node_id_for_requirement(requirement_id: str) -> str:
    return f"requirement:{requirement_id}"


@dataclass
class ImpactPlan:
    cr_id: str
    changed_nodes: list[str]
    affected_nodes: list[str]
    affected_requirements: list[str]
    tests: list[str]
    reasons: dict[str, list[str]]
    regenerate: list[str]
    conflicts: list[str]
    spec_hash_before: str
    spec_hash_after: str
    nodes_total: int
    tests_total: int
    notes: list[str] = field(default_factory=list)

    @property
    def percent_nodes(self) -> float:
        return 100.0 * len(set(self.affected_nodes)) / max(1, self.nodes_total)

    def to_dict(self) -> dict:
        return {
            "cr_id": self.cr_id,
            "changed_nodes": self.changed_nodes,
            "affected_nodes": self.affected_nodes,
            "affected_requirements": self.affected_requirements,
            "tests": self.tests,
            "reasons": self.reasons,
            "regenerate": self.regenerate,
            "conflicts": self.conflicts,
            "spec_hash_before": self.spec_hash_before,
            "spec_hash_after": self.spec_hash_after,
            "nodes_total": self.nodes_total,
            "tests_total": self.tests_total,
            "percent_nodes": round(self.percent_nodes, 2),
            "notes": self.notes,
        }


def _hash_index(index: SpecIndex) -> str:
    return hashlib.sha256(canonical(index.node_hashes()).encode("utf-8")).hexdigest()


def analyze_impact(old_program: Program, new_program: Program, cr: ChangeRequest,
                   tests: Iterable, old_index: Optional[SpecIndex] = None,
                   new_index: Optional[SpecIndex] = None) -> ImpactPlan:
    old_index = old_index or build_index(old_program, analyze(old_program).model)
    new_index = new_index or build_index(new_program, analyze(new_program).model)
    tests = list(tests)

    changed: set[str] = set(cr.target_nodes)
    hash_changed: set[str] = set(cr.target_nodes)
    removed: set[str] = set()
    for node_id, node in new_index.nodes.items():
        old_node = old_index.nodes.get(node_id)
        if old_node is None or old_node.content_hash != node.content_hash:
            changed.add(node_id)
            hash_changed.add(node_id)
    for node_id in old_index.nodes:
        if node_id not in new_index.nodes:
            removed.add(node_id)
            changed.add(node_id)
            hash_changed.add(node_id)

    requirement_ids = set(cr.edited_requirement_ids())
    changed_requirements: set[str] = set(requirement_ids)
    doc_nodes: set[str] = set()
    for requirement_id in requirement_ids:
        linked = new_index.requirements.get(requirement_id, []) + \
            old_index.requirements.get(requirement_id, [])
        for node_id in linked:
            doc_nodes.add(node_id)
            changed.add(node_id)
    # requirements that link to changed nodes are mentioned in the report
    for node_id in changed:
        node = new_index.nodes.get(node_id) or old_index.nodes.get(node_id)
        if node:
            changed_requirements.update(node.requirements)

    behavior_seeds = hash_changed | {node_id for node_id in cr.target_nodes}
    doc_only = doc_nodes - behavior_seeds
    behavior_affected = new_index.dependents(behavior_seeds)
    affected_removed = old_index.dependents(removed)
    behavior_affected |= affected_removed
    affected = behavior_affected | doc_only

    affected_requirements = set(changed_requirements)
    for node_id in affected:
        node = new_index.nodes.get(node_id) or old_index.nodes.get(node_id)
        if node:
            affected_requirements.update(node.requirements)
    for requirement_id in requirement_ids:
        affected_requirements.add(requirement_id)

    reasons: dict[str, list[str]] = {}
    extra_requirements: dict[str, list[str]] = {}
    selected: list[str] = []
    for test in tests:
        node_hits = sorted(set(test.nodes) & behavior_affected)
        # Requirement text edits select the tests tied to exactly that
        # requirement. Other affected requirements do not select anything:
        # behavioural selection is driven by the node graph only.
        req_hits = sorted(set(test.requirements) & requirement_ids)
        if not node_hits and not req_hits:
            continue
        text: list[str] = []
        if node_hits:
            text.append("spec nodes: " + ", ".join(node_hits))
        if req_hits:
            text.append("requirements: " + ", ".join(req_hits))
        reasons[test.id] = text
        selected.append(test.id)
        if req_hits:
            extra_requirements.setdefault(test.id, []).extend(req_hits)

    structural_kinds = {"entity", "field", "enum", "state", "transition",
                        "rule", "const", "invariant", "scenario"}
    regenerate: list[str] = []
    for test in tests:
        if test.id not in reasons:
            continue
        hit_nodes = set(test.nodes) & behavior_affected
        kinds = {(new_index.nodes.get(node_id) or old_index.nodes.get(node_id)).kind
                 for node_id in hit_nodes
                 if (new_index.nodes.get(node_id) or old_index.nodes.get(node_id))}
        if kinds & structural_kinds:
            regenerate.append(test.id)
    regenerate.sort()

    conflicts: list[str] = []
    for node_id in sorted(removed):
        impacted = sorted(test.id for test in tests if node_id in test.nodes)
        if impacted:
            conflicts.append(
                f"node {node_id} was removed but tests still reference it: "
                + ", ".join(impacted))
    for requirement_id in sorted(requirement_ids):
        if not new_index.requirements.get(requirement_id):
            conflicts.append(
                f"requirement {requirement_id} is edited but has no linked spec nodes")
    if cr.kind == "requirement_text" and cr.spec_edits:
        conflicts.append("text change also edits the specification, review the kind")
    if any("removed" in conflict for conflict in conflicts):
        conflicts.append("regenerate affected tests before running the suite")

    notes: list[str] = []
    if len(affected) < len(changed):
        notes.append("affected closure is smaller than the seed set, check target nodes")
    if extra_requirements:
        notes.append(f"{len(extra_requirements)} tests selected by requirement text only")

    return ImpactPlan(
        cr_id=cr.id,
        changed_nodes=sorted(changed),
        affected_nodes=sorted(affected),
        affected_requirements=sorted(affected_requirements),
        tests=sorted(selected),
        reasons=reasons,
        regenerate=regenerate,
        conflicts=conflicts,
        spec_hash_before=_hash_index(old_index),
        spec_hash_after=_hash_index(new_index),
        nodes_total=len(new_index.nodes),
        tests_total=len(tests),
        notes=notes,
    )


def verify_minimality(plan: ImpactPlan, new_program: Program, tests: Iterable,
                      seed: int = 1234) -> dict:
    """Run the selected subset and the full suite, compare failed test sets."""
    from ..runtime.runner import Runner
    tests = list(tests)
    runner = Runner(new_program)
    selected_ids = set(plan.tests)
    subset = [case for case in tests if case.id in selected_ids]
    subset_run = runner.run(subset, seed=seed)
    full_run = runner.run(tests, seed=seed)
    subset_failed = set(subset_run.failed_ids())
    full_failed = set(full_run.failed_ids())
    missed = sorted(full_failed - subset_failed)
    extra = sorted(subset_failed - full_failed)
    selected_passed = sorted(case_id for case_id in selected_ids - set(subset_failed))
    return {
        "equal": subset_failed == full_failed,
        "subset_failed": sorted(subset_failed),
        "full_failed": sorted(full_failed),
        "missed": missed,
        "extra": extra,
        "selected": len(subset),
        "selected_passed": selected_passed,
        "total": len(tests),
        "subset_digest": subset_run.digest,
        "full_digest": full_run.digest,
        "subset_duration_ms": round(subset_run.duration_ms, 3),
        "full_duration_ms": round(full_run.duration_ms, 3),
    }
