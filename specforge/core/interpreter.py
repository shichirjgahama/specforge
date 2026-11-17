"""Interpreter for the SpecForge DSL.

Evaluates expressions, executes rules and scenarios, checks DSL transitions and
invariants after every step. This is the executable side of the specification
the same runtime the generated tests use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional

from . import ast_nodes as A
from .nodes import fmt_expr
from .ops import OPS
from .semantic import SemModel, analyze


class EvalError(Exception):
    def __init__(self, message: str, span: Optional[A.Span] = None) -> None:
        super().__init__(message)
        self.span = span


@dataclass
class ScenarioResult:
    name: str
    ok: bool = True
    steps: int = 0
    failures: list[str] = field(default_factory=list)
    invariant_violations: list[str] = field(default_factory=list)
    transition_violations: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "ok": self.ok, "steps": self.steps,
            "failures": self.failures,
            "invariant_violations": self.invariant_violations,
            "transition_violations": self.transition_violations,
            "trace": self.trace, "error": self.error,
        }


class Interpreter:
    def __init__(self, program: A.Program, model: Optional[SemModel] = None) -> None:
        self.program = program
        self.model = model or analyze(program).model
        self.consts = self._collect_consts()
        self._transitions = self._collect_transitions()

    # -------------------------------------------------------------- constants
    def _collect_consts(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for const in self.program.consts:
            try:
                values[const.name] = self._literal(const.value, values)
            except EvalError:
                values[const.name] = 0
        return values

    def _literal(self, expr: A.Expr, values: dict) -> Any:
        if isinstance(expr, A.Literal):
            return expr.value
        if isinstance(expr, A.Name):
            if expr.name in values:
                return values[expr.name]
            raise EvalError(f"unknown constant {expr.name}", expr.span)
        if isinstance(expr, A.Unary) and expr.op == "-":
            return -self._literal(expr.operand, values)
        raise EvalError("constant must be a literal", expr.span)

    def _collect_transitions(self) -> set[tuple[str, str, str, str]]:
        result = set()
        for state in self.program.states:
            for edge in state.edges:
                result.add((state.name, edge.source, edge.target, edge.event))
        return result

    # ------------------------------------------------------------ expressions
    def eval(self, expr: A.Expr, world: dict) -> Any:
        try:
            return self._eval(expr, world)
        except EvalError:
            raise
        except Exception as exc:  # defensive: report interpreter errors precisely
            raise EvalError(str(exc), expr.span) from exc

    def _eval(self, expr: A.Expr, world: dict) -> Any:
        if isinstance(expr, A.Literal):
            return expr.value
        if isinstance(expr, A.Name):
            name = expr.name
            if name in self.consts:
                return self.consts[name]
            if name in world:
                return world[name]
            if name in self.model.enum_members:
                return name
            if name in ("true", "false"):
                return name == "true"
            raise EvalError(f"unknown name {name!r}", expr.span)
        if isinstance(expr, A.FieldAccess):
            base = self._eval(expr.base, world)
            if isinstance(base, dict):
                if expr.field_name in base:
                    return base[expr.field_name]
                raise EvalError(f"field {expr.field_name!r} is not present", expr.span)
            raise EvalError(f"cannot read field {expr.field_name!r}", expr.span)
        if isinstance(expr, A.ListExpr):
            return [self._eval(item, world) for item in expr.items]
        if isinstance(expr, A.Unary):
            value = self._eval(expr.operand, world)
            if expr.op == "not":
                return not bool(value)
            if expr.op == "-":
                return -value
            if expr.op == "+":
                return +value
            raise EvalError(f"unknown unary operator {expr.op}", expr.span)
        if isinstance(expr, A.Binary):
            op = expr.op
            if op == "and":
                left = self._eval(expr.left, world)
                return bool(left) and bool(self._eval(expr.right, world))
            if op == "or":
                left = self._eval(expr.left, world)
                return bool(left) or bool(self._eval(expr.right, world))
            left = self._eval(expr.left, world)
            right = self._eval(expr.right, world)
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                if right == 0:
                    raise EvalError("division by zero", expr.span)
                return left // right
            if op == "%":
                if right == 0:
                    raise EvalError("division by zero", expr.span)
                return left % right
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
            if op == "in":
                return left in right
            raise EvalError(f"unknown operator {op}", expr.span)
        if isinstance(expr, A.Call):
            args = [self._eval(arg, world) for arg in expr.args]
            return self._call(expr.name, args, world, expr.span)
        raise EvalError("unsupported expression", expr.span)

    def _call(self, name: str, args: list, world: dict, span: A.Span) -> Any:
        if name == "min":
            return min(args)
        if name == "max":
            return max(args)
        if name == "abs":
            return abs(args[0])
        if name == "minutesBetween":
            return int(args[1]) - int(args[0])
        if name in ("hoursBetween", "daysBetween"):
            divisor = 60 if name == "hoursBetween" else 1440
            return (int(args[1]) - int(args[0])) // divisor
        if name == "now":
            return int(world.get("now", 0))
        if name == "lastError":
            return str(world.get("__last_error__", ""))
        if name == "len":
            return len(args[0])
        if name == "contains":
            return str(args[1]) in str(args[0])
        if name == "startsWith":
            return str(args[0]).startswith(str(args[1]))
        if name == "weekday":
            # 0 = Monday, matching datetime.weekday()
            return (int(args[0]) // 1440 + 3) % 7
        if name == "formatTime":
            from ..runtime.engine import EPOCH
            return (EPOCH + timedelta(minutes=int(args[0]))).strftime("%Y-%m-%d %H:%M")
        if name == "hasPermission":
            perms = world.get("__permissions__", {})
            return args[1] in perms.get(args[0], set())
        if name == "countPenalties":
            return len(world.get("__penalties__", []))
        if name == "totalPenalties":
            return sum(int(p.get("amount", 0)) for p in world.get("__penalties__", []))
        if name == "isBlocked":
            customer = args[0] if args and isinstance(args[0], dict) else {}
            return customer.get("status") == "blocked"
        raise EvalError(f"unknown function {name}", span)

    # --------------------------------------------------------------- execute
    def execute_statements(self, stmts: list[A.Stmt], world: dict,
                           depth: int = 0) -> list[dict]:
        if depth > 20:
            raise EvalError("rule recursion limit reached")
        applied: list[dict] = []
        for stmt in stmts:
            if stmt.kind == "assign" and stmt.expr is not None:
                value = self.eval(stmt.expr, world)
                self._assign(stmt.target, value, world, stmt.span)
                applied.append({"target": stmt.target, "value": value})
            elif stmt.kind == "apply":
                nested = self._execute_rule(stmt.text, world, depth + 1)
                applied.extend(nested)
            elif stmt.kind == "assert" and stmt.expr is not None:
                if not bool(self.eval(stmt.expr, world)):
                    raise EvalError("assertion failed: " + fmt_expr(stmt.expr),
                                    stmt.span)
            elif stmt.kind == "emit":
                applied.append({"emit": stmt.text})
        return applied

    def _assign(self, target: str, value: Any, world: dict, span: A.Span) -> None:
        base, _, field_name = target.partition(".")
        record = world.get(base)
        if not isinstance(record, dict):
            raise EvalError(f"assignment target base {base!r} is not an entity", span)
        if not field_name:
            raise EvalError(f"assignment target {target!r} has no field", span)
        record[field_name] = value

    def _execute_rule(self, rule_name: str, world: dict, depth: int = 0) -> list[dict]:
        rule = self.program.rule(rule_name)
        if rule is None:
            raise EvalError(f"unknown rule {rule_name!r}")
        branch = rule.then if bool(self.eval(rule.when, world)) else rule.otherwise
        applied = self.execute_statements(branch, world, depth)
        if rule.ensures is not None and not bool(self.eval(rule.ensures, world)):
            raise EvalError(f"rule {rule_name} violated its ensures clause", rule.span)
        return applied

    def evaluate_rule(self, rule_name: str, world: dict) -> dict:
        applied = self._execute_rule(rule_name, world)
        return {"rule": rule_name, "assignments": applied}

    # ------------------------------------------------------------- scenarios
    def run_scenario(self, scenario: A.ScenarioDecl, simulation) -> ScenarioResult:
        result = ScenarioResult(name=scenario.name)
        world = simulation.world()

        try:
            for given in scenario.givens:
                value = self.eval(given.expr, world)
                if given.path == "now":
                    simulation.now = int(value)
                else:
                    simulation.set_path(given.path, value)
                world = simulation.world()
        except EvalError as exc:
            result.ok = False
            result.error = f"given failed: {exc}"
            return result

        for step in scenario.steps:
            try:
                args = [self.eval(arg, world) for arg in step.args]
            except EvalError as exc:
                result.ok = False
                result.failures.append(f"step {step.name}: {exc}")
                return result
            signature = OPS.get(step.name)
            kwargs: dict[str, Any] = {}
            if signature:
                for index, (param, _type) in enumerate(signature.params):
                    if index < len(args):
                        kwargs[param] = args[index]
            else:
                for index, value in enumerate(args):
                    kwargs[f"arg{index}"] = value
            op_result = simulation.apply(step.name, **kwargs)
            result.steps += 1
            result.trace.append({
                "step": step.name, "ok": op_result.ok,
                "error": op_result.error,
                "data": op_result.data,
            })
            world = simulation.world()
            world["__last_error__"] = simulation.last_error
            world["__penalties__"] = simulation.penalties
            self._check_state_transitions(simulation, result)
            self._check_invariants(world, step, result)

        world = simulation.world()
        world["__last_error__"] = simulation.last_error
        world["__penalties__"] = simulation.penalties
        for expect in scenario.expects:
            try:
                ok = bool(self.eval(expect, world))
            except EvalError as exc:
                ok = False
                result.failures.append(f"expect error: {exc}")
            if not ok:
                result.failures.append(f"expectation failed: {fmt_expr(expect)}")
        result.ok = not result.failures and not result.transition_violations
        return result

    def _check_state_transitions(self, simulation, result: ScenarioResult) -> None:
        seen = len(result.trace)
        for machine, src, dst, event in simulation.transitions:
            key = (machine, src, dst, event)
            if key not in self._transitions:
                message = f"forbidden transition {machine}: {src} -> {dst} on {event}"
                if message not in result.transition_violations:
                    result.transition_violations.append(message)

    def _check_invariants(self, world: dict, step: A.ScenarioStep,
                          result: ScenarioResult) -> None:
        for inv in self.program.invariants:
            try:
                ok = bool(self.eval(inv.expr, world))
            except EvalError:
                continue
            if not ok:
                message = f"{inv.name}: {inv.message or 'invariant violated'}"
                if message not in result.invariant_violations:
                    result.invariant_violations.append(message)

    # ------------------------------------------------------------ whole file
    def run_all_scenarios(self, simulation_factory=None) -> list[ScenarioResult]:
        results: list[ScenarioResult] = []
        for scenario in self.program.scenarios:
            if simulation_factory is None:
                from ..runtime.engine import Simulation
                simulation = Simulation.from_program(self.program)
            else:
                simulation = simulation_factory()
            results.append(self.run_scenario(scenario, simulation))
        return results


def evaluate_rule(program: A.Program, rule_name: str, world: dict) -> dict:
    interpreter = Interpreter(program)
    return interpreter.evaluate_rule(rule_name, world)
