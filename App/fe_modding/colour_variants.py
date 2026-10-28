"""Colour variants: a recoloured copy of a character's or a class's battle
texture, map texture and portrait, wired in through the tables that already
choose them (Path of Radiance).

Nothing here needs a code patch; each table already looks textures up per
character or per army:

- **Battle** (``zu/<code>_prm.dbx``): the texture is picked by animation
  ID, then PID, then army key. A character variant adds a ``PID_`` line
  naming a recoloured copy of the texture the character shows now; a class
  variant points the army's line at a recoloured copy of that army's
  texture.
- **Map** (``FE8Anim.bin``): each record names one ``tex_<n>.tpl`` per
  army. The recoloured copies get unused numbers in the same folder (loose
  files, like the vanilla army colours). A character whose animation ID is
  its own (``AID_ARMOR_GA``: Gatrie and his event copy) has its numbers
  changed in place; one sharing its class's ID gets a copy of the records
  under ``<ID>_<TAG>``, and the job-list line that ID had (if any) is
  copied with it so the battle model stays the same.
- **Portrait** (``Face/facedata.bin``): ``FID_<NAME>_<TAG>`` and
  ``FID_L_<NAME>_<TAG>`` point at recoloured copies of both texture sets
  (the palette changes, so the mouth and eye frames follow), and the
  character's ``fid`` points at the new small one.

:func:`plan_character_variant` / :func:`plan_class_variant` work out every
change without writing; :meth:`VariantPlan.previews` shows the textures
before and after a :class:`~fe_modding.recolour.Recolour`;
:func:`apply_variant` writes it all.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image

from . import model_slots, portraits
from .exceptions import ProjectError
from .formats import anim_registry, fe8data, lz10, pak, tpl, zdbx
from .formats.fe9_portraits import large_face_id
from .games import Game
from .game_profile import files_root_of, logical_game_path_of
from .project import ModProject
from .recolour import Recolour, recolour_tpl

TAG_RE = re.compile(r"^[A-Z][A-Z0-9]{0,7}$")
#: battle texture-line army keys, in FE8Anim.bin's army order
ARMY_KEYS = ("自軍", "敵軍", "中立", "味方")
ARMY_NAMES = dict(zip(ARMY_KEYS, anim_registry.ARMIES))
NULL_TEXTURE = "_null_"


@dataclass
class TextureCopy:
    """One recoloured copy to write: ``source`` read from ``source_path``
    (inside ``pack.cmp`` when ``pack_entry`` is set), written to ``dest``."""
    kind: str  # "battle", "map" or "portrait"
    label: str
    source_path: Path
    dest: Path
    pack_entry: str | None = None
    compressed: bool = False  # LZ10 (portrait .cms)

    def source_bytes(self) -> bytes:
        data = self.source_path.read_bytes()
        if self.pack_entry is not None:
            data = lz10.decompress(data)
            entry = next(e for e in pak.read_pak_entries(data) if e.name == self.pack_entry)
            return pak.read_pak_file_content(data, entry)
        return lz10.decompress(data) if self.compressed else data


@dataclass
class VariantPlan:
    """Every change of one variant, still unwritten."""
    title: str
    copies: list[TextureCopy] = field(default_factory=list)
    battle_lines: list[tuple[str, str, str]] = field(default_factory=list)  # (code, key, texture)
    job_lines: list[tuple[str, str]] = field(default_factory=list)  # (code, AID) to add
    map_textures: list[tuple[str, tuple[int, int, int, int]]] = field(default_factory=list)  # in place
    map_clones: list[tuple[str, str, tuple[int, int, int, int]]] = field(default_factory=list)  # (from, new, ids)
    character_aids: list[tuple[str, bool, str]] = field(default_factory=list)  # (PID, promoted, AID)
    faces: list[tuple[str, str, str]] = field(default_factory=list)  # (source FID, new FID, new file)
    character_fids: list[tuple[str, str]] = field(default_factory=list)  # (PID, FID)
    notes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.copies

    def summary(self) -> list[str]:
        """One line per change, for the dialog and the change log."""
        lines = [f"New {c.kind} texture {_short(c.dest)} ({c.label})" for c in self.copies]
        lines += [f"Battle model zu/{code}: {key} → {texture}.tpl" for code, key, texture in self.battle_lines]
        lines += [f"Job list: {aid} → zu/{code}" for code, aid in self.job_lines]
        lines += [f"Map model {aid}: textures {' '.join(map(str, ids))}" for aid, ids in self.map_textures]
        lines += [f"New map model {new} (copy of {old}), textures {' '.join(map(str, ids))}"
                  for old, new, ids in self.map_clones]
        lines += [f"{pid}: {'promoted' if promoted else 'unpromoted'} animation ID → {aid}"
                  for pid, promoted, aid in self.character_aids]
        lines += [f"New portrait record {new} (copy of {old})" for old, new, _ in self.faces]
        lines += [f"{pid}: portrait → {fid}" for pid, fid in self.character_fids]
        return lines

    def previews(self, recolour: Recolour, limit: int | None = None) -> list[tuple[str, Image.Image, Image.Image]]:
        """``(label, before, after)`` for the first image of each copy."""
        out = []
        for copy in self.copies[:limit]:
            source = copy.source_bytes()
            before = tpl.read_tpl_images(io.BytesIO(source))[0]
            after = tpl.read_tpl_images(io.BytesIO(recolour_tpl(source, recolour)))[0]
            out.append((f"{copy.kind}: {copy.label}", before, after))
        return out


def _short(path: Path) -> str:
    parts = path.parts
    return "/".join(parts[parts.index("files") + 1:]) if "files" in parts else path.name


def _check_tag(tag: str) -> str:
    tag = tag.strip().upper()
    if not TAG_RE.match(tag) or f"_{tag}" in anim_registry.WEAPON_SUFFIXES:
        raise ProjectError("The variant tag is 1-8 capital letters or digits starting with a letter "
                           "(not a weapon suffix such as SW).")
    return tag


class _Context:
    """The tables a plan reads, loaded once."""

    def __init__(self, project: ModProject) -> None:
        if project.game is not Game.PATH_OF_RADIANCE:
            raise ProjectError("Colour variants are only available for Path of Radiance projects.")
        self.project = project
        self.files = files_root_of(project)
        self.fe8 = fe8data.read_fe8data(logical_game_path_of(project, "game_data").read_bytes())
        self.characters = {c.pid: c for c in self.fe8.characters if c.pid}
        self.classes = {c.jid: c for c in self.fe8.classes if c.jid}
        self.records = model_slots.map_model_records(project)
        self.models = {key: code for key, code, _comment in model_slots.job_list(project)}
        self.taken_numbers: dict[str, set[int]] = {}
        self.planned_paths: set[Path] = set()

    # -- shared lookups -----------------------------------------------------------------
    def tiers(self, character) -> list[tuple[fe8data.ClassEntry, bool]]:
        """(class, promoted) for each class the character can be in: a
        promoted start has one, an unpromoted one also its promotion."""
        job = self.classes.get(character.jid)
        if job is None:
            return []
        if fe8data.class_category(job, self.fe8.classes) == "Promoted":
            return [(job, True)]
        tiers = [(job, False)]
        promoted = self.classes.get(job.promotes_to)
        if promoted is not None and promoted is not job:
            tiers.append((promoted, True))
        return tiers

    @staticmethod
    def own_aid(character, promoted: bool) -> str | None:
        return character.aid_promoted if promoted else character.aid_unpromoted

    def users_of_aid(self, aid: str) -> tuple[set[str], set[str]]:
        """(PIDs, JIDs) whose records name ``aid``."""
        pids = {c.pid for c in self.characters.values() if aid in (c.aid_unpromoted, c.aid_promoted)}
        jids = {j.jid for j in self.classes.values() if j.aid == aid}
        return pids, jids

    def records_of(self, aid: str) -> list[anim_registry.AnimRecord]:
        return [r for r in self.records if r.base_aid == aid]

    def battle_textures(self, code: str) -> dict[str, str] | None:
        try:
            return model_slots.battle_textures(self.project, code) or None
        except ProjectError:
            return None

    def new_path(self, path: Path) -> Path:
        if path.exists() or path in self.planned_paths:
            raise ProjectError(f"{_short(path)} already exists: pick another tag.")
        self.planned_paths.add(path)
        return path

    # -- map textures -------------------------------------------------------------------
    def map_source(self, folder: str, number: int) -> tuple[Path, str | None] | None:
        """Where ``ymu/<folder>tex_<n>.tpl`` lives: loose, or inside pack.cmp."""
        base = self.files / "ymu" / folder.rstrip("/")
        loose = base / f"tex_{number}.tpl"
        if loose.is_file():
            return loose, None
        pack_path = base / "pack.cmp"
        if pack_path.is_file():
            names = {e.name for e in pak.read_pak_entries(lz10.decompress(pack_path.read_bytes()))}
            if f"tex_{number}.tpl" in names:
                return pack_path, f"tex_{number}.tpl"
        return None

    def free_number(self, folder: str) -> int:
        """An unused texture number of a ``ymu/`` folder (0-255)."""
        if folder not in self.taken_numbers:
            base = self.files / "ymu" / folder.rstrip("/")
            taken = {r_id for r in self.records if r.class_folder == folder for r_id in r.texture_ids}
            names = [p.name for p in base.glob("tex_*.tpl")]
            pack_path = base / "pack.cmp"
            if pack_path.is_file():
                names += [e.name for e in pak.read_pak_entries(lz10.decompress(pack_path.read_bytes()))]
            for name in names:
                match = re.fullmatch(r"tex_(\d+)\.tpl", name)
                if match:
                    taken.add(int(match.group(1)))
            self.taken_numbers[folder] = taken
        taken = self.taken_numbers[folder]
        number = next((n for n in range(1, 256) if n not in taken), None)
        if number is None:
            raise ProjectError(f"ymu/{folder} has no unused texture number left.")
        taken.add(number)
        return number

    def recolour_map_numbers(self, plan: VariantPlan, aid: str, armies: range | list[int],
                             label: str) -> tuple[int, int, int, int] | None:
        """New texture numbers for ``aid``'s records with the chosen armies'
        textures copied (each distinct source once); None when there is
        nothing to copy."""
        records = self.records_of(aid)
        if not records:
            plan.notes.append(f"No map model records for {aid}: map texture skipped.")
            return None
        folders = {r.class_folder for r in records}
        if len(folders) > 1:
            plan.notes.append(f"{aid}'s weapon sets use several folders ({', '.join(sorted(folders))}): "
                              "map texture skipped.")
            return None
        folder = records[0].class_folder
        ids = list(records[0].texture_ids)
        copied: dict[int, int] = {}
        for army in armies:
            source_number = ids[army]
            if source_number not in copied:
                source = self.map_source(folder, source_number)
                if source is None:
                    plan.notes.append(f"ymu/{folder}tex_{source_number}.tpl not found: map texture skipped.")
                    return None
                number = self.free_number(folder)
                dest = self.new_path(self.files / "ymu" / folder.rstrip("/") / f"tex_{number}.tpl")
                plan.copies.append(TextureCopy("map", f"{label}, from tex_{source_number}", source[0], dest,
                                               pack_entry=source[1]))
                copied[source_number] = number
            ids[army] = copied[source_number]
        return tuple(ids)

    # -- battle textures ----------------------------------------------------------------
    def battle_copy(self, plan: VariantPlan, code: str, source: str, tag: str, label: str) -> str | None:
        """The name of a recoloured copy of ``zu/<code>/<source>.tpl``."""
        source_path = self.files / "zu" / code / f"{source}.tpl"
        if not source_path.is_file():
            plan.notes.append(f"zu/{code}/{source}.tpl not found: battle texture skipped.")
            return None
        name = f"{source}_{tag.lower()}"
        dest = self.new_path(self.files / "zu" / code / f"{name}.tpl")
        plan.copies.append(TextureCopy("battle", f"{label}, from {source}.tpl", source_path, dest))
        return name


def character_family(project: ModProject, pid: str) -> tuple[list[str], list[str]]:
    """``(suggested, others)``: the other records of the same character (same
    name key and portrait) to give the variant too. Suggested are the ones
    also in the same class whose PID extends this one (``PID_GATRIE_EV``);
    the rest (generic soldiers share names) are offered unticked."""
    fe8 = fe8data.read_fe8data(logical_game_path_of(project, "game_data").read_bytes())
    main = next((c for c in fe8.characters if c.pid == pid), None)
    if main is None:
        raise ProjectError(f"No character {pid!r}.")
    suggested, others = [], []
    for c in fe8.characters:
        if not c.pid or c.pid == pid or c.mpid != main.mpid or c.fid != main.fid:
            continue
        (suggested if c.pid.startswith(pid + "_") and c.jid == main.jid else others).append(c.pid)
    return suggested, others


def plan_character_variant(project: ModProject, pid: str, tag: str, *, also: tuple[str, ...] | list[str] = (),
                           battle: bool = True, map_models: bool = True, portrait: bool = True,
                           army: str = "自軍") -> VariantPlan:
    """The changes giving ``pid`` (and the records in ``also``) recoloured
    textures named after ``tag``. ``army`` is whose colours the character
    shows where no line of their own picks a texture (battle army key, map
    texture slot): the player's by default."""
    tag = _check_tag(tag)
    if army not in ARMY_KEYS:
        raise ProjectError(f"Unknown army key {army!r}.")
    ctx = _Context(project)
    main = ctx.characters.get(pid)
    if main is None:
        raise ProjectError(f"No character {pid!r}.")
    group = [pid] + [p for p in also if p != pid]
    for other in group:
        if other not in ctx.characters:
            raise ProjectError(f"No character {other!r}.")
    plan = VariantPlan(f"{tag} variant of {pid}")

    for job, promoted in ctx.tiers(main) if (battle or map_models) else []:
        tier = f"{job.jid}{' (promoted)' if promoted else ''}"
        aid = ctx.own_aid(main, promoted) or job.aid
        final_aid = aid
        aid_users, aid_classes = ctx.users_of_aid(aid) if aid else (set(), set())
        own = bool(aid) and not aid_classes and aid_users <= set(group) and all(
            ctx.own_aid(ctx.characters[p], promoted) == aid for p in group)
        if map_models and aid:
            if own:
                ids = ctx.recolour_map_numbers(plan, aid, range(4), tier)
                if ids is not None:
                    plan.map_textures.append((aid, ids))
            else:
                new_aid = f"{aid}_{tag}"
                if ctx.records_of(new_aid):
                    raise ProjectError(f"The animation ID {new_aid} already exists: pick another tag.")
                ids = ctx.recolour_map_numbers(plan, aid, range(4), tier)
                if ids is not None:
                    plan.map_clones.append((aid, new_aid, ids))
                    plan.character_aids += [(p, promoted, new_aid) for p in group]
                    final_aid = new_aid
                    if aid in ctx.models:
                        plan.job_lines.append((ctx.models[aid], new_aid))
        elif map_models:
            plan.notes.append(f"{tier}: no animation ID, map texture skipped.")

        if not battle:
            continue
        models = dict(ctx.models)
        models.update({new: code for code, new in plan.job_lines})
        code = zdbx.battle_model_for(models, job.jid, pid, final_aid)
        textures = ctx.battle_textures(code) if code else None
        if textures is None:
            plan.notes.append(f"{tier}: no battle model texture table, battle texture skipped.")
            continue
        if final_aid != aid or not (aid and aid in textures) or own:
            picked = next((textures[k] for k in (aid, pid, army) if k and textures.get(k, NULL_TEXTURE) != NULL_TEXTURE),
                          code)
        else:
            plan.notes.append(f"{tier}: zu/{code} picks the texture by {aid}, which other units share; "
                              "turn on map models so the character gets an animation ID of their own.")
            continue
        name = ctx.battle_copy(plan, code, picked, tag, tier)
        if name is None:
            continue
        plan.battle_lines += [(code, p, name) for p in group]
        if final_aid in textures:
            plan.battle_lines.append((code, final_aid, name))

    if portrait:
        _plan_portrait(ctx, plan, main, group, tag)
    if plan.empty:
        plan.notes.append("Nothing to recolour.")
    return plan


