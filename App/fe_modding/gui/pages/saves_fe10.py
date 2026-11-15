"""The Saves page's Radiant Dawn adapter: the Dolphin NAND file ``FE10_US.dat`` or ``FE10_EU.dat``
(``formats/save_file_fe10.py``) shown in the page's own tabs with the page's controls.

The file holds six files and six checkpoints (the page's File picker) and one system record (the
System data tab). Edits change the record in memory; Save writes the whole file back with every
record's checksum recomputed. Unknown bytes are kept as they are.

Names come from the save's own ID lists (ITBL) and, for display names, bases, supports and flags,
from the open workspace's FE10Data, messages and scripts."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from ... import script_sources
from ...formats import event_flags as ef
from ...formats import save_file_fe10 as sf
from ...formats.cmb.parser import ParseError, parse
from ..widgets import ScrollFrame, section_header
from .saves import OFF, ON, _CheckList, _Fields, _tree

TABS = ("overview", "units", "convoy", "map", "flags", "system", "raw")
INFO = ("Open the unencrypted FE10_US.dat (FE10_EU.dat for the European disc) from Dolphin's Radiant "
        "Dawn data folder (Wii/title/00010000/52464545/data, or .../52464550/data, under Dolphin's user "
        "folder) to edit a file's chapter, units, "
        "convoy and flags, and the system data every file shares. Unknown bytes are kept and the game's "
        "checksums recomputed. Encrypted data.bin exports from a Wii can't be read. Keep the game closed "
        "while you overwrite a save it uses.")
PICKER_LABEL = "File"
DEFAULT_THRESHOLDS = (50, 100, 150)   # retail RelianceParam
RANK_NAMES = {0: "None", 1: "C", 2: "B", 3: "A"}
# The system record's single values: grid attribute -> (offset, size).
SYSTEM_FIELDS = {"byte_3ac": (0x3AC, 1), "byte_3ad": (0x3AD, 1), "bytes_3ae": (0x3AE, 2),
                 "word_3b0": (0x3B0, 4), **{f"value_{i}": (0xCC + 2 * i, 2) for i in range(8)}}


class _StateView:
    """The battle state of a file, for the Overview grid."""

    def __init__(self, record: sf.SaveRecord):
        self._record = record

    @property
    def chapter(self) -> int:
        return self._record.chapter_number

    @chapter.setter
    def chapter(self, value: int) -> None:
        self._record.chapter_number = value

    @property
    def phase(self) -> int:
        return self._record.army_phase

    @phase.setter
    def phase(self, value: int) -> None:
        self._record.army_phase = value

    @property
    def turn(self) -> int:
        return self._record.turn

    @turn.setter
    def turn(self, value: int) -> None:
        self._record.turn = value


class _UnitView:
    """One unit for the Units grid: shown stats are the character's and class's bases plus the gains."""

    def __init__(self, record: sf.SaveRecord, unit: sf.SavedUnit, bases: Optional[list[int]]):
        self._record, self._unit, self._bases = record, unit, bases

    @property
    def job(self) -> int:
        return self._unit.class_number

    @job.setter
    def job(self, value: int) -> None:
        self._record.set_unit_class(self._unit, value)

    @property
    def army(self) -> int:
        return self._unit.army

    @army.setter
    def army(self, value: int) -> None:
        self._record.set_unit_army(self._unit, value)

    @property
    def level(self) -> int:
        return self._unit.level

    @level.setter
    def level(self, value: int) -> None:
        self._record.set_unit_state(self._unit, level=value)

    @property
    def exp(self) -> int:
        return self._unit.experience

    @exp.setter
    def exp(self, value: int) -> None:
        self._record.set_unit_state(self._unit, experience=value)

    @property
    def hp(self) -> int:
        return self._unit.current_hp

    @hp.setter
    def hp(self, value: int) -> None:
        self._record.set_unit_state(self._unit, current_hp=value)

    def stat(self, i: int) -> Optional[int]:
        return None if self._bases is None else self._bases[i] + self._unit.stat_gains[i]

    def set_stat(self, i: int, value: int) -> None:
        gains = list(self._unit.stat_gains)
        gains[i] = value - self._bases[i]
        self._record.set_unit_state(self._unit, stat_gains=gains)


def _stat_property(i: int) -> property:
    """Stat ``i`` of :class:`_UnitView` as an attribute (the grid binds attributes by name)."""
    return property(lambda self: self.stat(i), lambda self, value: self.set_stat(i, value))


for _i, _stat in enumerate(sf.UNIT_STATS):
    setattr(_UnitView, f"stat_{_stat}", _stat_property(_i))


class _ItemView:
    """One of a unit's seven items (``unit`` set) or a convoy slot."""

    def __init__(self, record: sf.SaveRecord, unit: Optional[sf.SavedUnit], slot: int, item):
        self._record, self._unit, self._slot, self.saved = record, unit, slot, item

    def _set(self, number: int, uses: int, flags: int) -> None:
        if self._unit is not None:
            self._record.set_unit_item(self._unit, self._slot, number, uses, flags)
            return
        if self.saved.forged:
            raise ValueError("A forged item changes with the forge fields below.")
        if not 0 <= uses <= 0xFF or not 0 <= flags <= 0xFF:
            raise ValueError("uses and flags must be 0..255")
        self._record.set_convoy_item(self._slot, number, 0 if number == 0 else uses << 8 | flags)

    @property
    def item(self) -> int:
        return self.saved.item_number

    @item.setter
    def item(self, value: int) -> None:
        self._set(value, self.saved.state >> 8, self.saved.state & 0xFF)

    @property
    def uses(self) -> int:
        return self.saved.state >> 8

    @uses.setter
    def uses(self, value: int) -> None:
        self._set(self.saved.item_number, value, self.saved.state & 0xFF)

    @property
    def flags(self) -> int:
        return self.saved.state & 0xFF

    @flags.setter
    def flags(self, value: int) -> None:
        self._set(self.saved.item_number, self.saved.state >> 8, value)


