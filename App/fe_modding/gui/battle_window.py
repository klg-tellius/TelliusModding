"""A window that plays a fight with the battle models, as the game stages it.

Models, clips, weapons and effects are found through
:mod:`fe_modding.battle_sim.scene_assets` (the model the job list gives the
unit's class, its weapon's clip set, its texture), the staging values come
from ``zdbx/param.dbx`` and the models' ``_prm.dbx``, and the game camera
plays the ``xcam/`` scripts: nothing is picked by hand. Loading models is
slow, so they are cached for the window's life.

Used by the battle simulator's "Render fight" button, by the playthrough
(:mod:`.playthrough_battle`) and, as a :class:`BattlePlayer` frame, by the
Battle Cameras page's preview.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

from .. import battle_sim
from ..battle_sim import camera as battle_camera
from ..battle_sim import scene_assets as sa
from ..battle_sim.units import weapon_from_item
from ..formats import effect_registry, effects as effects_fmt
from . import battle_stage
from ..game_files import as_path

#: The camera preview's fight: Ike with an Iron Sword against a level-1 Fighter with an Iron Axe.
PREVIEW_UNITS = (("PID_IKE", "Ike", "IID_IRONSWORD"), ("JID_FIGHTER", "Fighter", "IID_IRONAXE"))


def preview_log(fe8, rules, distance: int = 1):
    """A fight between :data:`PREVIEW_UNITS` (every strike that can hit hits)."""
    units = []
    for label, name, iid in PREVIEW_UNITS:
        try:
            unit = (battle_sim.from_character(fe8, label, name=name) if label.startswith("PID_")
                    else battle_sim.from_class(fe8, label, name=name))
        except (KeyError, AttributeError):
            unit = battle_sim.Combatant(name=name)
        item = next((i for i in (fe8.items if fe8 else ()) if i.iid == iid), None)
        if item is not None:
            unit.weapon = weapon_from_item(item)
        units.append(unit)
    return battle_sim.simulate(*units, rules=rules, distance=distance)


class BattlePlayer(ttk.Frame):
    """A note line, the staged fight and its playback controls: the body of
    :class:`BattleWindow`, also embedded by the Battle Cameras page."""

    def __init__(self, parent: tk.Misc, files: Path, rules, fe8, *, project=None, provider=None):
        super().__init__(parent)
        self._files = as_path(files)
        self._rules, self._fe8 = rules, fe8
        self._provider = provider or (battle_sim.provider_for(project) if project is not None else None)
        self._cache = battle_stage.SetCache()
        self._assets = None
        self._camera: Optional[battle_camera.GameCamera] = None
        self._effects: dict = {}
        self._effect_records = None
        self.top = ttk.Frame(self, padding=(0, 6))
        self.top.pack(fill="x")
        self._note = ttk.Label(self.top, text="", style="Muted.TLabel")
        self._note.pack(side="left", fill="x", expand=True)
        self.view = battle_stage.StageView(
            self, aspect=16.0 / 9.0 if getattr(self._provider, "game", "") == "fe10" else battle_camera.ASPECT)
        self.view.pack(fill="both", expand=True)

    # -- assets -----------------------------------------------------------------------------------
    def assets(self):
        if self._assets is None:
            if self._provider is not None:
                self._provider.validate()
                self._assets = getattr(self._provider, "assets", self._provider)
                return self._assets
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
                assets = self.assets()
                if hasattr(assets, "effect_paths"):
                    paths = assets.effect_paths(eid)
                else:
                    if self._effect_records is None:
                        registry = self._files / "FE8Effect.bin"
                        self._effect_records = effect_registry.read_effect_registry(registry.read_bytes()) \
                            if registry.is_file() else []
                    names = effect_registry.chain(self._effect_records, eid)
                    paths = tuple(effects_fmt.pack_path(self._files, name) for name in names)
                self._effects[eid] = battle_stage.load_effect_chain(paths) if paths else None
            except Exception:  # noqa: BLE001 - a broken effect pack is skipped
                self._effects[eid] = None
        return self._effects[eid]

    # -- playing ----------------------------------------------------------------------------------
    def play(self, log, distance: int, scenery: Optional[str] = None, *, autoplay: bool = True,
             camera_script=None) -> bool:
        """Stage ``log`` in ``scenery`` (a ``zbg/`` folder name, or None) and
        play it. With ``camera_script`` (a ``battle_camera.CameraScript``), that
        script alone drives the camera from the first tick instead of the
        game's. False when nothing could be staged (the note says why)."""
        assets = self.assets()
        units = [log.attacker, log.defender]
        top = self.winfo_toplevel()
        try:
            # the attacker as the player's unit, the defender as the enemy's, unless a texture names them
            found = [assets.unit(u, ranged=distance > 1, army=army)
                     for u, army in zip(units, (sa.PLAYER_ARMY, sa.ENEMY_ARMY))]
            if not any(a.code for a in found):
                self._note.configure(text="Neither unit has a battle model (jobList.dbx): nothing to play.")
                self.view.set_stage(None)
                return False
            top.configure(cursor="watch")
            self.update_idletasks()
            units3d = [battle_stage.load_unit(self._cache, a) for a in found]
            path = assets.sceneries().get(scenery) if scenery else None
            scene = self._cache.get(("scenery", path), lambda: battle_stage.load_scenery(path)) \
                if path is not None else None
            stage = battle_stage.BattleStage(units3d, scene, self._effect, assets.battle_params(),
                                             assets.foot_effect(scenery))
            if hasattr(assets, "camera"):
                camera = assets.camera(distance, found)
            else:
                camera = self._camera.with_packs(assets.camera_packs([a.code for a in found])) \
                    if self._camera is not None else None
            stage.set_log(log, distance, camera)
            if camera_script is not None and camera is not None:
                camera = battle_camera.GameCamera({**camera.scripts, camera_script.name: camera_script},
                                                  camera.rigs)
                opening = stage.timeline.camera[0] if stage.timeline.camera else None
                stage.timeline.camera[:] = [battle_camera.Cue(1, camera_script.name, 0, False,
                                                              opening.dest if opening is not None else None)]
                stage.shots = camera.track(stage.timeline.camera, stage.timeline.quakes,
                                           int(stage.timeline.length))
        except Exception as exc:  # noqa: BLE001 - show what failed instead of a dead window
            self._note.configure(text=f"Could not load the battle models: {exc}")
            self.view.set_stage(None)
            return False
        finally:
            top.configure(cursor="")
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

    def cleanup(self) -> None:
        self.view.cleanup()


class BattleWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, files: Path, rules, fe8, title: str = "Battle", *,
                 project=None, provider=None):
        super().__init__(parent)
        self.title(title)
        game = getattr(provider, "game", "") or getattr(getattr(project, "profile", None), "script_dialect", "")
        self.geometry("1100x720" if game == "fe10" else "880x760")
        self.minsize(480, 420)
        self.transient(parent.winfo_toplevel())
        self.player = BattlePlayer(self, files, rules, fe8, project=project, provider=provider)
        self.player.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.top, self.view = self.player.top, self.player.view
        self.protocol("WM_DELETE_WINDOW", self.close)

    def assets(self) -> sa.BattleAssets:
        return self.player.assets()

    def sceneries(self) -> list[str]:
        return self.player.sceneries()

    def play(self, log, distance: int, scenery: Optional[str] = None, *, autoplay: bool = True) -> bool:
        """Stage ``log`` in ``scenery`` (a ``zbg/`` folder name, or None) and
        play it. False when nothing could be staged (the note says why)."""
        self.deiconify()
        self.lift()
        return self.player.play(log, distance, scenery, autoplay=autoplay)

    def close(self) -> None:
        self.view.stop()
        if self.winfo_exists():
            self.withdraw()

    def cleanup(self) -> None:
        self.player.cleanup()
