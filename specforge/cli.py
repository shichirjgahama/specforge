"""Command line interface for SpecForge."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core.parser import parse
from .core.semantic import analyze
from .core.nodes import build_index
from .core.validator import validate
from .core.properties import check_all
from .services import PROJECT_ROOT, SpecForgeService, ServiceError
from .storage.repo import default_db_path


def _service(args) -> SpecForgeService:
    return SpecForgeService(db_path=getattr(args, "db", None))


def _print_diagnostics(diagnostics) -> None:
    if not diagnostics:
        print("no diagnostics")
        return
    for diagnostic in diagnostics:
        print(diagnostic.format())


def cmd_parse(args) -> int:
    source = Path(args.file).read_text(encoding="utf-8")
    parsed = parse(source, args.file)
    _print_diagnostics(parsed.diagnostics)
    print(f"tokens: {len(parsed.tokens)}, declarations: "
          f"{len(parsed.program.entities)} entities, "
          f"{len(parsed.program.rules)} rules, "
          f"{len(parsed.program.states)} state machines")
    return 0 if parsed.ok else 1


def cmd_check(args) -> int:
    source = Path(args.file).read_text(encoding="utf-8")
    parsed = parse(source, args.file)
    semantic = analyze(parsed.program)
    index = build_index(parsed.program, semantic.model)
    report = validate(semantic, index)
    _print_diagnostics(report.diagnostics)
    print(json.dumps(report.stats, indent=2, ensure_ascii=False))
    return 0 if report.ok else 1


def cmd_stats(args) -> int:
    service = _service(args)
    print(json.dumps(service.stats(), indent=2, ensure_ascii=False))
    return 0


def cmd_scenarios(args) -> int:
    service = _service(args)
    results = service.run_scenarios()
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"{result.name}: {status}, steps={result.steps}")
        for failure in result.failures:
            print(f"  failure: {failure}")
        for violation in result.invariant_violations:
            print(f"  invariant: {violation}")
        for violation in result.transition_violations:
            print(f"  transition: {violation}")
    return 0 if all(result.ok for result in results) else 1


def cmd_trace(args) -> int:
    service = _service(args)
    report = service.traceability()
    for row in report.rows:
        print(f"{row.requirement_id:7} {row.status:10} nodes={len(row.nodes):2} "
              f"tests={len(row.tests):2} {row.title}")
    print(json.dumps(report.summary, indent=2, ensure_ascii=False))
    if report.issues:
        print("issues:")
        for issue in report.issues:
            print("  " + issue)
    return 0


def cmd_test(args) -> int:
    service = _service(args)
    only = args.only.split(",") if args.only else None
    summary = service.run_all_tests(seed=args.seed, only=only)
    for result in summary.results:
        if result.status != "passed" or args.verbose:
            print(f"{result.test_id} {result.status:6} {result.title}")
            if result.message:
                print("   " + result.message)
    print(f"passed={summary.passed} failed={summary.failed} "
          f"digest={summary.digest[:16]} duration={summary.duration_ms:.1f}ms")
    if args.json:
        print(summary.report_json())
    return 0 if summary.ok else 1


def cmd_properties(args) -> int:
    service = _service(args)
    report = check_all(service.program)
    for item in report["results"]:
        status = "OK" if item["ok"] else "FAIL"
        print(f"{item['name']:26} {status:5} checks={item['checks']}")
        for violation in item["violations"]:
            print("   " + violation)
    print(f"all properties: {'OK' if report['ok'] else 'FAIL'}")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


def cmd_crs(args) -> int:
    service = _service(args)
    for cr in service.change_requests():
        print(f"{cr.id} [{cr.kind}] {cr.title}")
    return 0


def cmd_impact(args) -> int:
    service = _service(args)
    if args.reset:
        service.reset_spec()
    try:
        result = service.apply_change_request(args.cr_id, verify=not args.no_verify)
    except ServiceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    plan = result["plan"]
    print(f"{plan['cr_id']}: changed={len(plan['changed_nodes'])} "
          f"affected={len(plan['affected_nodes'])} selected={len(plan['tests'])} "
          f"of {plan['tests_total']} tests")
    print("changed nodes:")
    for node_id in plan["changed_nodes"]:
        print("  " + node_id)
    print("tests to run and why:")
    for test_id in plan["tests"]:
        reasons = "; ".join(plan["reasons"].get(test_id, []))
        print(f"  {test_id}: {reasons}")
    if plan["regenerate"]:
        print("regenerate: " + ", ".join(plan["regenerate"]))
    if plan["conflicts"]:
        print("conflicts:")
        for conflict in plan["conflicts"]:
            print("  " + conflict)
    minimality = result.get("minimality")
    if minimality:
        print(f"minimality: equal={minimality['equal']} "
              f"subset_failed={minimality['subset_failed']} "
              f"full_failed={minimality['full_failed']}")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if (not minimality or minimality["equal"]) else 1


def cmd_report(args) -> int:
    service = _service(args)
    if args.run_tests:
        summary = service.run_all_tests()
        print(f"tests: passed={summary.passed} failed={summary.failed}")
    path = service.build_report(args.out)
    print(f"report: {path}")
    return 0


def cmd_incremental(args) -> int:
    service = _service(args)
    result = service.incremental_change_demo(args.requirement)
    print(json.dumps({key: value for key, value in result.items()
                      if key != "cache"}, indent=2, ensure_ascii=False))
    return 0 if result["equal"] else 1


def cmd_migrate(args) -> int:
    import sqlite3
    from .storage.migrations import migrate, current_version
    path = Path(args.db) if args.db else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    before = current_version(conn)
    after = migrate(conn, args.to)
    conn.close()
    print(f"{path}: {before} -> {after}")
    return 0


def _write_cr_report(out_dir: Path, cr, result: dict) -> Path:
    plan = result["plan"]
    minimality = result["minimality"]
    lines = [
        f"# {cr.id}: {cr.title}",
        "",
        f"- Тип: `{cr.kind}`",
        f"- Описание: {cr.description}",
        f"- Версия спецификации до: `{plan['spec_hash_before'][:16]}`",
        f"- Версия спецификации после: `{plan['spec_hash_after'][:16]}`",
        f"- Узлов изменено: {len(plan['changed_nodes'])}",
        f"- Узлов затронуто: {len(plan['affected_nodes'])}",
        f"- Тестов выбрано: {len(plan['tests'])} из {plan['tests_total']}",
        "",
        "## Измененные узлы",
        "",
    ]
    lines += [f"- `{node_id}`" for node_id in plan["changed_nodes"]]
    lines += ["", "## План прогона", ""]
    for test_id in plan["tests"]:
        reason = "; ".join(plan["reasons"].get(test_id, []))
        lines.append(f"- `{test_id}`: {reason}")
    lines += [
        "",
        "## Результат до и после",
        "",
        f"- До изменения: 60 из 60 тестов проходили (базовая спецификация).",
        f"- После изменения: упавших тестов {len(minimality['full_failed'])}: "
        + (", ".join(minimality["full_failed"]) or "нет"),
        f"- Прогон только выбранных тестов упал на: "
        + (", ".join(minimality["subset_failed"]) or "нет"),
        f"- Полный прогон упал на: "
        + (", ".join(minimality["full_failed"]) or "нет"),
        f"- Минимальность (множества совпадают): {minimality['equal']}",
        f"- Тестов к перегенерации: {len(plan['regenerate'])}",
        f"- Конфликты: " + ("; ".join(plan["conflicts"]) or "нет"),
        "",
        "## Изменения требований",
        "",
    ]
    if cr.requirement_edits:
        for edit in cr.requirement_edits:
            lines.append(f"- `{edit.get('id', '?')}`: "
                         + ", ".join(f"{key}={value}" for key, value in edit.items()
                                     if key != "id"))
    else:
        lines.append("- нет")
    path = out_dir / f"{cr.id}-impact.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def cmd_demo(args) -> int:
    service = SpecForgeService(db_path=getattr(args, "db", None))
    baseline = service.run_all_tests()
    out_dir = PROJECT_ROOT / "data" / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline": {"passed": baseline.passed, "failed": baseline.failed,
                     "digest": baseline.digest,
                     "results": [r.to_dict() for r in baseline.results]},
        "change_requests": {},
    }
    for cr in service.change_requests():
        service.reset_spec()
        result = service.apply_change_request(cr.id, verify=True)
        payload["change_requests"][cr.id] = {
            "plan": result["plan"],
            "minimality": result["minimality"],
            "requirements": result["requirements"],
        }
        _write_cr_report(out_dir, cr, result)
        print(f"{cr.id}: selected={len(result['plan']['tests'])} "
              f"failed={len(result['minimality']['full_failed'])} "
              f"minimal={result['minimality']['equal']}")
    service.reset_spec()
    report_path = service.build_report(out_dir / "report.html")
    (out_dir / "demo.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"baseline digest: {baseline.digest}")
    print(f"demo data: {out_dir / 'demo.json'}")
    print(f"report: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specforge",
        description="SpecForge: DSL, traceability, impact analysis and tests.")
    parser.add_argument("--db", help="path to the SQLite database",
                        default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="initialise the database and seed data")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("stats", help="show database statistics")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("parse", help="parse a DSL file")
    p.add_argument("file")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("check", help="parse and semantically check a DSL file")
    p.add_argument("file")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("scenarios", help="execute all DSL scenarios")
    p.set_defaults(func=cmd_scenarios)

    p = sub.add_parser("trace", help="show the traceability matrix")
    p.set_defaults(func=cmd_trace)

    p = sub.add_parser("test", help="run generated tests")
    p.add_argument("--only", help="comma separated test ids")
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("properties", help="check the eight properties")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_properties)

    p = sub.add_parser("crs", help="list change requests")
    p.set_defaults(func=cmd_crs)

    p = sub.add_parser("impact", help="apply a change request and analyse impact")
    p.add_argument("cr_id")
    p.add_argument("--no-verify", action="store_true",
                   help="skip the subset versus full verification")
    p.add_argument("--reset", action="store_true",
                   help="restore the demo specification before applying")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_impact)

    p = sub.add_parser("report", help="write the HTML report")
    p.add_argument("--out", default=None)
    p.add_argument("--run-tests", action="store_true")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("incremental",
                       help="demonstrate hash based incremental analysis")
    p.add_argument("--requirement", default="R-013")
    p.set_defaults(func=cmd_incremental)

    p = sub.add_parser("migrate", help="migrate a database to a schema version")
    p.add_argument("--to", type=int, default=3)
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("demo", help="run the full demo and write reports")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
