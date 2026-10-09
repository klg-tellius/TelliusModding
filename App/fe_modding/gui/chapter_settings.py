"""A chapter page's Settings tab: the open phase's map-wide settings
(lighting, fog, grid colour and border, water - ``map_windows.MapSettingsForm``)
and the chapter's record in Game Data › Chapters (``stats_editor.ChapterRecordPanel``:
title, objectives, music, backgrounds, enemy levels...).

The map settings edit through the Build tab (its Undo/Redo, Save Chapter);
the chapter record edits the shared FE8Data.bin session (Save FE8Data.bin),
so Game Data › Chapters shows each edit at once."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from .map_windows import MapSettingsForm
from .widgets import ScrollFrame


class ChapterSettingsPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, builder, session_provider: Callable[[], object],
                 navigate: Optional[Callable[[tuple], None]] = None) -> None:
        super().__init__(parent)
        self._builder = builder
        self._map = builder.map_editor
        self._session_provider = session_provider
        self._navigate = navigate


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
        if not self.winfo_exists():
            return
        self._map_label.configure(text=self._map.map_name or "")


    def flush(self) -> None:
        """Keep the Settings tab API compatible with the chapter page."""
