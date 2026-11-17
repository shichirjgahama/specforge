"""Hand written lexer for the SpecForge DSL.

No parser generator and no regex-based structural parsing. Regular expressions
are used only for the two service constructs allowed by the assignment:
identifiers and integer literals. Everything else (symbols, strings, comments,
positions) is scanned by hand.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .diagnostics import Diagnostic, DiagnosticBag


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER_RE = re.compile(r"[0-9]+")


KEYWORDS = {
    "spec", "version", "entity", "enum", "role", "state", "rule", "invariant",
    "scenario", "given", "step", "expect", "link", "when", "then", "else",
    "ensures", "do", "priority", "may", "forbid", "const", "apply", "assert",
    "emit", "true", "false", "and", "or", "not", "in", "initial", "require",
    "message", "always", "returns", "let",
}

# Multi character symbols must be tried before single character ones.
SYMBOLS = [
    "->", ":=", "==", "!=", "<=", ">=", "&&", "||", "+=", "-=", "..",
    "{", "}", "(", ")", "[", "]", ";", ":", ",", ".", "<", ">", "+", "-",
    "*", "/", "%", "=", "!", "?",
]

SINGLE_CHAR_INDEX = {ch: True for ch in "{}()[];:,.<>+-*/%=!?"}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    col: int
    offset: int
    end_offset: int

    def is_punct(self, value: str) -> bool:
        return self.kind == "punct" and self.value == value

    def is_ident(self, value: str | None = None) -> bool:
        if self.kind != "ident":
            return False
        return value is None or self.value == value


class Lexer:
    def __init__(self, source: str, filename: str = "<spec>") -> None:
        if source.startswith("\ufeff"):
            source = source[1:]
        self.source = source
        self.filename = filename
        self.length = len(source)
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []
        self.bag = DiagnosticBag(source=filename)

    # ------------------------------------------------------------- helpers
    def _advance(self, count: int = 1) -> None:
        src = self.source
        for _ in range(count):
            if self.pos >= self.length:
                return
            if src[self.pos] == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
            self.pos += 1

    def _advance_text(self, text: str) -> None:
        # Text never contains newlines except block comments, handled separately.
        self.pos += len(text)
        self.col += len(text)

    def _add(self, kind: str, value: str, line: int, col: int,
             start: int) -> None:
        self.tokens.append(Token(kind, value, line, col, start, self.pos))

    # ------------------------------------------------------------- scanning
    def tokenize(self) -> tuple[list[Token], list[Diagnostic]]:
        src = self.source
        while self.pos < self.length:
            ch = src[self.pos]
            if ch in " \t\r\n":
                self._advance()
                continue

            # line comments
            if ch == "#" or (ch == "/" and self.pos + 1 < self.length
                             and src[self.pos + 1] == "/"):
                while self.pos < self.length and src[self.pos] != "\n":
                    self._advance()
                continue

            # block comment
            if ch == "/" and self.pos + 1 < self.length and src[self.pos + 1] == "*":
                start_line, start_col = self.line, self.col
                self._advance(2)
                closed = False
                while self.pos < self.length:
                    if (src[self.pos] == "*" and self.pos + 1 < self.length
                            and src[self.pos + 1] == "/"):
                        self._advance(2)
                        closed = True
                        break
                    self._advance()
                if not closed:
                    self.bag.error("E003", "unterminated block comment",
                                   start_line, start_col, 2)
                continue

            start = self.pos
            line, col = self.line, self.col

            # string literal
            if ch == '"':
                self._advance()
                buf: list[str] = []
                closed = False
                while self.pos < self.length:
                    cur = src[self.pos]
                    if cur == "\\" and self.pos + 1 < self.length:
                        nxt = src[self.pos + 1]
                        mapping = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                        buf.append(mapping.get(nxt, nxt))
                        self._advance(2)
                        continue
                    if cur == '"':
                        self._advance()
                        closed = True
                        break
                    if cur == "\n":
                        break
                    buf.append(cur)
                    self._advance()
                if not closed:
                    self.bag.error("E001", "unterminated string literal",
                                   line, col, max(1, self.pos - start))
                self._add("string", "".join(buf), line, col, start)
                continue

            # identifier or keyword
            match = IDENT_RE.match(src, self.pos)
            if match:
                text = match.group(0)
                self._advance_text(text)
                # Requirement / change request / test identifiers and business
                # rule ids are single tokens: R-001, CR-002, BRI-04, INV-01.
                # Only all uppercase identifiers are joined, a regular
                # identifier keeps its normal form.
                prefix = text
                if (prefix.isupper() and prefix.isalpha() and self.pos + 1 < self.length
                        and src[self.pos] == "-"
                        and src[self.pos + 1].isdigit()):
                    self._advance()  # '-'
                    digits_start = self.pos
                    while self.pos < self.length and src[self.pos].isdigit():
                        self._advance()
                    text = prefix + "-" + src[digits_start:self.pos]
                    self._add("ref", text, line, col, start)
                    continue
                kind = "keyword" if text in KEYWORDS else "ident"
                self._add(kind, text, line, col, start)
                continue

            # integer literal
            match = NUMBER_RE.match(src, self.pos)
            if match:
                text = match.group(0)
                self._advance_text(text)
                self._add("number", text, line, col, start)
                continue

            # symbols, longest match first
            matched = False
            for sym in SYMBOLS:
                if src.startswith(sym, self.pos):
                    self._advance_text(sym)
                    self._add("punct", sym, line, col, start)
                    matched = True
                    break
            if matched:
                continue

            # unknown character: report and skip, keep lexing
            self._advance()
            self.bag.error(
                "E002", f"unexpected character {ch!r}", line, col, 1,
                hint="allowed symbols are listed in docs/dsl.md",
            )

        self.tokens.append(Token("eof", "", self.line, self.col, self.pos, self.pos))
        return self.tokens, self.bag.sorted()


def tokenize(source: str, filename: str = "<spec>") -> tuple[list[Token], list[Diagnostic]]:
    return Lexer(source, filename).tokenize()
