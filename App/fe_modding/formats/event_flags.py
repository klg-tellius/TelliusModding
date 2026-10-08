"""Event-script flags (``regist``/``global``/``set``/``get``/``clr``) and where
a save file keeps them.

The game keeps every script flag in one 96-slot table, ``event_flag_table``
(``0x803307BC`` = ``party_data+0xB4``)::

    +0x000  char *names[96]    registered names (pointers into a .cmb pool)
    +0x180  u32   hashes[96]   h = h*37 + (signed char)c over the name
    +0x300  u8    bits[12]     slot i = bits[i >> 3] bit (i & 7), LSB first

A name is bound to a slot by registration and looked up by hash + strcmp,
scanning slots 0..95 (the first match wins):

* ``global(name)`` takes the lowest empty slot and clears its bit. Only
  ``startup.cmb``'s ``RegistGlobalFlags`` calls it, once at boot, after the
  engine's own eight ``gf_*`` flags, so globals occupy slots 0..29.
* ``regist(name)`` takes the highest empty slot (95 downward) and leaves the
  bit alone. Chapter scripts call it from ``Startup`` (directly or through
  ``RegistLocationFlags``/``RegistBaseFlags``), all unconditionally.
* ``set``/``clr`` change the bit, ``get`` reads it. An unregistered name is a
  silent no-op for ``set``/``clr`` and reads as 0 for ``get``.

At every chapter start (and every mid-chapter resume) the engine clears the
names from slot 95 downward until it meets an empty slot, clears the bit of
every nameless slot, then runs ``Startup`` again. Global bits therefore
survive for the whole playthrough, while a new chapter starts with only its
own local bits (RAM dumps of several chapter openings show no carry-over).
A save block's chapter flags belong to ``Scripts/CNN.cmb`` for map ``bmapNN``
(and ``bmapNN_2``); a save made between chapters can still hold the finished
chapter's bits, which the next chapter start clears.

**Only the 12 bit bytes are saved** - names are not. A save block's flags sit
at ``block + 0x164`` (``BMST`` payload offset ``0xAC``); on load the game
re-runs the same registrations and restores the bits by slot index. Changing
the registration order of an existing chapter or of ``RegistGlobalFlags``
therefore re-labels the bits of every save made before the change.

Each save block is protected by a standard CRC-32 over ``block[0x70:size]``
stored at ``block+0x50`` (blocks with ``save_kind`` 1 are exempt, and a CRC of
``0x12345678`` is accepted as-is) - :func:`refresh_crc` recomputes it after an
edit.

**Radiant Dawn** (:data:`FE10_FLAGS`) works the same way with a 128-slot
table (``0x803CAB38``: names ``+0x144``, hashes ``+0x344``, bits
``0x803CB07C``; ``global``/``regist``/``get``/``set``/``clr`` are the same
code with 0x80 bounds). ``init_event_script_system`` (``0x8009CF6C``)
registers ``gf_canceled``, ``gf_gameover``, ``gf_complete`` and
``gf_reserved2``..``6``; startup.cmb's ``RegistGlobalFlags`` adds 19 more.
The save side (Wii NAND) is not decoded yet, so the ``.gci`` helpers below are
Path of Radiance only.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .cmb import ast as A

SLOT_COUNT = 96
BIT_BYTES = SLOT_COUNT // 8

# Registered by init_event_script_system before RegistGlobalFlags runs.
ENGINE_FLAGS = (
    "gf_canceled", "gf_gameover", "gf_complete", "gf_reserved4",
    "gf_reserved3", "gf_reserved2", "gf_triA", "gf_triB",
)

# Vanilla startup.cmb RegistGlobalFlags, in order (slots 8..29), with a gloss.
VANILLA_GLOBAL_FLAGS = (
    ("G_シノン死亡", "Shinon died"),
    ("G_ガトリー死亡", "Gatrie died"),
    ("G_マーシャ死亡", "Marcia died"),
    ("G_レテ死亡", "Lethe died"),
    ("G_モウディ死亡", "Mordecai died"),
    ("G_リュシオン死亡", "Reyson died"),
    ("G_ＭＡＰ１２で漆黒とアイク戦闘", "Ike fought the Black Knight on map 12"),
    ("G_ヤナフ死亡", "Janaff died"),
    ("G_ウルキ死亡", "Ulki died"),
    ("G_情報３兄弟", "Info conversation: the three brothers"),
    ("G_リザーブド", "Reserved (unused)"),
    ("G_リザーブド", "Reserved (unused)"),
    ("G_Map20の情報会話３", "Map 20 info conversation 3"),
    ("G_ティバーン死亡", "Tibarn died"),
    ("G_リザーブド", "Reserved (unused)"),
    ("G_Ｍａｐ４マーシャ会話", "Map 4 Marcia conversation"),
    ("G_フォルカ仲間", "Volke recruited"),
    ("G_Map31ネサラ使用", "Naesala used on map 31"),
    ("G_ジル仲間条件", "Jill recruitment condition met"),
    ("G_漆黒の騎士倒した", "Black Knight defeated"),
    ("G_クリミア忠臣イベント", "Crimean retainers event"),
    ("DBG_最初からやってる", "Debug: playthrough started from the beginning"),
)
RESERVED_GLOBAL = "G_リザーブド"  # three unused placeholder slots (18, 19, 22)
ENGINE_FLAG_GLOSSES = {
    "gf_canceled": "Scene or event cancelled", "gf_gameover": "Map lost (runs Gameover events)",
    "gf_complete": "Map won (runs Complete events)", "gf_reserved4": "Reserved by the engine",
    "gf_reserved3": "Reserved by the engine", "gf_reserved2": "Reserved by the engine",
    "gf_triA": "Triangle-attack message A shown", "gf_triB": "Triangle-attack message B shown",
}
FLAG_GLOSSES = {**ENGINE_FLAG_GLOSSES,
                **{name: gloss for name, gloss in VANILLA_GLOBAL_FLAGS if name != RESERVED_GLOBAL}}

ENGINE_FLAGS_FE10 = (
    "gf_canceled", "gf_gameover", "gf_complete", "gf_reserved2",
    "gf_reserved3", "gf_reserved4", "gf_reserved5", "gf_reserved6",
)
# Vanilla Radiant Dawn startup.cmb RegistGlobalFlags, in order (slots 8..26).
VANILLA_GLOBAL_FLAGS_FE10 = (
    ("DBG_最初からやってる", "Debug: playthrough started from the beginning"),
    ("G_ペレアス死亡", "Pelleas died"),
    ("G_0407bアイク記憶復活", "4-7b: Ike's memory restored"),
    ("G_TRIANGLE_OSCAR", "Triangle attack: Oscar"),
    ("G_TRIANGLE_BOLE", "Triangle attack: Boyd"),
    ("G_TRIANGLE_LOFA", "Triangle attack: Rolf"),
    ("G_TRIANGLE_ERINCIA", "Triangle attack: Elincia"),
    ("G_TRIANGLE_TANIS", "Triangle attack: Tanith"),
    ("G_TRIANGLE_MARCIA", "Triangle attack: Marcia"),
    ("G_TRIANGLE_SIGRUN", "Triangle attack: Sigrun"),
    ("G_MS_0308_BT_Sen", "3-8 battle conversation"),
    ("G_MS_0314_BT_Sen", "3-14 battle conversation"),
    ("G_MS_0315_BT_Tau_Sen", "3-15 battle conversation"),
    ("G_0407e_セネリオ会話", "4-7e: Soren conversation"),
    ("G_0303_３兄弟会話", "3-3: the three brothers' conversation"),
    ("G_0111_漆黒出撃", "1-11: the Black Knight sorties"),
    ("G_0308_漆黒引き分け", "3-8: draw with the Black Knight"),
    ("G_reserve_for_talk0", "Reserved (talk)"),
    ("G_0407_ユンヌの加護", "4-7: Yune's protection"),
)
FLAG_GLOSSES_FE10 = {"gf_canceled": ENGINE_FLAG_GLOSSES["gf_canceled"],
                     "gf_gameover": ENGINE_FLAG_GLOSSES["gf_gameover"],
                     "gf_complete": ENGINE_FLAG_GLOSSES["gf_complete"],
                     **{f"gf_reserved{i}": "Reserved by the engine" for i in range(2, 7)},
                     **dict(VANILLA_GLOBAL_FLAGS_FE10)}


@dataclass(frozen=True)
class FlagTable:
    """One game's flag table: size, the engine's own flags, vanilla globals."""

    slot_count: int
    engine_flags: tuple
    vanilla_globals: tuple  # ((name, gloss), ...) in RegistGlobalFlags order
    glosses: dict
    reserved_global: Optional[str] = None


FE9_FLAGS = FlagTable(SLOT_COUNT, ENGINE_FLAGS, VANILLA_GLOBAL_FLAGS, FLAG_GLOSSES, RESERVED_GLOBAL)
FE10_FLAGS = FlagTable(128, ENGINE_FLAGS_FE10, VANILLA_GLOBAL_FLAGS_FE10, FLAG_GLOSSES_FE10)


def flag_table(dialect="fe9") -> FlagTable:
    """The flag table of a script dialect (a :class:`~.cmb.model.Dialect` or its name)."""
    name = dialect if isinstance(dialect, str) else getattr(dialect, "name", "fe9")
    return FE10_FLAGS if name == "fe10" else FE9_FLAGS


def flag_hash(name: str) -> int:
    """The engine's ``string_hash_multiplicative`` over the Shift-JIS bytes."""
    h = 0
    for b in name.encode("shift_jis"):
        h = (h * 37 + (b - 256 if b >= 128 else b)) & 0xFFFFFFFF
    return h


