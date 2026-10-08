"""Who names an ``FE8Data.bin`` record: the check before a record is removed
or renamed.

Records name each other, and are named by the rest of the game, through
their ID strings (``PID_``, ``JID_``, ``IID_``...), never by address:

* inside ``FE8Data.bin``, every pointer field whose string is the label
  (other records, support lists, bonds, skill restriction lists...);
* chapter scripts (``Scripts/*.cmb``), deployments (``zmap/*/dispos.cmp``),
  shops (``shop/*.bin``), the battle-model lists (``zdbx.cmp``) and the map
  model registry (``FE8Anim.bin``), searched as NUL-terminated strings;
* ``main.dol`` itself, whose string literals name a few records the engine
  looks up by ID (``PID_IKE``...).

Records of the character, class and item tables are also saved by their
1-based position (``fe8data.SAVED_BY_NUMBER``), which no search can see.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .formats import fe8data, lz10
from .game_profile import profile_of
from .project import ModProject


@dataclass(frozen=True)
class Reference:
    where: str  # "FE8Data.bin", "Scripts/C05.cmb", "sys/main.dol"...
    detail: str  # what names it ("class JID_ARCHER promotes_to", "3 times")

    def __str__(self) -> str:
        return f"{self.where}: {self.detail}"


#: Record-relative pointer field names per table, for readable references.
_FIELD_NAMES = {
    "character": {0x00: "pid", 0x04: "mpid", 0x0C: "fid", 0x10: "jid", 0x14: "affinity", 0x18: "weapon ranks",
                  0x1C: "skill 1", 0x20: "skill 2", 0x24: "skill 3", 0x28: "unpromoted model",
                  0x2C: "promoted model"},
    "class": {0x00: "jid", 0x04: "mjid", 0x08: "description", 0x0C: "promotes to", 0x10: "innate weapon",
              0x14: "weapon ranks", **{0x18 + 4 * i: f"skill {i + 1}" for i in range(5)},
              0x2C: "category", 0x30: "category", 0x34: "category", 0x38: "model"},
    "item": {0x00: "iid", 0x04: "miid", 0x08: "description", 0x38: "effect", 0x3C: "weapon effect"},
    "skill": {0x00: "sid", 0x04: "japanese name", 0x08: "msid", 0x0C: "help", 0x10: "help 2", 0x14: "effect",
              0x20: "scroll list", 0x24: "restriction list"},
    "chapter": {offset: name for name, offset in fe8data.CHAPTER_POINTER_FIELDS.items()},
}


def _record_id(data: bytes, kind: str, start: int, index: int) -> str:
    size = fe8data.TABLES[kind][1]
    if kind == "chapter":
        return f"chapter id {data[start + index * size + 0x3C]}"
    ptr = struct.unpack_from(">I", data, start + index * size)[0]
    return fe8data._resolve(data, ptr) or f"record {index}"


def fe8data_references(data: bytes, label: str, *, skip: Optional[tuple[str, int]] = None) -> list[Reference]:
    """Every pointer field of ``data`` naming ``label``. ``skip`` =
    (kind, index) leaves out the fields of that record (the record itself)."""
    encoded = fe8data._encode_label(label)
    fields = [f for f in fe8data.listed_pointer_fields(data)
              if fe8data._string_at(data, struct.unpack_from(">I", data, f)[0]) == encoded]
    if not fields:
        return []
    tables = {}
    for kind in fe8data.TABLES:
        try:
            tables[kind] = (fe8data.table_start(data, kind), fe8data.table_count(data, kind))
        except ValueError:
            continue
    sections = sorted((fe8data.HEADER_SIZE + o, name) for name, o in fe8data.symbol_offsets(data).items()
                      if not name.startswith("SID_"))
    lists = _skill_list_owners(data)
    lists.update(_support_owners(data))
    result: dict[str, int] = {}
    for field in sorted(fields):
        detail = None
        for kind, (start, count) in tables.items():
            size = fe8data.TABLES[kind][1]
            if start <= field < start + count * size:
                index, offset = divmod(field - start, size)
                if skip == (kind, index):
                    detail = ""
                    break
                name = _FIELD_NAMES.get(kind, {}).get(offset, f"+0x{offset:02X}")
                detail = f"{kind} {_record_id(data, kind, start, index)} {name}"
                break
        if detail is None and field in lists:
            detail = lists[field]
        if detail is None:
            section = next((name for pos, name in reversed(sections) if pos <= field), "data")
            detail = {"RelianceData": "support list", "KiznaData": "bond", "GroupData": "army group",
                      "BattleSkyData": "battle sky", "BattleTerrData": "battle terrain",
                      "DivineData": "affinity table", "TerrainData": "terrain type"}.get(section, section)
        if detail:
            result[detail] = result.get(detail, 0) + 1
    return [Reference("FE8Data.bin", detail if n == 1 else f"{detail} ({n} times)") for detail, n in result.items()]


def _skill_list_owners(data: bytes) -> dict[int, str]:
    """Absolute offsets of the words of every skill's scroll and restriction
    list, described by their skill."""
    owners = {}
    try:
        start, count = fe8data.table_start(data, "skill"), fe8data.table_count(data, "skill")
    except ValueError:
        return owners
    for i in range(count):
        rec = start + i * fe8data.SKILL_RECORD_SIZE
        sid = _record_id(data, "skill", start, i)
        scroll, restriction = struct.unpack_from(">II", data, rec + 0x20)
        if scroll:
            owners[fe8data.HEADER_SIZE + scroll] = f"skill {sid} scroll"
        for k in range(data[rec + 0x1C] if restriction else 0):
            owners[fe8data.HEADER_SIZE + restriction + 4 * k] = f"skill {sid} restriction list"
    return owners


def _support_owners(data: bytes) -> dict[int, str]:
    """Absolute offsets of the PID fields of the support lists and bonds,
    described by whose list or which bond they belong to."""
    owners = {}
    label = lambda o: fe8data._resolve(data, struct.unpack_from(">I", data, o)[0]) or "?"  # noqa: E731
    try:
        start = fe8data.section_start(data, "RelianceData")
        pos = start + 4
        for _ in range(struct.unpack_from(">I", data, start)[0]):
            owner = label(pos)
            owners[pos] = f"support list of {owner} (owner)"
            slots = data[pos + 7]
            for k in range(slots):
                owners[pos + 8 + 8 * k] = f"support list of {owner}"
            pos += 8 + 8 * slots
        pos = fe8data.section_start(data, "KiznaData") + 4
        while struct.unpack_from(">I", data, pos)[0]:
            name = f"bond {label(pos)} / {label(pos + 4)}"
            owners[pos] = owners[pos + 4] = name
            pos += 12
    except (ValueError, struct.error):
        pass
    return owners


def _count(blob: bytes, label: str) -> int:
    pattern = rb"(?<![A-Za-z0-9_])" + re.escape(fe8data._encode_label(label)) + rb"\x00"
    return len(re.findall(pattern, blob))


def _game_files(project: ModProject) -> Iterable[tuple[str, Path, bool]]:
    """(display path, file, compressed) of every file that names records."""
    root = project.extracted_dir
    files = root / "files"
    profile = profile_of(project)
    shops = profile.shop_folder(files)
    yield from ((f"Scripts/{p.name}", p, False) for p in sorted((files / "Scripts").glob("*.cmb")))
    yield from ((f"zmap/{p.parent.name}/dispos.cmp", p, True) for p in sorted((files / "zmap").glob("*/dispos.cmp")))
    yield from ((f"{shops.name}/{p.name}", p, False) for p in sorted(shops.glob("*.bin")))
    for logical in ("battle_data", "anim_data"):
        if profile.has_file(logical) and profile.path(files, logical).is_file():
            path = profile.path(files, logical)
            yield path.name, path, profile.logical(logical).compressed
    if (root / "sys" / "main.dol").is_file():
        yield "sys/main.dol", root / "sys" / "main.dol", False


def file_references(project: ModProject, label: str) -> list[Reference]:
    """Every game file outside ``FE8Data.bin`` that contains ``label``."""
    result = []
    for where, path, compressed in _game_files(project):
        try:
            blob = path.read_bytes()
            if compressed:
                blob = lz10.decompress(blob)
        except (OSError, ValueError, lz10.LZ10Error):
            continue
        n = _count(blob, label)
        if n:
            detail = "string literal (the engine looks it up by name)" if where == "sys/main.dol" else \
                f"named {n} time{'s' if n > 1 else ''}"
            result.append(Reference(where, detail))
    return result


def record_references(project: Optional[ModProject], data: bytes, kind: str, index: int) -> list[Reference]:
    """Everything that names record ``index`` of table ``kind`` by its ID,
    in ``FE8Data.bin`` and (with a project) in the other game files."""
    if kind == "chapter":
        return []  # chapters are found by chapter id, named by scripts' chapter changes
    label = _record_id(data, kind, fe8data.table_start(data, kind), index)
    refs = fe8data_references(data, label, skip=(kind, index))
    if project is not None:
        refs += file_references(project, label)
    return refs
