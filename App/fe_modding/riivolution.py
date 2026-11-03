"""Export a Radiant Dawn mod for Riivolution: a folder of changed files and an XML that loads them.

Riivolution runs a Wii disc and serves files from the SD card or a USB drive in place of the
disc's (Dolphin does the same from the game list: "Start with Riivolution Patches"), so a mod can
be played or shared without building a disc image. Path of Radiance is a GameCube game, which
Riivolution does not run.

The export (in ``build/riivolution/``) is laid out as it goes on the SD card:

- ``<mod id>/files/...``: the project's replaced and added files from the disc's ``files/`` tree,
  loaded by one ``<folder>`` patch over the disc root;
- ``riivolution/<mod id>.xml``: the patch, with one option to switch it on.

``main.dol`` cannot be replaced as a file: its changes become ``<memory>`` patches, written to RAM
after the game's executable is loaded. Each changed range of a section is a patch with the retail
bytes as ``original`` (Riivolution skips a patch whose original bytes do not match); a section the
mod added (a code cave) is written whole. Changes memory patches cannot express (another entry
point, a section moved or shrunk, a section inside the zeroed .bss area) stop the export, and
files the mod removed or other ``sys/`` files it changed are listed as warnings.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import quoteattr

from .exceptions import ModdingError
from .game_code.dol import Dol

EXPORT_DIR = "riivolution"
#: Changed bytes closer than this are one patch (fewer, larger patches).
MERGE_GAP = 8


class RiivolutionError(ModdingError):
    """Raised when a mod cannot be expressed as a Riivolution patch."""


@dataclass(frozen=True)
class MemoryPatch:
    address: int
    value: bytes
    original: Optional[bytes] = None    # None for memory the retail executable does not load

    def xml(self) -> str:
        attrs = f'offset="0x{self.address:08X}" value="{self.value.hex().upper()}"'
        if self.original is not None:
            attrs += f' original="{self.original.hex().upper()}"'
        return f"<memory {attrs} />"


@dataclass
class ExportResult:
    folder: Path
    xml: Path
    files: list[str] = field(default_factory=list)
    memory: list[MemoryPatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _runs(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """``(start, end)`` ranges where ``a`` and ``b`` (same length) differ, merged across gaps
    shorter than :data:`MERGE_GAP`."""
    runs: list[list[int]] = []
    i, n = 0, len(a)
    while i < n:
        if a[i] != b[i]:
            start = i
            while i < n and a[i] != b[i]:
                i += 1
            if runs and start - runs[-1][1] < MERGE_GAP:
                runs[-1][1] = i
            else:
                runs.append([start, i])
        else:
            i += 1
    return [(s, e) for s, e in runs]


def memory_patches(vanilla: Dol, modded: Dol) -> list[MemoryPatch]:
    """The ``<memory>`` patches that turn the loaded ``vanilla`` executable into ``modded``."""
    if modded.entry_point != vanilla.entry_point:
        raise RiivolutionError("main.dol starts at another entry point, which a memory patch cannot change.")
    by_address = {s.address: s for s in vanilla.sections}
    bss_start, bss_end = vanilla.bss_address, vanilla.bss_address + vanilla.bss_size
    kept = set()
    patches: list[MemoryPatch] = []
    for section in modded.sections:
        data = bytes(modded.data[section.offset:section.offset + section.size])
        retail = by_address.get(section.address)
        if retail is None:
            overlaps = [s for s in vanilla.sections
                        if s.address < section.address + section.size and section.address < s.address + s.size]
            if overlaps:
                raise RiivolutionError(f"main.dol section {section.index} overlaps retail code at "
                                       f"0x{overlaps[0].address:08X} at another address.")
            if section.address < bss_end and bss_start < section.address + section.size:
                raise RiivolutionError(f"main.dol section {section.index} lies in the .bss area the game "
                                       "clears at boot, so a memory patch there would be erased.")
            patches.append(MemoryPatch(section.address, data))
            continue
        kept.add(section.address)
        if section.size < retail.size:
            raise RiivolutionError(f"main.dol section {section.index} is smaller than the retail one.")
        old = bytes(vanilla.data[retail.offset:retail.offset + retail.size])
        for start, end in _runs(old, data[:retail.size]):
            patches.append(MemoryPatch(section.address + start, data[start:end], old[start:end]))
        if section.size > retail.size:
            patches.append(MemoryPatch(section.address + retail.size, data[retail.size:]))
    missing = [s for s in vanilla.sections if s.address not in kept]
    if missing:
        raise RiivolutionError(f"main.dol no longer has the retail section at 0x{missing[0].address:08X}.")
    return sorted(patches, key=lambda p: p.address)


def mod_id(name: str) -> str:
    """A folder and patch id for the mod: letters, digits and _ only."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    return cleaned or "mod"