# -- which names a script registers ------------------------------------------

def _calls(node) -> Iterable[A.Call]:
    """Every call in source order, statements before nested blocks."""
    if isinstance(node, list):
        for item in node:
            yield from _calls(item)
    elif isinstance(node, A.Call):
        for arg in node.args:
            yield from _calls(arg)
        yield node
    elif hasattr(node, "__dataclass_fields__"):
        for name in node.__dataclass_fields__:
            if name != "line":
                yield from _calls(getattr(node, name))


def registrations(module: A.Module, entry: str, native: str) -> list[str]:
    """Names passed to ``native`` (``"regist"`` or ``"global"``) in the order the
    game runs them from ``entry``, following calls into the module's own
    functions (each function once, as a straight-line pass - vanilla never
    registers conditionally)."""
    funcs = {fd.name: fd for fd in module.functions}
    seen: set[str] = set()
    out: list[str] = []

    def walk(name: str) -> None:
        if name in seen or name not in funcs:
            return
        seen.add(name)
        for call in _calls(funcs[name].body):
            if call.name == native and call.args and isinstance(call.args[0], A.Str):
                out.append(call.args[0].value)
            elif isinstance(call.name, str) and not call.extern:
                walk(call.name)

    walk(entry)
    return out


@dataclass
class Registration:
    """One ``regist``/``global`` call, where the game runs it."""

    name: str
    function: str  # the function holding the call
    line: int  # 1-based source line of the call statement