class _SupportView:
    """The selected support slot of the selected unit."""

    def __init__(self, record: sf.SaveRecord, unit: sf.SavedUnit, slot: int, thresholds):
        self._record, self._unit, self._slot, self._thresholds = record, unit, slot, thresholds

    @property
    def points(self) -> int:
        return self._unit.support_points[self._slot]

    @points.setter
    def points(self, value: int) -> None:
        self._record.set_unit_support_points(self._unit, self._slot, value)

    @property
    def rank(self) -> int:
        return sf.support_rank(self.points, self._thresholds)

    @rank.setter
    def rank(self, value: int) -> None:
        self.points = sf.rank_points(value, self._thresholds)


class _TileTableView:
    """The live count of a file's tile records."""

    def __init__(self, record: sf.SaveRecord):
        self._record = record

    @property
    def count(self) -> int:
        return self._record.tile_records()[1]

    @count.setter
    def count(self, value: int) -> None:
        self._record.set_tile_count(value)


class _TileView:
    """One tile record (x, y, type, subtype, four values)."""

    def __init__(self, record: sf.SaveRecord, index: int):
        self._record, self._index = record, index

    def _get(self) -> sf.TileRecord:
        return self._record.tile_records()[0][self._index]

    def _set(self, **changes) -> None:
        current = self._get()
        values = {"x": current.x, "y": current.y, "type": current.type, "subtype": current.subtype,
                  "values": current.values, **changes}
        self._record.set_tile_record(self._index, sf.TileRecord(**values))

    x = property(lambda self: self._get().x, lambda self, v: self._set(x=v))
    y = property(lambda self: self._get().y, lambda self, v: self._set(y=v))
    type = property(lambda self: self._get().type, lambda self, v: self._set(type=v))
    subtype = property(lambda self: self._get().subtype, lambda self, v: self._set(subtype=v))
    values = property(lambda self: self._get().values, lambda self, v: self._set(values=bytes(v)))


class _SystemView:
    """The system record's single values (:data:`SYSTEM_FIELDS`)."""

    def __init__(self, record: sf.SaveRecord):
        object.__setattr__(self, "_record", record)

    def __getattr__(self, name: str) -> int:
        if name not in SYSTEM_FIELDS:
            raise AttributeError(name)
        return self._record.system_value(*SYSTEM_FIELDS[name])

    def __setattr__(self, name: str, value: int) -> None:
        self._record.set_system_value(*SYSTEM_FIELDS[name], value)


