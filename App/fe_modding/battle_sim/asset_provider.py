"""Game-selected battle registry validation and asset lookup boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import scene_assets as sa
from .staging import BattleParams


class BattleAssetError(ValueError):
    pass


@dataclass
class AssetValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def require(self) -> None:
        if self.errors:
            raise BattleAssetError("; ".join(self.errors))


class BattleAssetProvider:
    game = ""

    def validate(self) -> AssetValidation:
        raise NotImplementedError


class Fe9BattleAssetProvider(BattleAssetProvider):
    game = "fe9"

    def __init__(self, files):
        from .scene_assets import BattleAssets
        self.assets = BattleAssets.from_files(files)

    def validate(self) -> AssetValidation:
        return AssetValidation()


class Fe10BattleAssetProvider(BattleAssetProvider):
    """Decoded FE10Data/Anim/Battle/Effect registry graph.

    Required cross-registry indices are errors; loose models, effects and xcam
    clips are optional and become precise warnings so a fight can degrade to
    the shared stage without hiding broken registry relationships.
    """

    game = "fe10"

    def __init__(self, project):
        from ..formats import fe10_anim, fe10_battle, fe10_effect_registry
        self.project = project
        self.files = Path(project.extracted_dir) / "files"
        self.anim = fe10_anim.read_fe10_anim(project.read_logical("anim_data"))
        self.battle = fe10_battle.read_fe10_battle(project.read_logical("battle_data"))
        self.effects = fe10_effect_registry.read_fe10_effect_registry(project.read_logical("effect_data"))
        self._headers = {header.aid_name: (index, header)
                         for index, header in enumerate(self.anim.headers) if header.aid_name}
        self._anim_rows = self.battle.table("FE10BAnimData").records
        self._weapon_rows = self.battle.table("FE10BWeapon").records

    def validate(self) -> AssetValidation:
        result = AssetValidation()
        for i, header in enumerate(self.anim.headers):
            if not 0 <= header.model_index < len(self.anim.models):
                result.errors.append(f"FE10Anim header {i} ({header.aid_name}) names missing model {header.model_index}")
        for row in self.battle.map_data:
            for variant, index in enumerate(row.model_indices):
                if index is not None and not 0 <= index < len(self.battle.map_models):
                    result.errors.append(f"FE10BMapData {row.map_name} variant {variant} names missing model {index}")
        camera_files = len(self.battle.table("FE10BCamFile").records)
        for group in self.battle.camera_groups:
            for choice in group.choices:
                if not 0 <= choice.file_index < camera_files:
                    result.errors.append(f"camera group {group.record_index} names missing camera {choice.file_index}")
        for header in self.anim.headers:
            folder = self.anim.models[header.model_index].folder if 0 <= header.model_index < len(self.anim.models) else ""
            if folder and not (self.files / "ymu" / folder / "pack.cmp").is_file():
                result.warnings.append(f"optional battle model folder {folder!r} was not found")
        result.require()
        return result

    # -- registry resolution -----------------------------------------------------------------
    def _header_for(self, unit):
        """Resolve the battle animation row in retail precedence order.

        A deployment-provided AID wins.  FE10BAnimData then specializes by
        PID/JID before falling back to its generic JID row.
        """
        if unit.aid and unit.aid in self._headers:
            return self._headers[unit.aid]
        candidates = []
        for row in self._anim_rows:
            strings = dict(row.strings)
            aid, pid, jid = strings.get(0), strings.get(4), strings.get(8)
            if not aid or aid not in self._headers or (jid and jid != unit.jid):
                continue
            if pid and pid == unit.pid:
                candidates.append((0, aid))
            elif not pid and jid == unit.jid:
                candidates.append((1, aid))
        return self._headers[min(candidates)[1]] if candidates else None

    @staticmethod
    def _weapon_slot(weapon_type: str, ranged: bool) -> int:
        kind = (weapon_type or "").lower()
        if kind in {"lance", "spear"}:
            return 3 if ranged else 2
        if kind == "axe":
            return 5 if ranged else 4
        if kind in {"bow", "crossbow"}:
            return 8 if kind == "crossbow" else 6
        if kind in {"rod", "staff"}:
            return 7
        if kind in {"sword", "knife"}:
            return 1
        return 0

    def _animation_roles(self, header_index: int, slot: int, *, magic: bool) -> tuple[dict, tuple[Path, ...]]:
        # Shared timeline roles -> FE10AnimMotion indices.  Missing variants
        # deliberately fall back to the first ordinary strike/idle clip.
        primary = 6 if magic else 4
        mapping = {
            sa.IDLE: (0,), sa.READY: (27, 0), sa.ATTACK1: (primary, 4),
            sa.ATTACK2: ((7 if magic else 5), primary, 4), sa.CRIT1: (8, primary, 4),
            sa.CRIT2: (8, primary, 4), sa.DODGE: (26, 0), sa.DAMAGE: (29, 0),
            sa.DEATH: (31, 29, 0), sa.RUN: (1, 3, 0), sa.THROW: (4,),
            sa.CRIT_THROW: (8, 4), sa.SHOT: (4,), sa.CRIT_SHOT: (8, 4),
            sa.SPELL: (6, 4), sa.SKILL: (19, 8, 4), sa.SKILL_THROW: (19, 8, 4),
        }
        header = self.anim.headers[header_index]
        folder = self.files / "ymu" / self.anim.models[header.model_index].folder
        roles, paths = {}, {}
        for role, motions in mapping.items():
            name = next((self.anim.animation_filename(header_index, slot, motion)
                         for motion in motions
                         if self.anim.animation_filename(header_index, slot, motion)), None)
            # Some magic actors use their unarmed matrix for spell clips.
            if name is None and slot and magic:
                name = next((self.anim.animation_filename(header_index, 0, motion)
                             for motion in motions
                             if self.anim.animation_filename(header_index, 0, motion)), None)
            if name:
                path = folder / name
                if path.is_file():
                    roles[role] = path.stem
                    paths[path.name.lower()] = path
        return roles, tuple(paths.values())

    def _weapon(self, unit, found: sa.UnitAssets) -> None:
        if unit.weapon is None:
            return
        key = unit.weapon.iid.removeprefix("IID_").upper()
        record = next((row for row in self._weapon_rows
                       if key in {dict(row.strings).get(4, "").upper(),
                                  dict(row.strings).get(8, "").upper()}), None)
        if record is None:
            found.notes.append(f"FE10BWeapon has no row for {unit.weapon.iid}")
            return
        strings = dict(record.strings)
        actor = strings.get(4) or strings.get(8)
        if actor:
            folder = self.files / "xwp" / actor.lower()
            model = folder / f"{actor.lower()}.cmp"
            if not model.is_file() and folder.is_dir():
                model = next(iter(sorted(folder.glob("*.cmp"))), model)
            if model.is_file():
                found.weapon_model = model
            found.weapon_name = actor
        magic = unit.weapon.attack_type == "magic" or unit.weapon.weapon_type.lower() in {
            "fire", "flame", "thunder", "wind", "light", "dark", "magic", "tome"
        }
        found.weapon_effect = strings.get(20) if magic else None
        found.weapon_damage_effect = strings.get(16) if magic else strings.get(12)

    def unit(self, unit, *, code=None, prefix=None, ranged: bool = False,
             army: str = sa.PLAYER_ARMY) -> sa.UnitAssets:
        resolved = self._header_for(unit)
        found = sa.UnitAssets(code=code)
        if resolved is None:
            found.notes.append(f"no FE10 animation registration for {unit.aid or unit.pid or unit.jid or unit.name}")
            return found
        header_index, header = resolved
        model = self.anim.models[header.model_index]
        found.code = header.aid_name
        found.pack = self.files / "ymu" / model.folder / "pack.cmp"
        if not found.pack.is_file():
            found.notes.append(f"required model ymu/{model.folder}/pack.cmp was not found")
            found.pack = None
            return found
        magic_types = {"fire", "flame", "thunder", "wind", "light", "dark", "magic", "tome"}
        magic = bool(unit.weapon and (unit.weapon.attack_type == "magic"
                                      or unit.weapon.weapon_type.lower() in magic_types))
        slot = self._weapon_slot(unit.weapon.weapon_type if unit.weapon else "", ranged)
        found.prefix = self.anim.weapons[slot].archive_suffix
        found.prefixes = [self.anim.weapons[i].archive_suffix
                          for i, variants in enumerate(model.variants) if any(variants)]
        found.roles, found.animation_paths = self._animation_roles(header_index, slot, magic=magic)
        texture = found.pack.parent / f"{header.texture_name}.tpl"
        found.texture = texture if texture.is_file() else None
        found.weapon_kind = {1: 0, 2: 1, 3: 6, 4: 2, 5: 7, 6: 3, 8: 9}.get(slot, 4 if magic else None)
        found.weapon_missile = 1 if ranged or magic else 0
        self._weapon(unit, found)
        return found

    def sceneries(self) -> dict[str, Path]:
        found = {}
        for model in self.battle.map_models:
            folder = self.files / "zbg" / model.archive_name
            pack = folder / "bf.cmp"
            if not pack.is_file() and folder.is_dir():
                pack = next(iter(sorted(folder.glob("*.cmp"))), pack)
            if pack.is_file():
                found.setdefault(model.archive_name, pack)
        return found

    def battle_params(self) -> BattleParams:
        # FE10BSetup is represented in engine fixed-point units; the shared
        # defaults preserve its traced world scale until all setup rows are
        # promoted to named BattleParams fields.
        return BattleParams()

    def foot_effect(self, scenery=None) -> int:
        return 1

    def effect_paths(self, eid: str) -> tuple[Path, ...]:
        by_name = {record.eid_name: (index, record) for index, record in enumerate(self.effects.records)}
        if eid not in by_name:
            return ()
        ordered, seen = [], set()

        def visit(index: int) -> None:
            if index in seen:
                return
            seen.add(index)
            record = self.effects.records[index]
            path = self.files / "yme" / f"{record.eid_name}.cmp"
            if path.is_file():
                ordered.append(path)
            for child in record.child_effect_indices:
                if child is not None:
                    visit(child)

        visit(by_name[eid][0])
        return tuple(ordered)

    def camera(self, distance: int, units=()):
        from .camera_fe10 import Fe10GameCamera
        return Fe10GameCamera(self.files / "xcam", self.battle, distance=distance, units=units)


def provider_for(project) -> BattleAssetProvider:
    return Fe10BattleAssetProvider(project) if project.profile.script_dialect == "fe10" \
        else Fe9BattleAssetProvider(project.extracted_dir / "files")