def registration_sites(module: A.Module, entry: str, native: str) -> list[Registration]:
    """Like :func:`registrations`, with each call's function and line."""
    funcs = {fd.name: fd for fd in module.functions}
    seen: set[str] = set()
    out: list[Registration] = []

    def walk_statements(fname: str, stmts: list) -> None:
        for stmt in stmts:
            for call in _calls(stmt):
                if call.name == native and call.args and isinstance(call.args[0], A.Str):
                    out.append(Registration(call.args[0].value, fname, stmt.line))
                elif isinstance(call.name, str) and not call.extern:
                    walk(call.name)

    def walk(name: str) -> None:
        if name in seen or name not in funcs:
            return
        seen.add(name)
        walk_statements(name, funcs[name].body)

    walk(entry)
    return out


def _call_source(native: str, name: str) -> str:
    from .cmb.decompiler import quote

    if native == "global":
        return f'extern("global", {quote(name)})'
    return f"{native}({quote(name)})"


def append_registration(source: str, entry: str, native: str, name: str) -> str:
    """Add ``native(name)`` after the last registration ``entry`` runs, so every
    existing flag keeps its slot. The line goes into ``entry`` itself, after
    the last statement that registers (directly or through a called
    function); with none, it becomes ``entry``'s first statement."""
    from .cmb.parser import parse

    module = parse(source)
    fd = next((f for f in module.functions if f.name == entry), None)
    if fd is None:
        raise ValueError(f"the script has no {entry}() function")
    names = {f.name for f in module.functions}
    anchor = None
    for stmt in fd.body:
        for call in _calls(stmt):
            if call.name == native or (isinstance(call.name, str) and not call.extern and call.name in names
                                       and registrations(module, call.name, native)):
                anchor = stmt
    lines = source.split("\n")
    if anchor is not None:
        at = anchor.line  # insert after this 1-based line
        indent = lines[at - 1][:len(lines[at - 1]) - len(lines[at - 1].lstrip())]
    else:
        at = fd.line  # right after the def line
        first = fd.body[0].line if fd.body else fd.line + 1
        body_line = lines[first - 1] if first - 1 < len(lines) else "    "
        indent = body_line[:len(body_line) - len(body_line.lstrip())] or "    "
    lines.insert(at, indent + _call_source(native, name))
    return "\n".join(lines)


