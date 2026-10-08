"""Main application window: the launcher (create or open a project), then the
project workspace (``shell.py``).

The workspace has no permanent sidebar. A top bar leads to six sections -
Home, Chapters, Characters, Game Data, Assets, Disc & Patch - and Ctrl+K
searches all of them. A chapter page gathers the chapter's map, deployment, dialogue and
script; a character page gathers the character's record, portrait, models and
every place they appear (``project_index.py`` joins the formats for that).
Every editor is an embedded ``EditorPanel`` created on first use and kept for
the whole session, so moving around never loses work.
"""

from __future__ import annotations

import tkinter as tk
import sys
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import config
from ..exceptions import ProjectError
from ..project import ModProject
from . import theme
from .changelog import ChangeLog
from .new_project_dialog import NewProjectDialog
from .patch_dialog import ApplyPatchDialog
from .settings_dialog import SettingsDialog
from .pages import ASSET_TOOLS, PAGE_FACTORIES
from .shell import NAV, Shell
from .widgets import Card, CardGrid, ScrollFrame, disable_wheel_value_changes


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tellius Modding")
        self.geometry("1360x860")
        self.minsize(960, 600)
        theme.setup(self)
        disable_wheel_value_changes(self)

        self._project: ModProject | None = None
        self._shell: Shell | None = None
        self._container = ttk.Frame(self, style="Page.TFrame")
        self._container.pack(fill="both", expand=True)

        self._build_menu()
        for key in ("<Control-k>", "<Control-K>"):
            self.bind(key, lambda e: self._shell.on_search_key(e) if self._shell else None)
        self.bind("<F5>", lambda e: self._shell and self._shell.open_play_chapter())
        self.bind("<Control-F5>", lambda e: self._shell and self._shell.play())
        self.bind("<Alt-Left>", lambda e: self._shell and self._shell.back())
        self.bind("<Alt-Right>", lambda e: self._shell and self._shell.forward())
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)
        self._show_launcher()
        from ..tools import WIT_EXE
        if getattr(sys, "frozen", False) and not WIT_EXE.is_file() and "--self-test" not in sys.argv:
            self.after(200, self._setup_tools)

    # -- menu -----------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project...", command=self._new_project)
        file_menu.add_command(label="Open Project...", command=self._open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Close Project", command=self._close_project)
        file_menu.add_separator()
        file_menu.add_command(label="Apply patch to a disc...", command=lambda: ApplyPatchDialog(self))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_app_close)
        menubar.add_cascade(label="File", menu=file_menu)

        go_menu = tk.Menu(menubar, tearoff=False)
        for key, label in NAV:
            go_menu.add_command(label=label, command=lambda k=key: self._go((k,)))
        go_menu.add_separator()
        go_menu.add_command(label="Search...", accelerator="Ctrl+K",
                            command=lambda: self._shell and self._shell.open_search())
        go_menu.add_command(label="Back", accelerator="Alt+Left", command=lambda: self._shell and self._shell.back())
        go_menu.add_command(label="Forward", accelerator="Alt+Right",
                            command=lambda: self._shell and self._shell.forward())
        menubar.add_cascade(label="Go", menu=go_menu)

        play_menu = tk.Menu(menubar, tearoff=False)
        play_menu.add_command(label="Play chapter in Dolphin...", accelerator="F5",
                              command=lambda: self._shell and self._shell.open_play_chapter())
        play_menu.add_command(label="Build and play disc in Dolphin", accelerator="Ctrl+F5",
                              command=lambda: self._shell and self._shell.play())
        menubar.add_cascade(label="Play", menu=play_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Changes this session", command=lambda: self._shell and self._shell.toggle_activity())
        menubar.add_cascade(label="View", menu=view_menu)

        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_command(label="Preferences...", command=lambda: SettingsDialog(self))
        settings_menu.add_command(label="Disc and media tools...", command=self._setup_tools)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        self.config(menu=menubar)

    def _setup_tools(self):
        from .tool_setup import ToolSetupDialog
        ToolSetupDialog(self)

    def _go(self, route) -> None:
        if self._shell is not None:
            self._shell.navigate(route)

    # -- launcher screen --------------------------------------------------
    def _show_launcher(self) -> None:
        self._project = None
        self._clear_container()

        scroll = ScrollFrame(self._container, padding=(0, 0))
        scroll.pack(fill="both", expand=True)
        column = ttk.Frame(scroll.body, style="Page.TFrame", padding=(48, 56, 48, 32))
        column.pack(anchor="n")

        ttk.Label(column, text="◆  Tellius Modding", style="Title.TLabel").pack(anchor="w")
        ttk.Label(column, text="Modding toolkit for Fire Emblem: Path of Radiance and Radiant Dawn.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 24))

        buttons = ttk.Frame(column, style="Page.TFrame")
        buttons.pack(anchor="w", pady=(0, 32))
        ttk.Button(buttons, text="New project…", style="Accent.TButton", command=self._new_project).pack(side="left")
        ttk.Button(buttons, text="Open project folder…", command=self._open_project).pack(side="left", padx=(8, 0))

        ttk.Label(column, text="Recent projects", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 10))
        recent = config.load_recent_projects()
        if not recent:
            ttk.Label(column, text="No recent projects.", style="Muted.TLabel").pack(anchor="w")
            return
        grid = CardGrid(column, card_width=620, gap=8)
        grid.pack(fill="x")
        for path in recent:
            exists = path.is_dir()
            grid.add(path, Card(grid, title=path.name, subtitle=str(path),
                                caption="" if exists else "Folder not found", width=620,
                                on_click=(lambda p=path: self._load_project(p)) if exists else None))
        grid.done()

    # -- actions ----------------------------------------------------------
    def _new_project(self) -> None:
        if not self._confirm_leave_project():
            return
        dialog = NewProjectDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            self._activate_project(dialog.result)

    def _open_project(self) -> None:
        chosen = filedialog.askdirectory(title="Open Project Folder", parent=self)
        if chosen:
            self._load_project(Path(chosen))

    def _load_project(self, directory: Path) -> None:
        if not self._confirm_leave_project():
            return
        try:
            project = ModProject.load(directory)
        except ProjectError as exc:
            messagebox.showerror("Could not open project", str(exc), parent=self)
            return
        self._activate_project(project)

    def _activate_project(self, project: ModProject) -> None:
        self._teardown()
        self._project = project
        config.add_recent_project(project.directory)
        self._clear_container()
        self._shell = Shell(self._container, project, ChangeLog(), PAGE_FACTORIES,
                            on_close_project=self._close_project,
                            asset_tools=tuple((key, label) for key, label, *_rest in ASSET_TOOLS))
        self._shell.pack(fill="both", expand=True)
        self._shell.navigate(("home",))
        self.title(f"{project.name} - Tellius Modding")

    def _confirm_leave_project(self) -> bool:
        """Before closing a project with unsaved edits, offer to save them all."""
        if self._shell is None:
            return True
        return self._shell.confirm_unsaved("", "close without saving (the changes are lost).")

    def _close_project(self) -> None:
        if not self._confirm_leave_project():
            return
        self._teardown()
        self.title("Tellius Modding")
        self._show_launcher()

    def _on_app_close(self) -> None:
        if not self._confirm_leave_project():
            return
        self._teardown()
        self.destroy()

    def _teardown(self) -> None:
        if self._shell is not None:
            self._shell.cleanup()
            self._shell = None

    # -- helpers ----------------------------------------------------------
    def _clear_container(self) -> None:
        for child in self._container.winfo_children():
            child.destroy()


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
