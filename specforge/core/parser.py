"""Recursive descent parser with panic mode error recovery.

The parser never stops at the first error. Every declaration and every
statement is parsed in a recovery scope: a failing construct is reported once,
then the parser skips to the next `;` or closing brace at the same nesting
level and continues with the next declaration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import ast_nodes as A
from .diagnostics import Diagnostic, DiagnosticBag
from .lexer import Token, tokenize


class _Recover(Exception):
    """Internal control flow: abandon the current construct."""


@dataclass
class ParseResult:
    program: A.Program
    diagnostics: list[Diagnostic] = field(default_factory=list)
    tokens: list[Token] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)


COMPARISON_OPS = {"==", "!=", "<", "<=", ">", ">=", "in"}


class Parser:
    def __init__(self, source: str, filename: str = "<spec>") -> None:
        self.source = source
        self.filename = filename
        self.tokens, lex_diagnostics = tokenize(source, filename)
        self.bag = DiagnosticBag(source=filename)
        self.bag.extend(lex_diagnostics)
        self.diagnostics: list[Diagnostic] = self.bag.items
        self.i = 0
        self.program = A.Program(source=source, filename=filename)
        self._last_link_target = None  # (object, node_id)

    # ------------------------------------------------------------ utilities
    def _tok(self, offset: int = 0) -> Token:
        idx = min(self.i + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self._tok()
        if self.i < len(self.tokens) - 1:
            self.i += 1
        return tok

    def _at(self, value: str) -> bool:
        tok = self._tok()
        return tok.value == value and tok.kind in ("punct", "keyword", "ident", "ref")

    def _at_kind(self, kind: str) -> bool:
        return self._tok().kind == kind

    def _accept(self, value: str) -> bool:
        if self._at(value):
            self._advance()
            return True
        return False

    def _span(self, start: Token) -> A.Span:
        prev = self.tokens[max(0, self.i - 1)]
        return A.Span(
            line=start.line, col=start.col,
            end_line=prev.line,
            end_col=prev.col + max(0, len(prev.value)),
        )

    def _fail(self, code: str, message: str, token: Token | None = None,
              hint: str = "") -> None:
        tok = token or self._tok()
        self.bag.error(code, message, tok.line, tok.col,
                       max(1, len(tok.value)), hint=hint)
        raise _Recover()

    def _require(self, value: str, hint: str = "") -> Token:
        if self._at(value):
            return self._advance()
        tok = self._tok()
        self.bag.error(
            "E010", f"expected {value!r} but found {tok.value or 'end of file'!r}",
            tok.line, tok.col, max(1, len(tok.value)), hint=hint,
        )
        raise _Recover()

    def _require_ident(self, what: str = "identifier") -> Token:
        tok = self._tok()
        if tok.kind in ("ident", "ref", "keyword"):
            return self._advance()
        self.bag.error(
            "E011", f"expected {what} but found {tok.value or 'end of file'!r}",
            tok.line, tok.col, max(1, len(tok.value)),
        )
        raise _Recover()

    def _semicolon(self, hint: str = "statements end with ';'") -> None:
        if self._accept(";"):
            return
        tok = self._tok()
        self.bag.error(
            "E015", f"missing ';' before {tok.value or 'end of file'!r}",
            tok.line, tok.col, max(1, len(tok.value)), hint=hint,
        )

    def _synchronize(self) -> None:
        """Skip to a safe point: end of statement or enclosing brace."""
        depth = 0
        moved = False
        while True:
            tok = self._tok()
            if tok.kind == "eof":
                return
            if depth == 0 and moved and tok.kind in ("keyword", "ident"):
                if tok.value in {"entity", "enum", "role", "state", "rule",
                                 "invariant", "scenario", "const", "spec"}:
                    return
            if tok.value == "{":
                depth += 1
            elif tok.value == "}":
                if depth == 0:
                    return
                depth -= 1
            elif tok.value == ";" and depth == 0:
                self._advance()
                return
            self._advance()
            moved = True

    # ---------------------------------------------------------------- entry
    def parse(self) -> ParseResult:
        try:
            self._parse_header()
        except _Recover:
            self._synchronize()

        while not self._at_kind("eof"):
            before = self.i
            try:
                self._parse_decl()
            except _Recover:
                self._synchronize()
            if self.i == before:
                # no progress, force one token forward to avoid a loop
                self._advance()

        self.diagnostics = self.bag.sorted()
        return ParseResult(self.program, self.diagnostics, self.tokens)

    def _parse_header(self) -> None:
        start = self._require("spec", hint="a program starts with: spec Name version 1;")
        name_tok = self._require_ident("specification name")
        self._require("version")
        num = self._tok()
        if num.kind != "number":
            self._fail("E016", f"version must be an integer, found {num.value!r}", num)
        self._advance()
        self._semicolon()
        self.program.header = A.Header(
            name=name_tok.value, version=int(num.value), span=self._span(start)
        )

    # ----------------------------------------------------------- declarations
    def _parse_decl(self) -> None:
        tok = self._tok()
        value = tok.value
        start = tok
        if tok.kind == "punct" and value in (";", "}"):
            self._advance()
            self.bag.error(
                "E017", f"unexpected {value!r} at top level", tok.line, tok.col, 1,
            )
            return
        if value == "const":
            self._parse_const(start)
        elif value == "entity":
            self._parse_entity(start)
        elif value == "enum":
            self._parse_enum(start)
        elif value == "role":
            self._parse_role(start)
        elif value == "state":
            self._parse_state(start)
        elif value == "rule":
            self._parse_rule(start)
        elif value == "invariant":
            self._parse_invariant(start)
        elif value == "scenario":
            self._parse_scenario(start)
        elif value == "link":
            self._parse_link()
        elif tok.kind == "eof":
            return
        else:
            self.bag.error(
                "E012", f"unknown declaration {value!r}", tok.line, tok.col,
                max(1, len(value)),
                hint="expected const, entity, enum, role, state, rule, invariant or scenario",
            )
            raise _Recover()

        # optional link statement directly after a declaration
        while self._at("link"):
            self._parse_link()

    # ------------------------------------------------------------------ const
    def _parse_const(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("constant name")
        self._require(":")
        type_ref = self._parse_type()
        self._require("=")
        expr = self._parse_expr()
        self._semicolon()
        decl = A.ConstDecl(name=name_tok.value, type=type_ref, value=expr,
                           span=self._span(start))
        self.program.consts.append(decl)
        self._last_link_target = (decl, f"const:{decl.name}")

    # ----------------------------------------------------------------- entity
    def _parse_entity(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("entity name")
        self._require("{", hint="entity body: { field: Type; ... }")
        fields: list[A.FieldDecl] = []
        while not self._at("}") and not self._at_kind("eof"):
            before = self.i
            try:
                field = self._parse_field()
                if field is not None:
                    fields.append(field)
            except _Recover:
                self._synchronize()
            if self.i == before:
                self._advance()
        self._require("}")
        self._accept(";")
        decl = A.EntityDecl(name=name_tok.value, fields=fields,
                            span=self._span(start))
        self.program.entities.append(decl)
        for field in fields:
            if not field.name:
                field.name = f"<field{len(fields)}>"
        self._last_link_target = (decl, f"entity:{decl.name}")

    def _parse_field(self) -> Optional[A.FieldDecl]:
        if self._at("link"):
            return None
        start = self._tok()
        name_tok = self._require_ident("field name")
        self._require(":")
        type_ref = self._parse_type()
        constraints: list[A.Constraint] = []
        while True:
            if self._at("["):
                constraints.append(self._parse_range())
            elif self._at("in"):
                self._advance()
                constraints.append(self._parse_set_constraint())
            elif self._at(">=") or self._at(">") or self._at("<=") or self._at("<"):
                op = self._advance().value
                num = self._tok()
                if num.kind != "number":
                    self._fail("E018", "constraint bound must be an integer", num)
                self._advance()
                kind = {"<=": "max", "<": "max", ">=": "min", ">": "min"}[op]
                constraints.append(A.Constraint(kind=kind, low=int(num.value),
                                                span=self._span(start)))
            else:
                break
        default = None
        if self._accept("="):
            default = self._parse_expr()
        self._semicolon()
        return A.FieldDecl(name=name_tok.value, type=type_ref,
                           constraints=constraints, default=default,
                           span=self._span(start))

    def _parse_range(self) -> A.Constraint:
        start = self._require("[")
        low = self._tok()
        if low.kind != "number":
            self._fail("E018", "range lower bound must be an integer", low)
        self._advance()
        self._require("..", hint="range syntax: [0..100]")
        high = self._tok()
        if high.kind != "number":
            self._fail("E018", "range upper bound must be an integer", high)
        self._advance()
        self._require("]")
        return A.Constraint(kind="range", low=int(low.value), high=int(high.value),
                            span=self._span(start))

    def _parse_set_constraint(self) -> A.Constraint:
        start = self._require("{")
        values: list[str] = []
        while not self._at("}") and not self._at_kind("eof"):
            tok = self._tok()
            if tok.kind not in ("ident", "keyword", "ref", "string"):
                self._fail("E019", "set constraint accepts identifiers only", tok)
            values.append(tok.value)
            self._advance()
            if not self._accept(","):
                break
        self._require("}")
        return A.Constraint(kind="set", values=values, span=self._span(start))

    # ------------------------------------------------------------------- enum
    def _parse_enum(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("enum name")
        self._require("{")
        members: list[str] = []
        member_spans: dict[str, A.Span] = {}
        while not self._at("}") and not self._at_kind("eof"):
            tok = self._tok()
            if tok.kind not in ("ident", "keyword"):
                self.bag.error("E020", "enum member must be an identifier",
                               tok.line, tok.col, max(1, len(tok.value)))
                self._advance()
                continue
            members.append(tok.value)
            member_spans[tok.value] = self._span(tok)
            self._advance()
            if not self._accept(","):
                break
        self._require("}")
        self._accept(";")
        decl = A.EnumDecl(name=name_tok.value, members=members,
                          member_spans=member_spans, span=self._span(start))
        self.program.enums.append(decl)
        self._last_link_target = (decl, f"enum:{decl.name}")

    # ------------------------------------------------------------------- role
    def _parse_role(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("role name")
        self._require("{")
        may: list[str] = []
        forbid: list[str] = []
        while not self._at("}") and not self._at_kind("eof"):
            tok = self._tok()
            if tok.value not in ("may", "forbid"):
                self.bag.error("E021", "role body accepts 'may' or 'forbid' lists",
                               tok.line, tok.col, max(1, len(tok.value)))
                self._synchronize()
                continue
            bucket = may if tok.value == "may" else forbid
            self._advance()
            while True:
                op = self._require_ident("permission name")
                bucket.append(op.value)
                if not self._accept(","):
                    break
            self._semicolon()
        self._require("}")
        self._accept(";")
        decl = A.RoleDecl(name=name_tok.value, may=may, forbid=forbid,
                          span=self._span(start))
        self.program.roles.append(decl)
        self._last_link_target = (decl, f"role:{decl.name}")

    # ------------------------------------------------------------------ state
    def _parse_state(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("state machine name")
        self._require("{", hint="state body: initial X; A -> B : event when ...;")
        decl = A.StateDecl(name=name_tok.value, span=self._span(start))
        last_edge: Optional[A.EdgeDecl] = None
        while not self._at("}") and not self._at_kind("eof"):
            before = self.i
            try:
                if self._at("initial"):
                    self._advance()
                    tok = self._require_ident("initial state")
                    decl.initial = tok.value
                    self._semicolon()
                elif self._at("link"):
                    link = self._parse_link()
                    target = last_edge if last_edge is not None else decl
                    target.links.extend(link.requirements)
                    link.target_node = (f"transition:{decl.name}:{last_edge.source}:{last_edge.event}"
                                        if last_edge is not None
                                        else f"state:{decl.name}")
                else:
                    edge = self._parse_edge()
                    decl.edges.append(edge)
                    last_edge = edge
            except _Recover:
                self._synchronize()
            if self.i == before:
                self._advance()
        self._require("}")
        self._accept(";")
        decl.span = self._span(start)
        self.program.states.append(decl)
        self._last_link_target = (decl, f"state:{decl.name}")

    def _parse_edge(self) -> A.EdgeDecl:
        start = self._tok()
        src = self._require_ident("source state")
        self._require("->", hint="transition syntax: available -> rented : rent when ...;")
        dst = self._require_ident("target state")
        self._require(":")
        event = self._require_ident("event name")
        guard = None
        if self._accept("when"):
            guard = self._parse_expr()
        actions: list[A.Stmt] = []
        if self._accept("do"):
            actions = self._parse_action_block()
        self._semicolon()
        return A.EdgeDecl(source=src.value, target=dst.value, event=event.value,
                          guard=guard, actions=actions, span=self._span(start))

    def _parse_action_block(self) -> list[A.Stmt]:
        actions: list[A.Stmt] = []
        if self._accept("{"):
            while not self._at("}") and not self._at_kind("eof"):
                before = self.i
                try:
                    actions.append(self._parse_stmt())
                except _Recover:
                    self._synchronize()
                if self.i == before:
                    self._advance()
            self._require("}")
            return actions
        actions.append(self._parse_stmt())
        return actions

    # ---------------------------------------------------------------- statements
    def _parse_stmt(self) -> A.Stmt:
        start = self._tok()
        if self._at("apply"):
            self._advance()
            rule = self._require_ident("rule name")
            self._semicolon()
            return A.Stmt(kind="apply", text=rule.value, span=self._span(start))
        if self._at("assert"):
            self._advance()
            expr = self._parse_expr()
            self._semicolon()
            return A.Stmt(kind="assert", expr=expr, span=self._span(start))
        if self._at("emit"):
            self._advance()
            tok = self._tok()
            if tok.kind != "string":
                self._fail("E022", "emit expects a string literal", tok)
            self._advance()
            self._semicolon()
            return A.Stmt(kind="emit", text=tok.value, span=self._span(start))

        target = self._parse_path()
        if self._accept(":=") or self._accept("="):
            expr = self._parse_expr()
            self._semicolon()
            return A.Stmt(kind="assign", target=target, expr=expr,
                          span=self._span(start))
        self._fail(
            "E023", f"expected ':=' assignment but found {self._tok().value!r}",
            hint="statements are: path := expr; apply Rule; assert expr; emit \"text\";",
        )
        raise _Recover()

    def _parse_path(self) -> str:
        tok = self._require_ident("field path")
        parts = [tok.value]
        while self._accept("."):
            parts.append(self._require_ident("field name").value)
        return ".".join(parts)

    # ------------------------------------------------------------------- rule
    def _parse_rule(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("rule name")
        priority = 0
        if self._accept("priority"):
            num = self._tok()
            if num.kind != "number":
                self._fail("E024", "priority must be an integer", num)
            self._advance()
            priority = int(num.value)
            self._accept(";")
        self._require("{", hint="rule body: { when ... then {...} else {...} ensures ...; }")
        if self._accept("priority"):
            num = self._tok()
            if num.kind != "number":
                self._fail("E024", "priority must be an integer", num)
            self._advance()
            priority = int(num.value)
            self._accept(";")
        self._require("when")
        when = self._parse_expr()
        self._require("then")
        then_stmts = self._parse_stmt_list({"else", "ensures", "}"})
        else_stmts: list[A.Stmt] = []
        if self._accept("else"):
            else_stmts = self._parse_stmt_list({"ensures", "}"})
        ensures = None
        if self._accept("ensures"):
            ensures = self._parse_expr()
            self._semicolon()
        self._require("}")
        self._accept(";")
        decl = A.RuleDecl(name=name_tok.value, priority=priority, when=when,
                          then=then_stmts, otherwise=else_stmts,
                          ensures=ensures, span=self._span(start))
        self.program.rules.append(decl)
        self._last_link_target = (decl, f"rule:{decl.name}")

    def _parse_stmt_list(self, stop: set[str]) -> list[A.Stmt]:
        stmts: list[A.Stmt] = []
        if self._accept("{"):
            while not self._at("}") and not self._at_kind("eof"):
                before = self.i
                try:
                    stmts.append(self._parse_stmt())
                except _Recover:
                    self._synchronize()
                if self.i == before:
                    self._advance()
            self._require("}")
            return stmts
        while not self._at_kind("eof") and self._tok().value not in stop:
            before = self.i
            try:
                stmts.append(self._parse_stmt())
            except _Recover:
                self._synchronize()
            if self.i == before:
                self._advance()
        return stmts

    # -------------------------------------------------------------- invariant
    def _parse_invariant(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("invariant name")
        self._require("always")
        expr = self._parse_expr()
        message = ""
        if self._accept("message"):
            tok = self._tok()
            if tok.kind != "string":
                self._fail("E025", "invariant message must be a string literal", tok)
            message = tok.value
            self._advance()
        self._semicolon()
        decl = A.InvariantDecl(name=name_tok.value, expr=expr, message=message,
                               span=self._span(start))
        self.program.invariants.append(decl)
        self._last_link_target = (decl, f"invariant:{decl.name}")

    # --------------------------------------------------------------- scenario
    def _parse_scenario(self, start: Token) -> None:
        self._advance()
        name_tok = self._require_ident("scenario name")
        self._require("{", hint="scenario body: given path = value; step op(...); expect expr;")
        decl = A.ScenarioDecl(name=name_tok.value, span=self._span(start))
        while not self._at("}") and not self._at_kind("eof"):
            before = self.i
            try:
                if self._at("given"):
                    gstart = self._advance()
                    path = self._parse_path()
                    if not (self._accept("=") or self._accept(":=")):
                        self._fail("E026", "given expects '=' before a value")
                    expr = self._parse_expr()
                    self._semicolon()
                    decl.givens.append(A.GivenBinding(path=path, expr=expr,
                                                      span=self._span(gstart)))
                elif self._at("step"):
                    sstart = self._advance()
                    op = self._require_ident("operation name")
                    args: list[A.Expr] = []
                    self._require("(")
                    if not self._at(")"):
                        while True:
                            args.append(self._parse_expr())
                            if not self._accept(","):
                                break
                    self._require(")")
                    self._semicolon()
                    decl.steps.append(A.ScenarioStep(name=op.value, args=args,
                                                     span=self._span(sstart)))
                elif self._at("expect"):
                    self._advance()
                    decl.expects.append(self._parse_expr())
                    self._semicolon()
                else:
                    tok = self._tok()
                    self._fail("E027",
                               f"scenario body accepts given/step/expect, found {tok.value!r}",
                               tok)
            except _Recover:
                self._synchronize()
            if self.i == before:
                self._advance()
        self._require("}")
        self._accept(";")
        decl.span = self._span(start)
        self.program.scenarios.append(decl)
        self._last_link_target = (decl, f"scenario:{decl.name}")

    # ------------------------------------------------------------------- link
    def _parse_link(self) -> A.RequirementLink:
        start = self._require("link")
        refs: list[str] = []
        while True:
            tok = self._tok()
            if tok.kind not in ("ref", "ident", "string"):
                self._fail("E028", "link expects requirement identifiers like R-001", tok)
            refs.append(tok.value)
            self._advance()
            if not self._accept(","):
                break
        self._semicolon()
        link = A.RequirementLink(requirements=refs, span=self._span(start))
        self.program.links.append(link)
        if self._last_link_target is not None:
            target, node_id = self._last_link_target
            target.links.extend(refs)
            link.target_node = node_id
        return link

    # ------------------------------------------------------------ expressions
    def _parse_expr(self) -> A.Expr:
        return self._parse_or()

    def _parse_or(self) -> A.Expr:
        left = self._parse_and()
        while self._at("or") or self._at("||"):
            tok = self._advance()
            right = self._parse_and()
            left = A.Binary(op="or", left=left, right=right,
                            span=A.Span(left.span.line, left.span.col,
                                        right.span.end_line, right.span.end_col))
        return left

    def _parse_and(self) -> A.Expr:
        left = self._parse_not()
        while self._at("and") or self._at("&&"):
            tok = self._advance()
            right = self._parse_not()
            left = A.Binary(op="and", left=left, right=right,
                            span=A.Span(left.span.line, left.span.col,
                                        right.span.end_line, right.span.end_col))
        return left

    def _parse_not(self) -> A.Expr:
        if self._at("not") or self._at("!"):
            tok = self._advance()
            operand = self._parse_not()
            return A.Unary(op="not", operand=operand, span=self._span(tok))
        return self._parse_comparison()

    def _parse_comparison(self) -> A.Expr:
        left = self._parse_additive()
        while True:
            tok = self._tok()
            if tok.value not in COMPARISON_OPS:
                break
            op = self._advance().value
            if op == "in":
                right = self._parse_in_set()
            else:
                right = self._parse_additive()
            left = A.Binary(op=op, left=left, right=right,
                            span=A.Span(left.span.line, left.span.col,
                                        right.span.end_line, right.span.end_col))
        return left

    def _parse_in_set(self) -> A.Expr:
        start = self._tok()
        if self._accept("{"):
            items: list[A.Expr] = []
            if not self._at("}"):
                while True:
                    tok = self._tok()
                    if tok.kind in ("ident", "keyword"):
                        items.append(A.Name(name=tok.value, span=self._span(tok)))
                        self._advance()
                    elif tok.kind == "number":
                        items.append(A.Literal(value=int(tok.value), kind="int",
                                               span=self._span(tok)))
                        self._advance()
                    elif tok.kind == "string":
                        items.append(A.Literal(value=tok.value, kind="text",
                                               span=self._span(tok)))
                        self._advance()
                    else:
                        self._fail("E029", "invalid value in set literal", tok)
                    if not self._accept(","):
                        break
            self._require("}")
            return A.ListExpr(items=items, span=self._span(start))
        if self._accept("["):
            items = []
            if not self._at("]"):
                while True:
                    items.append(self._parse_expr())
                    if not self._accept(","):
                        break
            self._require("]")
            return A.ListExpr(items=items, span=self._span(start))
        return self._parse_additive()

    def _parse_additive(self) -> A.Expr:
        left = self._parse_multiplicative()
        while self._at("+") or self._at("-"):
            op = self._advance().value
            right = self._parse_multiplicative()
            left = A.Binary(op=op, left=left, right=right,
                            span=A.Span(left.span.line, left.span.col,
                                        right.span.end_line, right.span.end_col))
        return left

    def _parse_multiplicative(self) -> A.Expr:
        left = self._parse_unary()
        while self._at("*") or self._at("/") or self._at("%"):
            op = self._advance().value
            right = self._parse_unary()
            left = A.Binary(op=op, left=left, right=right,
                            span=A.Span(left.span.line, left.span.col,
                                        right.span.end_line, right.span.end_col))
        return left

    def _parse_unary(self) -> A.Expr:
        if self._at("-") or self._at("+"):
            tok = self._advance()
            operand = self._parse_unary()
            return A.Unary(op=tok.value, operand=operand, span=self._span(tok))
        return self._parse_postfix()

    def _parse_postfix(self) -> A.Expr:
        expr = self._parse_primary()
        while True:
            if self._accept("."):
                tok = self._tok()
                if tok.kind not in ("ident", "keyword"):
                    self._fail("E030", "expected field name after '.'", tok)
                self._advance()
                expr = A.FieldAccess(base=expr, field_name=tok.value,
                                     span=A.Span(expr.span.line, expr.span.col,
                                                 tok.line, tok.col + len(tok.value)))
            else:
                break
        return expr

    def _parse_primary(self) -> A.Expr:
        tok = self._tok()
        if tok.kind == "number":
            self._advance()
            return A.Literal(value=int(tok.value), kind="int", span=self._span(tok))
        if tok.kind == "string":
            self._advance()
            return A.Literal(value=tok.value, kind="text", span=self._span(tok))
        if tok.kind == "ref":
            self._advance()
            return A.Name(name=tok.value, span=self._span(tok))
        if tok.kind in ("ident", "keyword"):
            if tok.value == "true":
                self._advance()
                return A.Literal(value=True, kind="bool", span=self._span(tok))
            if tok.value == "false":
                self._advance()
                return A.Literal(value=False, kind="bool", span=self._span(tok))
            self._advance()
            name = A.Name(name=tok.value, span=self._span(tok))
            if self._accept("("):
                args: list[A.Expr] = []
                if not self._at(")"):
                    while True:
                        args.append(self._parse_expr())
                        if not self._accept(","):
                            break
                self._require(")")
                return A.Call(name=tok.value, args=args, span=self._span(tok))
            return name
        if self._accept("("):
            inner = self._parse_expr()
            self._require(")")
            return inner
        self._fail(
            "E013", f"expected expression but found {tok.value or 'end of file'!r}", tok,
            hint="literals, field paths, constants, function calls and operators are allowed",
        )
        raise _Recover()

    def _parse_type(self) -> A.TypeRef:
        start = self._tok()
        tok = self._tok()
        if tok.kind not in ("ident", "keyword"):
            self._fail("E031", f"expected type name but found {tok.value!r}", tok)
        self._advance()
        arg = None
        if self._accept("<"):
            arg_tok = self._require_ident("type argument")
            arg = arg_tok.value
            self._require(">")
        optional = self._accept("?")
        return A.TypeRef(name=tok.value, arg=arg, optional=optional,
                         span=self._span(start))


def parse(source: str, filename: str = "<spec>") -> ParseResult:
    return Parser(source, filename).parse()