def _plan_portrait(ctx: _Context, plan: VariantPlan, main, group: list[str], tag: str) -> None:
    if not main.fid:
        plan.notes.append(f"{main.pid} has no portrait.")
        return
    faces = {r.fid: r for r in portraits.load_faces(ctx.project)}
    small = faces.get(main.fid)
    if small is None:
        plan.notes.append(f"{main.fid} is not in the face table: portrait skipped.")
        return
    name = f"{main.fid.removeprefix('FID_')}_{tag}"
    if not portraits.NAME_RE.match(name):
        plan.notes.append(f"FID_{name} is longer than 24 characters: portrait skipped.")
        return
    new_small = f"FID_{name}"
    if new_small in faces or large_face_id(new_small) in faces:
        raise ProjectError(f"{new_small} already exists: pick another tag.")
    for fid, filename in ((main.fid, f"{name}.cms"), (large_face_id(main.fid), f"L_{name}.cms")):
        record = faces.get(fid)
        if record is None:
            plan.notes.append(f"{fid} is not in the face table: that size is skipped.")
            continue
        source = portraits.face_dir(ctx.project) / record.filename
        if not source.is_file():
            plan.notes.append(f"Face/{record.filename} not found: that size is skipped.")
            continue
        dest = ctx.new_path(portraits.face_dir(ctx.project) / filename)
        plan.copies.append(TextureCopy("portrait", record.filename, source, dest, compressed=True))
        plan.faces.append((fid, f"FID_{'L_' if fid != main.fid else ''}{name}", filename))
    if any(new == new_small for _old, new, _file in plan.faces):
        plan.character_fids += [(p, new_small) for p in group if ctx.characters[p].fid == main.fid]


