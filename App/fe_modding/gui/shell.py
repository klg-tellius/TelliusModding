"""The project workspace: a top bar (sections, search, settings), a breadcrumb
bar with back/forward, the current page, and a status bar with the unsaved
count and the session's change log.

Navigation is by **route**, a tuple whose first item is the page kind:
``("home",)``, ``("chapters",)``, ``("chapter", "03", "map")``,
``("character", "PID_IKE", "look")``, ``("data", "classes")``,
``("asset", "portraits", "IKE")``... :meth:`Shell.navigate` shows the page
for the kind (one instance per kind, created on first use and kept, so its
editors keep their state) and records the route for back/forward.

Leaving a page never loses edits: its editors stay alive with them. The
unsaved count in the status bar lists them, and closing the project asks.
Only a page that reloads its editors with other data (another chapter) asks
first.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ..exceptions import ModdingError, ProjectError
from ..project import ModProject, sanitize_folder_name
from ..project_index import ProjectIndex
from .. import emulator, patch
from . import theme
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .fe8_session import Fe8DataSession
from .patch_dialog import ApplyPatchDialog
from .settings_dialog import SettingsDialog
from .widgets import Link, PortraitCache, track_hover

Route = tuple

NAV = [("home", "Home"), ("chapters", "Chapters"), ("characters", "Characters"), ("data", "Game Data"),
       ("flags", "Flags"), ("saves", "Saves"), ("assets", "Assets"), ("code", "Game Code"), ("check", "Check"),
       ("disc", "Disc & Patch")]
SECTION_OF = {"home": "home", "chapters": "chapters", "chapter": "chapters", "characters": "characters",
              "character": "characters", "data": "data", "flags": "flags", "saves": "saves", "assets": "assets", "asset": "assets", "code": "code", "check": "check", "disc": "disc"}
# Sections that work before the source disc is extracted.
UNEXTRACTED_KINDS = ("home", "disc")


class Page(ttk.Frame):
    """One screen of the workspace. Subclasses set ``kind`` and override
    :meth:`show` (called on every navigation to this kind, before the page is
    displayed; return False to refuse) and :meth:`crumbs`."""

    kind = ""

    def __init__(self, shell: "Shell"):
        super().__init__(shell.host, style="Page.TFrame")
        self.shell = shell

    @property
    def project(self) -> ModProject:
        return self.shell.project

    def show(self, route: Route) -> bool:
        return True

    def crumbs(self, route: Route) -> list[tuple[str, Optional[Route]]]:
        return []

    def history_label(self, route: Route) -> Optional[str]:
        """How Home's "Jump back in" names this route (None: not listed)."""
        return None

    def panels(self) -> list[EditorPanel]:
        """Every editor this page created, for the unsaved count and cleanup."""
        return []

    def index_changed(self) -> None:
        """A fresh :class:`ProjectIndex` is ready (after a save or an extract)."""

    def cleanup(self) -> None:
        for panel in self.panels():
            panel.cleanup()