def patch_xml(game_id: str, name: str, ident: str, memory: list[MemoryPatch], has_files: bool) -> str:
    lines = ['<wiidisc version="1">',
             f'  <id game={quoteattr(game_id[:4])} />',
             "  <options>",
             '    <section name="Tellius Modding">',
             f"      <option name={quoteattr(name)}>",
             '        <choice name="Enabled">',
             f"          <patch id={quoteattr(ident)} />",
             "        </choice>",
             "      </option>",
             "    </section>",
             "  </options>",
             f"  <patch id={quoteattr(ident)} root={quoteattr('/' + ident)}>"]
    if has_files:
        lines.append('    <folder external="files" disc="/" create="true" recursive="true" />')
    lines += [f"    {patch.xml()}" for patch in memory]
    lines += ["  </patch>", "</wiidisc>", ""]
    return "\n".join(lines)


def export_project(project, dest: Optional[Path] = None) -> ExportResult:
    """Write the Riivolution export of a Radiant Dawn project (input/output layout) and return
    what it holds. ``dest`` defaults to ``build/riivolution``; it is replaced."""
    if not project.profile.wii:
        raise RiivolutionError("Riivolution runs Wii discs only; Path of Radiance mods are built as a disc "
                               "image or shared as a patch.")
    if not project.is_overlay:
        raise RiivolutionError("The Riivolution export needs a project that keeps its files apart from the "
                               "vanilla ones (the shared vanilla files layout).")
    files = project.files
    changes = files.changes()
    dest = Path(dest) if dest is not None else project.build_dir / EXPORT_DIR
    ident = mod_id(project.name)
    warnings = []
    memory: list[MemoryPatch] = []
    if "sys/main.dol" in changes.replaced:
        memory = memory_patches(Dol(files.vanilla("sys/main.dol")), Dol(files.read("sys/main.dol")))
    other_sys = [rel for rel in changes.replaced + changes.added if rel.startswith("sys/") and rel != "sys/main.dol"]
    if other_sys:
        warnings.append("Riivolution cannot change these system files, so they are left out: " + ", ".join(other_sys))
    outside = [rel for rel in changes.replaced + changes.added
               if not rel.startswith("files/") and not rel.startswith("sys/")]
    if outside:
        warnings.append("Left out (not in the disc's file tree): " + ", ".join(outside))
    if changes.removed:
        warnings.append("Riivolution cannot remove files; these stay on the disc: " + ", ".join(changes.removed))
    if dest.exists():
        shutil.rmtree(dest)
    copied = []
    for rel in changes.replaced + changes.added:
        if rel.startswith("files/"):
            target = dest / ident / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(files.require(rel), target)
            copied.append(rel)
    game_id = files.read("sys/boot.bin")[:6].decode("ascii", "replace")
    xml = dest / "riivolution" / f"{ident}.xml"
    xml.parent.mkdir(parents=True, exist_ok=True)
    xml.write_bytes(patch_xml(game_id, project.name, ident, memory, bool(copied)).encode("utf-8"))
    return ExportResult(dest, xml, copied, memory, warnings)
