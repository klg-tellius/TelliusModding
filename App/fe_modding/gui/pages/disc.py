"""Disc & Patch: everything between the project and a disc image - choosing
and extracting the source disc, building a playable image, and making a
patch to share the mod without the game (``patch.py``)."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from ... import patch, text_export
from ...games import Game
from ..mod_details_dialog import ModDetailsDialog
from ..shell import Page
from ..widgets import ScrollFrame, section_header


class DiscPage(Page):
    kind = "disc"

    def __init__(self, shell):
        super().__init__(shell)
        self._scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        self._scroll.pack(fill="both", expand=True)

    def crumbs(self, route):
        return [("Home", ("home",)), ("Disc & Patch", None)]

    def show(self, route) -> bool:
        self._render()
        return True

    def _render(self) -> None:
        body = self._scroll.body
        for child in body.winfo_children():
            child.destroy()
        project = self.project

        ttk.Label(body, text="Disc & Patch", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"{project.game_info.display_name}  ·  {project.game_info.platform}",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 18))

        section_header(body, "Disc image").pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(body, style="Page.TFrame")
        row.pack(fill="x")
        self._source_card(row).pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._build_card(row).pack(side="left", fill="both", expand=True)

        section_header(body, "Share the mod").pack(anchor="w", pady=(28, 10))
        row = ttk.Frame(body, style="Page.TFrame")
        row.pack(fill="x")
        self._create_patch_card(row).pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._apply_patch_card(row).pack(side="left", fill="both", expand=True)

        if project.game == Game.PATH_OF_RADIANCE:
            section_header(body, "Version control").pack(anchor="w", pady=(28, 10))
            row = ttk.Frame(body, style="Page.TFrame")
            row.pack(fill="x")
            self._text_export_card(row).pack(side="left", fill="both", expand=True, padx=(0, 12))
            ttk.Frame(row, style="Page.TFrame").pack(side="left", fill="both", expand=True)

    def _panel(self, parent: tk.Misc, title: str, text: str) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Surface.TFrame", padding=18)
        ttk.Label(frame, text=title, style="SurfaceHeading.TLabel").pack(anchor="w")
        ttk.Label(frame, text=text, style="SurfaceMuted.TLabel", wraplength=460, justify="left").pack(
            anchor="w", pady=(4, 2))
        return frame

    def _caption(self, frame: ttk.Frame, text: str, pady=(0, 12), style: str = "SurfaceCaption.TLabel") -> None:
        ttk.Label(frame, text=text, style=style, wraplength=460, justify="left").pack(anchor="w", pady=pady)

    def _source_card(self, parent: tk.Misc) -> ttk.Frame:
        project, shell = self.project, self.shell
        frame = self._panel(parent, "Source disc", project.source_iso or "No disc image chosen yet.")
        if project.is_overlay:
            self._caption(frame, (f"Vanilla files: {project.input_root}\nMod files: {project.output_dir}"
                                  if shell.extracted else "No vanilla files yet: extract the disc, or use a folder "
                                  "you already extracted (Dolphin's Extract Entire Disc, WIT)."))
        else:
            self._caption(frame, "Extracted into " + str(project.disc_tree()) if shell.extracted
                          else "Not extracted yet.")
        if project.source_missing:
            self._caption(frame, f"The disc image is no longer at {project.source_path}. Choose it again "
                          "to extract or make a patch; the extracted files keep working without it.")
        for problem in project.input_problems()[:3]:
            self._caption(frame, problem, pady=(0, 4), style="SurfaceWarn.TLabel")
        buttons = ttk.Frame(frame, style="Surface.TFrame")
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Choose disc image…", command=shell.set_source,
                   state="disabled" if shell.task_running else "normal").pack(side="left")
        ttk.Button(buttons, text="Re-extract" if shell.extracted else "Extract",
                   style="TButton" if shell.extracted else "Accent.TButton", command=shell.extract,
                   state="normal" if project.source_iso and not shell.task_running else "disabled").pack(
            side="left", padx=(8, 0))
        if project.is_overlay:
            ttk.Button(buttons, text="Use extracted folder…", command=shell.use_input_folder,
                       state="disabled" if shell.task_running else "normal").pack(side="left", padx=(8, 0))
            self._caption(frame, "The vanilla files are shared by every project of this disc and never "
                          "changed; this project's edits are only in its output folder.", pady=(8, 0))
        elif shell.extracted:
            self._caption(frame, "Re-extracting overwrites the extracted files with the disc's.", pady=(8, 0))
        return frame

    def _build_card(self, parent: tk.Misc) -> ttk.Frame:
        project, shell = self.project, self.shell
        frame = self._panel(parent, "Build",
                            f"Packs the project's files into a {project.game_info.build_extension} disc image.")
        self._caption(frame, f"Output folder: {project.build_dir}")
        ttk.Button(frame, text="Build disc", style="Accent.TButton", command=shell.build,
                   state="normal" if shell.extracted and not shell.task_running else "disabled").pack(anchor="w")
        ttk.Button(frame, text="Build and play in Dolphin", command=shell.play,
                   state="normal" if shell.extracted and not shell.task_running else "disabled").pack(
            anchor="w", pady=(8, 0))
        self._caption(frame, "Needs Dolphin: set its location in Settings if it is not found.", pady=(4, 0))
        if project.last_build_warning:
            self._caption(frame, project.last_build_warning, pady=(8, 0), style="SurfaceWarn.TLabel")
        return frame

    def _create_patch_card(self, parent: tk.Misc) -> ttk.Frame:
        project, shell = self.project, self.shell
        frame = self._panel(parent, "Create a patch",
                            f"A {patch.PATCH_EXTENSION} file holding only the files this mod changes, "
                            "to share instead of a whole disc image.")
        if project.is_overlay:
            self._caption(frame, "Holds the files in the project's output folder, checked against the "
                          "vanilla files it was made from.")
        else:
            self._caption(frame, "Compares the extracted files with a fresh extraction of the source disc, "
                          "so the source disc image must still be where it was chosen from.")
        ttk.Button(frame, text="Create patch…", style="Accent.TButton", command=shell.create_patch,
                   state="normal" if shell.extracted and (project.source_iso or project.is_overlay)
                   and not shell.task_running else "disabled").pack(anchor="w")
        ttk.Button(frame, text="Mod details…",
                   command=lambda: ModDetailsDialog(self, project, on_saved=self._render)).pack(
            anchor="w", pady=(8, 0))
        who = " · ".join(part for part in (project.version, project.author) if part)
        self._caption(frame, who or "No author or version set yet.", pady=(4, 0))
        if shell.last_patch:
            self._caption(frame, shell.last_patch, pady=(8, 0))
        if project.profile.wii and project.is_overlay:
            ttk.Button(frame, text="Export for Riivolution…", command=shell.export_riivolution,
                       state="normal" if shell.extracted and not shell.task_running else "disabled").pack(
                anchor="w", pady=(12, 0))
            self._caption(frame, "The changed files and main.dol patches as a Riivolution folder, to play "
                          "on a Wii or in Dolphin from an unmodified disc.", pady=(4, 0))
        return frame

    def _apply_patch_card(self, parent: tk.Misc) -> ttk.Frame:
        frame = self._panel(parent, "Apply a patch",
                            "Builds a playable disc image from a patch and an unmodified copy of the game.")
        self._caption(frame, "Players can do the same from File ▸ Apply patch to a disc… without a project, "
                      "or with python -m fe_modding.patch apply PATCH DISC OUTPUT.")
        ttk.Button(frame, text="Apply patch…", command=self.shell.apply_patch).pack(anchor="w")
        return frame

    def _text_export_card(self, parent: tk.Misc) -> ttk.Frame:
        frame = self._panel(parent, "Export as text",
                            "Writes the game data as text files to keep in version control (git) and compare "
                            "between versions: FE8Data tables, deployments, shops, messages, decompiled scripts, "
                            "sound cues, the face table and the DBX tables.")
        self._caption(frame, "Export only: the game's own files stay the ones the app edits and builds. Each "
                      "export replaces the folder's previous one.")
        self._export_status = tk.StringVar(value="")
        ttk.Button(frame, text="Export as text…", command=self._export_text,
                   state="normal" if self.shell.extracted else "disabled").pack(anchor="w")
        ttk.Label(frame, textvariable=self._export_status, style="SurfaceCaption.TLabel", wraplength=460,
                  justify="left").pack(anchor="w", pady=(6, 0))
        return frame

    def _export_text(self) -> None:
        chosen = filedialog.askdirectory(title="Folder for the text export (for example a text_export folder "
                                               "in your git repository)", initialdir=str(self.project.directory),
                                         mustexist=False, parent=self)
        if not chosen:
            return
        dest = Path(chosen)
        results: "queue.Queue" = queue.Queue()

        def work() -> None:
            try:
                results.put(("done", text_export.export_project(
                    self.project, dest, progress=lambda label: results.put(("progress", label)))))
            except Exception as exc:  # noqa: BLE001
                results.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()
        self._export_status.set("Exporting…")

        def poll() -> None:
            while True:
                try:
                    kind, value = results.get_nowait()
                except queue.Empty:
                    self.after(150, poll)
                    return
                if kind == "progress":
                    self._export_status.set(f"Exporting: {value}…")
                    continue
                if kind == "error":
                    self._export_status.set(f"Export failed: {value}")
                    return
                written, problems = value
                text = f"Wrote {len(written)} files to {dest}."
                if problems:
                    text += " Skipped: " + "; ".join(problems)
                self._export_status.set(text)
                self.shell.changelog.append("Text export", f"Exported {len(written)} files to {dest}")
                return

        self.after(150, poll)

