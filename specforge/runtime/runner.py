"""Deterministic test runner.

The runner executes stored test cases against the current specification and
returns a canonical summary. Two runs with the same (specification, seed, test
set) produce byte identical digests.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Iterable

from ..core.ast_nodes import Program
from ..core.interpreter import Interpreter, EvalError
from .codegen import TestCase, SPECIAL_PATHS
from .engine import Simulation, apply_step


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def spec_hash(program: Program) -> str:
    from ..core.nodes import build_index
    from ..core.semantic import analyze
    index = build_index(program, analyze(program).model)
    return hashlib.sha256(canonical(index.node_hashes()).encode("utf-8")).hexdigest()


@dataclass
class TestResult:
    test_id: str
    kind: str
    title: str
    status: str
    message: str = ""
    actual: dict = field(default_factory=dict)
    requirements: tuple[str, ...] = ()
    nodes: tuple[str, ...] = ()
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id, "kind": self.kind, "title": self.title,
            "status": self.status, "message": self.message,
            "actual": self.actual, "requirements": list(self.requirements),
            "nodes": list(self.nodes),
        }

    def digest_part(self) -> dict:
        return {
            "test_id": self.test_id, "status": self.status,
            "message": self.message, "actual": self.actual,
        }


@dataclass
class RunSummary:
    results: list[TestResult]
    spec_hash: str
    seed: int
    digest: str = ""
    duration_ms: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def failed_ids(self) -> list[str]:
        return sorted(r.test_id for r in self.results if r.status == "failed")

    def to_dict(self) -> dict:
        return {
            "spec_hash": self.spec_hash, "seed": self.seed,
            "passed": self.passed, "failed": self.failed,
            "digest": self.digest,
            "results": [r.to_dict() for r in self.results],
        }

    def report_json(self) -> str:
        return canonical(self.to_dict())


class Runner:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.allowed = self._allowed_transitions()
        self._spec_hash = spec_hash(program)
        self.interpreter = Interpreter(program)

    def _allowed_transitions(self) -> set[tuple[str, str, str, str]]:
        allowed = set()
        for state in self.program.states:
            for edge in state.edges:
                allowed.add((state.name, edge.source, edge.target, edge.event))
        return allowed

    def run(self, cases: Iterable[TestCase], seed: int = 1234) -> RunSummary:
        started = time.perf_counter()
        results = [self._run_one(case) for case in sorted(cases, key=lambda c: c.id)]
        duration = (time.perf_counter() - started) * 1000.0
        digest_source = [result.digest_part() for result in results]
        digest = hashlib.sha256(canonical(digest_source).encode("utf-8")).hexdigest()
        return RunSummary(results=results, spec_hash=self._spec_hash, seed=seed,
                          digest=digest, duration_ms=duration)

    # ------------------------------------------------------------- execution
    def _run_one(self, case: TestCase) -> TestResult:
        started = time.perf_counter()
        sim = Simulation.from_program(self.program)
        messages: list[str] = []
        actual: dict = {}
        try:
            for path, value in case.setup.items():
                if path == "now":
                    sim.now = int(value)
                else:
                    sim.set_path(path, value)
            for step in case.steps:
                apply_step(sim, step)

            expected = case.expected
            actual_error = sim.last_error
            actual["error"] = actual_error
            if expected.get("error") is not None and actual_error != expected["error"]:
                messages.append(f"expected error {expected['error']!r}, got "
                                f"{actual_error!r}")

            for path, want in (expected.get("values") or {}).items():
                if path in SPECIAL_PATHS:
                    got = SPECIAL_PATHS[path](sim)
                else:
                    got = sim.get_path(path)
                actual[path] = got
                if got != want:
                    messages.append(f"{path}: expected {want!r}, got {got!r}")

            if expected.get("invariants") == "clean":
                violations = sim.check_invariants()
                if violations:
                    messages.append("invariants violated: " + "; ".join(violations))
                world = sim.world()
                world["__penalties__"] = sim.penalties
                for invariant in self.program.invariants:
                    try:
                        ok = bool(self.interpreter.eval(invariant.expr, world))
                    except EvalError as exc:
                        messages.append(f"{invariant.name}: evaluation error {exc}")
                        continue
                    if not ok:
                        messages.append(
                            f"{invariant.name}: {invariant.message or 'violated'}")

            for machine, src, dst, event in sim.transitions:
                key = (machine, src, dst, event)
                if key not in self.allowed:
                    messages.append(
                        f"forbidden transition {machine}: {src} -> {dst} on {event}")
                    break
        except Exception as exc:  # a broken test must not stop the run
            messages.append(f"execution error: {exc}")

        duration = (time.perf_counter() - started) * 1000.0
        return TestResult(
            test_id=case.id, kind=case.kind, title=case.title,
            status="failed" if messages else "passed",
            message="; ".join(messages), actual=actual,
            requirements=case.requirements, nodes=case.nodes,
            duration_ms=duration,
        )


def run_tests(program: Program, cases: Iterable[TestCase],
              seed: int = 1234) -> RunSummary:
    return Runner(program).run(cases, seed=seed)
