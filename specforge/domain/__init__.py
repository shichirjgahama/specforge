"""Domain seed data: requirements and change request templates."""
from __future__ import annotations

from dataclasses import dataclass

from .requirements_data import REQUIREMENTS as _REQUIREMENTS


@dataclass
class Requirement:
    id: str
    title: str
    story: str
    criteria: list[str]
    kind: str = "functional"  # functional | exception | boundary
    priority: str = "must"
    role: str = "Customer"
    status: str = "approved"
    version: int = 1
    notes: str = ""

    def text(self) -> str:
        return f"{self.title}. {self.story}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "story": self.story,
            "criteria": list(self.criteria),
            "kind": self.kind,
            "priority": self.priority,
            "role": self.role,
            "status": self.status,
            "version": self.version,
            "notes": self.notes,
        }


def load_requirements() -> list[Requirement]:
    return [Requirement(**item) for item in _REQUIREMENTS]


def requirement_map() -> dict[str, Requirement]:
    return {item.id: item for item in load_requirements()}


def counts() -> dict:
    items = load_requirements()
    return {
        "total": len(items),
        "exceptions": sum(1 for i in items if i.kind == "exception"),
        "boundary": sum(1 for i in items if i.kind == "boundary"),
        "functional": sum(1 for i in items if i.kind == "functional"),
    }
