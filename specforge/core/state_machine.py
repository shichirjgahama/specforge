"""State machine analysis and deterministic layered layout.

No graph library is used. Reachability is BFS, cycles use Tarjan SCC, layout is
a layered algorithm with barycenter ordering. The SVG renderer is dependency
free so the HTML report can embed diagrams offline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional
from xml.sax.saxutils import escape

from . import ast_nodes as A
from .semantic import strongly_connected


@dataclass
class GraphEdge:
    source: str
    target: str
    event: str
    guard: str = ""
    requirements: tuple[str, ...] = ()
    self_loop: bool = False


@dataclass
class GraphNode:
    name: str
    x: float = 0.0
    y: float = 0.0
    level: int = 0
    reachable: bool = True
    in_cycle: bool = False
    terminal: bool = False
    initial: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name, "x": self.x, "y": self.y, "level": self.level,
                "reachable": self.reachable, "in_cycle": self.in_cycle,
                "terminal": self.terminal, "initial": self.initial}


@dataclass
class StateGraph:
    machine: str
    initial: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    unreachable: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    dead_ends: list[str] = field(default_factory=list)
    reachable: list[str] = field(default_factory=list)
    width: float = 640.0
    height: float = 420.0

    def node(self, name: str) -> Optional[GraphNode]:
        for item in self.nodes:
            if item.name == name:
                return item
        return None

    def to_dict(self) -> dict:
        return {
            "machine": self.machine,
            "initial": self.initial,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [{"source": e.source, "target": e.target, "event": e.event,
                       "guard": e.guard, "requirements": list(e.requirements)}
                      for e in self.edges],
            "unreachable": self.unreachable,
            "cycles": self.cycles,
            "dead_ends": self.dead_ends,
            "width": self.width,
            "height": self.height,
        }


def build_state_graph(state: A.StateDecl, members: list[str]) -> StateGraph:
    graph = StateGraph(machine=state.name, initial=state.initial)
    names = list(members)
    if not names:
        names = sorted({e.source for e in state.edges} | {e.target for e in state.edges})

    adjacency: dict[str, set[str]] = {name: set() for name in names}
    for edge in state.edges:
        adjacency.setdefault(edge.source, set()).add(edge.target)
        graph.edges.append(GraphEdge(
            source=edge.source, target=edge.target, event=edge.event,
            guard=fmt_guard(edge.guard), requirements=tuple(edge.links),
            self_loop=edge.source == edge.target,
        ))

    reachable = _reachable(state.initial, adjacency)
    cycles = [component for component in strongly_connected(adjacency)
              if len(component) > 1 or (len(component) == 1 and
                                        component[0] in adjacency.get(component[0], set()))]
    in_cycle = {name for component in cycles for name in component}

    for name in names:
        outgoing = adjacency.get(name, set())
        graph.nodes.append(GraphNode(
            name=name, reachable=name in reachable, in_cycle=name in in_cycle,
            terminal=not outgoing, initial=name == state.initial,
        ))

    graph.unreachable = sorted(name for name in names if name not in reachable)
    graph.cycles = sorted(cycles)
    graph.dead_ends = sorted(name for name in names if not adjacency.get(name)
                             and name not in ("closed", "retired", "cancelled"))
    graph.reachable = sorted(reachable)
    _layout(graph, adjacency)
    return graph


def _reachable(initial: str, adjacency: dict[str, set[str]]) -> set[str]:
    if not initial:
        return set()
    seen: set[str] = set()
    stack = [initial]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))
    return seen


def _layout(graph: StateGraph, adjacency: dict[str, set[str]]) -> None:
    # layer = shortest distance from initial; unreachable states go last
    levels: dict[str, int] = {}
    if graph.initial:
        levels[graph.initial] = 0
        queue = [graph.initial]
        while queue:
            node = queue.pop(0)
            for child in sorted(adjacency.get(node, ())):
                if child not in levels:
                    levels[child] = levels[node] + 1
                    queue.append(child)
    max_level = max(levels.values()) if levels else 0
    for node in graph.nodes:
        if node.name not in levels:
            levels[node.name] = max_level + 1
    final_max_level = max(levels.values()) if levels else 0

    buckets: dict[int, list[str]] = {}
    for node in graph.nodes:
        buckets.setdefault(levels[node.name], []).append(node.name)
    for bucket in buckets.values():
        bucket.sort()

    # barycenter ordering: order nodes by average level of predecessors
    predecessors: dict[str, list[str]] = {name: [] for name in levels}
    for src, targets in adjacency.items():
        for dst in targets:
            predecessors.setdefault(dst, []).append(src)
    for level in sorted(buckets):
        def barycenter(name: str) -> float:
            preds = predecessors.get(name, [])
            if not preds:
                return float(levels[name] * 10)
            return sum(levels.get(p, 0) for p in preds) / len(preds)
        buckets[level].sort(key=lambda n: (barycenter(n), n))

    max_rows = max((len(v) for v in buckets.values()), default=1)
    margin_x, margin_y = 90.0, 70.0
    gap_x, gap_y = 210.0, 100.0
    height = margin_y * 2 + max(1, max_rows - 1) * gap_y
    width = margin_x * 2 + max(1, final_max_level) * gap_x
    for level, names in buckets.items():
        offset = (max_rows - len(names)) * gap_y / 2
        for row, name in enumerate(names):
            node = graph.node(name)
            if node is None:
                continue
            node.level = level
            node.x = margin_x + level * gap_x
            node.y = margin_y + offset + row * gap_y
    graph.width = max(width, 520.0)
    graph.height = max(height, 300.0)


def fmt_guard(guard) -> str:
    from .nodes import fmt_expr
    return fmt_expr(guard) if guard is not None else ""


def circular_positions(count: int, radius: float = 150.0,
                       cx: float = 340.0, cy: float = 220.0) -> list[tuple[float, float]]:
    """Fallback layout used for machines without an initial state."""
    result = []
    for index in range(count):
        angle = 2 * math.pi * index / max(1, count) - math.pi / 2
        result.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return result


# ------------------------------------------------------------------- drawing
NODE_W = 132
NODE_H = 44


def render_svg(graph: StateGraph, title: str = "") -> str:
    """Render the graph to a standalone SVG string (used by the HTML report)."""
    width = max(graph.width, 360)
    height = max(graph.height, 240)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Segoe UI, Arial, sans-serif">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" '
        'orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#546e7a"/></marker>'
        '<marker id="arrow-hot" markerWidth="10" markerHeight="8" refX="9" refY="4" '
        'orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#ef6c00"/></marker></defs>',
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="#fafbfc"/>',
    ]
    if title:
        parts.append(
            f'<text x="16" y="26" font-size="15" font-weight="600" fill="#263238">'
            f'{escape(title)}</text>'
        )
    for edge in graph.edges:
        src = graph.node(edge.source)
        dst = graph.node(edge.target)
        if src is None or dst is None:
            continue
        x1, y1, x2, y2, path = _edge_geometry(src, dst, edge.self_loop)
        hot = edge.source in {s for c in graph.cycles for s in c} or not src.reachable
        marker = "arrow-hot" if hot else "arrow"
        color = "#ef6c00" if hot else "#78909c"
        parts.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.4" '
            f'marker-end="url(#{marker})"/>'
        )
        mx, my = _label_position(src, dst, edge.self_loop)
        parts.append(
            f'<text x="{mx:.1f}" y="{my:.1f}" font-size="10" fill="{color}" '
            f'text-anchor="middle">{escape(edge.event)}</text>'
        )
    for node in graph.nodes:
        if not node.reachable:
            fill, stroke, text = "#ffebee", "#c62828", "#b71c1c"
        elif node.in_cycle:
            fill, stroke, text = "#fff8e1", "#ef6c00", "#e65100"
        elif node.initial:
            fill, stroke, text = "#e8f5e9", "#2e7d32", "#1b5e20"
        else:
            fill, stroke, text = "#ffffff", "#546e7a", "#263238"
        parts.append(
            f'<rect x="{node.x - NODE_W / 2:.1f}" y="{node.y - NODE_H / 2:.1f}" '
            f'width="{NODE_W}" height="{NODE_H}" rx="9" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.6"/>'
        )
        parts.append(
            f'<text x="{node.x:.1f}" y="{node.y + 4:.1f}" font-size="12" '
            f'text-anchor="middle" fill="{text}">{escape(node.name)}</text>'
        )
        if node.initial:
            parts.append(
                f'<text x="{node.x:.1f}" y="{node.y - NODE_H / 2 - 7:.1f}" '
                f'font-size="9" text-anchor="middle" fill="#2e7d32">initial</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _edge_geometry(src: GraphNode, dst: GraphNode, self_loop: bool):
    if self_loop:
        x = src.x
        y = src.y - NODE_H / 2
        path = (f"M{x - 22:.1f},{y:.1f} C{x - 52:.1f},{y - 58:.1f} "
                f"{x + 52:.1f},{y - 58:.1f} {x + 22:.1f},{y:.1f}")
        return x, y, x, y, path
    dx, dy = dst.x - src.x, dst.y - src.y
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    # rectangle boundary intersection, approximate by half extents
    sx = abs(ux) * NODE_W / 2 + 6
    sy = abs(uy) * NODE_H / 2 + 6
    start_x = src.x + ux * sx
    start_y = src.y + uy * sy
    end_x = dst.x - ux * sx
    end_y = dst.y - uy * sy
    mx = (start_x + end_x) / 2
    my = (start_y + end_y) / 2
    path = f"M{start_x:.1f},{start_y:.1f} L{end_x:.1f},{end_y:.1f}"
    return start_x, start_y, end_x, end_y, path


def _label_position(src: GraphNode, dst: GraphNode, self_loop: bool):
    if self_loop:
        return src.x, src.y - NODE_H / 2 - 34
    return (src.x + dst.x) / 2, (src.y + dst.y) / 2 - 6
