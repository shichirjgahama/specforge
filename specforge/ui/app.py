"""Tkinter user interface for SpecForge.

Six screens: requirements with versions, DSL editor with highlighting and
diagnostics, state machine graph, traceability matrix, change requests with
impact analysis, test runs and HTML export.
"""
from __future__ import annotations

import json
import re
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ..core.parser import parse
from ..core.state_machine import NODE_H, NODE_W
from ..services import SpecForgeService

BG = "#f3f6f8"
CARD = "#ffffff"
INK = "#1c2733"
MUTED = "#5d6b78"
LINE = "#d8e0e7"
ACCENT = "#0b6e4f"
BAD = "#b3261e"
WARN = "#b26a00"
MONO = ("Consolas", 10)
UI = ("Segoe UI", 10)
UI_BOLD = ("Segoe UI", 10, "bold")
UI_TITLE = ("Segoe UI", 16, "bold")

SCALE = 1.0


def px(value: float) -> int:
    return max(1, int(round(value * SCALE)))


def enable_high_dpi() -> None:
    """Turn on process DPI awareness so the window is not bitmap stretched."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # pragma: no cover - non Windows or old API
        pass

KEYWORDS = {
    "spec", "version", "const", "entity", "enum", "role", "state", "rule",
    "invariant", "scenario", "given", "step", "expect", "link", "when", "then",
    "else", "ensures", "do", "priority", "may", "forbid", "apply", "assert",
    "emit", "true", "false", "and", "or", "not", "in", "initial", "always",
    "message", "require",
}
TYPES = {"Int", "Money", "Text", "Bool", "Time", "Identifier", "State"}
TOKEN_RE = re.compile(
    r"//[^\n]*|#[^\n]*|\"[^\"\n]*\"|\b[A-Z]{1,4}-\d+\b|"
    r"\b\d+\b|\b[A-Za-z_][A-Za-z0-9_]*\b"
)


class Screen(ttk.Frame):
    def __init__(self, master, app: "SpecForgeApp") -> None:
        super().__init__(master, padding=0)
        self.app = app
        self.service = app.service
        self.build()

    def build(self) -> None:  # pragma: no cover - UI construction
        raise NotImplementedError

    def refresh(self) -> None:  # pragma: no cover - UI lifecycle
        pass


class RequirementsScreen(Screen):
    def build(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Requirements", font=UI_TITLE).pack(side="left")
        ttk.Button(toolbar, text="New", command=self.new_requirement).pack(
            side="right", padx=4)
        ttk.Button(toolbar, text="Save", command=self.save_requirement).pack(
            side="right", padx=4)
        ttk.Button(toolbar, text="Version history", command=self.show_history).pack(
            side="right", padx=4)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(body)
        columns = ("id", "title", "kind", "version", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="headings",
                                 selectmode="browse")
        for column, label, width in (
            ("id", "ID", px(70)), ("title", "Title", px(260)),
            ("kind", "Type", px(90)), ("version", "Ver", px(50)),
            ("status", "Status", px(90)),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        body.add(left, weight=3)

        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(right, weight=4)
        self.form = {}
        fields = [
            ("id", "ID"), ("title", "Title"), ("kind", "Type"),
            ("role", "Role"), ("priority", "Priority"), ("status", "Status"),
            ("version", "Version (read only)"),
        ]
        for index, (key, label) in enumerate(fields):
            ttk.Label(right, text=label, foreground=MUTED).grid(
                row=index, column=0, sticky="w", pady=3)
            entry = ttk.Entry(right)
            entry.grid(row=index, column=1, sticky="ew", pady=3)
            self.form[key] = entry
        self.form["version"].configure(state="readonly")
        right.columnconfigure(1, weight=1)

        row = len(fields)
        ttk.Label(right, text="User story", foreground=MUTED).grid(
            row=row, column=0, sticky="nw", pady=3)
        self.story = tk.Text(right, height=5, wrap="word", font=UI,
                             relief="solid", borderwidth=1)
        self.story.grid(row=row, column=1, sticky="nsew", pady=3)
        ttk.Label(right, text="Acceptance criteria (one per line)",
                  foreground=MUTED).grid(row=row + 1, column=0, sticky="nw", pady=3)
        self.criteria = tk.Text(right, height=8, wrap="word", font=UI,
                                relief="solid", borderwidth=1)
        self.criteria.grid(row=row + 1, column=1, sticky="nsew", pady=3)
        ttk.Label(right, text="Notes", foreground=MUTED).grid(
            row=row + 2, column=0, sticky="nw", pady=3)
        self.notes = tk.Text(right, height=3, wrap="word", font=UI,
                             relief="solid", borderwidth=1)
        self.notes.grid(row=row + 2, column=1, sticky="nsew", pady=3)
        self.links_label = ttk.Label(right, text="", foreground=MUTED,
                                     wraplength=520, justify="left")
        self.links_label.grid(row=row + 3, column=0, columnspan=2, sticky="w",
                              pady=(8, 0))
        self.message = ttk.Label(right, text="", foreground=ACCENT)
        self.message.grid(row=row + 4, column=0, columnspan=2, sticky="w")
        self.refresh()

    def refresh(self) -> None:
        selected = self.tree.selection()
        current = selected[0] if selected else None
        self.tree.delete(*self.tree.get_children())
        for requirement in self.service.requirements:
            self.tree.insert("", "end", iid=requirement["id"], values=(
                requirement["id"], requirement["title"], requirement["kind"],
                requirement["version"], requirement["status"],
            ))
        if current and self.tree.exists(current):
            self.tree.selection_set(current)
        elif self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)

    def on_select(self, event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        requirement = next((item for item in self.service.requirements
                            if item["id"] == selected[0]), None)
        if requirement is None:
            return
        for key in ("id", "title", "kind", "role", "priority", "status"):
            self.form[key].delete(0, "end")
            self.form[key].insert(0, requirement.get(key, ""))
        self.form["version"].configure(state="normal")
        self.form["version"].delete(0, "end")
        self.form["version"].insert(0, str(requirement["version"]))
        self.form["version"].configure(state="readonly")
        self._set_text(self.story, requirement["story"])
        self._set_text(self.criteria, "\n".join(requirement["criteria"]))
        self._set_text(self.notes, requirement.get("notes", ""))
        nodes = self.service.index.requirements.get(requirement["id"], [])
        self.links_label.configure(
            text=f"Linked spec nodes ({len(nodes)}): " + ", ".join(nodes[:8]) +
                 (" ..." if len(nodes) > 8 else ""))
        self.message.configure(text="")

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def save_requirement(self) -> None:
        requirement_id = self.form["id"].get().strip()
        title = self.form["title"].get().strip()
        if not requirement_id or not title:
            messagebox.showerror("Requirement", "ID and title are required")
            return
        data = {
            "id": requirement_id,
            "title": title,
            "story": self.story.get("1.0", "end").strip(),
            "criteria": [line.strip() for line in
                         self.criteria.get("1.0", "end").splitlines()
                         if line.strip()],
            "kind": self.form["kind"].get().strip() or "functional",
            "priority": self.form["priority"].get().strip() or "must",
            "role": self.form["role"].get().strip() or "Customer",
            "status": self.form["status"].get().strip() or "approved",
            "notes": self.notes.get("1.0", "end").strip(),
        }
        saved = self.service.save_requirement(data)
        self.refresh()
        self.tree.selection_set(saved["id"])
        self.message.configure(
            text=f"Saved {saved['id']} as version {saved['version']}")
        self.app.refresh_all(except_screen=self)

    def new_requirement(self) -> None:
        numbers = [int(item["id"].split("-")[1]) for item in self.service.requirements
                   if item["id"].startswith("R-")]
        new_id = f"R-{max(numbers, default=0) + 1:03d}"
        self.tree.selection_remove(*self.tree.selection())
        for key in ("title", "kind", "role", "priority", "status"):
            self.form[key].delete(0, "end")
        self.form["id"].delete(0, "end")
        self.form["id"].insert(0, new_id)
        self.form["kind"].insert(0, "functional")
        self.form["role"].insert(0, "Customer")
        self.form["priority"].insert(0, "must")
        self.form["status"].insert(0, "draft")
        self.form["version"].configure(state="normal")
        self.form["version"].delete(0, "end")
        self.form["version"].insert(0, "0")
        self.form["version"].configure(state="readonly")
        self._set_text(self.story, "")
        self._set_text(self.criteria, "")
        self._set_text(self.notes, "")
        self.links_label.configure(text="Not linked to spec nodes yet")

    def show_history(self) -> None:
        requirement_id = self.form["id"].get().strip()
        if not requirement_id:
            return
        versions = self.service.requirement_versions(requirement_id)
        window = tk.Toplevel(self)
        window.title(f"Version history - {requirement_id}")
        window.geometry("720x380")
        tree = ttk.Treeview(window, columns=("version", "created", "title"),
                            show="headings")
        for column, label, width in (("version", "Version", 80),
                                     ("created", "Created", 220),
                                     ("title", "Title", 360)):
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        for version in versions:
            tree.insert("", "end", values=(
                version["version"], version["created_at"],
                version["payload"].get("title", "")))
        tree.pack(fill="both", expand=True, padx=10, pady=10)


class DslScreen(Screen):
    def build(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Specification DSL", font=UI_TITLE).pack(side="left")
        ttk.Button(toolbar, text="Save as new version",
                   command=self.save_spec).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Parse", command=self.parse_spec).pack(
            side="right", padx=4)
        ttk.Button(toolbar, text="Reload", command=self.refresh).pack(
            side="right", padx=4)
        ttk.Label(toolbar, text="Ctrl+S saves", foreground=MUTED).pack(
            side="right", padx=10)

        paned = ttk.Panedwindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        editor_frame = ttk.Frame(paned)
        self.text = tk.Text(editor_frame, wrap="none", undo=True, font=MONO,
                            relief="solid", borderwidth=1, background="#fcfdfe",
                            tabs=("2c",))
        yscroll = ttk.Scrollbar(editor_frame, orient="vertical",
                                command=self.text.yview)
        xscroll = ttk.Scrollbar(editor_frame, orient="horizontal",
                                command=self.text.xview)
        self.text.configure(yscrollcommand=yscroll.set,
                            xscrollcommand=xscroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)
        paned.add(editor_frame, weight=5)

        bottom = ttk.Frame(paned)
        columns = ("severity", "line", "col", "code", "message")
        self.diagnostics = ttk.Treeview(bottom, columns=columns, show="headings",
                                        height=7)
        for column, label, width in (
            ("severity", "Severity", px(80)), ("line", "Line", px(55)),
            ("col", "Col", px(50)), ("code", "Code", px(70)),
            ("message", "Message", px(760)),
        ):
            self.diagnostics.heading(column, text=label)
            self.diagnostics.column(column, width=width, anchor="w")
        self.diagnostics.tag_configure("error", foreground=BAD)
        self.diagnostics.tag_configure("warning", foreground=WARN)
        self.diagnostics.tag_configure("info", foreground="#1a4f8b")
        self.diagnostics.pack(fill="both", expand=True, pady=(6, 0))
        self.diagnostics.bind("<Double-1>", self.jump_to_diagnostic)
        self.diagnostics.bind("<Return>", self.jump_to_diagnostic)
        paned.add(bottom, weight=2)

        self.text.tag_configure("keyword", foreground="#0b5d8a", font=("Consolas", 10, "bold"))
        self.text.tag_configure("type", foreground="#7b3fa0")
        self.text.tag_configure("number", foreground="#b26a00")
        self.text.tag_configure("string", foreground="#0b6e4f")
        self.text.tag_configure("comment", foreground="#8a97a3", font=("Consolas", 10, "italic"))
        self.text.tag_configure("ref", foreground="#b3261e")
        self.text.tag_configure("const", foreground="#1a4f8b")
        self.text.tag_configure("errorline", background="#ffe9e7")
        self.text.bind("<<Modified>>", self.on_modified)
        self.text.bind("<Control-s>", lambda event: self.save_spec())
        self.text.bind("<Control-S>", lambda event: self.save_spec())
        self._highlight_job = None
        self._diagnostics: list = []
        self._loading = False
        self._dirty = False
        self.refresh()

    def refresh(self) -> None:
        if self._dirty and self.text.get("1.0", "end-1c") != self.service.content:
            return
        self._loading = True
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.service.content)
        self.text.edit_modified(False)
        self._loading = False
        self._dirty = False
        self.parse_spec()

    def on_modified(self, event=None) -> None:
        if self._loading:
            return
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._dirty = True
            if self._highlight_job:
                self.after_cancel(self._highlight_job)
            self._highlight_job = self.after(200, self.highlight)

    def highlight(self) -> None:
        content = self.text.get("1.0", "end-1c")
        for tag in ("keyword", "type", "number", "string", "comment", "ref",
                    "const", "errorline"):
            self.text.tag_remove(tag, "1.0", "end")
        for match in TOKEN_RE.finditer(content):
            start = f"1.0 + {match.start()} chars"
            end = f"1.0 + {match.end()} chars"
            token = match.group(0)
            if token.startswith("//") or token.startswith("#"):
                self.text.tag_add("comment", start, end)
            elif token.startswith('"'):
                self.text.tag_add("string", start, end)
            elif token.isdigit():
                self.text.tag_add("number", start, end)
            elif re.fullmatch(r"[A-Z]{1,4}-\d+", token):
                self.text.tag_add("ref", start, end)
            elif token in TYPES:
                self.text.tag_add("type", start, end)
            elif token in KEYWORDS:
                self.text.tag_add("keyword", start, end)
            elif token in {"BRI", "INV"}:
                self.text.tag_add("const", start, end)
        for diagnostic in self._diagnostics:
            if diagnostic.severity == "error":
                line = diagnostic.line
                self.text.tag_add("errorline", f"{line}.0", f"{line}.end")

    def parse_spec(self) -> None:
        content = self.text.get("1.0", "end-1c")
        self.highlight()
        parsed = parse(content, "editor.sforge")
        self._diagnostics = parsed.diagnostics
        self.diagnostics.delete(*self.diagnostics.get_children())
        for diagnostic in parsed.diagnostics:
            self.diagnostics.insert("", "end", tags=(diagnostic.severity,),
                                    values=(diagnostic.severity, diagnostic.line,
                                            diagnostic.col, diagnostic.code,
                                            diagnostic.message))
        self.highlight()
        errors = sum(1 for d in parsed.diagnostics if d.severity == "error")
        warnings = len(parsed.diagnostics) - errors
        self.app.set_status(
            f"DSL: {errors} error(s), {warnings} warning(s), "
            f"{len(parsed.program.entities)} entities, "
            f"{len(parsed.program.rules)} rules")
        return parsed

    def jump_to_diagnostic(self, event=None) -> None:
        selected = self.diagnostics.selection()
        if not selected:
            return
        values = self.diagnostics.item(selected[0], "values")
        line, col = int(values[1]), int(values[2])
        index = f"{line}.{max(0, col - 1)}"
        self.text.mark_set("insert", index)
        self.text.see(index)
        self.text.focus_set()

    def save_spec(self) -> None:
        content = self.text.get("1.0", "end-1c")
        result = self.service.update_spec(content)
        self._dirty = False
        self.service = self.app.service
        self.parse_spec()
        self.app.refresh_all(except_screen=self)
        if result["ok"]:
            self.app.set_status(
                f"Specification saved as version {self.service.spec_record['version']}")
        else:
            errors = [item for item in result["diagnostics"]
                      if item["severity"] == "error"]
            messagebox.showerror(
                "Specification has errors",
                "The specification was stored, but it has errors:\n\n" +
                "\n".join(f"{item['line']}:{item['col']} {item['message']}"
                          for item in errors[:10]))


class GraphScreen(Screen):
    def build(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="State machine", font=UI_TITLE).pack(side="left")
        self.machine = tk.StringVar()
        self.selector = ttk.Combobox(toolbar, textvariable=self.machine,
                                     state="readonly", width=24)
        self.selector.pack(side="left", padx=12)
        self.selector.bind("<<ComboboxSelected>>", lambda event: self.draw())
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(
            side="right", padx=4)

        self.canvas = tk.Canvas(self, background="#fafbfc",
                                highlightthickness=1,
                                highlightbackground=LINE)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.info = ttk.Label(self, text="", foreground=MUTED, padding=(12, 6),
                              wraplength=1100, justify="left")
        self.info.pack(fill="x")
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.machine.set("")
        self.refresh()

    def refresh(self) -> None:
        names = sorted(self.service.graphs)
        self.selector.configure(values=names)
        if names and self.machine.get() not in names:
            self.machine.set(names[0])
        self.draw()

    def draw(self) -> None:
        self.canvas.delete("all")
        name = self.machine.get()
        graph = self.service.graphs.get(name)
        if graph is None:
            self.canvas.create_text(20, 20, anchor="nw", text="No state machine",
                                    fill=MUTED)
            return
        canvas_width = max(400, self.canvas.winfo_width())
        canvas_height = max(300, self.canvas.winfo_height())
        scale = min((canvas_width - 40) / max(1, graph.width),
                    (canvas_height - 40) / max(1, graph.height), 3.0)
        offset_x = (canvas_width - graph.width * scale) / 2
        offset_y = (canvas_height - graph.height * scale) / 2

        positions = {}
        for node in graph.nodes:
            positions[node.name] = (offset_x + node.x * scale,
                                    offset_y + node.y * scale)
        for edge in graph.edges:
            start = positions.get(edge.source)
            end = positions.get(edge.target)
            if not start or not end:
                continue
            source_node = graph.node(edge.source)
            hot = bool(source_node and (not source_node.reachable or source_node.in_cycle))
            color = "#ef6c00" if hot else "#78909c"
            if edge.self_loop:
                x, y = start
                self.canvas.create_arc(x - 34, y - NODE_H * scale - 30,
                                       x + 34, y - NODE_H * scale + 20,
                                       start=20, extent=320, style="arc",
                                       outline=color, width=1.4)
                self.canvas.create_text(x, y - NODE_H * scale - 34,
                                        text=edge.event, fill=color,
                                        font=("Segoe UI", 8))
                continue
            sx, sy = start
            ex, ey = end
            dx, dy = ex - sx, ey - sy
            distance = max(1.0, (dx * dx + dy * dy) ** 0.5)
            ux, uy = dx / distance, dy / distance
            half_w = NODE_W * scale / 2
            half_h = NODE_H * scale / 2
            sx2 = sx + ux * (abs(ux) * half_w + 3)
            sy2 = sy + uy * (abs(uy) * half_h + 3)
            ex2 = ex - ux * (abs(ux) * half_w + 3)
            ey2 = ey - uy * (abs(uy) * half_h + 3)
            self.canvas.create_line(sx2, sy2, ex2, ey2, fill=color, width=1.3,
                                    arrow=tk.LAST, arrowshape=(8, 10, 4))
            self.canvas.create_text((sx + ex) / 2, (sy + ey) / 2 - 6,
                                    text=edge.event, fill=color,
                                    font=("Segoe UI", 8))

        for node in graph.nodes:
            x, y = positions[node.name]
            if not node.reachable:
                fill, outline, text_color = "#ffebee", BAD, BAD
            elif node.in_cycle:
                fill, outline, text_color = "#fff8e1", WARN, "#e65100"
            elif node.initial:
                fill, outline, text_color = "#e8f5e9", "#2e7d32", "#1b5e20"
            else:
                fill, outline, text_color = "#ffffff", "#546e7a", INK
            tag = f"node:{node.name}"
            rectangle = self.canvas.create_rectangle(
                x - NODE_W * scale / 2, y - NODE_H * scale / 2,
                x + NODE_W * scale / 2, y + NODE_H * scale / 2,
                fill=fill, outline=outline, width=1.6, tags=(tag,))
            label = self.canvas.create_text(
                x, y, text=node.name, fill=text_color,
                font=("Segoe UI", max(8, int(10 * scale))), tags=(tag,))
            self.canvas.tag_bind(tag, "<Button-1>",
                                 lambda event, n=node.name: self.show_node(n))

        summary = [f"{graph.machine}: initial {graph.initial}",
                   f"states {len(graph.nodes)}, transitions {len(graph.edges)}"]
        if graph.unreachable:
            summary.append("unreachable: " + ", ".join(graph.unreachable))
        if graph.cycles:
            summary.append("cycles: " + "; ".join(" -> ".join(c) for c in graph.cycles))
        if graph.dead_ends:
            summary.append("dead ends: " + ", ".join(graph.dead_ends))
        self.info.configure(text=" | ".join(summary))

    def show_node(self, name: str) -> None:
        graph = self.service.graphs.get(self.machine.get())
        if graph is None:
            return
        node = graph.node(name)
        if node is None:
            return
        outgoing = [edge for edge in graph.edges if edge.source == name]
        detail = [f"{graph.machine}.{name}",
                  f"reachable: {node.reachable}, in cycle: {node.in_cycle}, "
                  f"initial: {node.initial}"]
        for edge in outgoing:
            guard = f" when {edge.guard}" if edge.guard else ""
            detail.append(f"  -> {edge.target} on {edge.event}{guard}")
        self.info.configure(text=" | ".join(detail))


class TraceScreen(Screen):
    def build(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Traceability matrix", font=UI_TITLE).pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(
            side="right", padx=4)
        self.summary = ttk.Label(toolbar, text="", foreground=MUTED)
        self.summary.pack(side="right", padx=12)

        columns = ("id", "title", "status", "nodes", "tests", "result")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        for column, label, width in (
            ("id", "Requirement", px(90)), ("title", "Title", px(330)),
            ("status", "Coverage", px(100)), ("nodes", "Spec nodes", px(110)),
            ("tests", "Tests", px(70)), ("result", "Last result", px(100)),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.tag_configure("covered", foreground=ACCENT)
        self.tree.tag_configure("partial", foreground=WARN)
        self.tree.tag_configure("uncovered", foreground=BAD)
        self.tree.tag_configure("no_spec", foreground=BAD)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.tree.bind("<Double-1>", self.show_detail)

        self.issues = tk.Text(self, height=8, wrap="word", font=UI,
                              relief="solid", borderwidth=1, background=CARD)
        self.issues.pack(fill="x", padx=10, pady=(0, 10))
        self.issues.configure(state="disabled")

    def refresh(self) -> None:
        report = self.service.traceability()
        self.tree.delete(*self.tree.get_children())
        for row in report.rows:
            self.tree.insert("", "end", iid=row.requirement_id, tags=(row.status,),
                             values=(row.requirement_id, row.title, row.status,
                                     len(row.nodes), len(row.tests),
                                     row.last_result or "no run"))
        summary = report.summary
        self.summary.configure(
            text=f"coverage {report.coverage_percent:.1f}% - "
                 f"covered {summary['covered']}, partial {summary['partial']}, "
                 f"uncovered {summary['uncovered']}, dead nodes {summary['dead_nodes']}")
        self.issues.configure(state="normal")
        self.issues.delete("1.0", "end")
        for issue in report.issues:
            self.issues.insert("end", issue + "\n")
        self.issues.configure(state="disabled")

    def show_detail(self, event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        requirement_id = selected[0]
        report = self.service.traceability()
        row = next((item for item in report.rows
                    if item.requirement_id == requirement_id), None)
        if row is None:
            return
        window = tk.Toplevel(self)
        window.title(f"Trace - {requirement_id}")
        window.geometry("820x520")
        text = tk.Text(window, wrap="word", font=UI)
        text.pack(fill="both", expand=True, padx=10, pady=10)
        results = self.service.latest_results_map()
        text.insert("end", f"{requirement_id}: {row.title}\n")
        text.insert("end", f"Coverage: {row.status}\n\nSpec nodes:\n")
        for node_id in row.nodes:
            node = self.service.index.get(node_id)
            signature = node.signature if node else ""
            text.insert("end", f"  {node_id}\n    {signature}\n")
        text.insert("end", "\nTests:\n")
        for test_id in row.tests:
            result = results.get(test_id)
            status = result["status"] if result else "not run"
            text.insert("end", f"  {test_id} [{status}]\n")
        text.configure(state="disabled")


class ImpactScreen(Screen):
    def build(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Change requests and impact",
                  font=UI_TITLE).pack(side="left")
        ttk.Button(toolbar, text="Apply and analyse",
                   command=self.apply_cr).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Reset spec",
                   command=self.reset_spec).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(
            side="right", padx=4)

        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(paned)
        columns = ("id", "kind", "title")
        self.crs = ttk.Treeview(left, columns=columns, show="headings",
                                selectmode="browse")
        for column, label, width in (("id", "CR", px(80)),
                                     ("kind", "Type", px(120)),
                                     ("title", "Title", px(280))):
            self.crs.heading(column, text=label)
            self.crs.column(column, width=width, anchor="w")
        self.crs.pack(fill="both", expand=True)
        self.crs.bind("<<TreeviewSelect>>", self.show_cr)
        self.description = tk.Text(left, height=9, wrap="word", font=UI,
                                   relief="solid", borderwidth=1, background=CARD)
        self.description.pack(fill="x", pady=(6, 0))
        self.description.configure(state="disabled")
        paned.add(left, weight=2)

        right = ttk.Frame(paned, padding=(10, 0, 0, 0))
        columns = ("test", "reason")
        self.plan = ttk.Treeview(right, columns=columns, show="headings")
        self.plan.heading("test", text="Test to run")
        self.plan.heading("reason", text="Why it is affected")
        self.plan.column("test", width=px(90), anchor="w")
        self.plan.column("reason", width=px(520), anchor="w")
        self.plan.pack(fill="both", expand=True)
        self.result = tk.Text(right, height=12, wrap="word", font=UI,
                              relief="solid", borderwidth=1, background=CARD)
        self.result.pack(fill="x", pady=(6, 0))
        self.result.configure(state="disabled")
        paned.add(right, weight=4)
        self.refresh()

    def refresh(self) -> None:
        self.crs.delete(*self.crs.get_children())
        for cr in self.service.change_requests():
            self.crs.insert("", "end", iid=cr.id,
                            values=(cr.id, cr.kind, cr.title))
        if self.crs.get_children() and not self.crs.selection():
            self.crs.selection_set(self.crs.get_children()[0])
        self.show_cr()

    def show_cr(self, event=None) -> None:
        selected = self.crs.selection()
        if not selected:
            return
        cr = self.service.change_request(selected[0])
        if cr is None:
            return
        self.description.configure(state="normal")
        self.description.delete("1.0", "end")
        self.description.insert(
            "end", f"{cr.id} [{cr.kind}]\n{cr.title}\n\n{cr.description}\n\n"
                   f"Target nodes: {', '.join(cr.target_nodes) or '-'}\n"
                   f"Spec edits: {len(cr.spec_edits)}, "
                   f"requirement edits: {len(cr.requirement_edits)}")
        self.description.configure(state="disabled")

    def apply_cr(self) -> None:
        selected = self.crs.selection()
        if not selected:
            messagebox.showinfo("Impact", "Select a change request first")
            return
        cr_id = selected[0]
        try:
            result = self.service.apply_change_request(cr_id, verify=True)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            messagebox.showerror("Impact analysis", str(exc))
            return
        plan = result["plan"]
        minimality = result["minimality"]
        self.plan.delete(*self.plan.get_children())
        for test_id in plan["tests"]:
            self.plan.insert("", "end",
                             values=(test_id, "; ".join(plan["reasons"][test_id])))
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert(
            "end",
            f"{plan['cr_id']}: {len(plan['changed_nodes'])} changed nodes, "
            f"{len(plan['affected_nodes'])} affected nodes, "
            f"{len(plan['tests'])} of {plan['tests_total']} tests selected\n\n"
            f"Changed nodes:\n  " + "\n  ".join(plan["changed_nodes"]) +
            f"\n\nRegenerate: {', '.join(plan['regenerate']) or 'none'}\n"
            f"Conflicts: {'; '.join(plan['conflicts']) or 'none'}\n\n"
            f"Minimality: selected failed {len(minimality['subset_failed'])}, "
            f"full failed {len(minimality['full_failed'])}, "
            f"equal={minimality['equal']}\n"
            f"Failed tests: {', '.join(minimality['full_failed']) or 'none'}")
        self.result.configure(state="disabled")
        self.app.refresh_all(except_screen=self)
        self.app.set_status(
            f"Impact {plan['cr_id']}: {len(plan['tests'])} tests selected, "
            f"failed {len(minimality['full_failed'])}, "
            f"minimality equal={minimality['equal']}")
        self.crs.selection_set(cr_id)
        self.show_cr()

    def reset_spec(self) -> None:
        if messagebox.askyesno("Reset", "Restore the packaged specification?"):
            self.service.reset_spec()
            self.app.refresh_all()
            self.app.set_status("Specification reset to the packaged version")


class TestsScreen(Screen):
    def build(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Tests and reports", font=UI_TITLE).pack(side="left")
        ttk.Button(toolbar, text="Export HTML report",
                   command=self.export_report).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Check properties",
                   command=self.check_properties).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Regenerate tests",
                   command=self.regenerate).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Run all tests",
                   command=self.run_tests).pack(side="right", padx=4)
        ttk.Label(toolbar, text="Seed", foreground=MUTED).pack(side="right", padx=(12, 4))
        self.seed = ttk.Entry(toolbar, width=8)
        self.seed.insert(0, "1234")
        self.seed.pack(side="right")

        self.summary = ttk.Label(self, text="", foreground=MUTED,
                                 padding=(12, 2))
        self.summary.pack(fill="x")

        columns = ("id", "kind", "status", "title", "message")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        for column, label, width in (
            ("id", "Test", px(70)), ("kind", "Kind", px(90)),
            ("status", "Status", px(80)), ("title", "Title", px(330)),
            ("message", "Message", px(500)),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.tag_configure("passed", foreground=ACCENT)
        self.tree.tag_configure("failed", foreground=BAD)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.tree.bind("<Double-1>", self.show_detail)
        self.refresh()

    def refresh(self) -> None:
        results = self.service.latest_results_map()
        self.tree.delete(*self.tree.get_children())
        for test in self.service.tests:
            result = results.get(test.id)
            status = result["status"] if result else "not run"
            message = result["message"] if result else ""
            self.tree.insert("", "end", iid=test.id, tags=(status,),
                             values=(test.id, test.kind, status, test.title,
                                     message[:200]))
        run = self.service.latest_run()
        if run:
            self.summary.configure(
                text=f"Run {run['id']}: passed {run['passed']}, failed "
                     f"{run['failed']}, digest {run['digest'][:16]}, "
                     f"spec hash {run['spec_hash'][:16]}, seed {run['seed']}")
        else:
            self.summary.configure(text="No run yet")

    def run_tests(self) -> None:
        try:
            seed = int(self.seed.get())
        except ValueError:
            messagebox.showerror("Tests", "Seed must be an integer")
            return
        summary = self.service.run_all_tests(seed=seed)
        self.refresh()
        if summary.failed:
            messagebox.showwarning(
                "Tests failed",
                f"{summary.failed} test(s) failed. See the results table.")
        self.app.refresh_all(except_screen=self)
        self.app.set_status(
            f"Tests: passed {summary.passed}, failed {summary.failed}, "
            f"digest {summary.digest[:16]}")

    def regenerate(self) -> None:
        if not messagebox.askyesno(
                "Regenerate tests",
                "Recompute expected values from the current specification? "
                "This clears the evidence of current failures."):
            return
        self.service.regenerate_tests()
        self.refresh()
        self.app.refresh_all(except_screen=self)
        self.app.set_status("Tests regenerated from the current specification")

    def check_properties(self) -> None:
        report = self.service.properties()
        lines = []
        for item in report["results"]:
            mark = "OK" if item["ok"] else "FAIL"
            lines.append(f"{mark:4} {item['name']} ({item['checks']} checks)")
            for violation in item["violations"][:3]:
                lines.append(f"     {violation}")
        lines.append("")
        lines.append("all properties: " + ("OK" if report["ok"] else "FAIL"))
        messagebox.showinfo("Properties", "\n".join(lines))
        self.app.set_status(
            "8 properties: " + ("OK" if report["ok"] else "FAIL"))

    def export_report(self) -> None:
        if not self.service.latest_run():
            self.service.run_all_tests()
        path = self.service.build_report()
        self.refresh()
        self.app.refresh_all(except_screen=self)
        self.app.set_status(f"Report written to {path}")
        messagebox.showinfo("Report", f"HTML report written to:\n{path}")

    def show_detail(self, event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        test_id = selected[0]
        test = next((item for item in self.service.tests if item.id == test_id),
                    None)
        if test is None:
            return
        result = self.service.latest_results_map().get(test_id)
        window = tk.Toplevel(self)
        window.title(f"Test {test_id}")
        window.geometry("820x560")
        text = tk.Text(window, wrap="word", font=MONO)
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("end", f"{test.id} [{test.kind}] {test.title}\n")
        text.insert("end", f"Requirements: {', '.join(test.requirements)}\n")
        text.insert("end", f"Spec nodes:\n")
        for node_id in test.nodes:
            text.insert("end", f"  {node_id}\n")
        text.insert("end", f"\nSetup:\n{json.dumps(test.setup, indent=2)}\n")
        text.insert("end", f"Steps:\n{json.dumps(test.steps, indent=2)}\n")
        text.insert("end", f"Expected:\n{json.dumps(test.expected, indent=2)}\n")
        if result:
            text.insert("end", f"\nResult: {result['status']}\n")
            text.insert("end", f"Message: {result['message']}\n")
            text.insert("end", f"Actual:\n{json.dumps(result['actual'], indent=2)}\n")
        text.configure(state="disabled")


class SpecForgeApp(tk.Tk):
    def __init__(self, service: Optional[SpecForgeService] = None) -> None:
        enable_high_dpi()
        super().__init__()
        global SCALE
        try:
            import ctypes
            dpi = ctypes.windll.user32.GetDpiForWindow(self.winfo_id())
            if dpi:
                self.tk.call("tk", "scaling", dpi / 72.0)
                SCALE = dpi / 96.0
        except Exception:
            pass
        self.service = service or SpecForgeService()
        self.title("SpecForge - RollCity specification workbench")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(int(1360 * SCALE), max(px(1080), screen_width - 80))
        height = min(int(900 * SCALE), max(px(700), screen_height - 120))
        self.geometry(f"{width}x{height}+20+20")
        self.minsize(px(1000), px(660))
        self.configure(background=BG)
        self._style()

        self.status = ttk.Label(self, text="", padding=(12, 5),
                                relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

        header = ttk.Frame(self, padding=(14, 10), style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="SpecForge", font=("Segoe UI", 18, "bold"),
                  style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="requirements -> DSL -> traceability -> tests",
                  style="Header.TLabel").pack(side="left", padx=14)
        self.header_info = ttk.Label(header, text="", style="Header.TLabel")
        self.header_info.pack(side="right", padx=(0, 18))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.screens = {
            "Requirements": RequirementsScreen(self.notebook, self),
            "DSL": DslScreen(self.notebook, self),
            "State machine": GraphScreen(self.notebook, self),
            "Traceability": TraceScreen(self.notebook, self),
            "Change requests": ImpactScreen(self.notebook, self),
            "Tests": TestsScreen(self.notebook, self),
        }
        for name, screen in self.screens.items():
            self.notebook.add(screen, text=name)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab)

        self.refresh_header()
        self.set_status(f"Database: {self.service.repo.path}")

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=UI, background=BG, foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("TLabelframe", background=BG)
        style.configure("Treeview", background=CARD, fieldbackground=CARD,
                        rowheight=px(24), borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),
                        background="#e8eef2", relief="flat")
        style.map("Treeview", background=[("selected", "#dcebe4")],
                  foreground=[("selected", INK)])
        style.configure("TButton", padding=(px(10), px(4)))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(px(14), px(7)))
        style.map("TNotebook.Tab", background=[("selected", CARD)])
        style.configure("Header.TFrame", background="#123b32")
        style.configure("Header.TLabel", background="#123b32",
                        foreground="#eef7f3")
        style.configure("TEntry", padding=2)
        style.configure("TPanedwindow", background=BG)

    def on_tab(self, event=None) -> None:
        current = self.notebook.tab(self.notebook.select(), "text")
        screen = self.screens.get(current)
        if screen is not None:
            screen.refresh()

    def refresh_all(self, except_screen: Optional[Screen] = None) -> None:
        self.refresh_header()
        for screen in self.screens.values():
            if screen is except_screen:
                continue
            try:
                screen.refresh()
            except Exception as exc:  # noqa: BLE001 - keep the UI alive
                self.set_status(f"refresh error: {exc}")

    def refresh_header(self) -> None:
        self.header_info.configure(
            text=f"spec v{self.service.spec_record['version']}  |  "
                 f"{len(self.service.index.nodes)} nodes  |  "
                 f"{len(self.service.tests)} tests  |  "
                 f"{len(self.service.requirements)} requirements")
        self.update_idletasks()

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)
        self.update_idletasks()


def run() -> None:
    app = SpecForgeApp()
    app.mainloop()


if __name__ == "__main__":
    run()
