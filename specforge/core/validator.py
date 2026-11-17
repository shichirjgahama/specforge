"""Logical validator: conflicts, dead ends, impossible assignments, scenarios.

Semantic analysis answers "is this well typed?". The validator answers "does
this make sense as a business model?".
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import ast_nodes as A
from .diagnostics import Diagnostic, DiagnosticBag
from .nodes import SpecIndex, fmt_expr
from .semantic import SemanticResult
from .state_machine import build_state_graph


@dataclass
class ValidationReport:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    graphs: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "stats": self.stats,
            "graphs": {name: graph.to_dict() for name, graph in self.graphs.items()},
        }


class Validator:
    def __init__(self, semantic: SemanticResult, index: SpecIndex) -> None:
        self.semantic = semantic
        self.program = semantic.program
        self.model = semantic.model
        self.index = index
        self.bag = DiagnosticBag(source=self.program.filename)
        self.graphs = {}

    def _err(self, code: str, message: str, span: A.Span, hint: str = "") -> None:
        self.bag.error(code, message, span.line, span.col,
                       max(1, span.end_col - span.col), hint=hint, category="validation")

    def _warn(self, code: str, message: str, span: A.Span, hint: str = "") -> None:
        self.bag.warning(code, message, span.line, span.col,
                         max(1, span.end_col - span.col), hint=hint, category="validation")

    def validate(self) -> ValidationReport:
        self.bag.extend(self.semantic.diagnostics)
        self._check_state_machines()
        self._check_rule_conflicts()
        self._check_literal_assignments()
        self._check_scenario_steps()
        self._check_empty_nodes()
        diagnostics = self.bag.sorted()
        stats = {
            "entities": len(self.program.entities),
            "fields": sum(len(e.fields) for e in self.program.entities),
            "enums": len(self.program.enums),
            "roles": len(self.program.roles),
            "states": len(self.program.states),
            "transitions": sum(len(s.edges) for s in self.program.states),
            "rules": len(self.program.rules),
            "invariants": len(self.program.invariants),
            "scenarios": len(self.program.scenarios),
            "consts": len(self.program.consts),
            "nodes": len(self.index.nodes),
            "errors": sum(1 for d in diagnostics if d.severity == "error"),
            "warnings": sum(1 for d in diagnostics if d.severity == "warning"),
        }
        return ValidationReport(diagnostics=diagnostics, graphs=self.graphs, stats=stats)

    # ------------------------------------------------------------------ state
    def _check_state_machines(self) -> None:
        for state in self.program.states:
            members = self.model.enums.get(state.name, [])
            if not state.edges:
                self._warn("W010", f"state machine {state.name} has no transitions",
                           state.span)
            graph = build_state_graph(state, members)
            self.graphs[state.name] = graph
            if not state.initial and members:
                self._warn("W006", f"state machine {state.name} has no initial state",
                           state.span)
            for name in graph.unreachable:
                # already reported by semantic as W001, keep the graph data only
                pass
            for name in graph.dead_ends:
                self._warn("W011", f"state {name!r} in {state.name} is a dead end: "
                                   f"no outgoing transitions", state.span,
                           hint="add a transition or mark the state as terminal")
            for component in graph.cycles:
                if len(component) == 1 and component[0] not in {
                        e.target for e in state.edges if e.source == component[0]}:
                    continue
            incoming = {e.target for e in state.edges}
            for edge in state.edges:
                if edge.source not in incoming and edge.source != state.initial:
                    self._warn("W012", f"transition {edge.key} starts from a state with "
                                       f"no incoming transitions", edge.span)

    # ------------------------------------------------------------------ rules
    def _check_rule_conflicts(self) -> None:
        assignments: dict[str, list[tuple[A.RuleDecl, A.Stmt]]] = defaultdict(list)
        for rule in self.program.rules:
            for stmt in rule.then:
                if stmt.kind == "assign":
                    assignments[stmt.target].append((rule, stmt))
            for stmt in rule.otherwise:
                if stmt.kind == "assign":
                    assignments.setdefault(stmt.target, [])
        for target, entries in sorted(assignments.items()):
            if len(entries) < 2:
                continue
            for first in range(len(entries)):
                for second in range(first + 1, len(entries)):
                    rule_a, stmt_a = entries[first]
                    rule_b, stmt_b = entries[second]
                    if rule_a.name == rule_b.name:
                        self._err("E130", f"rule {rule_a.name} assigns {target} more than once",
                                  stmt_b.span, hint="merge the assignments or add a branch")
                        continue
                    same_guard = fmt_expr(rule_a.when) == fmt_expr(rule_b.when)
                    if same_guard and rule_a.priority == rule_b.priority:
                        self._err(
                            "E131",
                            f"rules {rule_a.name} and {rule_b.name} write {target} under "
                            f"the same condition and priority",
                            stmt_b.span,
                            hint="use different priorities or make the conditions disjoint",
                        )
                    elif same_guard:
                        self._warn(
                            "W013",
                            f"rules {rule_a.name} (priority {rule_a.priority}) and "
                            f"{rule_b.name} (priority {rule_b.priority}) overlap on {target}",
                            stmt_b.span,
                            hint="lower priority rule wins only when conditions differ",
                        )

    def _check_literal_assignments(self) -> None:
        def check(stmt: A.Stmt, owner_span: A.Span) -> None:
            if stmt.kind != "assign" or not isinstance(stmt.expr, A.Literal):
                return
            base, _, field_name = stmt.target.partition(".")
            entity_type = self.model.world.get(base)
            if entity_type is None or entity_type.name != "Entity":
                return
            decl = self.model.entity_decls.get(entity_type.arg or "")
            if decl is None:
                return
            field_decl = next((f for f in decl.fields if f.name == field_name), None)
            if field_decl is None:
                return
            value = stmt.expr.value
            for constraint in field_decl.constraints:
                if constraint.kind == "range" and isinstance(value, int):
                    if value < (constraint.low or 0) or value > (constraint.high or 0):
                        self._err(
                            "E132",
                            f"{stmt.target} := {value} violates range "
                            f"[{constraint.low}..{constraint.high}]",
                            stmt.span,
                        )
                if constraint.kind == "set" and isinstance(value, str):
                    if value not in constraint.values:
                        self._err("E132", f"{stmt.target} := {value} is outside "
                                          f"allowed values {constraint.values}", stmt.span)
                if constraint.kind == "min" and isinstance(value, int):
                    if value < (constraint.low or 0):
                        self._err("E132", f"{stmt.target} := {value} is below minimum "
                                          f"{constraint.low}", stmt.span)
                if constraint.kind == "max" and isinstance(value, int):
                    if value > (constraint.high or 0):
                        self._err("E132", f"{stmt.target} := {value} is above maximum "
                                          f"{constraint.high}", stmt.span)

        for rule in self.program.rules:
            for stmt in rule.then + rule.otherwise:
                check(stmt, rule.span)
        for state in self.program.states:
            for edge in state.edges:
                for action in edge.actions:
                    check(action, edge.span)

    # -------------------------------------------------------------- scenarios
    def _check_scenario_steps(self) -> None:
        from .ops import EVENT_ALIASES
        events = {edge.event for state in self.program.states for edge in state.edges}
        op_names = set(self.model.op_signatures)
        for scenario in self.program.scenarios:
            for step in scenario.steps:
                if step.name in op_names:
                    aliases = EVENT_ALIASES.get(step.name)
                    if aliases is not None and not (aliases & events):
                        self._warn(
                            "W014",
                            f"scenario {scenario.name} calls {step.name} but no transition "
                            f"uses any of {sorted(aliases)}",
                            step.span,
                            hint="keep transition event names aligned with operations",
                        )

    def _check_empty_nodes(self) -> None:
        if not self.program.entities:
            self._err("E133", "specification has no entities", self.program.header.span)
        if not self.program.states:
            self._warn("W015", "specification has no state machines", self.program.header.span)


def validate(semantic: SemanticResult, index: SpecIndex) -> ValidationReport:
    return Validator(semantic, index).validate()
