"""Characters: a portrait card per character, and a page per character with
everything about them - the editable FE8Data/FE10Data record, their supports
(affinity, partners, bonds), portrait and models, every chapter and message
they appear in, and the script functions that name them.

Story copies of a character (``PID_BOLE_MAP1`` for the Prologue's Boyd,
``PID_IKE_EV2``...) share the name key (``MPID_``) of the main record; the
hub shows the main one and the page lists the copies, whose appearances are
included. Game-specific codecs feed the same routes and page layout.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from ...formats import fe10data, fe10_message
from ...game_profile import CHAPTERS, DATA_TABLES, GAME_DATA
from ...project_index import CATEGORY_LABELS, GENERIC, NAMED, PLAYABLE, difficulty_name, supported
from ... import excel_io
from .. import record_actions
from ..character_form import CharacterForm
from ..fe10_character_form import Fe10CharacterForm, Fe10CharacterSupportsPanel
from ..shell import Page, plain_text
from ..support_editor import CharacterSupportsPanel, read_conversation_ids
from ..widgets import Card, CardGrid, Chip, Link, ScrollFrame, section_header, tip
from ..widgets import info as help_mark

CATEGORY_CHIPS = {PLAYABLE: "chip_playable", NAMED: "chip_named", GENERIC: "chip_generic"}
TABS = ["stats", "supports", "look", "appearances", "scripts"]
TAB_LABELS = {"stats": "Stats", "supports": "Supports", "look": "Portrait & models", "appearances": "Appearances",
              "scripts": "Script references"}


def _matches_filter(character, category: str, words: list[str]) -> bool:
    """Whether a character belongs to both the selected category and search."""
    if category != "all" and character.category != category:
        return False
    hay = (f"{character.name} {character.pid} {' '.join(character.variants)} "
           f"{character.class_name}").casefold()
    return all(word in hay for word in words)


def _card_subtitle(character) -> str:
    """A character tile describes the record as it is, without its promotion path."""
    return character.class_name or character.jid or ""


class CharactersHub(Page):
    kind = "characters"

    def __init__(self, shell):
        super().__init__(shell)
        top = ttk.Frame(self, style="Page.TFrame", padding=(28, 12, 28, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Characters", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="New character…", command=self._new_character).pack(side="left", padx=(16, 0))
        self._export_button = ttk.Button(top, text="Export Excel…", command=self._export_excel)
        self._export_button.pack(side="left", padx=(8, 0))
        self._import_button = ttk.Button(top, text="Import Excel…", command=self._import_excel)
        self._import_button.pack(side="left", padx=(6, 0))
        self._query = tk.StringVar()
        ttk.Entry(top, textvariable=self._query, width=30).pack(side="right")
        ttk.Label(top, text="Search name, PID, or class", style="Muted.TLabel").pack(side="right", padx=(0, 8))
        self._query.trace_add("write", lambda *_: self._filter_changed())
        chips = ttk.Frame(self, style="Page.TFrame", padding=(28, 0, 28, 8))
        chips.pack(fill="x")
        rd = self.project.profile.supports(DATA_TABLES) and not self.project.profile.supports(GAME_DATA)
        self._category = tk.StringVar(value=PLAYABLE)
        self._category_buttons = {}
        for value, label in ((PLAYABLE, "Playable"), (NAMED, "Named NPCs & bosses"), (GENERIC, "Generic"),
                             ("all", "All")):
            button = ttk.Radiobutton(chips, text=label, value=value, variable=self._category,
                                     style="Toggle.TButton", command=self._filter_changed)
            button.pack(side="left", padx=(0, 6))
            self._category_buttons[value] = button
        if rd:
            self._export_button.configure(state="disabled")
            self._import_button.configure(state="disabled")
            reason = "Radiant Dawn character spreadsheets are not decoded yet; edit records in this shared page."
            tip(self._export_button, reason)
            tip(self._import_button, reason)
        self._count = ttk.Label(chips, text="", style="Muted.TLabel")
        self._count.pack(side="left", padx=(12, 0))
        self._scroll = ScrollFrame(self, padding=(28, 4, 28, 28))
        self._scroll.pack(fill="both", expand=True)
        self._grid = CardGrid(self._scroll.body, card_width=250, gap=10)
        self._grid.pack(fill="x")
        self._built_for = None

    def crumbs(self, route):
        return [("Characters", None)]

    def shown_characters(self) -> list:
        """The main records the list shows with its current category and search, in order (the
        character page's ‹ › buttons follow it)."""
        index = self.shell.index
        if index is None:
            return []
        category, words = self._category.get(), self._query.get().casefold().split()
        return [c for c in index.main_characters() if _matches_filter(c, category, words)]

    def _export_excel(self) -> None:
        session = self.shell.session
        if not session.available:
            return
        path = filedialog.asksaveasfilename(parent=self, title="Export characters", defaultextension=".xlsx", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            excel_io.export_fe8(path, session.data, only="Characters")
        except Exception as exc:
            messagebox.showerror("Could not export Excel", str(exc), parent=self)

    def _import_excel(self) -> None:
        session = self.shell.session
        if not session.available:
            return
        path = filedialog.askopenfilename(parent=self, title="Import characters", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            data, _docs, errors = excel_io.import_fe8(path, session.data, only="Characters")
            if errors:
                messagebox.showerror("Excel import has errors", "\n".join(errors[:30]), parent=self)
                return
            session.data = data
            session.changed(self)
            self._built_for = None
            self._build()
        except Exception as exc:
            messagebox.showerror("Could not import Excel", str(exc), parent=self)
    def _new_character(self) -> None:
        session = self.shell.session
        if getattr(session, "fe10", None) is not None:
            characters = session.fe10.characters
            template = simpledialog.askstring(
                "New character", "PID of the character to copy:",
                initialvalue=characters[0].id if characters else "", parent=self)
            source = next((r.index for r in characters if r.id == template), None)
            if source is None:
                if template:
                    messagebox.showerror("New character", f"{template} was not found.", parent=self)
                return
            new_id = simpledialog.askstring("New character", "ID for the copy:",
                                            initialvalue="PID_", parent=self)
            if not new_id or new_id == "PID_":
                return
            if any(r.id == new_id for r in characters):
                messagebox.showerror("New character", f"{new_id} is already used.", parent=self)
                return
            data, _index = fe10data.add_record(session.data, "character", source, new_id)
            session.replace(data, self)
            self.shell.navigate(("character", new_id))
            return
        if session.fe8 is None:
            return
        labels = [f"{c.pid or '?'}  #{c.index}" for c in session.fe8.characters]
        index = record_actions.add_record(self, session, "character", labels)
        if index is not None:
            self.shell.navigate(("character", session.fe8.characters[index].pid))

    def show(self, route) -> bool:
        if self._built_for is not self.shell.index:
            self._build()
        return True

    def index_changed(self) -> None:
        if self.winfo_ismapped():
            self._build()

    def _build(self) -> None:
        index = self.shell.index
        self._built_for = index
        self._grid.clear()
        if index is None:
            self._grid.add(None, ttk.Label(self._grid, text="Indexing…", style="Muted.TLabel"))
            self._grid.done()
            return
        if not supported(self.project):
            self._grid.add(None, ttk.Label(self._grid, style="Muted.TLabel",
                                           text=self.project.profile.unavailable(GAME_DATA)))
            self._grid.done()
            return
        for c in index.main_characters():
            subtitle = _card_subtitle(c)
            caption = c.pid + (f"  ·  +{len(c.variants)} cop{'ies' if len(c.variants) > 1 else 'y'}" if c.variants else "")
            card = Card(self._grid, title=c.name or c.pid, subtitle=subtitle, caption=caption, width=250,
                        image_box=(6, 3), on_click=lambda pid=c.pid: self.shell.navigate(("character", pid)))
            self._grid.add(c, card)
        self._grid.done()
        self._filter()

    def _filter_changed(self) -> None:
        self._filter()
        self._scroll.scroll_top()  # a new selection starts at the top

    def _filter(self) -> None:
        index = self.shell.index
        if index is None or not supported(self.project):
            return
        category = self._category.get()
        words = self._query.get().casefold().split()

        def keep(c) -> bool:
            if c is None:
                return True
            # Search narrows the selected category; it must not silently turn
            # the category buttons into "All" on the first typed character.
            return _matches_filter(c, category, words)

        shown = self._grid.filter(keep)
        self._count.configure(text=f"{shown} shown")
        for c, card in self._grid._cards:
            if c is not None and card in self._grid._visible:
                self.shell.portraits.request(c.fid, 56, lambda photo, w=card: w.winfo_exists() and w.set_image(photo))


class CharacterPage(Page):
    """Route ``("character", pid[, tab])``."""

    kind = "character"

    def __init__(self, shell):
        super().__init__(shell)
        self._pid: str | None = None
        self._tab = "stats"
        header = ttk.Frame(self, style="Page.TFrame", padding=(28, 6, 28, 10))
        header.pack(fill="x")
        self._portrait = tk.Label(header, borderwidth=0)
        self._portrait.pack(side="left", padx=(0, 16))
        text = ttk.Frame(header, style="Page.TFrame")
        text.pack(side="left", fill="x", expand=True)
        self._title = ttk.Label(text, text="", style="Title.TLabel")
        self._title.pack(anchor="w")
        self._subtitle = ttk.Frame(text, style="Page.TFrame")
        self._subtitle.pack(anchor="w", pady=(2, 0))
        self._chips = ttk.Frame(text, style="Page.TFrame")
        self._chips.pack(anchor="w", pady=(6, 0))
        # ‹ › step through the Characters list as it is filtered there; the picker finds any character
        steps = ttk.Frame(header, style="Page.TFrame")
        steps.pack(side="right", anchor="n")
        self._next_button = ttk.Button(steps, text="Next ›", command=lambda: self._step(1))
        self._next_button.pack(side="right")
        self._prev_button = ttk.Button(steps, text="‹ Previous", command=lambda: self._step(-1))
        self._prev_button.pack(side="right", padx=(0, 6))
        self._picker_var = tk.StringVar()
        self._picker = ttk.Combobox(steps, textvariable=self._picker_var, width=28)
        self._picker.pack(side="right", padx=(0, 12))
        tip(self._picker, "Type a name, PID or class, then pick a character (Enter opens the first match)")
        self._picker.bind("<KeyRelease>", self._picker_typed)
        self._picker.bind("<Return>", lambda e: self._picker_go())
        self._picker.bind("<<ComboboxSelected>>", lambda e: self._picker_go())
        self._position = ttk.Label(steps, text="", style="Muted.TLabel")
        self._position.pack(side="right", padx=(0, 10))
        self._picker_choices: dict[str, str] = {}

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        stats = ScrollFrame(self._notebook, padding=(16, 12))
        if getattr(shell.session, "fe10", None) is not None:
            self._form = Fe10CharacterForm(
                stats.body, shell.session,
                on_open_class=lambda jid: shell.navigate(("data", "classes", jid)),
                on_open_character=self._open_character)
        else:
            self._form = CharacterForm(stats.body, shell.session,
                                       on_open_class=lambda jid: shell.navigate(("data", "classes", jid)),
                                       on_open_character=self._open_character, project=shell.project,
                                       navigate=shell.navigate)
        self._form.pack(fill="both", expand=True)
        support_scroll = ScrollFrame(self._notebook, padding=(16, 12))
        self._build_supports(support_scroll.body)
        self._look = ScrollFrame(self._notebook, padding=(16, 12))
        self._appearances = ttk.Frame(self._notebook, style="Page.TFrame", padding=(16, 12))
        self._scripts = ttk.Frame(self._notebook, style="Page.TFrame", padding=(16, 12))
        for key, widget in zip(TABS, (stats, support_scroll, self._look, self._appearances, self._scripts)):
            self._notebook.add(widget, text=TAB_LABELS[key])
        self._notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed())
        self._scripts_for = None
        self._theme_bg()

    def _build_supports(self, body) -> None:
        session = self.shell.session
        self._supports = None
        if not session.available:
            ttk.Label(body, text=session.unavailable_reason, style="Muted.TLabel").pack(
                anchor="w")
            return
        bar = ttk.Frame(body, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 10))
        self._support_save = ttk.Button(bar, text=f"Save {session.file_label}", command=self._save_fe8)
        self._support_save.pack(side="left")
        self._support_status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._support_status.pack(side="left", padx=(12, 0))
        if getattr(session, "fe10", None) is not None:
            self._supports = Fe10CharacterSupportsPanel(
                body, session, self._name_of,
                lambda pid: self.shell.navigate(("character", pid, "supports")))
        else:
            self._supports = CharacterSupportsPanel(
                body,
                get_data=lambda: session.data,
                set_data=lambda b: setattr(session, "data", b),
                on_dirty=lambda: session.changed(self._supports),
                display_name=self._name_of,
                conversation_ids=self._support_conversation_ids,
                open_conversation=lambda pid, partner, rank: self.shell.page("data").open_support_conversation(
                    pid, partner, rank),
                open_character=lambda pid: self.shell.navigate(("character", pid, "supports")),
            )
        self._supports.pack(fill="both", expand=True)
        session.subscribe(self._on_session_changed)
        self._refresh_support_status()

    def _support_conversation_ids(self):
        data_page = self.shell.existing_page("data")
        if data_page is not None:
            return data_page.support_conversation_ids()
        return read_conversation_ids(self.project.extracted_dir / "files" / "Mess" / "yell.m")

    def _on_session_changed(self, source) -> None:
        try:
            if self._supports is not None and source is not self._supports and self.winfo_exists():
                self._supports.reload()
            self._refresh_support_status()
        except tk.TclError:
            pass

    def _refresh_support_status(self) -> None:
        dirty = self.shell.session.dirty
        self._support_save.configure(state="normal" if dirty else "disabled")
        self._support_status.configure(text=f"Unsaved changes in {self.shell.session.file_label}" if dirty else "",
                                       style="Warn.TLabel" if dirty else "Muted.TLabel")

    def _save_fe8(self) -> None:
        self.flush()
        try:
            self.shell.session.save()
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)

    def flush(self) -> None:
        if self._supports is not None:
            self._supports.flush()

    def _open_character(self, pid) -> None:
        """After a character was added (its PID) or removed (None)."""
        if pid is None:
            self._pid = None
            self.shell.navigate(("characters",))
        else:
            self.shell.navigate(("character", pid))

    def _theme_bg(self) -> None:
        from .. import theme
        self._portrait.configure(background=theme.color("bg"))
        theme.on_change(self._portrait, lambda: self._portrait.configure(background=theme.color("bg")))

    # -- Page --------------------------------------------------------------------------------
    def crumbs(self, route):
        crumbs = [("Characters", ("characters",)), (self._name_of(route[1]), ("character", route[1]))]
        tab = route[2] if len(route) > 2 and route[2] in TABS else "stats"
        if tab != "stats":
            crumbs.append((TAB_LABELS[tab], None))
        return crumbs

    def history_label(self, route):
        return self._name_of(route[1])

    def _name_of(self, pid: str) -> str:
        index = self.shell.index
        info = index.by_pid.get(pid) if index is not None else None
        return info.name if info is not None and info.name else pid

    def index_changed(self) -> None:
        if self._pid is not None:
            self._render(self._pid)

    def show(self, route) -> bool:
        pid = route[1] if len(route) > 1 else None
        if not pid:
            return False
        if pid != self._pid:
            self._pid = pid
            self._scripts_for = None
            self._render(pid)
        else:
            self._update_steps()  # the list's filter may have changed since
        tab = route[2] if len(route) > 2 and route[2] in TABS else None
        if tab is not None:
            self._notebook.select(TABS.index(tab))
        return True

    # -- previous / next ----------------------------------------------------------------------
    def _order(self) -> list:
        hub = self.shell.existing_page("characters")
        if hub is not None:
            return hub.shown_characters()
        index = self.shell.index
        return index.main_characters() if index is not None else []

    def _main_pid(self) -> str | None:
        index = self.shell.index
        info = index.by_pid.get(self._pid) if index is not None and self._pid else None
        return info.main_pid if info is not None else self._pid

    def _update_steps(self) -> None:
        order = [c.pid for c in self._order()]
        main = self._main_pid()
        position = order.index(main) if main in order else None
        self._prev_button.configure(state="normal" if position else "disabled")
        self._next_button.configure(
            state="normal" if position is not None and position + 1 < len(order) else "disabled")
        self._position.configure(text=f"{position + 1} of {len(order)}" if position is not None else
                                 f"not in the list ({len(order)})" if order else "")
        self._fill_picker("")

    def _step(self, step: int) -> None:
        order = [c.pid for c in self._order()]
        main = self._main_pid()
        if main not in order:
            return
        target = order.index(main) + step
        if 0 <= target < len(order):
            self.shell.navigate(("character", order[target], self._tab))

    def _fill_picker(self, text: str) -> None:
        index = self.shell.index
        words = text.casefold().split()
        characters = [c for c in (index.main_characters() if index is not None else [])
                      if _matches_filter(c, "all", words)]
        self._picker_choices = {f"{c.name or c.pid}  ({c.pid})": c.pid for c in characters}
        self._picker.configure(values=list(self._picker_choices))

    def _picker_typed(self, event) -> None:
        if event.keysym in ("Return", "Up", "Down", "Escape"):
            return
        self._fill_picker(self._picker_var.get())

    def _picker_go(self) -> None:
        text = self._picker_var.get()
        pid = self._picker_choices.get(text)
        if pid is None:
            self._fill_picker(text)
            pid = next(iter(self._picker_choices.values()), None)
        if pid is not None:
            self._picker_var.set("")
            self.shell.navigate(("character", pid, self._tab))

    def _on_tab_changed(self) -> None:
        self.flush()
        self._tab = TABS[self._notebook.index("current")]
        if self._tab == "supports" and self._supports is not None:
            self._supports.reload()  # conversations may have been added in Game Data
        if self._tab == "scripts":
            self._render_scripts()
        route = self.shell.route
        if route and route[0] == self.kind and self._pid is not None and route[2:3] != (self._tab,):
            self.shell.replace_route(("character", self._pid, self._tab))

    # -- rendering --------------------------------------------------------------------------------
    def _render(self, pid: str) -> None:
        index = self.shell.index
        info = index.by_pid.get(pid) if index is not None else None
        self._update_steps()
        self._title.configure(text=info.name if info and info.name else pid)
        for child in list(self._subtitle.winfo_children()) + list(self._chips.winfo_children()):
            child.destroy()
        self._portrait.configure(image="", width=0)
        self._form.show(self.shell.session.character_index(pid))
        if self._supports is not None:
            self._supports.show(pid if self.shell.session.character_index(pid) is not None else None)
        if info is None:
            unsaved = self.shell.session.character_index(pid) is not None
            ttk.Label(self._subtitle, style="Muted.TLabel",
                      text="Indexing…" if index is None else
                      f"New: save {self.shell.session.file_label} to list it with the others" if unsaved else
                      f"Not in {self.shell.session.file_label}'s character table.").pack(side="left")
            for frame in (self._look.body, self._appearances, self._scripts):
                for child in frame.winfo_children():
                    child.destroy()
            return
        ttk.Label(self._subtitle, text=info.pid, style="Muted.TLabel").pack(side="left")
        if info.jid:
            ttk.Label(self._subtitle, text="  ·  ", style="Faint.TLabel").pack(side="left")
            Link(self._subtitle, info.class_name or info.jid,
                 lambda: self.shell.navigate(("data", "classes", info.jid))).pack(side="left")
        if info.promoted_jid:
            ttk.Label(self._subtitle, text="  →  ", style="Faint.TLabel").pack(side="left")
            Link(self._subtitle, info.promoted_class_name or info.promoted_jid,
                 lambda: self.shell.navigate(("data", "classes", info.promoted_jid))).pack(side="left")
        Chip(self._chips, CATEGORY_LABELS[info.category], CATEGORY_CHIPS[info.category]).pack(side="left")
        family = index.family(pid)
        if len(family) > 1:
            ttk.Label(self._chips, text="Records:", style="Muted.TLabel").pack(side="left", padx=(14, 6))
            for member in family:
                if member.pid == pid:
                    ttk.Label(self._chips, text=member.pid, style="Strong.TLabel").pack(side="left", padx=(0, 8))
                else:
                    Link(self._chips, member.pid, lambda p=member.pid: self.shell.navigate(("character", p, self._tab)),
                         font_role="caption").pack(side="left", padx=(0, 8))
        self.shell.portraits.request(info.fid, 88, self._set_portrait)
        self._render_look(info)
        self._render_appearances(index, family)
        if self._tab == "scripts":
            self._render_scripts()

    def _set_portrait(self, photo) -> None:
        if self.winfo_exists():
            self._portrait.configure(image=photo)
            self._portrait.image = photo

    def _render_look(self, info) -> None:
        body = self._look.body
        rd = self.project.profile.supports(DATA_TABLES) and not self.project.profile.supports(GAME_DATA)
        for child in body.winfo_children():
            child.destroy()
        section_header(body, "Portrait").pack(anchor="w", pady=(0, 8))
        box = ttk.Frame(body, style="Surface.TFrame", padding=14)
        box.pack(fill="x")
        image = tk.Label(box, borderwidth=0)
        image.pack(side="left", padx=(0, 16))
        from .. import theme
        image.configure(background=theme.color("surface"))
        self.shell.portraits.request(info.fid, 128, lambda photo: image.winfo_exists() and (
            image.configure(image=photo), setattr(image, "image", photo)))
        text = ttk.Frame(box, style="Surface.TFrame")
        text.pack(side="left", fill="both", expand=True)
        ttk.Label(text, text=info.fid or "No portrait", style="SurfaceHeading.TLabel").pack(anchor="w")
        ttk.Label(text, text=f"File: Face/{info.portrait_file}" if info.portrait_file else "No face file found.",
                  style="SurfaceMuted.TLabel").pack(anchor="w", pady=(2, 10))
        if info.portrait_file:
            stem = info.portrait_file.rsplit(".", 1)[0]
            ttk.Button(text, text="Open in Portraits", command=lambda: self.shell.navigate(
                ("asset", "portraits", stem))).pack(anchor="w")
        ttk.Label(text, text=("Replacing the normal portrait also updates its Face/wide twin by default."
                              if rd else
                              "Replacing the face file changes it for every character that uses this portrait."),
                  style="SurfaceCaption.TLabel", wraplength=520).pack(anchor="w", pady=(10, 0))

        section_header(body, "Models", "what the game loads for this character").pack(anchor="w", pady=(24, 8))
        models = ttk.Frame(body, style="Surface.TFrame", padding=14)
        models.pack(fill="x")
        if rd:
            ttk.Label(models, text="Radiant Dawn model resolution is not decoded yet. This tab will use the same "
                                   "model links and tools once Phase 6 lands.", style="SurfaceMuted.TLabel",
                      wraplength=720, justify="left").pack(anchor="w")
            return
        rows = [
            ("Battle model", info.class_name or info.jid, info.battle_model),
            ("Battle model, promoted", info.promoted_class_name or info.promoted_jid, info.promoted_battle_model),
            ("Map model", info.aid_unpromoted or "class AID", info.map_model),
            ("Map model, promoted", info.aid_promoted or "class AID", info.promoted_map_model),
        ]
        for r, (label, via, model) in enumerate(rows):
            if via is None and model is None:
                continue
            ttk.Label(models, text=label, style="Surface.TLabel", width=24).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Label(models, text=model or "—", style="SurfaceHeading.TLabel", width=14).grid(row=r, column=1, sticky="w")
            ttk.Label(models, text=f"via {via}" if via else "", style="SurfaceMuted.TLabel").grid(
                row=r, column=2, sticky="w", padx=(0, 16))
            if model:
                ttk.Button(models, text="Open in 3D Models", command=lambda m=model: self.shell.navigate(
                    ("asset", "models", m))).grid(row=r, column=3, sticky="w")
        help_mark(models, "Models are shared by every unit that resolves to them. To give this character a model "
                          "of their own, open the model and use New slot…; Model tables… shows the lines that "
                          "pick it.", bg_token="surface").grid(row=len(rows), column=0, sticky="w", pady=(10, 0))
        actions = ttk.Frame(body, style="Page.TFrame")
        actions.pack(anchor="w", pady=(16, 0))
        ttk.Button(actions, text="Simulate a battle…", command=lambda: self.shell.navigate(
            ("asset", "battle_sim", info.pid))).pack(side="left")
        ttk.Button(actions, text="Colour variant…", command=lambda: self._colour_variant(info.pid)).pack(
            side="left", padx=(8, 0))
        help_mark(actions, "A recoloured copy of this character's battle texture, map texture and portrait "
                           "(a red Gatrie), used only by this character and the records you tick.").pack(
            side="left", padx=(6, 0))

    def _colour_variant(self, pid: str) -> None:
        from ..colour_variant_dialog import open_colour_variant
        open_colour_variant(self, self.project, self.shell.session, self.shell.changelog, pid=pid,
                            on_done=lambda: self._render(pid))

    def _render_appearances(self, index, family) -> None:
        frame = self._appearances
        for child in frame.winfo_children():
            child.destroy()
        pids = [m.pid for m in family]
        deployments = sorted(index.deployments_of(pids),
                             key=lambda d: (index.profile.chapter_sort_key(d.chapter_id) if d.chapter_id else (10 ** 9,),
                                            d.folder, "nhmc".find(d.difficulty)))
        messages = index.messages_of(pids)
        paned = ttk.PanedWindow(frame, orient="vertical")
        paned.pack(fill="both", expand=True)

        top = ttk.Frame(paned, style="Page.TFrame")
        paned.add(top, weight=1)
        section_header(top, "Deployed in", f"{len(deployments)} unit records · double-click to open").pack(
            anchor="w", pady=(0, 6))
        tree = self._tree(top, (("chapter", "Chapter", 220), ("map", "Map", 90), ("difficulty", "File", 110),
                                ("section", "Section", 200), ("pid", "Record", 150), ("class", "Class", 120),
                                ("tile", "Tile", 70)))
        self._deployment_rows = {}
        for i, d in enumerate(deployments):
            title = index.by_chapter[d.chapter_id].title if d.chapter_id in index.by_chapter else d.folder
            tree.insert("", "end", iid=str(i), values=(
                title, d.folder, difficulty_name(d.difficulty), d.section, d.pid,
                index.class_names.get(d.jid) or d.jid, f"{d.x}, {d.y}"))
            self._deployment_rows[str(i)] = d
        tree.bind("<Double-Button-1>", lambda e: self._open_deployment(tree))
        tree.bind("<Return>", lambda e: self._open_deployment(tree))

        bottom = ttk.Frame(paned, style="Page.TFrame")
        paned.add(bottom, weight=1)
        section_header(bottom, "Dialogue", f"{len(messages)} messages show their portrait or name them as speaker").pack(
            anchor="w", pady=(10, 6))
        mtree = self._tree(bottom, (("chapter", "Chapter", 220), ("message", "Message", 170), ("how", "As", 80),
                                    ("text", "Text", 520)))
        self._message_rows = {}
        texts = {c: dict(m) for c, m in index.messages_by_chapter.items()}
        for i, ref in enumerate(messages):
            title = index.by_chapter[ref.chapter_id].title if ref.chapter_id in index.by_chapter else ref.chapter_id
            raw = texts.get(ref.chapter_id, {}).get(ref.message_id, "")
            text = (fe10_message.plain_text(raw) if self.project.profile.message_dialect == "fe10"
                    else plain_text(raw))[:140]
            mtree.insert("", "end", iid=str(i), values=(title, ref.message_id, ref.how, text))
            self._message_rows[str(i)] = ref
        mtree.bind("<Double-Button-1>", lambda e: self._open_message(mtree))
        mtree.bind("<Return>", lambda e: self._open_message(mtree))
        if not deployments and not messages:
            text = ("Radiant Dawn appearances will populate here when its deployment codec joins the shared "
                    "chapter index." if self.project.profile.supports(DATA_TABLES) and
                    not self.project.profile.supports(CHAPTERS) else
                    "Not found in any deployment file or chapter message.")
            ttk.Label(top, text=text, style="Muted.TLabel", wraplength=760, justify="left").pack(anchor="w")

    def _render_scripts(self) -> None:
        if self._scripts_for == self._pid or self.shell.index is None:
            return
        self._scripts_for = self._pid
        frame = self._scripts
        for child in frame.winfo_children():
            child.destroy()
        index = self.shell.index
        pids = [m.pid for m in index.family(self._pid)] or [self._pid]
        refs = index.script_refs_of(pids)
        section_header(frame, "Script functions naming this character",
                       f"{len(refs)} · double-click to open").pack(anchor="w", pady=(0, 6))
        tree = self._tree(frame, (("chapter", "Chapter", 240), ("function", "Function", 220), ("label", "Uses", 220)))
        rows = {}
        for i, ref in enumerate(refs):
            title = index.by_chapter[ref.chapter_id].title if ref.chapter_id in index.by_chapter else ref.chapter_id
            tree.insert("", "end", iid=str(i), values=(title, ref.function, ref.label))
            rows[str(i)] = ref

        def open_selected(_event=None):
            selection = tree.selection()
            if selection:
                ref = rows[selection[0]]
                if self.project.profile.supports(CHAPTERS):
                    self.shell.navigate(("chapter", ref.chapter_id, "script", ref.function))
                else:
                    from .chapters import open_script
                    path = self.project.profile.script_path(self.project.extracted_dir / "files", ref.chapter_id)
                    open_script(self.shell, path, ref.function, ref.chapter_id)
        tree.bind("<Double-Button-1>", open_selected)
        tree.bind("<Return>", open_selected)
        ttk.Label(frame, style="Muted.TLabel", wraplength=900, justify="left",
                  text="Found from the PID_ and MPID_ strings each function pushes (unit moves, talks, joins, "
                       "deaths...). Functions are named as the Script tab names them.").pack(anchor="w", pady=(8, 0))

    def _tree(self, parent, columns) -> ttk.Treeview:
        holder = ttk.Frame(parent, style="Page.TFrame")
        holder.pack(fill="both", expand=True)
        tree = ttk.Treeview(holder, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key in ("text", "section", "label", "chapter"))
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _open_deployment(self, tree) -> None:
        selection = tree.selection()
        if not selection:
            return
        d = self._deployment_rows[selection[0]]
        if d.chapter_id is None:
            return  # debug/"always" folders aren't chapters
        self.shell.navigate(("chapter", d.chapter_id, "build", d.folder, d.difficulty, d.section, d.unit_index))

    def _open_message(self, tree) -> None:
        selection = tree.selection()
        if selection:
            ref = self._message_rows[selection[0]]
            if self.project.profile.supports(CHAPTERS):
                self.shell.navigate(("chapter", ref.chapter_id, "dialogue", ref.message_id))
                return
            path = self.project.profile.mess_path(self.project.extracted_dir / "files", ref.chapter_id)
            if self.shell.navigate(("asset", "conversations", path.name)):
                panel = self.shell.page("asset")._panels["conversations"]
                if panel._editor is not None:
                    panel._editor.after_idle(lambda: panel._editor.select_message(ref.message_id))
