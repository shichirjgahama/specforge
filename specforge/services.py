"""Application service: one object used by the CLI and the UI.

Keeps the current parsed specification, its node index, validation report and
the persisted artifacts in sync.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Optional

from .core import ast_nodes as A
from .core.impact import ChangeRequest, ChangeRequestError, analyze_impact, verify_minimality
from .core.incremental import full_analysis, verify_incremental
from .core.interpreter import Interpreter, ScenarioResult
from .core.nodes import SpecIndex, build_index
from .core.parser import ParseResult, parse
from .core.properties import check_all
from .core.semantic import SemanticResult, analyze
from .core.state_machine import StateGraph, build_state_graph
from .core.traceability import TraceabilityReport, build_traceability
from .core.validator import ValidationReport, validate
from .domain import load_requirements
from .domain.change_requests import seed_change_requests
from .report.html_report import render_html_report
from .runtime.codegen import generate_tests, TestCase
from .runtime.runner import RunSummary, Runner, spec_hash
from .storage.repo import Repository


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = PROJECT_ROOT / "specs" / "scooter_share.sforge"


class ServiceError(Exception):
    pass


class SpecForgeService:
    def __init__(self, db_path: Optional[str | Path] = None,
                 spec_path: Optional[str | Path] = None) -> None:
        self.repo = Repository(db_path)
        self.spec_path = Path(spec_path) if spec_path else DEFAULT_SPEC
        self._seed()
        self.reload()

    # ---------------------------------------------------------------- seeding
    def _seed(self) -> None:
        if self.repo.count_requirements() == 0:
            for item in load_requirements():
                data = item.to_dict()
                data.pop("version", None)
                self.repo.save_requirement(data)
        if not self.repo.latest_spec():
            content = self.spec_path.read_text(encoding="utf-8")
            parsed = parse(content, str(self.spec_path))
            index = None
            if parsed.ok:
                semantic = analyze(parsed.program)
                if semantic.ok:
                    index = build_index(parsed.program, semantic.model)
            self.repo.save_spec(content, str(self.spec_path),
                                hashlib.sha256(content.encode("utf-8")).hexdigest(),
                                [d.to_dict() for d in parsed.diagnostics], index)
        if self.repo.count_tests() == 0:
            self._generate_and_store_tests()
        if not self.repo.change_requests():
            for cr in seed_change_requests():
                self.repo.save_change_request(cr)

    def _generate_and_store_tests(self) -> list[TestCase]:
        spec = self.repo.latest_spec()
        if not spec:
            return []
        parsed = parse(spec["content"], spec["filename"])
        if not parsed.ok:
            raise ServiceError("cannot generate tests: specification has errors")
        semantic = analyze(parsed.program)
        index = build_index(parsed.program, semantic.model)
        cases = generate_tests(parsed.program, index)
        self.repo.save_tests(cases)
        return cases

    # ------------------------------------------------------------------ state
    def reload(self) -> None:
        spec = self.repo.latest_spec()
        if spec is None:
            raise ServiceError("no specification stored")
        self.spec_record = spec
        self.content = spec["content"]
        self.parsed: ParseResult = parse(self.content, spec["filename"])
        self.program: A.Program = self.parsed.program
        self.semantic: SemanticResult = analyze(self.program)
        self.index: SpecIndex = build_index(self.program, self.semantic.model)
        self.validation: ValidationReport = validate(self.semantic, self.index)
        self.graphs: dict[str, StateGraph] = {}
        for state in self.program.states:
            members = self.semantic.model.enums.get(state.name, [])
            self.graphs[state.name] = build_state_graph(state, members)
        self.requirements = self.repo.requirements()
        self.tests = self.repo.tests()

    @property
    def spec_hash(self) -> str:
        return spec_hash(self.program)

    @property
    def diagnostics(self):
        return self.validation.diagnostics

    # ------------------------------------------------------------ requirements
    def save_requirement(self, data: dict) -> dict:
        saved = self.repo.save_requirement(data)
        self.requirements = self.repo.requirements()
        return saved

    def requirement_versions(self, requirement_id: str) -> list[dict]:
        return self.repo.requirement_versions(requirement_id)

    # -------------------------------------------------------------------- spec
    def update_spec(self, content: str) -> dict:
        parsed = parse(content, str(self.spec_path))
        semantic = analyze(parsed.program)
        index = build_index(parsed.program, semantic.model)
        diagnostics = [d.to_dict() for d in parsed.diagnostics]
        if not semantic.ok:
            diagnostics.extend(d.to_dict() for d in semantic.diagnostics)
        spec_id = self.repo.save_spec(
            content, str(self.spec_path),
            hashlib.sha256(content.encode("utf-8")).hexdigest(),
            diagnostics, index if parsed.ok and semantic.ok else None,
        )
        self.reload()
        return {"spec_version_id": spec_id, "ok": parsed.ok and semantic.ok,
                "diagnostics": diagnostics}

    def spec_versions(self) -> list[dict]:
        return self.repo.spec_versions()

    def reset_spec(self) -> dict:
        """Restore the demo specification from the packaged file.

        Used by the demo and by isolated impact experiments. Tests are not
        regenerated, so the baseline expectations stay in place.
        """
        content = self.spec_path.read_text(encoding="utf-8")
        parsed = parse(content, str(self.spec_path))
        semantic = analyze(parsed.program)
        index = build_index(parsed.program, semantic.model)
        spec_id = self.repo.save_spec(
            content, str(self.spec_path),
            hashlib.sha256(content.encode("utf-8")).hexdigest(),
            [d.to_dict() for d in parsed.diagnostics], index,
        )
        self.reload()
        return {"spec_version_id": spec_id, "ok": semantic.ok}

    # --------------------------------------------------------------- scenarios
    def run_scenarios(self) -> list[ScenarioResult]:
        interpreter = Interpreter(self.program, self.semantic.model)
        return interpreter.run_all_scenarios()

    # ------------------------------------------------------------------- tests
    def run_all_tests(self, seed: int = 1234, only: Optional[Iterable[str]] = None
                      ) -> RunSummary:
        cases = self.tests
        if only is not None:
            wanted = set(only)
            cases = [case for case in cases if case.id in wanted]
        runner = Runner(self.program)
        summary = runner.run(cases, seed=seed)
        self.repo.save_run(summary, self.spec_record["id"])
        return summary

    def regenerate_tests(self) -> list[TestCase]:
        cases = self._generate_and_store_tests()
        self.tests = self.repo.tests()
        return cases

    def latest_run(self) -> Optional[dict]:
        runs = self.repo.runs(limit=1)
        return runs[0] if runs else None

    def latest_results_map(self) -> dict:
        run = self.latest_run()
        if not run:
            return {}
        return {item["test_id"]: item for item in self.repo.run_results(run["id"])}

    # ------------------------------------------------------------ traceability
    def traceability(self) -> TraceabilityReport:
        return build_traceability(self.index, self.requirements, self.tests,
                                  self.latest_results_map())

    # --------------------------------------------------------------- impact
    def change_requests(self) -> list[ChangeRequest]:
        return self.repo.change_requests()

    def change_request(self, cr_id: str) -> Optional[ChangeRequest]:
        for cr in self.change_requests():
            if cr.id == cr_id:
                return cr
        return None

    def apply_change_request(self, cr_id: str, verify: bool = True) -> dict:
        cr = self.change_request(cr_id)
        if cr is None:
            raise ServiceError(f"unknown change request {cr_id}")
        try:
            new_content = cr.apply_to_source(self.content)
        except ChangeRequestError as exc:
            raise ServiceError(str(exc)) from exc
        parsed = parse(new_content, str(self.spec_path))
        if not parsed.ok:
            raise ServiceError("change request produced a specification with syntax errors: "
                               + "; ".join(d.message for d in parsed.diagnostics
                                           if d.severity == "error"))
        semantic = analyze(parsed.program)
        if not semantic.ok:
            raise ServiceError("change request produced semantic errors: "
                               + "; ".join(d.message for d in semantic.diagnostics
                                           if d.severity == "error"))
        for edit in cr.requirement_edits:
            requirement_id = edit.get("id")
            if not requirement_id:
                continue
            current = self.repo.requirement(requirement_id)
            if current is None:
                raise ServiceError(f"unknown requirement {requirement_id}")
            updated = {
                "id": requirement_id,
                "title": edit.get("title", current["title"]),
                "story": edit.get("story", current["story"]),
                "criteria": list(current["criteria"]) + list(
                    edit.get("criteria_add", [])),
                "kind": edit.get("kind", current["kind"]),
                "priority": edit.get("priority", current["priority"]),
                "role": edit.get("role", current["role"]),
                "status": edit.get("status", current["status"]),
                "notes": edit.get("notes", current["notes"]),
            }
            self.repo.save_requirement(updated)

        old_program = self.program
        old_index = self.index
        spec_id = self.repo.save_spec(
            new_content, str(self.spec_path),
            hashlib.sha256(new_content.encode("utf-8")).hexdigest(),
            [d.to_dict() for d in parsed.diagnostics], build_index(parsed.program, semantic.model),
        )
        self.reload()
        plan = analyze_impact(old_program, self.program, cr, self.tests,
                              old_index=old_index, new_index=self.index)
        minimality = None
        if verify:
            minimality = verify_minimality(plan, self.program, self.tests)
        report_id = self.repo.save_impact(plan, minimality)
        return {
            "ok": True,
            "cr": cr.to_dict(),
            "plan": plan.to_dict(),
            "minimality": minimality,
            "spec_version_id": spec_id,
            "impact_report_id": report_id,
            "requirements": self.requirements,
            "validation": self.validation.to_dict(),
        }

    def impact_history(self, limit: int = 20) -> list[dict]:
        return self.repo.impact_reports(limit)

    def incremental_change_demo(self, requirement_id: str = "R-013") -> dict:
        """Change one requirement version and verify the incremental cache."""
        versions = self.repo.requirement_version_map()
        old_cache = full_analysis(self.index, versions)
        changed = dict(versions)
        changed[requirement_id] = int(changed.get(requirement_id, 0)) + 1
        result = verify_incremental(old_cache, self.index, changed)
        result.pop("cache", None)
        return result

    # -------------------------------------------------------------- properties
    def properties(self) -> dict:
        return check_all(self.program)

    # ------------------------------------------------------------------ report
    def build_report(self, out_path: Optional[str | Path] = None) -> Path:
        run = self.latest_run()
        results = self.repo.run_results(run["id"]) if run else []
        trace = self.traceability()
        html = render_html_report(
            title="RollCity specification report",
            spec=self.spec_record,
            requirements=self.requirements,
            traceability=trace,
            tests=self.tests,
            run=run,
            results=results,
            graphs=self.graphs,
            validation=self.validation,
            impact_reports=self.repo.impact_reports(limit=6),
        )
        target = Path(out_path) if out_path else (
            PROJECT_ROOT / "data" / "report.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        return target

    # ------------------------------------------------------------------- stats
    def stats(self) -> dict:
        data = self.repo.stats()
        data.update({
            "parsed_ok": self.parsed.ok,
            "semantic_ok": self.semantic.ok,
            "validation_ok": self.validation.ok,
            "diagnostics": len(self.validation.diagnostics),
            "scenarios": len(self.program.scenarios),
            "coverage": round(self.traceability().coverage_percent, 2),
        })
        return data
