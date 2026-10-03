"""The Build tab's "Play..." window: play the chapter on its top-down map.

The game itself runs in :mod:`fe_modding.playthrough`; this window shows it
and drives it:

- the map is the Build tab's canvas (same backdrop, grid and zones) with the
  units of the current state; click a unit of yours, then a tile, and pick
  an action from the menu (the attack entries carry the battle forecast);
- the transport bar steps the game by a chosen granularity (one script
  instruction / message page / AI entry, one action, one AI unit, one phase,
  or until the player has to act), runs it, pauses it, and moves back and
  forward through the history; giving a command or forcing a battle's
  outcome from an earlier point drops what came after and plays on from
  there;
- the side panel shows the selected unit, the running event script (its
  instructions with the current one marked, and the function's source),
  the running AI script, the current message page, the log and the flags;
- with "Battle animations" on, each fight plays with the battle models
  (:mod:`.playthrough_battle`) before the game goes on.
"""

from __future__ import annotations

import copy
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from ..formats.cmb.decompiler import Decompiler, function_to_source
from ..playthrough import actions, combat, engine, loader, movement, setup, triggers
from ..playthrough.ai_vm import program as ai_program
from ..playthrough.event_vm import code as script_code, disassemble
from ..playthrough.simulation import ACTION, INPUT, LINE, MESSAGE, PHASE, UNIT, UNFINISHED, Simulation
from ..playthrough.state import FACTION_NAMES, PLAYER, AiTurn, MessageShow, ScriptRun
from .map_builder import FACTION_COLORS, _BuildCanvas, _dim
from .map_windows import _Window

GRANULARITIES = (("Line (instruction, message page, AI entry)", LINE), ("Message page", MESSAGE),
                 ("Action", ACTION), ("AI unit", UNIT), ("Phase", PHASE), ("Until my turn", INPUT))
DIFFICULTIES = (("Normal", "n"), ("Hard", "h"), ("Maniac", "m"))
#: Where Restart starts: turn 1 at the first command (the opening plays unseen), the opening, or a saved point.
START_TURN1, START_OPENING, START_SAVED = "Turn 1", "Chapter opening", "Saved point"
SKIP = "skip"  # the run mode that plays the opening unseen
MOVE_COLOR, ATTACK_COLOR, CANTO_COLOR, THREAT_COLOR = "#4f8fe8", "#e85a4f", "#9be84f", "#e8a24f"
RUN_BUDGET_S = 0.04
MESSAGE_DELAY_MS = 1400
STAT_LABELS = ("HP", "Str", "Mag", "Skl", "Spd", "Lck", "Def", "Res")


class _PlayCanvas(_BuildCanvas):
    """The Build canvas, with units that have acted greyed out and an HP bar under each."""

    def _draw_unit(self, unit: dict) -> None:
        x0, y0, x1, y1 = self.box(unit["x"], unit["y"])
        pad = max(2, self.cell * 0.12)
        if unit["selected"]:
            self.create_rectangle(x0, y0, x1, y1, outline="#ffe14d", width=3)
        color = _dim(unit["color"]) if unit.get("done") else unit["color"]
        self.create_oval(x0 + pad, y0 + pad, x1 - pad, y1 - pad, fill=color,
                         outline="#ffd700" if unit.get("boss") else "#101010", width=2 if unit.get("boss") else 1)
        if self.cell >= 18:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2 - 1, text=unit["text"],
                             fill="#9a9a9a" if unit.get("done") else "#ffffff",
                             font=("Segoe UI", max(6, int(self.cell / 4)), "bold"))
        frac = unit.get("hp", 1.0)
        bar_y = y1 - max(2, self.cell * 0.1)
        self.create_rectangle(x0 + pad, bar_y, x1 - pad, y1 - 1, fill="#202020", outline="")
        self.create_rectangle(x0 + pad, bar_y, x0 + pad + (x1 - x0 - 2 * pad) * frac, y1 - 1,
                              fill="#5ad15a" if frac > 0.5 else "#e8c64f" if frac > 0.25 else "#e85a4f", outline="")


