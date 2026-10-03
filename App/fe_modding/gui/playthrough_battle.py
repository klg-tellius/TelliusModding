"""Plays a playthrough fight with the battle models (the battle simulator's 3D stage).

The playthrough hands over the fight's :class:`battle_sim.BattleLog`; the
models, clips, weapons and spell effects are found as the battle
simulator's 3D tab finds them (:mod:`fe_modding.battle_sim.scene_assets`)
and the fight plays once, then ``on_done`` runs (also when the window is
closed or Skip is pressed). Loading the models is slow, so they are cached
for the window's life.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

from ..battle_sim import camera as battle_camera_sim
from ..battle_sim import scene_assets as sa
from ..formats import effects as effects_fmt
from . import battle_stage


class BattleAnimationWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, files: Path, rules, fe8):
        super().__init__(parent)
        self.title("Battle")
        self.geometry("900x620")
        self.transient(parent.winfo_toplevel())
        self._files = files
        self._rules, self._fe8 = rules, fe8
        self._cache = battle_stage.SetCache()
        self._assets: Optional[sa.BattleAssets] = None
        self._effects: dict = {}
        self._on_done: Optional[Callable[[], None]] = None
        self._finish_job: Optional[str] = None
        self.scenery = tk.StringVar(value="(none)")
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Scenery").pack(side="left")
        self._scenery_box = ttk.Combobox(top, textvariable=self.scenery, state="readonly", width=28)
        self._scenery_box.pack(side="left", padx=(4, 12))
        ttk.Button(top, text="Skip", command=self._finish).pack(side="right")
        self._note = ttk.Label(top, text="", style="Muted.TLabel")
        self._note.pack(side="left", fill="x", expand=True)
        self.view = battle_stage.StageView(self)
        self.view.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.view.on_finished = lambda: self._finish_later(600)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def assets(self) -> sa.BattleAssets:
        if self._assets is None:
            try:
                self._assets = sa.BattleAssets.from_files(self._files)
            except Exception:  # noqa: BLE001 - a damaged zdbx.cmp: no models, the fight is skipped
                self._assets = sa.BattleAssets(self._files, b"")
            self._scenery_box["values"] = ["(none)"] + list(self._assets.sceneries())
            try:
                self.view.game_camera = battle_camera_sim.GameCamera.from_zdbx(self._assets.zdbx_data)
            except Exception:  # noqa: BLE001
                self.view.game_camera = None
        return self._assets

    def _effect(self, kind: str, key: str):
        eid = key
        if kind == "skill":
            eid = next((sk.effect for sk in (self._fe8.skills if self._fe8 else ()) if sk.effect and sk.sid
                        and self._rules.skill_key(sk.sid) == key), None)
        if not eid:
            return None
        if eid not in self._effects:
            try:
                self._effects[eid] = battle_stage.load_effect(effects_fmt.pack_path(self._files, eid))
            except Exception:  # noqa: BLE001
                self._effects[eid] = None
        return self._effects[eid]

    def play(self, log, distance: int, on_done: Callable[[], None]) -> None:
        """Play ``log``; ``on_done()`` runs once it has finished or was skipped."""
        self._cancel_finish()
        self._finish_pending()
        self._on_done = on_done
        self.deiconify()
        self.lift()
        assets = self.assets()
        units = [log.attacker, log.defender]
        try:
            found = [assets.unit(u, ranged=distance > 1) for u in units]
            if not any(a.code for a in found):
                self._note.configure(text="Neither unit has a battle model (jobList.dbx): nothing to play.")
                self.view.set_stage(None)
                self._finish_later(800)
                return
            self.configure(cursor="watch")
            self.update_idletasks()
            units3d = [battle_stage.load_unit(self._cache, a) for a in found]
            scenery = assets.sceneries().get(self.scenery.get())
            scene = self._cache.get(("scenery", scenery), lambda: battle_stage.load_scenery(scenery)) \
                if scenery is not None else None
            stage = battle_stage.BattleStage(units3d, scene, self._effect)
        except Exception as exc:  # noqa: BLE001 - no models: say so and go on with play
            self._note.configure(text=f"Could not load the battle models: {exc}")
            self.view.set_stage(None)
            self._finish_later(1200)
            return
        finally:
            self.configure(cursor="")
        notes = [f"{u.name}: {a.code or 'no model'}" for u, a in zip(units, found)]
        self._note.configure(text="   ".join(notes))
        stage.set_log(log, distance)
        self.view.set_stage(stage, (log.attacker.name, log.defender.name),
                            (log.attacker.stats[0], log.defender.stats[0]))
        self.view.toggle()

    def _finish_later(self, ms: int) -> None:
        self._cancel_finish()
        self._finish_job = self.after(ms, self._finish)

    def _cancel_finish(self) -> None:
        """Drop a scheduled close, so it can't end the next battle early."""
        if self._finish_job is not None:
            self.after_cancel(self._finish_job)
            self._finish_job = None

    def _finish_pending(self) -> None:
        if self._on_done is not None:
            done, self._on_done = self._on_done, None
            done()

    def _finish(self) -> None:
        self._cancel_finish()
        self.view.stop()
        if self.winfo_exists():
            self.withdraw()
        self._finish_pending()

    def _close(self) -> None:
        self._finish()

    def cleanup(self) -> None:
        self.view.cleanup()