def plan_class_variant(project: ModProject, jid: str, army: str, tag: str, *, promoted: bool = False,
                       battle: bool = True, map_models: bool = True) -> VariantPlan:
    """The changes recolouring one army's look of a class (and of its
    promotion with ``promoted``): every unit of that army that has no
    texture line of its own changes."""
    tag = _check_tag(tag)
    if army not in ARMY_KEYS:
        raise ProjectError(f"Unknown army key {army!r}.")
    ctx = _Context(project)
    job = ctx.classes.get(jid)
    if job is None:
        raise ProjectError(f"No class {jid!r}.")
    jobs = [job]
    if promoted:
        other = ctx.classes.get(job.promotes_to)
        if other is not None and other is not job:
            jobs.append(other)
    plan = VariantPlan(f"{tag} {ARMY_NAMES[army]} colours of {jid}")
    army_index = ARMY_KEYS.index(army)
    for job in jobs:
        if map_models:
            if not job.aid:
                plan.notes.append(f"{job.jid}: no animation ID, map texture skipped.")
            else:
                _pids, classes = ctx.users_of_aid(job.aid)
                if classes - {job.jid}:
                    plan.notes.append(f"{job.aid} is also the map model of {', '.join(sorted(classes - {job.jid}))}; "
                                      "they change too.")
                ids = ctx.recolour_map_numbers(plan, job.aid, [army_index], job.jid)
                if ids is not None:
                    plan.map_textures.append((job.aid, ids))
        if not battle:
            continue
        code = ctx.models.get(job.jid)
        textures = ctx.battle_textures(code) if code else None
        if textures is None:
            plan.notes.append(f"{job.jid}: no battle model texture table, battle texture skipped.")
            continue
        # other job-list lines on the same model change too, unless a texture line of their own
        # (their animation ID or character) picks another texture
        sharing = sorted(key for key, other in ctx.models.items()
                         if other == code and key != job.jid and key.rsplit("+", 1)[-1] not in textures)
        if sharing:
            plan.notes.append(f"zu/{code} is also used by {', '.join(sharing)}; their {ARMY_NAMES[army]} "
                              "units change too.")
        source = textures.get(army, NULL_TEXTURE)
        name = ctx.battle_copy(plan, code, code if source == NULL_TEXTURE else source, tag, job.jid)
        if name is not None:
            plan.battle_lines.append((code, army, name))
    if plan.empty:
        plan.notes.append("Nothing to recolour.")
    return plan


