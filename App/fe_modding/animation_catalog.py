"""The animation clips of a character model set, for the 3D Models page and scripts.

A clip is one ``.ga`` file at one place: a battle model keeps one archive per weapon (Path of
Radiance's ``zu/<code>/<code>_ax.pak``, Radiant Dawn's ``zu/<code>/ax.pak`` beside ``pack.cmp``),
and the same file name can sit in several of them (Boyd's ``fig1_dam_ax.ga`` is in both the axe
and the hand-axe archive). A map model keeps its clips in ``ymu/<folder>/pack.cmp`` and loose
next to it. :func:`set_clips` lists them with what plays them; :func:`clip_targets` says which
archives an edit of one clip rewrites; :func:`replace_clip_with_ga` takes a ``.ga`` written by
another tool (Tellius Forge's Blender add-on, for one) and puts it in place.

No tkinter here: ``gui.model_viewer`` uses these, and so can a script.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import rig_contract
from .formats import animation, lz10, pak, skeleton
from .game_profile import PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE

#: Frames per second of every ``.ga`` (the battle tables count 60 ticks a second; the glTF
#: export and import sample at this rate).
FPS = 60.0


class ClipError(Exception):
    """A clip that cannot be read or written as asked."""


# ---------------------------------------------------------------- containers


def is_battle_container(path: Path) -> bool:
    """A battle-model body container: FE9's weapon ``.pak`` or FE10's
    shared ``zu/<code>/pack.cmp``."""
    path = Path(path)
    return path.suffix.lower() == ".pak" or (
        path.name.casefold() == "pack.cmp" and path.parent.parent.name.casefold() == "zu")


def is_uncompressed_pack(path: Path) -> bool:
    return Path(path).suffix.lower() == ".pak"


def unpack(path: Path, data: bytes) -> tuple[list[pak.PakEntry], dict[str, bytes]]:
    raw = data if is_uncompressed_pack(path) else lz10.decompress(data)
    entries = pak.read_pak_entries(raw)
    return entries, {e.name: pak.read_pak_file_content(raw, e) for e in entries}


def pack_container(path: Path, entries: list[pak.PakEntry], files: dict[str, bytes]) -> bytes:
    packed = pak.pack_pak([(e.name, files[e.name]) for e in entries], [e.reserved for e in entries])
    return packed if is_uncompressed_pack(path) else lz10.compress(packed)


def read_container(container_path: Path) -> tuple[list[pak.PakEntry], dict[str, bytes]]:
    return unpack(container_path, Path(container_path).read_bytes())


def set_containers(container_path: Path) -> list[Path]:
    """Every container that owns the set's body and skeleton."""
    container_path = Path(container_path)
    if is_uncompressed_pack(container_path):
        return sorted(container_path.parent.glob(f"{container_path.parent.name}_*.pak"))
    return [container_path]


def animation_containers(container_path: Path) -> list[Path]:
    """Archives holding a battle set's animations.

    FE10's shared ``pack.cmp`` has the body and skeleton while sibling
    ``.pak`` archives hold animations; FE9 keeps all three together.
    """
    container_path = Path(container_path)
    if is_battle_container(container_path) and not is_uncompressed_pack(container_path):
        return sorted(container_path.parent.glob("*.pak"))
    return set_containers(container_path)


def pack_name(container_path: Path, archive: Path) -> str:
    """The clip-list name of an archive: the weapon (``ax`` of ``bole_ax.pak`` or ``ax.pak``),
    ``pack`` for a map model's ``pack.cmp``."""
    archive = Path(archive)
    if not is_battle_container(Path(container_path)) or archive.suffix.lower() != ".pak":
        return "pack"
    return archive.stem.rsplit("_", 1)[-1]


# ---------------------------------------------------------------- roles

