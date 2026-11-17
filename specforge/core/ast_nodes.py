"""AST for the SpecForge specification language (.sforge).

The language is hand written, not a YAML/JSON superset. Constructs:
  spec, const, entity, enum, role, state, rule, invariant, scenario, link.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Span:
    line: int = 1
    col: int = 1
    end_line: int = 1
    end_col: int = 1

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }


# ---------------------------------------------------------------- expressions

@dataclass
class Expr:
    span: Span = field(default_factory=Span)

    def children(self) -> list["Expr"]:
        return []


@dataclass
class Literal(Expr):
    value: Any = None
    kind: str = "int"  # int | text | bool | enum


@dataclass
class Name(Expr):
    name: str = ""


@dataclass
class FieldAccess(Expr):
    base: Expr = field(default_factory=Expr)
    field_name: str = ""


@dataclass
class Call(Expr):
    name: str = ""
    args: list[Expr] = field(default_factory=list)


@dataclass
class Unary(Expr):
    op: str = "-"
    operand: Expr = field(default_factory=Expr)


@dataclass
class Binary(Expr):
    op: str = "=="
    left: Expr = field(default_factory=Expr)
    right: Expr = field(default_factory=Expr)


@dataclass
class ListExpr(Expr):
    items: list[Expr] = field(default_factory=list)


def walk_expr(expr: Expr):
    yield expr
    for child in expr.children():
        yield from walk_expr(child)


def expr_children(expr: Expr) -> list[Expr]:
    if isinstance(expr, FieldAccess):
        return [expr.base]
    if isinstance(expr, Call):
        return list(expr.args)
    if isinstance(expr, Unary):
        return [expr.operand]
    if isinstance(expr, Binary):
        return [expr.left, expr.right]
    if isinstance(expr, ListExpr):
        return list(expr.items)
    return []


# attach children implementation without changing dataclass fields
Expr.children = lambda self: expr_children(self)  # type: ignore[assignment]


# ------------------------------------------------------------------ type refs

@dataclass
class TypeRef:
    name: str = "Int"
    arg: Optional[str] = None
    optional: bool = False
    span: Span = field(default_factory=Span)

    def text(self) -> str:
        base = self.name
        if self.arg:
            base += f"<{self.arg}>"
        if self.optional:
            base += "?"
        return base


@dataclass
class Constraint:
    kind: str = "range"  # range | set | min | max
    low: Optional[Any] = None
    high: Optional[Any] = None
    values: list[str] = field(default_factory=list)
    span: Span = field(default_factory=Span)


# --------------------------------------------------------------- declarations

@dataclass
class Header:
    name: str = ""
    version: int = 1
    span: Span = field(default_factory=Span)


@dataclass
class ConstDecl:
    name: str = ""
    type: TypeRef = field(default_factory=TypeRef)
    value: Expr = field(default_factory=Literal)
    doc: str = ""
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)


@dataclass
class FieldDecl:
    name: str = ""
    type: TypeRef = field(default_factory=TypeRef)
    constraints: list[Constraint] = field(default_factory=list)
    default: Optional[Expr] = None
    span: Span = field(default_factory=Span)


@dataclass
class EntityDecl:
    name: str = ""
    fields: list[FieldDecl] = field(default_factory=list)
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)


@dataclass
class EnumDecl:
    name: str = ""
    members: list[str] = field(default_factory=list)
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)
    member_spans: dict = field(default_factory=dict)


@dataclass
class RoleDecl:
    name: str = ""
    may: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)


@dataclass
class Stmt:
    kind: str = "assign"  # assign | call | assert | emit | apply
    target: str = ""
    expr: Optional[Expr] = None
    text: str = ""
    span: Span = field(default_factory=Span)


@dataclass
class EdgeDecl:
    source: str = ""
    target: str = ""
    event: str = ""
    guard: Optional[Expr] = None
    actions: list[Stmt] = field(default_factory=list)
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}->{self.target}:{self.event}"


@dataclass
class StateDecl:
    name: str = ""
    initial: str = ""
    edges: list[EdgeDecl] = field(default_factory=list)
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)


@dataclass
class RuleDecl:
    name: str = ""
    priority: int = 0
    when: Expr = field(default_factory=Literal)
    then: list[Stmt] = field(default_factory=list)
    otherwise: list[Stmt] = field(default_factory=list)
    ensures: Optional[Expr] = None
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)


@dataclass
class InvariantDecl:
    name: str = ""
    expr: Expr = field(default_factory=Literal)
    message: str = ""
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)


@dataclass
class GivenBinding:
    path: str = ""
    expr: Expr = field(default_factory=Literal)
    span: Span = field(default_factory=Span)


@dataclass
class ScenarioStep:
    name: str = ""
    args: list[Expr] = field(default_factory=list)
    span: Span = field(default_factory=Span)
    expect_ok: Optional[bool] = None


@dataclass
class ScenarioDecl:
    name: str = ""
    givens: list[GivenBinding] = field(default_factory=list)
    steps: list[ScenarioStep] = field(default_factory=list)
    expects: list[Expr] = field(default_factory=list)
    span: Span = field(default_factory=Span)
    links: list[str] = field(default_factory=list)


@dataclass
class RequirementLink:
    """Free standing `link R-001, R-002;` attached to the previous node."""

    requirements: list[str] = field(default_factory=list)
    target_node: str = ""
    span: Span = field(default_factory=Span)


@dataclass
class Program:
    header: Header = field(default_factory=Header)
    consts: list[ConstDecl] = field(default_factory=list)
    entities: list[EntityDecl] = field(default_factory=list)
    enums: list[EnumDecl] = field(default_factory=list)
    roles: list[RoleDecl] = field(default_factory=list)
    states: list[StateDecl] = field(default_factory=list)
    rules: list[RuleDecl] = field(default_factory=list)
    invariants: list[InvariantDecl] = field(default_factory=list)
    scenarios: list[ScenarioDecl] = field(default_factory=list)
    links: list[RequirementLink] = field(default_factory=list)
    source: str = ""
    filename: str = "<spec>"

    def entity(self, name: str) -> Optional[EntityDecl]:
        for item in self.entities:
            if item.name == name:
                return item
        return None

    def enum(self, name: str) -> Optional[EnumDecl]:
        for item in self.enums:
            if item.name == name:
                return item
        return None

    def state(self, name: str) -> Optional[StateDecl]:
        for item in self.states:
            if item.name == name:
                return item
        return None

    def rule(self, name: str) -> Optional[RuleDecl]:
        for item in self.rules:
            if item.name == name:
                return item
        return None

    def const(self, name: str) -> Optional[ConstDecl]:
        for item in self.consts:
            if item.name == name:
                return item
        return None

    def all_links(self) -> list[RequirementLink]:
        result = list(self.links)
        return result
