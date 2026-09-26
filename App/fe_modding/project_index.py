"""Cross-references for the workspace's chapter and character pages.

The editors each read one format; this module joins them so a page can show
everything about one chapter or one character:

* **characters** - every ``FE8Data.bin`` character record with its English
  name (``MPID_`` key in ``common.m``), class names (``MJID_``), portrait file
  (``FID_`` -> ``face/facedata.bin``), battle model (``zdbx`` job list, the
  engine's AID -> JID+PID -> JID order) and map model folder
  (``FE8Anim.bin``), grouped by name key so story copies (``PID_BOLE_MAP1``)
  sit under their main record;
* **deployments** - every unit of every ``zmap/bmapNN*/dispos.cmp``
  difficulty file, by PID;
* **dialogue** - every chapter message that loads a portrait (``$FC``/``$FCL_``)
  or names a speaker (``$cN``) belonging to a character;
* **scripts** - every chapter script function that pushes a ``PID_``/``MPID_``
  string (read lazily: decoding every script is the slow part).

Nothing here writes. Path of Radiance only for now: :func:`supported` says
whether the project's game is covered.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import chapters
from .formats import anim_registry, dispo, fe8data, lz10, message, pak, zdbx
from .formats.fe9_portraits import read_face_table
from .games import Game
from .project import ModProject

PLAYABLE, NAMED, GENERIC = "playable", "named", "generic"
CATEGORY_LABELS = {PLAYABLE: "Playable", NAMED: "Named NPCs & bosses", GENERIC: "Generic"}

# Normal/Hard/Maniac are presumed from the letters; the 4th file (c) is not identified yet.
_DIFFICULTY_NAMES = {"n": "Normal", "h": "Hard", "m": "Maniac", "c": "c (unidentified)"}
_PORTRAIT_CODE_RE = re.compile(r"\$FC(?:L_)?([^|$]*)\|")
_SPEAKER_CODE_RE = re.compile(r"\$c[0-9]([^|$]*)\|")
_TRAILING_DIGITS_RE = re.compile(r"\d+$")


def supported(project: ModProject) -> bool:
    return project.game == Game.PATH_OF_RADIANCE


def difficulty_name(code: str) -> str:
    return _DIFFICULTY_NAMES.get(code, code)


@dataclass(frozen=True)
class CharacterInfo:
    index: int
    pid: str
    mpid: Optional[str]
    name: str
    fid: Optional[str]
    jid: Optional[str]
    class_name: str
    promoted_jid: Optional[str]
    promoted_class_name: str
    aid_unpromoted: Optional[str]
    aid_promoted: Optional[str]
    portrait_file: Optional[str]
    battle_model: Optional[str]  # zu/<code>
    promoted_battle_model: Optional[str]
    map_model: Optional[str]  # ymu/<folder>
    promoted_map_model: Optional[str]
    category: str
    main_pid: str  # the first record with the same name key (itself when it is the main one)
    variants: tuple[str, ...] = ()  # the other records sharing the name key (main record only)

    @property
    def label(self) -> str:
        return f"{self.name} ({self.pid})" if self.name else self.pid


@dataclass(frozen=True)
class Deployment:
    chapter_id: Optional[str]
    folder: str  # zmap folder, e.g. bmap06_2
    difficulty: str  # n/h/m/c
    section: str
    unit_index: int
    pid: str
    jid: str
    x: int
    y: int


@dataclass(frozen=True)
class MessageRef:
    chapter_id: str
    message_id: str
    how: str  # "portrait" or "speaker"


@dataclass(frozen=True)
class ScriptRef:
    chapter_id: str
    function: str
    label: str  # the PID_/MPID_ string the function pushes


@dataclass(frozen=True)
class ChapterInfo:
    id: str
    title: str
    phases: tuple[str, ...]
    message_count: int
    units_by_difficulty: dict = field(default_factory=dict, hash=False)
    has_script: bool = False
    has_map: bool = False
    has_deployment: bool = False


class ProjectIndex:
    """Built once (:meth:`build`, slow: run it off the UI thread) and then
    queried. :meth:`invalidate` marks it stale after a save; the next
    :meth:`build` re-reads everything."""

    def __init__(self, project: ModProject):
        self.project = project
        self.files = project.extracted_dir / "files"
        self._lock = threading.Lock()
        self.ready = False
        self.error: Optional[str] = None
        self.characters: list[CharacterInfo] = []
        self.by_pid: dict[str, CharacterInfo] = {}
        self.chapters: list[ChapterInfo] = []
        self.by_chapter: dict[str, ChapterInfo] = {}
        self.titles: dict[str, str] = {}
        self.class_names: dict[str, str] = {}  # JID -> English name
        self.item_names: dict[str, str] = {}  # IID -> English name
        self.texts: dict[str, str] = {}
        self.deployments: list[Deployment] = []
        self.message_refs: dict[str, list[MessageRef]] = {}  # pid -> refs
        self.messages_by_chapter: dict[str, list[tuple[str, str]]] = {}  # id -> [(message id, text)]
        self._script_refs: Optional[dict[str, list[ScriptRef]]] = None
        self._script_functions: dict[str, list[tuple[str, int]]] = {}

    # -- building -------------------------------------------------------------
    def build(self) -> None:
        try:
            self._build()
            self.error = None
        except Exception as exc:  # noqa: BLE001 - shown on the pages, never fatal
            self.error = f"{type(exc).__name__}: {exc}"
        self.ready = True

    def invalidate(self) -> None:
        self.ready = False
        self._script_refs = None

    def _build(self) -> None:
        self.titles = chapters.chapter_titles(self.project)
        self.texts = self._read_texts()
        self.deployments = self._read_deployments()
        self._build_messages()
        self._build_chapters()
        if supported(self.project):
            self._build_characters()
            self._build_message_refs()
        self._script_refs = None

    def _read_texts(self) -> dict[str, str]:
        system_cmp = self.files / "system.cmp"
        try:
            return fe8data.read_message_texts(system_cmp) if system_cmp.exists() else {}
        except Exception:  # noqa: BLE001
            return {}

    def text(self, key: Optional[str]) -> str:
        return (self.texts.get(key) or "").strip() if key else ""

    def _read_deployments(self) -> list[Deployment]:
        out = []
        zmap = self.files / "zmap"
        for path in sorted(zmap.glob("*/dispos.cmp")) if zmap.is_dir() else []:
            folder = path.parent.name
            try:
                decompressed = lz10.decompress(path.read_bytes())
                entries = pak.read_pak_entries(decompressed)
            except Exception:  # noqa: BLE001 - one bad file must not hide the rest
                continue
            for entry in entries:
                match = re.fullmatch(r"dispos_(\w)\.bin", entry.name)
                if not match:
                    continue
                try:
                    sections = dispo.read_dispo_bytes(pak.read_pak_file_content(decompressed, entry))
                except Exception:  # noqa: BLE001
                    continue
                for section in sections:
                    for ui, unit in enumerate(section.units):
                        f = unit.fields
                        out.append(Deployment(
                            chapter_id=chapters.chapter_of_map_folder(folder), folder=folder,
                            difficulty=match.group(1), section=section.name, unit_index=ui,
                            pid=f[0].display, jid=f[1].display,
                            x=f[32].value if len(f) > 32 else -1, y=f[33].value if len(f) > 33 else -1,
                        ))
        return out

    def _build_messages(self) -> None:
        self.messages_by_chapter = {}
        for chapter_id in chapters.list_chapter_ids(self.project):
            path = self.files / "Mess" / f"c{chapter_id.zfill(2)}.m"
            try:
                self.messages_by_chapter[chapter_id] = [(m.speaker, m.text) for m in message.read_messages_path(path)]
            except Exception:  # noqa: BLE001
                self.messages_by_chapter[chapter_id] = []

    def _build_chapters(self) -> None:
        self.chapters = []
        for chapter_id in chapters.list_chapter_ids(self.project):
            paths = chapters.chapter_paths(self.project, chapter_id)
            phases = tuple(chapters.chapter_phases(self.project, chapter_id))
            units: dict[str, int] = {}
            first = phases[0] if phases else None
            for d in self.deployments:
                if d.folder == first:
                    units[d.difficulty] = units.get(d.difficulty, 0) + 1
            self.chapters.append(ChapterInfo(
                id=chapter_id,
                title=chapters.chapter_display_title(chapter_id, self.titles),
                phases=phases,
                message_count=len(self.messages_by_chapter.get(chapter_id, [])),
                units_by_difficulty=units,
                has_script=paths.script is not None,
                has_map=paths.map is not None,
                has_deployment=paths.deployment is not None,
            ))
        self.by_chapter = {c.id: c for c in self.chapters}

    def _build_characters(self) -> None:
        data = (self.files / "FE8Data.bin").read_bytes()
        fe8 = fe8data.read_fe8data(data)
        classes = {c.jid: c for c in fe8.classes if c.jid}
        self.class_names = {jid: self.text(c.mjid) for jid, c in classes.items()}
        self.item_names = {it.iid: self.text(it.miid) for it in fe8.items if it.iid}
        faces = self._read_faces()
        battle_models = self._read_battle_models()
        map_folders = self._read_map_folders()

        def class_name(jid: Optional[str]) -> str:
            entry = classes.get(jid)
            return self.text(entry.mjid) if entry else ""

        def promoted(jid: Optional[str]) -> Optional[str]:
            entry = classes.get(jid)
            return entry.promotes_to if entry and entry.promotes_to != jid else None

        # tutorial records borrow real portraits (the tutorial heron uses Reyson's), and some
        # characters have two MPIDs with the same displayed name (MPID_DARKKNIGHT/MPID_BLACKKNIGHT),
        # so a portrait counts as shared only across distinct, non-empty displayed names outside the
        # tutorial
        def is_tutorial(mpid: Optional[str]) -> bool:
            return (mpid or "").startswith("MPID_TUT_")

        fid_names: dict[str, set] = {}
        for c in fe8.characters:
            name = self.text(c.mpid)
            if c.fid and name and not is_tutorial(c.mpid):
                fid_names.setdefault(c.fid, set()).add(name)

        first_by_mpid: dict[str, str] = {}
        records = []
        for c in fe8.characters:
            if not c.pid:
                continue
            key = c.mpid or c.pid
            main = first_by_mpid.setdefault(key, c.pid)
            if (c.fid is None or len(fid_names.get(c.fid, ())) > 1 or (c.mpid or "").endswith("DUMMY")
                    or is_tutorial(c.mpid)):
                category = GENERIC
            # 0x49-0x50 are the fixed-mode level-up accumulators (fe8data.CharacterEntry.fixed_growth_start);
            # only units that level up on the player side have them
            # non-zero, while bosses also have growth rates
            elif sum(c.fixed_growth_start) > 0:
                category = PLAYABLE
            else:
                category = NAMED
            pro = promoted(c.jid)
            face = faces.get(c.fid) if c.fid else None
            records.append(dict(
                index=c.index, pid=c.pid, mpid=c.mpid, name=self.text(c.mpid), fid=c.fid, jid=c.jid,
                class_name=class_name(c.jid), promoted_jid=pro, promoted_class_name=class_name(pro),
                aid_unpromoted=c.aid_unpromoted, aid_promoted=c.aid_promoted,
                portrait_file=face.filename if face else None,
                battle_model=_zu(zdbx.battle_model_for(battle_models, c.jid, c.pid, c.aid_unpromoted) if c.jid else None),
                promoted_battle_model=_zu(zdbx.battle_model_for(battle_models, pro, c.pid, c.aid_promoted) if pro else None),
                map_model=_ymu(map_folders.get(c.aid_unpromoted or (classes[c.jid].aid if c.jid in classes else None))),
                promoted_map_model=_ymu(map_folders.get(c.aid_promoted or (classes[pro].aid if pro in classes else None))),
                category=category, main_pid=main,
            ))
        variants: dict[str, list[str]] = {}
        for r in records:
            if r["main_pid"] != r["pid"]:
                variants.setdefault(r["main_pid"], []).append(r["pid"])
        self.characters = [CharacterInfo(**r, variants=tuple(variants.get(r["pid"], ()))) for r in records]
        self.by_pid = {c.pid: c for c in self.characters}

    def _read_faces(self) -> dict:
        try:
            packed = lz10.decompress((self.files / "system.cmp").read_bytes())
            for entry in pak.read_pak_entries(packed):
                if entry.name.replace("\\", "/").casefold() == "face/facedata.bin":
                    return read_face_table(pak.read_pak_file_content(packed, entry))
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _read_battle_models(self) -> dict[str, str]:
        try:
            tables = dict(zdbx.read_zdbx_files((self.files / "zdbx.cmp").read_bytes()))
            return zdbx.job_list_models(tables[zdbx.JOB_LIST].decode("shift_jis"))
        except Exception:  # noqa: BLE001
            return {}

    def _read_map_folders(self) -> dict[str, str]:
        """Base AID -> ymu folder name."""
        try:
            records = anim_registry.read_anim_registry_path(self.files / "FE8Anim.bin")
        except Exception:  # noqa: BLE001
            return {}
        return {r.base_aid: r.class_folder.rstrip("/") for r in records}

    def _build_message_refs(self) -> None:
        by_face: dict[str, list[str]] = {}
        by_speaker: dict[str, list[str]] = {}
        for c in self.characters:
            if c.fid:
                by_face.setdefault(c.fid, []).append(c.pid)
            by_speaker.setdefault(c.pid.removeprefix("PID_"), []).append(c.pid)
        refs: dict[str, list[MessageRef]] = {}
        for chapter_id, messages in self.messages_by_chapter.items():
            for msg_id, text in messages:
                hits: dict[str, str] = {}
                for name in _PORTRAIT_CODE_RE.findall(text):
                    fid = "FID_" + name
                    for pid in by_face.get(fid) or by_face.get(_TRAILING_DIGITS_RE.sub("", fid)) or ():
                        hits.setdefault(pid, "portrait")
                for name in _SPEAKER_CODE_RE.findall(text):
                    for pid in by_speaker.get(name, ()):
                        hits.setdefault(pid, "speaker")
                for pid, how in hits.items():
                    refs.setdefault(pid, []).append(MessageRef(chapter_id, msg_id, how))
        self.message_refs = refs

    # -- queries --------------------------------------------------------------
    def main_characters(self, category: Optional[str] = None) -> list[CharacterInfo]:
        return [c for c in self.characters
                if c.main_pid == c.pid and (category is None or c.category == category)]

    def family(self, pid: str) -> list[CharacterInfo]:
        """The record and every other record sharing its name key."""
        info = self.by_pid.get(pid)
        if info is None:
            return []
        main = self.by_pid.get(info.main_pid, info)
        return [main] + [self.by_pid[p] for p in main.variants if p in self.by_pid]

    def deployments_of(self, pids) -> list[Deployment]:
        wanted = set(pids)
        return [d for d in self.deployments if d.pid in wanted]

    def cast(self, folder: str, difficulty: str) -> list[Deployment]:
        return [d for d in self.deployments if d.folder == folder and d.difficulty == difficulty]

    def messages_of(self, pids) -> list[MessageRef]:
        out = []
        for pid in pids:
            out.extend(self.message_refs.get(pid, ()))
        return sorted(set(out), key=lambda r: (int(r.chapter_id), r.message_id))

    def script_refs_of(self, pids) -> list[ScriptRef]:
        """Scripts pushing one of these PIDs or their name keys (MPID_)."""
        refs = self._ensure_script_refs()
        labels = set(pids) | {self.by_pid[p].mpid for p in pids if p in self.by_pid and self.by_pid[p].mpid}
        out = []
        for label in labels:
            out.extend(refs.get(label, ()))
        return sorted(set(out), key=lambda r: (int(r.chapter_id), r.function))

    def script_functions(self, chapter_id: str) -> list[tuple[str, int]]:
        """``(function name, trigger type)`` of a chapter script, named as the
        decompiler names them."""
        self._ensure_script_refs()
        return self._script_functions.get(chapter_id, [])

    def _ensure_script_refs(self) -> dict[str, list[ScriptRef]]:
        with self._lock:
            if self._script_refs is None:
                self._script_refs = self._read_script_refs()
            return self._script_refs

    def _read_script_refs(self) -> dict[str, list[ScriptRef]]:
        from .formats.cmb.binary import read_cmb_path
        from .formats.cmb.decompiler import _Names

        refs: dict[str, list[ScriptRef]] = {}
        self._script_functions = {}
        for chapter_id in chapters.list_chapter_ids(self.project):
            path = self.files / "Scripts" / f"C{chapter_id.zfill(2)}.cmb"
            if not path.exists():
                continue
            try:
                script = read_cmb_path(path)
                names = _Names(script).defs
            except Exception:  # noqa: BLE001
                continue
            self._script_functions[chapter_id] = [(names[i], fn.type) for i, fn in enumerate(script.functions)]
            for i, fn in enumerate(script.functions):
                for instr in fn.code:
                    for operand in getattr(instr, "operands", ()):
                        if isinstance(operand, str) and operand.startswith(("PID_", "MPID_")):
                            refs.setdefault(operand, []).append(ScriptRef(chapter_id, names[i], operand))
        return refs


def _zu(code: Optional[str]) -> Optional[str]:
    return f"zu/{code}" if code else None


def _ymu(folder: Optional[str]) -> Optional[str]:
    return f"ymu/{folder}" if folder else None
