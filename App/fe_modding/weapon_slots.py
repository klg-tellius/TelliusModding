"""New weapons for both games: a model slot under ``xwp/``, a battle-weapon entry and an item, plus
which visual effects a weapon can play.

A weapon model is ``xwp/<name>/<name>.cmp`` (an LZ10 pack holding ``<name>.g``, ``.gs`` and
``.tpl``). :func:`clone_weapon_model` copies one under a new name, with its entries renamed, so
the copy can take a new mesh (3D Models › Import .glb) while the original keeps its own.

The battle finds the weapon of an equipped item by the item ID without ``IID_``:

- Path of Radiance opens ``xwp/<NAME>.dbx`` in ``zdbx.cmp`` (:mod:`formats.battle_weapons`);
- Radiant Dawn reads the ``FE10BWeapon`` row of ``FE10Battle.cms`` whose key is ``<NAME>``
  (:mod:`formats.fe10_battle_weapons`).

:func:`add_weapon` does all of it in one go: the item copied from a template item (with its own
name and help text), the model slot, and the battle entry pointing at that model with the chosen
effects. The game-data file is passed in and returned (the editors keep it in their shared,
unsaved session); every other file is written at once.

Effects. A weapon's effects are played by the battle code for its type: an effect made for a
thrown weapon (``EID_K_THUNDER2_WP``, the Sonic Axe's) on a sword crashed Path of Radiance when the
sword struck. :func:`effect_uses` lists what the game's own weapons play, per type, and
:func:`effect_warnings` flags an effect no vanilla weapon of that type plays. An added effect counts
as the vanilla one it was cloned from (same skeleton and animation, :func:`effect_origin`), so a
recoloured copy of a safe effect is safe.

Nothing here uses Tk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .exceptions import ProjectError
from .formats import battle_weapons as bw, effects, fe8data, lz10, message, pak, zdbx
from .game_files import files_of, game_path, remove_tree
from .game_profile import files_root_of
from .games import Game
from .project import ModProject

MODEL_NAME_RE = re.compile(r"^[a-z0-9_]{1,24}$")
WEAPON_KEY_RE = re.compile(r"^[A-Z0-9_]{1,24}$")
FORGE = "forge"


# -- model slots ----------------------------------------------------------------------------------

def _xwp(project: ModProject):
    return files_root_of(project) / "xwp"


def weapon_models(project: ModProject) -> list[str]:
    """Every ``xwp/<name>`` folder holding ``<name>.cmp`` (forged models excluded)."""
    root = _xwp(project)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and p.name.lower() != FORGE and (p / f"{p.name}.cmp").is_file())


def _rel(project: ModProject, path) -> str:
    return game_path(*Path(str(path)).relative_to(Path(str(files_root_of(project)))).parts)


def vanilla_weapon_models(project: ModProject) -> set[str]:
    """The ``xwp/`` models the game's own battle weapons name (lower case)."""
    return {e.model.lower() for e in weapon_entries(project, vanilla=True) if e.model}


def is_added_model(project: ModProject, name: str) -> bool:
    """Whether ``xwp/<name>`` is a model the mod added (not one of the disc's)."""
    pack = _xwp(project) / name / f"{name}.cmp"
    added = files_of(project).is_added(_rel(project, pack))
    if added is not None:
        return added
    return name.lower() not in vanilla_weapon_models(project)  # the layer cannot tell: the tables can


def _rename_entries(raw: bytes, source: str, new: str) -> bytes:
    """An xwp pack (LZ10 pack, or a bare pack) with entries named ``<source>.*`` renamed ``<new>.*``."""
    try:
        data, compressed = lz10.decompress(raw), True
    except Exception:  # noqa: BLE001 - not every container is compressed
        data, compressed = raw, False
    entries = pak.read_pak_entries(data)
    items = []
    for entry in entries:
        name = entry.name
        stem, dot, ext = name.rpartition(".")
        if dot and stem.lower() == source.lower():
            name = f"{new}.{ext}"
        items.append((name, pak.read_pak_file_content(data, entry)))
    packed = pak.pack_pak(items, [entry.reserved for entry in entries])
    return lz10.compress(packed) if compressed else packed