#: Radiant Dawn battle clips (``att1_ax.ga``): the role of each file prefix. Prefixes not listed
#: (``pat1``, ``chrg``, ``app``...) are not traced yet and stay unnamed.
FE10_BATTLE_PREFIXES = {
    "pois": "ready stance",
    "tpoi": "tired stance",
    "att1": "attack 1",
    "att2": "attack 2",
    "att3": "attack 3",
    "cri1": "critical 1",
    "crit2": "critical 2",
    "dam1": "damage 1",
    "dam2": "damage 2",
    "dam3": "damage 3",
    "dog1": "dodge 1",
    "dog2": "dodge 2",
    "move": "run",
    "dead": "death",
}

#: Radiant Dawn map motions (``FE10Anim``'s motion table, ``wait_1.ga``...).
FE10_MAP_MOTIONS = {
    "wait": "idle", "move": "walk", "twait": "tired idle", "walk": "slow walk", "atk": "attack 1",
    "atk2": "attack 2", "mag": "spell 1", "mag2": "spell 2", "crit": "critical", "atku": "attack 1 upward",
    "atk2u": "attack 2 upward", "magu": "spell 1 upward", "mag2u": "spell 2 upward", "critu": "critical upward",
    "atkd": "attack 1 downward", "atk2d": "attack 2 downward", "magd": "spell 1 downward",
    "mag2d": "spell 2 downward", "critd": "critical downward", "arc": "mastery 1", "arc2": "mastery 2",
    "arc3": "mastery 3", "arc4": "mastery 4", "arc5": "mastery 5", "rod": "staff", "tack": "unarmed attack",
    "avoid": "dodge", "poise": "ready stance", "guard": "guard", "damage": "hit reaction",
    "trans": "transformation", "dead": "death", "up": "climb up", "down": "climb down", "flip": "knocked back 1",
    "flip2": "knocked back 2",
}

#: Radiant Dawn weapon archive suffixes (``FE10Anim``'s weapon table).
FE10_WEAPONS = {
    "no": "unarmed", "sw": "sword", "sp": "lance", "ja": "javelin", "ax": "axe", "ha": "hand axe",
    "bw": "bow", "rd": "staff", "bg": "crossbow",
}

#: Path of Radiance weapon archive suffixes.
FE9_WEAPONS = {
    "no": "unarmed", "sw": "sword", "sp": "lance", "ja": "javelin", "ax": "axe", "ha": "hand axe",
    "bw": "bow", "rd": "staff", "rod": "staff", "mg": "magic", "kn": "knife", "ar": "bow",
}


def weapon_label(pack: str, fe10: bool = False) -> str:
    """``ax`` -> ``axe``; ``pack`` and ``loose`` (map models) as they are."""
    table = FE10_WEAPONS if fe10 else FE9_WEAPONS
    return table.get(pack.lower(), pack)


def describe_clip(file: str, battle: bool, fe10: bool) -> str:
    """What a clip is, from its file name alone."""
    stem = Path(file).stem
    if battle and fe10:
        return FE10_BATTLE_PREFIXES.get(stem.split("_")[0].lower(), "")
    if battle:
        return rig_contract.describe_battle_file(stem)
    if fe10:
        motion = stem.rsplit("_", 1)[0].lower()
        return FE10_MAP_MOTIONS.get(motion, "")
    return rig_contract.describe_map_file(stem)


def _files_root(container_path: Path) -> Path:
    """The disc's ``files`` folder above a ``ymu/``/``zu/`` set."""
    return Path(container_path).parent.parent.parent


def _fe9_battle_users(container_path: Path) -> dict[str, list[str]]:
    """File stem (lower case) -> the ``zu/<code>.dbx`` roles that play it."""
    zdbx_path = PATH_OF_RADIANCE_PROFILE.path(_files_root(container_path), "battle_data")
    if not zdbx_path.is_file():
        return {}
    users: dict[str, list[str]] = {}
    try:
        lines = rig_contract.read_battle_roles(zdbx_path.read_bytes(), Path(container_path).parent.name)
    except Exception:  # noqa: BLE001 - a damaged table only loses the role column
        return {}
    for key, stem in lines:
        users.setdefault(stem.lower(), []).append(rig_contract.describe_role(key))
    return users


