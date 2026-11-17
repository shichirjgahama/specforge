"""Diagnostics with stable codes and source positions.

Position convention: 1-based line and column, matching editors.
All diagnostics are sortable so that two runs produce byte-identical reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    line: int = 1
    col: int = 1
    length: int = 1
    severity: str = "error"
    source: str = "<spec>"
    hint: str = ""
    category: str = "syntax"

    @property
    def sort_key(self) -> tuple:
        return (self.line, self.col, self.code, self.message)

    def format(self) -> str:
        base = (
            f"{self.source}:{self.line}:{self.col}: {self.severity} "
            f"{self.code}: {self.message}"
        )
        if self.hint:
            base += f" (hint: {self.hint})"
        return base

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "col": self.col,
            "length": self.length,
            "severity": self.severity,
            "source": self.source,
            "hint": self.hint,
            "category": self.category,
        }

    @staticmethod
    def from_dict(data: dict) -> "Diagnostic":
        return Diagnostic(
            code=data["code"],
            message=data["message"],
            line=data.get("line", 1),
            col=data.get("col", 1),
            length=data.get("length", 1),
            severity=data.get("severity", "error"),
            source=data.get("source", "<spec>"),
            hint=data.get("hint", ""),
            category=data.get("category", "syntax"),
        )


def sort_diagnostics(items: Iterable[Diagnostic]) -> list[Diagnostic]:
    return sorted(items, key=lambda d: d.sort_key)


def has_errors(items: Iterable[Diagnostic]) -> bool:
    return any(d.severity == "error" for d in items)


def count_by_severity(items: Iterable[Diagnostic]) -> dict:
    result = {"error": 0, "warning": 0, "info": 0}
    for item in items:
        result[item.severity] = result.get(item.severity, 0) + 1
    return result


def format_many(items: Iterable[Diagnostic]) -> str:
    return "\n".join(d.format() for d in sort_diagnostics(items))


@dataclass
class DiagnosticBag:
    """Collects diagnostics, preserving insertion order until sorted."""

    source: str = "<spec>"
    items: list[Diagnostic] = field(default_factory=list)

    def error(self, code: str, message: str, line: int, col: int,
              length: int = 1, hint: str = "", category: str = "syntax") -> None:
        self.items.append(Diagnostic(
            code=code, message=message, line=line, col=col, length=length,
            severity="error", source=self.source, hint=hint, category=category,
        ))

    def warning(self, code: str, message: str, line: int, col: int,
                length: int = 1, hint: str = "", category: str = "syntax") -> None:
        self.items.append(Diagnostic(
            code=code, message=message, line=line, col=col, length=length,
            severity="warning", source=self.source, hint=hint, category=category,
        ))

    def info(self, code: str, message: str, line: int, col: int,
             length: int = 1, hint: str = "", category: str = "syntax") -> None:
        self.items.append(Diagnostic(
            code=code, message=message, line=line, col=col, length=length,
            severity="info", source=self.source, hint=hint, category=category,
        ))

    def extend(self, other: Iterable[Diagnostic]) -> None:
        self.items.extend(other)

    def sorted(self) -> list[Diagnostic]:
        return sort_diagnostics(self.items)

    def has_errors(self) -> bool:
        return has_errors(self.items)
