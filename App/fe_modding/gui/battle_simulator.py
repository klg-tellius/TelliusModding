"""Battle simulator: pick two units and their weapons, adjust them, read the
forecast and run the fight with random or fixed outcomes, then watch it.

Each side starts from a character (in its own class or another) or a bare
class, read from the shared ``FE8Data.bin`` session. Its level can be raised
and an unpromoted unit can be promoted (at a chosen level) into its linked
class; the stats then follow the game's fixed growth mode
(:func:`fe_modding.battle_sim.units.from_character`).
Stats, current HP, Con, skills, terrain and a few flags can then be changed;
those changes live in the simulator only and are never written to the game.

The page puts the attacker above the defender on the left, and the
forecast, outcome, rolls and fight log on the right. Under the units sit the
distance, the battle scenery (a ``zbg/`` folder) and **Render fight**, which
opens :class:`.battle_window.BattleWindow` and plays the fight as the game
stages it.

The maths is :mod:`fe_modding.battle_sim` (Path of Radiance rules). In
**Random** mode the fight is rolled from a seed, so the same seed replays the
same fight. In **Fixed** mode every roll the fight asks for (each strike's
hit and crit, each skill activation) is listed and toggled by
double-clicking it; the fight is re-run after every change.
"""

from __future__ import annotations

import random
import struct
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .. import battle_sim
from ..battle_sim import rules_fe9
from ..battle_sim import units as bsu
from ..battle_sim import scene_assets as sa
from ..battle_sim.units import STAT_NAMES, Combatant, weapon_from_item
from ..formats import fe8data
from ..formats.fe9_message_scene import to_display
from ..game_profile import profile_of
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .fe8_session import Fe8DataSession
from .widgets import ScrollFrame

#: Weapon types the simulator offers (staves are filtered out by might).
COMBAT_WEAPON_TYPES = ("sword", "lance", "axe", "bow", "knife", "flame", "thunder", "wind", "rod", "fang")
SIDE_NAMES = ("Attacker", "Defender")
RERUN_DELAY_MS = 120
NO_SCENERY = "(none)"
#: The scenery picked first, when the project has it (a Crimean plain).
DEFAULT_SCENERY = "map03_ground01"


class _Names:
    """Display names from ``system.cmp``'s message texts, with the label as fallback."""

    def __init__(self, project: ModProject):
        self._project = project
        self._texts: Optional[dict] = None

    def text(self, key: Optional[str]) -> str:
        if not key:
            return ""
        if self._texts is None:
            profile = profile_of(self._project)
            path = profile.path(self._project.extracted_dir / "files", "system_archive") \
                if profile.has_file("system_archive") else None
            try:
                self._texts = fe8data.read_message_texts(path) if path is not None and path.exists() else {}
            except Exception:  # noqa: BLE001 - names are a convenience
                self._texts = {}
        text = self._texts.get(key, "").strip()
        if text and not text.isascii():
            try:
                text = to_display(text)
            except UnicodeError:
                pass
        return text

    def character(self, c) -> str:
        return f"{self.text(c.mpid) or c.pid} ({c.pid})"

    def cls(self, c) -> str:
        return f"{self.text(c.mjid) or c.jid} ({c.jid})"

    def item(self, it) -> str:
        return f"{self.text(it.miid) or it.iid} ({it.iid})"

    def skill(self, s) -> str:
        text = self.text(s.msid)
        name = text if text and text.isascii() else (s.sid or "")[4:].replace("_", " ").title()
        return f"{name} ({s.sid})"


def _label_id(text: str) -> str:
    """The label in a "Name (LABEL)" choice."""
    return text[text.rfind("(") + 1:-1] if text.endswith(")") else text