def _fe10_map_users(container_path: Path) -> dict[str, list[str]]:
    """File name (lower case) -> ``weapon: motion`` of every ``FE10Anim`` row that draws this
    map model folder and plays the file."""
    from .formats import fe10_anim

    path = RADIANT_DAWN_PROFILE.path(_files_root(container_path), "anim_data")
    if not path.is_file():
        return {}
    try:
        data = path.read_bytes()
        table = fe10_anim.read_fe10_anim(lz10.decompress(data) if data[:1] == b"\x10" else data)
    except Exception:  # noqa: BLE001
        return {}
    folder = Path(container_path).parent.name.lower()
    users: dict[str, set[str]] = {}
    for model in table.models:
        if model.folder.lower() != folder:
            continue
        for w, row in enumerate(model.variants):
            if w >= len(table.weapons):
                break
            weapon = FE10_WEAPONS.get(table.weapons[w].archive_suffix, table.weapons[w].archive_suffix)
            for m, variant in enumerate(row):
                if not variant or m >= len(table.motions):
                    continue
                motion = table.motions[m].file_stem
                name = f"{motion}_{variant}.ga".lower()
                users.setdefault(name, set()).add(f"{weapon}: {FE10_MAP_MOTIONS.get(motion, motion)}")
    return {name: sorted(found) for name, found in users.items()}


# ---------------------------------------------------------------- the clip list


@dataclass
class ClipInfo:
    """One clip of a set. ``packs`` lists every archive holding this exact file (same name and
    same bytes); a file of the same name with other bytes in another archive is another clip."""

    file: str
    packs: list[str]
    data: bytes = field(repr=False)
    role: str = ""
    used_by: list[str] = field(default_factory=list)
    frames: int = 0
    loops: bool = False
    events: list = field(default_factory=list, repr=False)
    fe10: bool = False
    error: str = ""

    @property
    def pack(self) -> str:
        """The first archive holding the clip."""
        return self.packs[0] if self.packs else ""

    @property
    def stem(self) -> str:
        return Path(self.file).stem

    def combat_frames(self) -> dict[int, list[int]]:
        """Combat code (0 hit, 1 swing, 2 release) -> the frames it fires at."""
        out: dict[int, list[int]] = {}
        for key in self.events:
            for code in key.codes:
                value = code[0] if isinstance(code, tuple) else code
                if value in rig_contract.COMBAT_CODES:
                    out.setdefault(value, []).append(key.frame)
        return out

    def label(self) -> str:
        """``fig1_dam_ax.ga (ax, ha)`` when the clip sits in several archives."""
        return self.file if len(self.packs) <= 1 else f"{self.file} ({', '.join(self.packs)})"


def _clip(file: str, packs: list[str], data: bytes, battle: bool) -> ClipInfo:
    try:
        fe10 = animation.is_fe10_animation(data)
    except animation.AnimationError:
        fe10 = False
    info = ClipInfo(file, packs, data, role=describe_clip(file, battle, fe10), fe10=fe10)
    try:
        anim = animation.read_animation_bytes(data)
        info.frames = anim.header.end_frame
        info.loops = anim.header.loops
        info.events = rig_contract._events(data)
    except Exception as exc:  # noqa: BLE001 - listed, flagged, not playable
        info.error = str(exc)
    return info


