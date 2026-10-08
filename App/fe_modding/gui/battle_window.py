"""A window that plays a fight with the battle models, as the game stages it.

Models, clips, weapons and effects are found through
:mod:`fe_modding.battle_sim.scene_assets` (the model the job list gives the
unit's class, its weapon's clip set, its texture), the staging values come
from ``zdbx/param.dbx`` and the models' ``_prm.dbx``, and the game camera
plays the ``xcam/`` scripts: nothing is picked by hand. Loading models is
slow, so they are cached for the window's life.

Used by the battle simulator's "Render fight" button and by the playthrough
(:mod:`.playthrough_battle`).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

from ..battle_sim import camera as battle_camera
from ..battle_sim import scene_assets as sa
from ..formats import effects as effects_fmt
from . import battle_stage


class BattleWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, files: Path, rules, fe8, title: str = "Battle"):
        super().__init__(parent)
        self.title(title)
        self.geometry("880x760")
        self.minsize(480, 420)
        self.transient(parent.winfo_toplevel())
        self._files = Path(files)
        self._rules, self._fe8 = rules, fe8
        self._cache = battle_stage.SetCache()
        self._assets: Optional[sa.BattleAssets] = None
        self._camera: Optional[battle_camera.GameCamera] = None
        self._effects: dict = {}
        self.top = ttk.Frame(self, padding=(8, 6))
        self.top.pack(fill="x")
        self._note = ttk.Label(self.top, text="", style="Muted.TLabel")
        self._note.pack(side="left", fill="x", expand=True)
        self.view = battle_stage.StageView(self)
        self.view.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self.close)

    # -- assets -----------------------------------------------------------------------------------
    def assets(self) -> sa.BattleAssets:
        if self._assets is None:
            try:
                self._assets = sa.BattleAssets.from_files(self._files)
            except Exception:  # noqa: BLE001 - a damaged zdbx.cmp: no models, nothing to play
                self._assets = sa.BattleAssets(self._files, b"")
            try:
                self._camera = battle_camera.GameCamera.from_zdbx(self._assets.zdbx_data)
            except Exception:  # noqa: BLE001 - no camera scripts: the opening camera stays
                self._camera = None
        return self._assets

    def sceneries(self) -> list[str]:
        return list(self.assets().sceneries())

    def _effect(self, kind: str, key: str):
        """The effect pack of a timeline cue: a skill's EID (the skill record's 0x14), else the
        cue's own EID_ (hit sparks, marks, spells, death, dust)."""
        eid = key
        if kind == "skill":
            eid = next((sk.effect for sk in (self._fe8.skills if self._fe8 else ()) if sk.effect and sk.sid
                        and self._rules.skill_key(sk.sid) == key), None)
        if not eid:
            return None
        if eid not in self._effects:
            try:
                self._effects[eid] = battle_stage.load_effect(effects_fmt.pack_path(self._files, eid))
            except Exception:  # noqa: BLE001 - a broken effect pack is skipped
                self._effects[eid] = None
        return self._effects[eid]

    # -- playing ----------------------------------------------------------------------------------
    def play(self, log, distance: int, scenery: Optional[str] = None, *, autoplay: bool = True) -> bool:
        """Stage ``log`` in ``scenery`` (a ``zbg/`` folder name, or None) and
        play it. False when nothing could be staged (the note says why)."""
        self.deiconify()
        self.lift()
        assets = self.assets()
        units = [log.attacker, log.defender]
        try:
            # the attacker as the player's unit, the defender as the enemy's, unless a texture names them
            found = [assets.unit(u, ranged=distance > 1, army=army)
                     for u, army in zip(units, (sa.PLAYER_ARMY, sa.ENEMY_ARMY))]
            if not any(a.code for a in found):
                self._note.configure(text="Neither unit has a battle model (jobList.dbx): nothing to play.")
                self.view.set_stage(None)
                return False
            self.configure(cursor="watch")
            self.update_idletasks()
            units3d = [battle_stage.load_unit(self._cache, a) for a in found]
            path = assets.sceneries().get(scenery) if scenery else None
            scene = self._cache.get(("scenery", path), lambda: battle_stage.load_scenery(path)) \
                if path is not None else None
            stage = battle_stage.BattleStage(units3d, scene, self._effect, assets.battle_params(),
                                             assets.foot_effect(scenery))
            camera = self._camera.with_packs(assets.camera_packs([a.code for a in found])) \
                if self._camera is not None else None
            stage.set_log(log, distance, camera)
        except Exception as exc:  # noqa: BLE001 - show what failed instead of a dead window
            self._note.configure(text=f"Could not load the battle models: {exc}")
            self.view.set_stage(None)
            return False
        finally:
            self.configure(cursor="")
        notes = []
        for u, a in zip(units, found):
            what = f"{u.name}: {a.code or 'no model'}"
            if u.weapon is not None and a.weapon_model is None and not a.weapon_effect:  # tomes have none
                what += " (no weapon model)"
            notes.append(what)
        self._note.configure(text="     ".join(notes))
        self.view.set_stage(stage, (log.attacker.name, log.defender.name),
                            (log.attacker.stats[0], log.defender.stats[0]))
        if autoplay:
            self.view.play_when_shown()
        return True

    def close(self) -> None:
        self.view.stop()
        if self.winfo_exists():
            self.withdraw()

    def cleanup(self) -> None:
        self.view.cleanup()
