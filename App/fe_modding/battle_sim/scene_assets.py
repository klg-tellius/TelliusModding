"""Which files a simulated battle draws: each unit's battle model and
animations, its weapon's model, and the scenery.

The lookup follows the chain the rest of the app already documents:

- model code: ``zdbx.battle_model_for`` over ``zdbx/jobList.dbx`` (AID, then
  class + character, then class);
- animations: ``zu/<code>.dbx`` maps ``<weapon prefix>_<role>`` to a ``.ga``
  stem (:func:`fe_modding.rig_contract.read_battle_roles`), for roles such as
  ``攻撃1`` (attack 1), ``必殺1`` (critical 1), ``回避`` (dodge);
- texture: ``zu/<code>_prm.dbx``'s ``texnum`` lines, tried by AID, then PID,
  then army (``zdbx.param_textures``);
- weapon: ``xwp/<IID without IID_>.dbx``'s Model block
  (:func:`fe_modding.formats.icons.weapon_model`);
- scenery: the first ``.cmp`` of a ``zbg/<name>/`` folder.

Which weapon prefix goes with which item weapon type is **not** in any
decoded table. :data:`WEAPON_PREFIXES` is derived from the trail-bone names
(``_sw1_``, ``_sp1_``...) and the role lines, and the simulator falls back
to any prefix the model has, so the choice can be overridden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .. import rig_contract
from ..formats import battle_params, battle_weapons, icons, zdbx
from .units import Combatant

#: Weapon prefixes to try for an item weapon type, best first; ``ranged`` for distance 2+.
WEAPON_PREFIXES = {
    "sword": ("sw",), "lance": ("sp",), "axe": ("ax",), "bow": ("bw",), "knife": ("kn", "sw"),
    "flame": ("mg", "ex"), "thunder": ("mg", "ex"), "wind": ("mg", "ex"), "rod": ("mg", "ex"),
    "fang": ("ex",),
}
RANGED_PREFIXES = {"lance": ("ja",), "axe": ("ha",), "sword": ("ar",)}

#: Battle roles (``zu/<code>.dbx`` keys).
IDLE, READY, ATTACK1, ATTACK2, CRIT1, CRIT2 = "待機", "構え", "攻撃1", "攻撃2", "必殺1", "必殺2"
DODGE, DAMAGE, DEATH, RUN, THROW, CRIT_THROW = "回避", "ダメージ", "死亡", "走り", "投げ", "必殺投げ"
SHOT, CRIT_SHOT, SPELL = "射撃", "必殺射撃", "魔法"


@dataclass
class UnitAssets:
    code: Optional[str] = None
    pack: Optional[Path] = None  # one weapon pack of zu/<code>/ (the set loads all of them)
    prefix: Optional[str] = None
    prefixes: list = field(default_factory=list)  # every prefix the model's table has
    roles: dict = field(default_factory=dict)  # role -> .ga stem, for ``prefix``
    texture: Optional[Path] = None
    weapon_model: Optional[Path] = None
    weapon_kind: Optional[int] = None  # battle_weapons.KINDS
    params: dict = field(default_factory=dict)  # zu/<code>_prm.dbx values
    notes: list = field(default_factory=list)

    @property
    def spacing(self) -> Optional[float]:
        """``間合い``, the model's attack range (unit not measured)."""
        try:
            return float(self.params["間合い"])
        except (KeyError, ValueError):
            return None


def _text(data: Optional[bytes]) -> str:
    return data.decode("shift_jis", errors="replace") if data else ""