def clone_weapon_model(project: ModProject, source: str, new: str) -> list:
    """Copy ``xwp/<source>/`` to ``xwp/<new>/``: the pack renamed ``<new>.cmp`` with its entries
    renamed too, every other file as it is. Returns the written files."""
    new = new.strip()
    if not MODEL_NAME_RE.match(new):
        raise ProjectError("A weapon model name uses 1-24 lowercase letters, digits or underscores.")
    root = _xwp(project)
    src = root / source
    if not (src / f"{source}.cmp").is_file():
        raise ProjectError(f"No weapon model xwp/{source}.")
    dest = root / new
    if dest.exists():
        raise ProjectError(f"xwp/{new} already exists.")
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for path in sorted(src.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        name = path.name
        if path.stem.lower() == source.lower():
            name = f"{new}{path.suffix}"
            if path.suffix.lower() == ".cmp":
                data = _rename_entries(data, source, new)
        (dest / name).write_bytes(data)
        written.append(dest / name)
    return written


def remove_weapon_model(project: ModProject, name: str) -> None:
    """Delete a model folder the mod added. The game's own models are refused."""
    folder = _xwp(project) / name
    if not folder.is_dir():
        raise ProjectError(f"No weapon model xwp/{name}.")
    if not is_added_model(project, name):
        raise ProjectError(f"xwp/{name} is one of the game's own weapon models.")
    remove_tree(folder)


# -- battle entries -------------------------------------------------------------------------------

@dataclass(frozen=True)
class WeaponEntry:
    """A weapon as the battle sees it, in either game."""
    key: str  # item ID without IID_ (PoR table name / RD row key)
    group: object  # PoR (kind, missile); RD FE10BWeaponType index
    model: Optional[str]
    effects: dict  # field -> EID or None ("effect", "target"; RD also "hit", "crit")
    index: Optional[int] = None  # RD row


def _por_entries(zdbx_bytes: bytes) -> list[WeaponEntry]:
    out = []
    for name, data in zdbx.read_zdbx_files(zdbx_bytes):
        if not (name.startswith("xwp/") and name.endswith(".dbx")):
            continue
        try:
            table = bw.read_weapon(data.decode("shift_jis"))
        except (bw.WeaponError, UnicodeDecodeError):
            continue
        out.append(WeaponEntry(name[4:-4], (table.kind, table.missile), table.model,
                               {"effect": table.effect_id, "target": table.damage_effect_id}))
    return out


def _rd_entries(battle_bytes: bytes) -> list[WeaponEntry]:
    from .formats import fe10_battle_weapons as fw
    return [WeaponEntry(w.labels.get("key") or "", w.type, w.labels.get("model"),
                        {k: w.labels.get(k) for k in ("hit", "crit", "effect", "target")}, w.index)
            for w in fw.read_weapons(battle_bytes)]


def weapon_entries(project: ModProject, *, vanilla: bool = False) -> list[WeaponEntry]:
    """The battle weapons of the project (``vanilla``: of the disc as extracted)."""
    if project.game is Game.RADIANT_DAWN:
        if vanilla:
            raw = project.extracted_bytes(project.logical_path("battle_data"))
            if raw is None:
                raw = project.logical_path("battle_data").read_bytes()
            return _rd_entries(lz10.decompress(raw))
        return _rd_entries(project.read_logical("battle_data"))
    path = project.logical_path("battle_data")
    raw = project.extracted_bytes(path) if vanilla else None
    return _por_entries(raw if raw is not None else path.read_bytes())


def group_label(project: ModProject, group) -> str:
    if project.game is Game.RADIANT_DAWN:
        return f"type {group}"
    kind, missile = group
    return f"{bw.KINDS.get(kind, kind)}, {bw.MISSILES.get(missile, missile)}"


# -- effects --------------------------------------------------------------------------------------

def effect_uses(project: ModProject) -> dict:
    """``{group: {field: {EID: [weapon keys]}}}`` over the game's own weapons."""
    out: dict = {}
    for entry in weapon_entries(project, vanilla=True):
        for key, eid in entry.effects.items():
            if eid:
                out.setdefault(entry.group, {}).setdefault(key, {}).setdefault(eid, []).append(entry.key)
    return out


def _pack_parts(project: ModProject, name: str, *, vanilla: bool = False) -> Optional[dict]:
    path = effects.pack_path(files_root_of(project), name)
    raw = project.extracted_bytes(path) if vanilla else None
    if raw is None:
        if vanilla and files_of(project).is_added(_rel(project, path)) is True:
            return None
        if not path.is_file():
            return None
        raw = path.read_bytes()
    try:
        return effects.read_effect_pack(raw)
    except effects.EffectError:
        return None


def _signature(parts: dict) -> tuple:
    """What a recoloured or renamed clone keeps: the skeleton and the animation."""
    by_ext = {name.rsplit(".", 1)[-1]: data for name, data in parts.items()}
    return by_ext.get("g"), by_ext.get("ga")


def effect_origin(project: ModProject, eid: str, candidates) -> Optional[str]:
    """The effect of ``candidates`` that ``eid`` is (``eid`` itself) or was cloned from: same
    skeleton and animation. None when it matches none of them."""
    if eid in candidates:
        return eid
    parts = _pack_parts(project, eid)
    if parts is None:
        return None
    signature = _signature(parts)
    if signature == (None, None):
        return None
    for name in sorted(candidates):
        source = _pack_parts(project, name, vanilla=True)
        if source is not None and _signature(source) == signature:
            return name
    return None


FIELD_LABELS = {"effect": "Effect", "target": "Target effect", "hit": "Hit effect", "crit": "Critical hit effect"}


def safe_effects(project: ModProject, group, field_name: str, uses: Optional[dict] = None) -> list[str]:
    """The effects the game's own weapons of ``group`` play in ``field_name``, most used first."""
    uses = effect_uses(project) if uses is None else uses
    found = uses.get(group, {}).get(field_name, {})
    return sorted(found, key=lambda eid: (-len(found[eid]), eid))


def effect_warnings(project: ModProject, group, chosen: dict, uses: Optional[dict] = None) -> list[str]:
    """A sentence per chosen effect no vanilla weapon of ``group`` plays in that field (or a
    clone of one). Empty: every effect is one the game itself uses that way."""
    uses = effect_uses(project) if uses is None else uses
    notes = []
    for key, eid in chosen.items():
        if not eid:
            continue
        safe = safe_effects(project, group, key, uses)
        origin = effect_origin(project, eid, safe)
        if origin is not None:
            continue
        label = FIELD_LABELS.get(key, key)
        used_elsewhere = sorted({g for g, fields in uses.items() for k, eids in fields.items()
                                 if eid in eids and g != group})
        where = (f" The game plays it on {', '.join(group_label(project, g) for g in used_elsewhere)} weapons."
                 if used_elsewhere else "")
        if safe:
            advice = f" Safe here: {', '.join(safe[:6])} (or a clone of one)."
        else:
            advice = " No vanilla weapon of this type has one: leave it empty."
        notes.append(f"{label} {eid}: no vanilla {group_label(project, group)} weapon plays it.{where}{advice}"
                     " Untested effects can crash the battle.")
    return notes


# -- new weapon -----------------------------------------------------------------------------------

@dataclass
class WeaponSpec:
    """One weapon to add: a copy of item ``template`` (an IID) under ``IID_<key>``."""
    key: str  # without IID_
    template: str  # IID_ of an existing weapon item
    name: str = ""  # in-game name; empty keeps the template's
    description: str = ""  # help text; empty keeps the template's
    model_from: Optional[str] = None  # xwp model to copy; None: the template's model; "": no model
    effects: dict = field(default_factory=dict)  # field -> EID or "" (None: keep the template's)
    trail_colour: Optional[int] = None  # Path of Radiance item trail colour (0-8)


@dataclass
class WeaponResult:
    game_data: bytes
    model: Optional[str] = None  # the new xwp/ model folder
    files: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _template_entry(project: ModProject, key: str) -> WeaponEntry:
    entry = next((e for e in weapon_entries(project) if e.key.upper() == key.upper()), None)
    if entry is None:
        raise ProjectError(f"The battle has no weapon entry for IID_{key}: pick a weapon as the template.")
    return entry


def _check_spec(project: ModProject, spec: WeaponSpec) -> tuple[str, str]:
    key = spec.key.strip().upper().removeprefix("IID_")
    if not WEAPON_KEY_RE.match(key):
        raise ProjectError("A weapon ID uses 1-24 capital letters, digits or underscores (IID_ is added).")
    if any(e.key.upper() == key for e in weapon_entries(project)):
        raise ProjectError(f"The battle already has a weapon entry {key}.")
    template = spec.template.strip()
    if not template.startswith("IID_"):
        template = "IID_" + template
    return key, template


def _write_texts(project: ModProject, texts: dict, warnings: list) -> None:
    """``{key: text}`` into the message files the game reads its item names from."""
    if not texts:
        return
    if project.game is Game.RADIANT_DAWN:
        from .chapters_fe10 import TITLE_FILES
        names = [game_path("Mess", name) for name in TITLE_FILES]
    else:
        from .game_profile import logical_rel_of
        names = [logical_rel_of(project, "common_mess")]
    files, wrote = files_of(project), False
    for rel in names:
        path = files.find(rel)
        if path is None or not path.is_file():
            continue
        kept = [m for m in message.read_messages_path(path) if m.speaker not in texts]
        added = kept + [message.Message(k, v) for k, v in texts.items()]
        files.write(rel, message.write_messages(added, message.read_text_order_path(path)))
        wrote = True
    if not wrote:
        warnings.append("No message file found: the new item has no name text.")


def add_weapon(project: ModProject, game_data: bytes, spec: WeaponSpec) -> WeaponResult:
    """Add the item, the model slot and the battle entry of ``spec``; see the module docstring.
    ``game_data`` is FE8Data.bin / FE10Data.cms (decompressed); the result carries it updated."""
    key, template = _check_spec(project, spec)
    source = _template_entry(project, template.removeprefix("IID_"))
    result = WeaponResult(game_data)
    iid = f"IID_{key}"

    # model slot
    model_from = source.model.lower() if spec.model_from is None and source.model else (spec.model_from or "")
    model = None
    if model_from:
        model = key.lower()
        if model in weapon_models(project):
            raise ProjectError(f"xwp/{model} already exists: remove it or pick another ID.")
        result.files += clone_weapon_model(project, model_from, model)
        result.model = model

    # effects
    chosen = {k: source.effects.get(k) for k in source.effects}
    for k, v in spec.effects.items():
        if v is not None:
            chosen[k] = v.strip() or None
    result.warnings += effect_warnings(project, source.group, chosen)

    # item and texts
    texts = {}
    try:
        if project.game is Game.RADIANT_DAWN:
            result.game_data = _add_rd_item(result.game_data, iid, template, spec, texts)
        else:
            result.game_data = _add_por_item(result.game_data, iid, template, spec, texts)
    except (ValueError, StopIteration) as exc:
        if model:
            remove_tree(_xwp(project) / model)
        raise ProjectError(str(exc) if not isinstance(exc, StopIteration) else f"No item {template}.") from exc

    # battle entry
    try:
        if project.game is Game.RADIANT_DAWN:
            from .formats import fe10_battle_weapons as fw
            data = project.read_logical("battle_data")
            data, _index = fw.add_weapon(data, source.index, key, model=model,
                                         labels={k: chosen.get(k) for k in ("hit", "crit", "effect", "target")})
            project.write_logical("battle_data", data)
        else:
            kind, missile = source.group
            text = bw.new_weapon_dbx(key, kind=kind, missile=missile, model=model,
                                     effect_id=chosen.get("effect"), damage_effect_id=chosen.get("target"))
            path = project.logical_path("battle_data")
            tables = dict(zdbx.read_zdbx_files(path.read_bytes()))
            tables[f"xwp/{key}.dbx"] = zdbx.encode_dbx(text)
            project.write_keeping_original(path, zdbx.build_zdbx_archive(list(tables.items())))
    except Exception:
        if model:
            remove_tree(_xwp(project) / model)
        raise
    _write_texts(project, texts, result.warnings)
    return result


def _add_por_item(data: bytes, iid: str, template: str, spec: WeaponSpec, texts: dict) -> bytes:
    items = {i.iid: i for i in fe8data.read_fe8data(data).items}
    if iid in items:
        raise ValueError(f"{iid} already exists.")
    data, index = fe8data.add_record(data, "item", iid, copy_from=items[template].index)
    key = iid.removeprefix("IID_")
    for value, label, item_field in ((spec.name, f"MIID_{key}", "miid"),
                                     (spec.description, f"MH_I_{key}", "help_key")):
        if value.strip():
            data = fe8data.add_label(data, label)
            data = fe8data.patch_item_field(data, index, item_field, label)
            texts[label] = value.strip()
    if spec.trail_colour is not None:
        data = fe8data.patch_item_field(data, index, "trail_color", int(spec.trail_colour))
    return data


def _add_rd_item(data: bytes, iid: str, template: str, spec: WeaponSpec, texts: dict) -> bytes:
    from .formats import fe10data
    items = {r.id: r for r in fe10data.read_fe10data(data).items}
    if iid in items:
        raise ValueError(f"{iid} already exists.")
    data, index = fe10data.add_record(data, "item", items[template].index, iid)
    key = iid.removeprefix("IID_")
    for value, label, item_field in ((spec.name, f"MIID_{key}", "miid"),
                                     (spec.description, f"MH_I_{key}", "help")):
        if value.strip():
            data = fe10data.patch_field(data, "item", index, item_field, label)
            texts[label] = value.strip()
    return data


def weapon_templates(project: ModProject, game_data: bytes) -> list[str]:
    """Item IDs that make a template: items with a battle weapon entry."""
    keys = {e.key.upper() for e in weapon_entries(project)}
    if project.game is Game.RADIANT_DAWN:
        from .formats import fe10data
        ids = [r.id for r in fe10data.read_fe10data(game_data).items]
    else:
        ids = [i.iid for i in fe8data.read_fe8data(game_data).items]
    return [iid for iid in ids if iid and iid.removeprefix("IID_").upper() in keys]
