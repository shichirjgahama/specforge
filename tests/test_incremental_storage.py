"""Incremental recomputation, SQLite migrations and repository tests."""
import sqlite3

import pytest

from specforge.core.incremental import (
    AnalysisCache, full_analysis, incremental_update, verify_incremental,
)
from specforge.storage.migrations import (
    LATEST_VERSION, current_version, migrate, table_names,
)
from specforge.storage.repo import Repository, default_db_path


def test_incremental_recompute_is_bounded_and_exact(service):
    service.reset_spec()
    result = service.incremental_change_demo("R-013")
    assert result["equal"] is True
    assert result["percent"] <= 5.0
    assert result["recomputed_count"] <= max(1, result["node_count"] // 20)
    assert result["recomputed"]


def test_incremental_matches_full_analysis_for_other_requirement(service, index):
    from specforge.core.nodes import canonical
    versions = service.repo.requirement_version_map()
    old = full_analysis(index, versions)
    changed = dict(versions)
    changed["R-001"] = changed["R-001"] + 1
    fresh, recomputed = incremental_update(old, index, changed)
    full = full_analysis(index, changed)
    assert canonical(fresh.results) == canonical(full.results)
    assert recomputed


def test_incremental_detects_spec_hash_change(program, index, service):
    from specforge.core.nodes import canonical
    versions = service.repo.requirement_version_map()
    old = full_analysis(index, versions)
    # mutate a rule body and rebuild the index
    from specforge.core.parser import parse
    from specforge.core.semantic import analyze
    from specforge.core.nodes import build_index
    source = program.source.replace("rental.lateFee := 0;",
                                    "rental.lateFee := 0;\n    penalty.reason := \"none\";")
    new_program = parse(source, "changed").program
    new_index = build_index(new_program, analyze(new_program).model)
    result = verify_incremental(old, new_index, versions)
    assert result["equal"] is True
    assert "rule:BRI-04" in result["recomputed"]


def test_migrations_upgrade_v1_to_v3_and_keep_data(tmp_path):
    path = tmp_path / "migration.db"
    conn = sqlite3.connect(str(path))
    assert migrate(conn, 1) == 1
    assert current_version(conn) == 1
    conn.execute(
        "INSERT INTO requirements(id, version, title, story, criteria, kind, priority, "
        "role, status, notes, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("R-999", 1, "Old requirement", "story", "[]", "functional", "must",
         "Customer", "approved", "", "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO spec_versions(version, filename, content, content_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "old.sforge", "spec Old version 1;", "hash", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    assert migrate(conn, LATEST_VERSION) == 3
    assert current_version(conn) == 3
    row = conn.execute("SELECT title FROM requirements WHERE id='R-999'").fetchone()
    assert row[0] == "Old requirement"
    spec = conn.execute("SELECT content FROM spec_versions").fetchone()
    assert spec[0] == "spec Old version 1;"
    names = table_names(conn)
    assert {"change_requests", "impact_reports", "node_cache", "schema_version"} <= set(names)
    conn.close()


def test_migrate_is_idempotent(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "idem.db"))
    assert migrate(conn, 3) == 3
    assert migrate(conn, 3) == 3
    conn.close()


def test_repository_versions_requirements(service):
    original = service.repo.requirement("R-001")
    assert original["version"] >= 1
    updated = dict(original)
    updated["title"] = original["title"] + " (v2)"
    saved = service.repo.save_requirement(updated)
    assert saved["version"] == original["version"] + 1
    versions = service.repo.requirement_versions("R-001")
    assert len(versions) >= 2
    assert versions[-1]["payload"]["title"].endswith("(v2)")


def test_node_cache_roundtrip(service, index):
    versions = service.repo.requirement_version_map()
    cache = full_analysis(index, versions)
    digest = "deadbeef"
    service.repo.save_cache(digest, cache)
    loaded = service.repo.load_cache(digest)
    assert loaded is not None
    assert loaded.results == cache.results
    assert service.repo.load_cache("missing") is None


def test_default_db_path_is_in_user_profile():
    path = default_db_path()
    assert path.name == "specforge.db"
    assert "SpecForge" in str(path)


def test_run_results_are_persisted(service):
    summary = service.run_all_tests()
    runs = service.repo.runs()
    assert runs
    results = service.repo.run_results(runs[0]["id"])
    assert len(results) == 60
    assert {item["status"] for item in results} == {"passed"}
    assert runs[0]["digest"] == summary.digest