def set_clips(container_path: Path, pending: dict[Path, bytes] | None = None) -> list[ClipInfo]:
    """Every clip of the set, archive by archive in file order, a file shared by several archives
    once. ``pending`` maps paths to bytes an import would write (the review shows those)."""
    container_path = Path(container_path)
    pending = pending or {}

    def data_of(path: Path) -> bytes:
        return pending.get(path) or path.read_bytes()

    battle = is_battle_container(container_path)
    found: list[tuple[str, str, bytes]] = []
    containers = list(dict.fromkeys(animation_containers(container_path) if battle else [container_path]))
    for archive in containers:
        _e, files = unpack(archive, data_of(archive))
        name = pack_name(container_path, archive)
        found += [(n, name, d) for n, d in files.items() if Path(n).suffix.lower() == ".ga"]
    if not battle:
        found += [(p.name, "loose", data_of(p)) for p in sorted(container_path.parent.glob("*.ga"))]

    clips: list[ClipInfo] = []
    by_key: dict[tuple[str, bytes], ClipInfo] = {}
    for name, archive, data in found:
        key = (name.lower(), data)
        if key in by_key:
            by_key[key].packs.append(archive)
            continue
        clip = _clip(name, [archive], data, battle)
        by_key[key] = clip
        clips.append(clip)

    fe10 = any(c.fe10 for c in clips)
    if battle and not fe10:
        users = _fe9_battle_users(container_path)
        for clip in clips:
            clip.used_by = users.get(clip.stem.lower(), [])
    elif not battle and fe10:
        users = _fe10_map_users(container_path)
        for clip in clips:
            clip.used_by = users.get(clip.file.lower(), [])
    return clips


def clip_packs(clips: list[ClipInfo], clip: ClipInfo) -> list[str] | None:
    """What to pass as ``pack`` to edit ``clip``: None when no other clip has its file name (every
    copy is this clip), else the clip's own archives."""
    if any(c is not clip and c.file == clip.file for c in clips):
        return list(clip.packs)
    return None


def clips_from_animations(animations: list[tuple[str, bytes]], battle: bool = False) -> list[ClipInfo]:
    """Clips for a list of ``(file name, bytes)`` with no archive known (a preview of loose files)."""
    return [_clip(name, [""], data, battle) for name, data in animations]


def clips_by_pack(clips: list[ClipInfo]) -> dict[str, list[ClipInfo]]:
    """The tree of the clip list: archive -> its clips (a shared clip under its first archive)."""
    out: dict[str, list[ClipInfo]] = {}
    for clip in clips:
        out.setdefault(clip.pack, []).append(clip)
    return out


# ---------------------------------------------------------------- writing one clip


def clip_targets(container_path: Path, file: str, pack: str | list[str] | None = None
                 ) -> tuple[list[Path], list[str]]:
    """The archives (or loose file) an edit of ``file`` rewrites, and a note for the review.

    With ``pack`` (an archive name or a list of them), those archives only. Without, every archive holding ``file`` with the
    same bytes as the first one: identical copies are one clip (Boyd's damage clip is played with
    the axe and the hand axe), so they change together. Copies that differ stay as they are, and
    the note says so."""
    container_path = Path(container_path)
    containers = list(dict.fromkeys(set_containers(container_path) + animation_containers(container_path)))
    holders: list[tuple[Path, bytes]] = []
    for archive in containers:
        _e, files = read_container(archive)
        if file in files:
            holders.append((archive, files[file]))
    if not holders:
        loose = container_path.parent / file
        if loose.is_file():
            return [loose], []
        raise ClipError(f"{file} is not an animation of this set.")
    if pack is not None:
        wanted = [pack] if isinstance(pack, str) else list(pack)
        chosen = [a for a, _d in holders if pack_name(container_path, a) in wanted]
        if not chosen:
            raise ClipError(f"{file} is not in the {', '.join(wanted)} archive of this set.")
        others = [pack_name(container_path, a) for a, _d in holders if a not in chosen]
        notes = [f"{file} changes in the {', '.join(wanted)} archive only; the copy in {', '.join(others)} "
                 "stays as it is."] if others else []
        return chosen, notes
    first = holders[0][1]
    same = [a for a, d in holders if d == first]
    different = [pack_name(container_path, a) for a, d in holders if d != first]
    notes = []
    if len(same) > 1:
        notes.append(f"{file} is shared by the {', '.join(pack_name(container_path, a) for a in same)} "
                     "archives: every copy changes.")
    if different:
        notes.append(f"The {', '.join(different)} archive holds a different {file}; it stays as it is "
                     "(pick that archive to change it).")
    return same, notes


def clip_bytes(container_path: Path, file: str, pack: str | list[str] | None = None) -> bytes:
    """The current bytes of a clip (the first archive holding it, or ``pack``'s)."""
    targets, _notes = clip_targets(container_path, file, pack)
    target = targets[0]
    if target.suffix.lower() == ".ga":
        return target.read_bytes()
    return read_container(target)[1][file]


