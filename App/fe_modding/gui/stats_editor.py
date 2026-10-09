"""Game Data editor: classes, items, skills, terrain types, chapters and the
general tables - all live in ``FE8Data.bin`` (see
:mod:`fe_modding.formats.fe8data` for how it was reverse-engineered and what's
confirmed vs. still open). Characters live in the same file but are edited on
their own page (``character_form.py``); both work on one shared
:class:`~.fe8_session.Fe8DataSession`, so neither can overwrite the other.

Each record tab lists its records as tiles (:class:`~.widgets.TileBrowser`:
a search box, category toggles for items (weapon type) and classes
(unpromoted, promoted, laguz), and the item or skill icon on
the tile); clicking one opens its
full-width form, with **‹ All …** and previous/next above it.
Every field is written to the session as soon as it is left (Tab, Enter, a
click elsewhere or a drop-down choice); **Save FE8Data.bin** writes the file,
and the build copies it into ``system.cmp``, which holds the copy the game
reads.

Editable, per tab:

- classes: ID (JID), name key (MJID), description key (MH_J), promotes-to,
  class model AID, innate weapon, weapon ranks (a new rank string is added to
  the pool, so classes that shared the old one keep it), the five innate
  skills, build, weight, movement, skill capacity, vision, movement type,
  caps, base stats, growth rates, growth modifiers and the three category
  tokens (check boxes);
- items: every field of the 96-byte record, decoded (``fe8data.ItemEntry``):
  ID, name and description keys, weapon and attack type, rank, weapon EXP,
  icon, combat stats, cost, the six property and two "effective against"
  token slots (check boxes), effects, trail colour, and the stat and growth
  bonuses while equipped. There is no hex box: only the two padding bytes the
  game never reads are left out;
- skills: ID (SID, renaming the record's own symbol with it), Japanese name,
  menu name key (MSID), both help keys, effect, the restriction list, the
  scroll that teaches it, icon, capacity cost and the "has a scroll" byte
  (never read);
- terrain: name and display-name key, and the 24-byte stats block
  (``fe8data.patch_terrain_stats``), shared with the types using the same
  block unless the type is given its own;
- chapters: every field of the ``ChapterData`` record (files, objectives per
  difficulty, scenes, enemy levels, trial grades);
- general: the ``GameData`` difficulty constants, the army groups
  (``GroupData``), the battle skies (``BattleSkyData``) and the build
  time/author (``DatabaseHead``).

The battle scenes (``BattleTerrData``) are edited on each chapter's page
(``battle_scene_editor.py``).

Classes, items and chapters have **New…** (empty or a
copy) and **Remove** (refused while anything still names the record, see
:mod:`.record_actions`). Skills and terrain types keep their count: the game
refers to them by position.

Items and skills show their icon from ``window/icon.tpl``
(:mod:`fe_modding.formats.icons`); **Edit icon ›** opens that icon in
Assets › Icons, which replaces, exports and saves it. A weapon links to its
battle model under Assets › 3D Models: the one its ``xwp/<NAME>.dbx`` table
in ``zdbx.cmp`` names, and ``xwp/forge/<name>_b`` for the forged version.
Links go through the ``navigate`` callback the page passes in (a workspace
route).

The skill and chapter forms also edit the whole record as hex, except
its pointer words (``fe8data.patch_record_bytes`` refuses those: the loader
relocates them, so they are edited through their own fields). A field naming
another record (a class's promotion, a character's class, a skill) takes only
labels already in the file; IDs, text keys, model and effect names are added
to the string pool when new.
"""

from __future__ import annotations

import struct
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from ..formats import fe8data, icons, zdbx
from .. import excel_io
from ..formats.fe9_message_scene import to_display
from ..game_profile import PATH_OF_RADIANCE_PROFILE, profile_of
from ..project import ModProject
from . import record_actions, theme
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .fe8_session import Fe8DataSession
from . import message_reference
from .widgets import ScrollFrame, TileBrowser

#: params[1] and params[2]; params[0] is the icon, edited next to its picture.
SKILL_PARAM_LABELS = ["Capacity cost", "Has scroll (unread)"]
#: Weapon types whose items have a battle model (xwp/); tomes, staves and items have none.
MODEL_WEAPON_TYPES = ("sword", "lance", "axe", "bow", "knife")
TAB_KEYS = ["classes", "items", "skills", "terrain", "chapters", "general"]
#: Tabs whose records can be added and removed, and their table kind.
TAB_KINDS = {"classes": "class", "items": "item", "chapters": "chapter"}
#: Tabs of tables the engine binds by position (FE8DATA_NOTES.md §4.7).
FIXED_TABS = {"skills": "The game checks skills by their position in the table: they can be edited, "
                        "not added or removed.",
              "terrain": "The game walks exactly 77 terrain types: they can be edited, not added or removed."}
#: The tiles of each tab: icons for items and skills (classes have no icon).
TILE_OPTIONS = {"items": {"image_box": (4, 2)}, "skills": {"image_box": (4, 2)}}
#: Icons are drawn at this many pixels on their tiles (items are 24, skills 32).
TILE_IMAGE_SIZE = 48
GAME_DATA_LABELS = {
    "battle_exp_mode_bonus": "Battle EXP mode bonus", "battle_exp_level_constant": "Battle EXP level constant",
    "promotion_exp_bonus_base": "Promoted-unit EXP base", "boss_exp_bonus": "Boss kill EXP bonus",
    "thief_exp_bonus": "Thief kill EXP bonus", "laguz_growth_bonus": "Laguz growth bonus",
    "class_critical_bonus": "Class critical bonus (Crit+)",
}


def _number(text: str, low: int, high: int) -> int:
    try:
        value = int(text.strip())
    except ValueError:
        raise ValueError("must be a whole number") from None
    if not low <= value <= high:
        raise ValueError(f"must be {low} to {high}")
    return value


def _label_or_none(text: str) -> Optional[str]:
    return text.strip() or None


class _TextVar:
    """``get``/``set`` over a Text widget, so a hex box is a form field like the entries."""

    def __init__(self, widget: tk.Text):
        self._widget = widget

    def get(self) -> str:
        return self._widget.get("1.0", "end-1c")

    def set(self, value: str) -> None:
        self._widget.delete("1.0", "end")
        self._widget.insert("1.0", value)


class _Field:
    def __init__(self, label: str, var, read: Callable[[], str], apply: Callable[[bytes, str], bytes]):
        self.label, self.var, self.read, self.apply = label, var, read, apply
        self.shown = ""  # what the form last displayed; only a changed field is written

    def load(self) -> None:
        self.shown = self.read()
        self.var.set(self.shown)


class _Form:
    """The fields of the record shown in one tab. A field is written to the
    session when it is left; the raw hex box goes first so decoded fields
    edited at the same time win over its old copy of them."""

    def __init__(self, editor: "StatsEditor", kind: str, index: int):
        self.editor, self.kind, self.index = editor, kind, index
        self.fields: list[_Field] = []

    def add(self, widgets, label: str, var, read, apply, *, first: bool = False) -> None:
        """One field, edited through ``widgets`` (one widget or several)."""
        field = _Field(label, var, read, apply)
        field.load()
        if first:
            self.fields.insert(0, field)
        else:
            self.fields.append(field)
        commit = lambda _e=None: self.editor._commit(self)  # noqa: E731
        for widget in widgets if isinstance(widgets, (list, tuple)) else (widgets,):
            widget.bind("<FocusOut>", commit, add="+")
            widget.bind("<Return>" if not isinstance(widget, tk.Text) else "<Control-Return>", commit, add="+")
            if isinstance(widget, ttk.Combobox):
                widget.bind("<<ComboboxSelected>>", commit, add="+")
            if isinstance(widget, ttk.Checkbutton):
                widget.configure(command=commit)

    def reload(self) -> None:
        """Show the record as the session has it now, keeping fields the
        user is still editing."""
        for field in self.fields:
            if field.var.get() == field.shown:
                field.load()


