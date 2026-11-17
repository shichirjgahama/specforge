"""Specification node index: content hashes and a dependency graph.

Every declaration becomes a node with a stable id:
  entity:Scooter, field:Scooter.battery, enum:ScooterState, role:Customer,
  const:lateFee, state:ScooterState, transition:ScooterState:reserve,
  rule:BRI-02, invariant:DepositNonNegative, scenario:HappyPath.

Edges point from a node to the nodes it depends on. Impact analysis walks the
reverse graph: everything that (transitively) depends on a changed node must
be re-checked.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import ast_nodes as A
from .semantic import SemModel


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- AST printer
def expr_key(expr: A.Expr) -> dict:
    if isinstance(expr, A.Literal):
        return {"k": "lit", "v": expr.value, "t": expr.kind}
    if isinstance(expr, A.Name):
        return {"k": "name", "v": expr.name}
    if isinstance(expr, A.FieldAccess):
        return {"k": "field", "b": expr_key(expr.base), "f": expr.field_name}
    if isinstance(expr, A.Call):
        return {"k": "call", "v": expr.name, "a": [expr_key(a) for a in expr.args]}
    if isinstance(expr, A.Unary):
        return {"k": "un", "op": expr.op, "a": expr_key(expr.operand)}
    if isinstance(expr, A.Binary):
        return {"k": "bin", "op": expr.op, "l": expr_key(expr.left),
                "r": expr_key(expr.right)}
    if isinstance(expr, A.ListExpr):
        return {"k": "list", "a": [expr_key(i) for i in expr.items]}
    return {"k": "unknown"}


def stmt_key(stmt: A.Stmt) -> dict:
    return {
        "k": stmt.kind,
        "target": stmt.target,
        "expr": expr_key(stmt.expr) if stmt.expr is not None else None,
        "text": stmt.text,
    }


def type_key(type_ref: A.TypeRef) -> dict:
    return {"n": type_ref.name, "a": type_ref.arg, "o": type_ref.optional}


def fmt_expr(expr: A.Expr) -> str:
    if isinstance(expr, A.Literal):
        if expr.kind == "text":
            return json.dumps(expr.value, ensure_ascii=False)
        if expr.kind == "bool":
            return "true" if expr.value else "false"
        return str(expr.value)
    if isinstance(expr, A.Name):
        return expr.name
    if isinstance(expr, A.FieldAccess):
        return f"{fmt_expr(expr.base)}.{expr.field_name}"
    if isinstance(expr, A.Call):
        return f"{expr.name}(" + ", ".join(fmt_expr(a) for a in expr.args) + ")"
    if isinstance(expr, A.Unary):
        if expr.op == "not":
            return f"not {fmt_expr(expr.operand)}"
        return f"{expr.op}{fmt_expr(expr.operand)}"
    if isinstance(expr, A.Binary):
        return f"({fmt_expr(expr.left)} {expr.op} {fmt_expr(expr.right)})"
    if isinstance(expr, A.ListExpr):
        return "{" + ", ".join(fmt_expr(i) for i in expr.items) + "}"
    return "?"


def fmt_stmt(stmt: A.Stmt) -> str:
    if stmt.kind == "assign":
        return f"{stmt.target} := {fmt_expr(stmt.expr) if stmt.expr else '?'}"
    if stmt.kind == "apply":
        return f"apply {stmt.text}"
    if stmt.kind == "assert":
        return f"assert {fmt_expr(stmt.expr) if stmt.expr else '?'}"
    if stmt.kind == "emit":
        return f'emit "{stmt.text}"'
    return stmt.kind


# ---------------------------------------------------------------------- node
@dataclass
class SpecNode:
    id: str
    kind: str
    name: str
    line: int = 1
    col: int = 1
    requirements: tuple[str, ...] = ()
    deps: tuple[str, ...] = ()
    content_hash: str = ""
    signature: str = ""
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "line": self.line,
            "col": self.col,
            "requirements": list(self.requirements),
            "deps": list(self.deps),
            "content_hash": self.content_hash,
            "signature": self.signature,
            "detail": self.detail,
        }


class RefCollector:
    """Collects field, const, enum and rule references from an expression."""

    def __init__(self, model: SemModel) -> None:
        self.model = model
        self.fields: set[str] = set()
        self.consts: set[str] = set()
        self.enums: set[str] = set()
        self.rules: set[str] = set()

    def visit(self, expr: Optional[A.Expr]) -> None:
        if expr is None:
            return
        if isinstance(expr, A.FieldAccess):
            if isinstance(expr.base, A.Name):
                base_type = self.model.world.get(expr.base.name)
                if base_type is not None and base_type.name == "Entity":
                    self.fields.add(f"field:{base_type.arg}.{expr.field_name}")
            self.visit(expr.base)
            return
        if isinstance(expr, A.Name):
            if expr.name in self.model.consts:
                self.consts.add(f"const:{expr.name}")
            if expr.name in self.model.enum_members:
                self.enums.add(f"enum:{self.model.enum_members[expr.name]}")
            return
        if isinstance(expr, A.Binary):
            self.visit(expr.left)
            self.visit(expr.right)
            return
        if isinstance(expr, A.Unary):
            self.visit(expr.operand)
            return
        if isinstance(expr, A.Call):
            for arg in expr.args:
                self.visit(arg)
            if expr.name in self.model.rules:
                self.rules.add(f"rule:{expr.name}")
            return
        if isinstance(expr, A.ListExpr):
            for item in expr.items:
                self.visit(item)

    def visit_stmt(self, stmt: A.Stmt) -> None:
        if stmt.expr is not None:
            self.visit(stmt.expr)
        if stmt.kind == "assign" and stmt.target:
            base, _, field_name = stmt.target.partition(".")
            base_type = self.model.world.get(base)
            if base_type is not None and base_type.name == "Entity":
                self.fields.add(f"field:{base_type.arg}.{field_name}")
        if stmt.kind == "apply" and stmt.text:
            self.rules.add(f"rule:{stmt.text}")

    def result(self) -> set[str]:
        return set(self.fields) | set(self.consts) | set(self.enums) | set(self.rules)


def collect_stmt_deps(model: SemModel, stmts: Iterable[A.Stmt]) -> set[str]:
    collector = RefCollector(model)
    for stmt in stmts:
        collector.visit_stmt(stmt)
    return collector.result()


class SpecIndex:
    def __init__(self) -> None:
        self.nodes: dict[str, SpecNode] = {}
        self.aliases: dict[str, str] = {}
        self.requirements: dict[str, list[str]] = {}
        self._reverse: dict[str, set[str]] = {}

    # -------------------------------------------------------------- building
    @property
    def reverse(self) -> dict[str, set[str]]:
        if not self._reverse:
            self._reverse = self._build_reverse()
        return self._reverse

    def _build_reverse(self) -> dict[str, set[str]]:
        reverse: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for node in self.nodes.values():
            for dep in node.deps:
                if dep in reverse:
                    reverse[dep].add(node.id)
        return reverse

    def add(self, node: SpecNode) -> None:
        self.nodes[node.id] = node
        for req in node.requirements:
            self.requirements.setdefault(req, []).append(node.id)

    def by_kind(self, kind: str) -> list[SpecNode]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def get(self, node_id: str) -> Optional[SpecNode]:
        return self.nodes.get(node_id)

    def resolve(self, node_id: str) -> Optional[SpecNode]:
        if node_id in self.nodes:
            return self.nodes[node_id]
        alias = self.aliases.get(node_id)
        if alias:
            return self.nodes.get(alias)
        return None

    # -------------------------------------------------------------- analysis
    def dependents(self, changed: Iterable[str]) -> set[str]:
        """All nodes that transitively depend on the changed set (inclusive)."""
        result: set[str] = set()
        stack = [node for node in changed if node in self.nodes]
        while stack:
            node_id = stack.pop()
            if node_id in result:
                continue
            result.add(node_id)
            for parent in self.reverse.get(node_id, ()):
                if parent not in result:
                    stack.append(parent)
        return result

    def dependency_closure(self, node_ids: Iterable[str]) -> set[str]:
        result: set[str] = set()
        stack = list(node_ids)
        while stack:
            node_id = stack.pop()
            if node_id in result or node_id not in self.nodes:
                continue
            result.add(node_id)
            stack.extend(self.nodes[node_id].deps)
        return result

    def tests_for_nodes(self, node_ids: Iterable[str]) -> set[str]:
        node_set = set(node_ids)
        return {req for req in node_set if req.startswith("test:")}

    def requirements_of(self, node_ids: Iterable[str]) -> list[str]:
        result: set[str] = set()
        for node_id in node_ids:
            node = self.nodes.get(node_id)
            if node:
                result.update(node.requirements)
        return sorted(result)

    def coverage(self) -> dict[str, list[str]]:
        return {req: list(ids) for req, ids in self.requirements.items()}

    def node_hashes(self) -> dict[str, str]:
        return {node_id: node.content_hash for node_id, node in sorted(self.nodes.items())}


# ------------------------------------------------------------------ builder
def build_index(program: A.Program, model: SemModel) -> SpecIndex:
    index = SpecIndex()
    links_by_node = _links_by_node(program)

    # enums
    for enum in program.enums:
        node_id = f"enum:{enum.name}"
        node = SpecNode(
            id=node_id, kind="enum", name=enum.name,
            line=enum.span.line, col=enum.span.col,
            requirements=tuple(links_by_node.get(node_id, ())),
            content_hash=sha256_text(canonical({"name": enum.name, "members": enum.members})),
            signature=f"enum {enum.name} {{ {', '.join(enum.members)} }}",
            detail={"members": enum.members},
        )
        index.add(node)

    # constants
    for const in program.consts:
        node_id = f"const:{const.name}"
        value = model.const_values.get(const.name)
        node = SpecNode(
            id=node_id, kind="const", name=const.name,
            line=const.span.line, col=const.span.col,
            requirements=tuple(links_by_node.get(node_id, ())),
            content_hash=sha256_text(canonical({
                "name": const.name, "type": type_key(const.type), "value": value,
            })),
            signature=f"const {const.name}: {const.type.text()} = {value}",
            detail={"value": value, "type": const.type.text()},
        )
        index.add(node)

    # entities + fields
    for entity in program.entities:
        entity_id = f"entity:{entity.name}"
        structure = [{"name": f.name, "type": type_key(f.type)} for f in entity.fields]
        index.add(SpecNode(
            id=entity_id, kind="entity", name=entity.name,
            line=entity.span.line, col=entity.span.col,
            requirements=tuple(links_by_node.get(entity_id, ())),
            content_hash=sha256_text(canonical({"name": entity.name, "fields": structure})),
            signature=f"entity {entity.name} ({len(entity.fields)} fields)",
            detail={"fields": [f.name for f in entity.fields]},
        ))
        for fld in entity.fields:
            field_id = f"field:{entity.name}.{fld.name}"
            dtype = model.field_type(entity.name, fld.name)
            deps = {entity_id}
            if dtype.name == "State" and dtype.arg:
                deps.add(f"enum:{dtype.arg}")
            if dtype.name == "Entity" and dtype.arg:
                deps.add(f"entity:{dtype.arg}")
            index.add(SpecNode(
                id=field_id, kind="field", name=f"{entity.name}.{fld.name}",
                line=fld.span.line, col=fld.span.col,
                requirements=tuple(links_by_node.get(field_id, ())),
                deps=tuple(sorted(deps)),
                content_hash=sha256_text(canonical({
                    "name": fld.name, "type": type_key(fld.type),
                    "constraints": [
                        {"k": c.kind, "low": c.low, "high": c.high, "values": c.values}
                        for c in fld.constraints
                    ],
                    "default": expr_key(fld.default) if fld.default else None,
                })),
                signature=f"{entity.name}.{fld.name}: {fld.type.text()}",
                detail={"entity": entity.name, "type": dtype.describe()},
            ))

    # roles
    for role in program.roles:
        node_id = f"role:{role.name}"
        index.add(SpecNode(
            id=node_id, kind="role", name=role.name,
            line=role.span.line, col=role.span.col,
            requirements=tuple(links_by_node.get(node_id, ())),
            content_hash=sha256_text(canonical({"may": role.may, "forbid": role.forbid})),
            signature=f"role {role.name} may {', '.join(role.may)}",
            detail={"may": role.may, "forbid": role.forbid},
        ))

    # state machines and transitions
    for state in program.states:
        state_id = f"state:{state.name}"
        index.aliases[f"enum:{state.name}"] = f"enum:{state.name}"
        index.add(SpecNode(
            id=state_id, kind="state", name=state.name,
            line=state.span.line, col=state.span.col,
            requirements=tuple(links_by_node.get(state_id, ())),
            deps=(f"enum:{state.name}",),
            content_hash=sha256_text(canonical({
                "name": state.name, "initial": state.initial,
                "edges": [edge_key(e) for e in state.edges],
            })),
            signature=f"state {state.name} initial {state.initial}",
            detail={"initial": state.initial,
                    "states": model.enums.get(state.name, []),
                    "edges": [e.key for e in state.edges]},
        ))
        for edge in state.edges:
            transition_id = f"transition:{state.name}:{edge.source}:{edge.event}"
            collector = RefCollector(model)
            collector.visit(edge.guard)
            for action in edge.actions:
                collector.visit_stmt(action)
            deps = collector.result() | {f"enum:{state.name}", state_id}
            index.add(SpecNode(
                id=transition_id, kind="transition", name=edge.event,
                line=edge.span.line, col=edge.span.col,
                requirements=tuple(links_by_node.get(transition_id, ())) or
                tuple(links_by_node.get(state_id, ())),
                deps=tuple(sorted(deps)),
                content_hash=sha256_text(canonical(edge_key(edge))),
                signature=f"{edge.source} -> {edge.target} : {edge.event}",
                detail={"source": edge.source, "target": edge.target,
                        "event": edge.event, "machine": state.name,
                        "guard": fmt_expr(edge.guard) if edge.guard else "",
                        "actions": [fmt_stmt(a) for a in edge.actions]},
            ))

    # rules
    for rule in program.rules:
        node_id = f"rule:{rule.name}"
        collector = RefCollector(model)
        collector.visit(rule.when)
        collector.visit(rule.ensures)
        for stmt in rule.then + rule.otherwise:
            collector.visit_stmt(stmt)
        index.add(SpecNode(
            id=node_id, kind="rule", name=rule.name,
            line=rule.span.line, col=rule.span.col,
            requirements=tuple(links_by_node.get(node_id, ())),
            deps=tuple(sorted(collector.result())),
            content_hash=sha256_text(canonical({
                "name": rule.name, "priority": rule.priority,
                "when": expr_key(rule.when),
                "then": [stmt_key(s) for s in rule.then],
                "else": [stmt_key(s) for s in rule.otherwise],
                "ensures": expr_key(rule.ensures) if rule.ensures else None,
            })),
            signature=f"rule {rule.name} when {fmt_expr(rule.when)}",
            detail={"priority": rule.priority, "when": fmt_expr(rule.when),
                    "then": [fmt_stmt(s) for s in rule.then],
                    "else": [fmt_stmt(s) for s in rule.otherwise]},
        ))

    # invariants
    for inv in program.invariants:
        node_id = f"invariant:{inv.name}"
        collector = RefCollector(model)
        collector.visit(inv.expr)
        index.add(SpecNode(
            id=node_id, kind="invariant", name=inv.name,
            line=inv.span.line, col=inv.span.col,
            requirements=tuple(links_by_node.get(node_id, ())),
            deps=tuple(sorted(collector.result())),
            content_hash=sha256_text(canonical({"name": inv.name, "expr": expr_key(inv.expr)})),
            signature=f"invariant {inv.name} always {fmt_expr(inv.expr)}",
            detail={"expr": fmt_expr(inv.expr), "message": inv.message},
        ))

    # scenarios
    for sc in program.scenarios:
        node_id = f"scenario:{sc.name}"
        collector = RefCollector(model)
        for given in sc.givens:
            collector.visit(given.expr)
            base, _, fname = given.path.partition(".")
            base_type = model.world.get(base)
            if base_type is not None and base_type.name == "Entity":
                collector.fields.add(f"field:{base_type.arg}.{fname}")
        for step in sc.steps:
            for arg in step.args:
                collector.visit(arg)
            from .ops import EVENT_ALIASES
            aliases = EVENT_ALIASES.get(step.name, set())
            for state in program.states:
                for edge in state.edges:
                    if edge.event == step.name or edge.event in aliases:
                        collector.rules.add(
                            f"transition:{state.name}:{edge.source}:{edge.event}")
        for expect in sc.expects:
            collector.visit(expect)
        index.add(SpecNode(
            id=node_id, kind="scenario", name=sc.name,
            line=sc.span.line, col=sc.span.col,
            requirements=tuple(links_by_node.get(node_id, ())),
            deps=tuple(sorted(collector.result())),
            content_hash=sha256_text(canonical({
                "name": sc.name,
                "givens": [{"p": g.path, "e": expr_key(g.expr)} for g in sc.givens],
                "steps": [{"n": s.name, "a": [expr_key(a) for a in s.args]} for s in sc.steps],
                "expects": [expr_key(e) for e in sc.expects],
            })),
            signature=f"scenario {sc.name} ({len(sc.steps)} steps)",
            detail={"givens": [g.path for g in sc.givens],
                    "steps": [s.name for s in sc.steps]},
        ))

    return index


def edge_key(edge: A.EdgeDecl) -> dict:
    return {
        "source": edge.source, "target": edge.target, "event": edge.event,
        "guard": expr_key(edge.guard) if edge.guard else None,
        "actions": [stmt_key(a) for a in edge.actions],
    }


def _links_by_node(program: A.Program) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for link in program.links:
        if not link.target_node:
            continue
        result.setdefault(link.target_node, []).extend(link.requirements)
    return result
