"""Standalone HTML report. No external assets, works offline from a file."""
from __future__ import annotations

import html
from typing import Iterable, Optional

from ..core.state_machine import render_svg


def esc(value) -> str:
    return html.escape(str(value), quote=True)


CSS = """
:root {
  --ink: #1c2733; --muted: #5d6b78; --line: #d8e0e7;
  --bg: #f6f8fa; --card: #ffffff; --accent: #0b6e4f; --accent-soft: #e7f3ee;
  --warn: #b26a00; --warn-soft: #fff4e5; --bad: #b3261e; --bad-soft: #fdecea;
  --info: #1a4f8b; --info-soft: #e8f0fb;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.5 "Segoe UI", Arial, sans-serif; }
header { background: #123b32; color: #eef7f3; padding: 26px 34px 22px; }
header h1 { margin: 0 0 6px; font-size: 24px; font-weight: 600; letter-spacing: .2px; }
header .meta { color: #b8d6c9; font-size: 13px; }
main { max-width: 1180px; margin: 0 auto; padding: 24px 22px 60px; }
section { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 20px 22px; margin: 0 0 20px; }
h2 { font-size: 17px; margin: 0 0 14px; font-weight: 600; }
h3 { font-size: 14px; margin: 18px 0 8px; font-weight: 600; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px; margin-bottom: 20px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 14px 16px; }
.card .value { font-size: 24px; font-weight: 600; }
.card .label { color: var(--muted); font-size: 12px; text-transform: uppercase;
  letter-spacing: .4px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 9px; border-bottom: 1px solid var(--line);
  vertical-align: top; }
th { background: #f0f4f7; font-weight: 600; font-size: 12px; color: #3b4a57; }
tr:hover td { background: #fafcfd; }
code, .mono { font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 600; white-space: nowrap; }
.ok { background: var(--accent-soft); color: var(--accent); }
.partial { background: var(--warn-soft); color: var(--warn); }
.bad { background: var(--bad-soft); color: var(--bad); }
.info { background: var(--info-soft); color: var(--info); }
.muted { color: var(--muted); }
.small { font-size: 12px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 900px) { .grid2 { grid-template-columns: 1fr; } }
ul.compact { margin: 4px 0 0 18px; padding: 0; }
ul.compact li { margin: 2px 0; }
.diag { border-left: 3px solid var(--line); padding: 6px 10px; margin: 6px 0;
  background: #fbfcfd; font-size: 12px; }
.diag.error { border-color: var(--bad); }
.diag.warning { border-color: var(--warn); }
.diag.info { border-color: var(--info); }
.graph { overflow: auto; border: 1px solid var(--line); border-radius: 8px;
  background: #fafbfc; }
.legend span { margin-right: 14px; font-size: 12px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  margin-right: 5px; vertical-align: middle; }
footer { color: var(--muted); font-size: 12px; text-align: center; margin-top: 26px; }
"""


def _badge(status: str) -> str:
    mapping = {
        "covered": ("ok", "covered"),
        "partial": ("partial", "partial"),
        "uncovered": ("bad", "uncovered"),
        "no_spec": ("bad", "no specification"),
        "passed": ("ok", "passed"),
        "failed": ("bad", "failed"),
        "error": ("bad", "error"),
        "warning": ("partial", "warning"),
        "info": ("info", "info"),
    }
    css, label = mapping.get(status, ("info", status))
    return f'<span class="badge {css}">{esc(label)}</span>'


