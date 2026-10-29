"""Project check for Radiant Dawn: broken references in ``FE10Data.cms`` / ``FE10Growth.cms``,
chapter files that are missing, and the same deployment, script and shop checks as Path of Radiance.

The same :class:`validator.Issue` rows as the Path of Radiance check (:mod:`validator`), with routes
into the Radiant Dawn Game Data page. An untouched retail extraction reports no errors; what the
retail data itself does in places the game never reaches is reported as a warning.
"""

from __future__ import annotations

from typing import Iterable, Optional

from . import chapters
from .exceptions import ProjectError
from .formats import dispo, fe10data, fe10growth, lz10, map_file, pak
from .project import ModProject
from .validator import (ERROR, SEVERITIES, WARNING, Issue, Report, _check_script_globals, _check_scripts,
                        _check_shops, _duplicates)
from .game_profile import files_root_of

WHERE = "FE10Data.cms"
#: Retail chapter records whose script or map the disc does not have: the Part 4 "a/b" records
#: (their map folders are lmapNN) and CFINAL (bmapFINAL). The game never loads those files, so a
#: missing one there is a warning; anywhere else it is an error.
RETAIL_MISSING_FILES = frozenset({f"C040{n}{s}" for n in range(1, 7) for s in "ab"} | {"CFINAL"})
#: Retail deployments that name a missing record: (map folder, section, ID). ``PID_TIBARN_EV`` is a unit
#: of a 3-15 event map with no character record in the retail database.
RETAIL_MISSING_DEPLOYED = frozenset({("emap0315a", "emap0315a_ed01_c", "PID_TIBARN_EV")})
#: Retail units whose turn-1 tile is terrain their class cannot enter: (map folder, section, PID).
#: The game moves such a unit to a passable tile nearby, so these are left alone, as is the debug
#: map ``bmap0000`` (RETAIL_TEST_MAPS).
RETAIL_TEST_MAPS = frozenset({"bmap0000"})
RETAIL_IMPASSABLE_STARTS = frozenset({
    ("bmap0103", "bmap0103_mikata_c", "PID_SOTHE"),
    *(("bmap0109", f"bmap0109_horyo_{d}", "PID_MAP9_PRISONER") for d in "nh"),
    *(("bmap0203", f"bmap0203_teki_{d}", "PID_REBELLIONLARMOR2") for d in "nh"),
    ("bmap0204", "bmap0204_ed01_c", "PID_CRIMEASOLDIER"),
    *(("bmap0313", f"bmap0313_teki2_{d}", "PID_CRIMEASOLDIER") for d in "nh"),
    ("bmap0407a", "bmap0407a_op0407a_02_c", "PID_APOSTLELKNIGHT"),
    ("emap0407c", "emap0407c_mikata_c", "PID_SENERIO"),
    *(("test_taisen01", s, "PID_VS_ARC") for s in ("test_taisen01_4p_red_n", "test_taisen01_bak4p_red_n")),
})
#: Deployment fields that name a record: (field, table, what the message calls it).
_DISPO_REFERENCES = (("pid", "character", "is"), ("jid", "class", "has class"),
                     *((f"item{i}", "item", "carries") for i in range(7)),
                     *((f"skill{i}", "skill", "has skill") for i in range(5)))
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
    files = files_root_of(project)
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


def _terrain_grid(folder) -> Optional[list]:
    """The map folder's ``[x][y]`` terrain names (``map.cmp``'s ``map.bin``), None when unreadable."""
    try:
        compressed = (folder / "map.cmp").read_bytes()
        # the pack's entry table, then only as far as map.bin's end: the models after it are most of it
        try:
            entries = pak.read_pak_entries(lz10.decompress(compressed, limit=0x8000))
        except Exception:  # noqa: BLE001 - an entry table longer than the prefix
            entries = pak.read_pak_entries(lz10.decompress(compressed))
        entry = next(e for e in entries if e.name == "map.bin")
        packed = lz10.decompress(compressed, limit=entry.offset + entry.length)
        return map_file.terrain_grid(pak.read_pak_file_content(packed, entry))
    except Exception:  # noqa: BLE001 - the Build tab reports unreadable maps
        return None