def clip_output(container_path: Path, file: str, ga: bytes, pack: str | list[str] | None = None
                ) -> tuple[dict[Path, bytes], list[str]]:
    """The files to write so ``file`` becomes ``ga`` (see :func:`clip_targets`), and the notes."""
    targets, notes = clip_targets(container_path, file, pack)
    out: dict[Path, bytes] = {}
    for target in targets:
        if target.suffix.lower() == ".ga":
            out[target] = ga
            continue
        entries, files = read_container(target)
        files[file] = ga
        out[target] = pack_container(target, entries, files)
    return out, notes


def _skeleton_bone_count(container_path: Path) -> int | None:
    for archive in set_containers(Path(container_path)):
        _e, files = read_container(archive)
        for name, data in files.items():
            if Path(name).suffix.lower() == ".g":
                return len(skeleton.read_skeleton_file(data).bones)
    return None


def retimed_events(events: list, old_end: int, new_end: int) -> list:
    """``events`` moved in proportion from an ``old_end``-frame clip to a ``new_end``-frame one."""
    if old_end <= 0 or old_end == new_end:
        return list(events)
    ratio = new_end / old_end
    return [type(e)(min(new_end, round(e.frame * ratio)), e.codes) for e in events]


def replace_clip_with_ga(container_path: Path, file: str, ga: bytes, pack: str | list[str] | None = None
                         ) -> tuple[dict[Path, bytes], list[str]]:
    """Put a ``.ga`` written elsewhere (Tellius Forge's Blender add-on, a hex edit, another set)
    in place of the set's clip ``file``.

    Refused when the file does not parse, is the other game's format, or animates bones the set's
    skeleton lacks. A file with no event track takes the replaced clip's events, moved in
    proportion to the new length: Blender exports carry none, and a battle clip without its hit
    and swing events stalls the fight."""
    try:
        new = animation.read_animation_bytes(ga)
        new_fe10 = animation.is_fe10_animation(ga)
    except Exception as exc:  # noqa: BLE001
        raise ClipError(f"Not a readable .ga file: {exc}") from exc
    old = clip_bytes(container_path, file, pack)
    old_fe10 = animation.is_fe10_animation(old)
    if new_fe10 != old_fe10:
        game = "Radiant Dawn" if old_fe10 else "Path of Radiance"
        raise ClipError(
            f"This file is in the other game's .ga format; {file} is a {game} clip. In Tellius Forge, set the "
            f"action's ga_game_flag to {1 if old_fe10 else 0} and export again.")
    bones = _skeleton_bone_count(container_path)
    used = {g.bone_index for g in new.groups}
    if bones is not None and used and max(used) >= bones:
        raise ClipError(
            f"The file animates bone {max(used)}, but this set's skeleton has {bones} bones: it was made for "
            "another skeleton.")
    warnings: list[str] = []
    new_events = rig_contract._events(ga)
    old_events = rig_contract._events(old)
    old_end = animation.read_animation_bytes(old).header.end_frame
    if not new_events and old_events:
        moved = retimed_events(old_events, old_end, new.header.end_frame)
        ga = rig_contract.replace_events(ga, moved)
        text = "The file has no events: the replaced clip's were copied"
        if old_end != new.header.end_frame:
            text += f" and moved from {old_end} to {new.header.end_frame} frames"
        warnings.append(text + ". Check them with Events...")
    warnings += [e.replace("the fight would", "the fight may") for e in rig_contract.event_errors(file, ga, old)]
    out, notes = clip_output(container_path, file, ga, pack)
    return out, notes + warnings


# ---------------------------------------------------------------- copying from another model


