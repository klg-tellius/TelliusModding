"""Colour variants on Radiant Dawn: a recoloured copy of a character's map textures, battle textures
and portrait, wired in through the tables that already choose them (the counterpart of
:mod:`colour_variants`).

- **Map** (``FE10Anim.cms``): an ``FE10AnimHeader`` row gives an animation ID (``AID_MIKAYA1``) its
  texture (``mikaya1``, the loose ``ymu/<model folder>/<texture>.tpl``) and its model row. Map
  colours belong to the ID, not to an army (``AID_SOLDIER`` is ``soldier1_b``, ``AID_SOLDIER_De``
  ``soldier1_d``). Each of the character's IDs (``aid_1``-``aid_4``) gets a copy
  ``<ID>_<TAG>`` naming a recoloured ``<texture>_<tag>.tpl`` in the same folder; the copy's ordinal
  is its row number, like every retail row.
- **Battle** (``FE10Battle.cms``): an ``FE10BAnimData`` selector picks the battle unit by animation
  ID (then PID and class); each ``FE10BUnit`` owns a slice of ``FE10BTex`` rows that name the
  texture per army, or per PID (``PID_ISAIYA`` -> ``ISAIYA``), as loose ``zu/<model>/<texture>.tpl``.
  Each selector of an old ID is copied for the new ID, and the unit gets a ``PID`` row naming a
  recoloured copy of the texture the character shows now.
- **Portrait** (``Face/facedata.bin`` and ``Face/wide/facedata.bin``): ``FID_<NAME>_<TAG>`` /
  ``FID_L_<NAME>_<TAG>`` point at a recoloured copy of ``<NAME>.cms`` (one LZ10 TPL of the cut-in,
  body, mouth and eye frames: the palette changes, so every frame follows), and the character's
  ``fid`` points at it.

:func:`plan_character_variant` works out every change without writing;
:func:`apply_variant` writes it all. Class variants are not offered: Radiant Dawn's map colours are
per animation ID, so recolouring "one army of a class" has no single table row to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .colour_variants import TextureCopy, VariantPlan, _check_tag, write_copies
from .exceptions import ProjectError
from .formats import fe10_anim, fe10_battle, fe10_faces, fe10data, lz10
from .game_profile import files_root_of
from .project import ModProject
from .recolour import Recolour

FACE_DIRS = ("Face", "Face/wide")
ARMY_KEYS = ("自軍", "敵軍", "中立", "味方")


@dataclass
class RdVariantPlan(VariantPlan):
    """Every change of one Radiant Dawn variant, still unwritten."""
    anim_clones: list[tuple[str, str, str]] = field(default_factory=list)   # (AID, new AID, new texture)
    selector_clones: list[tuple[int, str]] = field(default_factory=list)     # (FE10BAnimData row, new AID)
    unit_textures: list[tuple[int, str, str]] = field(default_factory=list)  # (FE10BUnit row, PID, texture)
    rd_character_aids: list[tuple[str, str, str]] = field(default_factory=list)  # (PID, field, AID)
    rd_faces: list[tuple[str, str]] = field(default_factory=list)            # (source FID, new name)

    def summary(self) -> list[str]:
        lines = [f"New {c.kind} texture {_short(c.dest)} ({c.label})" for c in self.copies]
        lines += [f"New map animation {new} (copy of {old}), texture {texture}" for old, new, texture in self.anim_clones]
        lines += [f"Battle selector {row} copied for {aid}" for row, aid in self.selector_clones]
        lines += [f"Battle unit {row}: {pid} → {texture}.tpl" for row, pid, texture in self.unit_textures]
        lines += [f"{pid}: {key} → {aid}" for pid, key, aid in self.rd_character_aids]
        lines += [f"New portrait record FID_{name} (copy of {old})" for old, name in self.rd_faces]
        lines += [f"{pid}: portrait → {fid}" for pid, fid in self.character_fids]
        return lines


def _short(path: Path) -> str:
    parts = path.parts
    return "/".join(parts[parts.index("files") + 1:]) if "files" in parts else path.name


def plan_character_variant(project: ModProject, pid: str, tag: str, *, battle: bool = True,
                           map_models: bool = True, portrait: bool = True) -> RdVariantPlan:
    """Every change for character ``pid``'s variant ``tag``; nothing is written. Without
    ``map_models`` the animation IDs stay as they are (the battle rows are found through the old
    IDs' selectors); without ``battle`` the new IDs keep the battle textures they had."""
    tag = _check_tag(tag)
    files = files_root_of(project)
    db = fe10data.read_fe10data(project.read_logical("game_data"))
    character = next((r for r in db.characters if r.id == pid), None)
    if character is None:
        raise ProjectError(f"{pid} is not a character.")
    anim = fe10_anim.read_fe10_anim(project.read_logical("anim_data"))
    battle = fe10_battle.read_fe10_battle(project.read_logical("battle_data"))
    headers = {h.aid_name: h for h in anim.headers}
    models = anim.table("FE10AnimData").records
    units = {u.unit_name: (i, u) for i, u in enumerate(battle.unit_texture_sets)}
    plan = RdVariantPlan(f"{pid} variant {tag}")

    for key in ("aid_1", "aid_2", "aid_3", "aid_4"):
        aid = character.values.get(key)
        header = headers.get(aid) if aid else None
        if header is None:
            continue
        new_aid = f"{aid}_{tag}"
        if new_aid in headers:
            raise ProjectError(f"{new_aid} already exists: pick another tag.")
        folder = dict(models[header.model_index].strings).get(0) if header.model_index is not None else None
        source = files / "ymu" / (folder or "") / f"{header.texture_name}.tpl"
        texture = f"{header.texture_name}_{tag.lower()}"
        clone = map_models and bool(folder) and source.is_file()
        if clone:
            plan.copies.append(TextureCopy("map", aid, source, source.with_name(f"{texture}.tpl")))
            plan.anim_clones.append((aid, new_aid, texture))
            plan.rd_character_aids.append((pid, key, new_aid))
        elif map_models:
            plan.notes.append(f"{aid}: no loose map texture ymu/{folder}/{header.texture_name}.tpl; left as it is.")
        for row, selector in enumerate(battle.table("FE10BAnimData").records):
            strings = dict(selector.strings)
            if strings.get(0) != aid or strings.get(4) not in (None, pid):
                continue
            found = units.get(strings.get(12))
            if found is None:
                continue
            index, unit = found
            if clone:   # the new ID must find the same battle unit as the old one
                plan.selector_clones.append((row, new_aid))
            if not battle or any(r == index for r, _p, _t in plan.unit_textures):
                continue
            shown = next((m.texture_name for m in unit.mappings if m.condition == pid), None) or next(
                (m.texture_name for m in unit.mappings if m.condition == ARMY_KEYS[0]), unit.model_name)
            source = files / "zu" / unit.model_name / f"{shown}.tpl"
            if not source.is_file():
                plan.notes.append(f"Battle unit {unit.unit_name}: no zu/{unit.model_name}/{shown}.tpl; left as it is.")
                continue
            battle_texture = f"{shown}_{tag.lower()}"
            plan.copies.append(TextureCopy("battle", unit.unit_name, source, source.with_name(f"{battle_texture}.tpl")))
            plan.unit_textures.append((index, pid, battle_texture))

    fid = character.values.get("fid") if portrait else None
    if fid:
        name = fid.removeprefix("FID_")
        new_name = f"{name}_{tag}"
        for folder in FACE_DIRS:
            table = files / folder / "facedata.bin"
            if not table.is_file():
                continue
            record = next((r for r in fe10_faces.read_face_data(table.read_bytes()) if r.fid == fid), None)
            if record is None or not (files / folder / record.filename).is_file():
                continue
            if any(r.fid == f"FID_{new_name}" for r in fe10_faces.read_face_data(table.read_bytes())):
                raise ProjectError(f"FID_{new_name} already exists: pick another tag.")
            source = files / folder / record.filename
            plan.copies.append(TextureCopy("portrait", f"{folder}/{record.filename}", source,
                                           source.with_name(f"{new_name}.cms"), compressed=True))
            if (fid, new_name) not in plan.rd_faces:
                plan.rd_faces.append((fid, new_name))
        if plan.rd_faces:
            plan.character_fids.append((pid, f"FID_{new_name}"))
    if plan.empty:
        raise ProjectError(f"{pid} has no map, battle or portrait texture to recolour.")
    return plan


def apply_variant(project: ModProject, plan: RdVariantPlan, recolour: Recolour) -> list[str]:
    """Write the recoloured copies, then the table changes. Returns the summary lines."""
    write_copies(plan, recolour)
    files = files_root_of(project)

    if plan.anim_clones:
        data = project.read_logical("anim_data")
        for old, new, texture in plan.anim_clones:
            index = next(i for i, h in enumerate(fe10_anim.read_fe10_anim(data).headers) if h.aid_name == old)
            data, row = fe10_anim.clone_anim_header(data, index, new)
            data = fe10_anim.update_anim_header(data, row, texture_name=texture, ordinal=row)
        project.write_logical("anim_data", data)

    if plan.selector_clones or plan.unit_textures:
        data = project.read_logical("battle_data")
        selectors = fe10_battle.read_fe10_battle(data).table("FE10BAnimData").records
        for row, new_aid in plan.selector_clones:
            strings = dict(selectors[row].strings)
            data, _row = fe10_battle.clone_battle_selector(data, row, strings.get(12, ""), aid=new_aid,
                                                           pid=strings.get(4), jid=strings.get(8))
        for unit, pid, texture in plan.unit_textures:
            data = fe10_battle.add_unit_texture(data, unit, pid, texture)
        project.write_logical("battle_data", data)

    for folder in FACE_DIRS:
        table = files / folder / "facedata.bin"
        if not plan.rd_faces or not table.is_file():
            continue
        data = table.read_bytes()
        for fid, name in plan.rd_faces:
            records = fe10_faces.read_face_data(data)
            source = next((i for i, r in enumerate(records) if r.fid == fid), None)
            if source is not None and (files / folder / f"{name}.cms").is_file():
                data, _index = fe10_faces.add_face_record(data, source, name, records[source].name_id)
        project.write_keeping_original(table, data)

    if plan.rd_character_aids or plan.character_fids:
        data = project.read_logical("game_data")
        index = {r.id: r.index for r in fe10data.read_fe10data(data).characters}
        for pid, key, aid in plan.rd_character_aids:
            data = fe10data.patch_field(data, "character", index[pid], key, aid)
        for pid, fid in plan.character_fids:
            data = fe10data.patch_field(data, "character", index[pid], "fid", fid)
        project.write_logical("game_data", data)
    return plan.summary()