def rename_registration(source: str, site: Registration, old: str, new: str) -> str:
    """Rename the flag registered on ``site.line`` (keeps its slot)."""
    from .cmb.decompiler import quote

    lines = source.split("\n")
    line = lines[site.line - 1]
    if quote(old) not in line:
        raise ValueError(f"line {site.line} does not register {old!r}")
    lines[site.line - 1] = line.replace(quote(old), quote(new), 1)
    return "\n".join(lines)


def flag_uses(module: A.Module) -> dict[str, list[tuple[str, str]]]:
    """Flag name -> ``(function, native)`` for every literal ``set``/``get``/
    ``clr``/``regist``/``global`` call and every talk/battle/base-talk label."""
    uses: dict[str, list[tuple[str, str]]] = {}
    for fd in module.functions:
        for call in _calls(fd.body):
            if call.name in ("set", "get", "clr", "regist", "global") and call.args and \
                    isinstance(call.args[0], A.Str):
                uses.setdefault(call.args[0].value, []).append((fd.name, call.name))
        for d in fd.decorators:
            label = d.kwargs.get("name") if d.name in ("on_talk", "on_battle") else \
                d.kwargs.get("flag") if d.name == "on_base_talk" else None
            if isinstance(label, A.Str):
                uses.setdefault(label.value, []).append((fd.name, "trigger"))
    return uses


def check_flag_name(name: str, taken: Iterable[str]) -> Optional[str]:
    """Why ``name`` can't be a new flag, or ``None``."""
    if not name:
        return "the name is empty"
    try:
        name.encode("shift_jis")
    except UnicodeEncodeError:
        return "the game stores names in Shift-JIS; this name has characters it can't encode"
    if '"' in name or "\\" in name or "\n" in name:
        return "quotes, backslashes and line breaks are not allowed"
    if name in set(taken):
        return f"{name!r} is already registered"
    return None


def exported_functions(module: A.Module) -> dict[str, int]:
    """Name -> argument count of every function a script exports (what other
    scripts can call by name)."""
    out = {}
    for fd in module.functions:
        for d in fd.decorators:
            if d.name == "export":
                name = d.args[0].value if d.args and isinstance(d.args[0], A.Str) else fd.name
                out[name] = len(fd.params)
    return out


def global_flags(startup: A.Module, table: FlagTable = FE9_FLAGS) -> list[str]:
    """Global flag names in slot order (0..), engine flags first."""
    return list(table.engine_flags) + registrations(startup, "RegistGlobalFlags", "global")


def global_flags_vanilla(table: FlagTable = FE9_FLAGS) -> list[str]:
    return list(table.engine_flags) + [name for name, _ in table.vanilla_globals]