def character_sets(files_root: Path) -> list[tuple[str, Path]]:
    """``(label, container)`` of every animated character set under a disc's ``files`` folder:
    map units ``ymu/<folder>/pack.cmp`` and battle models ``zu/<code>`` (Radiant Dawn's
    ``pack.cmp``, Path of Radiance's first weapon ``.pak``)."""
    files_root = Path(files_root)
    sets: list[tuple[str, Path]] = []
    ymu = files_root / "ymu"
    if ymu.is_dir():
        sets += [(f"ymu/{p.parent.name}", p) for p in sorted(ymu.glob("*/pack.cmp"))]
    zu = files_root / "zu"
    if zu.is_dir():
        for folder in sorted(p for p in zu.iterdir() if p.is_dir()):
            shared = folder / "pack.cmp"
            if shared.is_file():
                sets.append((f"zu/{folder.name}", shared))
                continue
            paks = sorted(folder.glob(f"{folder.name}_*.pak"))
            if paks:
                sets.append((f"zu/{folder.name}", paks[0]))
    return sets


def disc_game(files_root: Path) -> str:
    """``fe9`` or ``fe10`` for a disc's ``files`` folder (by its main data file), ``""`` if neither."""
    files_root = Path(files_root)
    if (files_root / "FE10Data.cms").is_file() or (files_root / "FE10Anim.cms").is_file():
        return "fe10"
    if (files_root / "FE8Data.bin").is_file() or (files_root / "zdbx.cmp").is_file():
        return "fe9"
    return ""


def copy_sources(project_files: Path | None = None) -> list[tuple[str, Path]]:
    """``(label, files folder)`` to copy clips from: the project's own files, then every disc
    registered as a vanilla store (Settings > Vanilla discs), the other game's included."""
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    if project_files is not None and Path(project_files).is_dir():
        out.append(("This project", Path(project_files)))
        seen.add(Path(project_files).resolve())
    try:
        from . import vanilla_store
        stores = vanilla_store.list_stores()
    except Exception:  # noqa: BLE001 - no store registry: the project only
        stores = []
    for store in stores:
        files = Path(store.root) / "files"
        if not files.is_dir() or files.resolve() in seen:
            continue
        seen.add(files.resolve())
        game = {"fe9": "Path of Radiance", "fe10": "Radiant Dawn"}.get(disc_game(files), "disc")
        out.append((f"Vanilla {game} ({store.disc_id})", files))
    return out


def _clip_key(clip: ClipInfo, set_code: str) -> str:
    """A clip's name without its set's code (``swm1_at1_sw`` -> ``at1_sw``)."""
    stem = clip.stem.lower()
    code = set_code.lower()
    return stem[len(code) + 1:] if code and stem.startswith(code + "_") else stem


def _role_base(role: str) -> str:
    """``dodge 1`` -> ``dodge``; ``critical 1, followed by dodge`` stays as it is."""
    return role.rstrip("0123456789 ").strip()


def matching_clip(source: ClipInfo, source_set: str, targets: list[ClipInfo], target_set: str
                  ) -> ClipInfo | None:
    """The target clip that plays what ``source`` plays: same name once the set codes are dropped
    (``swm1_at1_sw.ga`` -> ``swf1_at1_sw.ga``), else the same role (``fig1_at1_ax.ga``, attack 1,
    -> Radiant Dawn's ``att1_ax.ga``), the same weapon first."""
    key = _clip_key(source, source_set)
    weapon = key.rsplit("_", 1)[-1] if "_" in key else ""
    role = source.role.lower()
    base = _role_base(role)
    best, best_score = None, 0
    for clip in targets:
        other = _clip_key(clip, target_set)
        if other == key:
            return clip
        target_role = clip.role.lower()
        score = 0
        if role and target_role == role:
            score = 50
        elif base and target_role and (_role_base(target_role) == base or base.endswith("/ " + target_role)
                                       or target_role.endswith("/ " + base)):
            score = 20
        if score and weapon and other.rsplit("_", 1)[-1] == weapon:
            score += 5
        if score > best_score:
            best, best_score = clip, score
    return best


def _body_files(container_path: Path) -> dict[str, bytes]:
    """The pack holding the set's skeleton (and body)."""
    _e, files = read_container(set_containers(Path(container_path))[0])
    return files


