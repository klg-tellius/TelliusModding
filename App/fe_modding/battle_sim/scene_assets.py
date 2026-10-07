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
decoded table. :data:`WEAPON_PREFIXES` is read off the vanilla role tables
(``ar`` on archers, ``ja`` / ``ha`` beside ``sp`` / ``ax`` for javelins and
hand axes, ``ms`` for wave swords, ``cr`` on beasts, ``br`` on dragons,
``no`` unarmed); a model without the wanted prefix falls back to any it has.

The staging values come from the same archive: ``zdbx/param.dbx``
(:meth:`BattleAssets.battle_params`) and each model's ``_prm.dbx``
(:meth:`UnitAssets.staging`), see :mod:`.staging`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .. import rig_contract
from ..formats import battle_params, battle_weapons, icons, zdbx
from .staging import BattleParams, UnitParams
from .units import Combatant

#: Weapon prefixes to try for an item weapon type, best first; ``ranged`` for distance 2+.
WEAPON_PREFIXES = {
    "sword": ("sw",), "lance": ("sp",), "axe": ("ax",), "bow": ("ar", "bw"), "knife": ("kn", "sw"),
    "flame": ("mg",), "thunder": ("mg",), "wind": ("mg",), "rod": ("mg",), "fang": ("cr", "br"),
}
RANGED_PREFIXES = {"lance": ("ja",), "axe": ("ha",), "sword": ("ms",)}
UNARMED_PREFIX = "no"
#: ``_prm.dbx`` texture keys by army (table 0x8028F6B8): player, enemy, other, allied.
ARMIES = ("自軍", "敵軍", "中立", "味方")
PLAYER_ARMY, ENEMY_ARMY = ARMIES[0], ARMIES[1]

#: Battle roles (``zu/<code>.dbx`` keys).
IDLE, READY, ATTACK1, ATTACK2, CRIT1, CRIT2 = "待機", "構え", "攻撃1", "攻撃2", "必殺1", "必殺2"
DODGE, DAMAGE, DEATH, RUN, THROW, CRIT_THROW = "回避", "ダメージ", "死亡", "走り", "投げ", "必殺投げ"
SHOT, CRIT_SHOT, SPELL = "射撃", "必殺射撃", "魔法"
SKILL, SKILL_THROW = "奥義", "奥義投げ"


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
    weapon_missile: int = 0  # the weapon table's missile (1 missiles and tomes, 2 magic swords)
    weapon_effect: Optional[str] = None  # its effectId (a tome's spell)
    weapon_damage_effect: Optional[str] = None  # its damageEffId
    params: dict = field(default_factory=dict)  # zu/<code>_prm.dbx values
    notes: list = field(default_factory=list)

    @property
    def spacing(self) -> Optional[float]:
        """``間合い``, the model's attack range in world units."""
        try:
            return float(self.params["間合い"])
        except (KeyError, ValueError):
            return None

    def staging(self) -> UnitParams:
        return UnitParams.from_values(self.params)


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
             ranged: bool = False, army: str = PLAYER_ARMY) -> UnitAssets:
        """The files ``unit`` is drawn with. The texture is looked up as
        ``resolve_and_apply_actor_texture_param`` does: by animation ID, then
        PID, then ``army`` (:data:`ARMIES`)."""
        found = UnitAssets(code=code or self.model_for(unit))
        if not found.code:
            found.notes.append("no battle model for this class in jobList.dbx")
        else:
            folder = self.files_dir / "zu" / found.code
            lines = self.role_lines(found.code)
            found.prefixes = sorted({key.split("_", 1)[0] for key, _stem in lines})
            weapon_type = unit.weapon.weapon_type if unit.weapon else ""
            wanted = list(RANGED_PREFIXES.get(weapon_type, ())) if ranged else []
            wanted += list(WEAPON_PREFIXES.get(weapon_type, ())) if unit.weapon else [UNARMED_PREFIX]
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
                for key in (unit.aid, unit.pid, army):
                    name = textures.get(key) if key else None
                    if name:
                        path = folder / f"{name}.tpl"
                        if path.is_file():
                            found.texture = path
                            break
        if unit.weapon is not None:
            weapon = icons.weapon_model(self.files_dir, unit.weapon.iid, self._weapons)
            name = weapon.name if weapon is not None else unit.weapon.iid.removeprefix("IID_")
            if weapon is not None:
                found.weapon_model = weapon.path
            text = self._weapons.get(name.upper())  # a tome's table has no model, only its effect
            if text:
                try:
                    table = battle_weapons.read_weapon(text)
                except battle_weapons.WeaponError:
                    table = None
                if table is not None:
                    found.weapon_kind = table.kind
                    found.weapon_missile = table.missile
                    found.weapon_effect = table.effect_id
                    found.weapon_damage_effect = table.damage_effect_id
        return found

    def foot_effect(self, scenery: Optional[str]) -> int:
        """The backdrop's ``footEffect`` (``zbg/<name>/param.dbx``: 0 none, 1 dust, 2 water,
        3 snow, 4 none), which picks the dust a clip raises; 1 when the table is missing."""
        text = _text(self.tables.get(f"zbg/{scenery}/param.dbx")) if scenery else None
        for line in (text or "").splitlines():
            words = line.split("#", 1)[0].split()
            if len(words) > 1 and words[0] == "footEffect":
                try:
                    return int(float(words[1]))
                except ValueError:
                    break
        return 1

    def camera_packs(self, codes) -> list[bytes]:
        """The ``xcam/<folder>/cam.cmp`` packs a fight with these models loads: each model's clip
        cameras and the tomes' ``xcam/magic`` ones (missing packs are left out)."""
        packs = []
        for folder in dict.fromkeys([*(c for c in codes if c), "magic"]):
            path = self.files_dir / "xcam" / folder / "cam.cmp"
            if path.is_file():
                packs.append(path.read_bytes())
        return packs

    def battle_params(self) -> BattleParams:
        """``zdbx/param.dbx`` (vanilla values when it is missing)."""
        text = _text(self.tables.get("zdbx/param.dbx"))
        return BattleParams.from_text(text) if text else BattleParams()

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
