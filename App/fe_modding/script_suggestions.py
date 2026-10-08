"""Context-aware suggestions for the Script editor's completion popup.

Two things decide what the popup offers while typing ``.fe9s`` source:

- **The argument the cursor is in.** ``MoviePlay(`` offers the project's
  videos, ``UnitGetByPID(`` its characters, ``Dispos(`` the deployment groups
  of the chapter's maps, ``BGMPlay(0, `` the music cues, ``SFXPlay(`` the
  ``gcfesnd.bin`` sound effects, ``RectBuild(`` the ``RID_`` resources of
  ``s/rect.bin`` and ``window/RectDesc.bin``... The kind of each
  argument comes from the extern catalogue (``pid``, ``iid``, ``mess``...)
  refined by :data:`ARG_KINDS` for the many arguments the catalogue only
  knows as ``str`` (names taken from ``docs/app/script-call-reference.md``).
- **A well-known prefix.** Typing ``PID_``, ``IID_``, ``JID_``, ``SID_``,
  ``BGM_``, ``SFX_``, ``RID_``, ``bmap`` or ``Movie/`` anywhere offers the matching
  values too.

Everything else falls back to function-name completion. Values are read
from the project's extracted files on first use and cached until
:meth:`ScriptSuggestions.invalidate`; any list that can't be read is simply
empty - suggestions are a convenience, never a reason to fail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import chapters
from .game_profile import profile_of
from .project import ModProject


@dataclass(frozen=True)
class Suggestion:
    """One value: ``text`` is what goes in the source (without quotes)."""

    text: str
    detail: str = ""


@dataclass(frozen=True)
class Completion:
    """One popup entry: insert ``text`` in place of the ``replace`` characters
    before the cursor."""

    text: str
    label: str
    replace: int


@dataclass(frozen=True)
class ArgContext:
    """The call argument the cursor is in (on the current line)."""

    function: str
    index: int
    in_string: bool
    partial: str  # what's typed of the argument so far (inside the quotes when in_string)


KIND_TITLES = {
    "pid": "character",
    "iid": "item",
    "jid": "class",
    "skill": "skill",
    "mess": "message",
    "bgm": "music cue",
    "sfx": "sound effect",
    "movie": "video",
    "map": "map",
    "group": "deployment group",
    "flag": "flag",
    "rect": "rectangle",
    "chapter": "chapter",
}
UNQUOTED_KINDS = {"chapter"}

# Arguments the extern catalogue types as plain str/int, by (function, index).
_GROUP_FUNCTIONS = (
    "Dispos", "DisposAsynchronous", "DisposAuxiliary", "DisposContinue", "DisposFirst", "DisposGetGroupCenter",
    "DisposWarp", "InstantDispos", "InstantDisposContinue", "InstantDisposFirst", "InstantDisposRank", "Join",
    "SallyAddByGroup", "SallySetByGroup", "SelectAuxiliary", "Dispos_ForEventTiamat",
)
_GROUP_TRIPLES = (
    "DisposSetMode", "DisposContinueSetMode", "DisposFirstSetMode", "InstantDisposSetMode",
    "InstantDisposContinueSetMode", "InstantDisposFirstSetMode",
)
ARG_KINDS: dict[str, dict[int, str]] = {
    "MoviePlay": {0: "movie"},
    "ChapterMoviePlay": {0: "chapter"},
    "MapLoad": {0: "map"},
    "SFXPlay": {0: "sfx"},
    "UnitAddSkill": {1: "skill"},
    "UnitClrSkill": {1: "skill"},
    "UnitTstSkill": {1: "skill"},
    "LocalDieTalkWithBgmChange": {0: "flag", 1: "mess"},
    "Dispos_ForEvent": {2: "group", 3: "group"},
    "Dispos_ForEventSenerio": {0: "group", 1: "group"},
    "PIDisAlive": {0: "pid"},
    "UnitCheckLinked_BreakupByPID": {0: "pid"},
    "_gi": {1: "iid"},
    **{name: {0: "flag"} for name in ("set", "clr", "get", "global", "regist")},
    **{name: {0: "mess"} for name in (
        "Dialog", "DialogDirect", "DialogTutorial", "TalkEventDirect", "_tt", "td", "TutShowKari")},
    **{name: {0: "group"} for name in _GROUP_FUNCTIONS},
    **{name: {0: "group", 1: "group", 2: "group"} for name in _GROUP_TRIPLES},
}
# Functions whose first argument is an RID_ rectangle name (RectSet, RectFadeIn...).
_RECT_FUNCTION = re.compile(r"^Rect[A-Z]")

PREFIX_KINDS = (
    ("PID_", "pid"), ("IID_", "iid"), ("JID_", "jid"), ("SID_", "skill"), ("BGM_", "bgm"),
    ("SFX_", "sfx"), ("RID_", "rect"), ("bmap", "map"), ("Movie/", "movie"),
)
_POOL_PREFIXES = {
    "pid": ("PID_",), "iid": ("IID_",), "jid": ("JID_",), "skill": ("SID_",), "bgm": ("BGM_",),
    "sfx": ("SFX_", "SE_"), "rect": ("RID_",), "movie": ("Movie/",), "map": ("bmap",), "mess": ("MS",),
}

_IDENT = re.compile(r"[A-Za-z_]\w*$")
_STRING_PARTIAL = re.compile(r"[^\s\"(),]*$")
_CHAPTER_SCRIPT = re.compile(r"^C(\d+)\.cmb$", re.IGNORECASE)
_NAME_FIELDS = {"character": ("pid", "mpid"), "item": ("iid", "miid"), "class": ("jid", "mjid"),
                "skill": ("sid", "msid")}
MAX_ITEMS = 60
_SILENT_SFX_ID = 0x158


def chapter_of_script(path: Optional[Path], project: Optional[ModProject] = None) -> Optional[str]:
    """``C06.cmb`` -> ``"06"`` (``C0407a.cmb`` -> ``"0407a"`` with a Radiant Dawn ``project``);
    None for shared scripts."""
    if path is None:
        return None
    if project is not None and profile_of(project).chapter_id_width != 2:
        match = re.match(rf"^C({profile_of(project).chapter_id_pattern})\.cmb$", path.name, re.IGNORECASE)
        return match.group(1).lower() if match else None
    match = _CHAPTER_SCRIPT.match(path.name)
    return match.group(1).zfill(2) if match else None


def arg_context(before: str) -> Optional[ArgContext]:
    """The innermost call argument open at the end of ``before`` (the current
    line up to the cursor), or None outside any call or in a comment."""
    stack: list[list] = []  # [function, index]
    in_string = False
    string_start = 0
    i = 0
    while i < len(before):
        ch = before[i]
        if in_string:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string, string_start = True, i + 1
        elif ch == "#":
            return None
        elif ch == "(":
            m = _IDENT.search(before[:i].rstrip())
            stack.append([m.group() if m else "", 0])
        elif ch == ")":
            if stack:
                stack.pop()
        elif ch == "," and stack:
            stack[-1][1] += 1
        i += 1
    if not stack or not stack[-1][0]:
        return None
    function, index = stack[-1]
    if in_string:
        return ArgContext(function, index, True, before[string_start:])
    m = _IDENT.search(before) or re.search(r"\d+$", before)
    return ArgContext(function, index, False, m.group() if m else "")


def resolve_kind(function: str, index: int, externs: dict) -> Optional[str]:
    """What an argument names (a key of :data:`KIND_TITLES`), if known."""
    kind = ARG_KINDS.get(function, {}).get(index)
    if kind:
        return kind
    if index == 0 and _RECT_FUNCTION.match(function):
        return "rect"
    sig = externs.get(function)
    if sig is not None:
        kind = sig.arg_kind(index)
        if kind in KIND_TITLES:
            return kind
    return None


def prefix_kind(word: str) -> Optional[str]:
    """The kind a value starting like ``word`` belongs to (``PID_...``)."""
    return next((kind for prefix, kind in PREFIX_KINDS if word.startswith(prefix)), None)


def rank(values: Iterable[Suggestion], typed: str) -> list[Suggestion]:
    """Values starting with ``typed`` first, then ones containing it (in the
    value or its description), both case-insensitively."""
    low = typed.lower()
    starts, contains = [], []
    for s in values:
        text = s.text.lower()
        if text.startswith(low):
            starts.append(s)
        elif low and (low in text or low in s.detail.lower()):
            contains.append(s)
    return starts + contains


def label(s: Suggestion, width: int = 26) -> str:
    return f"{s.text:<{width}} {s.detail}" if s.detail else s.text


class ScriptSuggestions:
    """Per-project value lists, loaded lazily and cached."""

    def __init__(self, project: ModProject):
        self._project = project
        self._cache: dict = {}

    @property
    def files(self) -> Path:
        return self._project.extracted_dir / "files"

    def invalidate(self) -> None:
        self._cache.clear()

    # -- public -------------------------------------------------------------
    def values(self, kind: str, *, chapter_id: Optional[str] = None, pool: Iterable[str] = (),
               source: str = "") -> list[Suggestion]:
        """Every known value of ``kind`` for a script of ``chapter_id`` (None for
        a shared script), plus matching strings already in the script's pool."""
        if kind == "flag":
            values = self._flags(source)
        else:
            key = (kind, chapter_id)
            if key not in self._cache:
                try:
                    self._cache[key] = self._load(kind, chapter_id)
                except Exception:  # noqa: BLE001 - suggestions are optional
                    self._cache[key] = []
            values = self._cache[key]
        seen = {s.text for s in values}
        prefixes = _POOL_PREFIXES.get(kind, ())
        extra = [Suggestion(s, "used in this script") for s in pool
                 if s and s not in seen and any(s.startswith(p) for p in prefixes)]
        return values + sorted(extra, key=lambda s: s.text)

    def completions(self, before: str, after: str, *, force: bool, externs: dict,
                    identifiers: Callable[[str], list[str]], chapter_id: Optional[str] = None,
                    pool: Iterable[str] = (), source: str = "") -> list[Completion]:
        """The popup's entries for the cursor between ``before`` and ``after``
        (the current line split at the cursor)."""
        pool = list(pool)
        ctx = arg_context(before)
        word_match = _IDENT.search(before)
        word = word_match.group() if word_match else ""

        if ctx is not None and ctx.in_string:
            partial = _STRING_PARTIAL.search(ctx.partial).group()
            kind = resolve_kind(ctx.function, ctx.index, externs) or prefix_kind(partial)
            if kind is None:
                return []
            closing = "" if after.startswith('"') else '"'
            return [Completion(s.text + closing, label(s), len(partial))
                    for s in rank(self.values(kind, chapter_id=chapter_id, pool=pool, source=source),
                                  partial)[:MAX_ITEMS]]

        if _in_string_or_comment(before):
            return []

        kind = resolve_kind(ctx.function, ctx.index, externs) if ctx is not None else None
        typed = ctx.partial if ctx is not None else word
        if kind is None and word:
            kind = prefix_kind(word)
            typed = word
        if kind is not None and (typed or force or before.rstrip().endswith(("(", ","))):
            found = rank(self.values(kind, chapter_id=chapter_id, pool=pool, source=source), typed)
            if found:
                quote = "" if kind in UNQUOTED_KINDS else '"'
                return [Completion(f"{quote}{s.text}{quote}", label(s), len(typed)) for s in found[:MAX_ITEMS]]

        if len(word) < (1 if force else 2):
            return []
        names = identifiers(word)
        if not names or (len(names) == 1 and names[0] == word):
            return []
        return [Completion(n, n, len(word)) for n in names[:40]]

    # -- loaders ------------------------------------------------------------
    def _load(self, kind: str, chapter_id: Optional[str]) -> list[Suggestion]:
        loader = {
            "pid": self._characters, "iid": self._items, "jid": self._classes, "skill": self._skills,
            "bgm": self._bgm, "sfx": self._sfx, "rect": self._rects,
            "movie": self._movies, "map": self._maps, "chapter": self._chapters,
            "group": lambda: self._groups(chapter_id), "mess": lambda: self._messages(chapter_id),
        }.get(kind)
        return loader() if loader else []

    def _fe8(self):
        if "fe8" not in self._cache:
            from .formats import fe8data
            try:
                self._cache["fe8"] = fe8data.read_fe8data_path(profile_of(self._project).path(self.files, "game_data"))
            except Exception:  # noqa: BLE001
                self._cache["fe8"] = None
        return self._cache["fe8"]

    def _texts(self) -> dict:
        if "texts" not in self._cache:
            from .formats import fe8data
            try:
                self._cache["texts"] = fe8data.read_message_texts(profile_of(self._project).path(self.files, "system_archive"))
            except Exception:  # noqa: BLE001
                self._cache["texts"] = {}
        return self._cache["texts"]

    def _fe10_tables(self):
        """(FE10Data, names) for a game whose database is FE10Data.cms (Radiant Dawn), else None."""
        if "fe10" not in self._cache:
            self._cache["fe10"] = None
            if profile_of(self._project).script_dialect == "fe10":
                from .formats import fe10data
                try:
                    data = fe10data.read_fe10data(self._project.read_logical("game_data"))
                    self._cache["fe10"] = (data, fe10data.message_names(self.files / "Mess"))
                except Exception:  # noqa: BLE001
                    pass
        return self._cache["fe10"]

    def _fe10_named(self, kind: str) -> list[Suggestion]:
        data, names = self._fe10_tables()
        id_key, name_key = _NAME_FIELDS[kind]
        out, seen = [], set()
        for record in data.table(kind):
            value = record.values.get(id_key)
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(Suggestion(value, " ".join(names.get(record.values.get(name_key) or "", "").split())))
        return out

    def _named(self, entries, id_attr: str, name_attr: str) -> list[Suggestion]:
        texts = self._texts()
        out, seen = [], set()
        for entry in entries:
            value = getattr(entry, id_attr)
            if not value or value in seen:
                continue
            seen.add(value)
            name = (texts.get(getattr(entry, name_attr) or "") or "").strip()
            out.append(Suggestion(value, " ".join(name.split())))
        return out

    def _characters(self) -> list[Suggestion]:
        if self._fe10_tables():
            return self._fe10_named("character")
        fe8 = self._fe8()
        return self._named(fe8.characters, "pid", "mpid") if fe8 else []

    def _items(self) -> list[Suggestion]:
        if self._fe10_tables():
            return self._fe10_named("item")
        fe8 = self._fe8()
        return self._named(fe8.items, "iid", "miid") if fe8 else []

    def _classes(self) -> list[Suggestion]:
        if self._fe10_tables():
            return self._fe10_named("class")
        fe8 = self._fe8()
        return self._named(fe8.classes, "jid", "mjid") if fe8 else []

    def _skills(self) -> list[Suggestion]:
        if self._fe10_tables():
            return self._fe10_named("skill")
        fe8 = self._fe8()
        return self._named(fe8.skills, "sid", "msid") if fe8 else []

    def _bgm(self) -> list[Suggestion]:
        from .formats import gcfesnd
        cues = gcfesnd.read_bgm_cues_path(self.files / "Sound" / "gcfesnd.bin")
        return [Suggestion(c.name, "(no file)" if c.is_dummy else c.path.rsplit("/", 1)[-1]) for c in cues]

    def _sfx(self) -> list[Suggestion]:
        """``SFX_*`` cue names of ``gcfesnd.bin`` (sound id 0x158 is the silent dummy)."""
        from .formats import gcfesnd
        out, seen = [], set()
        for cue in gcfesnd.read_sfx_cues_path(self.files / "Sound" / "gcfesnd.bin"):
            if cue.name in seen:
                continue
            seen.add(cue.name)
            silent = " · silent" if cue.sound_id == _SILENT_SFX_ID else ""
            out.append(Suggestion(cue.name, f"{cue.group.lower()} · sound {cue.sound_id:#x}{silent}"))
        return out

    def _rects(self) -> list[Suggestion]:
        """``RID_*`` resources: backgrounds/illustrations of ``s/rect.bin`` and
        window layouts of ``window/RectDesc.bin``."""
        from .formats import rect
        from .formats.fe9_conversation_assets import read_rect_resources
        out, seen = [], set()
        try:
            for resource in rect.read_rect_file(self.files / "s" / "rect.bin").resources:
                if resource.name not in seen:
                    seen.add(resource.name)
                    width, height = resource.size
                    out.append(Suggestion(resource.name, f"image {width}×{height}" if width else "image"))
        except Exception:  # noqa: BLE001 - keep whatever the other file offers
            pass
        desc = next((p for p in (self.files / "window" / "RectDesc.bin", self.files / "window" / "rectdesc.bin")
                     if p.is_file()), None)
        if desc is not None:
            try:
                names = read_rect_resources(desc.read_bytes())
            except Exception:  # noqa: BLE001
                names = {}
            for name in names:
                if name not in seen:
                    seen.add(name)
                    out.append(Suggestion(name, "window layout"))
        return out

    def _movies(self) -> list[Suggestion]:
        movie_dir = self.files / "Movie"
        if not movie_dir.is_dir():
            return []
        out = []
        for path in sorted(movie_dir.glob("*.thp"), key=lambda p: p.name.lower()):
            out.append(Suggestion(f"Movie/{path.name}", f"{path.stat().st_size / 1_048_576:.1f} MB"))
        return out

    def _chapter_titles(self) -> dict:
        if "titles" not in self._cache:
            try:
                self._cache["titles"] = chapters.chapter_titles(self._project)
            except Exception:  # noqa: BLE001
                self._cache["titles"] = {}
        return self._cache["titles"]

    def _chapter_title(self, chapter_id: Optional[str]) -> str:
        if chapter_id is None:
            return ""
        try:
            return chapters.chapter_display_title(chapter_id, self._chapter_titles())
        except Exception:  # noqa: BLE001
            return ""

    def _maps(self) -> list[Suggestion]:
        zmap = self.files / "zmap"
        if not zmap.is_dir():
            return []
        out = []
        for folder in sorted((p for p in zmap.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
            out.append(Suggestion(folder.name, self._chapter_title(chapters.chapter_of_map_folder(folder.name))))
        return out

    def _chapters(self) -> list[Suggestion]:
        numeric = profile_of(self._project).chapter_id_width == 2  # Path of Radiance scripts pass chapter numbers
        return [Suggestion(str(int(cid)) if numeric and cid.isdigit() else cid, self._chapter_title(cid))
                for cid in chapters.list_chapter_ids(self._project)]

    def _groups(self, chapter_id: Optional[str]) -> list[Suggestion]:
        """Deployment groups (``dispos.cmp`` section names) of the chapter's
        maps, or of every map for a shared script."""
        from .formats import dispo, lz10, pak
        if chapter_id is not None:
            folders = chapters.chapter_phases(self._project, chapter_id)
        else:
            zmap = self.files / "zmap"
            folders = sorted(p.name for p in zmap.iterdir() if p.is_dir()) if zmap.is_dir() else []
        units: dict[str, int] = {}
        where: dict[str, list[str]] = {}
        for folder in folders:
            path = profile_of(self._project).deployment_path(self.files, folder)
            if not path.exists():
                continue
            try:
                decompressed = lz10.decompress(path.read_bytes())
                entries = pak.read_pak_entries(decompressed)
            except Exception:  # noqa: BLE001
                continue
            for entry in entries:
                if not re.fullmatch(r"dispos_\w\.bin", entry.name):
                    continue
                try:
                    sections = dispo.read_dispo_bytes(pak.read_pak_file_content(decompressed, entry))
                except Exception:  # noqa: BLE001
                    continue
                for section in sections:
                    units[section.name] = max(units.get(section.name, 0), len(section.units))
                    if folder not in where.setdefault(section.name, []):
                        where[section.name].append(folder)
        return [Suggestion(name, f"{', '.join(where[name])} · {units[name]} unit(s)")
                for name in sorted(units, key=str.lower)]

    def _messages(self, chapter_id: Optional[str]) -> list[Suggestion]:
        """Message IDs of the chapter's ``Mess/cNN.m``."""
        if chapter_id is None:
            return []
        from .formats import message
        profile = profile_of(self._project)
        path = profile.mess_path(self.files, chapter_id)
        if profile.message_dialect == "fe10":
            from .formats import fe10_message, fe10data
            english = path.with_name("e_" + path.name)  # same keys, English text
            path = english if english.exists() else path
            key_of, text_of = fe10data.message_key, fe10_message.plain_text
        else:
            from .formats.fe9_message_scene import to_display
            key_of, text_of = to_display, lambda text: re.sub(r"[\x00-\x1f]|<[^>]*>", " ", text)
        if not path.exists():
            return []
        out = []
        for msg in message.read_messages_path(path):
            try:
                key = key_of(msg.speaker)
            except UnicodeError:
                key = msg.speaker
            try:
                preview = " ".join(text_of(msg.text).split())[:50]
            except Exception:  # noqa: BLE001 - a preview is a convenience
                preview = ""
            out.append(Suggestion(key, preview))
        return out

    def _flags(self, source: str) -> list[Suggestion]:
        """Campaign flags (``startup.cmb``) and the flags this script registers."""
        out = []
        try:
            from .script_sources import CompileContext
            out += [Suggestion(name, "campaign flag") for name in CompileContext.for_project(self._project).global_flags or []]
        except Exception:  # noqa: BLE001
            pass
        key = ("local_flags", hash(source))
        if key not in self._cache:
            self._cache = {k: v for k, v in self._cache.items() if not (isinstance(k, tuple) and k[0] == "local_flags")}
            try:
                from .formats import event_flags
                from .formats.cmb.parser import parse
                self._cache[key] = event_flags.local_flags(parse(source))
            except Exception:  # noqa: BLE001 - half-typed source doesn't parse
                self._cache[key] = self._cache.get("last_local_flags", [])
            self._cache["last_local_flags"] = self._cache[key]
        seen = {s.text for s in out}
        out += [Suggestion(name, "chapter flag") for name in self._cache[key] if name not in seen]
        return out


def _in_string_or_comment(before: str) -> bool:
    in_string = False
    i = 0
    while i < len(before):
        ch = before[i]
        if in_string and ch == "\\":
            i += 1
        elif ch == '"':
            in_string = not in_string
        elif ch == "#" and not in_string:
            return True
        i += 1
    return in_string
