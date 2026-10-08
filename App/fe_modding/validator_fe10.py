"""Project check for Radiant Dawn: broken references in ``FE10Data.cms`` / ``FE10Growth.cms`` and
chapter files that are missing.

The same :class:`validator.Issue` rows as the Path of Radiance check (:mod:`validator`), with routes
into the Radiant Dawn Game Data page. An untouched retail extraction reports no errors; what the
retail data itself does in places the game never reaches is reported as a warning.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .exceptions import ProjectError
from .formats import fe10data, fe10growth
from .project import ModProject
from .validator import ERROR, WARNING, Issue, Report, _duplicates

WHERE = "FE10Data.cms"
#: Retail chapter records whose script or map the disc does not have: the Part 4 "a/b" records
#: (their map folders are lmapNN) and CFINAL (bmapFINAL). The game never loads those files, so a
#: missing one there is a warning; anywhere else it is an error.
RETAIL_MISSING_FILES = frozenset({f"C040{n}{s}" for n in range(1, 7) for s in "ab"} | {"CFINAL"})
#: List entries of these prefixes must name a record of the table.
_PREFIX_TABLE = {"PID_": "character", "JID_": "class", "IID_": "item", "SID_": "skill"}


def _ids(db: fe10data.Fe10Data, kind: str) -> set:
    return {r.id for r in db.table(kind) if r.id}


def validate_fe10data(data: bytes, growth: Optional[bytes] = None) -> list[Issue]:
    """Every check that needs only the two database files."""
    try:
        db = fe10data.read_fe10data(data)
    except Exception as exc:  # noqa: BLE001 - report instead of hiding the other checks
        return [Issue(WARNING, "Game data", WHERE, f"The file could not be read ({exc}); its records were not checked.")]
    issues: list[Issue] = []
    known = {kind: _ids(db, kind) for kind in ("character", "class", "item", "skill")}

    def check(area: str, route: tuple, owner: str, what: str, label: Optional[str], kind: str,
              severity: str = ERROR) -> None:
        if label and label not in known[kind]:
            issues.append(Issue(severity, area, WHERE, f"{owner} has {what} {label}, which does not exist.", route))

    def known_label(label: Optional[str]) -> bool:
        kind = next((k for p, k in _PREFIX_TABLE.items() if label and label.startswith(p)), None)
        return kind is None or label in known[kind]

    for area, kind, noun in (("Characters", "character", "PID"), ("Classes", "class", "JID"),
                             ("Items", "item", "IID"), ("Skills", "skill", "SID")):
        for value in _duplicates(r.id for r in db.table(kind)):
            issues.append(Issue(ERROR, area, WHERE, f"{noun} {value} is used by more than one record; "
                                "the game finds only one.", ("data", f"{kind}s" if kind != "class" else "classes")))

    for r in db.characters:
        route, owner = ("data", "characters", r.id), r.id or f"character {r.index}"
        if not r.values.get("jid"):
            issues.append(Issue(ERROR, "Characters", WHERE, f"{owner} has no class.", route))
        jid = r.values.get("jid")
        if jid and not jid.startswith("JID_"):  # retail PID_DUMMY names ダミー: a placeholder no chapter deploys
            issues.append(Issue(WARNING, "Characters", WHERE, f"{owner}'s class is {jid}, not a class ID.", route))
        else:
            check("Characters", route, owner, "class", jid, "class")
        for sid in r.lists["skills"]:
            check("Characters", route, owner, "skill", sid, "skill")
    for r in db.classes:
        route, owner = ("data", "classes", r.id), r.id or f"class {r.index}"
        for key, what in (("promotes_to", "promotion"), ("demotes_to", "previous tier"), ("other_form", "other form")):
            check("Classes", route, owner, what, r.values.get(key), "class")
        check("Classes", route, owner, "innate weapon", r.values.get("innate_weapon"), "item")
        for sid in r.lists["skills"]:
            check("Classes", route, owner, "skill", sid, "skill")
        check("Classes", route, owner, "extra skill", r.values.get("extra_skill"), "skill")
    for r in db.skills:
        route, owner = ("data", "skills", r.id), r.id or f"skill {r.index}"
        check("Skills", route, owner, "scroll item", r.values.get("item"), "item")
        for _mode, label in r.lists["conditions"]:
            if not known_label(label):
                issues.append(Issue(ERROR, "Skills", WHERE, f"{owner}'s conditions name {label}, which does not exist.",
                                    route))
    for r in db.table("chapter"):
        route, owner = ("data", "chapters", r.id), r.id or f"chapter {r.index}"
        check("Chapters", route, owner, "lord", r.values.get("lord"), "character")
    for r in db.table("support"):
        route, owner = ("data", "supports", r.id), r.id or f"support row {r.index}"
        check("Supports", route, owner, "support owner", r.values.get("pid"), "character")
        for pid, _flag, _speed in r.lists["partners"]:
            check("Supports", route, owner, "partner", pid, "character")
    for r in db.table("bond"):
        route = ("data", "bonds")
        for key in ("pid", "partner"):
            label = r.values.get(key)
            if label and label.startswith("PID_"):
                check("Bonds", route, f"Bond {r.index}", "character", label, "character")

    if growth is not None:
        try:
            for g in fe10growth.read_growth(growth):
                route = ("data", "growth", g.pid)
                if g.first > g.last:
                    issues.append(Issue(ERROR, "Stats per level", "FE10Growth.cms",
                                        f"{g.pid} has levels {g.first}-{g.last}, an empty range.", route))
                if g.pid and g.pid not in known["character"]:
                    issues.append(Issue(WARNING, "Stats per level", "FE10Growth.cms",
                                        f"{g.pid} has stats per level but no character record.", route))
        except Exception as exc:  # noqa: BLE001
            issues.append(Issue(WARNING, "Stats per level", "FE10Growth.cms", f"The file could not be read ({exc})."))
    return issues


def _check_chapter_files(project: ModProject, db: fe10data.Fe10Data, issues: list) -> None:
    files = project.files_dir
    mess_files = {p.name.lower() for p in (files / "Mess").glob("*.m")} if (files / "Mess").is_dir() else set()
    for r in db.table("chapter"):
        route, owner = ("data", "chapters", r.id), r.id or f"chapter {r.index}"
        script, folder, messages = r.values.get("script"), r.values.get("map"), r.values.get("messages")
        severity = WARNING if r.id in RETAIL_MISSING_FILES else ERROR
        if script and not (files / "Scripts" / f"{script}.cmb").is_file():
            issues.append(Issue(severity, "Chapters", f"Scripts/{script}.cmb", f"{owner}'s script is missing.", route))
        if folder and not (files / "zmap" / folder).is_dir():
            issues.append(Issue(severity, "Chapters", f"zmap/{folder}", f"{owner}'s map folder is missing.", route))
        if messages and not ({f"{messages.lower()}.m", f"e_{messages.lower()}.m"} & mess_files):
            issues.append(Issue(WARNING, "Chapters", f"Mess/{messages}.m",
                                f"{owner}'s message file is not on the disc (no {messages}.m in any language).", route))


def validate_fe10_project(project: ModProject) -> Report:
    try:
        data = project.read_logical("game_data")
    except ProjectError as exc:
        return Report([Issue(ERROR, "Project", WHERE, str(exc))])
    try:
        growth: Optional[bytes] = project.read_logical("growth_data")
    except ProjectError:
        growth = None
    issues = validate_fe10data(data, growth)
    try:
        _check_chapter_files(project, fe10data.read_fe10data(data), issues)
    except Exception:  # noqa: BLE001 - the database problem is already reported
        pass
    return Report(issues)


def summary(issues: Iterable[Issue]) -> str:
    issues = list(issues)
    errors = sum(i.severity == ERROR for i in issues)
    return f"{errors} error(s), {len(issues) - errors} warning(s)"
