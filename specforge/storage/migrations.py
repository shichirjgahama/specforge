"""Versioned SQLite schema without alembic.

schema_version holds one row per applied migration. Migrations are plain Python
functions executed in order, each in a transaction. Opening a v1 database and
migrating to v3 keeps all rows intact.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable

LATEST_VERSION = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def current_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0]) if row and row[0] is not None else 0


def _migration_1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE requirements (
            id TEXT PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            story TEXT NOT NULL,
            criteria TEXT NOT NULL DEFAULT '[]',
            kind TEXT NOT NULL DEFAULT 'functional',
            priority TEXT NOT NULL DEFAULT 'must',
            role TEXT NOT NULL DEFAULT 'Customer',
            status TEXT NOT NULL DEFAULT 'approved',
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE requirement_versions (
            requirement_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (requirement_id, version)
        );

        CREATE TABLE spec_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE spec_nodes (
            spec_version_id INTEGER NOT NULL,
            node_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            requirements TEXT NOT NULL DEFAULT '[]',
            detail TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (spec_version_id, node_id)
        );

        CREATE TABLE test_cases (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            requirements TEXT NOT NULL DEFAULT '[]',
            nodes TEXT NOT NULL DEFAULT '[]',
            setup TEXT NOT NULL DEFAULT '{}',
            steps TEXT NOT NULL DEFAULT '[]',
            expected TEXT NOT NULL DEFAULT '{}',
            seed INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'generated'
        );

        CREATE TABLE test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            spec_version_id INTEGER,
            spec_hash TEXT NOT NULL,
            seed INTEGER NOT NULL,
            passed INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            digest TEXT NOT NULL
        );

        CREATE TABLE test_results (
            run_id INTEGER NOT NULL,
            test_id TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            actual TEXT NOT NULL DEFAULT '{}',
            duration_ms REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, test_id)
        );
        """
    )


def _migration_2(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE change_requests (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );

        CREATE TABLE impact_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cr_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            plan TEXT NOT NULL,
            minimality TEXT NOT NULL DEFAULT '{}'
        );
        """
    )


def _migration_3(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE node_cache (
            spec_hash TEXT NOT NULL,
            node_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY (spec_hash, node_id)
        );

        CREATE INDEX idx_test_results_test ON test_results(test_id);
        CREATE INDEX idx_spec_nodes_kind ON spec_nodes(kind);
        CREATE INDEX idx_requirements_kind ON requirements(kind);
        """
    )
    conn.execute("ALTER TABLE spec_versions ADD COLUMN diagnostics TEXT NOT NULL DEFAULT '[]'")


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migration_1,
    2: _migration_2,
    3: _migration_3,
}


def migrate(conn: sqlite3.Connection, target: int = LATEST_VERSION) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    current = current_version(conn)
    if target > LATEST_VERSION:
        raise ValueError(f"target version {target} is newer than {LATEST_VERSION}")
    for version in range(current + 1, target + 1):
        migration = MIGRATIONS[version]
        try:
            migration(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
                (version, utc_now()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return current_version(conn)


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]
