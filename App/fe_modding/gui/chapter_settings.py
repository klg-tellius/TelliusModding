"""The per-chapter Map settings and Chapter data tabs.

Map settings edit the selected phase through Build's Undo/Redo and Save Chapter.
Chapter data edits the shared FE8Data.bin session and has its own save control.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .map_windows import MapSettingsForm
from .stats_editor import ChapterRecordPanel
from .widgets import ScrollFrame


class MapSettingsPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, builder) -> None:
        super().__init__(parent)
        self._map = builder.map_editor

        scroll = ScrollFrame(self, padding=(16, 12))
        scroll.pack(fill="both", expand=True)
        body = scroll.body
        top = ttk.Frame(body)
        top.pack(fill="x", anchor="w")
        ttk.Label(top, text="Map", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="Save Chapter", command=builder.save_chapter).pack(side="left", padx=(12, 0))
        self._map_label = ttk.Label(top, text="", style="Muted.TLabel")
        self._map_label.pack(side="left", padx=(10, 0))
        ttk.Label(body, style="Muted.TLabel", wraplength=720, justify="left", text=(
            "Lighting, fog, grid and water of the phase picked at the top of the page. Apply puts the changes on the "
            "Build tab's Undo/Redo; Save Chapter writes them.")).pack(anchor="w", pady=(2, 8))
        MapSettingsForm(body, builder).pack(fill="x", anchor="w")

        self._map.add_listener(self._on_map_changed)
        self._on_map_changed()

    def _on_map_changed(self) -> None:
        if self.winfo_exists():
            self._map_label.configure(text=self._map.map_name or "")

    def cleanup(self) -> None:
        self._map.remove_listener(self._on_map_changed)


class ChapterDataPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, builder, session_provider: Callable[[], object]) -> None:
        super().__init__(parent)
        self._chapter_record: ChapterRecordPanel | None = None
        scroll = ScrollFrame(self, padding=(16, 12))
        scroll.pack(fill="both", expand=True)
        session = session_provider()
        if session.available:
            self._chapter_record = ChapterRecordPanel(
                scroll.body, builder.project, builder.changelog, session, navigate=builder.navigate)
            self._chapter_record.pack(fill="x", anchor="w")
        else:
            ttk.Label(scroll.body, text=session.unavailable_reason, style="Muted.TLabel").pack(anchor="w")

    def show_chapter(self, chapter_id: str, map_name: str | None) -> None:
        if self._chapter_record is not None:
            self._chapter_record.show_chapter(int(chapter_id) if chapter_id.isdigit() else None, map_name)

    def flush(self) -> None:
        if self._chapter_record is not None:
            self._chapter_record.flush()

    def cleanup(self) -> None:
        if self._chapter_record is not None:
            self._chapter_record.cleanup()