class BattleAssets:
    """The battle tables of one project (``zdbx.cmp``) and its ``files/`` folder."""

    def __init__(self, files_dir: Path, zdbx_data: bytes):
        self.files_dir = Path(files_dir)
        self.zdbx_data = zdbx_data
        self.tables = dict(zdbx.read_zdbx_files(zdbx_data)) if zdbx_data else {}
        job = self.tables.get(zdbx.JOB_LIST)
        self.models = zdbx.job_list_models(_text(job)) if job else {}
        self._weapons = icons.weapon_tables(zdbx.read_zdbx_archive(zdbx_data)) if zdbx_data else {}

    @classmethod
    def from_files(cls, files_dir: Path) -> "BattleAssets":
        path = Path(files_dir) / "zdbx.cmp"
        return cls(files_dir, path.read_bytes() if path.is_file() else b"")

    # -- models ---------------------------------------------------------------------------------
    def model_codes(self) -> list[str]:
        """Codes with a ``zu/<code>.dbx`` table and a ``zu/<code>/`` folder."""
        codes = {n[3:-4] for n in self.tables if n.startswith("zu/") and n.endswith(".dbx")
                 and not n.endswith("_prm.dbx")}
        return sorted(c for c in codes if (self.files_dir / "zu" / c).is_dir())

    def model_for(self, unit: Combatant) -> Optional[str]:
        if not unit.jid:
            return None
        return zdbx.battle_model_for(self.models, unit.jid, unit.pid, unit.aid)

    def role_lines(self, code: str) -> list[tuple[str, str]]:
        return rig_contract.read_battle_roles(self.zdbx_data, code) if self.zdbx_data else []

    def unit(self, unit: Combatant, *, code: Optional[str] = None, prefix: Optional[str] = None,
             ranged: bool = False) -> UnitAssets:
        found = UnitAssets(code=code or self.model_for(unit))
        if not found.code:
            found.notes.append("no battle model for this class in jobList.dbx")
        else:
            folder = self.files_dir / "zu" / found.code
            lines = self.role_lines(found.code)
            found.prefixes = sorted({key.split("_", 1)[0] for key, _stem in lines})
            weapon_type = unit.weapon.weapon_type if unit.weapon else ""
            wanted = list(RANGED_PREFIXES.get(weapon_type, ())) if ranged else []
            wanted += list(WEAPON_PREFIXES.get(weapon_type, ()))
            choice = prefix if prefix in found.prefixes else next(
                (p for p in wanted if p in found.prefixes), found.prefixes[0] if found.prefixes else None)
            found.prefix = choice
            for key, stem in lines:
                head, _sep, role = key.partition("_")
                if head == choice and role:
                    found.roles.setdefault(role, stem)
            packs = sorted(folder.glob(f"{found.code}_*.pak")) if folder.is_dir() else []
            found.pack = next((p for p in packs if p.stem == f"{found.code}_{choice}"), packs[0] if packs else None)
            if found.pack is None:
                found.notes.append(f"zu/{found.code}/ has no weapon pack")
            param = self.tables.get(f"zu/{found.code}_prm.dbx")
            if param:
                text = _text(param)
                found.params = battle_params.read_params(text).values
                textures = zdbx.param_textures(text)
                for key in (unit.aid, unit.pid):
                    name = textures.get(key) if key else None
                    if name:
                        path = folder / f"{name}.tpl"
                        if path.is_file():
                            found.texture = path
                            break
        if unit.weapon is not None:
            weapon = icons.weapon_model(self.files_dir, unit.weapon.iid, self._weapons)
            if weapon is not None:
                found.weapon_model = weapon.path
                text = self._weapons.get(weapon.name.upper())
                if text:
                    found.weapon_kind = battle_weapons.read_weapon(text).kind
        return found

    # -- scenery --------------------------------------------------------------------------------
    def sceneries(self) -> dict[str, Path]:
        """``zbg/`` folder name -> its first ``.cmp`` pack."""
        zbg = self.files_dir / "zbg"
        found: dict[str, Path] = {}
        if zbg.is_dir():
            for folder in sorted(p for p in zbg.iterdir() if p.is_dir()):
                pack = next(iter(sorted(folder.glob("*.cmp"))), None)
                if pack is not None:
                    found[folder.name] = pack
        return found


def attack_role(roles: dict, *, crit: bool, second: bool, weapon_type: str, magic: bool, ranged: bool) -> str:
    """The role a strike plays, falling back to plain attack 1."""
    if magic:
        wanted = [SPELL]
    elif weapon_type == "bow":
        wanted = [CRIT_SHOT, SHOT] if crit else [SHOT]
    elif ranged:
        wanted = [CRIT_THROW, THROW] if crit else [THROW]
    else:
        wanted = []
    wanted += ([CRIT2] if crit and second else []) + ([CRIT1] if crit else [])
    wanted += [ATTACK2] if second else []
    wanted += [ATTACK1]
    return next((r for r in wanted if r in roles), ATTACK1)