def global_flags_from_cmb(startup_cmb: Path) -> list[str]:
    """Global flag names in slot order from a (possibly modded) ``startup.cmb``."""
    from .cmb import decompile, read_cmb_path
    from .cmb.parser import parse

    script = read_cmb_path(startup_cmb)
    source, _stats = decompile(script, startup_cmb.name)
    return global_flags(parse(source), flag_table(script.dialect))


def local_flags(chapter: A.Module) -> list[str]:
    """Chapter-local flag names in registration order (slot 95 downward)."""
    return registrations(chapter, "Startup", "regist")


def slot_names(globals_: list[str], locals_: list[str], slot_count: int = SLOT_COUNT) -> list[Optional[str]]:
    """Slot -> name, as the table looks after a chapter's ``Startup``. Locals
    that don't fit are dropped, as the engine does."""
    slots: list[Optional[str]] = [None] * slot_count
    for i, name in enumerate(globals_[:slot_count]):
        slots[i] = name
    top = slot_count - 1
    for name in locals_:
        while top >= 0 and slots[top] is not None:
            top -= 1
        if top < 0:
            break
        slots[top] = name
    return slots


def capacity_problem(global_count: int, local_count: int, slot_count: int = SLOT_COUNT) -> Optional[str]:
    """Why a chapter's registrations don't fit the table, or ``None``.

    The reset walks down from the top slot until it finds an empty slot, so
    at least one slot must stay free or the next chapter start also wipes
    every global flag's name.
    """
    free = slot_count - global_count - local_count
    if free >= 1:
        return None
    if free == 0:
        return (f"{global_count} global + {local_count} local flags fill all {slot_count} slots: "
                "the chapter-start reset would also unregister every global flag")
    return (f"{global_count} global + {local_count} local flags need {-free} more slot(s) than the "
            f"table's {slot_count}: the last regist() calls are silently ignored")


# -- save files ---------------------------------------------------------------

GCI_HEADER_SIZE = 0x40
BLOCK_OFFSETS = (0x2000, 0x6000, 0xA000, 0xE000, 0x12000, 0x16000, 0x1A000, 0x20000)
SAVE_MAGIC = 0x4645384A  # "FE8J"
FLAGS_OFFSET = 0x164  # block + 0xB8 (payload, "BMST" tag) + 4 + 0xA8
CRC_START = 0x70
CRC_EXEMPT = 0x12345678


@dataclass
class SaveBlock:
    offset: int  # from the start of the .gci file
    size: int
    sequence: int
    save_kind: int
    save_mode: int
    chapter_map: str  # "bmapNN" the block resumes into
    crc_ok: bool

    @property
    def flags_offset(self) -> int:
        return self.offset + FLAGS_OFFSET


def _block_at(data: bytes, offset: int) -> Optional[SaveBlock]:
    b = data[offset:]
    if len(b) < 0x200:
        return None
    magic, _version, seq, size, crc = struct.unpack(">5I", b[0x40:0x54])
    if magic != SAVE_MAGIC or b[0xB8:0xBC] != b"BMST" or not 0x200 <= size <= len(b):
        return None
    ok = crc == CRC_EXEMPT or b[0x60] == 1 or zlib.crc32(b[CRC_START:size]) == crc
    # current_chapter_name_buffer (party_data+0x504) is the 0x18 bytes before the 8 pad bytes
    # that end the BMST payload, 0x140+0x18 bytes after the flags.
    name_at = FLAGS_OFFSET + BIT_BYTES + 0x140
    chapter = b[name_at:name_at + 0x18].split(b"\0")[0].decode("ascii", "replace")
    return SaveBlock(offset, size, seq, b[0x60], b[0x65], chapter, ok)


def save_blocks(gci: bytes) -> list[SaveBlock]:
    """Every populated save block of a Path of Radiance ``.gci``."""
    blocks = []
    for rel in BLOCK_OFFSETS:
        block = _block_at(gci, GCI_HEADER_SIZE + rel)
        if block is not None:
            blocks.append(block)
    return blocks


def read_flag_bits(gci: bytes, block: SaveBlock) -> list[bool]:
    raw = gci[block.flags_offset:block.flags_offset + BIT_BYTES]
    return [bool(raw[i >> 3] & (1 << (i & 7))) for i in range(SLOT_COUNT)]