class Fe10Saves:
    """Radiant Dawn's side of the Saves page (``page``: the :class:`SaveEditorPage`)."""

    TABS = TABS
    INFO = INFO
    PICKER_LABEL = PICKER_LABEL

    def __init__(self, page):
        self.page = page
        self.shell = page.shell
        self.path: Optional[Path] = None
        self.save: Optional[sf.SaveFile] = None
        self.records: list[sf.SaveRecord] = []
        self.labels: list[str] = []
        self.record: Optional[sf.SaveRecord] = None
        self._units: dict[int, sf.SavedUnit] = {}
        self._unit_problem = ""
        self._unit_slot: Optional[int] = None
        self._support_slot: Optional[int] = None
        self._convoy_slot: Optional[int] = None
        self._tile: Optional[int] = None
        self._fields: list[_Fields] = []
        self._character_choices: dict = {}

    # -- workspace ------------------------------------------------------------------------
    def _database(self):
        try:
            session = self.shell.session
        except Exception:  # noqa: BLE001 - no FE10Data: numbers and IDs only
            return None
        return getattr(session, "fe10", None) if session is not None else None

    def _text(self, key) -> str:
        index = getattr(self.shell, "index", None)
        return index.text(key) if index is not None and getattr(index, "ready", False) and key else ""

    def _lists(self) -> dict:
        try:
            return self.record.id_name_lists() if self.record is not None and not self.record.empty else {}
        except (KeyError, ValueError):
            return {}

    def _name(self, kind: str, number: int) -> str:
        """Display name of a number in the save's own list ``kind``."""
        first = {"character": 1, "class": 1, "item": 1, "skill": 0}[kind]
        ids = self._lists().get(kind, [])
        if not 0 <= number - first < len(ids):
            return f"#{number}"
        record_id = ids[number - first]
        database = self._database()
        if database is not None:
            rows = {"character": database.characters, "class": database.classes, "item": database.items,
                    "skill": database.skills}[kind]
            key = {"character": "mpid", "class": "mjid", "item": "miid", "skill": "msid"}[kind]
            row = next((r for r in rows if r.id == record_id), None)
            title = self._text(row.values.get(key)) if row is not None else ""
            if title and title != row.values.get(key):
                return f"{title} ({record_id})"
        return record_id

    def _choices(self, kind: str) -> dict:
        first = {"character": 1, "class": 1, "item": 1, "skill": 0}[kind]
        out = {0: "(empty)"} if kind == "item" else ({0: "(none)"} if kind == "character" else {})
        out.update({i + first: self._name(kind, i + first) for i in range(len(self._lists().get(kind, [])))})
        return out

    def _support_counts(self) -> Optional[dict[int, int]]:
        database = self._database()
        if database is None or self.record is None:
            return None
        counts = {row.values["pid"]: len(row.lists["partners"]) for row in database.table("support")}
        return {i: counts.get(pid, 0) for i, pid in enumerate(self._lists().get("character", []), 1)}

    def _partners(self, unit: sf.SavedUnit) -> list[str]:
        database = self._database()
        pid = self._lists().get("character", [])[unit.person_number - 1]
        row = next((r for r in database.table("support") if r.values["pid"] == pid), None) if database else None
        return [partner[0] for partner in row.lists["partners"]] if row is not None else []

    def _thresholds(self) -> tuple[int, int, int]:
        try:
            values = self._database().table("support_param")[0].values
            return values["points_c"], values["points_b"], values["points_a"]
        except (AttributeError, KeyError, IndexError, TypeError):
            return DEFAULT_THRESHOLDS

    def _bases(self, unit: sf.SavedUnit) -> Optional[tuple[list[int], list[int]]]:
        """(character bonus + class base, class cap) per stat, from the open workspace."""
        database = self._database()
        lists = self._lists()
        if database is None or not lists:
            return None
        pid = lists["character"][unit.person_number - 1] if 0 < unit.person_number <= len(lists["character"]) else None
        jid = lists["class"][unit.class_number - 1] if 0 < unit.class_number <= len(lists["class"]) else None
        person = next((c for c in database.characters if c.id == pid), None)
        job = next((c for c in database.classes if c.id == jid), None)
        if person is None or job is None:
            return None
        return ([person.values[f"bonus_{s}"] + job.values[f"base_{s}"] for s in sf.UNIT_STATS],
                [job.values[f"cap_{s}"] for s in sf.UNIT_STATS])

    # -- building -------------------------------------------------------------------------
    def _fields_in(self, parent, columns: int = 2) -> _Fields:
        f = _Fields(parent, self.page, columns)
        self._fields.append(f)
        return f

    def build(self, tabs: dict) -> None:
        self._build_overview(tabs["overview"])
        self._build_units(tabs["units"])
        self._build_convoy(tabs["convoy"])
        self._build_map(tabs["map"])
        self._build_flags(tabs["flags"])
        self._build_system(tabs["system"])
        self._build_raw(tabs["raw"])

    def _build_overview(self, tab) -> None:
        self._summary = ttk.Label(tab, justify="left", anchor="nw")
        self._summary.pack(fill="x")
        section_header(tab, "Battle state", "the chapter is the game's internal chapter number").pack(
            anchor="w", pady=(12, 0))
        f = self._fields_in(tab, 3)
        f.pack(anchor="w", pady=(4, 10))
        state = lambda: _StateView(self.record) if self._has("BMST") else None  # noqa: E731
        f.add("Chapter", state, "chapter")
        f.add("Phase (army)", state, "phase")
        f.add("Turn", state, "turn", "u16")
        start = ttk.Frame(tab)
        start.pack(anchor="w", pady=(6, 0))
        self._start_button = ttk.Button(start, text="Start a chapter from its opening…", command=self._start_chapter)
        self._start_button.pack(side="left")
        ttk.Label(start, style="Muted.TLabel", wraplength=640, justify="left", text=(
            "Makes the file a save from the end of the chapter before: the file menu offers Start Chapter "
            "and the chapter's opening plays (4-P's army split, for example). Changing only the chapter "
            "number keeps a base or preparations file where it was saved.")).pack(side="left", padx=(10, 0))

    def _build_units(self, tab) -> None:
        left = ttk.Frame(tab)
        left.pack(side="left", fill="y")
        self._unit_tree = _tree(left, {"slot": ("Slot", 44, False), "name": ("Character", 150, False),
                                       "class": ("Class", 140, False), "army": ("Army", 44, False),
                                       "lv": ("Lv", 34, False)}, height=24)
        self._unit_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_unit())
        self._unit_status = ttk.Label(left, style="Muted.TLabel", wraplength=420, justify="left")
        self._unit_status.pack(anchor="w")

        scroll = ScrollFrame(tab, padding=(16, 4))
        scroll.pack(side="left", fill="both", expand=True)
        b = scroll.body
        unit = self._unit_view
        section_header(b, "Identity").pack(anchor="w")
        f = self._fields_in(b, 2)
        f.pack(anchor="w", pady=(4, 10))
        f.add("Class", unit, "job", {})
        f.add("Army", unit, "army")
        f.add("Level", unit, "level")
        f.add("EXP (255 = none)", unit, "exp")
        f.add("Current HP", unit, "hp")
        self._identity_fields = f

        section_header(b, "Stats", "as the game shows them: the bases plus what the unit gained").pack(anchor="w")
        f = self._fields_in(b, 4)
        f.pack(anchor="w", pady=(4, 2))
        for name in sf.UNIT_STATS:
            f.add(name.capitalize(), unit, f"stat_{name}", "u8", width=6)
        self._caps = ttk.Label(b, style="Muted.TLabel")
        self._caps.pack(anchor="w", pady=(0, 10))

        section_header(b, "Items", "flags: 0x80 equipped, 0x20 forged (a forged item can't change here)").pack(
            anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 10))
        for k in range(sf.UNIT_ITEM_SLOTS):
            slot = (lambda k: lambda: self._item_view(k))(k)
            f.add(f"Item {k + 1}", slot, "item", {})
            f.add("Uses", slot, "uses", width=6)
            f.add("Flags", slot, "flags", width=6)
        self._item_fields = f

        section_header(b, "Skills").pack(anchor="w")
        self._skill_list = _CheckList(b, "Double-click to give or remove. A given skill is saved as learned, "
                                         "like a scroll's; a unit holds at most 18.", height=8)
        self._skill_list.pack(anchor="w", fill="x", pady=(4, 10))

        section_header(b, "Supports", "points per RelianceData partner").pack(anchor="w")
        self._support_note = ttk.Label(b, style="Muted.TLabel", wraplength=640, justify="left")
        self._support_note.pack(anchor="w")
        pair = ttk.Frame(b)
        pair.pack(anchor="w", pady=(4, 0))
        ttk.Label(pair, text="Support partner").pack(side="left")
        self._partner_var = tk.StringVar()
        self._partner_box = ttk.Combobox(pair, textvariable=self._partner_var, state="disabled", width=36,
                                         height=20)
        self._partner_box.pack(side="left", padx=(6, 0))
        self._partner_box.bind("<<ComboboxSelected>>", lambda e: self._set_partner())
        self._support_tree = _tree(b, {"slot": ("Slot", 44, False), "partner": ("Partner", 220, False),
                                       "points": ("Points", 60, False), "rank": ("Rank", 60, True)}, height=8)
        self._support_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_support())
        f = self._fields_in(b, 2)
        f.pack(anchor="w", pady=(0, 10))
        f.add("Points", self._support_view, "points")
        f.add("Rank", self._support_view, "rank", dict(RANK_NAMES))

    def _build_convoy(self, tab) -> None:
        forge = ttk.Frame(tab)
        forge.pack(side="bottom", fill="x", pady=(6, 0))
        f = self._fields_in(tab, 3)
        f.pack(side="bottom", anchor="w", pady=(6, 0))
        f.add("Item", self._convoy_view, "item", {})
        f.add("Uses", self._convoy_view, "uses", width=6)
        f.add("Flags", self._convoy_view, "flags", width=6)
        self._convoy_fields = f
        self._forge_vars = {key: tk.StringVar() for key in ("name", "might", "hit", "crit", "weight", "rgba")}
        self._forge_entries = []
        for key, label, width in (("name", "Forge name", 16), ("might", "Mt", 5), ("hit", "Hit", 5),
                                  ("crit", "Crit", 5), ("weight", "Wt−", 5), ("rgba", "RGBA", 10)):
            ttk.Label(forge, text=label).pack(side="left", padx=(10 if self._forge_entries else 0, 4))
            entry = ttk.Entry(forge, textvariable=self._forge_vars[key], width=width)
            entry.pack(side="left")
            self._forge_entries.append(entry)
        self._forge_apply = ttk.Button(forge, text="Apply forge", command=self._apply_forge)
        self._forge_apply.pack(side="left", padx=(10, 0))
        self._convoy_tree = _tree(tab, {"slot": ("Slot", 50, False), "item": ("Item", 300, False),
                                        "uses": ("Uses", 60, False), "forge": ("Forge", 160, True)}, height=20)
        self._convoy_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_convoy())

    def _build_map(self, tab) -> None:
        ttk.Label(tab, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "The map's tile records, as on Path of Radiance: opened chests, doors and roofs, visited villages, "
            "range overlays and the rest. Only the first “count” records are live; the ones after it keep "
            "leftover bytes. Type names are Path of Radiance's; Radiant Dawn files show range overlay (6) "
            "and chest opened (0x23), the others are not checked on Radiant Dawn.")).pack(anchor="w")
        f = self._fields_in(tab, 4)
        f.pack(side="bottom", anchor="w", pady=(6, 0))
        table = lambda: _TileTableView(self.record) if self._has("T  T") else None  # noqa: E731
        tile = lambda: _TileView(self.record, self._tile) if self._has("T  T") and self._tile is not None else None  # noqa: E731
        f.add("Count", table, "count", "u32")
        f.add("X", tile, "x", "s8", width=6)
        f.add("Y", tile, "y", "s8", width=6)
        f.add("Type", tile, "type", dict(sf.TILE_TYPES))
        f.add("Subtype", tile, "subtype", width=6)
        for i in range(4):
            f.add(f"Value {i}", tile, ("values", i), width=6)
        self._map_tree = _tree(tab, {"n": ("#", 40, False), "xy": ("Tile", 70, False), "type": ("Type", 160, False),
                                     "sub": ("Subtype", 60, False), "values": ("Values", 160, True)}, height=16)
        self._map_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_tile())

    def _fill_map(self) -> None:
        tree = self._map_tree
        tree.delete(*tree.get_children())
        if not self._has("T  T"):
            return
        try:
            records, count = self.record.tile_records()
        except ValueError:
            return
        for i, r in enumerate(records[:max(count, 0)]):
            tree.insert("", "end", iid=str(i), values=(i + 1, f"{r.x}, {r.y}", sf.TILE_TYPES.get(r.type, r.type),
                                                      r.subtype, " ".join(str(v) for v in r.values)))
        if count < len(records):
            tree.insert("", "end", iid=str(count), values=(count + 1, "", "(next free record)", "", ""),
                        tags=("muted",))
        if self._tile is not None and tree.exists(str(self._tile)):
            tree.selection_set(str(self._tile))

    def _pick_tile(self) -> None:
        sel = self._map_tree.selection()
        self._tile = int(sel[0]) if sel else None
        for f in self._fields:
            f.load()

    def _build_flags(self, tab) -> None:
        self._flags_note = ttk.Label(tab, style="Muted.TLabel", wraplength=900, justify="left")
        self._flags_note.pack(anchor="w")
        self._flag_tree = _tree(tab, {"on": ("Set", 50, False), "slot": ("Slot", 60, False),
                                      "name": ("Name", 280, False), "meaning": ("Meaning", 420, True)}, height=20)
        self._flag_tree.bind("<Double-1>", lambda e: self._toggle_flag())
        self._flag_tree.bind("<space>", lambda e: self._toggle_flag())

    def _build_system(self, tab) -> None:
        scroll = ScrollFrame(tab, padding=(4, 4))
        scroll.pack(fill="both", expand=True)
        b = scroll.body
        ttk.Label(b, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "Shared by every file. These are the parts of the system record as the game writes it; what each "
            "bit and value means is not traced yet, so they are named by where they sit in the record.")).pack(
            anchor="w")
        f = self._fields_in(b, 4)
        f.pack(anchor="w", pady=(6, 10))
        system = lambda: _SystemView(self.save.system) if self._system_ok() else None  # noqa: E731
        for name, (offset, size) in SYSTEM_FIELDS.items():
            f.add(f"+0x{offset:X}", system, name, {1: "u8", 2: "u16", 4: "u32"}[size])
        row = ttk.Frame(b)
        row.pack(anchor="w", pady=(4, 0))
        ttk.Label(row, text="Bit set").pack(side="left")
        names = [p[0] for p in sf.SYSTEM_PARTS if p[3] == "bits"]
        self._bits_var = tk.StringVar(value=names[0])
        box = ttk.Combobox(row, textvariable=self._bits_var, values=names, state="readonly", width=24)
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self._fill_system_bits())
        self._bit_list = _CheckList(b, "Double-click a bit to switch it.", height=12)
        self._bit_list.pack(anchor="w", fill="x", pady=(4, 10))
        section_header(b, "Records", "30 records of 24 bytes (read only)").pack(anchor="w")
        self._system_records = _tree(b, {"n": ("#", 40, False), "bytes": ("Bytes", 600, True)}, height=10)

    def _build_raw(self, tab) -> None:
        ttk.Label(tab, style="Muted.TLabel", wraplength=900, justify="left",
                  text="The file's sections; select one to see only its bytes. Bytes are shown as they will be "
                       "written (read only).").pack(anchor="w")
        self._section_tree = _tree(tab, {"tag": ("Section", 90, False), "offset": ("Offset", 100, False),
                                         "size": ("Size", 140, True)}, height=8)
        self._section_tree.bind("<<TreeviewSelect>>", lambda e: self._fill_raw())
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self._raw_text = tk.Text(frame, wrap="none", font=("Consolas", 10), height=16)
        scroll = ttk.Scrollbar(frame, command=self._raw_text.yview)
        self._raw_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._raw_text.pack(side="left", fill="both", expand=True)

    # -- targets ----------------------------------------------------------------------------
    def _has(self, section: str) -> bool:
        return self.record is not None and not self.record.empty and self.record.section(section) is not None

    def _system_ok(self) -> bool:
        return self.save is not None and self.save.system.valid

    def _unit(self) -> Optional[sf.SavedUnit]:
        return self._units.get(self._unit_slot) if self._unit_slot is not None else None

    def _unit_view(self) -> Optional[_UnitView]:
        unit = self._unit()
        if unit is None:
            return None
        known = self._bases(unit)
        return _UnitView(self.record, unit, known[0] if known else None)

    def _item_view(self, k: int) -> Optional[_ItemView]:
        unit = self._unit()
        return _ItemView(self.record, unit, k, unit.items[k]) if unit is not None else None

    def _support_view(self) -> Optional[_SupportView]:
        unit = self._unit()
        if unit is None or self._support_slot is None or self._support_slot >= unit.support_slot_count:
            return None
        return _SupportView(self.record, unit, self._support_slot, self._thresholds())

    def _convoy_view(self) -> Optional[_ItemView]:
        if self._convoy_slot is None or not self._has("SOKO"):
            return None
        try:
            return _ItemView(self.record, None, self._convoy_slot, self.record.convoy_items()[self._convoy_slot])
        except (ValueError, IndexError):
            return None

    # -- file -------------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        return bool(self.save and (self.save.system.dirty or any(r.dirty for r in self.save.records)))

    def open_dialog(self) -> None:
        chosen = filedialog.askopenfilename(title="Open a Radiant Dawn save", parent=self.page,
                                            filetypes=[("Radiant Dawn save", "FE10_*.dat"),
                                                       ("DAT files", "*.dat"), ("All files", "*.*")])
        if chosen:
            self.open_path(Path(chosen))

    def open_path(self, path: Path, keep: Optional[int] = None) -> bool:
        try:
            save = sf.SaveFile.from_path(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not open the save", str(exc), parent=self.page)
            return False
        if path.is_dir():
            path = sf.find_in(path)
        self.path, self.save = path, save
        self.records = list(save.records)
        active = save.active_records()
        self.labels = [sf.record_label(record, active) for record in self.records]
        if keep is not None:
            preferred = self.records[keep]
        else:
            preferred = max(active, key=lambda r: r.timestamp_saved) if active else self.records[0]
        self.page.set_picker(str(path), self.labels, self.labels[self.records.index(preferred)])
        return True

    def select(self, label: str) -> None:
        if label not in self.labels:
            return
        self.record = self.records[self.labels.index(label)]
        self._unit_slot = self._support_slot = self._convoy_slot = self._tile = None
        self.refresh()

    def write(self, path: Path) -> bool:
        if self.save is None:
            return False
        temp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(self.save.to_bytes())
            os.replace(temp, path)
            banner = self.path.parent / "banner.bin" if self.path else None
            if banner is not None and banner.is_file() and not (path.parent / "banner.bin").exists():
                (path.parent / "banner.bin").write_bytes(banner.read_bytes())
        except OSError as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror("Could not write the save", str(exc), parent=self.page)
            return False
        self.shell.changelog.append(path.name, "Edited Radiant Dawn save")
        keep = self.records.index(self.record) if self.record in self.records else None
        self.open_path(path, keep)
        return True

    def save_as_dialog(self) -> None:
        if self.save is None:
            return
        chosen = filedialog.asksaveasfilename(title="Save the edited save as", parent=self.page,
                                              initialfile=self.path.name if self.path else sf.FILE_NAME,
                                              defaultextension=".dat",
                                              filetypes=[("Radiant Dawn save", "*.dat")])
        if chosen:
            self.write(Path(chosen))

    def problems(self) -> list[str]:
        """What :meth:`check` reports: header, checksum and unit-framing problems of the edited file."""
        if self.save is None:
            return []
        try:
            problems = sf.validate(sf.SaveFile.from_bytes(self.save.to_bytes()))
            counts = self._support_counts()
            if counts is not None:
                for record in self.save.active_records():
                    record.unit_records(counts)
        except (KeyError, ValueError) as exc:
            problems = [str(exc)]
        return problems

    def check(self) -> None:
        if self.save is None:
            return
        problems = self.problems()
        if problems:
            messagebox.showwarning("Problems", "\n".join(problems[:30]), parent=self.page)
        else:
            messagebox.showinfo("Check", "No problems found.", parent=self.page)

    def play(self) -> None:
        if self.save is None:
            return
        banner_path = self.path.parent / "banner.bin" if self.path else None
        try:
            banner = banner_path.read_bytes() if banner_path is not None and banner_path.is_file() else None
        except OSError as exc:
            messagebox.showerror("Could not read banner.bin", str(exc), parent=self.page)
            return
        self.shell.play_from_wii_save(self.save.to_bytes(), banner)

    def status(self) -> str:
        return f"{len(self._units)} unit(s)" if self._units else ""

    def changed(self) -> None:
        """After an edit: read the units again (a skill edit moves the records after it) and redraw."""
        keep = self._unit_slot, self._support_slot, self._convoy_slot, self._tile
        self.refresh()
        self._unit_slot, self._support_slot, self._convoy_slot, self._tile = keep
        if keep[3] is not None and self._map_tree.exists(str(keep[3])):
            self._map_tree.selection_set(str(keep[3]))
        for tree, key in ((self._unit_tree, keep[0]), (self._convoy_tree, keep[2]),
                          (self._support_tree, None)):
            if key is not None and tree.exists(str(key)):
                tree.selection_set(str(key))
                tree.see(str(key))
        for f in self._fields:
            f.load()
        self._fill_unit_extras()
        self._sync_forge()

    # -- refresh ----------------------------------------------------------------------------
    def refresh(self) -> None:
        self._read_units()
        self._fill_summary()
        self._fill_units()
        self._fill_convoy()
        self._fill_map()
        self._fill_flags()
        self._fill_system()
        self._fill_sections()
        self._load_choices()
        for f in self._fields:
            f.load()
        self._fill_unit_extras()
        self._sync_forge()
        self._start_button.configure(state="normal" if self._has("BMST") else "disabled")
        self.page.sync()

    def _read_units(self) -> None:
        self._units, self._unit_problem = {}, ""
        if not self._has("UNIP"):
            return
        counts = self._support_counts()
        if counts is None:
            self._unit_problem = "Open an extracted Radiant Dawn workspace: its FE10Data frames the units."
            return
        try:
            self._units = {u.slot: u for u in self.record.unit_records(counts) if not u.empty}
        except (KeyError, ValueError, IndexError) as exc:
            self._unit_problem = f"Could not read the units: {exc}"

    def _fill_summary(self) -> None:
        record = self.record
        if record is None:
            self._summary.configure(text="")
            return
        if record.empty:
            self._summary.configure(text="Empty file.")
            return
        lines = [f"Sequence {record.sequence} · checksum {'valid' if record.crc_ok else 'invalid'}"]
        if self._has("BMST"):
            resume = {2: "a base or the preparations", sf.RESUME_CHAPTER_END: "the end of the chapter before",
                      0x0B: "the chapter's opening event"}.get(record.resume_step, f"step {record.resume_step}")
            lines.append(f"Map {record.map_name or '(none)'} · resumes at {resume}")
        self._summary.configure(text="\n".join(lines))

    def _fill_units(self) -> None:
        tree = self._unit_tree
        tree.delete(*tree.get_children())
        for slot, unit in self._units.items():
            tree.insert("", "end", iid=str(slot), values=(slot + 1, self._name("character", unit.person_number),
                                                          self._name("class", unit.class_number), unit.army,
                                                          unit.level))
        self._unit_status.configure(text=self._unit_problem)

    def _load_choices(self) -> None:
        """The class and item pickers list the save's own IDs."""
        wanted = {"job": self._choices("class"), "item": self._choices("item")}
        for fields_ in (self._identity_fields, self._item_fields, self._convoy_fields):
            for i, (target, attr, kind, var, on_set, box) in enumerate(fields_._items):
                if isinstance(attr, str) and attr in wanted and wanted[attr]:
                    fields_._items[i] = (target, attr, wanted[attr], var, on_set, box)
                    box.configure(values=[fields_._choice(v, n) for v, n in wanted[attr].items()])
        self._character_choices = self._choices("character")
        self._partner_box.configure(values=[_Fields._choice(v, n) for v, n in self._character_choices.items()])

    def _pick_unit(self) -> None:
        sel = self._unit_tree.selection()
        slot = int(sel[0]) if sel else None
        if slot == self._unit_slot:
            return
        self._unit_slot, self._support_slot = slot, None
        for f in self._fields:
            f.load()
        self._fill_unit_extras()

    def _fill_unit_extras(self) -> None:
        unit = self._unit()
        known = self._bases(unit) if unit is not None else None
        self._caps.configure(text="Class caps: " + ", ".join(
            f"{s.capitalize()} {c}" for s, c in zip(sf.UNIT_STATS, known[1])) if known else "")
        self._fill_skills(unit)
        self._fill_supports(unit)

    def _fill_skills(self, unit: Optional[sf.SavedUnit]) -> None:
        if unit is None:
            self._skill_list.fill([], lambda i: False, lambda i, on: None)
            return
        have = {s.skill_number: s for s in unit.skills}
        rows = []
        for number in range(len(self._lists().get("skill", []))):
            name = self._name("skill", number)
            if number in have:
                name += f"  ({sf.SKILL_SOURCES.get(have[number].source, have[number].source)})"
            rows.append((number, f"{number:3d}  {name}"))

        def set_(number: int, on: bool) -> None:
            skills = [s for s in unit.skills if s.skill_number != number]
            if on:
                skills.append(sf.SavedSkill(number, 2, 0))
            try:
                self.record.set_unit_skills(unit, skills)
            except ValueError as exc:
                messagebox.showerror("Skills", str(exc), parent=self.page)
                return
            self.page.mark_dirty()
        self._skill_list.fill(rows, lambda number: number in have, set_)

    def _fill_supports(self, unit: Optional[sf.SavedUnit]) -> None:
        tree = self._support_tree
        tree.delete(*tree.get_children())
        if unit is None or not unit.support_slot_count:
            self._support_note.configure(text="" if unit is None else "This character has no supports.")
            self._partner_box.configure(state="disabled")
            self._partner_var.set("")
            return
        thresholds = self._thresholds()
        partners = self._partners(unit)
        lists = self._lists().get("character", [])
        for slot, points in enumerate(unit.support_points):
            pid = partners[slot] if slot < len(partners) else ""
            name = self._name("character", lists.index(pid) + 1) if pid in lists else pid
            tree.insert("", "end", iid=str(slot), values=(slot + 1, name, points,
                                                          RANK_NAMES[sf.support_rank(points, thresholds)]))
        if self._support_slot is not None and tree.exists(str(self._support_slot)):
            tree.selection_set(str(self._support_slot))
            tree.see(str(self._support_slot))
        self._support_note.configure(text=(
            f"Points stop at {thresholds[0]}, {thresholds[1]} and {thresholds[2]} until the support menu's "
            "rank-up adds one, so a rank set here writes the value just past its threshold. The partner is the "
            "one support a unit has at a time; setting it links the partner back and unlinks the pairs it "
            "replaces, as the game does (points are kept)."))
        self._partner_box.configure(state="readonly")
        self._partner_var.set(_Fields._choice(unit.active_partner,
                                              self._character_choices.get(unit.active_partner, "")))

    def _pick_support(self) -> None:
        sel = self._support_tree.selection()
        self._support_slot = int(sel[0]) if sel else None
        for f in self._fields:
            f.load()

    def _set_partner(self) -> None:
        unit = self._unit()
        if unit is None:
            return
        text = self._partner_var.get()
        try:
            number = int(text[text.rindex("(") + 1:-1]) if text.endswith(")") else int(text or 0)
        except ValueError:
            return
        if number == unit.active_partner:
            return
        try:
            self.link(unit.person_number, number)
        except (ValueError, IndexError, KeyError) as exc:
            messagebox.showerror("Support partner", str(exc), parent=self.page)
            return
        self.page.mark_dirty()

    def link(self, person: int, partner: int) -> None:
        """Pair characters ``person`` and ``partner`` (0: none) both ways, unlinking the pairs this replaces."""
        counts = self._support_counts()

        def unit_of(number: int) -> Optional[sf.SavedUnit]:
            return next((u for u in self.record.unit_records(counts)
                         if not u.empty and u.person_number == number and u.support_slot_count), None)

        me = unit_of(person)
        if me is None:
            raise ValueError("this character has no supports")
        old = me.active_partner
        self.record.set_unit_active_partner(me, partner)
        if old and old != partner:
            other = unit_of(old)
            if other is not None and other.active_partner == person:
                self.record.set_unit_active_partner(other, 0)
        if partner:
            other = unit_of(partner)
            if other is not None:
                replaced = other.active_partner
                self.record.set_unit_active_partner(other, person)
                if replaced and replaced != person:
                    third = unit_of(replaced)
                    if third is not None and third.active_partner == partner:
                        self.record.set_unit_active_partner(third, 0)

    def _fill_convoy(self) -> None:
        tree = self._convoy_tree
        tree.delete(*tree.get_children())
        if not self._has("SOKO"):
            return
        try:
            items = self.record.convoy_items()
        except ValueError:
            return
        for item in items:
            tree.insert("", "end", iid=str(item.slot),
                        values=(item.slot + 1, self._name("item", item.item_number) if item.item_number else "",
                                item.state >> 8 if item.item_number else "",
                                item.forged_name or ("yes" if item.forged else "")),
                        tags=() if item.item_number else ("muted",))
        if self._convoy_slot is not None and tree.exists(str(self._convoy_slot)):
            tree.selection_set(str(self._convoy_slot))

    def _pick_convoy(self) -> None:
        sel = self._convoy_tree.selection()
        self._convoy_slot = int(sel[0]) if sel else None
        self._convoy_fields.load()
        self._sync_forge()

    def _sync_forge(self) -> None:
        view = self._convoy_view()
        item = view.saved if view is not None else None
        values = item.forge_values if item is not None and item.forged else None
        self._forge_vars["name"].set(item.forge_name_bytes.decode("shift_jis", "replace") if values else "")
        for key, value in (("might", values.might_steps if values else ""),
                           ("hit", values.hit_steps if values else ""),
                           ("crit", values.critical_steps if values else ""),
                           ("weight", values.weight_reduction_steps if values else "")):
            self._forge_vars[key].set(str(value))
        self._forge_vars["rgba"].set(f"#{values.red:02X}{values.green:02X}{values.blue:02X}{values.alpha:02X}"
                                     if values else "")
        state = "normal" if values is not None else "disabled"
        for entry in self._forge_entries:
            entry.configure(state=state)
        self._forge_apply.configure(state=state)

    def _apply_forge(self) -> None:
        if self._convoy_slot is None:
            return
        v = self._forge_vars
        try:
            colour = v["rgba"].get().strip().removeprefix("#").removeprefix("0x")
            if len(colour) != 8:
                raise ValueError("RGBA is eight hexadecimal digits")
            payload = sf.ForgePayload(int(v["might"].get(), 0), int(v["hit"].get(), 0), int(v["crit"].get(), 0),
                                      int(v["weight"].get(), 0), *bytes.fromhex(colour))
            self.record.update_forged_convoy_item(self._convoy_slot, name=v["name"].get(), payload=payload)
        except (ValueError, IndexError) as exc:
            messagebox.showerror("Forge", str(exc), parent=self.page)
            return
        self.page.mark_dirty()

    # -- flags ------------------------------------------------------------------------------
    def slot_names(self) -> tuple[list, int]:
        """(name per BMST flag slot, number of campaign flags), from the workspace's scripts: the
        campaign flags of startup.cmb, then the chapter flags of the file's map's script."""
        project = self.page.project
        table = ef.FE10_FLAGS
        try:
            globals_ = ef.global_flags(parse(script_sources.peek(project, script_sources.startup_path(project))),
                                       table)
        except (OSError, ValueError, ParseError, AttributeError):
            globals_ = ef.global_flags_vanilla(table)
        locals_: list = []
        for chapter_id in sf.chapter_ids_for_map(self.record.map_name):
            try:
                path = script_sources.chapter_script(project, chapter_id)
                if path is not None:
                    locals_ = ef.local_flags(parse(script_sources.peek(project, path)))
                    break
            except (OSError, ValueError, ParseError, AttributeError):
                break
        return ef.slot_names(globals_, locals_, table.slot_count), len(globals_)

    def _fill_flags(self) -> None:
        tree = self._flag_tree
        tree.delete(*tree.get_children())
        if not self._has("BMST"):
            self._flags_note.configure(text="")
            return
        try:
            bits = self.record.script_flags()
        except ValueError:
            return
        names, n_globals = self.slot_names()
        stale = self.record.resume_step == sf.RESUME_CHAPTER_END
        self._flags_note.configure(text=(
            "This file was saved at the end of a chapter: starting the next one clears every chapter flag "
            "below, so their bits are leftovers of the finished chapter." if stale else
            "Chapter flags are named from the script of the file's map.")
            + " Double-click a flag (or press Space) to switch it.")
        for slot, on in enumerate(bits):
            name = names[slot]
            meaning = ef.FE10_FLAGS.glosses.get(name, "") if name else "No name in this chapter"
            if name == ef.FE10_FLAGS.reserved_global:
                meaning = "Reserved, unused"
            if stale and slot >= n_globals:
                meaning = ("stale - " + meaning) if meaning else "stale"
            if not on and name is None:
                continue
            tree.insert("", "end", iid=str(slot), values=(ON if on else OFF, slot, name or "", meaning),
                        tags=() if name else ("muted",))

    def _toggle_flag(self) -> None:
        sel = self._flag_tree.selection()
        if not sel or not self._has("BMST"):
            return
        slot = int(sel[0])
        on = not self.record.script_flags()[slot]
        self.record.set_script_flag(slot, on)
        self._flag_tree.set(sel[0], "on", ON if on else OFF)
        self.page.sync()

    # -- system / raw ---------------------------------------------------------------------
    def _fill_system(self) -> None:
        self._fill_system_bits()
        tree = self._system_records
        tree.delete(*tree.get_children())
        if not self._system_ok():
            return
        data = self.save.system.system_part("Records at +0xDC")
        for i in range(sf.SYSTEM_RECORD_COUNT):
            row = data[i * sf.SYSTEM_RECORD_SIZE:(i + 1) * sf.SYSTEM_RECORD_SIZE]
            tree.insert("", "end", iid=str(i), values=(i + 1, row.hex(" ")))

    def _fill_system_bits(self) -> None:
        if not self._system_ok():
            self._bit_list.fill([], lambda i: False, lambda i, on: None)
            return
        system, name = self.save.system, self._bits_var.get()
        start = next(p[1] for p in sf.SYSTEM_PARTS if p[0] == name)
        rows = [(i, f"+0x{start + (i >> 3):X} bit 0x{1 << (i & 7):02X}")
                for i in range(8 * len(system.system_part(name)))]

        def get(i: int) -> bool:
            return bool(system.system_part(name)[i >> 3] & (1 << (i & 7)))

        def set_(i: int, on: bool) -> None:
            data = bytearray(system.system_part(name))
            data[i >> 3] = data[i >> 3] | (1 << (i & 7)) if on else data[i >> 3] & ~(1 << (i & 7))
            system.set_system_part(name, bytes(data))
            self.page.sync()
        self._bit_list.fill(rows, get, set_)

    def _fill_sections(self) -> None:
        tree = self._section_tree
        tree.delete(*tree.get_children())
        if self.record is not None:
            for i, section in enumerate(self.record.sections):
                tree.insert("", "end", iid=str(i), values=(section.name, f"0x{section.data_offset:05X}",
                                                           f"{section.size} (0x{section.size:X})"))
        self._fill_raw()

    def _fill_raw(self) -> None:
        text = self._raw_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        sel = self._section_tree.selection()
        if self.record is not None:
            if sel:
                section = self.record.sections[int(sel[0])]
                data, base = self.record.section_bytes(section.name), section.data_offset
            else:
                data, base = self.record.build(), 0
                data = data[:len(data.rstrip(b"\xff")) + 16]
            text.insert("1.0", "\n".join(f"{base + o:06X}  {data[o:o + 16].hex(' ')}"
                                         for o in range(0, len(data), 16)))
        text.configure(state="disabled")

    # -- chapter start ------------------------------------------------------------------------
    def _start_chapter(self) -> None:
        database = self._database()
        if not self._has("BMST"):
            return
        if database is None:
            messagebox.showinfo("Start a chapter", "Open an extracted Radiant Dawn workspace first: the chapter "
                                "list comes from its FE10Data.", parent=self.page)
            return
        chapters = sorted((row for row in database.table("chapter") if row.values.get("number")),
                          key=lambda row: row.values["number"])
        current = next((i for i, row in enumerate(chapters) if row.values["number"] == self.record.chapter_number), 0)
        answer = simpledialog.askstring("Start a chapter", "Chapter id to start from its opening (C0401 is 4-P):",
                                        initialvalue=chapters[current].values["cid"], parent=self.page)
        if not answer:
            return
        chosen = next((i for i, row in enumerate(chapters) if row.values["cid"].lower() == answer.strip().lower()),
                      None)
        if chosen is None:
            known = ", ".join(row.values["cid"] for row in chapters[:12])
            messagebox.showerror("Start a chapter", f"No chapter {answer!r}. Known: {known}…", parent=self.page)
            return
        target, before = chapters[chosen], chapters[chosen - 1] if chosen else chapters[chosen]
        affinity = next((row.index for row in database.table("affinity")
                         if row.values.get("affinity") == target.values.get("affinity")), 0)
        try:
            self.record.start_at_chapter(target.values["number"], before.values.get("map") or target.values["map"],
                                         affinity)
        except ValueError as exc:
            messagebox.showerror("Start a chapter", str(exc), parent=self.page)
            return
        self.page.mark_dirty()
