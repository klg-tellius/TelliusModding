"""Check: runs the project check (``validator.py``) and lists what it finds - dangling record
references, missing chapter files, unreachable chapters. Double-click a row to open the place
to fix it."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from ... import validator
from ..shell import Page


class CheckPage(Page):
    kind = "check"

    def __init__(self, shell):
        super().__init__(shell)
        self._rows: dict[str, validator.Issue] = {}
        self._results: "queue.Queue" = queue.Queue()
        self._running = False
        top = ttk.Frame(self, style="Page.TFrame", padding=(28, 12, 28, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Check project", style="Title.TLabel").pack(side="left")
        self._button = ttk.Button(top, text="Run check", style="Accent.TButton", command=self.run)
        self._button.pack(side="left", padx=(16, 0))
        self._summary = tk.StringVar(value="Finds broken references and missing chapter files before the game does.")
        ttk.Label(self, textvariable=self._summary, style="Muted.TLabel", wraplength=900, justify="left",
                  padding=(28, 0, 28, 8)).pack(anchor="w")
        holder = ttk.Frame(self, style="Page.TFrame", padding=(28, 0, 28, 20))
        holder.pack(fill="both", expand=True)
        columns = (("severity", "Severity", 80), ("area", "Area", 120), ("where", "File", 220), ("message", "Problem", 560))
        self._tree = ttk.Treeview(holder, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, label, width in columns:
            self._tree.heading(key, text=label)
            self._tree.column(key, width=width, stretch=key == "message")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<Double-Button-1>", lambda e: self._open_selected())
        self._tree.bind("<Return>", lambda e: self._open_selected())

    def crumbs(self, route):
        return [("Home", ("home",)), ("Check", None)]

    def show(self, route) -> bool:
        return True

    def run(self) -> None:
        if self._running:
            return
        self._running = True
        self._button.state(["disabled"])
        self._summary.set("Checking…")
        project = self.project

        def work():
            try:
                flow = None
                try:
                    from .chapters import open_flow
                    flow, _problem = open_flow(project)
                except Exception:  # noqa: BLE001 - the flow is optional
                    flow = None
                self._results.put(("ok", validator.validate_project(project, flow)))
            except Exception as exc:  # noqa: BLE001 - shown to the user, not lost in the thread
                self._results.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
        self.after(150, self._poll)

    def _poll(self) -> None:
        try:
            status, payload = self._results.get_nowait()
        except queue.Empty:
            self.after(150, self._poll)
            return
        self._running = False
        self._button.state(["!disabled"])
        if status == "error":
            self._summary.set(f"The check failed: {payload}")
            return
        self._show(payload)

    def _show(self, report: validator.Report) -> None:
        self._tree.delete(*self._tree.get_children())
        self._rows = {}
        for issue in report.issues:
            row = self._tree.insert("", "end", values=(issue.severity, issue.area, issue.where, issue.message))
            self._rows[row] = issue
        errors, warnings = len(report.errors), len(report.warnings)
        self._summary.set("No problems found." if not report.issues else
                          f"{errors} error{'s' if errors != 1 else ''}, {warnings} warning{'s' if warnings != 1 else ''}. "
                          "Double-click a row to open it.")

    def _open_selected(self) -> None:
        selection = self._tree.selection()
        issue = self._rows.get(selection[0]) if selection else None
        if issue is not None and issue.route:
            self.shell.navigate(issue.route)
