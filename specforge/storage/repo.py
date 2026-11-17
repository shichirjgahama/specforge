"""Repository over SQLite. No ORM, explicit SQL, deterministic JSON columns."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from ..core.incremental import AnalysisCache
from ..core.nodes import SpecIndex
from ..core.impact import ChangeRequest, ImpactPlan
from ..runtime.codegen import TestCase
from ..runtime.runner import RunSummary
from .migrations import current_version, migrate, utc_now


def default_db_path() -> Path:
    override = os.environ.get("SPECFORGE_DB")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "SpecForge" / "specforge.db"
    return Path.home() / ".local" / "share" / "SpecForge" / "specforge.db"


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


class Repository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        migrate(self.conn)

    def close(self) -> None:
        self.conn.close()

    @property
    def version(self) -> int:
        return current_version(self.conn)

    # ----------------------------------------------------------- requirements
    def count_requirements(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0])

    def requirements(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM requirements ORDER BY id"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["criteria"] = json.loads(item["criteria"])
            result.append(item)
        return result

    def requirement(self, requirement_id: str) -> Optional[dict]:
        items = [r for r in self.requirements() if r["id"] == requirement_id]
        return items[0] if items else None

    def save_requirement(self, data: dict) -> dict:
        existing = self.requirement(data["id"])
        version = int(existing["version"]) + 1 if existing else 1
        payload = {
            "id": data["id"],
            "title": data.get("title", ""),
            "story": data.get("story", ""),
            "criteria": list(data.get("criteria", [])),
            "kind": data.get("kind", "functional"),
            "priority": data.get("priority", "must"),
            "role": data.get("role", "Customer"),
            "status": data.get("status", "approved"),
            "notes": data.get("notes", ""),
            "version": version,
        }
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO requirements(id, version, title, story, criteria, kind,
                                     priority, role, status, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                version=excluded.version, title=excluded.title, story=excluded.story,
                criteria=excluded.criteria, kind=excluded.kind,
                priority=excluded.priority, role=excluded.role,
                status=excluded.status, notes=excluded.notes,
                updated_at=excluded.updated_at
            """,
            (payload["id"], version, payload["title"], payload["story"],
             _json(payload["criteria"]), payload["kind"], payload["priority"],
             payload["role"], payload["status"], payload["notes"], now),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO requirement_versions(requirement_id, version, "
            "payload, created_at) VALUES (?, ?, ?, ?)",
            (payload["id"], version, _json(payload), now),
        )
        self.conn.commit()
        return payload

    def requirement_versions(self, requirement_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT version, payload, created_at FROM requirement_versions "
            "WHERE requirement_id = ? ORDER BY version", (requirement_id,)
        ).fetchall()
        return [{"version": row["version"], "payload": json.loads(row["payload"]),
                 "created_at": row["created_at"]} for row in rows]

    def requirement_version_map(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT id, version FROM requirements").fetchall()
        return {row["id"]: int(row["version"]) for row in rows}

    # ------------------------------------------------------------------ specs
    def save_spec(self, content: str, filename: str, content_hash: str,
                  diagnostics: Iterable[dict] = (), nodes: Optional[SpecIndex] = None,
                  version: Optional[int] = None) -> int:
        latest = self.latest_spec()
        if version is None:
            version = int(latest["version"]) + 1 if latest else 1
        cursor = self.conn.execute(
            "INSERT INTO spec_versions(version, filename, content, content_hash, "
            "created_at, diagnostics) VALUES (?, ?, ?, ?, ?, ?)",
            (version, filename, content, content_hash, utc_now(),
             _json(list(diagnostics))),
        )
        spec_version_id = int(cursor.lastrowid)
        if nodes is not None:
            self.conn.executemany(
                "INSERT INTO spec_nodes(spec_version_id, node_id, kind, name, "
                "content_hash, requirements, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(spec_version_id, node.id, node.kind, node.name, node.content_hash,
                  _json(list(node.requirements)), _json(node.detail))
                 for node in nodes.nodes.values()],
            )
        self.conn.commit()
        return spec_version_id

    def latest_spec(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM spec_versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["diagnostics"] = json.loads(item.get("diagnostics") or "[]")
        return item

    def spec(self, spec_version_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM spec_versions WHERE id = ?", (spec_version_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["diagnostics"] = json.loads(item.get("diagnostics") or "[]")
        return item

    def spec_versions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, version, filename, content_hash, created_at FROM spec_versions "
            "ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def spec_nodes(self, spec_version_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM spec_nodes WHERE spec_version_id = ? ORDER BY node_id",
            (spec_version_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["requirements"] = json.loads(item["requirements"])
            item["detail"] = json.loads(item["detail"])
            result.append(item)
        return result

    # ------------------------------------------------------------------ tests
    def tests(self) -> list[TestCase]:
        rows = self.conn.execute("SELECT * FROM test_cases ORDER BY id").fetchall()
        result = []
        for row in rows:
            result.append(TestCase(
                id=row["id"], kind=row["kind"], title=row["title"],
                requirements=tuple(json.loads(row["requirements"])),
                nodes=tuple(json.loads(row["nodes"])),
                setup=json.loads(row["setup"]), steps=json.loads(row["steps"]),
                expected=json.loads(row["expected"]), seed=int(row["seed"]),
                source=row["source"],
            ))
        return result

    def save_tests(self, cases: Iterable[TestCase]) -> int:
        count = 0
        for case in cases:
            self.conn.execute(
                """
                INSERT INTO test_cases(id, kind, title, requirements, nodes, setup,
                                       steps, expected, seed, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind, title=excluded.title,
                    requirements=excluded.requirements, nodes=excluded.nodes,
                    setup=excluded.setup, steps=excluded.steps,
                    expected=excluded.expected, seed=excluded.seed,
                    source=excluded.source
                """,
                (case.id, case.kind, case.title, _json(list(case.requirements)),
                 _json(list(case.nodes)), _json(case.setup), _json(case.steps),
                 _json(case.expected), case.seed, case.source),
            )
            count += 1
        self.conn.commit()
        return count

    def count_tests(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM test_cases").fetchone()[0])

    # ------------------------------------------------------------------- runs
    def save_run(self, summary: RunSummary, spec_version_id: Optional[int],
                 started_at: Optional[str] = None) -> int:
        cursor = self.conn.execute(
            "INSERT INTO test_runs(started_at, spec_version_id, spec_hash, seed, "
            "passed, failed, digest) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (started_at or utc_now(), spec_version_id, summary.spec_hash,
             summary.seed, summary.passed, summary.failed, summary.digest),
        )
        run_id = int(cursor.lastrowid)
        self.conn.executemany(
            "INSERT INTO test_results(run_id, test_id, status, message, actual, "
            "duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
            [(run_id, result.test_id, result.status, result.message,
              _json(result.actual), result.duration_ms)
             for result in summary.results],
        )
        self.conn.commit()
        return run_id

    def runs(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM test_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def run_results(self, run_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM test_results WHERE run_id = ? ORDER BY test_id", (run_id,)
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["actual"] = json.loads(item["actual"])
            result.append(item)
        return result

    # ------------------------------------------------------- change requests
    def save_change_request(self, cr: ChangeRequest) -> None:
        self.conn.execute(
            """
            INSERT INTO change_requests(id, title, kind, description, payload,
                                        status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, kind=excluded.kind,
                description=excluded.description, payload=excluded.payload,
                status=excluded.status
            """,
            (cr.id, cr.title, cr.kind, cr.description, _json(cr.to_dict()),
             cr.status, cr.created_at or utc_now()),
        )
        self.conn.commit()

    def change_requests(self) -> list[ChangeRequest]:
        rows = self.conn.execute(
            "SELECT payload FROM change_requests ORDER BY id"
        ).fetchall()
        return [ChangeRequest.from_dict(json.loads(row["payload"])) for row in rows]

    def save_impact(self, plan: ImpactPlan, minimality: Optional[dict] = None) -> int:
        cursor = self.conn.execute(
            "INSERT INTO impact_reports(cr_id, created_at, plan, minimality) "
            "VALUES (?, ?, ?, ?)",
            (plan.cr_id, utc_now(), _json(plan.to_dict()), _json(minimality or {})),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def impact_reports(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM impact_reports ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["plan"] = json.loads(item["plan"])
            item["minimality"] = json.loads(item["minimality"])
            result.append(item)
        return result

    # ------------------------------------------------------------------ cache
    def save_cache(self, spec_hash: str, cache: AnalysisCache) -> None:
        self.conn.execute("DELETE FROM node_cache WHERE spec_hash = ?", (spec_hash,))
        self.conn.executemany(
            "INSERT INTO node_cache(spec_hash, node_id, payload) VALUES (?, ?, ?)",
            [(spec_hash, node_id, _json(payload))
             for node_id, payload in cache.results.items()],
        )
        self.conn.execute(
            "DELETE FROM node_cache WHERE spec_hash NOT IN ("
            "SELECT spec_hash FROM node_cache GROUP BY spec_hash ORDER BY "
            "MAX(rowid) DESC LIMIT 5)"
        )
        self.conn.commit()

    def load_cache(self, spec_hash: str) -> Optional[AnalysisCache]:
        rows = self.conn.execute(
            "SELECT node_id, payload FROM node_cache WHERE spec_hash = ?",
            (spec_hash,),
        ).fetchall()
        if not rows:
            return None
        results = {row["node_id"]: json.loads(row["payload"]) for row in rows}
        return AnalysisCache(results=results,
                             requirement_versions=self.requirement_version_map())

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict:
        def scalar(sql: str) -> int:
            return int(self.conn.execute(sql).fetchone()[0])
        return {
            "db_path": str(self.path),
            "schema_version": self.version,
            "requirements": scalar("SELECT COUNT(*) FROM requirements"),
            "spec_versions": scalar("SELECT COUNT(*) FROM spec_versions"),
            "spec_nodes": scalar("SELECT COUNT(DISTINCT node_id) FROM spec_nodes"),
            "tests": scalar("SELECT COUNT(*) FROM test_cases"),
            "runs": scalar("SELECT COUNT(*) FROM test_runs"),
            "change_requests": scalar("SELECT COUNT(*) FROM change_requests"),
            "impact_reports": scalar("SELECT COUNT(*) FROM impact_reports"),
        }
