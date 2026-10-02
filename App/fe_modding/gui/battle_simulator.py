"""Battle simulator: pick two units and their weapons, adjust them, read the
forecast and run the fight with random or fixed outcomes.

Each side starts from a character (at base level, in its own class or
another) or a bare class, read from the shared ``FE8Data.bin`` session.
Stats, current HP, Con, skills, terrain and a few flags can then be changed;
those changes live in the simulator only and are never written to the game.

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
from ..battle_sim.units import STAT_NAMES, Combatant, weapon_from_item
from ..formats import fe8data
from ..formats.fe9_message_scene import to_display
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .fe8_session import Fe8DataSession

#: Weapon types the simulator offers (staves are filtered out by might).
COMBAT_WEAPON_TYPES = ("sword", "lance", "axe", "bow", "knife", "flame", "thunder", "wind", "rod", "fang")
SIDE_NAMES = ("Attacker", "Defender")
RERUN_DELAY_MS = 120


class _Names:
    """Display names from ``system.cmp``'s message texts, with the label as fallback."""

    def __init__(self, project: ModProject):
        self._project = project
        self._texts: Optional[dict] = None

    def text(self, key: Optional[str]) -> str:
        if not key:
            return ""
        if self._texts is None:
            path = self._project.extracted_dir / "files" / "system.cmp"
            try:
                self._texts = fe8data.read_message_texts(path) if path.exists() else {}
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
    """One combatant's settings."""

    def __init__(self, sim: "BattleSimulator", index: int):
        super().__init__(sim._sides_frame, text=SIDE_NAMES[index], padding=8)
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
        self.boss = tk.BooleanVar(value=False)
        self.blessed = tk.BooleanVar(value=False)
        self.status = tk.BooleanVar(value=False)
        self.skills: list[str] = []

        row = ttk.Frame(self)
        row.pack(fill="x")
        for value, text in (("character", "Character"), ("class", "Class only")):
            ttk.Radiobutton(row, text=text, value=value, variable=self.source,
                            command=self._source_changed).pack(side="left", padx=(0, 8))
        self._unit_box = self._combo("Unit", self.unit, lambda: self._unit_changed(keep_class=False))
        self._class_box = self._combo("Class", self.cls, self._unit_changed)
        self._weapon_box = self._combo("Weapon", self.weapon, self.sim.rerun)
        ttk.Checkbutton(self, text="List every weapon, not just the class's types", variable=self.all_weapons,
                        command=self._fill_weapons).pack(anchor="w")

        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(8, 0))
        for i, name in enumerate(STAT_NAMES + ["Con", "Cur HP"]):
            ttk.Label(grid, text=name, style="Muted.TLabel").grid(row=0, column=i, padx=2)
        for i, var in enumerate(self.stats + [self.con, self.hp]):
            spin = ttk.Spinbox(grid, from_=0, to=255, width=4, textvariable=var, command=self.sim.rerun)
            spin.grid(row=1, column=i, padx=2)
            spin.bind("<KeyRelease>", lambda _e: self.sim.rerun())

        skills = ttk.Frame(self)
        skills.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Label(skills, text="Skills", style="Muted.TLabel").pack(anchor="w")
        self._skill_list = tk.Listbox(skills, height=5, exportselection=False)
        self._skill_list.pack(fill="both", expand=True)
        add = ttk.Frame(skills)
        add.pack(fill="x", pady=(4, 0))
        self._skill_add = ttk.Combobox(add, state="readonly")
        self._skill_add.pack(side="left", fill="x", expand=True)
        ttk.Button(add, text="Add", command=self._add_skill).pack(side="left", padx=(4, 0))
        ttk.Button(add, text="Remove", command=self._remove_skill).pack(side="left", padx=(4, 0))

        self._terrain_box = self._combo("Terrain", self.terrain, self.sim.rerun)
        flags = ttk.Frame(self)
        flags.pack(fill="x", pady=(4, 0))
        for text, var in (("Boss", self.boss), ("Blessed armour", self.blessed), ("Status condition", self.status)):
            ttk.Checkbutton(flags, text=text, variable=var, command=self.sim.rerun).pack(side="left", padx=(0, 8))
        ttk.Button(self, text="Reset from game data", command=self._unit_changed).pack(anchor="w", pady=(8, 0))

    def _combo(self, label: str, var, on_change) -> ttk.Combobox:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text=label, width=8).pack(side="left")
        box = ttk.Combobox(row, textvariable=var, state="readonly", height=24)
        box.pack(side="left", fill="x", expand=True)
        box.bind("<<ComboboxSelected>>", lambda _e: on_change())
        return box

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

    def _unit_changed(self, keep_class: bool = True) -> None:
        """Reload the stats, skills and weapons from the game data."""
        fe8 = self.sim.fe8
        if fe8 is None:
            return
        char = self._character() if self.source.get() == "character" else None
        if char is not None and (not keep_class or not self.cls.get()):
            cls = next((c for c in fe8.classes if c.jid == char.jid), None)
            if cls is not None:
                self.cls.set(self.sim.names.cls(cls))
        if self.source.get() == "class" and not self.cls.get() and self._class_box["values"]:
            self.cls.set(self._class_box["values"][0])
        jid = _label_id(self.cls.get()) or None
        try:
            if char is not None:
                base = battle_sim.from_character(fe8, char.pid, jid=jid)
            else:
                base = battle_sim.from_class(fe8, jid)
        except KeyError:
            return
        self._loading = True
        for var, value in zip(self.stats, base.stats):
            var.set(value)
        self.hp.set(base.hp)
        self.con.set(base.build)
        self.skills = list(base.skills)
        self._loading = False
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
            self.weapon.set(values[1] if len(values) > 1 else values[0])
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
        self._session = session or Fe8DataSession(project, changelog)
        self.names = _Names(project)
        self.rules = rules_fe9.Fe9Rules()
        self.terrains: list = []
        self._choices: dict = {}  # fixed mode: (strike, kind) -> bool
        self._log: Optional[battle_sim.BattleLog] = None
        self._pending = None
        self.mode = tk.StringVar(value="random")
        self.seed = tk.StringVar(value="1")
        self.distance = tk.IntVar(value=1)

        ttk.Label(self, text="Battle Simulator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Path of Radiance rules. Changes here stay in the simulator; nothing is written "
                             "to the game.", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self._sides_frame = body
        self.sides = [_Side(self, 0), _Side(self, 1)]
        self.sides[0].grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        middle = ttk.Frame(body)
        middle.grid(row=0, column=1, sticky="nsew", padx=6)
        self.sides[1].grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_middle(middle)

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
    def _build_middle(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x")
        ttk.Label(top, text="Distance").pack(side="left")
        ttk.Spinbox(top, from_=1, to=10, width=3, textvariable=self.distance, command=self.rerun).pack(
            side="left", padx=(4, 12))
        ttk.Button(top, text="Swap sides", command=self._swap).pack(side="left")

        forecast = ttk.LabelFrame(parent, text="Forecast", padding=8)
        forecast.pack(fill="x", pady=(8, 0))
        self._forecast_cells = {}
        rows = ("HP", "Atk", "Damage", "Hit", "Crit", "Attack speed", "Strikes")
        for c, name in enumerate(("", SIDE_NAMES[0], SIDE_NAMES[1])):
            ttk.Label(forecast, text=name, style="Muted.TLabel").grid(row=0, column=c, sticky="w", padx=6)
        for r, name in enumerate(rows, start=1):
            ttk.Label(forecast, text=name).grid(row=r, column=0, sticky="w", padx=6)
            for side in (0, 1):
                cell = ttk.Label(forecast, text="-")
                cell.grid(row=r, column=side + 1, sticky="w", padx=6)
                self._forecast_cells[(name, side)] = cell
        self._forecast_note = ttk.Label(
            forecast, style="Muted.TLabel", wraplength=320, justify="left",
            text="Unverified: the Hit, Avoid, Crit, attack speed and weapon triangle formulas are the community's, "
                 "not confirmed in the game code.")
        self._forecast_note.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        mode = ttk.LabelFrame(parent, text="Outcome", padding=8)
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
            row=1, column=1, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(mode, text="Clear choices", command=self._clear_choices).grid(
            row=1, column=3, sticky="w", pady=(4, 0), padx=(6, 0))

        rolls = ttk.LabelFrame(parent, text="Rolls (Fixed: double-click to flip)", padding=4)
        rolls.pack(fill="both", expand=True, pady=(8, 0))
        cols = (("strike", "#", 36), ("who", "Who", 110), ("what", "Roll", 120), ("chance", "%", 46),
                ("result", "Result", 70))
        self._rolls = ttk.Treeview(rolls, columns=[c[0] for c in cols], show="headings", height=8)
        for key, text, width in cols:
            self._rolls.heading(key, text=text)
            self._rolls.column(key, width=width, anchor="w", stretch=key == "what")
        self._rolls.pack(fill="both", expand=True)
        self._rolls.bind("<Double-1>", self._flip)

        log = ttk.LabelFrame(parent, text="Fight", padding=4)
        log.pack(fill="both", expand=True, pady=(8, 0))
        self._log_text = tk.Text(log, height=9, wrap="word", state="disabled")
        self._log_text.pack(fill="both", expand=True)

    # -- data -----------------------------------------------------------------------------------
    def _on_session_changed(self, _source) -> None:
        if self._session.fe8 is None:
            self._set_log("FE8Data.bin was not found in this project.")
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
        self._show(self._log)

    def _show(self, log: battle_sim.BattleLog) -> None:
        for side, unit in enumerate((log.attacker, log.defender)):
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

    def cleanup(self) -> None:
        self._session.unsubscribe(self._on_session_changed)
        if self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None