class PlaythroughWindow(_Window):
    def __init__(self, builder) -> None:
        super().__init__(builder, "Play chapter", "1500x920")
        self._builder = builder
        self._project = builder._project
        self._files = self._project.extracted_dir / "files"
        self.empty_text = "Open a chapter with a map."
        self.sim: Optional[Simulation] = None
        self._selected: Optional[int] = None
        self._reach: dict = {}
        self._watch: Optional[int] = None  # a unit whose threat range is shown
        self._running: Optional[tuple] = None  # (until, start mark) while running
        self._after = None
        self._waiting_animation = False
        self._battle_window = None
        self._source_cache: dict = {}
        self._conversation = None  # (assets, renderer) once loaded, False when unavailable
        self._message_photo = None
        self._seed = tk.StringVar(value="0")
        self._difficulty = tk.StringVar(value=DIFFICULTIES[0][0])
        self._granularity = tk.StringVar(value=GRANULARITIES[1][0])
        self._animate = tk.BooleanVar(value=False)
        self._auto_messages = tk.BooleanVar(value=False)
        self._follow = tk.BooleanVar(value=True)
        self._show_zones = tk.BooleanVar(value=True)
        self._start_at = tk.StringVar(value=START_TURN1)
        self._saved_start = None  # (GameState, label) saved with "Start here"
        self._build()
        self.bind("<space>", lambda e: self.step())
        self.bind("<Left>", lambda e: self.back())
        self.bind("<Right>", lambda e: self.forward())
        self.bind("<Escape>", lambda e: self._deselect())
        self.after(50, self.restart)

    # -- layout ---------------------------------------------------------------------------------
    def _build(self) -> None:
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Button(top, text="Restart", command=self.restart).pack(side="left")
        ttk.Label(top, text="Start at").pack(side="left", padx=(10, 2))
        self._start_box = ttk.Combobox(top, textvariable=self._start_at, values=[START_TURN1, START_OPENING],
                                       state="readonly", width=15)
        self._start_box.pack(side="left")
        self._start_box.bind("<<ComboboxSelected>>", lambda e: self.restart())
        ttk.Button(top, text="Start here", command=self.save_start).pack(side="left", padx=(4, 0))
        ttk.Label(top, text="Difficulty").pack(side="left", padx=(10, 2))
        ttk.Combobox(top, textvariable=self._difficulty, values=[d for d, _ in DIFFICULTIES], state="readonly",
                     width=8).pack(side="left")
        ttk.Label(top, text="Seed").pack(side="left", padx=(10, 2))
        ttk.Entry(top, textvariable=self._seed, width=8).pack(side="left")
        ttk.Checkbutton(top, text="Battle animations", variable=self._animate).pack(side="left", padx=(14, 0))
        ttk.Checkbutton(top, text="Auto-advance messages", variable=self._auto_messages).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(top, text="Follow the running code", variable=self._follow).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(top, text="Script zones", variable=self._show_zones,
                        command=self._refresh_map).pack(side="left", padx=(8, 0))

        transport = ttk.Frame(self, padding=(8, 0, 8, 4))
        transport.pack(fill="x")
        ttk.Label(transport, text="Step by").pack(side="left")
        ttk.Combobox(transport, textvariable=self._granularity, values=[g for g, _ in GRANULARITIES],
                     state="readonly", width=36).pack(side="left", padx=(4, 8))
        for text, command, tip in (("⏮", self.back_command, "back to the previous command or phase"),
                                   ("◀", self.back, "one entry back"),
                                   ("▶", self.step, "step (Space)"),
                                   ("▶▶ Run", self.run, "run until your turn"),
                                   ("⏸", self.pause, "pause"),
                                   ("⏭", self.to_end, "to the latest entry")):
            ttk.Button(transport, text=text, command=command, width=7 if len(text) > 2 else 3).pack(side="left",
                                                                                                    padx=1)
        ttk.Button(transport, text="End phase", command=self.end_phase).pack(side="left", padx=(12, 0))
        ttk.Button(transport, text="Force next battle...", command=self.force_battle).pack(side="left", padx=(4, 0))
        self._position = tk.DoubleVar(value=0)
        self._scale = ttk.Scale(transport, from_=0, to=1, variable=self._position, command=self._scrub)
        self._scale.pack(side="left", fill="x", expand=True, padx=(12, 4))
        self._position_label = ttk.Label(transport, text="", width=34)
        self._position_label.pack(side="left")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        middle = ttk.Frame(paned)
        paned.add(middle, weight=3)
        self.canvas = _PlayCanvas(middle, self)
        self.canvas.show.update({"zones": True, "props": False})
        ybar = ttk.Scrollbar(middle, orient="vertical", command=self.canvas.yview)
        xbar = ttk.Scrollbar(middle, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self._status = ttk.Label(middle, text="", anchor="w")
        self._status.pack(side="bottom", fill="x", padx=6)
        self._hover = ttk.Label(middle, text="", style="Muted.TLabel", anchor="w")
        self._hover.pack(side="bottom", fill="x", padx=6)
        zoom = ttk.Frame(middle)
        zoom.pack(side="bottom", fill="x", padx=6)
        ttk.Button(zoom, text="−", width=3, command=lambda: self.canvas.zoom(1 / 1.25)).pack(side="left")
        ttk.Button(zoom, text="+", width=3, command=lambda: self.canvas.zoom(1.25)).pack(side="left", padx=(2, 0))
        ttk.Label(zoom, text="Click one of your units, then a tile. Right-click or Esc cancels; click an "
                             "enemy to see its range.", style="Muted.TLabel").pack(side="left", padx=8)
        xbar.pack(side="bottom", fill="x")
        ybar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        right = ttk.Frame(paned, width=520)
        paned.add(right, weight=2)
        self._tabs = ttk.Notebook(right)
        self._tabs.pack(fill="both", expand=True)
        self._unit_text = self._text_tab("Unit")
        self._script_text = self._text_tab("Script")
        self._ai_text = self._text_tab("AI")
        message = ttk.Frame(self._tabs, padding=6)
        self._tabs.add(message, text="Message")
        self._message_canvas = tk.Canvas(message, background="#000000", highlightthickness=0, height=300)
        self._message_canvas.pack(fill="both", expand=True)
        self._message_label = ttk.Label(message, text="", wraplength=480, justify="left")
        self._message_label.pack(fill="x", pady=(6, 0))
        self._log_text = self._text_tab("Log")
        self._flags_text = self._text_tab("Flags")
        for widget in (self._script_text, self._ai_text, self._log_text):
            widget.tag_configure("current", background="#5a4a00", foreground="#ffffff")
            widget.tag_configure("head", font=("Segoe UI", 9, "bold"))
            widget.tag_configure("muted", foreground="#8a8a8a")
            widget.tag_configure("warn", foreground="#e8a24f")

    def _text_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self._tabs, padding=4)
        self._tabs.add(frame, text=title)
        text = tk.Text(frame, wrap="none", font=("Consolas", 9), height=10, width=70)
        bar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=bar.set, state="disabled")
        bar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        return text

    @staticmethod
    def _write(widget: tk.Text, lines: list, current: Optional[int] = None) -> None:
        """``lines`` are strings or (string, tag); ``current`` is a line to mark and show."""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for i, line in enumerate(lines):
            text, tag = (line, None) if isinstance(line, str) else line
            tags = tuple(t for t in (tag, "current" if i == current else None) if t)
            widget.insert("end", text + "\n", tags)
        widget.configure(state="disabled")
        if current is not None:
            widget.see(f"{current + 1}.0")

    # -- starting -------------------------------------------------------------------------------
    def _make_world(self, problems: list):
        b = self._builder
        data = b.map_editor.map_data
        if data is None or data.capacity is None:
            raise ValueError("This chapter has no map.")
        session = b._session_provider()
        fe8 = getattr(session, "fe8", None)
        if fe8 is None:
            from ..formats import fe8data

            fe8 = fe8data.read_fe8data((self._files / "FE8Data.bin").read_bytes())
        index = b._index_provider()
        names = {pid: info.name for pid, info in getattr(index, "by_pid", {}).items() if info.name}
        script_editor = b._script
        path = script_editor.chapter_path if script_editor is not None else None
        source = script_editor.chapter_source() if script_editor is not None and script_editor.dirty else None
        script = loader.chapter_script(self._files, path, source, problems)
        documents = [b._deploy.document(v) for v in b._deploy.variants()]
        difficulty = dict(DIFFICULTIES)[self._difficulty.get()]
        world = loader.load_world(self._files, map_data=data, terrain_grid=b.map_editor.terrain_grid,
                                  terrain_types=b.map_editor.terrain_types, documents=documents, fe8=fe8,
                                  script=script, difficulty=difficulty, names=names,
                                  chapter_stem=path.stem if path is not None else None, problems=problems)
        world.item_names = {k: v for k, v in (getattr(index, "item_names", {}) or {}).items() if v}
        if script is None:
            problems.append("This chapter has no event script: every deployment section of the chosen "
                            "difficulty for the player is placed, and no events run.")
        return world

    def restart(self) -> None:
        self.pause()
        problems: list = []
        try:
            world = self._make_world(problems)
            seed = int(self._seed.get() or 0)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Play chapter", str(exc), parent=self)
            return
        mode = self._start_at.get()
        if mode == START_SAVED and self._saved_start is not None:
            state = self._saved_start[0].snapshot()
            problems.append(f"Started from the saved point \"{self._saved_start[1]}\" (it keeps its own random "
                            "numbers: the seed doesn't apply).")
        else:
            state = setup.initial_state(world, seed=seed)
        self.sim = Simulation(world, state)
        self._source_cache.clear()
        self._selected, self._reach, self._watch = None, {}, None
        self.canvas.size = (world.width, world.height)
        self.canvas.terrain = world.terrain
        self.canvas.playable = world.playable
        self.canvas.backdrop = self._builder._backdrop
        for problem in problems:
            state.emit("warn", problem)
        if problems:
            self.sim.history[0].steps.append(engine.Step("task", "Setup", outputs=list(state.out)))
            state.out = []
        self.refresh()
        if mode == START_TURN1:
            self._running = (SKIP, None)
            self._tick()
        elif mode == START_OPENING:
            self.run()

    def save_start(self) -> None:
        """Make the shown entry the point Restart starts from."""
        if self.sim is None:
            return
        state = self.sim.state
        label = f"turn {state.turn}, {FACTION_NAMES.get(state.phase, state.phase)} phase: {self.sim.entry.label}"
        self._saved_start = (state.snapshot(), label)
        self._start_box.configure(values=[START_TURN1, START_OPENING, START_SAVED])
        self._start_at.set(START_SAVED)
        note = f"Restart now starts from {label}."
        if any(isinstance(t, (ScriptRun, MessageShow, AiTurn)) for t in state.pending):
            note += " It is inside running code: Restart goes on from there, with the code as edited by then."
        self._hover.configure(text=note)

    def _map_changed(self) -> None:
        self._hover.configure(text="The map changed in the Build tab: press Restart to play the new version.")

    # -- transport ------------------------------------------------------------------------------
    @property
    def _until(self) -> str:
        return dict(GRANULARITIES)[self._granularity.get()]

    def step(self) -> None:
        if self.sim is None or self._waiting_animation:
            return
        self.pause()
        if not self.sim.at_end:
            self.sim.forward_by(self._until)
            self.refresh()
            return
        self._start(self._until)

    def run(self) -> None:
        if self.sim is None or self._waiting_animation:
            return
        if not self.sim.at_end:
            self.sim.forward_by(INPUT)
            self.refresh()
            return
        self._start(INPUT)

    def _start(self, until: str) -> None:
        self._running = (until, self.sim.mark())
        self._tick()

    def pause(self) -> None:
        self._running = None
        if self._after is not None:
            self.after_cancel(self._after)
            self._after = None

    def _tick(self) -> None:
        self._after = None
        if self._running is None or self.sim is None:
            return
        until, start = self._running
        if until == SKIP:
            self._skip()
            return
        began = time.monotonic()
        while True:
            result = self.sim.step()
            if result.kind in ("input", "over") and not result.outputs:
                self._stop()
                return
            battle = next((o for o in result.outputs if o.kind == "battle"), None)
            message = any(o.kind == "message" for o in result.outputs)
            if self.sim.boundary(until, result, start) or (message and not self._auto_messages.get()):
                self._stop()
                if battle is not None and self._animate.get() and until != LINE:
                    self._animate_battle(battle, resume=False)
                return
            if battle is not None and self._animate.get():
                self.refresh()
                self._animate_battle(battle, resume=True)
                return
            if message:
                self.refresh()
                self._after = self.after(MESSAGE_DELAY_MS, self._tick)
                return
            if time.monotonic() - began > RUN_BUDGET_S:
                self.refresh(light=True)
                self._after = self.after(1, self._tick)
                return

    def _skip(self) -> None:
        """One slice of playing the opening unseen (Start at: Turn 1)."""
        problem = self.sim.fast_forward(budget_s=RUN_BUDGET_S)
        if problem == UNFINISHED:
            self._status.configure(text=f"Playing the opening... ({len(self.sim.history) - 1} steps)")
            self._after = self.after(1, self._tick)
            return
        if problem is not None:
            self.sim.state.emit("warn", problem)
            self.sim.entry.steps.append(engine.Step("task", "Start", outputs=list(self.sim.state.out)))
            self.sim.state.out = []
            self._hover.configure(text=problem)
        self._stop()

    def _stop(self) -> None:
        self._running = None
        self.refresh()

    def _animate_battle(self, output, resume: bool) -> None:
        from .playthrough_battle import BattleAnimationWindow

        if self._battle_window is None or not self._battle_window.winfo_exists():
            self._battle_window = BattleAnimationWindow(self, self._files, self.sim.world.rules, self.sim.world.fe8)
        self._waiting_animation = True

        def done() -> None:
            self._waiting_animation = False
            if resume and self._running is not None and self.winfo_exists():
                self._after = self.after(10, self._tick)

        self._battle_window.play(output.data["log"], output.data["distance"], done)

    def back(self) -> None:
        if self.sim is not None:
            self.pause()
            self.sim.back()
            self.refresh()

    def forward(self) -> None:
        if self.sim is not None:
            self.pause()
            self.sim.forward()
            self.refresh()

    def back_command(self) -> None:
        if self.sim is not None:
            self.pause()
            self.sim.back_to(("command", "phase"))
            self.refresh()

    def to_end(self) -> None:
        if self.sim is not None:
            self.pause()
            self.sim.goto(len(self.sim.history) - 1)
            self.refresh()

    def _scrub(self, value) -> None:
        if self.sim is None or self._running is not None:
            return
        index = int(float(value))
        if index != self.sim.cursor:
            self.sim.goto(index)
            self.refresh()

    # -- commands -------------------------------------------------------------------------------
    def _command(self, command) -> None:
        if self.sim is None:
            return
        self.pause()
        try:
            self.sim.command(command)
        except actions.CommandError as exc:
            messagebox.showinfo("Play chapter", str(exc), parent=self)
            return
        self._deselect(refresh=False)
        self.refresh()
        if self._until == LINE:
            return  # line by line: the player steps on
        self._start(INPUT)

    def end_phase(self) -> None:
        if self.sim is None or not self.sim.needs_input:
            return
        state = self.sim.state
        if state.canto is not None:  # the Canto unit stays where it is
            uid = state.canto[0]
            try:
                self.sim.command(actions.CantoMove(uid, state.units[uid].tile))
            except actions.CommandError:
                pass
        self._command(actions.EndPhase())

    def force_battle(self) -> None:
        if self.sim is None:
            return
        dialog = _ForceDialog(self, self.sim.state.forced)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        choices = dialog.result
        self.sim.edit(lambda s: setattr(s, "forced", choices if choices is not False else None),
                      "Next battle forced" if choices is not False else "Next battle random")
        self.refresh()

    # -- canvas events (the _BuildCanvas protocol) ------------------------------------------------
    def on_press(self, tile, event) -> None:
        if self.sim is None or tile is None or self._running is not None or self._waiting_animation:
            return
        state = self.sim.state
        if state.canto is not None and not state.pending:
            uid, left = state.canto
            reach = movement.destinations(self.sim.world, state, state.units[uid], budget=left)
            if tile in reach:
                self._command(actions.CantoMove(uid, tile))
            return
        if self._selected is not None and tile in self._reach:
            self._action_menu(tile, event)
            return
        unit = state.unit_at(*tile)
        if unit is None:
            self._deselect()
            return
        if unit.faction == PLAYER and not unit.done and self.sim.needs_input:
            self._selected = unit.uid
            self._watch = None
            self._reach = movement.destinations(self.sim.world, state, unit)
        else:
            self._selected, self._reach = None, {}
            self._watch = None if self._watch == unit.uid else unit.uid
        self._show_unit(unit)
        self._refresh_map()

    def on_drag(self, tile, event) -> None:
        pass

    def on_release(self, tile, event) -> None:
        pass

    def on_right(self, tile, event) -> None:
        if self.sim is not None and self.sim.state.canto is not None and not self.sim.state.pending:
            uid, _left = self.sim.state.canto
            self._command(actions.CantoMove(uid, self.sim.state.units[uid].tile))
            return
        self._deselect()

    def on_hover(self, tile) -> None:
        if self.sim is None or tile is None:
            self._hover.configure(text="")
            return
        world, state = self.sim.world, self.sim.state
        t = world.terrain_at(*tile)
        text = f"({tile[0]}, {tile[1]})  {world.terrain_name(*tile)}"
        if t is not None:
            text += f"  avoid {t.avoid} def {t.defense}"
        unit = state.unit_at(*tile)
        if unit is not None:
            text += (f"   |   {world.name(unit.pid)} ({FACTION_NAMES.get(unit.faction, unit.faction)}) "
                     f"Lv {unit.level} HP {unit.hp}/{unit.stats[0]}")
        self._hover.configure(text=text)

    def _deselect(self, refresh: bool = True) -> None:
        self._selected, self._reach = None, {}
        if refresh:
            self._refresh_map()

    def _action_menu(self, dest: tuple, event) -> None:
        world, state = self.sim.world, self.sim.state
        unit = state.units[self._selected]
        menu = tk.Menu(self, tearoff=0)
        for choice in actions.choices(world, state, unit, dest):
            label = choice.label
            if choice.action == "attack":
                label += "   " + self._forecast_text(unit, dest, state.units[choice.target], choice.item)
            menu.add_command(label=label, command=lambda c=choice: self._command(
                actions.Act(unit.uid, dest, c.action, c.target, c.item)))
        menu.add_separator()
        menu.add_command(label="Cancel", command=self._deselect)
        menu.tk_popup(event.x_root, event.y_root)

    def _forecast_text(self, unit, dest: tuple, target, item_index: int) -> str:
        world = self.sim.world
        moved = copy.copy(unit)
        moved.x, moved.y = dest
        item = world.items.get(unit.items[item_index][0])
        f = combat.forecast(world, moved, target, item, movement.distance(dest, target.tile))
        a, d = f.attacker, f.defender
        text = f"Hit {a.hit}  Dmg {a.damage}{' x2' if a.doubles else ''}  Crit {a.crit}"
        if d.can_attack:
            text += f"   |   counter: Hit {d.hit}  Dmg {d.damage}{' x2' if d.doubles else ''}  Crit {d.crit}"
        else:
            text += "   |   no counter"
        return text

    # -- refreshing -----------------------------------------------------------------------------
    def refresh(self, light: bool = False) -> None:
        if self.sim is None or not self.winfo_exists():
            return
        self._refresh_map()
        sim = self.sim
        n = len(sim.history)
        self._scale.configure(to=max(1, n - 1))
        self._position.set(sim.cursor)
        entry = sim.entry
        self._position_label.configure(text=f"{sim.cursor + sim.dropped}/{n - 1 + sim.dropped}  {entry.label[:24]}")
        state = sim.state
        status = f"Turn {state.turn}, {FACTION_NAMES.get(state.phase, state.phase)} phase"
        if state.over:
            status += f"  -  chapter {state.over}"
        elif state.canto is not None and not state.pending:
            status += f"  -  Canto: {sim.world.name(state.units[state.canto[0]].pid)} may move "\
                      f"{state.canto[1]} more (click a tile, right-click to stay)"
        elif sim.needs_input:
            status += "  -  your turn"
        elif state.pending:
            status += f"  -  next: {state.pending[0].title}"
        if state.forced is not None:
            status += "  -  next battle forced"
        if not sim.at_end:
            status += "  -  (history: a command from here starts a new branch)"
        self._status.configure(text=status)
        if light:
            return
        self._refresh_script()
        self._refresh_ai()
        self._refresh_message()
        self._refresh_log()
        self._refresh_flags()
        if self._selected is not None and self._selected in state.units:
            self._show_unit(state.units[self._selected])
        if self._follow.get() and state.pending:
            front = state.pending[0]
            tab = {ScriptRun: 1, AiTurn: 2, MessageShow: 3}.get(type(front))
            if entry.steps and entry.steps[-1].kind == "message":
                tab = 3
            if tab is not None:
                self._tabs.select(tab)

    def _refresh_map(self) -> None:
        if self.sim is None:
            return
        world, state = self.sim.world, self.sim.state
        canvas = self.canvas
        if canvas.backdrop is None and self._builder._backdrop is not None:
            canvas.backdrop = self._builder._backdrop
        canvas.units = []
        for u in state.living():
            canvas.units.append({
                "key": u.uid, "x": u.x, "y": u.y, "pos2": (u.x, u.y),
                "color": FACTION_COLORS.get(u.faction, "#8a8a8a"), "text": world.name(u.pid)[:3],
                "selected": u.uid in (self._selected, self._watch), "highlight": False,
                "done": u.done and u.faction == state.phase, "hp": u.hp / max(1, u.stats[0]), "boss": u.boss,
            })
        zones = []
        if self._show_zones.get() and world.scripts:
            for rect, side, name in triggers.zones(world):
                color = "#4fc3f7" if side == 0 else "#ff8a65" if side == 1 else "#ce93d8"
                zones.append({"rect": rect, "area": side >= 0, "color": color, "text": name, "selected": False})
        overlay = []
        if self._selected is not None and self._selected in state.units:
            unit = state.units[self._selected]
            overlay += [(t, MOVE_COLOR) for t in self._reach]
            ranges = combat.attack_ranges(world, unit) + [combat.item_range(unit, it) for _i, it in
                                                          combat.staff_items(world, unit)]
            strike = set()
            for tile in self._reach:
                for low, high in ranges:
                    strike |= movement.tiles_in_range(world, tile, low, high)
            overlay += [(t, ATTACK_COLOR) for t in strike - set(self._reach)]
        elif state.canto is not None and not state.pending:
            uid, left = state.canto
            overlay += [(t, CANTO_COLOR) for t in movement.destinations(world, state, state.units[uid], budget=left)]
        if self._watch is not None and self._watch in state.units and state.units[self._watch].on_map:
            unit = state.units[self._watch]
            ranges = combat.attack_ranges(world, unit)
            overlay += [(t, THREAT_COLOR) for t in movement.threat_tiles(world, state, unit, ranges)]
            overlay += [(t, MOVE_COLOR) for t in movement.destinations(world, state, unit)]
        for tile, color in overlay:
            zones.append({"rect": (tile[0], tile[1], tile[0], tile[1]), "area": True, "color": color, "text": "",
                          "selected": False})
        canvas.zones = zones
        canvas.redraw()

    def _show_unit(self, unit) -> None:
        world = self.sim.world
        lines = [(f"{world.name(unit.pid)}  ({unit.pid})", "head"),
                 f"{FACTION_NAMES.get(unit.faction, unit.faction)}   {unit.jid}   Lv {unit.level}   EXP {unit.exp}",
                 f"Tile {unit.tile}   Mov {unit.move}   Build {unit.build}" + ("   acted" if unit.done else ""),
                 "", "  ".join(f"{n} {v}" for n, v in zip(STAT_LABELS, unit.stats)), f"HP {unit.hp}/{unit.stats[0]}",
                 "", ("Items", "head")]
        for i, (iid, uses, drop) in enumerate(unit.items):
            lines.append(f"  {i}. {world.item_name(iid)}  ({uses})" + ("  drops" if drop else ""))
        lines += ["", ("Skills", "head"), "  " + ", ".join(unit.skills or ["-"])]
        if unit.faction != PLAYER:
            lines += ["", ("AI", "head"), f"  attack {unit.seq_attack or '-'} (pc {unit.ai_pc[0]})",
                      f"  move {unit.seq_move or '-'} (pc {unit.ai_pc[1]})", f"  heal {unit.seq_heal or '-'}",
                      f"  mtype {unit.mtype or '-'}   order {unit.ai_order}"]
        self._write(self._unit_text, lines)
        if not self._follow.get() or not self.sim.state.pending:
            self._tabs.select(0)

    def _refresh_script(self) -> None:
        state, world = self.sim.state, self.sim.world
        lines: list = [("Queue", "head")]
        for task in state.pending[:12]:
            lines.append("  " + task.title)
        if len(state.pending) > 12:
            lines.append(f"  ... {len(state.pending) - 12} more")
        if not state.pending:
            lines.append(("  (empty)", "muted"))
        run = next((t for t in state.pending if isinstance(t, ScriptRun) and t.frames), None)
        current = None
        if run is not None:
            lines += ["", (f"Event {run.name}   context {run.ctx}", "head"), ("Call stack", "head")]
            for frame in reversed(run.frames):
                lines.append(f"  {triggers.function_names(world, frame.script)[frame.function]}  pc {frame.pc}  "
                             f"stack {frame.stack[-6:]}  locals {frame.locals[:8]}")
            frame = run.frames[-1]
            c = script_code(world, frame.script, frame.function)
            name = triggers.function_names(world, frame.script)[frame.function]
            lines += ["", (f"{name}: instructions (next one marked)", "head")]
            for i, ins in enumerate(c.instrs):
                if i == frame.pc:
                    current = len(lines)
                lines.append(f"  {i:4d}  {disassemble(ins)}")
            lines += ["", (f"{name}: source", "head")]
            lines += ["  " + s for s in self._function_source(frame.script, frame.function)]
        self._write(self._script_text, lines, current)

    def _function_source(self, script: int, function: int) -> list:
        key = (script, function)
        if key not in self._source_cache:
            try:
                decompiler = Decompiler(self.sim.world.scripts[script])
                fd = decompiler.function(function, self.sim.world.scripts[script].functions[function])
                self._source_cache[key] = function_to_source(fd)
            except Exception as exc:  # noqa: BLE001
                self._source_cache[key] = [f"(could not decompile: {exc})"]
        return self._source_cache[key]

    def _refresh_ai(self) -> None:
        state, world = self.sim.state, self.sim.world
        turn = next((t for t in state.pending if isinstance(t, AiTurn)), None)
        if turn is None:
            self._write(self._ai_text, [("No AI unit is acting.", "muted")])
            return
        unit = state.units.get(turn.uid)
        lines = [(f"{world.name(unit.pid) if unit else turn.uid}: {turn.stage}", "head"),
                 f"registers {turn.registers}   found {turn.found}   threat limit "
                 f"{'none' if turn.threat_limit == 0xFFFF else turn.threat_limit}   entries run {turn.steps}"]
        if turn.candidate:
            lines.append(f"candidate: {turn.candidate.get('text')}")
        current = None
        prog = None
        if turn.stage in ("attack", "move"):
            prog = ai_program(world, turn.script) if not turn.fallback else None
            lines += ["", (f"{turn.script}" + (" (built-in fallback)" if turn.fallback else ""), "head")]
            if prog is not None:
                for i, line in enumerate(prog.lines):
                    if i >= prog.body and i > turn.pc + 8:
                        break
                    if i == turn.pc:
                        current = len(lines)
                    owner = "" if prog.owners[i] == prog.name else f"   [{prog.owners[i]}]"
                    lines.append((f"  {i:3d}  {line}{owner}", "muted" if i >= prog.body else None))
        self._write(self._ai_text, lines, current)

    def _refresh_message(self) -> None:
        sim = self.sim
        found = None
        for i in range(sim.cursor, max(-1, sim.cursor - 40), -1):
            entry = sim.history[i]
            if any(s.kind == "command" for s in entry.steps):
                break
            found = next((o for o in reversed(entry.outputs) if o.kind == "message"), None)
            if found is not None:
                break
        self._message_canvas.delete("all")
        if found is None:
            self._message_label.configure(text="")
            return
        data = found.data
        self._message_label.configure(text=f"{data['msg_id']}  page {data['page']}/{data['pages']}\n{found.text}")
        image = self._render_message(data["raw"], data["page"])
        if image is not None:
            w = max(1, self._message_canvas.winfo_width())
            h = max(1, self._message_canvas.winfo_height())
            scale = min(w / image.width, h / image.height)
            size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            self._message_photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS))
            self._message_canvas.create_image(w // 2, h // 2, image=self._message_photo)

    def _render_message(self, raw: str, page: int):
        if self._conversation is None:
            try:
                from ..formats.fe9_conversation_assets import ConversationAssets
                from ..formats.fe9_conversation_render import ConversationRenderer

                assets = ConversationAssets(self._project.extracted_dir)
                self._conversation = (assets, ConversationRenderer(assets))
            except Exception:  # noqa: BLE001 - no fonts or faces: the text alone is shown
                self._conversation = False
        if not self._conversation:
            return None
        from ..formats.fe9_conversation import build_timeline

        try:
            renderer = self._conversation[1]
            timeline = build_timeline(raw, measure=renderer.measure)
            waits = [e for e in timeline.events if e.wait] or [timeline.events[-1]]
            event = waits[min(page, len(waits)) - 1] if page <= len(waits) else timeline.events[-1]
            return renderer.render(event, time_ms=event.time_ms + 5000).image
        except Exception:  # noqa: BLE001
            return None

    def _refresh_log(self) -> None:
        sim = self.sim
        lines, current = [], None
        first = max(0, sim.cursor - 250)
        last = min(len(sim.history), sim.cursor + 40)
        for i in range(first, last):
            entry = sim.history[i]
            if i == sim.cursor:
                current = len(lines)
            for out in entry.outputs:
                if out.kind in ("log", "action", "battle", "death", "message", "phase", "trigger", "warn", "ai",
                                "script"):
                    if out.kind in ("ai", "script") and not out.text:
                        continue
                    tag = "warn" if out.kind == "warn" else "muted" if out.kind in ("ai", "script") else None
                    if i > sim.cursor:
                        tag = "muted"
                    for k, text in enumerate(out.text.splitlines() or [""]):
                        lines.append((f"{i:5d} {out.kind:7s} {text}" if k == 0 else f"{'':13s} {text}", tag))
        self._write(self._log_text, lines, current)

    def _refresh_flags(self) -> None:
        state = self.sim.state
        lines = [("Flags (slot, name, value)", "head")]
        for i, (name, value) in enumerate(state.flags):
            if name is not None:
                lines.append(f"  {i:2d}  {'ON ' if value else 'off'}  {name}")
        lines += ["", ("Script globals", "head"), "  " + "  ".join(f"g{i}={v}" for i, v in enumerate(state.globals)
                                                                     if v)]
        lines += ["", f"Gold {state.money}   seen events {len(state.seen)}   visited {sorted(state.visited)}",
                  f"opened {sorted(state.opened)}"]
        self._write(self._flags_text, lines)

    def close(self) -> None:
        self.pause()
        if self._battle_window is not None and self._battle_window.winfo_exists():
            self._battle_window.cleanup()
            self._battle_window.destroy()
        super().close()


class _ForceDialog(tk.Toplevel):
    """Choose the outcome of each strike of the next battle (battle_sim.FixedOutcomes keys)."""

    STRIKES = 8

    def __init__(self, parent, current: Optional[dict]):
        super().__init__(parent)
        self.title("Force the next battle")
        self.transient(parent)
        self.result = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Strikes are numbered in fight order (counters and follow-ups included).\n"
                             "Unlisted strikes hit when they can, without crits or skills.",
                  style="Muted.TLabel", justify="left").grid(row=0, column=0, columnspan=4, sticky="w")
        self._vars = []
        current = current or {}
        for n in range(1, self.STRIKES + 1):
            hit = tk.BooleanVar(value=current.get((n, "hit"), True))
            crit = tk.BooleanVar(value=current.get((n, "crit"), False))
            ttk.Label(body, text=f"Strike {n}").grid(row=n, column=0, sticky="w", pady=1)
            ttk.Checkbutton(body, text="hits", variable=hit).grid(row=n, column=1, sticky="w", padx=6)
            ttk.Checkbutton(body, text="crits", variable=crit).grid(row=n, column=2, sticky="w", padx=6)
            self._vars.append((n, hit, crit))
        buttons = ttk.Frame(body)
        buttons.grid(row=self.STRIKES + 1, column=0, columnspan=4, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Use random rolls", command=self._random).pack(side="left")
        ttk.Button(buttons, text="Force", command=self._ok).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _ok(self) -> None:
        choices = {}
        for n, hit, crit in self._vars:
            choices[(n, "hit")] = hit.get()
            choices[(n, "crit")] = crit.get() and hit.get()
        self.result = choices
        self.destroy()

    def _random(self) -> None:
        self.result = False
        self.destroy()