def _skeleton_data(container_path: Path) -> bytes:
    files = _body_files(container_path)
    found = [d for n, d in files.items() if Path(n).suffix.lower() == ".g"]
    if not found:
        raise ClipError(f"{Path(container_path).parent.name} has no skeleton.")
    return found[0]


#: Bones the two games name differently (Path of Radiance, Radiant Dawn).
BONE_ALIASES = (("Head", "_head_"), ("Top", "_top_"))


def bone_renames(source_names: list[str], target_names: set[str]) -> dict[str, str]:
    """Source bone -> target bone for the names :data:`BONE_ALIASES` pairs, when the target has
    the other name and not the source's own."""
    out = {}
    for a, b in BONE_ALIASES:
        for old, new in ((a, b), (b, a)):
            if old in source_names and old not in target_names and new in target_names and new not in source_names:
                out[old] = new
    return out


def _rename_glb_nodes(glb: bytes, renames: dict[str, str]) -> bytes:
    """``glb`` with the nodes named in ``renames`` renamed."""
    import json
    import struct

    if not renames:
        return glb
    json_len = struct.unpack_from("<I", glb, 12)[0]
    doc = json.loads(glb[20:20 + json_len].decode("utf-8"))
    for node in doc.get("nodes", []):
        if node.get("name") in renames:
            node["name"] = renames[node["name"]]
    text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    rest = glb[20 + json_len:]
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + rest
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


@dataclass
class ClipCopy:
    """What :func:`copy_clip` would write: the files, the notes for the review, and how many of
    the source clip's animated bones the target skeleton has by name."""

    outputs: dict[Path, bytes]
    warnings: list[str]
    matched: int
    animated: int


def copy_clip(source_container: Path, source_file: str, target_container: Path, target_file: str,
              *, source_pack: str | list[str] | None = None, target_pack: str | list[str] | None = None
              ) -> ClipCopy:
    """The clip ``source_file`` of one character set played on another set's skeleton, in place
    of its clip ``target_file``: same game or the other one.

    The source clip is posed on its own skeleton and read back on the target's (through glTF, as an
    imported animation: ``gltf_export`` then ``gltf_import.import_animation``). Bones are matched
    by name; the target's other bones keep their rest pose. The clip is written in the target
    game's format, over the replaced clip's footer (Radiant Dawn's material, visibility and
    particle tracks).

    Events: within a game, the source clip's (its hits, sounds, trails go with its motion). Across
    the games, the replaced clip's moved in proportion to the new length: sound and effect numbers
    differ between the discs, and the combat codes the fight waits for stay in place.

    Refused when fewer than a quarter of the source clip's animated bones are in the target
    skeleton (bones are matched by name, and :data:`BONE_ALIASES` across the games), or fewer than
    six: the motion would not carry over (fit the model with Fit new rig... instead)."""
    from .formats import gltf_export, gltf_import

    source_data = clip_bytes(source_container, source_file, source_pack)
    template = clip_bytes(target_container, target_file, target_pack)
    try:
        source_anim = animation.read_animation_bytes(source_data)
    except Exception as exc:  # noqa: BLE001
        raise ClipError(f"{source_file} could not be read: {exc}") from exc
    source_bones = skeleton.read_skeleton_file(_skeleton_data(source_container)).bones
    target_g = _skeleton_data(target_container)
    target_bones = skeleton.read_skeleton_file(target_g).bones

    target_names = {b.name for b in target_bones}
    renames = bone_renames([b.name for b in source_bones], target_names)
    animated = {renames.get(n, n) for n in
                (source_bones[g.bone_index].name for g in source_anim.groups if g.bone_index < len(source_bones))}
    matched = animated & target_names
    if len(matched) < 6 or len(matched) * 4 < len(animated):
        raise ClipError(
            f"Only {len(matched)} of the {len(animated)} bones {source_file} moves are in the target skeleton "
            "(bones are matched by name): the motion would not carry over. Give the target model the source "
            "set's animations with Fit new rig... instead.")

    glb = _rename_glb_nodes(gltf_export.export_glb([], source_bones, {}, [("clip", source_anim)]), renames)
    try:
        ga, warnings = gltf_import.import_animation(glb, target_g, animation_name="clip", template=template)
    except Exception as exc:  # noqa: BLE001
        raise ClipError(f"{source_file} could not be played on the target skeleton: {exc}") from exc
    warnings = [w for w in warnings if not w.startswith(
        ("Events copied", "The replaced animation's footer", "Animated joints with no bone"))]

    same_game = animation.is_fe10_animation(source_data) == animation.is_fe10_animation(template)
    new_end = animation.read_animation_bytes(ga).header.end_frame
    if same_game:
        events = rig_contract._events(source_data)
        note = f"Events: {source_file}'s."
    else:
        old_end = animation.read_animation_bytes(template).header.end_frame
        events = retimed_events(rig_contract._events(template), old_end, new_end)
        note = (f"Events: {target_file}'s" + (f", moved from {old_end} to {new_end} frames" if old_end != new_end
                                               else "") + " (sound and effect numbers differ between the games). "
                "Check them with Events...")
    ga = rig_contract.replace_events(ga, events)
    missing = sorted(animated - target_names)
    notes = [f"{len(matched)} of the {len(animated)} bones {source_file} moves are in the target skeleton."]
    if missing:
        shown = ", ".join(missing[:12]) + (", ..." if len(missing) > 12 else "")
        notes.append(f"Not in the target skeleton (their motion is dropped): {shown}.")
    still = sorted(target_names - animated - {b.name for b in target_bones if b.name.startswith("_")})
    if still:
        notes.append(f"{len(still)} target bones have no motion in the source clip and keep their rest pose.")
    notes.append(note)
    notes += [e.replace("the fight would", "the fight may") for e in rig_contract.event_errors(target_file, ga, template)]
    outputs, where = clip_output(target_container, target_file, ga, target_pack)
    return ClipCopy(outputs, where + notes + warnings, len(matched), len(animated))


