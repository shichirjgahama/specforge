"""CLI integration and UI smoke tests."""
import tkinter as tk
from pathlib import Path

import pytest

from specforge.cli import main
from specforge.services import SpecForgeService

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "specs" / "scooter_share.sforge"


def test_cli_check_and_test(tmp_path, capsys):
    db = tmp_path / "cli.db"
    assert main(["check", str(SPEC)]) == 0
    assert main(["--db", str(db), "test", "--only", "T-001,T-002"]) == 0
    output = capsys.readouterr().out
    assert "passed=2" in output
    assert "failed=0" in output


def test_cli_impact_and_trace(tmp_path, capsys):
    db = tmp_path / "cli.db"
    assert main(["--db", str(db), "impact", "CR-003", "--reset"]) == 0
    output = capsys.readouterr().out
    assert "minimality: equal=True" in output
    assert "T-033" in output
    assert main(["--db", str(db), "trace"]) == 0


def test_ui_constructs_all_screens(tmp_path):
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display available")
    from specforge.ui.app import SpecForgeApp
    service = SpecForgeService(db_path=tmp_path / "ui.db")
    app = SpecForgeApp(service)
    try:
        app.update()
        assert set(app.screens) == {
            "Requirements", "DSL", "State machine", "Traceability",
            "Change requests", "Tests",
        }
        for screen in app.screens.values():
            screen.refresh()
            app.update()
        assert len(app.screens["Traceability"].tree.get_children()) == 20
        assert len(app.screens["Tests"].tree.get_children()) == 60
        assert len(app.screens["State machine"].canvas.find_all()) > 0
    finally:
        app.destroy()