def render_html_report(title: str, spec: dict, requirements: Iterable[dict],
                       traceability, tests: Iterable, run: Optional[dict],
                       results: Iterable[dict], graphs: dict,
                       validation, impact_reports: Iterable[dict] = ()) -> str:
    requirements = list(requirements)
    tests = list(tests)
    results = list(results)
    impact_reports = list(impact_reports)
    result_by_id = {item["test_id"]: item for item in results}
    trace_by_id = {row.requirement_id: row for row in traceability.rows}
    totals = traceability.summary
    spec_hash = spec.get("content_hash", "")[:16]
    passed = sum(1 for item in results if item["status"] == "passed")
    failed = sum(1 for item in results if item["status"] == "failed")

    parts: list[str] = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body>",
        "<header>",
        f"<h1>{esc(title)}</h1>",
        f"<div class='meta'>spec {esc(spec.get('filename', ''))} "
        f"version {esc(spec.get('version', 1))} - hash {esc(spec_hash)} - "
        f"requirements {len(requirements)} - spec nodes {totals.get('spec_nodes', 0)} - "
        f"tests {len(tests)}</div>",
        "</header><main>",
    ]

    # summary cards
    parts.append("<div class='cards'>")
    for label, value, css in (
        ("Requirements", len(requirements), ""),
        ("Spec nodes", totals.get("spec_nodes", 0), ""),
        ("Tests", len(tests), ""),
        ("Passed", passed, "ok"),
        ("Failed", failed, "bad" if failed else ""),
        ("Coverage", f"{traceability.coverage_percent:.1f}%", ""),
        ("Schema version", "3", ""),
    ):
        parts.append(
            f"<div class='card'><div class='value'>{esc(value)}</div>"
            f"<div class='label'>{esc(label)}</div></div>")
    parts.append("</div>")

    # traceability summary
    parts.append("<section><h2>Coverage and traceability</h2>")
    parts.append(
        "<p class='muted small'>Requirement -> specification node -> test case -> "
        "last result. A requirement is covered when every linked spec node is "
        "referenced by at least one test.</p>")
    parts.append("<table><thead><tr><th>Requirement</th><th>Title</th><th>Type</th>"
                 "<th>Spec nodes</th><th>Tests</th><th>Status</th><th>Last result</th>"
                 "</tr></thead><tbody>")
    for requirement in requirements:
        row = trace_by_id.get(requirement["id"])
        if row is None:
            continue
        parts.append(
            "<tr>"
            f"<td class='mono'>{esc(requirement['id'])}</td>"
            f"<td>{esc(requirement['title'])}</td>"
            f"<td>{esc(requirement.get('kind', ''))}</td>"
            f"<td class='mono small'>{esc(', '.join(row.nodes) or '-')}</td>"
            f"<td class='mono small'>{esc(', '.join(row.tests) or '-')}</td>"
            f"<td>{_badge(row.status)}</td>"
            f"<td>{_badge(row.last_result) if row.last_result else '<span class=\"muted\">no run</span>'}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    if traceability.issues:
        parts.append("<h3>Open traceability issues</h3><ul class='compact'>")
        for issue in traceability.issues:
            parts.append(f"<li>{esc(issue)}</li>")
        parts.append("</ul>")
    parts.append("</section>")

    # test results
    parts.append("<section><h2>Test results</h2>")
    if run:
        parts.append(
            f"<p class='muted small'>Run {esc(run['id'])} from {esc(run['started_at'])}, "
            f"spec hash {esc(run['spec_hash'][:16])}, seed {esc(run['seed'])}, "
            f"digest {esc(run['digest'][:16])}, passed {esc(run['passed'])}, "
            f"failed {esc(run['failed'])}.</p>")
    else:
        parts.append("<p class='muted'>The test suite has not been executed yet.</p>")
    parts.append("<table><thead><tr><th>Test</th><th>Kind</th><th>Title</th>"
                 "<th>Requirements</th><th>Status</th><th>Message</th></tr></thead><tbody>")
    for test in tests:
        result = result_by_id.get(test.id)
        status = result["status"] if result else "not run"
        message = result["message"] if result else ""
        if len(message) > 180:
            message = message[:177] + "..."
        parts.append(
            "<tr>"
            f"<td class='mono'>{esc(test.id)}</td>"
            f"<td>{esc(test.kind)}</td>"
            f"<td>{esc(test.title)}</td>"
            f"<td class='mono small'>{esc(', '.join(test.requirements))}</td>"
            f"<td>{_badge(status) if result else '<span class=\"muted\">not run</span>'}</td>"
            f"<td class='small'>{esc(message) or '<span class=\"muted\">-</span>'}</td>"
            "</tr>"
        )
    parts.append("</tbody></table></section>")

    # state machines
    parts.append("<section><h2>State machines</h2>")
    parts.append("<div class='legend'>"
                 "<span><i class='dot' style='background:#2e7d32'></i>initial</span>"
                 "<span><i class='dot' style='background:#ef6c00'></i>inside a cycle</span>"
                 "<span><i class='dot' style='background:#c62828'></i>unreachable</span>"
                 "<span><i class='dot' style='background:#546e7a'></i>normal</span></div>")
    for name, graph in sorted(graphs.items()):
        parts.append(f"<h3>{esc(name)} - initial state {esc(graph.initial)}</h3>")
        parts.append("<div class='graph'>" + render_svg(graph, name) + "</div>")
        info = []
        if graph.unreachable:
            info.append("unreachable: " + ", ".join(graph.unreachable))
        if graph.cycles:
            info.append("cycles: " + "; ".join(" -> ".join(cycle) for cycle in graph.cycles))
        if graph.dead_ends:
            info.append("dead ends: " + ", ".join(graph.dead_ends))
        if info:
            parts.append("<p class='small muted'>" + esc(" | ".join(info)) + "</p>")
    parts.append("</section>")

    # diagnostics
    parts.append("<section><h2>Specification diagnostics</h2>")
    if validation.diagnostics:
        for diag in validation.diagnostics[:80]:
            parts.append(
                f"<div class='diag {esc(diag.severity)}'>"
                f"<span class='mono'>{esc(diag.code)}</span> "
                f"{esc(diag.message)} "
                f"<span class='muted small'>(line {esc(diag.line)}, col {esc(diag.col)})</span>"
                "</div>")
    else:
        parts.append("<p class='muted'>No diagnostics.</p>")
    parts.append("</section>")

    # impact reports
    if impact_reports:
        parts.append("<section><h2>Impact analysis</h2>")
        for report in impact_reports:
            plan = report["plan"]
            minimality = report.get("minimality") or {}
            parts.append(f"<h3>{esc(plan['cr_id'])} - changed nodes "
                         f"{len(plan['changed_nodes'])}, affected nodes "
                         f"{len(plan['affected_nodes'])}, selected tests "
                         f"{len(plan['tests'])}</h3>")
            parts.append("<div class='grid2'><div>")
            parts.append("<p class='small muted'>Changed nodes</p><ul class='compact'>")
            for node_id in plan["changed_nodes"][:20]:
                parts.append(f"<li class='mono'>{esc(node_id)}</li>")
            parts.append("</ul></div><div>")
            parts.append("<p class='small muted'>Selected tests</p><ul class='compact'>")
            for test_id in plan["tests"][:30]:
                parts.append(f"<li class='mono'>{esc(test_id)}</li>")
            parts.append("</ul></div></div>")
            if minimality:
                eq = "equal" if minimality.get("equal") else "different"
                css = "ok" if minimality.get("equal") else "bad"
                parts.append(
                    f"<p class='small'>Minimality check: selected failed "
                    f"{esc(len(minimality.get('subset_failed', [])))}, full failed "
                    f"{esc(len(minimality.get('full_failed', [])))}, sets are "
                    f"<span class='badge {css}'>{eq}</span></p>")
            if plan.get("conflicts"):
                parts.append("<ul class='compact small'>")
                for conflict in plan["conflicts"]:
                    parts.append(f"<li>{esc(conflict)}</li>")
                parts.append("</ul>")
        parts.append("</section>")

    parts.append("<footer>Generated locally by SpecForge. Offline HTML, "
                 "no external resources.</footer></main></body></html>")
    return "".join(parts)