# ---------------------------------------------------------------- events

#: Short names of the combat codes for the clip list.
COMBAT_SHORT = {0: "hit", 1: "swing", 2: "release"}


def event_code_label(code) -> str:
    """One event code as the summary shows it: ``0 hit``, ``1510 sound``, ``20 sword trail start``;
    Radiant Dawn's ``(code, parameter)`` as ``code:parameter``."""
    value, parameter = code if isinstance(code, tuple) else (code, None)
    text = str(value) if parameter is None else f"{value}:{parameter}"
    if value in COMBAT_SHORT:
        return f"{text} {COMBAT_SHORT[value]}"
    if value >= 1000:
        return f"{text} sound"
    name = rig_contract.EVENT_NAMES.get(value)
    return f"{text} {name}" if name else text


def event_marks(events: list, length: int, x0: float, width: float, margin: float = 8.0
                ) -> list[tuple[float, int, bool]]:
    """``(x, frame, combat)`` of each event key on a strip under a slider at ``x0`` of ``width``
    pixels (the slider's thumb keeps ``margin`` pixels at each end)."""
    if width <= 2 * margin:
        return []
    length = max(length, 1)
    out = []
    for key in events:
        combat = any((c[0] if isinstance(c, tuple) else c) in rig_contract.COMBAT_CODES for c in key.codes)
        x = x0 + margin + (width - 2 * margin) * min(max(key.frame, 0), length) / length
        out.append((x, key.frame, combat))
    return out


# ---------------------------------------------------------------- playback


def playback_frame(started: float, now: float, length: int, speed: float = 1.0, loop: bool = True,
                   start_frame: float = 0.0) -> tuple[float, bool]:
    """The frame to show ``now`` for a clip of ``length`` frames that started playing at
    ``started`` from ``start_frame``, at ``speed`` times the game's 60 frames a second; and
    whether playback has ended (never when looping)."""
    length = max(length, 1)
    frame = start_frame + (now - started) * FPS * speed
    if loop:
        return frame % (length + 1), False
    if frame >= length:
        return float(length), True
    return frame, False


def clock() -> float:
    return time.monotonic()