def apply_variant(project: ModProject, plan: VariantPlan, recolour: Recolour) -> list[str]:
    """Write the recoloured copies, then the table changes. Returns the
    summary lines. The copies are written first and removed again if a
    copy fails, so a refused variant leaves no stray files."""
    if plan.empty:
        raise ProjectError("Nothing to recolour.")
    written: list[Path] = []
    try:
        for copy in plan.copies:
            if copy.dest.exists():
                raise ProjectError(f"{_short(copy.dest)} already exists: pick another tag.")
            data = recolour_tpl(copy.source_bytes(), recolour)
            copy.dest.parent.mkdir(parents=True, exist_ok=True)
            copy.dest.write_bytes(lz10.compress(data) if copy.compressed else data)
            written.append(copy.dest)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise

    for code, aid in plan.job_lines:
        model_slots.assign_battle_model(project, code, aid=aid)
    for code, key, texture in plan.battle_lines:
        model_slots.set_battle_texture(project, code, key, texture)
    for old, new, ids in plan.map_clones:
        model_slots.clone_map_model(project, old, new, None, ids)
    for aid, ids in plan.map_textures:
        model_slots.set_map_textures(project, aid, ids)
    for pid, promoted, aid in plan.character_aids:
        model_slots.assign_map_model(project, pid, aid, promoted=promoted)

    if plan.faces:
        records = portraits.load_faces(project)
        by_fid = {r.fid: r for r in records}
        records += [replace(by_fid[old], fid=new, filename=filename) for old, new, filename in plan.faces]
        portraits.save_faces(project, records)
    if plan.character_fids:
        path = logical_game_path_of(project, "game_data")
        data = path.read_bytes()
        index = {c.pid: c.index for c in fe8data.read_fe8data(data).characters if c.pid}
        for pid, fid in plan.character_fids:
            data = fe8data.patch_character_field(data, index[pid], "fid", fid)
        project.write_keeping_original(path, data)
    return plan.summary()