def write_flag_bits(gci: bytearray, block: SaveBlock, bits: list[bool]) -> None:
    """Store ``bits`` (96 booleans) in ``block`` and re-sign it."""
    raw = bytearray(BIT_BYTES)
    for i, on in enumerate(bits[:SLOT_COUNT]):
        if on:
            raw[i >> 3] |= 1 << (i & 7)
    gci[block.flags_offset:block.flags_offset + BIT_BYTES] = raw
    refresh_crc(gci, block)


def refresh_crc(gci: bytearray, block: SaveBlock) -> None:
    b = block.offset
    crc = zlib.crc32(bytes(gci[b + CRC_START:b + block.size]))
    gci[b + 0x50:b + 0x54] = crc.to_bytes(4, "big")
    block.crc_ok = True


# -- command line ---------------------------------------------------------------

def _chapter_script(scripts: Path, chapter_map: str) -> Optional[Path]:
    """``bmapNN`` (and ``bmapNN_2``...) runs ``Scripts/CNN.cmb``."""
    if chapter_map.startswith("bmap") and chapter_map[4:6].isdigit():
        path = scripts / f"C{int(chapter_map[4:6]):02d}.cmb"
        return path if path.exists() else None
    return None


def _slot_labels(scripts: Optional[Path], block: SaveBlock) -> list[Optional[str]]:
    if scripts is None:
        return slot_names(global_flags_vanilla(), [])
    from .cmb import decompile, read_cmb_path
    from .cmb.parser import parse

    globals_ = global_flags_from_cmb(scripts / "startup.cmb")
    chapter = _chapter_script(scripts, block.chapter_map)
    locals_ = []
    if chapter is not None:
        locals_ = local_flags(parse(decompile(read_cmb_path(chapter), chapter.name)[0]))
    return slot_names(globals_, locals_)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(prog="python -m fe_modding.formats.event_flags",
                                 description="Show or change script flags in a Path of Radiance .gci save.")
    ap.add_argument("gci", type=Path)
    ap.add_argument("--scripts", type=Path, help="Scripts/ folder, to name the chapter-local slots")
    ap.add_argument("--block", type=lambda s: int(s, 0), help="block offset (default: newest block)")
    ap.add_argument("--set", nargs="+", default=[], metavar="FLAG", help="slot number or flag name to turn on")
    ap.add_argument("--clr", nargs="+", default=[], metavar="FLAG", help="slot number or flag name to turn off")
    ap.add_argument("-o", "--output", type=Path, help="where to write the edited save (default: in place)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    data = bytearray(args.gci.read_bytes())
    blocks = save_blocks(bytes(data))
    if not blocks:
        print("no Path of Radiance save blocks found", file=sys.stderr)
        return 1
    for b in blocks:
        print(f"block 0x{b.offset:05x}  size 0x{b.size:x}  seq {b.sequence:5d}  kind {b.save_kind}  "
              f"mode {b.save_mode}  {b.chapter_map:<10} crc {'ok' if b.crc_ok else 'BAD'}")
    block = max(blocks, key=lambda b: b.sequence)
    if args.block is not None:
        block = next(b for b in blocks if b.offset == args.block)
    labels = _slot_labels(args.scripts, block)
    bits = read_flag_bits(bytes(data), block)

    def slot_of(token: str) -> int:
        if token.isdigit():
            return int(token)
        return labels.index(token)

    for token in args.set:
        bits[slot_of(token)] = True
    for token in args.clr:
        bits[slot_of(token)] = False
    print(f"\nflags of block 0x{block.offset:05x} ({block.chapter_map}):")
    for i, on in enumerate(bits):
        if on or (args.set or args.clr) and labels[i]:
            name = labels[i] or "(no name in this chapter)"
            gloss = FLAG_GLOSSES.get(labels[i] or "", "")
            print(f"  {i:2d} {'ON ' if on else 'off'} {name}  {gloss}".rstrip())
    if args.set or args.clr:
        write_flag_bits(data, block, bits)
        (args.output or args.gci).write_bytes(bytes(data))
        print(f"\nwrote {args.output or args.gci}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
