"""Hash based incremental analysis.

Every specification node has a content hash and a list of requirement links.
A requirement edit bumps the requirement version; the analysis payload of a
node includes the versions of its linked requirements. On update only nodes
whose hash, links or requirement versions changed are recomputed, plus the
transitive closure of nodes that depend on them. Everything else is copied
from the cache.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from .nodes import SpecIndex, canonical, sha256_text


@dataclass
class AnalysisCache:
    results: dict[str, dict] = field(default_factory=dict)
    requirement_versions: dict[str, int] = field(default_factory=dict)

    def node_hashes(self) -> dict[str, str]:
        return {node_id: data["hash"] for node_id, data in self.results.items()}

    def to_dict(self) -> dict:
        return {"results": self.results,
                "requirement_versions": self.requirement_versions}

    def to_json(self) -> str:
        return canonical(self.to_dict())

    @staticmethod
    def from_json(text: str) -> "AnalysisCache":
        data = json.loads(text)
        return AnalysisCache(results=data.get("results", {}),
                             requirement_versions=data.get("requirement_versions", {}))


def analyze_node(node, requirement_versions: dict[str, int]) -> dict:
    versions = {req: int(requirement_versions.get(req, 0))
                for req in node.requirements}
    payload = {
        "hash": node.content_hash,
        "kind": node.kind,
        "name": node.name,
        "deps": list(node.deps),
        "requirements": list(node.requirements),
        "requirement_versions": versions,
        "status": "ok",
    }
    payload["result_hash"] = sha256_text(canonical(payload))
    return payload


def full_analysis(index: SpecIndex, requirement_versions: dict[str, int]) -> AnalysisCache:
    cache = AnalysisCache(requirement_versions=dict(requirement_versions))
    for node_id, node in sorted(index.nodes.items()):
        cache.results[node_id] = analyze_node(node, requirement_versions)
    return cache


def _changed_nodes(old: AnalysisCache, index: SpecIndex,
                   requirement_versions: dict[str, int]) -> set[str]:
    changed: set[str] = set()
    for node_id, node in index.nodes.items():
        previous = old.results.get(node_id)
        if previous is None:
            changed.add(node_id)
            continue
        if previous.get("hash") != node.content_hash:
            changed.add(node_id)
            continue
        if tuple(previous.get("requirements", ())) != tuple(node.requirements):
            changed.add(node_id)
            continue
        for req in node.requirements:
            if int(previous.get("requirement_versions", {}).get(req, 0)) != int(
                    requirement_versions.get(req, 0)):
                changed.add(node_id)
                break
    return changed


def incremental_update(old: AnalysisCache, index: SpecIndex,
                       requirement_versions: dict[str, int]
                       ) -> tuple[AnalysisCache, list[str]]:
    changed = _changed_nodes(old, index, requirement_versions)
    affected = index.dependents(changed)
    new_cache = AnalysisCache(requirement_versions=dict(requirement_versions))
    for node_id, node in sorted(index.nodes.items()):
        if node_id in affected:
            new_cache.results[node_id] = analyze_node(node, requirement_versions)
        elif node_id in old.results:
            new_cache.results[node_id] = old.results[node_id]
        else:
            new_cache.results[node_id] = analyze_node(node, requirement_versions)
    recomputed = sorted(affected)
    return new_cache, recomputed


def verify_incremental(old: AnalysisCache, index: SpecIndex,
                       requirement_versions: dict[str, int]) -> dict:
    incremental, recomputed = incremental_update(old, index, requirement_versions)
    full = full_analysis(index, requirement_versions)
    equal = canonical(incremental.results) == canonical(full.results)
    total = max(1, len(index.nodes))
    return {
        "equal": equal,
        "recomputed": recomputed,
        "recomputed_count": len(recomputed),
        "node_count": len(index.nodes),
        "percent": round(100.0 * len(recomputed) / total, 2),
        "cache": incremental,
    }