def _impassable_start(unit, grid, moves: dict, costs: dict) -> Optional[str]:
    """The terrain name when ``unit``'s turn-1 tile (its second position) is one its class can't
    enter (movement cost 255 for the class's movement type), else None. ``moves``: JID -> movement
    type; ``costs``: terrain name -> its record's values."""
    jid = unit[dispo.FIELD["jid"]]
    move = moves.get(jid.partition("/")[0]) if isinstance(jid, str) else None
    x, y = unit[dispo.FIELD["pos2_x"]], unit[dispo.FIELD["pos2_y"]]
    if move is None or grid is None or not (0 <= x < len(grid) and 0 <= y < len(grid[0])):
        return None
    terrain = costs.get(grid[x][y])
    return grid[x][y] if terrain is not None and terrain.get(f"cost_{move}") == 255 else None


def _check_deployments(project: ModProject, known: dict, issues: list, db: Optional[fe10data.Fe10Data] = None) -> None:
    """Every unit of every ``zmap/<folder>/dispos_<diff>.bin`` names records that exist. A label's
    ``/`` suffix (``IID_HERB/D``, an item the unit drops; ``/L``, ``/S``, ``/F``) is a flag, not part
    of the ID. With the database, a unit whose turn-1 tile is terrain its class can't enter is a
    warning: the game moves it to a passable tile nearby, and its deployment crashes when there is
    none (checked in Dolphin: an 11x11 block of impassable 森 around 1-1's start)."""
    zmap = files_root_of(project) / "zmap"
    grids: dict = {}
    moves = {r.id: r.values.get("movement_type") for r in db.classes} if db is not None else {}
    costs = {r.id: r.values for r in db.table("terrain")} if db is not None else {}
    for path in sorted(zmap.glob("*/dispos_*.bin")) if zmap.is_dir() else []:
        folder, at = path.parent.name, f"zmap/{path.parent.name}/{path.name}"
        chapter = chapters.chapter_of_map_folder(folder)
        route = ("chapter", chapter) if chapter else ()
        area = f"Chapter {chapter}" if chapter else "Deployments"
        try:
            doc = dispo.parse_dispo(path.read_bytes())
        except Exception as exc:  # noqa: BLE001
            issues.append(Issue(ERROR, area, at, f"The file could not be read ({exc}).", route))
            continue
        # one row per missing ID and file: a renamed class would otherwise give one per unit
        missing: dict = {}
        if db is not None and folder not in grids and folder not in RETAIL_TEST_MAPS:
            grids[folder] = _terrain_grid(path.parent)
        for section in doc.sections:
            for index, unit in enumerate(section.units):
                terrain = _impassable_start(unit, grids.get(folder), moves, costs)
                pid = unit[dispo.FIELD["pid"]]
                if terrain and (folder, section.name, pid) not in RETAIL_IMPASSABLE_STARTS:
                    x, y = unit[dispo.FIELD["pos2_x"]], unit[dispo.FIELD["pos2_y"]]
                    issues.append(Issue(WARNING, area, at,
                                        f"section {section.name}, unit {index + 1} ({pid}) starts on {terrain} "
                                        f"({x}, {y}), which its class cannot enter: the game moves it to a "
                                        "passable tile nearby, and the deployment crashes when there is none.",
                                        route))
                for field, kind, verb in _DISPO_REFERENCES:
                    value = unit[dispo.FIELD[field]]
                    label = value.partition("/")[0] if isinstance(value, str) else None
                    if label and label not in known[kind]:
                        retail = (folder, section.name, label) in RETAIL_MISSING_DEPLOYED
                        missing.setdefault((verb, label, retail), []).append((section.name, index + 1))
        for (verb, label, retail), units in missing.items():
            if len(units) == 1:
                text = f"section {units[0][0]}, unit {units[0][1]} {verb} {label}, which does not exist."
            else:
                names = ", ".join(dict.fromkeys(name for name, _ in units))
                text = f"{len(units)} units name {label}, which does not exist (sections {names})."
            if retail:
                issues.append(Issue(WARNING, area, at, text + " The retail data has it too.", route))
            else:
                issues.append(Issue(ERROR, area, at, text, route))


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
        db = fe10data.read_fe10data(data)
    except Exception:  # noqa: BLE001 - the database problem is already reported
        return Report(issues)
    known = {kind: _ids(db, kind) for kind in ("character", "class", "item", "skill")}
    _check_chapter_files(project, db, issues)
    _check_deployments(project, known, issues, db)
    _check_scripts(project, set().union(*known.values()), issues)
    _check_script_globals(project, issues)
    _check_shops(project, known["item"], issues)
    return Report(sorted(issues, key=lambda i: (SEVERITIES.index(i.severity), i.area, i.where, i.message)))


def summary(issues: Iterable[Issue]) -> str:
    issues = list(issues)
    errors = sum(i.severity == ERROR for i in issues)
    return f"{errors} error(s), {len(issues) - errors} warning(s)"
