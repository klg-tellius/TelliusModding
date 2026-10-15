"""Game Data for Radiant Dawn: the tables of ``FE10Data.cms`` (characters, classes, items, skills,
chapters, terrain, supports, army groups, bonds, affinities, the weapon triangle, difficulty constants,
battle scenery, biorhythm) and the per-level stats of ``FE10Growth.cms``.

One panel, one tab per table (the Game Data hub picks the tab). Each tab lists the records with
their English names (``Mess/e_common.m``, else the Japanese ``common.m``) and shows the selected
record's fields as a form grouped like the record; a field applies when it is left or on Enter.
A record's lists (skills, sound classes, attributes, effectivenesses, skill conditions) and an
item's stat-bonus block are edited below the fields; they change the record's size, which
:mod:`fe10data` handles by moving everything after it. Save writes ``FE10Data.cms`` back
LZ10-compressed through the project (keeping the extracted file in ``originals/``).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from ..exceptions import ProjectError
from ..formats import fe10data, fe10growth, fe10_message
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from . import message_reference
from .widgets import ScrollFrame

TAB_KEYS = ("characters", "classes", "items", "skills", "growth", "chapters", "terrain", "battle_scenery",
            "supports", "groups", "bonds", "affinities", "affinity_pairs", "triangle", "difficulty", "biorhythm")
KIND_OF_TAB = {"characters": "character", "classes": "class", "items": "item", "skills": "skill",
               "chapters": "chapter", "terrain": "terrain", "supports": "support", "groups": "group",
               "bonds": "bond", "affinities": "affinity", "affinity_pairs": "affinity_pair",
               "triangle": "triangle", "difficulty": "difficulty", "growth": "growth",
               "battle_scenery": "battle_scenery", "biorhythm": "biorhythm"}
TAB_TITLES = {"characters": "Characters", "classes": "Classes", "items": "Items", "skills": "Skills",
              "chapters": "Chapters", "terrain": "Terrain", "supports": "Supports", "groups": "Army groups",
              "bonds": "Bonds", "affinities": "Affinities", "affinity_pairs": "Affinity pairs",
              "triangle": "Weapon triangle", "difficulty": "Difficulty constants", "growth": "Stats per level",
              "battle_scenery": "Battle scenery", "biorhythm": "Biorhythm"}
NAME_KEY = {"character": "mpid", "class": "mjid", "item": "miid", "skill": "msid", "chapter": "title",
            "terrain": "name_key", "group": "name_key"}

#: Label fields picked from labels with this prefix (the rest offer the values the table uses).
LABEL_PREFIXES = {
    "pid": "PID_", "mpid": "MPID_", "mnpid": "MNPID_", "fid": "FID_", "jid": "JID_",
    "aid": "AID_", "aid_1": "AID_", "aid_2": "AID_", "aid_3": "AID_", "aid_4": "AID_",
    "mjid": "MJID_", "demotes_to": "JID_", "promotes_to": "JID_", "other_form": "JID_",
    "innate_weapon": "IID_", "iid": "IID_", "miid": "MIID_", "effect": "EID_", "effect_2": "EID_",
    "effect_3": "EID_", "sid": "SID_", "msid": "MSID_", "item": "IID_", "extra_skill": "SID_",
    "lord": "PID_", "title": "MCT", "step_effect": "EID_", "move_sound": "SFX_", "move_sound_2": "SFX_",
}
#: Label fields named by a prefix of their key (chapter objectives per difficulty).
KEY_PREFIXES = (("win", "MW_"), ("lose", "ML_"))
HELP_PREFIX = {"character": "MNPID_", "class": "MH_J_", "item": "MH_I_", "skill": "MH_SKILL_"}
LIST_PREFIXES = {"skills": ("SID_",), "sounds": ("SFXC_",), "requirements": ("SFXC_",),
                 "conditions": ("SID_", "JID_", "PID_")}


def read_names(project: ModProject) -> dict[str, str]:
    """Message key -> first line of its text, English when the disc has it."""
    return fe10data.message_names(project.files_dir / "Mess")


class Fe10DataEditor(EditorPanel):
    display_name = "FE10Data.cms"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._dirty = False
        self._data = b""
        self._db: Optional[fe10data.Fe10Data] = None
        self._growth_data = b""
        self._growth: list[fe10data.Record] = []
        self._growth_dirty = False
        self._names = read_names(project)
        self._message_texts = message_reference.message_texts(project)
        self._tab = "characters"
        self._selected: dict[str, Optional[int]] = {key: None for key in TAB_KEYS}
        self._vars: dict[str, tk.StringVar] = {}
        self._shown: tuple = ()  # (tab, index) the form shows
        self._choice_cache: dict[tuple, list[str]] = {}
        self._build()
        self._load()

    # -- data ---------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            self._data = self._project.read_logical("game_data")
            self._db = fe10data.read_fe10data(self._data)
        except (ProjectError, ValueError, KeyError, IndexError) as exc:
            self._db = None
            self._status.configure(text=str(exc))
            return
        try:
            self._growth_data = self._project.read_logical("growth_data")
            self._growth = self._growth_records()
        except (ProjectError, ValueError, KeyError, IndexError):
            self._growth_data, self._growth = b"", []
        self._choice_cache.clear()
        self._refresh_list()

    def _growth_records(self) -> list[fe10data.Record]:
        """FE10Growth.cms's records in the shape the list and form use."""
        out = []
        for g in fe10growth.read_growth(self._growth_data):
            r = fe10data.Record("growth", g.index, g.lines_at, g.lines_at + fe10growth.LINE_SIZE * len(g.lines),
                                values={"pid": g.pid, "first": g.first, "last": g.last})
            r.lists["lines"] = g.lines
            out.append(r)
        return out

    def _table(self, kind: str) -> list[fe10data.Record]:
        return self._growth if kind == "growth" else self._db.table(kind)

    @property
    def dirty(self) -> bool:
        return self._dirty or self._growth_dirty

    def _replace_growth(self, data: bytes, what: str) -> None:
        self._growth_data = data
        self._growth = self._growth_records()
        self._growth_dirty = True
        self._save_button.configure(state="normal")
        self._status.configure(text=f"{what} (unsaved)")
        self._changelog.append("FE10Growth.cms", what)

    def _replace(self, data: bytes, what: str) -> None:
        """Adopt an edited file (re-read so offsets after a size change are current)."""
        self._data = data
        self._db = fe10data.read_fe10data(data)
        self._choice_cache.clear()
        self._dirty = True
        self._save_button.configure(state="normal")
        self._status.configure(text=f"{what} (unsaved)")
        self._changelog.append("FE10Data.cms", what)

    def save(self) -> None:
        saved = []
        for dirty_attr, logical, data_attr, label in (("_dirty", "game_data", "_data", "FE10Data.cms"),
                                                      ("_growth_dirty", "growth_data", "_growth_data", "FE10Growth.cms")):
            if not getattr(self, dirty_attr):
                continue
            try:
                self._project.write_logical(logical, getattr(self, data_attr))
            except OSError as exc:
                messagebox.showerror(f"Could not save {label}", str(exc), parent=self)
                return
            setattr(self, dirty_attr, False)
            saved.append(label)
            self._changelog.append(label, "Saved the game data tables")
        if saved:
            self._save_button.configure(state="disabled")
            self._status.configure(text=f"Saved {' and '.join(saved)}.")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Unsaved changes", "Discard the unsaved game data changes?", parent=self)

    def _title_card(self) -> None:
        """Draw the selected chapter's title card from its title (Radiant Dawn's window/title cards)."""
        from .. import chapters

        index = self._selected.get(self._tab)
        if self._db is None or index is None:
            messagebox.showinfo("Title card", "Select a chapter first.", parent=self)
            return
        cid = self._table("chapter")[index].values.get("cid") or ""
        chapter_id = cid[1:] if cid[1:].isdigit() else cid[1:].lower()
        title = self._names.get(self._table("chapter")[index].values.get("title") or "", "") or \
            chapters.chapter_titles(self._project).get(chapter_id, "")
        dialog = _TitleCardDialog(self, self._project, chapter_id, title)
        self.wait_window(dialog)
        written = getattr(dialog, "written", None)
        if written is not None:
            self._changelog.append(written.name, f"Drew the title card of chapter {chapter_id}")
            self._status.configure(text=f"Wrote {written.name}.")

    # -- layout -------------------------------------------------------------------------------
    def _build(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        self._heading = ttk.Label(top, text="", style="Heading.TLabel")
        self._heading.pack(side="left")
        self._save_button = ttk.Button(top, text="Save", style="Accent.TButton", command=self.save, state="disabled")
        self._save_button.pack(side="right")
        self._remove_button = ttk.Button(top, text="Remove", command=self._remove_record)
        self._add_button = ttk.Button(top, text="New (copy of selected)...", command=self._add_record)
        self._card_button = ttk.Button(top, text="Title card...", command=self._title_card)
        search = ttk.Frame(self, padding=(8, 6, 8, 0))
        search.pack(fill="x")
        ttk.Label(search, text="Search").pack(side="left")
        self._query = tk.StringVar()
        ttk.Entry(search, textvariable=self._query).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._query.trace_add("write", lambda *_: self._refresh_list())
        self._status = ttk.Label(self, text="", style="Muted.TLabel", padding=(8, 4))
        self._status.pack(anchor="w")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body)
        body.add(left, weight=2)
        self._tree = ttk.Treeview(left, columns=("id", "name"), show="headings", selectmode="browse")
        self._tree.heading("id", text="ID")
        self._tree.heading("name", text="Name")
        self._tree.column("id", width=200)
        self._tree.column("name", width=160)
        scroll = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        self._form = ScrollFrame(body, padding=(12, 0, 0, 0))
        body.add(self._form, weight=3)

    # -- list ---------------------------------------------------------------------------------
    @property
    def kind(self) -> str:
        return KIND_OF_TAB[self._tab]

    def select_tab(self, tab: str) -> None:
        if tab not in TAB_KEYS:
            return
        self._tab = tab
        self._refresh_list()

    def select_record(self, record_id: str) -> None:
        if self._db is None:
            return
        for r in self._table(self.kind):
            if r.id == record_id:
                self._selected[self._tab] = r.index
                self._refresh_list()
                return

    @staticmethod
    def _record_label(r: fe10data.Record) -> str:
        if r.kind in ("difficulty", "biorhythm"):
            return f"Row {r.index + 1}"
        if r.kind in ("bond", "affinity_pair", "triangle"):
            other = r.values.get("partner") or r.values.get("against") or ""
            return f"{r.id or '-'} / {other}"
        return r.id or f"#{r.index}"

    def _record_name(self, r: fe10data.Record) -> str:
        if r.kind in ("support", "bond", "growth") and (r.values.get("pid") or "").startswith("PID_"):
            return self._names.get("M" + r.values["pid"], "")
        key = r.values.get(NAME_KEY.get(r.kind, ""))
        return self._names.get(key, "") if key else ""

    def _refresh_list(self) -> None:
        file_key = "growth_data" if self.kind == "growth" else "game_data"
        for button in (self._remove_button, self._add_button, self._card_button):
            button.pack_forget()
        if self.kind == "chapter":
            self._card_button.pack(side="right", padx=(0, 6))
        if self.kind in fe10data.ADDABLE_KINDS:
            self._remove_button.pack(side="right", padx=(0, 6))
            self._add_button.pack(side="right", padx=(0, 6))
        self._heading.configure(text=f"{TAB_TITLES[self._tab]} ({self._project.profile.file_label(file_key)})")
        self._tree.delete(*self._tree.get_children())
        if self._db is None:
            return
        query = self._query.get().strip().lower()
        shown = 0
        for r in self._table(self.kind):
            name = self._record_name(r)
            if query and query not in (r.id or "").lower() and query not in name.lower():
                continue
            self._tree.insert("", "end", iid=str(r.index), values=(self._record_label(r), name))
            shown += 1
        if not self._dirty:
            self._status.configure(text=f"{shown} of {len(self._table(self.kind))} records")
        index = self._selected.get(self._tab)
        if index is not None and self._tree.exists(str(index)):
            self._tree.selection_set(str(index))
            self._tree.see(str(index))
            if self._shown != (self._tab, index):
                self._show_record(index)
        elif self._shown != (self._tab, None):
            self._show_record(None)

    def _on_select(self) -> None:
        selection = self._tree.selection()
        index = int(selection[0]) if selection else None
        self._selected[self._tab] = index
        if self._shown != (self._tab, index):
            self._show_record(index)

    # -- form ---------------------------------------------------------------------------------
    def _choices(self, key: str) -> list[str]:
        """Values offered for a label field or list."""
        cache_key = (self.kind, key)
        if cache_key in self._choice_cache:
            return self._choice_cache[cache_key]
        prefixes = LIST_PREFIXES.get(key)
        if prefixes is None and key == "help":
            prefixes = (HELP_PREFIX[self.kind],)
        if prefixes is None and key in LABEL_PREFIXES:
            prefixes = (LABEL_PREFIXES[key],)
        if prefixes is None and self.kind == "bond" and key in ("pid", "partner"):
            prefixes = ("PID_",)
        if prefixes is None:
            prefixes = next(((p,) for start, p in KEY_PREFIXES if key.startswith(start)), None)
        if prefixes is not None:
            values = sorted({v for p in prefixes for v in fe10data.labels_with_prefix(self._data, p)})
        else:  # the values this table already uses (affinities, weapon types, ranks...)
            seen = set()
            for r in self._table(self.kind):
                if key in r.lists:
                    seen.update(v if isinstance(v, str) else v[1] for v in r.lists[key])
                elif r.values.get(key):
                    seen.add(r.values[key])
            values = sorted(v for v in seen if v)
        self._choice_cache[cache_key] = values
        return values

    def _message_prefix(self, key: str, current: str) -> str | None:
        if key in ("help", "help_2"):
            return HELP_PREFIX.get(self.kind)
        if key in ("mpid", "mnpid", "mjid", "miid", "msid", "title"):
            return LABEL_PREFIXES[key]
        if key.startswith("win"):
            return "MW_"
        if key.startswith("lose"):
            return "ML_"
        if key == "name_key":
            return current.rsplit("_", 1)[0] + "_" if "_" in current else (
                "MT_" if self.kind == "terrain" else "MG_")
        return None

    def _message_values(self, prefix: str) -> tuple[list[str], dict[str, str]]:
        keys = sorted(key for key in self._message_texts if key.startswith(prefix))
        labels = {f"{key} — {message_reference.preview(self._message_texts[key], True)}": key for key in keys}
        return [*labels, message_reference.CREATE_MESSAGE], labels

    def _show_record(self, index: Optional[int]) -> None:
        body = self._form.body
        for child in body.winfo_children():
            child.destroy()
        self._vars = {}
        self._shown = (self._tab, index)
        if self._db is None or index is None:
            ttk.Label(body, text="Pick a record on the left.", style="Muted.TLabel").pack(anchor="w")
            return
        r = self._table(self.kind)[index]
        label = self._record_label(r)
        ttk.Label(body, text=self._record_name(r) or label, style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"{label}  ·  record {r.index}  ·  {r.end - r.start} bytes at {r.start:#x}",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        if self.kind == "terrain":
            self._terrain_block_note(body, r)
        if self.kind == "support":
            self._support_editor(body, r)
            return
        if self.kind == "growth":
            self._growth_editor(body, r)
            return
        if self.kind == "battle_scenery":
            self._scenery_editor(body, r)
            return
        groups: dict[str, ttk.Frame] = {}
        for d in fe10data.field_defs(self.kind):
            frame = groups.get(d.group)
            if frame is None:
                ttk.Label(body, text=d.group, style="Strong.TLabel").pack(anchor="w", pady=(10, 2))
                frame = groups[d.group] = ttk.Frame(body)
                frame.pack(anchor="w", fill="x")
                frame.columnconfigure(1, weight=1)
            row = len(frame.grid_slaves(column=0))
            ttk.Label(frame, text=d.label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 10))
            var = self._vars[d.key] = tk.StringVar(value=self._text(r.values.get(d.key)))
            prefix = self._message_prefix(d.key, self._text(r.values.get(d.key))) if d.kind == "label" else None
            if prefix:
                values, labels = self._message_values(prefix)
                widget = ttk.Combobox(frame, textvariable=var, values=values, width=42)

                def chosen(_e, key=d.key, field_var=var, field_prefix=prefix, choices=labels, box=widget):
                    selected = field_var.get()
                    if selected == message_reference.CREATE_MESSAGE:
                        old_id = self._text(self._table(self.kind)[r.index].values.get(key))
                        field_var.set(old_id)
                        initial = message_reference.suggested_id(
                            field_prefix, f"{r.id}_{key}", set(self._message_texts))
                        dialog = message_reference.NewMessageDialog(self, initial)
                        if dialog.result is None:
                            return
                        name, new_text = dialog.result
                        if not name.startswith(field_prefix):
                            messagebox.showerror("Create message", f"ID must start with {field_prefix}.", parent=self)
                            return
                        try:
                            fe10data.patch_field(self._data, self.kind, r.index, key, name)
                            message_reference.create_message(self._project, name, new_text)
                        except (OSError, ValueError) as exc:
                            messagebox.showerror("Create message", str(exc), parent=self)
                            return
                        self._message_texts = message_reference.message_texts(self._project)
                        self._names = read_names(self._project)
                        self._changelog.append(message_reference.common_path(self._project).name,
                                               f"Created message {name}")
                        box.configure(values=self._message_values(field_prefix)[0])
                        field_var.set(name)
                    else:
                        field_var.set(choices.get(selected, selected))
                    self._apply_field(key, r.index)
                    self._refresh_list()

                widget.bind("<<ComboboxSelected>>", chosen)
            elif d.kind == "label":
                widget = ttk.Combobox(frame, textvariable=var, values=self._choices(d.key), width=34)
                widget.bind("<<ComboboxSelected>>", lambda _e, k=d.key: self._apply_field(k, r.index))
            else:
                widget = ttk.Entry(frame, textvariable=var, width=10)
            widget.grid(row=row, column=1, sticky="w", pady=2)
            if prefix:
                shown = tk.StringVar()
                def show_text(*_args, source=var, target=shown):
                    target.set(fe10_message.plain_text(self._message_texts.get(source.get(), ""))
                               or ("(message not found)" if source.get() else ""))
                var.trace_add("write", show_text)
                show_text()
                ttk.Label(frame, textvariable=shown, style="Muted.TLabel", wraplength=440,
                          justify="left").grid(row=row, column=2, sticky="w", padx=(10, 0))
            widget.bind("<FocusOut>", lambda _e, k=d.key: self._apply_field(k, r.index))
            widget.bind("<Return>", lambda _e, k=d.key: self._apply_field(k, r.index))
            note = fe10data.FIELD_NOTES.get(d.key)
            if note and not prefix:
                ttk.Label(frame, text=note, style="Muted.TLabel", wraplength=320, justify="left").grid(
                    row=row, column=2, sticky="w", padx=(10, 0))
        for key, title in fe10data.LISTS.get(self.kind, {}).items():
            self._list_editor(body, r, key, title)
        if self.kind == "item":
            self._bonus_editor(body, r)

    @staticmethod
    def _text(value) -> str:
        return "" if value is None else str(value)

    def _apply_field(self, key: str, index: int) -> None:
        """Apply a form field of record ``index`` (bound per form: focus can leave the field after
        another record was picked)."""
        if self._db is None or key not in self._vars or index != self._selected.get(self._tab):
            return
        r = self._db.table(self.kind)[index]
        text = self._vars[key].get().strip()
        old = r.values.get(key)
        if text == self._text(old):
            return
        definition = next(d for d in fe10data.field_defs(self.kind) if d.key == key)
        try:
            if definition.kind == "label":
                value = text or None
            elif definition.kind == "f32":
                value = float(text)
            else:
                value = int(text, 0)
            data = fe10data.patch_field(self._data, self.kind, r.index, key, value)
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            self._vars[key].set(self._text(old))
            return
        self._replace(data, f"{r.id}: {definition.label} = {text or '(none)'}")
        if key == NAME_KEY.get(self.kind) or key == fe10data.ID_FIELD.get(self.kind):
            self._refresh_list()

    # -- lists --------------------------------------------------------------------------------
    def _list_editor(self, body, r: fe10data.Record, key: str, title: str) -> None:
        ttk.Label(body, text=title, style="Strong.TLabel").pack(anchor="w", pady=(12, 2))
        note = fe10data.FIELD_NOTES.get(key)
        if note:
            ttk.Label(body, text=note, style="Muted.TLabel").pack(anchor="w")
        frame = ttk.Frame(body)
        frame.pack(anchor="w", fill="x")
        modal = self.kind == "skill"
        entries = list(r.lists[key])
        box = tk.Listbox(frame, height=max(3, min(8, len(entries) + 1)), width=44, exportselection=False)
        for entry in entries:
            box.insert("end", f"{entry[0]}  {entry[1]}" if modal else (entry or "(none)"))
        box.grid(row=0, column=0, rowspan=4, sticky="w")
        pick = tk.StringVar()
        mode = tk.StringVar(value="1" if key == "conditions" else "0")
        controls = ttk.Frame(frame)
        controls.grid(row=0, column=1, sticky="nw", padx=(8, 0))
        ttk.Combobox(controls, textvariable=pick, values=self._choices(key), width=30).pack(anchor="w")
        if modal:
            mode_row = ttk.Frame(controls)
            mode_row.pack(anchor="w", pady=(2, 0))
            ttk.Label(mode_row, text="Mode").pack(side="left")
            ttk.Entry(mode_row, textvariable=mode, width=4).pack(side="left", padx=(6, 0))
        buttons = ttk.Frame(controls)
        buttons.pack(anchor="w", pady=(4, 0))

        def write(new_entries, what):
            try:
                data = fe10data.set_list(self._data, self.kind, r.index, key, new_entries)
            except ValueError as exc:
                messagebox.showerror("Could not change the list", str(exc), parent=self)
                return
            self._replace(data, f"{r.id}: {title} {what}")
            self._show_record(r.index)

        def add():
            label = pick.get().strip()
            if not label:
                return
            try:
                entry = (int(mode.get(), 0), label) if modal else label
            except ValueError:
                messagebox.showerror("Invalid mode", "The mode is a number.", parent=self)
                return
            write(entries + [entry], f"+ {label}")

        def remove():
            chosen = box.curselection()
            if chosen:
                i = chosen[0]
                write(entries[:i] + entries[i + 1:], f"- {entries[i][1] if modal else entries[i]}")

        def move(delta):
            chosen = box.curselection()
            if not chosen:
                return
            i = chosen[0]
            j = i + delta
            if 0 <= j < len(entries):
                moved = list(entries)
                moved[i], moved[j] = moved[j], moved[i]
                write(moved, "reordered")

        ttk.Button(buttons, text="Add", command=add).pack(side="left")
        ttk.Button(buttons, text="Remove", command=remove).pack(side="left", padx=(4, 0))
        ttk.Button(buttons, text="↑", width=3, command=lambda: move(-1)).pack(side="left", padx=(4, 0))
        ttk.Button(buttons, text="↓", width=3, command=lambda: move(1)).pack(side="left", padx=(2, 0))

    def _bonus_editor(self, body, r: fe10data.Record) -> None:
        ttk.Label(body, text="Stat bonuses while held", style="Strong.TLabel").pack(anchor="w", pady=(12, 2))
        frame = ttk.Frame(body)
        frame.pack(anchor="w")
        has = tk.BooleanVar(value=r.bonuses is not None)
        values = [tk.StringVar(value=str(v)) for v in (r.bonuses or [0] * len(fe10data.BONUS_NAMES))]

        def apply(*_):
            if not has.get():
                if r.bonuses is None:
                    return
                bonuses = None
            else:
                try:
                    bonuses = [int(v.get() or 0) for v in values]
                except ValueError:
                    messagebox.showerror("Invalid value", "Bonuses are whole numbers.", parent=self)
                    return
                if bonuses == r.bonuses:
                    return
            try:
                data = fe10data.set_item_bonuses(self._data, r.index, bonuses)
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=self)
                return
            self._replace(data, f"{r.id}: stat bonuses {'removed' if bonuses is None else 'set'}")
            self._show_record(r.index)

        ttk.Checkbutton(frame, text="Has a bonus block", variable=has, command=apply).grid(
            row=0, column=0, columnspan=10, sticky="w")
        for i, name in enumerate(fe10data.BONUS_NAMES):
            ttk.Label(frame, text=name).grid(row=1, column=i, padx=2)
            entry = ttk.Entry(frame, textvariable=values[i], width=4,
                              state="normal" if r.bonuses is not None else "disabled")
            entry.grid(row=2, column=i, padx=2)
            entry.bind("<FocusOut>", apply)
            entry.bind("<Return>", apply)

    # -- terrain and supports -----------------------------------------------------------------
    def _terrain_block_note(self, body, r: fe10data.Record) -> None:
        users = fe10data.terrain_block_users(self._data, r.index)
        others = [self._db.table("terrain")[i].values.get("name") or str(i) for i in users if i != r.index]
        if not others:
            text = "This type has its own stats block."
        else:
            more = "..." if len(others) > 8 else ""
            text = (f"The stats below are shared with {len(others)} other type(s): {', '.join(others[:8])}{more}. "
                    "Editing them changes all of them.")
        row = ttk.Frame(body)
        row.pack(anchor="w", fill="x", pady=(0, 6))
        ttk.Label(row, text=text, style="Muted.TLabel", wraplength=520, justify="left").pack(side="left")
        if others:
            def split():
                self._replace(fe10data.own_terrain_block(self._data, r.index), f"{r.id}: own terrain stats block")
                self._show_record(r.index)
            ttk.Button(row, text="Give this type its own stats", command=split).pack(side="left", padx=(8, 0))

    def _support_editor(self, body, r: fe10data.Record) -> None:
        ttk.Label(body, text="Partners: flag (0 or 255) and support speed", style="Strong.TLabel").pack(
            anchor="w", pady=(4, 2))
        grid = ttk.Frame(body)
        grid.pack(anchor="w")
        for column, title in enumerate(("Partner", "", "Flag", "Speed")):
            ttk.Label(grid, text=title, style="Muted.TLabel").grid(row=0, column=column, sticky="w", padx=(0, 8))
        for k, (pid, flag, speed) in enumerate(r.lists["partners"]):
            ttk.Label(grid, text=pid or "-").grid(row=k + 1, column=0, sticky="w", padx=(0, 8))
            ttk.Label(grid, text=self._names.get("M" + (pid or ""), ""), style="Muted.TLabel").grid(
                row=k + 1, column=1, sticky="w", padx=(0, 8))
            flag_var, speed_var = tk.StringVar(value=str(flag)), tk.StringVar(value=str(speed))
            for column, var in ((2, flag_var), (3, speed_var)):
                entry = ttk.Entry(grid, textvariable=var, width=5)
                entry.grid(row=k + 1, column=column, sticky="w", padx=(0, 8), pady=1)
                apply = (lambda _e, k=k, f=flag_var, v=speed_var: self._apply_support(r, k, f, v))
                entry.bind("<FocusOut>", apply)
                entry.bind("<Return>", apply)

    def _apply_support(self, r: fe10data.Record, k: int, flag_var: tk.StringVar, speed_var: tk.StringVar) -> None:
        if r.index != self._selected.get(self._tab) or self.kind != "support":
            return
        current = self._db.table("support")[r.index].lists["partners"][k]
        try:
            flag, speed = int(flag_var.get(), 0), int(speed_var.get(), 0)
            if (flag, speed) == tuple(current[1:]):
                return
            data = fe10data.set_support(self._data, r.index, k, flag, speed)
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            flag_var.set(str(current[1]))
            speed_var.set(str(current[2]))
            return
        self._replace(data, f"{r.id} / {current[0]}: support flag {flag}, speed {speed}")

    # -- stats per level (FE10Growth.cms) and battle scenery ----------------------------------
    def _growth_editor(self, body, r: fe10data.Record) -> None:
        shared = fe10growth.sharing(self._growth_data, r.index)
        note = (f"Absolute stats at each internal level (tier 1: 1-20, tier 2: 21-40, tier 3: 41-60), "
                f"levels {r.values['first']}-{r.values['last']}. A unit's starting stats come from its "
                "Characters record, not from here; what the game uses these lines for is not known yet.")
        if len(shared) > 1:
            note += f" Shared with records {', '.join(str(i) for i in shared if i != r.index)}."
        ttk.Label(body, text=note, style="Muted.TLabel", wraplength=560, justify="left").pack(anchor="w", pady=(0, 6))
        grid = ttk.Frame(body)
        grid.pack(anchor="w")
        ttk.Label(grid, text="Level", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        for column, stat in enumerate(fe10data.STAT_NAMES):
            ttk.Label(grid, text=stat, style="Muted.TLabel").grid(row=0, column=column + 1, padx=2)
        for k, line in enumerate(r.lists["lines"]):
            level = r.values["first"] + k
            ttk.Label(grid, text=f"{level}  ({fe10growth.GrowthRecord.describe_level(level)})").grid(
                row=k + 1, column=0, sticky="w", padx=(0, 8))
            variables = [tk.StringVar(value=str(v)) for v in line]
            for column, var in enumerate(variables):
                entry = ttk.Entry(grid, textvariable=var, width=4)
                entry.grid(row=k + 1, column=column + 1, padx=2, pady=1)
                apply = (lambda _e, level=level, vs=variables: self._apply_growth(r, level, vs))
                entry.bind("<FocusOut>", apply)
                entry.bind("<Return>", apply)

    def _apply_growth(self, r: fe10data.Record, level: int, variables) -> None:
        if r.index != self._selected.get(self._tab) or self.kind != "growth":
            return
        current = self._growth[r.index].lists["lines"][level - r.values["first"]]
        try:
            stats = [int(v.get(), 0) for v in variables]
            if stats == current:
                return
            data = fe10growth.set_line(self._growth_data, r.index, level, stats)
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            for var, value in zip(variables, current):
                var.set(str(value))
            return
        self._replace_growth(data, f"{r.id}: stats at level {level}")

    def _scenery_editor(self, body, r: fe10data.Record) -> None:
        names = fe10data.battle_scenery_names(self._data)
        terrain = [t.values.get("name") or str(t.index) for t in self._db.table("terrain")]
        choices = ["(none)"] + [f"{i} {n}" for i, n in enumerate(names)]
        ttk.Label(body, text="Battle background fought in front of, per terrain type of this map. Types left at "
                  "(none) fall back to type 0's entry, which reads as the map's default.", style="Muted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(0, 6))
        grid = ttk.Frame(body)
        grid.pack(anchor="w")
        rows = [(i, v) for i, v in enumerate(r.lists["scenery"]) if v != 0xFFFF]
        for row, (i, value) in enumerate(rows):
            ttk.Label(grid, text=f"{i} {terrain[i] if i < len(terrain) else ''}").grid(row=row, column=0, sticky="w",
                                                                                       padx=(0, 8))
            var = tk.StringVar(value=choices[value + 1] if value < len(names) else str(value))
            box = ttk.Combobox(grid, textvariable=var, values=choices, width=30, state="readonly")
            box.grid(row=row, column=1, sticky="w", pady=1)
            box.bind("<<ComboboxSelected>>", lambda _e, i=i, v=var: self._apply_scenery(r, i, v.get()))
        add = ttk.Frame(body)
        add.pack(anchor="w", pady=(8, 0))
        ttk.Label(add, text="Set terrain type").pack(side="left")
        pick_type = tk.StringVar()
        ttk.Combobox(add, textvariable=pick_type, width=22, state="readonly",
                     values=[f"{i} {n}" for i, n in enumerate(terrain)]).pack(side="left", padx=(6, 6))
        pick_scenery = tk.StringVar(value=choices[0])
        ttk.Combobox(add, textvariable=pick_scenery, values=choices, width=26, state="readonly").pack(side="left")
        ttk.Button(add, text="Apply", command=lambda: pick_type.get() and self._apply_scenery(
            r, int(pick_type.get().split()[0]), pick_scenery.get())).pack(side="left", padx=(6, 0))

    def _apply_scenery(self, r: fe10data.Record, terrain: int, choice: str) -> None:
        scenery = 0xFFFF if choice == "(none)" else int(choice.split()[0])
        try:
            data = fe10data.set_battle_scenery(self._data, r.index, terrain, scenery)
        except (ValueError, IndexError) as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            return
        if data != self._data:
            self._replace(data, f"{r.id}: terrain {terrain} battle scenery {choice}")
            self._show_record(r.index)

    # -- adding and removing records ----------------------------------------------------------
    def references(self, label: str) -> list[str]:
        """Records naming ``label`` in a field or list (other than its own ID)."""
        found = []
        for kind in fe10data.ALL_KINDS:
            id_key = fe10data.ID_FIELD.get(kind)
            for r in self._table(kind):
                hit = any(v == label for k, v in r.values.items() if k != id_key) or any(
                    (v == label) if isinstance(v, str) else (label in v) for values in r.lists.values()
                    for v in values if isinstance(v, (str, tuple)))
                if hit:
                    found.append(f"{kind} {self._record_label(r)}")
        return found

    def _add_record(self) -> None:
        index = self._selected.get(self._tab)
        if self._db is None or index is None:
            messagebox.showinfo("New record", "Pick the record the new one starts as a copy of.", parent=self)
            return
        source = self._table(self.kind)[index]
        new_id = None
        prefix = fe10data.ID_PREFIX.get(self.kind)
        if prefix is not None:
            new_id = simpledialog.askstring("New record", f"ID of the copy of {source.id}:",
                                            initialvalue=prefix, parent=self)
            if not new_id or new_id == prefix:
                return
            if any(r.id == new_id for r in self._table(self.kind)):
                messagebox.showerror("New record", f"{new_id} is already used.", parent=self)
                return
        try:
            data, new_index = fe10data.add_record(self._data, self.kind, index, new_id)
        except ValueError as exc:
            messagebox.showerror("New record", str(exc), parent=self)
            return
        self._replace(data, f"New {self.kind} {new_id or new_index} (copy of {self._record_label(source)})")
        self._selected[self._tab] = new_index
        self._refresh_list()

    def _remove_record(self) -> None:
        index = self._selected.get(self._tab)
        if self._db is None or index is None:
            return
        r = self._table(self.kind)[index]
        label = self._record_label(r)
        warning = ""
        if r.id and self.kind in ("character", "class", "item"):
            users = self.references(r.id)
            if users:
                messagebox.showerror("Remove", f"{r.id} is still named by: {', '.join(users[:10])}"
                                     f"{'...' if len(users) > 10 else ''}. Change those first.", parent=self)
                return
        if self.kind in ("character", "class", "item"):
            warning += ("\n\nOnly FE10Data.cms is searched for uses: map deployments and event scripts that "
                        "name it are not checked for Radiant Dawn yet.")
        if self.kind in fe10data.SAVED_BY_NUMBER:
            warning += ("\n\nSaves store these records by number: saves made before this change will load "
                       "the records after it under the wrong numbers.")
        if not messagebox.askyesno("Remove", f"Remove {label}?{warning}", parent=self):
            return
        try:
            data = fe10data.remove_record(self._data, self.kind, index)
        except ValueError as exc:
            messagebox.showerror("Remove", str(exc), parent=self)
            return
        self._replace(data, f"Removed {self.kind} {label}")
        self._selected[self._tab] = None
        self._refresh_list()


class _TitleCardDialog(tk.Toplevel):
    """Draw a chapter's title card (``window/title/e_ch<id>.cms``) from its title, preview it next to
    the current one, and write it."""

    def __init__(self, parent, project: ModProject, chapter_id: str, title: str):
        super().__init__(parent)
        from .. import chapter_images
        from PIL import ImageTk

        self._ci, self._tk_image = chapter_images, ImageTk
        self.title(f"Title card of chapter {chapter_id}")
        self.transient(parent.winfo_toplevel())
        self._project, self._chapter, self._font = project, chapter_id, None
        self._files = project.extracted_dir / "files"
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Title (from the chapter's title key):").pack(anchor="w")
        self._title = tk.StringVar(value=title)
        entry = ttk.Entry(body, textvariable=self._title, width=60)
        entry.pack(fill="x")
        self._title.trace_add("write", lambda *_: self._draw())
        self._images = ttk.Frame(body)
        self._images.pack(pady=8)
        self._current = tk.Label(self._images, background="#28283c")
        self._current.grid(row=0, column=0, padx=4)
        self._new = tk.Label(self._images, background="#28283c")
        self._new.grid(row=0, column=1, padx=4)
        ttk.Label(self._images, text="Current").grid(row=1, column=0)
        ttk.Label(self._images, text="New").grid(row=1, column=1)
        self._font_label = ttk.Label(body, style="Muted.TLabel", text="Font: the game's dialogue font "
                                     "(the retail serif is pre-drawn art; pick a serif TrueType font to match it)")
        self._font_label.pack(anchor="w")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Use a TrueType/OpenType font...", command=self._pick_font).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Write", style="Accent.TButton", command=self._write).pack(side="right", padx=4)
        self._result = None
        path = self._files / chapter_images.FE10_CARD_FOLDER / chapter_images.fe10_card_name(chapter_id)
        if path.is_file():
            self._photo_current = ImageTk.PhotoImage(chapter_images.preview(path.read_bytes()))
            self._current.configure(image=self._photo_current)
        self._draw()
        self.grab_set()

    def _draw(self) -> None:
        try:
            self._result = self._ci.fe10_title_card(self._files, self._chapter, self._title.get(), truetype=self._font)
        except (OSError, ValueError) as exc:
            self._result = None
            self._new.configure(image="", text=str(exc), foreground="white")
            return
        if self._result is None:
            self._new.configure(image="", text="No card template or font on the disc", foreground="white")
            return
        self._photo_new = self._tk_image.PhotoImage(self._ci.preview(self._result[1]))
        self._new.configure(image=self._photo_new, text="")

    def _pick_font(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self, title="Font", filetypes=[("Fonts", "*.ttf *.otf *.ttc")])
        if path:
            self._font = path
            self._font_label.configure(text=f"Font: {path}")
            self._draw()

    def _write(self) -> None:
        if self._result is None:
            return
        path, data = self._result
        self._project.write_keeping_original(path, data)
        self.written = path
        self.destroy()