class _Side(ttk.LabelFrame):
    """One combatant's settings, laid out in a few compact rows."""

    def __init__(self, sim: "BattleSimulator", parent: tk.Misc, index: int):
        super().__init__(parent, text=SIDE_NAMES[index], padding=(10, 6))
        self.sim, self.index = sim, index
        self._loading = False
        self.source = tk.StringVar(value="character")
        self.unit = tk.StringVar()
        self.cls = tk.StringVar()
        self.weapon = tk.StringVar()
        self.all_weapons = tk.BooleanVar(value=False)
        self.terrain = tk.StringVar()
        self.hp = tk.IntVar(value=1)
        self.con = tk.IntVar(value=0)
        self.stats = [tk.IntVar(value=0) for _ in STAT_NAMES]
        self.level = tk.IntVar(value=1)
        self.promoted = tk.BooleanVar(value=False)
        self.promoted_at = tk.IntVar(value=bsu.MAX_LEVEL)
        self.boss = tk.BooleanVar(value=False)
        self.blessed = tk.BooleanVar(value=False)
        self.status = tk.BooleanVar(value=False)
        self.skills: list[str] = []
        self.columnconfigure(1, weight=1)
        self.columnconfigure(3, weight=1)

        row = ttk.Frame(self)
        row.grid(row=0, column=0, columnspan=4, sticky="ew")
        for value, text in (("character", "Character"), ("class", "Class only")):
            ttk.Radiobutton(row, text=text, value=value, variable=self.source,
                            command=self._source_changed).pack(side="left", padx=(0, 10))
        ttk.Button(row, text="Reset from game data", command=self._unit_changed).pack(side="right")

        self._unit_box = self._combo(1, 0, "Unit", self.unit, lambda: self._unit_changed(keep_class=False), span=3)
        self._class_box = self._combo(2, 0, "Class", self.cls, self._class_selected)
        self._terrain_box = self._combo(2, 2, "Terrain", self.terrain, self.sim.rerun)
        levels = ttk.Frame(self)
        levels.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(levels, text="Level", width=8).pack(side="left")
        self._level_entry = self._small_entry(levels, self.level, self._level_changed)
        self._level_entry.pack(side="left")
        self._promoted_check = ttk.Checkbutton(levels, text="Promoted", variable=self.promoted,
                                               command=self._promotion_changed)
        self._promoted_check.pack(side="left", padx=(14, 0))
        self._at_label = ttk.Label(levels, text="at level")
        self._at_label.pack(side="left", padx=(8, 4))
        self._at_entry = self._small_entry(levels, self.promoted_at, self._level_changed)
        self._at_entry.pack(side="left")
        ttk.Label(levels, text="fixed growth", style="Caption.TLabel").pack(side="left", padx=(12, 0))

        self._weapon_box = self._combo(4, 0, "Weapon", self.weapon, self.sim.rerun)
        ttk.Checkbutton(self, text="Any weapon type", variable=self.all_weapons,
                        command=self._fill_weapons).grid(row=4, column=2, columnspan=2, sticky="w", padx=(10, 0))

        grid = ttk.Frame(self)
        grid.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
        for i, (name, var) in enumerate(zip(STAT_NAMES + ["Con", "Cur HP"], self.stats + [self.con, self.hp])):
            ttk.Label(grid, text=name, style="Caption.TLabel").grid(row=0, column=i, padx=(0, 6), sticky="w")
            entry = ttk.Entry(grid, width=4, textvariable=var, justify="center")
            entry.grid(row=1, column=i, padx=(0, 6), sticky="w")
            entry.bind("<KeyRelease>", lambda _e: self.sim.rerun())
            entry.bind("<Up>", lambda _e, v=var: self._nudge(v, 1))
            entry.bind("<Down>", lambda _e, v=var: self._nudge(v, -1))

        skills = ttk.Frame(self)
        skills.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        skills.columnconfigure(1, weight=1)
        ttk.Label(skills, text="Skills", width=8).grid(row=0, column=0, sticky="nw")
        self._skill_list = tk.Listbox(skills, height=3, exportselection=False, activestyle="none")
        self._skill_list.grid(row=0, column=1, rowspan=2, sticky="ew")
        self._skill_add = ttk.Combobox(skills, state="readonly", width=24, height=24)
        self._skill_add.grid(row=0, column=2, columnspan=2, sticky="ew", padx=(8, 0))
        ttk.Button(skills, text="Add", command=self._add_skill).grid(row=1, column=2, sticky="ew", padx=(8, 0),
                                                                   pady=(4, 0))
        ttk.Button(skills, text="Remove", command=self._remove_skill).grid(row=1, column=3, sticky="ew",
                                                                         padx=(4, 0), pady=(4, 0))

        flags = ttk.Frame(self)
        flags.grid(row=7, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for text, var in (("Boss", self.boss), ("Blessed armour", self.blessed), ("Status condition", self.status)):
            ttk.Checkbutton(flags, text=text, variable=var, command=self.sim.rerun).pack(side="left", padx=(0, 12))

    def _combo(self, row: int, column: int, label: str, var, on_change, span: int = 1) -> ttk.Combobox:
        ttk.Label(self, text=label, width=8 if column == 0 else 0).grid(
            row=row, column=column, sticky="w", pady=(6, 0), padx=(0 if column == 0 else 10, 4))
        box = ttk.Combobox(self, textvariable=var, state="readonly", height=24, width=20)
        box.grid(row=row, column=column + 1, columnspan=span, sticky="ew", pady=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda _e: on_change())
        return box

    def _nudge(self, var, step: int) -> str:
        try:
            var.set(max(0, min(255, int(var.get()) + step)))
        except (tk.TclError, ValueError):
            var.set(0)
        self.sim.rerun()
        return "break"

    def _small_entry(self, parent: tk.Misc, var, on_change) -> ttk.Entry:
        """A 4-wide number entry: Up/Down step it, Return or leaving it applies it."""
        entry = ttk.Entry(parent, width=4, textvariable=var, justify="center")

        def step(delta: int) -> str:
            try:
                var.set(int(var.get()) + delta)
            except (tk.TclError, ValueError):
                pass
            on_change()
            return "break"

        entry.bind("<Up>", lambda _e: step(1))
        entry.bind("<Down>", lambda _e: step(-1))
        entry.bind("<Return>", lambda _e: on_change())
        entry.bind("<FocusOut>", lambda _e: on_change())
        return entry

    # -- choices --------------------------------------------------------------------------------
    def fill(self) -> None:
        fe8, names = self.sim.fe8, self.sim.names
        if fe8 is None:
            return
        self._unit_box["values"] = [names.character(c) for c in fe8.characters if c.pid]
        self._class_box["values"] = [names.cls(c) for c in fe8.classes if c.jid]
        self._skill_add["values"] = [names.skill(s) for s in fe8.skills if s.sid]
        self._terrain_box["values"] = ["None"] + [
            f"{names.text(t.name_key) or t.name} ({t.avoid}/{t.defense}/{t.resistance})" for t in self.sim.terrains]
        self.terrain.set("None")
        if not self.unit.get() and self._unit_box["values"]:
            self.unit.set(self._unit_box["values"][min(self.index, len(self._unit_box["values"]) - 1)])
        self._source_changed()

    def _source_changed(self) -> None:
        self._unit_box.configure(state="readonly" if self.source.get() == "character" else "disabled")
        self._unit_changed(keep_class=False)

    def _character(self):
        pid = _label_id(self.unit.get())
        return next((c for c in self.sim.fe8.characters if c.pid == pid), None)

    def _class_entry(self, jid: Optional[str]):
        return next((c for c in self.sim.fe8.classes if c.jid == jid), None) if jid else None

    def _start_class(self):
        """The class the unit levels in before any promotion: the character's own class, or in
        class mode the unpromoted class of the selected promoted one."""
        fe8 = self.sim.fe8
        char = self._character() if self.source.get() == "character" else None
        if char is not None:
            return self._class_entry(char.jid)
        cls = self._class_entry(_label_id(self.cls.get()))
        linked = bsu.linked_class(fe8, cls)
        if bsu.class_kind(fe8, cls) == "Promoted" and bsu.promotion_of(fe8, linked) is cls:
            return linked
        return cls

    def _promotion_path(self) -> bool:
        """True when the unit levels in its start class, then promotes into the selected one."""
        start = self._start_class()
        return (self.promoted.get() and start is not None and bsu.class_kind(self.sim.fe8, start) == "Unpromoted"
                and _label_id(self.cls.get()) not in (None, "", start.jid))

    def _class_selected(self) -> None:
        cls = self._class_entry(_label_id(self.cls.get()))
        start = self._start_class()
        self.promoted.set(bsu.class_kind(self.sim.fe8, cls) == "Promoted")
        if start is not None and bsu.class_kind(self.sim.fe8, start) == "Promoted":
            self.promoted.set(True)
        self._unit_changed()

    def _promotion_changed(self) -> None:
        """Switch to the start class's promotion, or back to the start class."""
        start = self._start_class()
        target = bsu.promotion_of(self.sim.fe8, start) if self.promoted.get() else start
        if target is not None:
            self.cls.set(self.sim.names.cls(target))
        self._unit_changed()

    def _level_bounds(self) -> tuple[int, int]:
        char = self._character() if self.source.get() == "character" else None
        low = 1 if self._promotion_path() or char is None else char.level
        return max(1, min(low, bsu.MAX_LEVEL)), bsu.MAX_LEVEL

    def _clamp_levels(self) -> None:
        low, high = self._level_bounds()
        for var, lo, default in ((self.level, low, low), (self.promoted_at, bsu.PROMOTION_LEVEL, high)):
            try:
                value = int(var.get())
            except (tk.TclError, ValueError):
                value = default
            var.set(max(lo, min(high, value)))
        char = self._character() if self.source.get() == "character" else None
        if char is not None and self.promoted_at.get() < char.level:
            self.promoted_at.set(min(high, char.level))

    def _build(self) -> Optional[Combatant]:
        """The unit from the game data at the chosen level, class and promotion."""
        fe8 = self.sim.fe8
        char = self._character() if self.source.get() == "character" else None
        jid = _label_id(self.cls.get()) or None
        self._clamp_levels()
        path = self._promotion_path()
        try:
            if char is not None:
                return battle_sim.from_character(fe8, char.pid, jid=jid, level=self.level.get(),
                                                 promoted_at=self.promoted_at.get() if path else None)
            start = self._start_class()
            return battle_sim.from_class(fe8, jid, level=self.level.get(),
                                         promoted_from=start.jid if path else None,
                                         promoted_at=self.promoted_at.get())
        except KeyError:
            return None

    def _refresh_promotion_controls(self) -> None:
        fe8 = self.sim.fe8
        start = self._start_class()
        kind = bsu.class_kind(fe8, start)
        can_promote = kind == "Unpromoted" and bsu.promotion_of(fe8, start) is not None
        if kind == "Promoted":
            self.promoted.set(True)
        self._promoted_check.configure(state="normal" if can_promote else "disabled")
        path = self._promotion_path()
        self._at_entry.configure(state="normal" if path else "disabled")
        self._at_label.configure(state="normal" if path else "disabled")

    def _set_stats(self, base: Combatant) -> None:
        self._loading = True
        for var, value in zip(self.stats, base.stats):
            var.set(value)
        self.hp.set(base.hp)
        self.con.set(base.build)
        self._loading = False

    def _level_changed(self) -> None:
        """Recompute the stats for the new level; skills and weapon stay as they are."""
        if self.sim.fe8 is None or not hasattr(self, "_base"):
            return
        base = self._build()
        if base is None:
            return
        self._set_stats(base)
        base.skills = list(self.skills)
        self._base = base
        self.sim.rerun()

    def _unit_changed(self, keep_class: bool = True) -> None:
        """Reload the stats, skills and weapons from the game data."""
        fe8 = self.sim.fe8
        if fe8 is None:
            return
        char = self._character() if self.source.get() == "character" else None
        if char is not None and (not keep_class or not self.cls.get()):
            cls = self._class_entry(char.jid)
            if cls is not None:
                self.cls.set(self.sim.names.cls(cls))
        if self.source.get() == "class" and not self.cls.get() and self._class_box["values"]:
            self.cls.set(self._class_box["values"][0])
        if not keep_class:
            self.level.set(char.level if char is not None else 1)
            self.promoted_at.set(bsu.MAX_LEVEL)
            self.promoted.set(bsu.class_kind(fe8, self._class_entry(_label_id(self.cls.get()))) == "Promoted")
        self._refresh_promotion_controls()
        base = self._build()
        if base is None:
            return
        self._set_stats(base)
        self.skills = list(base.skills)
        self._base = base
        self._fill_skills()
        self._fill_weapons()

    def _fill_skills(self) -> None:
        by_sid = {s.sid: s for s in self.sim.fe8.skills}
        self._skill_list.delete(0, "end")
        for sid in self.skills:
            entry = by_sid.get(sid)
            name = self.sim.names.skill(entry) if entry else sid
            key = self.sim.rules.skill_key(sid)
            self._skill_list.insert("end", name + ("" if key else "  - no battle effect"))

    def _add_skill(self) -> None:
        sid = _label_id(self._skill_add.get())
        if sid and sid not in self.skills:
            self.skills.append(sid)
            self._fill_skills()
            self.sim.rerun()

    def _remove_skill(self) -> None:
        for i in reversed(self._skill_list.curselection()):
            del self.skills[i]
        self._fill_skills()
        self.sim.rerun()

    def _fill_weapons(self) -> None:
        fe8 = self.sim.fe8
        cls = next((c for c in fe8.classes if c.jid == _label_id(self.cls.get())), None)
        ranks = fe8data.class_weapon_rank_map(cls) if cls is not None and not self.all_weapons.get() else None
        items = [it for it in fe8.items
                 if it.iid and it.weapon_type in COMBAT_WEAPON_TYPES and (it.might or it.weapon_type != "rod")]
        if ranks is not None:
            usable = {t.lower() for t in ranks}
            filtered = [it for it in items if self._rank_columns(it) & usable]
            if cls.innate_weapon:
                filtered += [it for it in items if it.iid == cls.innate_weapon and it not in filtered]
            items = filtered or items
        values = ["(unarmed)"] + [self.sim.names.item(it) for it in items]
        self._weapon_box["values"] = values
        if self.weapon.get() not in values:
            # laguz start on their class's natural weapon (equip_innate_laguz_weapon)
            innate = next((it for it in items if cls is not None and it.iid == cls.innate_weapon), None)
            self.weapon.set(self.sim.names.item(innate) if innate is not None else
                            (values[1] if len(values) > 1 else values[0]))
        self.sim.rerun()

    @staticmethod
    def _rank_columns(item) -> set:
        """The class rank columns (WEAPON_TYPE_NAMES, lower case) that may wield an item; knives
        go with swords, light tomes with either magic-adjacent column (see fe8data.WEAPON_TYPE_NAMES)."""
        return {"flame": {"fire"}, "rod": {"light", "staff"}, "knife": {"sword"}}.get(
            item.weapon_type, {item.weapon_type})

    # -- result -----------------------------------------------------------------------------------
    def combatant(self) -> Optional[Combatant]:
        if self.sim.fe8 is None or self._loading or not hasattr(self, "_base"):
            return None
        try:
            stats = [max(0, int(v.get())) for v in self.stats]
            hp, con = int(self.hp.get()), int(self.con.get())
        except (tk.TclError, ValueError):
            return None
        stats[0] = max(1, stats[0])
        unit = self._base.copy()
        unit.name = self.unit.get().split(" (")[0] if self.source.get() == "character" else \
            self.cls.get().split(" (")[0]
        unit.stats, unit.hp, unit.build = stats, max(1, min(hp, stats[0])), con
        unit.skills = list(self.skills)
        iid = _label_id(self.weapon.get())
        item = next((it for it in self.sim.fe8.items if it.iid == iid), None)
        unit.weapon = weapon_from_item(item) if item is not None else None
        terrain = self._terrain_box.current()
        if terrain > 0:
            t = self.sim.terrains[terrain - 1]
            unit.terrain = (t.avoid, t.defense, t.resistance)
        unit.boss, unit.blessed_armor, unit.status_condition = self.boss.get(), self.blessed.get(), self.status.get()
        return unit


class BattleSimulator(EditorPanel):
    display_name = "Battle simulator"
    uses_fe8_session = True

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog,
                 session: Fe8DataSession | None = None):
        super().__init__(parent, padding=12)
        self._project = project
        self._files = project.extracted_dir / "files"
        self._session = session or Fe8DataSession(project, changelog)
        self.names = _Names(project)
        self.rules = rules_fe9.Fe9Rules()
        self.terrains: list = []
        self._choices: dict = {}  # fixed mode: (strike, kind) -> bool
        self._log: Optional[battle_sim.BattleLog] = None
        self._distance = 1
        self._pending = None
        self._window = None  # battle_window.BattleWindow, made on the first render
        self.mode = tk.StringVar(value="random")
        self.seed = tk.StringVar(value="1")
        self.distance = tk.IntVar(value=1)
        self.scenery = tk.StringVar(value=NO_SCENERY)

        ttk.Label(self, text="Battle Simulator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Path of Radiance rules. Changes here stay in the simulator; nothing is written "
                             "to the game.", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3, uniform="half")
        body.columnconfigure(1, weight=2, uniform="half")
        body.rowconfigure(0, weight=1)

        left = ScrollFrame(body, padding=(0, 0, 8, 0))
        left.grid(row=0, column=0, sticky="nsew")
        self.sides = [_Side(self, left.body, 0), _Side(self, left.body, 1)]
        self.sides[0].pack(fill="x")
        self._build_battle_bar(left.body)
        self.sides[1].pack(fill="x")

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self._build_results(right)

        self._session.subscribe(self._on_session_changed)
        self._on_session_changed(None)

    def select_character(self, pid: str, side: int = 0) -> None:
        """Put character ``pid`` on ``side`` (0 attacker, 1 defender)."""
        if self.fe8 is None:
            return
        char = next((c for c in self.fe8.characters if c.pid == pid), None)
        if char is None:
            return
        s = self.sides[side]
        s.source.set("character")
        s.unit.set(self.names.character(char))
        s._source_changed()

    @property
    def fe8(self):
        return self._session.fe8

    # -- layout ---------------------------------------------------------------------------------
    def _build_battle_bar(self, parent: tk.Misc) -> None:
        bar = ttk.Frame(parent, padding=(0, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="Distance").pack(side="left")
        ttk.Spinbox(bar, from_=1, to=10, width=3, textvariable=self.distance, command=self.rerun).pack(
            side="left", padx=(4, 12))
        ttk.Label(bar, text="Scenery").pack(side="left")
        self._scenery_box = ttk.Combobox(bar, textvariable=self.scenery, state="readonly", width=20, height=24)
        self._scenery_box.pack(side="left", padx=(4, 12))
        ttk.Button(bar, text="Swap sides", command=self._swap).pack(side="left")
        self._render_button = ttk.Button(bar, text="Render fight", style="Accent.TButton", command=self._render)
        self._render_button.pack(side="right")

    def _build_results(self, parent: tk.Misc) -> None:
        forecast = ttk.LabelFrame(parent, text="Forecast", padding=(10, 6))
        forecast.pack(fill="x")
        self._forecast_cells = {}
        self._forecast_heads = []
        rows = ("HP", "Atk", "Damage", "Hit", "Crit", "Attack speed", "Strikes")
        forecast.columnconfigure(1, weight=1, uniform="fc")
        forecast.columnconfigure(2, weight=1, uniform="fc")
        for c in (1, 2):
            head = ttk.Label(forecast, text=SIDE_NAMES[c - 1], style="Strong.TLabel")
            head.grid(row=0, column=c, sticky="w", padx=6)
            self._forecast_heads.append(head)
        for r, name in enumerate(rows, start=1):
            ttk.Label(forecast, text=name, style="Muted.TLabel").grid(row=r, column=0, sticky="w", padx=(0, 6))
            for side in (0, 1):
                cell = ttk.Label(forecast, text="-")
                cell.grid(row=r, column=side + 1, sticky="w", padx=6)
                self._forecast_cells[(name, side)] = cell
        ttk.Label(forecast, style="Caption.TLabel", wraplength=360, justify="left",
                  text="Unverified: the Hit, Avoid, Crit, attack speed and weapon triangle formulas are the "
                       "community's, not confirmed in the game code.").grid(
            row=len(rows) + 1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        mode = ttk.LabelFrame(parent, text="Outcome", padding=(10, 6))
        mode.pack(fill="x", pady=(8, 0))
        ttk.Radiobutton(mode, text="Random", value="random", variable=self.mode, command=self.rerun).grid(
            row=0, column=0, sticky="w")
        ttk.Label(mode, text="Seed").grid(row=0, column=1, padx=(8, 2))
        seed = ttk.Entry(mode, textvariable=self.seed, width=10)
        seed.grid(row=0, column=2)
        seed.bind("<KeyRelease>", lambda _e: self.rerun())
        ttk.Button(mode, text="Reroll", command=self._reroll).grid(row=0, column=3, padx=(6, 0))
        ttk.Radiobutton(mode, text="Fixed", value="fixed", variable=self.mode, command=self.rerun).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(mode, text="Fix this fight", command=self._fix_current).grid(
            row=1, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(4, 0))
        ttk.Button(mode, text="Clear choices", command=self._clear_choices).grid(
            row=1, column=3, sticky="w", pady=(4, 0), padx=(6, 0))

        rolls = ttk.LabelFrame(parent, text="Rolls (Fixed: double-click to flip)", padding=4)
        rolls.pack(fill="both", expand=True, pady=(8, 0))
        cols = (("strike", "#", 32), ("who", "Who", 100), ("what", "Roll", 100), ("chance", "%", 40),
                ("result", "Result", 70))
        self._rolls = ttk.Treeview(rolls, columns=[c[0] for c in cols], show="headings", height=6)
        for key, text, width in cols:
            self._rolls.heading(key, text=text)
            self._rolls.column(key, width=width, minwidth=width, anchor="w", stretch=key in ("who", "what"))
        self._rolls.pack(fill="both", expand=True)
        self._rolls.bind("<Double-1>", self._flip)

        log = ttk.LabelFrame(parent, text="Fight", padding=4)
        log.pack(fill="both", expand=True, pady=(8, 0))
        self._log_text = tk.Text(log, height=7, wrap="word", state="disabled", relief="flat")
        self._log_text.pack(fill="both", expand=True)

    # -- data -----------------------------------------------------------------------------------
    def _on_session_changed(self, _source) -> None:
        self._fill_sceneries()
        if self._session.fe8 is None:
            self._set_log(self._session.unavailable_reason)
            return
        try:
            game = fe8data.read_game_data(self._session.data)
        except (KeyError, ValueError, IndexError, struct.error):
            game = {}
        bonus = game.get("class_critical_bonus", (rules_fe9.CLASS_CRIT_BONUS,))[0]
        self.rules = rules_fe9.Fe9Rules(self.fe8.skills, class_crit_bonus=bonus)
        try:
            self.terrains = fe8data.read_terrain_types(self._session.data)
        except (KeyError, ValueError, IndexError, struct.error):
            self.terrains = []
        for side in self.sides:
            side.fill()

    def _fill_sceneries(self) -> None:
        names = list(sa.BattleAssets(self._files, b"").sceneries())
        self._scenery_box["values"] = [NO_SCENERY] + names
        if self.scenery.get() not in names:
            self.scenery.set(DEFAULT_SCENERY if DEFAULT_SCENERY in names else (names[0] if names else NO_SCENERY))

    def _swap(self) -> None:
        a, b = self.sides
        state = [(s.source.get(), s.unit.get(), s.cls.get(), s.weapon.get()) for s in (a, b)]
        for side, (source, unit, cls, weapon) in zip((b, a), state):
            side.source.set(source)
            side.unit.set(unit)
            side.cls.set(cls)
            side._unit_changed()
            side.weapon.set(weapon)
        self.rerun()

    def _reroll(self) -> None:
        self.mode.set("random")
        self.seed.set(str(random.randrange(1, 1_000_000)))
        self.rerun()

    def _fix_current(self) -> None:
        if self._log is not None:
            self._choices = {(d.strike, d.kind): d.result for d in self._log.decisions}
        self.mode.set("fixed")
        self.rerun()

    def _clear_choices(self) -> None:
        self._choices.clear()
        self.rerun()

    def _flip(self, event) -> None:
        if self.mode.get() != "fixed" or self._log is None:
            return
        row = self._rolls.identify_row(event.y)
        if not row:
            return
        d = self._log.decisions[int(row)]
        self._choices[(d.strike, d.kind)] = not d.result
        self.rerun()

    # -- run ------------------------------------------------------------------------------------
    def rerun(self) -> None:
        if self._pending is not None:
            self.after_cancel(self._pending)
        self._pending = self.after(RERUN_DELAY_MS, self._run)

    def _run(self) -> None:
        self._pending = None
        units = [s.combatant() for s in self.sides]
        if any(u is None for u in units):
            return
        try:
            distance = max(1, int(self.distance.get()))
        except (tk.TclError, ValueError):
            distance = 1
        if self.mode.get() == "fixed":
            outcomes = battle_sim.FixedOutcomes(self._choices)
        else:
            try:
                seed = int(self.seed.get())
            except ValueError:
                seed = sum(map(ord, self.seed.get()))
            outcomes = battle_sim.RngOutcomes(seed)
        self._log = battle_sim.simulate(units[0], units[1], rules=self.rules, outcomes=outcomes, distance=distance)
        self._distance = distance
        self._show(self._log)

    def _show(self, log: battle_sim.BattleLog) -> None:
        for side, unit in enumerate((log.attacker, log.defender)):
            self._forecast_heads[side].configure(text=unit.name or SIDE_NAMES[side])
            f = log.forecast.side(side)
            values = {
                "HP": f"{log.hp_start[side]} / {unit.stats[0]}",
                "Atk": str(f.atk) + (" (effective)" if f.effective else "") if f.can_attack else "-",
                "Damage": str(f.damage) if f.can_attack else "-",
                "Hit": str(f.hit) if f.can_attack else "-",
                "Crit": str(f.crit) if f.can_attack else "-",
                "Attack speed": str(f.attack_speed),
                "Strikes": (f"{f.strikes}" + (" x2" if f.doubles else "")) if f.can_attack else "cannot attack",
            }
            for name, text in values.items():
                self._forecast_cells[(name, side)].configure(text=text)
        self._rolls.delete(*self._rolls.get_children())
        names = (log.attacker.name, log.defender.name)
        for i, d in enumerate(log.decisions):
            what = d.kind if not d.kind.startswith("proc:") else \
                rules_fe9.SKILL_NAMES.get(d.kind[5:], d.kind[5:])
            result = ("yes" if d.result else "no") + ("" if d.roll is None else f" ({d.roll})")
            fixed = "*" if (d.strike, d.kind) in self._choices else ""
            self._rolls.insert("", "end", iid=str(i),
                               values=(d.strike, names[d.side], what, d.chance, result + fixed))
        summary = log.text() or "Neither unit can attack at this distance."
        dead = log.dead
        if dead is not None:
            summary += f"\n\n{names[dead]} is defeated."
        self._set_log(summary)

    def _set_log(self, text: str) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.insert("1.0", text)
        self._log_text.configure(state="disabled")

    # -- render ---------------------------------------------------------------------------------
    def _render(self) -> None:
        """Play the current fight in the battle window, as the game stages it."""
        if self._pending is not None:
            self.after_cancel(self._pending)
            self._run()
        if self._log is None:
            return
        from .battle_window import BattleWindow

        if self._window is None or not self._window.winfo_exists():
            self._window = BattleWindow(self, self._files, self.rules, self.fe8, title="Battle Simulator - fight")
        scenery = self.scenery.get()
        self._window.play(self._log, self._distance, None if scenery == NO_SCENERY else scenery)

    def cleanup(self) -> None:
        self._session.unsubscribe(self._on_session_changed)
        if self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None
        if self._window is not None and self._window.winfo_exists():
            self._window.cleanup()
            self._window.destroy()
        self._window = None