class StatsEditor(EditorPanel):
    display_name = "Game Data"
    shares_fe8_session = True  # its unsaved edits are the session's, listed once as FE8Data.bin

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog,
                 session: Fe8DataSession | None = None, navigate: Optional[Callable[[tuple], None]] = None):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._navigate = navigate
        self._icon_images: list = []
        self._icon_stamp: Optional[int] = None
        self._tables: dict = {}
        self._tables_stamp: Optional[int] = None
        self._session = session or Fe8DataSession(project, changelog)
        self._path = self._session.path
        self._texts: Optional[dict] = None
        self._skill_descriptions: Optional[dict] = None
        self._forms: dict[str, Optional[_Form]] = {key: None for key in TAB_KEYS}
        self._pickers: dict[str, TileBrowser] = {}
        self._bodies: dict[str, ScrollFrame] = {}
        self._session.subscribe(self._on_session_changed)
        self._build_widgets()
        if self._session.available:
            self._refresh_pickers()
            self._show_general()
        else:
            ttk.Label(self._notebook.master, text=self._session.unavailable_reason,
                      style="Muted.TLabel").pack(pady=8)
        self._on_session_changed(None)  # the character page may have edited the session already

    # -- shared FE8Data.bin ------------------------------------------------
    @property
    def _data(self) -> bytes:
        return self._session.data

    @_data.setter
    def _data(self, value: bytes) -> None:
        self._session.data = value

    @property
    def _dirty(self) -> bool:
        return self._session.dirty

    @property
    def _fe8(self):
        return self._session.fe8

    @property
    def _labels_by_prefix(self) -> dict:
        return self._session.labels_by_prefix

    def confirm_navigate_away(self) -> bool:
        self.flush()
        return True  # edits stay in the session until saved; the workspace asks on close

    def _on_session_changed(self, source) -> None:
        try:
            dirty = self._session.dirty
            self._save_button.config(state="normal" if dirty else "disabled")
            self._revert_button.config(state="normal" if dirty else "disabled")
            if source is not self:
                # another view (character page, supports) or a reload: show the records as they are now
                for form in self._forms.values():
                    if form is not None:
                        form.reload()
        except tk.TclError:
            pass

    # -- names ---------------------------------------------------------------------
    def _text(self, key: Optional[str]) -> str:
        if not key:
            return ""
        if self._texts is None:
            system_cmp = profile_of(self._project).path_or_none(self._project.extracted_dir / "files", "system_archive")
            try:
                loose = message_reference.common_path(self._project)
                self._texts = (message_reference.message_texts(self._project) if loose.is_file()
                               else fe8data.read_message_texts(system_cmp)
                               if system_cmp is not None and system_cmp.exists() else {})
            except Exception:  # noqa: BLE001 - names are a convenience
                self._texts = {}
        text = self._texts.get(key, "").strip()
        if text and not text.isascii():
            try:
                text = to_display(text)
            except UnicodeError:
                pass
        return text

    def _descriptions(self) -> dict:
        if self._skill_descriptions is None:
            system_cmp = profile_of(self._project).path_or_none(self._project.extracted_dir / "files", "system_archive")
            try:
                self._skill_descriptions = (
                    fe8data.read_skill_descriptions(system_cmp) if system_cmp is not None and system_cmp.exists() else {})
            except Exception:  # noqa: BLE001 - descriptions are a convenience
                self._skill_descriptions = {}
        return self._skill_descriptions

    def class_name(self, c) -> str:
        return self._text(c.mjid) or (c.jid or "")

    def item_name(self, it) -> str:
        return self._text(it.miid) or (it.iid or "")

    def skill_name(self, s) -> str:
        text = self._text(s.msid)
        if text and text.isascii():
            return text
        return (s.sid or "")[4:].replace("_", " ").title() or "(unnamed)"

    def _terrain_name(self, t) -> str:
        return self._text(t.name_key) or t.name

    # -- icons and weapon models ---------------------------------------------------
    @property
    def _files_dir(self) -> Path:
        return self._project.extracted_dir / "files"

    def _icons(self) -> list:
        """The two images of window/icon.tpl, re-read when the file changes."""
        path = icons.icon_path(self._files_dir)
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return []
        if stamp != self._icon_stamp:
            try:
                self._icon_images = icons.read_icon_images(path.read_bytes())
            except Exception:  # noqa: BLE001 - icons are a convenience
                self._icon_images = []
            self._icon_stamp = stamp
        return self._icon_images

    def _icon_row(self, parent, row: int, columns: int, size: int, image_index: int,
                  cell: Callable[[], Optional[int]], target: Callable[[], str],
                  sharing: Optional[Callable[[], str]] = None) -> Callable[[], None]:
        """The icon at twice its size and a link to it in Assets › Icons;
        returns the function that redraws it."""
        frame = ttk.Frame(parent, style="Page.TFrame")
        frame.grid(row=row, column=0, columnspan=columns, sticky="w", pady=(4, 2))
        picture = ttk.Label(frame, relief="groove", anchor="center")
        picture.pack(side="left")
        edit = None
        if self._navigate is not None:
            edit = ttk.Button(frame, text="Edit icon ›", command=lambda: self._navigate(("asset", "icons", target())))
            edit.pack(side="left", padx=(10, 0))
        note = ttk.Label(frame, style="Muted.TLabel", wraplength=460, justify="left")
        note.pack(side="left", padx=(12, 0))

        def refresh() -> None:
            try:
                image = icons.cell_image(self._icons(), image_index, cell(), size)
                if image is None:
                    picture.config(image="", text="no icon", width=8)
                    picture.image = None
                else:
                    backing = Image.new("RGBA", image.size, (96, 96, 96, 255))
                    backing.alpha_composite(image)
                    photo = ImageTk.PhotoImage(backing.resize((size * 2, size * 2), Image.NEAREST))
                    picture.config(image=photo, text="", width=0)
                    picture.image = photo
                if edit is not None:
                    edit.config(state="normal" if image is not None else "disabled")
                note.config(text=sharing() if sharing is not None else "")
            except tk.TclError:
                pass

        refresh()
        return refresh

    def _weapon_tables(self) -> dict:
        """``xwp/<NAME>.dbx`` of zdbx.cmp, re-read when the file changes."""
        path = PATH_OF_RADIANCE_PROFILE.path(self._files_dir, "battle_data")  # battle tables: Path of Radiance only for now
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return {}
        if stamp != self._tables_stamp:
            try:
                self._tables = icons.weapon_tables(zdbx.read_zdbx_path(path))
            except Exception:  # noqa: BLE001 - the model link is a convenience
                self._tables = {}
            self._tables_stamp = stamp
        return self._tables

    def _model_row(self, parent, row: int, columns: int, iid: Optional[str]) -> None:
        """The weapon's battle model, as its zdbx.cmp table names it, and its forged version."""
        found = icons.weapon_model(self._files_dir, iid, self._weapon_tables())
        if found is None:
            return
        frame = ttk.Frame(parent, style="Page.TFrame")
        frame.grid(row=row, column=0, columnspan=columns, sticky="w", pady=(4, 2))
        ttk.Label(frame, text="Battle model").pack(side="left", padx=(0, 10))
        if found.path is not None:
            ttk.Label(frame, text=f"{found.label}/{found.path.name}").pack(side="left")
            if self._navigate is not None:
                ttk.Button(frame, text="Open 3D model ›", command=lambda: self._navigate(
                    ("asset", "models", found.label))).pack(side="left", padx=(8, 0))
        elif not found.has_table:
            ttk.Label(frame, text=f"none: zdbx.cmp has no xwp/{found.name}.dbx, so battles draw no weapon",
                      style="Warn.TLabel").pack(side="left")
        elif found.folder:
            ttk.Label(frame, text=f"missing: {found.folder}/{found.model}.cmp", style="Warn.TLabel").pack(side="left")
        else:
            ttk.Label(frame, text=f"none (xwp/{found.name}.dbx names no model)", style="Muted.TLabel").pack(side="left")
        forged = icons.forged_model_path(self._files_dir, iid)
        if forged is not None and self._navigate is not None:
            ttk.Button(frame, text="Forged model ›", command=lambda: self._navigate(
                ("asset", "models", f"xwp/forge/{forged.stem}"))).pack(side="left", padx=(6, 0))
        ttk.Label(parent, style="Muted.TLabel", wraplength=760, justify="left", text=(
            "The battle looks the item ID without IID_ up in zdbx.cmp (xwp/<NAME>.dbx), whose Model block names "
            "the folder and model: a new item ID needs its own table there.")
        ).grid(row=row + 1, column=0, columnspan=columns, sticky="w")

    # -- layout ---------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        self._save_button = ttk.Button(top, text="Save FE8Data.bin", style="Accent.TButton", command=self._save,
                                       state="disabled")
        self._save_button.pack(side="left")
        self._revert_button = ttk.Button(top, text="Discard unsaved edits", command=self._revert, state="disabled")
        self._revert_button.pack(side="left", padx=(6, 0))
        self._excel_export_button = ttk.Button(top, text="Export Excel…", command=self._export_excel)
        self._excel_import_button = ttk.Button(top, text="Import Excel…", command=self._import_excel)
        self._status_label = ttk.Label(top, text="", style="Muted.TLabel")
        self._status_label.pack(side="left", padx=(10, 0))
        ttk.Label(top, text="Fields apply when you leave them; the build copies the saved file into system.cmp.",
                  style="Muted.TLabel").pack(side="right")

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._notebook.bind("<<NotebookTabChanged>>", lambda e: (self.flush(), self._sync_excel_buttons()), add="+")
        for key, title, noun in (("classes", "Classes", "classes"), ("items", "Items", "items"),
                                 ("skills", "Skills", "skills"), ("terrain", "Terrain", "terrain types"),
                                 ("chapters", "Chapters", "chapters"), ("general", "General", "")):
            tab = ttk.Frame(self._notebook, style="Page.TFrame")
            self._notebook.add(tab, text=title)
            if key == "general":
                body = ScrollFrame(tab, padding=(16, 8, 16, 16))
                body.pack(fill="both", expand=True)
                self._bodies[key] = body
                continue
            picker = TileBrowser(tab, noun, lambda i, k=key: self._show(k, i), **TILE_OPTIONS.get(key, {}))
            picker.pack(fill="both", expand=True)
            self._pickers[key] = picker
            if key in TAB_KINDS:
                ttk.Button(picker.actions, text="New…", command=lambda k=key: self._add_record(k)).pack(
                    side="left", padx=(14, 0))
                ttk.Button(picker.record_actions, text="Remove", command=lambda k=key: self._remove_record(k)).pack(
                    side="left", padx=(6, 0))
            elif key in FIXED_TABS:
                ttk.Label(picker.actions, text=FIXED_TABS[key], style="Muted.TLabel", wraplength=420,
                          justify="left").pack(side="left", padx=(14, 0))
            body = ScrollFrame(picker.detail, padding=(16, 8, 16, 16))
            body.pack(fill="both", expand=True)
            self._bodies[key] = body

    def _refresh_pickers(self) -> None:
        fe8 = self._fe8

        def unique(labels: list[str]) -> list[str]:
            seen: dict[str, int] = {}
            for label in labels:
                seen[label] = seen.get(label, 0) + 1
            return [f"{label}  #{i}" if seen[label] > 1 else label for i, label in enumerate(labels)]

        self._icons()  # re-reads icon.tpl when it changed, so a replaced icon redraws the tiles
        self._pickers["classes"].set_entries(
            unique([f"{self.class_name(c)}  ·  {c.jid or '?'}" for c in fe8.classes]),
            [f"{c.mjid} {c.aid}" for c in fe8.classes],
            [fe8data.class_category(c, fe8.classes) for c in fe8.classes], fe8data.CLASS_CATEGORIES)
        self._pickers["items"].set_entries(
            unique([f"{self.item_name(it)}  ·  {it.iid or '?'}" for it in fe8.items]),
            [it.miid or "" for it in fe8.items],
            [fe8data.item_category(it) for it in fe8.items], fe8data.ITEM_CATEGORIES,
            image=lambda i, callback: self._icon_tile(
                icons.ITEM_CELL, icons.ITEM_IMAGE, icons.item_cell(self._fe8.items[i].icon), callback),
            image_keys=[(it.icon, self._icon_stamp) for it in fe8.items])
        self._pickers["skills"].set_entries(
            unique([f"{self.skill_name(s)}  ·  {s.sid or '?'}" for s in fe8.skills]),
            [f"{s.msid} {s.japanese_name}" for s in fe8.skills],
            image=lambda i, callback: self._icon_tile(
                icons.SKILL_CELL, icons.SKILL_IMAGE, icons.skill_cell(self._fe8.skills[i].params[0]), callback),
            image_keys=[(s.params[0], self._icon_stamp) for s in fe8.skills])
        try:
            self._terrain_types = fe8data.read_terrain_types(self._data)
        except (KeyError, ValueError, struct.error):
            self._terrain_types = []
        self._pickers["terrain"].set_entries(
            unique([f"{self._terrain_name(t)}  ·  {t.name}" for t in self._terrain_types]))
        try:
            chapters = fe8data.read_chapter_data(self._data)
        except (KeyError, ValueError, struct.error):
            chapters = []
        self._pickers["chapters"].set_entries(
            unique([f"{self._text(c.title_key) or c.title_key or '(untitled)'}  ·  {c.script or '-'}  ·  id {c.chapter_id}"
                    for c in chapters]),
            [f"{c.map_name} {c.message}" for c in chapters])

    def _icon_tile(self, size: int, image_index: int, cell: Optional[int], callback: Callable) -> None:
        image = icons.cell_image(self._icons(), image_index, cell, size)
        if image is None:
            return
        backing = Image.new("RGBA", image.size, (96, 96, 96, 255))
        backing.alpha_composite(image)
        scale = TILE_IMAGE_SIZE / max(image.size)
        callback(ImageTk.PhotoImage(backing.resize(
            (round(image.width * scale), round(image.height * scale)), Image.NEAREST)))

    def _new_form(self, key: str, kind: str, index: int) -> tuple[_Form, ttk.Frame]:
        self._commit(self._forms[key])
        body = self._bodies[key]
        for child in body.body.winfo_children():
            child.destroy()
        body.scroll_top()
        form = _Form(self, kind, index)
        self._forms[key] = form
        return form, body.body

    def _show(self, key: str, index: int) -> None:
        {"classes": self._show_class, "items": self._show_item, "skills": self._show_skill,
         "terrain": self._show_terrain, "chapters": self._show_chapter}[key](index)

    # -- adding and removing records --------------------------------------------------------
    def _add_record(self, key: str) -> None:
        self.flush()
        picker = self._pickers[key]
        index = record_actions.add_record(self, self._session, TAB_KINDS[key], picker.labels,
                                          picker.current, source=self)
        if index is None:
            return
        self._on_session_changed(self)
        self._forms[key] = None
        self._refresh_pickers()
        picker.select(index)
        self._status_label.config(text="Added: save FE8Data.bin to keep it", style="Muted.TLabel")

    def _remove_record(self, key: str) -> None:
        self.flush()
        picker = self._pickers[key]
        index = picker.current
        if index is None:
            return
        label = picker.labels[index]
        if not record_actions.remove_record(self, self._session, self._project, TAB_KINDS[key], index, label,
                                            source=self):
            return
        self._on_session_changed(self)
        self._forms[key] = None
        self._refresh_pickers()
        if picker.labels:
            picker.select(min(index, len(picker.labels) - 1))
        self._status_label.config(text=f"Removed {label}: save FE8Data.bin to keep it", style="Muted.TLabel")

    # -- committing -------------------------------------------------------------
    def _commit(self, form: Optional[_Form]) -> None:
        """Write the form's changed fields to the session."""
        if form is None or self._forms.get(self._form_key(form)) is not form:
            return
        data, errors, failed = self._data, [], set()
        for field in form.fields:
            value = field.var.get()
            if value == field.shown:
                continue
            try:
                data = field.apply(data, value)
            except (ValueError, struct.error, OverflowError, IndexError) as exc:
                errors.append(f"{field.label}: {exc}")
                failed.add(id(field))
        if data != self._data:
            self._data = data
            self._session.changed(self)
            self._on_session_changed(self)
            if form.kind != "general":
                self._refresh_pickers()  # names and IDs show in the pickers
        for field in form.fields:
            if id(field) not in failed:
                try:
                    field.load()
                except (tk.TclError, IndexError):
                    pass
        try:
            if errors:
                self._status_label.config(text="Not applied - " + "; ".join(errors), style="Danger.TLabel")
            elif self._session.dirty:
                self._status_label.config(text="Unsaved changes", style="Muted.TLabel")
        except tk.TclError:
            pass

    def _form_key(self, form: _Form) -> str:
        return {"class": "classes", "item": "items", "skill": "skills", "terrain": "terrain", "chapter": "chapters",
                "general": "general"}[form.kind]

    def flush(self) -> None:
        """Apply whatever field still has the focus (a picker button or a
        tab change doesn't take it, so its FocusOut may not have run)."""
        for form in list(self._forms.values()):
            self._commit(form)

    # -- form building helpers ---------------------------------------------------------
    @staticmethod
    def _heading(parent, text: str, row: int, columns: int = 8) -> None:
        ttk.Label(parent, text=text, style="Subtitle.TLabel").grid(
            row=row, column=0, columnspan=columns, sticky="w", pady=(14, 4))

    def _pointer_combo(self, parent, prefix: str, width: int = 30,
                       name_hint: str = "NEW") -> tuple[ttk.Combobox, tk.StringVar]:
        var = tk.StringVar()
        options = sorted(self._labels_by_prefix.get(prefix, {}).keys())
        if prefix not in {"MJID", "MIID", "MSID", "MH_J", "MH_I", "MH_SKILL", "MT_"}:
            return ttk.Combobox(parent, textvariable=var, values=[""] + options, width=width), var
        self._texts = None  # another editor may have changed common.m
        texts = self._message_texts()
        labels = {f"{key} — {message_reference.preview(value)}": key
                  for key, value in sorted(texts.items()) if key.startswith(prefix)}
        box = ttk.Combobox(parent, textvariable=var, values=["", *labels, message_reference.CREATE_MESSAGE],
                           width=max(width, 42))
        last = [""]
        id_prefix = prefix if prefix.endswith("_") else prefix + "_"
        def remember(*_args):
            value = var.get()
            if value != message_reference.CREATE_MESSAGE:
                last[0] = labels.get(value, value)
        var.trace_add("write", remember)
        def selected(_event):
            value = var.get()
            if value == message_reference.CREATE_MESSAGE:
                var.set(last[0])
                initial = message_reference.suggested_id(id_prefix, name_hint, set(texts))
                dialog = message_reference.NewMessageDialog(self, initial)
                if dialog.result is None:
                    return "break"
                name, new_text = dialog.result
                if not name.startswith(id_prefix):
                    messagebox.showerror("Create message", f"ID must start with {id_prefix}.", parent=self)
                    return "break"
                try:
                    message_reference.create_message(self._project, name, new_text)
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Create message", str(exc), parent=self)
                    return "break"
                self._texts = None
                texts[name] = new_text
                labels[f"{name} — {message_reference.preview(new_text)}"] = name
                box.configure(values=["", *labels, message_reference.CREATE_MESSAGE])
                self._changelog.append(message_reference.common_path(self._project).name,
                                       f"Created message {name}")
                var.set(name)
                self.flush()
                return "break"
            var.set(labels.get(value, value))
        box.bind("<<ComboboxSelected>>", selected)
        return box, var

    def _message_texts(self) -> dict[str, str]:
        if self._texts is None:
            self._text(" ")
        return self._texts or {}

    def _message_preview(self, parent, var: tk.StringVar, row: int, column: int,
                         columns: int = 4) -> None:
        shown = tk.StringVar()
        def update(*_args):
            key = var.get()
            shown.set(self._text(key) or ("(message not found)" if key else ""))
        var.trace_add("write", update)
        update()
        ttk.Label(parent, textvariable=shown, style="Muted.TLabel", wraplength=420,
                  justify="left").grid(row=row, column=column, columnspan=columns,
                                       sticky="w", padx=(8, 0))

    def _hex_box(self, parent, form: _Form, kind: str, index: int, row: int, columns: int) -> None:
        size = fe8data.RECORD_TABLES[kind][1]
        self._heading(parent, "Whole record (hex)", row, columns)
        protected = sorted(fe8data.protected_record_words(self._data, kind, index))
        ttk.Label(parent, style="Muted.TLabel", wraplength=760, justify="left", text=(
            f"{size} bytes, 16 per line. Everything here can be changed except the pointer words at "
            + ", ".join(f"0x{o:02X}" for o in protected)
            + " (edit those through their fields). Applied when you leave the box or press Ctrl+Enter."
        )).grid(row=row + 1, column=0, columnspan=columns, sticky="w")
        text = tk.Text(parent, width=52, height=(size + 15) // 16, wrap="none", font=("Consolas", 10))
        text.grid(row=row + 2, column=0, columnspan=columns, sticky="w", pady=(4, 0))
        offsets = ttk.Label(parent, style="Muted.TLabel", font=("Consolas", 10), justify="left",
                            text="\n".join(f"+0x{o:02X}" for o in range(0, size, 16)))
        offsets.grid(row=row + 2, column=columns, sticky="nw", padx=(6, 0), pady=(6, 0))

        def read() -> str:
            raw = fe8data.record_bytes(self._data, kind, index)
            return "\n".join(raw[o:o + 16].hex(" ") for o in range(0, len(raw), 16))

        def apply(data: bytes, value: str) -> bytes:
            try:
                new = bytes.fromhex(" ".join(value.split()))
            except ValueError:
                raise ValueError("not valid hex") from None
            return fe8data.patch_record_bytes(data, kind, index, new)

        form.add(text, "Record bytes", _TextVar(text), read, apply, first=True)

    def _byte_row(self, parent, form: _Form, row: int, title: str, names: list[str],
                  read: Callable[[int], int], apply: Callable[[bytes, int, int], bytes],
                  low: int = 0, high: int = 255) -> None:
        ttk.Label(parent, text=title).grid(row=row + 1, column=0, sticky="w", padx=(0, 10))
        for i, name in enumerate(names):
            ttk.Label(parent, text=name, style="Muted.TLabel").grid(row=row, column=i + 1, sticky="w")
            var = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=6)
            entry.grid(row=row + 1, column=i + 1, sticky="w", padx=(0, 6), pady=1)
            form.add(entry, f"{title} {name}", var, lambda i=i: str(read(i)),
                     lambda data, v, i=i: apply(data, i, _number(v, low, high)))

    # -- classes ------------------------------------------------------------------------
    def _show_class(self, index: int) -> None:
        form, parent = self._new_form("classes", "class", index)
        cls = lambda: self._fe8.classes[index]  # noqa: E731 - always the reparsed record
        patch = fe8data.patch_class_field
        c = cls()
        ttk.Label(parent, text=self.class_name(c), style="Title.TLabel").grid(row=0, column=0, columnspan=9, sticky="w")
        ttk.Label(parent, text=f"{c.jid}  ·  class record {index}", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=9, sticky="w")
        row = 2
        self._heading(parent, "Identity and links", row)
        row += 1

        def pointer_row(label: str, field: str, prefix: str, note: str = "", link=None) -> None:
            nonlocal row
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
            box, var = self._pointer_combo(parent, prefix, name_hint=f"{c.jid}_{field}")
            box.grid(row=row, column=1, columnspan=4, sticky="w")
            form.add(box, label, var, lambda: getattr(cls(), field) or "",
                     lambda data, v: patch(data, index, field, _label_or_none(v)))
            if link is not None:
                ttk.Button(parent, text="Open ›", command=lambda: link(var.get().strip())).grid(
                    row=row, column=5, sticky="w", padx=(6, 0))
            if prefix in {"MJID", "MH_J"}:
                self._message_preview(parent, var, row, 6)
            elif note:
                ttk.Label(parent, text=note, style="Muted.TLabel").grid(row=row, column=6, columnspan=4, sticky="w",
                                                                        padx=(8, 0))
            row += 1

        ttk.Label(parent, text="Class ID (JID)").grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=32)
        entry.grid(row=row, column=1, columnspan=4, sticky="w")
        form.add(entry, "Class ID", var, lambda: cls().jid or "", lambda data, v: patch(data, index, "jid", v))
        ttk.Label(parent, text="characters, deployments and scripts name the class by it", style="Muted.TLabel").grid(
            row=row, column=6, columnspan=4, sticky="w", padx=(8, 0))
        row += 1
        pointer_row("Name key (MJID)", "mjid", "MJID", "the displayed class name")
        pointer_row("Description key", "hybrid_id", "MH_J")
        pointer_row("Promotes to / linked class", "promotes_to", "JID", link=self.select_class)
        pointer_row("Class model (AID)", "aid", "AID", "used by units whose character has none")
        pointer_row("Innate weapon", "innate_weapon", "IID", "laguz: the attack of the transformed unit",
                    link=self.select_item)

        self._heading(parent, "Weapon ranks", row)
        row += 1
        ttk.Label(parent, style="Muted.TLabel", wraplength=760, justify="left", text=(
            "- cannot use, * usable without a fixed rank, else the rank letter. A rank string no other class "
            "has is added to the file, so classes that shared the old one keep it.")).grid(
            row=row, column=0, columnspan=10, sticky="w")
        row += 1
        rank_frame = ttk.Frame(parent, style="Page.TFrame")
        rank_frame.grid(row=row, column=0, columnspan=10, sticky="w")
        rank_vars: list[tk.StringVar] = []
        rank_boxes = []
        for i, weapon in enumerate(fe8data.WEAPON_TYPE_NAMES):
            ttk.Label(rank_frame, text=weapon, style="Muted.TLabel").grid(row=0, column=i, sticky="w")
            var = tk.StringVar()
            box = ttk.Combobox(rank_frame, textvariable=var, values=list(fe8data.WEAPON_RANK_CHARS), width=3,
                               state="readonly")
            box.grid(row=1, column=i, sticky="w", padx=(0, 6))
            rank_vars.append(var)
            rank_boxes.append(box)

        class _Ranks:
            def get(self) -> str:
                return "".join(v.get() or "-" for v in rank_vars)

            def set(self, value: str) -> None:
                value = (value or "").ljust(len(rank_vars), "-")
                for v, ch in zip(rank_vars, value):
                    v.set(ch)

        form.add(rank_boxes, "Weapon ranks", _Ranks(), lambda: cls().weapon_ranks or "",
                 lambda data, v: patch(data, index, "weapon_ranks", v))
        row += 1

        self._heading(parent, "Innate skills", row)
        row += 1
        ttk.Label(parent, text="Every unit of this class has these.", style="Muted.TLabel").grid(
            row=row, column=0, columnspan=10, sticky="w")
        row += 1
        for i in range(5):
            ttk.Label(parent, text=f"Skill {i + 1}").grid(row=row, column=0, sticky="w", pady=1)
            box, var = self._pointer_combo(parent, "SID")
            box.grid(row=row, column=1, columnspan=4, sticky="w")
            form.add(box, f"Skill {i + 1}", var, lambda i=i: cls().skills[i] or "",
                     lambda data, v, i=i: patch(data, index, f"skill{i}", _label_or_none(v)))
            ttk.Button(parent, text="Open ›", command=lambda v=var: self.select_skill(v.get().strip())).grid(
                row=row, column=5, sticky="w", padx=(6, 0))
            row += 1

        self._heading(parent, "Movement and build", row)
        row += 1
        for label, field, note in (("Movement", "movement", ""), ("Build (Con)", "build", ""),
                                   ("Weight", "weight", ""),
                                   ("Skill capacity", "skill_capacity", "the capacity skills fill (0-255)"),
                                   ("Vision", "vision", "fog-of-war sight range; a Torch adds to it")):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=1)
            var = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=6)
            entry.grid(row=row, column=1, sticky="w")
            offset = fe8data.CLASS_BYTE_FIELDS[field]
            form.add(entry, label, var,
                     lambda o=offset: str(fe8data.record_bytes(self._data, "class", index)[o]),
                     lambda data, v, f=field: patch(data, index, f, _number(v, 0, 255)))
            if note:
                ttk.Label(parent, text=note, style="Muted.TLabel").grid(row=row, column=2, columnspan=6, sticky="w",
                                                                        padx=(8, 0))
            row += 1
        ttk.Label(parent, text="Movement type").grid(row=row, column=0, sticky="w", pady=1)
        type_names = [f"{i}: {name}" for i, name in enumerate(fe8data.MOVEMENT_TYPE_NAMES)]
        var = tk.StringVar()
        box = ttk.Combobox(parent, textvariable=var, values=type_names, state="readonly", width=34)
        box.grid(row=row, column=1, columnspan=5, sticky="w")
        form.add(box, "Movement type", var,
                 lambda: type_names[cls().movement_type] if cls().movement_type < len(type_names)
                 else str(cls().movement_type),
                 lambda data, v: patch(data, index, "movement_type", int(v.split(":")[0])))
        ttk.Label(parent, text="picks the terrain cost column (Terrain tab)", style="Muted.TLabel").grid(
            row=row, column=6, columnspan=4, sticky="w", padx=(8, 0))
        row += 1

        self._heading(parent, "Stats", row)
        row += 1
        stats = fe8data.STAT_NAMES
        stats_frame = ttk.Frame(parent)
        stats_frame.grid(row=row, column=0, columnspan=10, sticky="w")
        stats_frame.columnconfigure(0, minsize=132)
        for column in range(1, len(stats) + 1):
            stats_frame.columnconfigure(column, minsize=76)
        self._byte_row(stats_frame, form, 0, "Caps", stats, lambda i: cls().stat_caps[i],
                       lambda d, i, v: patch(d, index, f"cap{i}", v))
        self._byte_row(stats_frame, form, 2, "Base stats", stats, lambda i: cls().base_stats[i],
                       lambda d, i, v: patch(d, index, f"base_stat{i}", v))
        self._byte_row(stats_frame, form, 4, "Growth %", stats, lambda i: cls().growths[i],
                       lambda d, i, v: patch(d, index, f"growth{i}", v))
        self._byte_row(stats_frame, form, 6, "Growth modifiers", stats, lambda i: cls().growth_modifiers[i],
                       lambda d, i, v: patch(d, index, f"growth_modifier{i}", v), low=-128, high=127)
        row += 1
        ttk.Label(parent, style="Muted.TLabel", wraplength=760, justify="left", text=(
            "Base stats add to a character's personal stats (Luck base is unused). "
            "Growth % is the class rate used for automatic leveling; it is not added to a character's personal rate. "
            "Growth modifiers add signed percentage points to the personal growth of characters in this class "
            "during level ups. For example, 45% personal growth plus a +5 class modifier becomes 50%.")).grid(
            row=row, column=0, columnspan=10, sticky="w", pady=(4, 0))
        row += 1
        row = self._token_checks(parent, form, row, 10, "Categories", "categories", fe8data.CLASS_CATEGORY_SLOTS,
                                 fe8data.ITEM_CATEGORY_TOKENS, cls, index, fe8data.patch_class_field)
        ttk.Label(parent, style="Muted.TLabel", wraplength=760, justify="left", text=(
            "What the class is: weapons effective against a category hit it harder, and some skills and items "
            "check it.")).grid(row=row, column=0, columnspan=10, sticky="w")
        row += 1

    # -- items ------------------------------------------------------------------------
    def _show_item(self, index: int) -> None:
        form, parent = self._new_form("items", "item", index)
        item = lambda: self._fe8.items[index]  # noqa: E731
        patch = fe8data.patch_item_field
        it = item()
        columns = 11
        ttk.Label(parent, text=self.item_name(it), style="Title.TLabel").grid(
            row=0, column=0, columnspan=columns, sticky="w")
        ttk.Label(parent, text=f"{it.iid}  ·  item record {index}", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=columns, sticky="w")
        row = 2

        def note(text: str, style: str = "Muted.TLabel") -> None:
            nonlocal row
            ttk.Label(parent, text=text, style=style, wraplength=760, justify="left").grid(
                row=row, column=0, columnspan=columns, sticky="w", pady=(2, 2))
            row += 1

        def labelled(label: str, widget, field_note: str = "") -> None:
            nonlocal row
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 10))
            widget.grid(row=row, column=1, columnspan=4, sticky="w")
            if field_note:
                ttk.Label(parent, text=field_note, style="Muted.TLabel").grid(
                    row=row, column=5, columnspan=columns - 5, sticky="w", padx=(8, 0))
            row += 1

        def number(label: str, field: str, low: int, high: int, field_note: str = "") -> None:
            var = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=7)
            form.add(entry, label, var, lambda: str(getattr(item(), field)),
                     lambda data, v: patch(data, index, field, _number(v, low, high)))
            labelled(label, entry, field_note)
            return var

        def pointer(label: str, field: str, prefix: str, field_note: str = "") -> None:
            box, var = self._pointer_combo(parent, prefix, name_hint=f"{it.iid}_{field}")
            form.add(box, label, var, lambda: getattr(item(), field) or "",
                     lambda data, v: patch(data, index, field, _label_or_none(v)))
            labelled(label, box, "" if prefix in {"MIID", "MH_I"} else field_note)
            if prefix in {"MIID", "MH_I"}:
                self._message_preview(parent, var, row - 1, 5, columns - 5)

        def choice(label: str, field: str, options: list, field_note: str = "") -> None:
            shown = {token: text for token, text in options}
            tokens = {text: token for token, text in options}
            var = tk.StringVar()
            box = ttk.Combobox(parent, textvariable=var, values=[text for _, text in options], state="readonly",
                               width=30)

            def read() -> str:
                value = getattr(item(), field)
                return shown.get(value, value or "")

            form.add(box, label, var, read, lambda data, v: patch(data, index, field, tokens.get(v, v) or None))
            labelled(label, box, field_note)

        self._heading(parent, "Identity and text", row, columns)
        row += 1
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=32)
        form.add(entry, "Item ID", var, lambda: item().iid or "", lambda data, v: patch(data, index, "iid", v))
        labelled("Item ID (IID)", entry, "deployments, shops and scripts name the item by it")
        pointer("Name key (MIID)", "miid", "MIID", self._text(it.miid))
        pointer("Description key (MH_I)", "help_key", "MH_I")
        description = self._text(it.help_key)
        if description:
            note(description, "TLabel")

        self._heading(parent, "Type and rank", row, columns)
        row += 1
        types = [(token, f"{token} · {name}") for token, name in fe8data.ITEM_WEAPON_TYPES]
        choice("Weapon type", "weapon_type", types, "the rank it trains and who can equip it")
        choice("Attack type", "attack_type", types, "Fire, Thunder, Wind and Light/staff hit with Mag against Res")
        choice("Rank needed", "rank", [(None, "(none)")] + [
            (token, f"{token} · {exp} weapon EXP" if exp else f"{token} · none") for token, exp in fe8data.ITEM_RANKS])
        number("Weapon EXP per use", "weapon_exp", 0, 255)

        self._heading(parent, "Icon and model", row, columns)
        row += 1
        icon_var = number("Icon", "icon", 0, 255, "cell icon + 96 of window/icon.tpl's first image")

        def sharing() -> str:
            icon = item().icon
            others = [self.item_name(o) for o in self._fe8.items if o.icon == icon and o.index != index]
            return ("Also the icon of " + ", ".join(others) + ": editing it changes theirs too.") if others else ""

        refresh = self._icon_row(parent, row, columns, icons.ITEM_CELL, icons.ITEM_IMAGE,
                                 lambda: icons.item_cell(item().icon), lambda: f"item:{item().icon}", sharing)
        icon_var.trace_add("write", lambda *_: refresh())
        row += 1
        found = icons.weapon_model(self._files_dir, it.iid, self._weapon_tables())
        if it.weapon_type in MODEL_WEAPON_TYPES or (found is not None and found.folder):
            self._model_row(parent, row, columns, it.iid)
            row += 2

        self._heading(parent, "Combat and price", row, columns)
        row += 1
        combat = [("Might", "might"), ("Hit %", "hit"), ("Crit %", "crit"), ("Weight", "weight"), ("Uses", "uses"),
                  ("Min range", "min_range"), ("Max range", "max_range")]
        self._byte_row(parent, form, row, "Values", [label for label, _ in combat],
                       lambda i: getattr(item(), combat[i][1]),
                       lambda d, i, v: patch(d, index, combat[i][1], v))
        row += 2
        note("Max range 255 means Mag / 2 (the long-range staves).")
        number("Cost per use", "cost", 0, 0xFFFF, f"shop price = cost × uses (now {it.cost * it.uses})")

        properties = dict(fe8data.ITEM_PROPERTY_TOKENS)
        properties.update({t: "No effect: the game ignores it" for t in fe8data.ITEM_IGNORED_PROPERTY_TOKENS})
        row = self._token_checks(parent, form, row, columns, "Properties", "properties",
                                 fe8data.ITEM_PROPERTY_SLOTS, properties, item, index)
        row = self._token_checks(parent, form, row, columns, "Effective against", "categories",
                                 fe8data.ITEM_CATEGORY_SLOTS, fe8data.ITEM_CATEGORY_TOKENS, item, index)

        self._heading(parent, "Effects", row, columns)
        row += 1
        pointer("Use / spell effect", "effect", "EID", "staff, tome and consumable effect")
        pointer("Weapon effect", "weapon_effect", "EID", "EID_..._WP")
        colors = [(i, f"{i}: {name}  (#{rgba >> 8:06X})") for i, (name, rgba) in enumerate(fe8data.ITEM_TRAIL_COLORS)]
        var = tk.StringVar()
        box = ttk.Combobox(parent, textvariable=var, values=[text for _, text in colors], state="readonly", width=30)
        form.add(box, "Trail colour", var, lambda: dict(colors).get(item().trail_color, str(item().trail_color)),
                 lambda data, v: patch(data, index, "trail_color", int(v.split(":")[0])))
        labelled("Attack trail colour", box, "a forged weapon uses its forge colour instead")

        self._heading(parent, "Bonuses while equipped", row, columns)
        row += 1
        note("Added to the unit's stats while the item is equipped; a stat booster (Energy Drop, Boots, ...) "
             "gives them for good. Negative values are allowed.")
        self._byte_row(parent, form, row, "Stats", fe8data.ITEM_STAT_BONUS_NAMES, lambda i: item().stat_bonus[i],
                       lambda d, i, v: patch(d, index, f"stat_bonus{i}", v), low=-128, high=127)
        row += 2
        self._byte_row(parent, form, row, "Growth %", fe8data.STAT_NAMES, lambda i: item().growth_bonus[i],
                       lambda d, i, v: patch(d, index, f"growth_bonus{i}", v), low=-128, high=127)
        row += 2
        note("Growth modifiers are added to the unit's growth rates while the weapon is equipped. "
             "The record's last two bytes are alignment padding the game never reads.")

    def _token_checks(self, parent, form: _Form, row: int, columns: int, title: str, field: str, slots: int,
                      tokens: dict, item: Callable, index: int, patch: Callable = fe8data.patch_item_field) -> int:
        """One check box per token of a record's token slots (item properties
        and categories, class categories); returns the next free grid row."""
        self._heading(parent, f"{title} (up to {slots})", row, columns)
        frame = ttk.Frame(parent, style="Page.TFrame")
        frame.grid(row=row + 1, column=0, columnspan=columns, sticky="w")
        order = list(tokens)
        checks: dict[str, tk.BooleanVar] = {}
        buttons = []
        for i, (token, text) in enumerate(tokens.items()):
            var = tk.BooleanVar()
            button = ttk.Checkbutton(frame, text=f"{token} - {text}", variable=var)
            button.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 18), pady=1)
            checks[token] = var
            buttons.append(button)

        def canonical(values) -> str:
            return ",".join([t for t in order if t in values] + sorted(t for t in values if t not in order))

        class _Tokens:
            """The checked tokens as one string; tokens without a box are kept."""
            extras: list = []

            def get(self) -> str:
                return canonical([t for t, v in checks.items() if v.get()] + self.extras)

            def set(self, value: str) -> None:
                chosen = [t for t in value.split(",") if t]
                for token, v in checks.items():
                    v.set(token in chosen)
                self.extras = [t for t in chosen if t not in checks]

        form.add(buttons, title, _Tokens(), lambda: canonical([t for t in getattr(item(), field) if t]),
                 lambda data, v: patch(data, index, field, [t for t in v.split(",") if t]))
        return row + 2

    # -- skills ------------------------------------------------------------------------
    def _show_skill(self, index: int) -> None:
        form, parent = self._new_form("skills", "skill", index)
        skill = lambda: self._fe8.skills[index]  # noqa: E731
        s = skill()
        ttk.Label(parent, text=self.skill_name(s), style="Title.TLabel").grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(parent, text=f"{s.sid}  ·  {s.japanese_name or ''}  ·  skill record {index}",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=6, sticky="w")
        row = 2
        self._heading(parent, "Name and description", row, 6)
        row += 1

        def text_row(label: str, field: str, note: str = "", prefix: Optional[str] = None) -> None:
            nonlocal row
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=1)
            if prefix:
                widget, var = self._pointer_combo(parent, prefix, name_hint=f"{s.sid}_{field}")
            else:
                var = tk.StringVar()
                widget = ttk.Entry(parent, textvariable=var, width=32)
            widget.grid(row=row, column=1, columnspan=4, sticky="w")
            form.add(widget, label, var, lambda: getattr(skill(), field) or "",
                     lambda data, v: fe8data.patch_skill_field(data, index, field, v.strip() if field == "sid"
                                                               else _label_or_none(v)))
            if prefix == "MSID":
                self._message_preview(parent, var, row, 5, 1)
            elif note:
                ttk.Label(parent, text=note, style="Muted.TLabel").grid(row=row, column=5, sticky="w", padx=(8, 0))
            row += 1

        text_row("Skill ID (SID)", "sid", "characters, classes and scripts name the skill by it")
        text_row("Japanese name", "japanese_name", "internal name, never shown")
        text_row("Menu name key (MSID)", "msid", prefix="MSID")
        text_row("Help key", "help_key", "text key in common.m")
        text_row("Second help key", "help2_key")
        text_row("Effect (EID)", "effect", "played when the skill triggers", prefix="EID")
        descriptions = self._descriptions()
        text = "\n\n".join(t for t in (descriptions.get(s.help_key or ""), descriptions.get(s.help2_key or "")) if t)
        ttk.Label(parent, text=text or "(no player-facing description)", wraplength=700, justify="left").grid(
            row=row, column=0, columnspan=6, sticky="w", pady=(6, 0))
        row += 1
        ttk.Label(parent, style="Muted.TLabel", text=f"Text keys {s.help_key or '-'} / {s.help2_key or '-'} "
                                                      "in system.cmp's common.m.").grid(
            row=row, column=0, columnspan=6, sticky="w")
        row += 1
        chant = fe8data.chant_stat_name(self._fe8.skills, s)
        self._heading(parent, "Who can have it", row, 6)
        row += 1
        ttk.Label(parent, text="Restricted to").grid(row=row, column=0, sticky="w", pady=1)
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=60)
        entry.grid(row=row, column=1, columnspan=5, sticky="w")
        form.add(entry, "Restricted to", var, lambda: ", ".join(skill().restricted_to),
                 lambda data, v: fe8data.patch_skill_field(data, index, "restricted_to",
                                                           [t for t in v.replace(",", " ").split() if t]))
        row += 1
        ttk.Label(parent, text="PID_ and JID_ labels, separated by commas; empty: anyone can have it.",
                  style="Muted.TLabel").grid(row=row, column=1, columnspan=5, sticky="w")
        row += 1
        ttk.Label(parent, text="Taught by scroll").grid(row=row, column=0, sticky="w", pady=1)
        box, var = self._pointer_combo(parent, "IID")
        box.grid(row=row, column=1, columnspan=4, sticky="w")
        form.add(box, "Taught by", var, lambda: (skill().skill_items or [""])[0],
                 lambda data, v: fe8data.patch_skill_field(data, index, "skill_items", [v.strip()] if v.strip() else []))
        row += 1
        if chant:
            ttk.Label(parent, text=f"Chant boosts: {chant}", wraplength=700, justify="left").grid(
                row=row, column=0, columnspan=6, sticky="w")
            row += 1
        self._heading(parent, "Icon", row, 6)
        row += 1
        ttk.Label(parent, text="Icon").grid(row=row, column=0, sticky="w", pady=2)
        icon_var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=icon_var, width=6)
        entry.grid(row=row, column=1, sticky="w")
        form.add(entry, "Icon", icon_var, lambda: str(skill().params[0]),
                 lambda data, v: fe8data.patch_skill_field(data, index, "param0", _number(v, 0, 255)))
        ttk.Label(parent, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "cell icon - 1 of window/icon.tpl's second image; 0: no icon, and the skill is left out of the "
            "lists of skills a unit can learn")).grid(row=row, column=2, columnspan=4, sticky="w", padx=(8, 0))
        row += 1

        def sharing() -> str:
            icon = skill().params[0]
            others = [self.skill_name(o) for o in self._fe8.skills if icon and o.params[0] == icon and o.index != index]
            return ("Also the icon of " + ", ".join(others) + ".") if others else ""

        refresh = self._icon_row(parent, row, 6, icons.SKILL_CELL, icons.SKILL_IMAGE,
                                 lambda: icons.skill_cell(skill().params[0]), lambda: f"skill:{skill().params[0]}",
                                 sharing)
        icon_var.trace_add("write", lambda *_: refresh())
        row += 1
        self._heading(parent, "Parameters", row, 6)
        row += 1
        for i, label in enumerate(SKILL_PARAM_LABELS, start=1):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=6)
            entry.grid(row=row, column=1, sticky="w")
            form.add(entry, label, var, lambda i=i: str(skill().params[i]),
                     lambda data, v, i=i: fe8data.patch_skill_field(data, index, f"param{i}", _number(v, 0, 255)))
            row += 1
        ttk.Label(parent, style="Muted.TLabel", wraplength=700, justify="left", text=(
            "Skill lists show the capacity cost and grey the skill out when the unit's class capacity, minus "
            "the skills it already has, is lower." + (f" Triggering plays {s.effect}." if s.effect else ""))).grid(
            row=row, column=0, columnspan=6, sticky="w")
        row += 1
        self._hex_box(parent, form, "skill", index, row, 6)

    # -- terrain ------------------------------------------------------------------------
    def _show_terrain(self, index: int) -> None:
        form, parent = self._new_form("terrain", "terrain", index)
        t = self._terrain_types[index]

        def current() -> fe8data.TerrainType:
            return fe8data.read_terrain_types(self._data)[index]

        ttk.Label(parent, text=self._terrain_name(t), style="Title.TLabel").grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(parent, text=f"{t.name}  ·  terrain type {index}", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=6, sticky="w")
        users = fe8data.terrain_block_users(self._data, index)
        shared = [self._terrain_types[i] for i in users if i != index]
        if shared:
            note = ("Shares its stats with " + ", ".join(self._terrain_name(o) for o in shared)
                    + ": edits here change them too.")
            ttk.Label(parent, text=note, style="Warn.TLabel", wraplength=720, justify="left").grid(
                row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
            ttk.Button(parent, text="Give this type its own stats",
                       command=lambda: self._separate_terrain(index)).grid(row=3, column=0, columnspan=3, sticky="w",
                                                                           pady=(4, 0))
        else:
            ttk.Label(parent, text="Has its own stats block.", style="Muted.TLabel").grid(
                row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))

        ttk.Label(parent, text="Name").grid(row=4, column=0, sticky="w", pady=(10, 1))
        name_var = tk.StringVar()
        name_entry = ttk.Entry(parent, textvariable=name_var, width=24)
        name_entry.grid(row=4, column=1, columnspan=3, sticky="w", pady=(10, 1))
        form.add(name_entry, "Terrain name", name_var, lambda: current().name,
                 lambda data, v: fe8data.patch_terrain_names(data, index, name=v))
        ttk.Label(parent, text="map tiles name their terrain by this string: rename it in the maps too",
                  style="Muted.TLabel").grid(row=4, column=4, columnspan=4, sticky="w", padx=(8, 0), pady=(10, 1))
        ttk.Label(parent, text="Display name key").grid(row=5, column=0, sticky="w", pady=1)
        key_box, key_var = self._pointer_combo(parent, "MT_", name_hint=t.name)
        key_box.grid(row=5, column=1, columnspan=3, sticky="w", pady=1)
        form.add(key_box, "Terrain name key", key_var, lambda: current().name_key,
                 lambda data, v: fe8data.patch_terrain_names(data, index, name_key=v))
        self._message_preview(parent, key_var, 5, 4)

        def byte_apply(position: int, low: int, high: int):
            def apply(data: bytes, value: str) -> bytes:
                block = bytearray(fe8data.terrain_stats_block(fe8data.read_terrain_types(data)[index]))
                block[position] = _number(value, low, high) & 0xFF
                return fe8data.patch_terrain_stats(data, index, bytes(block))
            return apply

        row = 6
        self._heading(parent, "Bonuses", row, 6)
        row += 1
        for r, (labels, reads, base) in enumerate((
                (("Avoid", "Defense", "Resistance"),
                 (lambda: current().avoid, lambda: current().defense, lambda: current().resistance), 0),
                (("Avoid (flag 4)", "Defense (flag 4)", "Res. (flag 4)"),
                 tuple(lambda k=k: current().alt_bonus[k] for k in range(3)), 3))):
            for k, (label, read) in enumerate(zip(labels, reads)):
                ttk.Label(parent, text=label).grid(row=row + r, column=2 * k, sticky="w", padx=(0 if k == 0 else 12, 4))
                var = tk.StringVar()
                entry = ttk.Entry(parent, textvariable=var, width=6)
                entry.grid(row=row + r, column=2 * k + 1, sticky="w", pady=1)
                form.add(entry, label, var, lambda read=read: str(read()), byte_apply(base + k, -128, 127))
        row += 2
        for k, (label, read, position) in enumerate((("Heal % per turn", lambda: current().heal, 6),
                                                     ("Object tile (0/1)", lambda: current().flag7, 7))):
            ttk.Label(parent, text=label).grid(row=row, column=2 * k, sticky="w", padx=(0 if k == 0 else 12, 4))
            var = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=6)
            entry.grid(row=row, column=2 * k + 1, sticky="w", pady=1)
            form.add(entry, label, var, lambda read=read: str(read()), byte_apply(position, 0, 255))
        row += 1
        self._heading(parent, "Movement cost per movement type (255 = impassable)", row, 6)
        row += 1
        for i, name in enumerate(fe8data.MOVEMENT_TYPE_NAMES):
            r, c = divmod(i, 3)
            ttk.Label(parent, text=f"{i}: {name}").grid(row=row + r, column=2 * c, sticky="w",
                                                         padx=(0 if c == 0 else 12, 4))
            var = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=5)
            entry.grid(row=row + r, column=2 * c + 1, sticky="w", pady=1)
            form.add(entry, name, var, lambda i=i: str(current().move_costs[i]), byte_apply(8 + i, 0, 255))

    def _separate_terrain(self, index: int) -> None:
        self._commit(self._forms["terrain"])
        t = fe8data.read_terrain_types(self._data)[index]
        self._data = fe8data.patch_terrain_stats(self._data, index, fe8data.terrain_stats_block(t), own_block=True)
        self._session.changed(self)
        self._on_session_changed(self)
        self._status_label.config(text=f"{self._terrain_name(t)} has its own stats now", style="Muted.TLabel")
        self._terrain_types = fe8data.read_terrain_types(self._data)
        self._show_terrain(index)

    # -- chapters ------------------------------------------------------------------------
    def _show_chapter(self, index: int) -> None:
        form, parent = self._new_form("chapters", "chapter", index)
        chapter = lambda: fe8data.read_chapter_data(self._data)[index]  # noqa: E731
        patch = fe8data.patch_chapter_field
        c = chapter()
        columns = 8
        ttk.Label(parent, text=self._text(c.title_key) or c.title_key or "(untitled)", style="Title.TLabel").grid(
            row=0, column=0, columnspan=columns, sticky="w")
        ttk.Label(parent, text=f"chapter id {c.chapter_id}  ·  chapter record {index}", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=columns, sticky="w")
        row = 2

        def text_row(label: str, field: str, read: Callable[[], Optional[str]], note: str = "",
                     prefix: Optional[str] = None) -> None:
            nonlocal row
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=1, padx=(0, 10))
            if prefix:
                widget, var = self._pointer_combo(parent, prefix)
            else:
                var = tk.StringVar()
                widget = ttk.Entry(parent, textvariable=var, width=32)
            widget.grid(row=row, column=1, columnspan=3, sticky="w")
            form.add(widget, label, var, lambda: read() or "", lambda data, v: patch(data, index, field, v))
            if note:
                ttk.Label(parent, text=note, style="Muted.TLabel", wraplength=420, justify="left").grid(
                    row=row, column=4, columnspan=columns - 4, sticky="w", padx=(8, 0))
            row += 1

        self._heading(parent, "Identity and files", row, columns)
        row += 1
        text_row("Title key", "title_key", lambda: chapter().title_key, self._text(c.title_key) or "MCT_ text key")
        ttk.Label(parent, text="Chapter id").grid(row=row, column=0, sticky="w", pady=1)
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=6)
        entry.grid(row=row, column=1, sticky="w")
        form.add(entry, "Chapter id", var, lambda: str(chapter().chapter_id),
                 lambda data, v: patch(data, index, "chapter_id", _number(v, 0, 255)))
        ttk.Label(parent, text="scripts change to a chapter by this id; 90 and up are the trial maps",
                  style="Muted.TLabel").grid(row=row, column=4, columnspan=columns - 4, sticky="w", padx=(8, 0))
        row += 1
        text_row("Map", "map_name", lambda: chapter().map_name, "zmap/<name>/; its battle scenes: the chapter page")
        text_row("Script", "script", lambda: chapter().script, "Scripts/<name>.cmb")
        text_row("Message file", "message", lambda: chapter().message, "Mess/<name>.m; empty: none")
        text_row("Map music", "bgm", lambda: chapter().bgm)

        self._heading(parent, "Objectives (text keys)", row, columns)
        row += 1
        slots = ("Goal", "Unused slot", "Defeat condition", "Goal, second line")
        for k, label in enumerate(slots):
            text_row(label, f"objective{k}", lambda k=k: chapter().objectives[k], self._text(c.objectives[k]))
        for mode, field in (("Hard", "hard_objective"), ("Maniac", "maniac_objective")):
            for k, slot in enumerate((0, 1, 3)):
                text_row(f"{mode}: {slots[slot].lower()}", f"{field}{k}",
                         lambda k=k, a=f"{field}s": getattr(chapter(), a)[k], "empty: the Normal text")

        self._heading(parent, "Scenes", row, columns)
        row += 1
        text_row("Base background", "base_background", lambda: chapter().base_background, "RID_ of the base screen")
        text_row("Conversation background", "talk_background", lambda: chapter().talk_background,
                 "default background of the chapter's conversations")
        text_row("Class-change scene map", "scene_map", lambda: chapter().scene_map)
        text_row("Class-change scene sky", "scene_sky", lambda: chapter().scene_sky, "a Battle scenes sky name")

        self._heading(parent, "Enemy levels and trial grades", row, columns)
        row += 1
        self._byte_row(parent, form, row, "Enemy levels +", list(fe8data.DIFFICULTY_NAMES),
                       lambda i: chapter().enemy_bonus_levels[i],
                       lambda d, i, v: patch(d, index, f"enemy_bonus_level{i}", v))
        row += 2
        ttk.Label(parent, style="Muted.TLabel", wraplength=760, justify="left", text=(
            "Levels added to auto-levelled enemies on each difficulty. The grades below only matter on the trial "
            "maps: the most turns and units lost, and the fewest kills, for grades A to D.")).grid(
            row=row, column=0, columnspan=columns, sticky="w")
        row += 1
        grades = ["A", "B", "C", "D"]
        for title, attr, field in (("Turns", "trial_turn_grades", "trial_turn_grade"),
                                   ("Units lost", "trial_loss_grades", "trial_loss_grade"),
                                   ("Kills", "trial_score_grades", "trial_score_grade")):
            self._byte_row(parent, form, row, title, grades, lambda i, a=attr: getattr(chapter(), a)[i],
                           lambda d, i, v, f=field: patch(d, index, f"{f}{i}", v))
            row += 2
        self._hex_box(parent, form, "chapter", index, row, columns)

    # -- general ------------------------------------------------------------------------------
    def _show_general(self) -> None:
        if "general" not in self._bodies or not self._session.available:
            return
        form, parent = self._new_form("general", "general", 0)
        columns = 6
        row = 0
        self._heading(parent, "Difficulty constants", row, columns)
        row += 1
        for d, name in enumerate(fe8data.DIFFICULTY_NAMES):
            ttk.Label(parent, text=name, style="Muted.TLabel").grid(row=row, column=d + 1, sticky="w")
        row += 1
        for name, _reader in fe8data.GAME_DATA_ROWS:
            ttk.Label(parent, text=GAME_DATA_LABELS.get(name, name)).grid(row=row, column=0, sticky="w", pady=1,
                                                                          padx=(0, 10))
            for d in range(len(fe8data.DIFFICULTY_NAMES)):
                var = tk.StringVar()
                entry = ttk.Entry(parent, textvariable=var, width=6)
                entry.grid(row=row, column=d + 1, sticky="w", padx=(0, 6), pady=1)
                form.add(entry, f"{GAME_DATA_LABELS.get(name, name)} ({fe8data.DIFFICULTY_NAMES[d]})", var,
                         lambda n=name, d=d: str(fe8data.read_game_data(self._data)[n][d]),
                         lambda data, v, n=name, d=d: fe8data.patch_game_data(data, n, d, _number(v, 0, 255)))
            row += 1
        ttk.Label(parent, style="Muted.TLabel", wraplength=760, justify="left", text=(
            "One byte per difficulty, read by the EXP, growth and critical formulas (MAIN_DOL_NOTES.md, "
            "\"GameData accessor family\").")).grid(row=row, column=0, columnspan=columns, sticky="w")
        row += 1

        def lines_box(title: str, note: str, read: Callable[[], list], write: Callable[[bytes, list], bytes],
                      first: int, names: Callable[[Optional[str]], str] = lambda value: "") -> None:
            """One value per line, numbered from ``first`` in a column beside it."""
            nonlocal row
            self._heading(parent, title, row, columns)
            ttk.Label(parent, text=note, style="Muted.TLabel", wraplength=760, justify="left").grid(
                row=row + 1, column=0, columnspan=columns, sticky="w")
            values = read()
            frame = ttk.Frame(parent, style="Page.TFrame")
            frame.grid(row=row + 2, column=0, columnspan=columns, sticky="w", pady=(4, 0))
            height = len(values) + 3  # room to add lines without scrolling
            text = tk.Text(frame, width=34, height=height, wrap="none", font=("Consolas", 10))
            text.pack(side="left")
            side = tk.Text(frame, width=34, height=height, wrap="none", font=("Consolas", 10), borderwidth=0,
                           highlightthickness=0, background=theme.color("bg"), foreground=theme.color("muted"))
            side.pack(side="left", padx=(8, 0))

            def number(*_args) -> None:
                lines = text.get("1.0", "end-1c").splitlines()
                side.configure(state="normal")
                side.delete("1.0", "end")
                side.insert("1.0", "\n".join(f"{first + i:>3}  {names(None if v.strip() in ('', '-') else v.strip())}"
                                             for i, v in enumerate(lines)))
                side.configure(state="disabled")

            text.bind("<KeyRelease>", number, add="+")
            form.add(text, title, _TextVar(text), lambda: "\n".join(v or "-" for v in read()),
                     lambda data, v: write(data, [None if line.strip() in ("", "-") else line.strip()
                                                  for line in v.splitlines()]))
            number()
            row += 3

        keys = lambda: fe8data.read_group_names(self._data)  # noqa: E731
        lines_box("Army groups", "One MG_ army-name key per line, from group 1 (group 0 has none; '-' for none). "
                  "Deployments name groups by number: add new ones at the end. Applied when you leave the box "
                  "or press Ctrl+Enter.", lambda: keys()[1:],
                  lambda data, v: fe8data.write_group_names(data, [None] + v), 1,
                  lambda key: fe8data.GROUP_KEY_NAMES.get(key, self._text(key)) if key else "(none)")
        lines_box("Battle skies", "One sky name per map weather id, from id 0 ('-' for none). A map's weather id "
                  "picks the sky drawn behind its battles.", lambda: fe8data.read_battle_skies(self._data),
                  fe8data.write_battle_skies, 0)

        self._heading(parent, "File information", row, columns)
        row += 1
        head = lambda: fe8data.read_database_head(self._data)  # noqa: E731
        for k, label in enumerate(("Build time", "Author")):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=1)
            var = tk.StringVar()
            entry = ttk.Entry(parent, textvariable=var, width=30)
            entry.grid(row=row, column=1, columnspan=3, sticky="w")
            form.add(entry, label, var, lambda k=k: head()[k] or "",
                     lambda data, v, k=k: fe8data.patch_database_head(
                         data, *(v if i == k else fe8data.read_database_head(data)[i] for i in range(2))))
            row += 1
        ttk.Label(parent, text="Printed to the debug console when the game loads the file; no effect in game.",
                  style="Muted.TLabel").grid(row=row, column=0, columnspan=columns, sticky="w")

    def _excel_only(self) -> str | None:
        tab = self._notebook.select()
        if not tab:
            return None
        index = self._notebook.index(tab)
        return {TAB_KEYS.index("items"): "Items", TAB_KEYS.index("terrain"): "Terrain"}.get(index)

    def _sync_excel_buttons(self) -> None:
        if self._excel_only() is None:
            self._excel_export_button.pack_forget()
            self._excel_import_button.pack_forget()
        else:
            if not self._excel_export_button.winfo_manager():
                self._excel_export_button.pack(side="left", padx=(12, 0))
                self._excel_import_button.pack(side="left", padx=(6, 0))

    # -- save/revert ---------------------------------------------------------
    def _save(self) -> None:
        self.flush()
        try:
            self._session.save()
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            return
        self._status_label.config(text=f"Saved {self._path.name}", style="Muted.TLabel")

    def _export_excel(self) -> None:
        only = self._excel_only()
        if only is None:
            return
        self.flush()
        path = filedialog.asksaveasfilename(parent=self, title=f"Export {only.lower()}", defaultextension=".xlsx", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            excel_io.export_fe8(path, self._data, only=only)
            self._status_label.config(text=f"Exported {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Could not export Excel", str(exc), parent=self)

    def _import_excel(self) -> None:
        only = self._excel_only()
        if only is None:
            return
        self.flush()
        path = filedialog.askopenfilename(parent=self, title=f"Import {only.lower()}", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            data, _docs, errors = excel_io.import_fe8(path, self._data, only=only)
            if errors:
                messagebox.showerror("Excel import has errors", "\n".join(errors[:30]), parent=self)
                return
            self._data = data
            self._session.changed(self)
            self._refresh_pickers()
            self._status_label.config(text=f"Imported {Path(path).name}; save FE8Data.bin")
        except Exception as exc:
            messagebox.showerror("Could not import Excel", str(exc), parent=self)
    def _revert(self) -> None:
        if not messagebox.askyesno(
                "Discard unsaved edits?",
                "Put FE8Data.bin back as it was last saved? This discards every unsaved edit to characters, "
                "classes, items, skills, terrain and supports.", icon="warning", parent=self):
            return
        for key in self._forms:
            self._forms[key] = None  # nothing left to commit
        self._session.revert()
        self._refresh_pickers()
        self._show_general()
        for key, picker in self._pickers.items():
            if picker.current is not None:
                self._show(key, picker.current)
        self._status_label.config(text="Unsaved edits discarded", style="Muted.TLabel")

    # -- workspace navigation -------------------------------------------------
    def select_tab(self, name: str) -> None:
        """Show one tab: classes, items, skills or terrain."""
        if name in TAB_KEYS:
            self._notebook.select(TAB_KEYS.index(name))

    def _select_record(self, tab: str, records, key: Callable, wanted: str) -> None:
        if self._fe8 is None or not wanted:
            return
        for i, record in enumerate(records):
            if key(record) == wanted:
                self.select_tab(tab)
                self._pickers[tab].select(i)
                return

    def select_class(self, jid: str) -> None:
        self._select_record("classes", self._fe8.classes if self._fe8 else [], lambda c: c.jid, jid)

    def select_item(self, iid: str) -> None:
        self._select_record("items", self._fe8.items if self._fe8 else [], lambda it: it.iid, iid)

    def select_skill(self, sid: str) -> None:
        self._select_record("skills", self._fe8.skills if self._fe8 else [], lambda s: s.sid, sid)

    def select_chapter(self, index: int) -> None:
        """Show a ``ChapterData`` record by its position."""
        picker = self._pickers.get("chapters")
        if picker is not None and 0 <= index < len(picker._labels):
            self.select_tab("chapters")
            picker.select(index)


class _Body:
    """A form body without a scrollbar of its own, for a form placed in a
    window that already scrolls."""

    def __init__(self, frame: ttk.Frame):
        self.body = frame

    def scroll_top(self) -> None:
        pass


class ChapterRecordPanel(StatsEditor):
    """Game Data › Chapters' form, shown where a chapter's map is edited (the
    Build tab's Map settings window): the ``ChapterData`` record whose map is
    the open map folder, or a choice when several records use it (trial
    maps). It edits the same FE8Data.bin session, so Game Data shows each
    edit at once, and the file is saved with Save FE8Data.bin."""

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog, session: Fe8DataSession,
                 navigate: Optional[Callable[[tuple], None]] = None):
        self._map_name: Optional[str] = None
        self._matches: list[int] = []
        self._record: Optional[int] = None
        super().__init__(parent, project, changelog, session, navigate)

    def _build_widgets(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x")
        self._save_button = ttk.Button(top, text="Save FE8Data.bin", style="Accent.TButton", command=self._save,
                                       state="disabled")
        self._save_button.pack(side="left")
        self._revert_button = ttk.Button(top, text="Discard unsaved edits", command=self._revert, state="disabled")
        self._revert_button.pack(side="left", padx=(6, 0))

        self._status_label = ttk.Label(top, text="", style="Muted.TLabel")
        self._status_label.pack(side="left", padx=(10, 0))
        if self._navigate is not None:
            ttk.Button(top, text="Open in Game Data ›", command=self._open_in_game_data).pack(side="right")
        chooser = ttk.Frame(self)
        chooser.pack(fill="x", pady=(6, 0))
        self._record_label = ttk.Label(chooser, text="Record")
        self._record_var = tk.StringVar()
        self._record_combo = ttk.Combobox(chooser, textvariable=self._record_var, state="readonly", width=60)
        self._record_combo.bind("<<ComboboxSelected>>", lambda e: self._pick(self._record_combo.current()))
        ttk.Label(self, style="Muted.TLabel", wraplength=720, justify="left", text=(
            "The same record as Game Data › Chapters, stored in FE8Data.bin: fields apply when you leave them, and "
            "Save FE8Data.bin (not Save Chapter) writes them.")).pack(anchor="w", pady=(4, 0))
        frame = ttk.Frame(self)
        frame.pack(fill="x")
        self._bodies["chapters"] = _Body(frame)
        self._notebook = frame  # StatsEditor puts its "not found" note in the notebook's master

    def _refresh_pickers(self) -> None:
        """Relabel the records (a title or map may just have changed)."""
        try:
            chapters = fe8data.read_chapter_data(self._data)
        except (KeyError, ValueError, struct.error):
            chapters = []
        self._matches = [c.index for c in chapters if self._map_name and c.map_name == self._map_name]
        labels = [f"{self._text(chapters[i].title_key) or chapters[i].title_key or '(untitled)'}  ·  "
                  f"{chapters[i].script or '-'}  ·  id {chapters[i].chapter_id}  ·  record {i}" for i in self._matches]
        try:
            self._record_combo.configure(values=labels)
            if len(self._matches) > 1:
                self._record_label.pack(side="left")
                self._record_combo.pack(side="left", padx=(8, 0))
            else:
                self._record_label.pack_forget()
                self._record_combo.pack_forget()
            if self._record in self._matches:
                self._record_combo.current(self._matches.index(self._record))
        except tk.TclError:
            pass

    def _show_general(self) -> None:
        pass

    def select_tab(self, name: str) -> None:
        pass

    def show_map(self, map_name: Optional[str]) -> None:
        """Show the record of map folder ``map_name`` (``bmap05_2``)."""
        if map_name == self._map_name and self._forms["chapters"] is not None:
            return
        self.flush()
        self._map_name = map_name
        self._refresh_pickers()
        if self._record not in self._matches:
            self._record = self._matches[0] if self._matches else None
        self._pick(self._matches.index(self._record) if self._record is not None else -1)

    def _pick(self, position: int) -> None:
        if 0 <= position < len(self._matches):
            self._record = self._matches[position]
            self._record_combo.current(position)
            self._show_chapter(self._record)
            return
        self._record = None
        form, parent = self._new_form("chapters", "chapter", -1)
        self._forms["chapters"] = None
        ttk.Label(parent, style="Muted.TLabel", wraplength=720, justify="left", text=(
            f"No Game Data › Chapters record uses the map {self._map_name}." if self._map_name
            else "Open a chapter with a map.")).grid(row=0, column=0, sticky="w", pady=(8, 0))

    def _revert(self) -> None:
        super()._revert()
        self._forms["chapters"] = None
        self.show_map(self._map_name)

    def _open_in_game_data(self) -> None:
        self.flush()
        self._navigate(("data", "chapters", str(self._record)) if self._record is not None else ("data", "chapters"))

    def cleanup(self) -> None:
        self.flush()
        self._session.unsubscribe(self._on_session_changed)