class Shell(ttk.Frame):
    def __init__(self, master: tk.Misc, project: ModProject, changelog: ChangeLog,
                 page_factories: dict[str, Callable[["Shell"], Page]], *, on_close_project: Callable[[], None],
                 asset_tools: tuple = ()):
        super().__init__(master, style="Page.TFrame")
        self.project = project
        self.changelog = changelog
        self._factories = page_factories
        self._asset_tools = asset_tools  # (key, label) of the Assets tools, for search
        self._on_close_project = on_close_project
        self._pages: dict[str, Page] = {}
        self._current: Optional[Page] = None
        self.route: Optional[Route] = None
        self._back: list[Route] = []
        self._forward: list[Route] = []
        self.visited: list[tuple[Route, str]] = []
        self._session: Optional[Fe8DataSession] = None
        self.portraits = PortraitCache(self, project.extracted_dir)
        self.index: Optional[ProjectIndex] = None
        self._index_thread: Optional[threading.Thread] = None
        self._index_again = False
        self._task_running = False
        self.last_status = ""
        self.last_patch = ""  # what the last "Create patch" made, for the Disc & Patch page
        self._palette: Optional[SearchPalette] = None

        self._build_top_bar()
        self._build_crumb_bar()
        self.host = ttk.Frame(self, style="Page.TFrame")
        self.host.pack(fill="both", expand=True)
        self._build_status_bar()

        changelog.subscribe(self._on_change_entry)
        self._poll_unsaved()
        self.refresh_extracted_state()

    # -- shared services --------------------------------------------------------------
    @property
    def extracted(self) -> bool:
        return self.project.has_extracted_files

    @property
    def session(self) -> Fe8DataSession:
        """The shared FE8Data.bin (characters and game data edit the same bytes)."""
        if self._session is None:
            self._session = Fe8DataSession(self.project, self.changelog)
            self._session.on_saved.append(self.rebuild_index)
        return self._session

    def page(self, kind: str) -> Page:
        if kind not in self._pages:
            self._pages[kind] = self._factories[kind](self)
        return self._pages[kind]

    def existing_page(self, kind: str) -> Optional[Page]:
        return self._pages.get(kind)

    # -- top bar ---------------------------------------------------------------------------
    def _build_top_bar(self) -> None:
        bar = tk.Frame(self, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._top_bar = bar
        brand = tk.Label(bar, text="◆  Tellius", font=theme.font("brand"), padx=16)
        brand.pack(side="left")
        project_label = tk.Label(bar, text=self.project.name, font=theme.font("body"))
        project_label.pack(side="left")
        game = tk.Label(bar, text=self.project.game_info.short_code, font=theme.font("caption"), padx=6)
        game.pack(side="left", padx=(8, 18))
        self._nav: dict[str, _NavItem] = {}
        for key, label in NAV:
            item = _NavItem(bar, label, lambda k=key: self.navigate((k,)))
            item.pack(side="left", fill="y")
            self._nav[key] = item

        right = tk.Frame(bar)
        right.pack(side="right", padx=12)
        settings = ttk.Button(right, text="⚙", width=3, command=self.open_settings)
        settings.pack(side="right", padx=(8, 0))
        search = ttk.Button(right, text="⌕  Search everything…      Ctrl+K", command=self.open_search, width=34)
        search.pack(side="right")

        def paint():
            bg = theme.color("surface_alt")
            for w in (bar, brand, project_label, right):
                w.configure(background=bg)
            brand.configure(foreground=theme.color("accent"))
            project_label.configure(foreground=theme.color("fg"))
            game.configure(background=theme.color("accent_bg"), foreground=theme.color("accent"))
        paint()
        theme.on_change(bar, paint)
        sep = tk.Frame(self, height=1)
        sep.pack(fill="x")
        theme.on_change(sep, lambda: sep.configure(background=theme.color("border")))
        sep.configure(background=theme.color("border"))

    def open_settings(self) -> None:
        SettingsDialog(self)

    # -- crumb bar ---------------------------------------------------------------------------
    def _build_crumb_bar(self) -> None:
        bar = ttk.Frame(self, style="Page.TFrame", padding=(16, 8, 16, 4))
        bar.pack(fill="x")
        self._back_button = ttk.Button(bar, text="‹", width=2, command=self.back)
        self._back_button.pack(side="left")
        self._forward_button = ttk.Button(bar, text="›", width=2, command=self.forward)
        self._forward_button.pack(side="left", padx=(4, 12))
        self._crumbs = ttk.Frame(bar, style="Page.TFrame")
        self._crumbs.pack(side="left", fill="x", expand=True)

    def _render_crumbs(self) -> None:
        for child in self._crumbs.winfo_children():
            child.destroy()
        page = self._current
        crumbs = page.crumbs(self.route) if page is not None and self.route else []
        for i, (label, route) in enumerate(crumbs):
            if i:
                ttk.Label(self._crumbs, text="›", style="Faint.TLabel").pack(side="left", padx=6)
            if route is not None and i < len(crumbs) - 1:
                Link(self._crumbs, label, lambda r=route: self.navigate(r)).pack(side="left")
            else:
                ttk.Label(self._crumbs, text=label, style="Strong.TLabel").pack(side="left")
        self._back_button.configure(state="normal" if self._back else "disabled")
        self._forward_button.configure(state="normal" if self._forward else "disabled")

    # -- status bar ---------------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        self._drawer = ttk.Frame(self, style="Page.TFrame", padding=(16, 6))
        drawer_head = ttk.Frame(self._drawer, style="Page.TFrame")
        drawer_head.pack(fill="x")
        ttk.Label(drawer_head, text="Changes this session", style="Heading.TLabel").pack(side="left")
        ttk.Label(drawer_head, text="Not saved with the project; review before building.",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))
        ttk.Button(drawer_head, text="Hide", command=self.toggle_activity).pack(side="right")
        self._activity = tk.Listbox(self._drawer, height=8, activestyle="none")
        self._activity.pack(fill="both", expand=True, pady=(6, 0))
        self._drawer_open = False

        bar = tk.Frame(self, height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._status_bar = bar
        self._unsaved_label = tk.Label(bar, text="", font=theme.font("caption"), padx=14)
        self._unsaved_label.pack(side="left")
        self._changes_button = tk.Label(bar, text="0 changes this session  ▴", font=theme.font("caption"),
                                        cursor="hand2", padx=8)
        self._changes_button.pack(side="left")
        self._changes_button.bind("<Button-1>", lambda e: self.toggle_activity())
        self._status_text = tk.Label(bar, text="", font=theme.font("caption"), padx=14)
        self._status_text.pack(side="right")
        self._progress = ttk.Progressbar(bar, mode="indeterminate", length=160)

        def paint():
            bg = theme.color("surface_alt")
            bar.configure(background=bg)
            self._unsaved_label.configure(background=bg, foreground=theme.color("warn"))
            self._changes_button.configure(background=bg, foreground=theme.color("accent"))
            self._status_text.configure(background=bg, foreground=theme.color("muted"))
        paint()
        theme.on_change(bar, paint)

    def toggle_activity(self) -> None:
        if self._drawer_open:
            self._drawer.pack_forget()
        else:
            self._drawer.pack(fill="x", side="bottom", before=self._status_bar)
        self._drawer_open = not self._drawer_open

    def _on_change_entry(self, entry) -> None:
        self._activity.insert(0, entry.format())
        count = len(self.changelog.entries)
        self._changes_button.configure(text=f"{count} change{'s' if count != 1 else ''} this session  ▴")
        self.rebuild_index()  # a save may have changed names, units, messages...

    def set_status(self, text: str, busy: bool = False) -> None:
        self.last_status = text
        self._status_text.configure(text=text)
        if busy:
            self._progress.pack(side="right", padx=(0, 8), pady=6)
            self._progress.start(12)
        else:
            self._progress.stop()
            self._progress.pack_forget()

    def flush_pages(self) -> None:
        """Let pages whose fields apply when left apply the one still focused."""
        for page in self._pages.values():
            flush = getattr(page, "flush", None)
            if flush is not None:
                try:
                    flush()
                except tk.TclError:
                    pass

    def unsaved(self, flush: bool = False) -> list[str]:
        """Names of every editor holding unsaved edits (``flush``: apply
        pending field edits first - not while the user may be typing)."""
        if flush:
            self.flush_pages()
        names = []
        for page in self._pages.values():
            for panel in page.panels():
                if panel.dirty and not getattr(panel, "shares_fe8_session", False):
                    names.append(panel.display_name or type(panel).__name__)
        if self._session is not None and self._session.dirty:
            names.append("FE8Data.bin")
        return names

    def _poll_unsaved(self) -> None:
        try:
            names = self.unsaved()
            self._unsaved_label.configure(text=f"●  {len(names)} unsaved: {', '.join(names)}" if names else "")
            self.after(1000, self._poll_unsaved)
        except tk.TclError:
            pass

    # -- navigation -----------------------------------------------------------------------------
    def navigate(self, route: Route, *, record: bool = True) -> bool:
        route = tuple(route)
        if not self.extracted and route[0] not in UNEXTRACTED_KINDS:
            route = ("home",)
        page = self.page(route[0])
        previous = self._current
        if not page.show(route):
            return False
        if page is not previous:
            if previous is not None:
                flush = getattr(previous, "flush", None)
                if flush is not None:
                    flush()
                previous.pack_forget()
            page.pack(fill="both", expand=True)
            self._current = page
        if record and self.route is not None and self.route != route:
            self._back.append(self.route)
            del self._back[:-50]
            self._forward.clear()
        self.route = route
        self._after_route_change()
        return True

    def replace_route(self, route: Route) -> None:
        """The page changed what it shows (a tab) - update the crumbs, no history."""
        self.route = tuple(route)
        self._after_route_change()

    def _after_route_change(self) -> None:
        section = SECTION_OF.get(self.route[0], "")
        for key, item in self._nav.items():
            item.set_active(key == section)
        label = self._current.history_label(self.route) if self._current else None
        if label:
            key = self.route[:2]
            self.visited = [(r, l) for r, l in self.visited if r[:2] != key]
            self.visited.insert(0, (self.route, label))
            del self.visited[12:]
        self._render_crumbs()

    def back(self) -> None:
        if self._back:
            route = self._back.pop()
            current = self.route
            if self.navigate(route, record=False):
                if current is not None:
                    self._forward.append(current)
                self._render_crumbs()
            else:
                self._back.append(route)

    def forward(self) -> None:
        if self._forward:
            route = self._forward.pop()
            current = self.route
            if self.navigate(route, record=False):
                if current is not None:
                    self._back.append(current)
                self._render_crumbs()
            else:
                self._forward.append(route)

    def refresh_extracted_state(self) -> None:
        extracted = self.extracted
        for key, item in self._nav.items():
            item.set_enabled(extracted or key in UNEXTRACTED_KINDS)
        if extracted and self.index is None:
            self.rebuild_index()

    # -- project index ------------------------------------------------------------------------------
    def rebuild_index(self) -> None:
        if not self.extracted:
            return
        if self._index_thread is not None and self._index_thread.is_alive():
            self._index_again = True
            return
        self._index_again = False
        fresh = ProjectIndex(self.project)
        self._index_thread = threading.Thread(target=fresh.build, daemon=True)
        self._index_thread.start()
        if self.index is None:
            self.set_status("Indexing chapters and characters…")
        self.after(100, lambda: self._wait_index(fresh))

    def _wait_index(self, fresh: ProjectIndex) -> None:
        if not fresh.ready:
            self.after(100, lambda: self._wait_index(fresh))
            return
        self.index = fresh
        if self.last_status.startswith("Indexing"):
            self.set_status(f"Index error: {fresh.error}" if fresh.error else "")
        for page in list(self._pages.values()):
            try:
                page.index_changed()
            except tk.TclError:
                pass
        if self._index_again:
            self.rebuild_index()

    # -- search -----------------------------------------------------------------------------------------
    def on_search_key(self, event) -> Optional[str]:
        """Ctrl+K from the window (bound once by the main window)."""
        if isinstance(event.widget, tk.Text):
            return None  # Ctrl+K belongs to the text box there
        self.open_search()
        return "break"

    def open_search(self) -> None:
        if not self.extracted:
            return
        if self._palette is not None and self._palette.winfo_exists():
            self._palette.focus_entry()
            return
        self._palette = SearchPalette(self, self.search_items())

    def search_items(self) -> list[tuple[str, str, str, Route]]:
        """``(kind, label, detail, route)`` for everything the palette finds."""
        items: list[tuple[str, str, str, Route]] = [("Go to", label, "", (key,)) for key, label in NAV]
        for key, label in self._asset_tools:
            items.append(("Tool", label, "Assets", ("asset", key)))
        items += [("Tool", label, "Game Data", ("data", key))
                  for key, label in (("classes", "Classes"), ("items", "Items"), ("skills", "Skills"),
                                     ("terrain", "Terrain"), ("supports", "Supports"),
                                     ("props", "Map Objects"))]
        items += [("Tool", label, "Flags", ("flags", key))
                  for key, label in (("campaign", "Campaign flags"), ("chapter", "Chapter flags"),
                                     ("save", "Save file flags"))]
        index = self.index
        if index is None:
            return items
        for c in index.chapters:
            items.append(("Chapter", c.title, f"disc {c.id}", ("chapter", c.id)))
        for c in index.characters:
            detail = " · ".join(x for x in (c.pid, c.class_name) if x)
            items.append(("Character", c.name or c.pid, detail, ("character", c.pid)))
        for jid, name in index.class_names.items():
            items.append(("Class", name or jid, jid, ("data", "classes", jid)))
        for iid, name in index.item_names.items():
            items.append(("Item", name or iid, iid, ("data", "items", iid)))
        session = self._session
        if session is not None and session.available:
            for skill in session.fe8.skills:
                if skill.sid:
                    items.append(("Skill", skill.sid[4:].replace("_", " ").title(), skill.sid,
                                  ("data", "skills", skill.sid)))
        for chapter_id, messages in index.messages_by_chapter.items():
            title = index.by_chapter[chapter_id].title if chapter_id in index.by_chapter else chapter_id
            for msg_id, text in messages:
                items.append(("Message", msg_id, f"{title} · {plain_text(text)[:80]}",
                              ("chapter", chapter_id, "dialogue", msg_id)))
        return items

    # -- disc tasks ------------------------------------------------------------------------------------------
    def set_source(self) -> None:
        project = self.project
        formats = " ".join(f"*{ext}" for ext in project.game_info.disc_formats)
        chosen = filedialog.askopenfilename(
            title="Choose the source disc image",
            filetypes=[(f"{project.game_info.display_name} disc images", formats), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return
        try:
            project.set_source(chosen)
        except ProjectError as exc:
            messagebox.showerror("Could not set source", str(exc), parent=self)
            return
        self._refresh_home()

    def extract(self) -> None:
        project = self.project
        if not project.source_iso:
            return
        if self.extracted and not messagebox.askyesno(
                "Re-extract the disc?",
                "Extracting again overwrites the extracted files with the disc's own, "
                "so edits made to them are replaced.\n\nContinue?", icon="warning", parent=self):
            return
        self.run_task(f"Extracting {project.source_iso} …", project.extract,
                      lambda _r: self._on_extracted())

    def _on_extracted(self) -> None:
        self.set_status(f"Extracted into {self.project.extracted_dir}")
        self.index = None
        self.refresh_extracted_state()
        self._refresh_home()

    def build(self) -> None:
        if not self.extracted or self._task_running:
            return
        names = self.unsaved(flush=True)
        if names and not messagebox.askyesno(
                "Unsaved changes",
                "These editors have changes that aren't saved and won't be in the disc:\n\n  "
                + "\n  ".join(names) + "\n\nBuild anyway?", parent=self):
            return
        self.run_task("Building disc image …", self.project.build, self._on_built)

    def _on_built(self, dest) -> None:
        self.set_status(f"Built {dest}")
        self._refresh_home()
        if self.project.last_build_warning:
            messagebox.showwarning("Disc image is oversized", self.project.last_build_warning, parent=self)

    def play(self, *, build_first: bool = True) -> None:
        """Build the disc (unless ``build_first`` is off and an image exists) and start it in Dolphin."""
        if not self.extracted or self._task_running:
            return
        project = self.project
        image = project.build_dir / f"{sanitize_folder_name(project.name)}{project.game_info.build_extension}"
        if emulator.configured_dolphin() is None:
            messagebox.showinfo("Dolphin not found", "Set Dolphin's location first (Settings > Preferences).",
                                parent=self)
            return
        if not build_first and image.is_file():
            self._launch(image)
            return
        names = self.unsaved(flush=True)
        if names and not messagebox.askyesno(
                "Unsaved changes",
                "These editors have changes that aren't saved and won't be in the disc:\n\n  "
                + "\n  ".join(names) + "\n\nBuild and play anyway?", parent=self):
            return

        def built(dest) -> None:
            self._on_built(dest)
            self._launch(dest)
        self.run_task("Building disc image …", project.build, built)

    def _launch(self, image) -> None:
        try:
            emulator.launch(image)
        except emulator.EmulatorError as exc:
            messagebox.showerror("Could not start Dolphin", str(exc), parent=self)
            return
        self.set_status(f"Started {image} in Dolphin")

    def create_patch(self) -> None:
        if not self.extracted or self._task_running:
            return
        names = self.unsaved(flush=True)
        if names and not messagebox.askyesno(
                "Unsaved changes",
                "These editors have changes that aren't saved and won't be in the patch:\n\n  "
                + "\n  ".join(names) + "\n\nCreate the patch anyway?", parent=self):
            return
        project = self.project
        dest = filedialog.asksaveasfilename(
            title="Save the patch as", parent=self, defaultextension=patch.PATCH_EXTENSION,
            initialdir=str(project.build_dir),
            initialfile=f"{sanitize_folder_name(project.name)}{patch.PATCH_EXTENSION}",
            filetypes=[("Tellius patches", f"*{patch.PATCH_EXTENSION}")])
        if not dest:
            return
        self.run_task("Creating patch (extracting the source disc to compare) …",
                      lambda: patch.create_project_patch(project, dest), lambda s: self._on_patch_created(dest, s))

    def _on_patch_created(self, dest: str, summary) -> None:
        self.last_patch = f"Last patch: {dest} - {summary.describe()}"
        self.set_status(f"Created {dest}")
        if summary.empty:
            messagebox.showinfo("Empty patch", "The extracted files are identical to the source disc's, "
                                "so the patch changes nothing.", parent=self)
        else:
            messagebox.showinfo("Patch created", f"{dest}\n\n{summary.describe()}", parent=self)

    def apply_patch(self) -> None:
        ApplyPatchDialog(self)

    def run_task(self, status: str, work: Callable, on_success: Callable) -> None:
        self._task_running = True
        self._refresh_home()
        self.set_status(status, busy=True)
        results: "queue.Queue" = queue.Queue()

        def worker():
            try:
                results.put(("ok", work()))
            except ModdingError as exc:
                results.put(("error", str(exc)))
            except OSError as exc:
                results.put(("error", f"Unexpected error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                status_, payload = results.get_nowait()
            except queue.Empty:
                self.after(150, poll)
                return
            self._task_running = False
            self.set_status("")
            if status_ == "ok":
                on_success(payload)
            else:
                messagebox.showerror("Operation failed", payload, parent=self)
            self.refresh_extracted_state()
            self._refresh_home()
        poll()

    @property
    def task_running(self) -> bool:
        return self._task_running

    def _refresh_home(self) -> None:
        """Re-render Home or Disc & Patch if showing: they show the task state."""
        for kind in UNEXTRACTED_KINDS:
            page = self._pages.get(kind)
            if page is not None and self._current is page:
                page.show((kind,))

    def close_project(self) -> None:
        self._on_close_project()

    # -- teardown --------------------------------------------------------------------------------------------
    def cleanup(self) -> None:
        self.portraits.close()
        for page in self._pages.values():
            page.cleanup()


def plain_text(text: str) -> str:
    """Message text without its ``$`` commands, on one line."""
    import re
    text = re.sub(r"\$(?:FCL_|FC|R|B|c[0-9])[^|$]*\|", "", text)
    text = re.sub(r"\$(?:MC|MD|UB|Ub|SD|SE|F[0-9cdhoASD]|w[0-9]|s[0-9]|d[0-9]|O[0-9]|=[0-9]{4}|[KPHNGY<])", "", text)
    return " ".join(text.split())


class _NavItem(tk.Frame):
    """A top-bar section: label with an accent underline when active."""

    def __init__(self, parent: tk.Misc, text: str, command: Callable[[], None]):
        super().__init__(parent)
        self._command = command
        self._active = False
        self._enabled = True
        self._hover = False
        self._label = tk.Label(self, text=text, font=theme.font("body"), padx=14, cursor="hand2")
        self._label.pack(fill="both", expand=True)
        self._bar = tk.Frame(self, height=3)
        self._bar.pack(fill="x", side="bottom")
        for w in (self, self._label, self._bar):
            w.bind("<Button-1>", lambda e: self._enabled and self._command())
        track_hover(self, self._set_hover)
        self._paint()
        theme.on_change(self, self._paint)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._paint()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._label.configure(cursor="hand2" if enabled else "")
        self._paint()

    def _set_hover(self, hover: bool) -> None:
        if hover != self._hover:
            self._hover = hover
            self._paint()

    def _paint(self) -> None:
        # colours only: the font stays the same so the bar never changes width
        bg = theme.color("nav_active" if self._hover and self._enabled else "surface_alt")
        self.configure(background=bg)
        self._label.configure(
            background=bg,
            foreground=theme.color("faint") if not self._enabled else theme.color("fg" if self._active else "muted"),
        )
        self._bar.configure(background=theme.color("accent") if self._active else bg)


class SearchPalette(tk.Toplevel):
    """Ctrl+K: type to find a chapter, character, class, item, message or
    tool; Enter (or a click) goes there, Escape closes."""

    LIMIT = 60

    def __init__(self, shell: Shell, items: list[tuple[str, str, str, Route]]):
        super().__init__(shell)
        self._shell = shell
        self._items = items
        self._haystack = [f"{label} {detail} {kind}".casefold() for kind, label, detail, _r in items]
        self._shown: list[int] = []
        self.overrideredirect(True)
        self.transient(shell.winfo_toplevel())
        border = tk.Frame(self, padx=1, pady=1)
        border.pack(fill="both", expand=True)
        body = ttk.Frame(border, padding=10)
        body.pack(fill="both", expand=True)
        self._query = tk.StringVar()
        entry = ttk.Entry(body, textvariable=self._query, font=theme.font("heading"))
        entry.pack(fill="x")
        self._entry = entry
        ttk.Label(body, text="Chapters, characters, classes, items, messages, tools  ·  ↑↓ Enter  ·  Esc",
                  style="Caption.TLabel").pack(anchor="w", pady=(6, 4))
        self._list = tk.Listbox(body, height=14, activestyle="none", font=theme.font("body"),
                                highlightthickness=0, borderwidth=0)
        self._list.pack(fill="both", expand=True)
        border.configure(background=theme.color("accent"))
        self._list.configure(background=theme.color("surface"), foreground=theme.color("fg"),
                             selectbackground=theme.color("accent_bg"), selectforeground=theme.color("fg"))

        self._query.trace_add("write", lambda *_: self._filter())
        entry.bind("<Down>", lambda e: self._move(1))
        entry.bind("<Up>", lambda e: self._move(-1))
        entry.bind("<Return>", lambda e: self._go())
        entry.bind("<Escape>", lambda e: self.destroy())
        self._list.bind("<ButtonRelease-1>", lambda e: self._go())
        self._list.bind("<Escape>", lambda e: self.destroy())
        self.bind("<FocusOut>", self._on_focus_out)

        top = shell.winfo_toplevel()
        width = min(640, max(420, top.winfo_width() - 80))
        x = top.winfo_rootx() + (top.winfo_width() - width) // 2
        y = top.winfo_rooty() + 56
        self.geometry(f"{width}x420+{x}+{y}")
        self._filter()
        self.after(10, self.focus_entry)

    def focus_entry(self) -> None:
        self.lift()
        self._entry.focus_force()

    def _on_focus_out(self, _event) -> None:
        self.after(50, self._close_if_unfocused)

    def _close_if_unfocused(self) -> None:
        try:
            focus = self.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        if focus is None or focus.winfo_toplevel() is not self:
            self.destroy()

    def _filter(self) -> None:
        words = self._query.get().casefold().split()
        shown = []
        for i, hay in enumerate(self._haystack):
            if all(w in hay for w in words):
                shown.append(i)
                if len(shown) >= self.LIMIT:
                    break
        self._shown = shown
        self._list.delete(0, "end")
        for i in shown:
            kind, label, detail, _route = self._items[i]
            self._list.insert("end", f"  {kind:<10} {label}" + (f"   —   {detail}" if detail else ""))
        if shown:
            self._list.selection_set(0)

    def _move(self, step: int) -> str:
        if not self._shown:
            return "break"
        current = self._list.curselection()
        index = min(max(0, (current[0] if current else -1) + step), len(self._shown) - 1)
        self._list.selection_clear(0, "end")
        self._list.selection_set(index)
        self._list.see(index)
        return "break"

    def _go(self) -> None:
        current = self._list.curselection()
        if not current or current[0] >= len(self._shown):
            return
        route = self._items[self._shown[current[0]]][3]
        self.destroy()
        self._shell.navigate(route)
