"""Project check: finds broken references and missing files before the game does.

Records name each other by ID string (``PID_``, ``JID_``, ``IID_``, ``SID_``), and a chapter
is a set of files named by its ``ChapterData`` record. A typo, a deleted record or a missing
file is only seen in the game, usually as a crash. :func:`validate_project` reads the project
and returns every problem it can find as :class:`Issue` rows; :func:`validate_fe8data` is the
part that needs only the bytes of ``FE8Data.bin``. Nothing here writes or uses Tk.

Severity: ``error`` is something the game cannot load or will misread; ``warning`` is
suspicious but may be intended (a script string that only looks like a record ID, a chapter no
flow reaches). A check that cannot read its input says so as a ``warning`` and the rest still
run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from . import chapters
from .formats import dispo, fe8data, lz10, pak, shop, supports
from .project import ModProject

ERROR, WARNING = "error", "warning"
SEVERITIES = (ERROR, WARNING)

#: Chapter ids from here up are trial maps and other special records, not story chapters.
FIRST_SPECIAL_CHAPTER = 90

_RECORD_STRING = re.compile(rb"(?<![A-Za-z0-9_])((?:PID|JID|IID|SID)_[A-Za-z0-9_]+)\x00")


@dataclass(frozen=True)
class Issue:
    severity: str
    area: str       # "Characters", "Classes", "Chapter 07"...
    where: str      # file or table the problem is in
    message: str
    route: tuple = ()  # workspace route that opens the place to fix it, when there is one

    def __str__(self) -> str:
        return f"{self.severity}: {self.where}: {self.message}"


@dataclass
class Report:
    issues: list

    @property
    def errors(self) -> list:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors


def _duplicates(values: Iterable[Optional[str]]) -> list[str]:
    seen, repeated = set(), []
    for value in values:
        if value is None:
            continue
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return repeated


def validate_fe8data(data: bytes) -> list[Issue]:
    """Every check that needs only ``FE8Data.bin``."""
    issues: list[Issue] = []
    where = "FE8Data.bin"
    try:
        fe8 = fe8data.read_fe8data(data)
    except Exception as exc:  # noqa: BLE001 - report instead of hiding the other checks
        return [Issue(WARNING, "FE8Data.bin", where, f"The file could not be read ({exc}); its records were not checked.")]

    pids = {c.pid for c in fe8.characters if c.pid}
    jids = {c.jid for c in fe8.classes if c.jid}
    iids = {i.iid for i in fe8.items if i.iid}
    sids = {s.sid for s in fe8.skills if s.sid}

    for area, ids, noun in (("Characters", (c.pid for c in fe8.characters), "PID"),
                            ("Classes", (c.jid for c in fe8.classes), "JID"),
                            ("Items", (i.iid for i in fe8.items), "IID"),
                            ("Skills", (s.sid for s in fe8.skills), "SID")):
        for value in _duplicates(ids):
            issues.append(Issue(ERROR, area, where,
                                f"{noun} {value} is used by more than one record; the game finds only one."))

    for c in fe8.characters:
        route = ("data",)
        name = c.pid or f"character {c.index}"
        if c.jid is None:
            issues.append(Issue(ERROR, "Characters", where, f"{name} has no class.", route))
        elif c.jid not in jids:
            issues.append(Issue(ERROR, "Characters", where, f"{name} has class {c.jid}, which does not exist.", route))
        for sid in c.sids:
            if sid and sid not in sids:
                issues.append(Issue(ERROR, "Characters", where, f"{name} has skill {sid}, which does not exist.", route))
        if c.weapon_ranks is not None and len(c.weapon_ranks) != 9:
            issues.append(Issue(ERROR, "Characters", where,
                                f"{name}: the weapon rank string {c.weapon_ranks!r} must have 9 characters."))

    for k in fe8.classes:
        name = k.jid or f"class {k.index}"
        if k.promotes_to and k.promotes_to not in jids:
            issues.append(Issue(ERROR, "Classes", where, f"{name} promotes to {k.promotes_to}, which does not exist."))
        if k.innate_weapon and k.innate_weapon not in iids:
            issues.append(Issue(ERROR, "Classes", where,
                                f"{name} has innate weapon {k.innate_weapon}, which does not exist."))
        for sid in k.skills:
            if sid and sid not in sids:
                issues.append(Issue(ERROR, "Classes", where, f"{name} has skill {sid}, which does not exist."))
        if k.weapon_ranks is not None and len(k.weapon_ranks) != 9:
            issues.append(Issue(ERROR, "Classes", where,
                                f"{name}: the weapon rank string {k.weapon_ranks!r} must have 9 characters."))

    for s in fe8.skills:
        name = s.sid or f"skill {s.index}"
        for label in s.restricted_to:
            if label.startswith("PID_") and label not in pids or label.startswith("JID_") and label not in jids:
                issues.append(Issue(WARNING, "Skills", where, f"{name} is restricted to {label}, which does not exist."))
        for iid in s.skill_items:
            if iid and iid not in iids:
                issues.append(Issue(WARNING, "Skills", where, f"{name}'s scroll {iid} does not exist."))

    try:
        lists = supports.read_support_lists(data)
        for line in supports.validate_support_lists(lists):
            severity = ERROR if line.startswith("Error:") else WARNING
            issues.append(Issue(severity, "Supports", where, line.split(":", 1)[1].strip()))
        for sl in lists:
            if sl.owner not in pids:
                issues.append(Issue(ERROR, "Supports", where, f"A support list belongs to {sl.owner}, which does not exist."))
            for slot in sl.slots:
                if not slot.empty and slot.partner not in pids:
                    issues.append(Issue(ERROR, "Supports", where,
                                        f"{sl.owner} has support partner {slot.partner}, which does not exist."))
        for bond in supports.read_bonds(data):
            for pid in (bond.pid1, bond.pid2):
                if pid not in pids:
                    issues.append(Issue(WARNING, "Supports", where, f"A bond names {pid}, which does not exist."))
    except Exception as exc:  # noqa: BLE001
        issues.append(Issue(WARNING, "Supports", where, f"The support tables could not be read ({exc})."))

    try:
        records = fe8data.read_chapter_data(data)
    except Exception as exc:  # noqa: BLE001
        records = []
        issues.append(Issue(WARNING, "Chapters", where, f"ChapterData could not be read ({exc})."))
    for cid in _duplicates(r.chapter_id for r in records):
        issues.append(Issue(ERROR, "Chapters", where, f"Chapter id {cid} is used by more than one ChapterData record."))
    return issues


def _chapter_label(record) -> str:
    return f"Chapter {record.chapter_id:02d}"


def _decompress_pak(path):
    packed = lz10.decompress(path.read_bytes())
    return packed, pak.read_pak_entries(packed)


def _check_chapter_files(project: ModProject, records, issues: list, titles: dict, reachable: Optional[set]) -> None:
    files = project.extracted_dir / "files"
    for r in records:
        if r.chapter_id >= FIRST_SPECIAL_CHAPTER:
            continue
        area = _chapter_label(r)
        route = ("chapter", f"{r.chapter_id:02d}")
        if r.script and not (files / "Scripts" / f"{r.script}.cmb").is_file():
            issues.append(Issue(ERROR, area, f"Scripts/{r.script}.cmb", "The chapter's script file is missing.", route))
        if r.message and not (files / "Mess" / f"{r.message}.m").is_file():
            issues.append(Issue(ERROR, area, f"Mess/{r.message}.m", "The chapter's message file is missing.", route))
        if r.map_name:
            folder = files / "zmap" / r.map_name
            for name in ("map.cmp", "dispos.cmp"):
                if not (folder / name).is_file():
                    issues.append(Issue(ERROR, area, f"zmap/{r.map_name}/{name}", "The chapter's map file is missing.", route))
        else:
            issues.append(Issue(ERROR, area, "FE8Data.bin", "The chapter record names no map.", route))
        if f"{r.chapter_id:02d}" not in titles and r.chapter_id >= 1:
            issues.append(Issue(WARNING, area, "Mess/common.m", f"No title ({r.title_key or 'MCT'}): the chapter shows blank.", route))
        if reachable is not None and r.chapter_id > 31 and r.chapter_id not in reachable:
            issues.append(Issue(WARNING, area, "main.dol",
                                "No chapter leads to this one in the story flow, so it cannot be played in order.", route))


def _check_deployments(project: ModProject, pids: set, jids: set, issues: list) -> None:
    zmap = project.extracted_dir / "files" / "zmap"
    for path in sorted(zmap.glob("*/dispos.cmp")) if zmap.is_dir() else []:
        folder = path.parent.name
        try:
            packed, entries = _decompress_pak(path)
        except Exception as exc:  # noqa: BLE001
            issues.append(Issue(ERROR, "Deployments", f"zmap/{folder}/dispos.cmp", f"The file could not be read ({exc})."))
            continue
        chapter = chapters.chapter_of_map_folder(folder)
        route = ("chapter", chapter) if chapter else ()
        area = f"Chapter {chapter}" if chapter else "Deployments"
        for entry in entries:
            if not re.fullmatch(r"dispos_\w\.bin", entry.name):
                continue
            try:
                sections = dispo.read_dispo_bytes(pak.read_pak_file_content(packed, entry))
            except Exception as exc:  # noqa: BLE001
                issues.append(Issue(ERROR, area, f"zmap/{folder}/{entry.name}", f"The file could not be read ({exc}).", route))
                continue
            for section in sections:
                for index, unit in enumerate(section.units):
                    pid, jid = unit.fields[0].display, unit.fields[1].display
                    at = f"zmap/{folder}/{entry.name}"
                    who = f"section {section.name}, unit {index + 1}"
                    if pid and pid not in pids:
                        issues.append(Issue(ERROR, area, at, f"{who} is {pid}, which does not exist.", route))
                    if jid and jid not in jids:
                        issues.append(Issue(ERROR, area, at, f"{who} has class {jid}, which does not exist.", route))


def _check_scripts(project: ModProject, known: set, issues: list) -> None:
    scripts = project.extracted_dir / "files" / "Scripts"
    for path in sorted(scripts.glob("*.cmb")) if scripts.is_dir() else []:
        try:
            blob = path.read_bytes()
        except OSError as exc:
            issues.append(Issue(WARNING, "Scripts", f"Scripts/{path.name}", f"The file could not be read ({exc})."))
            continue
        missing = sorted({m.decode("ascii") for m in _RECORD_STRING.findall(blob)} - known)
        match = re.fullmatch(r"[Cc](\d+)", path.stem)
        route = ("chapter", match.group(1).zfill(2), "script") if match else ()
        for label in missing:
            issues.append(Issue(WARNING, f"Chapter {match.group(1).zfill(2)}" if match else "Scripts",
                                f"Scripts/{path.name}", f"The script names {label}, which does not exist.", route))


def _check_shops(project: ModProject, iids: set, issues: list) -> None:
    folder = project.extracted_dir / "files" / "shop"
    for path in sorted(folder.glob("*.bin")) if folder.is_dir() else []:
        try:
            doc = shop.parse_shop(path.read_bytes())
        except Exception as exc:  # noqa: BLE001
            issues.append(Issue(ERROR, "Shops", f"shop/{path.name}", f"The file could not be read ({exc})."))
            continue
        for section in doc.sections:
            for item in section.items:
                if isinstance(item, str) and item.startswith("IID_") and item not in iids:
                    issues.append(Issue(ERROR, "Shops", f"shop/{path.name}",
                                        f"{section.name} sells {item}, which does not exist."))


def validate_project(project: ModProject, flow=None) -> Report:
    """Check an extracted project. ``flow`` is a ``game_code.chapter_flow.ChapterFlow`` (optional);
    with it, chapters above the retail ones that no chapter leads to are reported."""
    fe8_path = project.extracted_dir / "files" / "FE8Data.bin"
    if not fe8_path.is_file():
        return Report([Issue(ERROR, "Project", "FE8Data.bin", "The project has no extracted FE8Data.bin; extract the disc first.")])
    data = fe8_path.read_bytes()
    issues = validate_fe8data(data)
    try:
        fe8 = fe8data.read_fe8data(data)
        records = fe8data.read_chapter_data(data)
    except Exception:  # noqa: BLE001 - already reported by validate_fe8data
        return Report(issues)

    pids = {c.pid for c in fe8.characters if c.pid}
    jids = {c.jid for c in fe8.classes if c.jid}
    iids = {i.iid for i in fe8.items if i.iid}
    sids = {s.sid for s in fe8.skills if s.sid}

    reachable = None
    if flow is not None and flow.available:
        reachable, current = set(), 0
        while current not in reachable and current < FIRST_SPECIAL_CHAPTER:
            reachable.add(current)
            current = flow.next_of(current)
    titles = chapters.chapter_titles(project)
    _check_chapter_files(project, records, issues, titles, reachable)
    _check_deployments(project, pids, jids, issues)
    _check_scripts(project, pids | jids | iids | sids, issues)
    _check_shops(project, iids, issues)
    return Report(sorted(issues, key=lambda i: (SEVERITIES.index(i.severity), i.area, i.where, i.message)))
