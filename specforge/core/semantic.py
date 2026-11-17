"""Semantic analysis: a lightweight type checker for the DSL.

Checks performed before any interpretation:
  * duplicate declarations and fields
  * unknown types, fields, constants and enum members
  * expression typing (Int/Money/Text/Bool/Time/Entity/State/Enum)
  * conditions (when/ensures/expect/invariant) must be Bool
  * transitions reference existing states of the matching enum
  * assignments target existing fields with compatible values
  * scenario steps match the operation catalogue
  * rule dependency cycles (through `apply`)
  * unreachable states in each state machine (warning)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import ast_nodes as A
from .diagnostics import Diagnostic, DiagnosticBag
from .ops import OPS, OpSignature


PRIMITIVES = {"Int", "Money", "Text", "Bool", "Time", "Identifier"}
NUMERIC = {"Int", "Money"}


@dataclass(frozen=True)
class DType:
    name: str = "Unknown"  # Int | Money | Text | Bool | Time | Identifier | Entity | State | Enum | Unknown
    arg: Optional[str] = None

    def is_numeric(self) -> bool:
        return self.name in NUMERIC

    def describe(self) -> str:
        if self.name == "Entity":
            return str(self.arg)
        if self.name == "State":
            return f"State<{self.arg}>"
        if self.name == "Enum":
            return str(self.arg)
        return self.name


UNKNOWN = DType("Unknown")
INT = DType("Int")
MONEY = DType("Money")
TEXT = DType("Text")
BOOL = DType("Bool")
TIME = DType("Time")
IDENTIFIER = DType("Identifier")


def entity_type(name: str) -> DType:
    return DType("Entity", name)


def state_type(enum: str) -> DType:
    return DType("State", enum)


def enum_type(enum: str) -> DType:
    return DType("Enum", enum)


@dataclass
class SemModel:
    entities: dict[str, dict[str, DType]] = field(default_factory=dict)
    entity_decls: dict[str, A.EntityDecl] = field(default_factory=dict)
    enums: dict[str, list[str]] = field(default_factory=dict)
    enum_members: dict[str, str] = field(default_factory=dict)
    consts: dict[str, DType] = field(default_factory=dict)
    const_values: dict[str, object] = field(default_factory=dict)
    roles: dict[str, A.RoleDecl] = field(default_factory=dict)
    states: dict[str, A.StateDecl] = field(default_factory=dict)
    world: dict[str, DType] = field(default_factory=dict)
    rules: dict[str, A.RuleDecl] = field(default_factory=dict)
    invariants: dict[str, A.InvariantDecl] = field(default_factory=dict)
    scenarios: dict[str, A.ScenarioDecl] = field(default_factory=dict)
    op_signatures: dict[str, OpSignature] = field(default_factory=lambda: dict(OPS))

    def field_type(self, entity: str, field_name: str) -> DType:
        return self.entities.get(entity, {}).get(field_name, UNKNOWN)

    @staticmethod
    def world_name(entity: str) -> str:
        return entity[0].lower() + entity[1:] if entity else entity


@dataclass
class SemanticResult:
    program: A.Program
    model: SemModel
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)


class SemanticAnalyzer:
    def __init__(self, program: A.Program) -> None:
        self.program = program
        self.bag = DiagnosticBag(source=program.filename)
        self.model = SemModel()
        self._rule_deps: dict[str, set[str]] = {}

    # ------------------------------------------------------------ utilities
    def _err(self, code: str, message: str, span: A.Span,
             hint: str = "", category: str = "semantic") -> None:
        self.bag.error(code, message, span.line, span.col,
                       max(1, span.end_col - span.col), hint=hint, category=category)

    def _warn(self, code: str, message: str, span: A.Span,
              hint: str = "", category: str = "semantic") -> None:
        self.bag.warning(code, message, span.line, span.col,
                         max(1, span.end_col - span.col), hint=hint, category=category)

    # --------------------------------------------------------------- model
    def _build_model(self) -> None:
        m = self.model
        seen: dict[str, A.Span] = {}

        def declare(namespace: dict, name: str, value, span: A.Span, kind: str) -> bool:
            if not name:
                return False
            if name in namespace:
                self._err("E100", f"duplicate {kind} {name!r}", span,
                          hint="names must be unique inside their namespace")
                return False
            namespace[name] = value
            return True

        for c in self.program.consts:
            declare(m.consts, c.name, self._resolve_type(c.type, allow_entity=False),
                    c.span, "constant")
            try:
                m.const_values[c.name] = self._literal_value(c.value)
            except ValueError:
                m.const_values[c.name] = None
                self._err("E119", f"constant {c.name!r} must have a literal value", c.value.span)

        for e in self.program.enums:
            if not declare(m.enums, e.name, [], e.span, "enum"):
                continue
            for member in e.members:
                if member in m.enums[e.name]:
                    self._err("E112", f"duplicate enum member {member!r} in {e.name}",
                              e.member_spans.get(member, e.span))
                    continue
                if member in m.enum_members and m.enum_members[member] != e.name:
                    self._warn("W003",
                               f"member {member!r} is used by enums "
                               f"{m.enum_members[member]} and {e.name}",
                               e.member_spans.get(member, e.span),
                               hint="unqualified enum members become ambiguous")
                m.enums[e.name].append(member)
                m.enum_members.setdefault(member, e.name)

        for ent in self.program.entities:
            if not declare(m.entities, ent.name, {}, ent.span, "entity"):
                continue
            m.entity_decls[ent.name] = ent
            m.world[SemModel.world_name(ent.name)] = entity_type(ent.name)

        # second pass: fields may reference entities declared later
        for ent in self.program.entities:
            if ent.name not in m.entity_decls:
                continue
            fields: dict[str, DType] = {}
            for fld in ent.fields:
                if fld.name in fields:
                    self._err("E113", f"duplicate field {fld.name!r} in entity {ent.name}",
                              fld.span)
                    continue
                dtype = self._resolve_type(fld.type, allow_entity=True)
                fields[fld.name] = dtype
            m.entities[ent.name] = fields

        for role in self.program.roles:
            declare(m.roles, role.name, role, role.span, "role")

        for st in self.program.states:
            declare(m.states, st.name, st, st.span, "state machine")

        for rule in self.program.rules:
            declare(m.rules, rule.name, rule, rule.span, "rule")
            self._rule_deps.setdefault(rule.name, set())

        for inv in self.program.invariants:
            declare(m.invariants, inv.name, inv, inv.span, "invariant")

        for sc in self.program.scenarios:
            declare(m.scenarios, sc.name, sc, sc.span, "scenario")

        # link declarations to nodes for traceability
        self._attach_links()

    def _attach_links(self) -> None:
        for link in self.program.links:
            for ref in link.requirements:
                if not ref.startswith("R-"):
                    self._warn("W004", f"link target {ref!r} does not look like R-NNN",
                               link.span, hint="requirements are named R-001, R-002, ...")

    def _literal_value(self, expr: A.Expr):
        if isinstance(expr, A.Literal):
            return expr.value
        if isinstance(expr, A.Name):
            if expr.name in self.model.const_values:
                return self.model.const_values[expr.name]
            raise ValueError("not a literal")
        if isinstance(expr, A.Unary) and expr.op == "-":
            value = self._literal_value(expr.operand)
            if isinstance(value, int):
                return -value
        raise ValueError("not a literal")

    def _resolve_type(self, ref: A.TypeRef, allow_entity: bool) -> DType:
        name = ref.name
        if name in PRIMITIVES:
            return DType(name)
        if name in ("State", "List"):
            if not ref.arg:
                self._err("E120", f"type {name} requires a type argument", ref.span)
                return UNKNOWN
            if ref.arg not in self.model.enums:
                self._err("E101", f"unknown enum {ref.arg!r} in type {ref.text()}", ref.span)
                return UNKNOWN
            return state_type(ref.arg)
        if name in self.model.enums:
            return enum_type(name)
        if allow_entity and name in self.model.entities:
            return entity_type(name)
        self._err("E101", f"unknown type {name!r}", ref.span,
                  hint="primitive types: Int, Money, Text, Bool, Time, Identifier")
        return UNKNOWN

    # ----------------------------------------------------------- inference
    def infer(self, expr: A.Expr) -> DType:
        if isinstance(expr, A.Literal):
            if expr.kind == "int":
                return INT
            if expr.kind == "text":
                return TEXT
            if expr.kind == "bool":
                return BOOL
            return UNKNOWN
        if isinstance(expr, A.Name):
            return self._infer_name(expr)
        if isinstance(expr, A.FieldAccess):
            return self._infer_field(expr)
        if isinstance(expr, A.ListExpr):
            return DType("List")
        if isinstance(expr, A.Unary):
            inner = self.infer(expr.operand)
            if expr.op == "not":
                if inner not in (BOOL, UNKNOWN):
                    self._err("E104", f"'not' expects Bool, got {inner.describe()}", expr.span)
                return BOOL
            if inner.name not in NUMERIC and inner.name != "Unknown":
                self._err("E103", f"unary {expr.op!r} expects a number, got {inner.describe()}",
                          expr.span)
            return MONEY if inner.name == "Money" else INT
        if isinstance(expr, A.Binary):
            return self._infer_binary(expr)
        if isinstance(expr, A.Call):
            return self._infer_call(expr)
        return UNKNOWN

    def _infer_name(self, expr: A.Name) -> DType:
        name = expr.name
        if name in self.model.consts:
            return self.model.consts[name]
        if name in self.model.world:
            return self.model.world[name]
        if name in self.model.enum_members:
            return enum_type(self.model.enum_members[name])
        if name in ("true", "false"):
            return BOOL
        self._err("E105", f"unknown name {name!r}", expr.span,
                  hint="names are constants, entities (lowercase), or enum members")
        return UNKNOWN

    def _infer_field(self, expr: A.FieldAccess) -> DType:
        base = self.infer(expr.base)
        if base.name == "Unknown":
            return UNKNOWN
        if base.name != "Entity":
            self._err("E106", f"cannot access field {expr.field_name!r} of {base.describe()}",
                      expr.span)
            return UNKNOWN
        entity = base.arg or ""
        fields = self.model.entities.get(entity, {})
        if expr.field_name not in fields:
            self._err("E102", f"entity {entity} has no field {expr.field_name!r}",
                      expr.span,
                      hint="fields: " + ", ".join(sorted(fields)) if fields else "")
            return UNKNOWN
        return fields[expr.field_name]

    def _infer_binary(self, expr: A.Binary) -> DType:
        if expr.op in ("and", "or"):
            left = self.infer(expr.left)
            right = self.infer(expr.right)
            for side in (left, right):
                if side.name not in ("Bool", "Unknown"):
                    self._err("E104", f"operator {expr.op!r} expects Bool operands, "
                                      f"got {side.describe()}", expr.span)
            return BOOL
        left = self.infer(expr.left)
        right = self.infer(expr.right)
        if expr.op == "in":
            if isinstance(expr.right, A.ListExpr):
                for item in expr.right.items:
                    item_type = self.infer(item)
                    if self._state_member(item, left):
                        continue
                    self._check_comparable(left, item_type, expr.span)
            return BOOL
        if expr.op in ("==", "!="):
            if self._state_member(expr.right, left) or self._state_member(expr.left, right):
                return BOOL
            self._check_comparable(left, right, expr.span)
            return BOOL
        if expr.op in ("<", "<=", ">", ">="):
            if left.name not in NUMERIC | {"Time", "Unknown"}:
                self._err("E103", f"comparison expects numbers or Time, got {left.describe()}",
                          expr.span)
            elif right.name not in NUMERIC | {"Time", "Unknown"}:
                self._err("E103", f"comparison expects numbers or Time, got {right.describe()}",
                          expr.span)
            return BOOL
        if expr.op in ("+", "-", "*", "/", "%"):
            for side in (left, right):
                if side.name not in NUMERIC | {"Unknown", "Time", "Int"}:
                    self._err("E103", f"arithmetic expects numbers, got {side.describe()}",
                              expr.span)
            if expr.op in ("+", "-") and left.name == "Time" and right.name == "Int":
                return TIME
            if expr.op == "+" and left.name == "Int" and right.name == "Time":
                return TIME
            if expr.op == "+" and (left.name == "Text" or right.name == "Text"):
                return TEXT
            if left.name == "Money" or right.name == "Money":
                return MONEY if expr.op in ("+", "-", "*") else INT
            return INT
        return UNKNOWN

    def _check_comparable(self, left: DType, right: DType, span: A.Span) -> None:
        if "Unknown" in (left.name, right.name):
            return
        if left.name == right.name and left.arg == right.arg:
            return
        if {left.name, right.name} == {"State", "Enum"} and left.arg == right.arg:
            return
        if {left.name, right.name} == {"Time", "Int"}:
            return
        if left.is_numeric() and right.is_numeric():
            return
        if left.name == "Text" and right.name == "Text":
            return
        self._err("E103", f"cannot compare {left.describe()} with {right.describe()}", span)

    def _state_member(self, expr: A.Expr, state: DType) -> bool:
        return (state.name == "State" and isinstance(expr, A.Name)
                and expr.name in self.model.enums.get(state.arg or "", []))

    def _infer_call(self, expr: A.Call) -> DType:
        name = expr.name
        args = [self.infer(a) for a in expr.args]

        def require(count: int) -> bool:
            if len(args) != count:
                self._err("E111", f"{name}() expects {count} argument(s), got {len(args)}",
                          expr.span)
                return False
            return True

        def numeric(index: int = 0) -> DType:
            if index < len(args) and args[index].name not in NUMERIC | {"Unknown"}:
                self._err("E111", f"{name}() expects a number at position {index + 1}, "
                                  f"got {args[index].describe()}", expr.span)
            return args[index] if index < len(args) else UNKNOWN

        if name in ("min", "max"):
            require(2)
            if len(args) == 2:
                if args[0].name not in NUMERIC | {"Unknown"} or args[1].name not in NUMERIC | {"Unknown"}:
                    self._err("E111", f"{name}() expects numeric arguments", expr.span)
                if args[0].name == "Money" or args[1].name == "Money":
                    return MONEY
            return INT
        if name == "abs":
            require(1)
            return MONEY if (args and args[0].name == "Money") else INT
        if name in ("minutesBetween", "hoursBetween", "daysBetween"):
            require(2)
            for a in args:
                if a.name not in ("Time", "Unknown"):
                    self._err("E111", f"{name}() expects Time arguments, got {a.describe()}",
                              expr.span)
            return INT
        if name == "now":
            require(0)
            return TIME
        if name == "lastError":
            require(0)
            return TEXT
        if name == "len":
            require(1)
            return INT
        if name in ("contains", "startsWith"):
            require(2)
            return BOOL
        if name == "weekday":
            require(1)
            return INT
        if name in ("formatTime", "upper"):
            require(1)
            return TEXT
        if name == "hasPermission":
            require(2)
            return BOOL
        if name == "countPenalties":
            require(1)
            return INT
        if name == "totalPenalties":
            require(1)
            return MONEY
        if name == "isBlocked":
            require(1)
            return BOOL
        sig = OPS.get(name)
        if sig is not None:
            self._err("E121", f"operation {name}() cannot be used in an expression",
                      expr.span)
            return UNKNOWN
        self._err("E110", f"unknown function {name!r}", expr.span,
                  hint="supported: min, max, abs, minutesBetween, hoursBetween, "
                       "daysBetween, now, lastError, len, contains, startsWith, "
                       "weekday, formatTime, hasPermission, countPenalties, totalPenalties")
        return UNKNOWN

    # ------------------------------------------------------------ checking
    def analyze(self) -> SemanticResult:
        self._build_model()
        self._check_consts()
        self._check_entities()
        self._check_roles()
        self._check_states()
        self._check_rules()
        self._check_invariants()
        self._check_scenarios()
        self._check_rule_cycles()
        return SemanticResult(self.program, self.model, self.bag.sorted())

    def _check_consts(self) -> None:
        for c in self.program.consts:
            declared = self.model.consts.get(c.name)
            actual = self.infer(c.value)
            if declared is None or actual.name == "Unknown":
                continue
            if not self._assignable(declared, actual):
                self._err("E103", f"constant {c.name} declared as {declared.describe()} "
                                  f"but value is {actual.describe()}", c.value.span)

    def _check_entities(self) -> None:
        for ent in self.program.entities:
            seen = set()
            for fld in ent.fields:
                if fld.name in seen:
                    continue
                seen.add(fld.name)
                declared = self.model.field_type(ent.name, fld.name)
                for cons in fld.constraints:
                    if declared.name not in NUMERIC | {"Unknown"}:
                        self._err("E103", f"constraint on non numeric field {ent.name}.{fld.name}",
                                  cons.span)
                    if cons.kind == "range":
                        if isinstance(cons.low, int) and isinstance(cons.high, int) and cons.low > cons.high:
                            self._err("E122", f"empty range [{cons.low}..{cons.high}]", cons.span)
                if fld.default is not None:
                    default_type = self.infer(fld.default)
                    if declared.name == "State" and default_type.name == "Enum":
                        if declared.arg != default_type.arg:
                            self._err("E103", f"default state for {ent.name}.{fld.name} "
                                              f"must be {declared.arg}", fld.default.span)
                    elif not self._assignable(declared, default_type):
                        self._err("E103", f"default for {ent.name}.{fld.name} is "
                                          f"{default_type.describe()}, expected {declared.describe()}",
                                  fld.default.span)

    def _check_roles(self) -> None:
        from .ops import PERMISSIONS
        for role in self.program.roles:
            for op in role.may + role.forbid:
                if op not in PERMISSIONS:
                    self._warn("W005", f"role {role.name} mentions unknown permission {op!r}",
                               role.span, hint="permissions: " + ", ".join(PERMISSIONS))
            overlap = set(role.may) & set(role.forbid)
            for op in sorted(overlap):
                self._err("E123", f"permission {op!r} is both allowed and forbidden for "
                                  f"role {role.name}", role.span)

    def _check_states(self) -> None:
        for st in self.program.states:
            members = self.model.enums.get(st.name)
            if members is None:
                self._err("E106", f"state machine {st.name} needs an enum with the same name",
                          st.span)
                continue
            if not st.initial:
                self._warn("W006", f"state machine {st.name} has no initial state", st.span)
            elif st.initial not in members:
                self._err("E106", f"initial state {st.initial!r} is not a member of "
                                  f"{st.name}", st.span)
            events: set[tuple[str, str]] = set()
            for edge in st.edges:
                if edge.source not in members:
                    self._err("E106", f"unknown source state {edge.source!r} in {st.name}",
                              edge.span)
                if edge.target not in members:
                    self._err("E106", f"unknown target state {edge.target!r} in {st.name}",
                              edge.span)
                key = (edge.source, edge.event)
                if key in events:
                    self._err("E117",
                              f"duplicate transition event {edge.event!r} from state "
                              f"{edge.source!r} in {st.name}", edge.span,
                              hint="an event must be unique for its source state")
                events.add(key)
                if edge.guard is not None:
                    guard_type = self.infer(edge.guard)
                    if guard_type.name not in ("Bool", "Unknown"):
                        self._err("E104", f"transition guard must be Bool, got "
                                          f"{guard_type.describe()}", edge.guard.span)
                for action in edge.actions:
                    self._check_stmt(action, scope=f"transition {st.name}.{edge.event}")
            self._check_reachability(st, members)

    def _check_reachability(self, st: A.StateDecl, members: list[str]) -> None:
        if not st.initial or st.initial not in members:
            return
        adjacency: dict[str, set[str]] = {}
        for edge in st.edges:
            adjacency.setdefault(edge.source, set()).add(edge.target)
        reachable: set[str] = set()
        stack = [st.initial]
        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            stack.extend(adjacency.get(node, ()))
        for member in members:
            if member not in reachable:
                self._warn("W001", f"state {member!r} is unreachable in {st.name}",
                           st.span, hint="add an incoming transition or remove the state",
                           category="validation")

    def _check_rules(self) -> None:
        for rule in self.program.rules:
            when_type = self.infer(rule.when)
            if when_type.name not in ("Bool", "Unknown"):
                self._err("E104", f"rule condition must be Bool, got {when_type.describe()}",
                          rule.when.span)
            for stmt in rule.then + rule.otherwise:
                self._check_stmt(stmt, scope=f"rule {rule.name}")
            if rule.ensures is not None:
                ensures_type = self.infer(rule.ensures)
                if ensures_type.name not in ("Bool", "Unknown"):
                    self._err("E104", f"ensures must be Bool, got {ensures_type.describe()}",
                              rule.ensures.span)

    def _check_invariants(self) -> None:
        for inv in self.program.invariants:
            inv_type = self.infer(inv.expr)
            if inv_type.name not in ("Bool", "Unknown"):
                self._err("E104", f"invariant {inv.name} must be Bool, got "
                                  f"{inv_type.describe()}", inv.expr.span)

    def _check_scenarios(self) -> None:
        for sc in self.program.scenarios:
            for given in sc.givens:
                base, _, field_name = given.path.partition(".")
                if given.path == "now":
                    value_type = self.infer(given.expr)
                    if value_type.name not in ("Int", "Unknown"):
                        self._err("E111", "now must be set to an integer minute",
                                  given.expr.span)
                    continue
                dtype = self.model.world.get(base)
                if dtype is None or dtype.name != "Entity":
                    self._err("E124", f"given path base {base!r} is not an entity",
                              given.span, hint="use entityName.field, for example customer.deposit")
                    continue
                fields = self.model.entities.get(dtype.arg or "", {})
                if field_name not in fields:
                    self._err("E102", f"entity {dtype.arg} has no field {field_name!r}",
                              given.span)
                    continue
                value_type = self.infer(given.expr)
                if not self._assignable(fields[field_name], value_type):
                    self._err("E103", f"given {given.path} expects "
                                      f"{fields[field_name].describe()}, got "
                                      f"{value_type.describe()}", given.expr.span)
            for step in sc.steps:
                sig = OPS.get(step.name)
                if sig is None:
                    self._err("E110", f"unknown step operation {step.name!r}", step.span,
                              hint="operations: " + ", ".join(sorted(OPS)))
                    continue
                if len(step.args) != len(sig.params):
                    self._err("E111", f"{step.name}() expects {len(sig.params)} argument(s), "
                                      f"got {len(step.args)}", step.span)
                    continue
                for index, arg in enumerate(step.args):
                    expected = sig.params[index][1]
                    actual = self.infer(arg)
                    if actual.name == "Unknown":
                        continue
                    if expected in PRIMITIVES:
                        if expected == "Int" and actual.name == "Money":
                            continue
                        if actual.name != expected:
                            self._err("E111", f"{step.name}() argument {index + 1} expects "
                                              f"{expected}, got {actual.describe()}", arg.span)
                    else:
                        if actual.name != "Entity" or actual.arg != expected:
                            self._err("E111", f"{step.name}() argument {index + 1} expects "
                                              f"{expected}, got {actual.describe()}", arg.span)
            for expect in sc.expects:
                expect_type = self.infer(expect)
                if expect_type.name not in ("Bool", "Unknown"):
                    self._err("E104", f"scenario expect must be Bool, got "
                                      f"{expect_type.describe()}", expect.span)

    def _check_stmt(self, stmt: A.Stmt, scope: str) -> None:
        if stmt.kind == "apply":
            if stmt.text not in self.model.rules:
                self._err("E115", f"apply references unknown rule {stmt.text!r}", stmt.span)
            else:
                self._rule_deps.setdefault(scope_rule_name(scope), set()).add(stmt.text)
            return
        if stmt.kind == "assert":
            if stmt.expr is not None:
                expr_type = self.infer(stmt.expr)
                if expr_type.name not in ("Bool", "Unknown"):
                    self._err("E104", f"assert expects Bool, got {expr_type.describe()}",
                              stmt.expr.span)
            return
        if stmt.kind in ("emit", "call"):
            return
        if stmt.kind == "assign" and stmt.expr is not None:
            base, _, field_name = stmt.target.partition(".")
            dtype = self.model.world.get(base)
            if dtype is None or dtype.name != "Entity":
                self._err("E107", f"assignment target {stmt.target!r} does not start with "
                                  f"an entity", stmt.span)
                return
            fields = self.model.entities.get(dtype.arg or "", {})
            if field_name not in fields:
                self._err("E107", f"entity {dtype.arg} has no field {field_name!r}",
                          stmt.span)
                return
            value_type = self.infer(stmt.expr)
            if not self._assignable(fields[field_name], value_type):
                self._err("E108", f"cannot assign {value_type.describe()} to "
                                  f"{stmt.target} ({fields[field_name].describe()})",
                          stmt.expr.span)

    def _check_rule_cycles(self) -> None:
        graph: dict[str, set[str]] = {}
        for rule in self.program.rules:
            deps = {dep for dep in self._rule_deps.get(rule.name, set())
                    if dep in self.model.rules}
            graph[rule.name] = deps
        for component in strongly_connected(graph):
            if len(component) > 1 or (len(component) == 1 and
                                      component[0] in graph.get(component[0], set())):
                names = ", ".join(sorted(component))
                rule = self.model.rules[sorted(component)[0]]
                self._err("E118", f"cyclic rule dependency: {names}", rule.span,
                          hint="rule cycles cannot terminate during interpretation")
        for name in graph:
            self._rule_deps[name] = graph[name]

    @staticmethod
    def _assignable(target: DType, value: DType) -> bool:
        if target.name == "Unknown" or value.name == "Unknown":
            return True
        if target.name == value.name and target.arg == value.arg:
            return True
        if target.name == "State" and value.name == "Enum" and target.arg == value.arg:
            return True
        if target.name == "Time" and value.name == "Int":
            return True
        if target.is_numeric() and value.is_numeric():
            return True
        return False


def scope_rule_name(scope: str) -> str:
    prefix = "rule "
    if scope.startswith(prefix):
        return scope[len(prefix):]
    return scope


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan SCC, iterative to stay safe on large generated graphs."""
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []

    for root in sorted(graph):
        if root in indices:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_index = work.pop()
            if child_index == 0:
                indices[node] = index
                low[node] = index
                index += 1
                stack.append(node)
                on_stack.add(node)
            children = sorted(graph.get(node, ()))
            recurse = False
            while child_index < len(children):
                child = children[child_index]
                child_index += 1
                if child not in indices:
                    work.append((node, child_index))
                    work.append((child, 0))
                    recurse = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], indices[child])
            if recurse:
                continue
            if low[node] == indices[node]:
                component: list[str] = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                result.append(sorted(component))
            if work:
                parent, _ = work[-1]
                low[parent] = min(low[parent], low[node])
    return result


def analyze(program: A.Program) -> SemanticResult:
    return SemanticAnalyzer(program).analyze()
