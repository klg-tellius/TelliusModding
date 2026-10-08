"""Per-format handlers of the disc-wide byte-coverage map (:mod:`coverage`).

Each handler places every byte of one file. A field gets the status its
topic note gives it (``research/*.md``); when a note changes a field's
confidence, the handler here changes with it. Formats the app rebuilds byte
for byte are checked by a round trip first: a file that does not rebuild is
reported as a failure instead of being counted as decoded.
"""

from __future__ import annotations

import io
import struct

from . import lz10, pak
from .common import HEADER_SIZE, SECTION_TABLE_SENTINEL
from .coverage import (DECODED, PADDING, PLAUSIBLE, UNCLASSIFIED, UNDECODED, UNREAD, FileCoverage, Walker,
                       _base, _ext, _u16, _u32, handles)



def _roundtrip(cov: FileCoverage, rebuilt: bytes) -> None:
    if rebuilt != cov.data:
        raise ValueError("does not rebuild byte for byte")


# ------------------------------------------------------------------ shared containers

def hsdarc(cov: FileCoverage) -> list[tuple[str, int, int]]:
    """The relocatable-resource container (``CONTAINER_FORMATS.md`` §2): mark
    the header, relocation list, export table and names; return the exports
    as ``(name, start, end)`` with absolute offsets, sorted by address."""
    data = cov.data
    size, data_size, reloc_count, export_count = struct.unpack_from(">4I", data, 0)
    data_end = HEADER_SIZE + data_size
    table = data_end + 4 * reloc_count
    names = table + 8 * export_count
    cov.mark(0, 0x14, DECODED)
    # +0x14 is read by no load found (FE8DATA_NOTES, header); +0x18..+0x1F are
    # written in RAM by load_relocatable_resource (stamp and flag), zero on disc.
    cov.mark(0x14, 4, UNREAD, "header +0x14")
    cov.mark(0x18, 8, DECODED)
    cov.mark(data_end, len(data) - data_end, DECODED)
    exports = []
    for i in range(export_count):
        address, name_offset = struct.unpack_from(">II", data, table + 8 * i)
        end = data.find(b"\0", names + name_offset)
        exports.append((data[names + name_offset:end].decode("shift_jis", "replace"), HEADER_SIZE + address))
    exports.sort(key=lambda e: e[1])
    return [(name, start, exports[i + 1][1] if i + 1 < len(exports) else data_end)
            for i, (name, start) in enumerate(exports)]


def labeled_sections(cov: FileCoverage) -> list[tuple[str, int, int]]:
    """The "labeled section" container of ``map.bin``/``dispos``/``shop``: a
    sentinel-terminated section table. Same marks as :func:`hsdarc`."""
    data = cov.data
    _size, data_size, pointer_count = struct.unpack_from(">3I", data, 0)
    data_end = HEADER_SIZE + data_size
    cov.mark(0, HEADER_SIZE, DECODED)
    cov.mark(data_end, len(data) - data_end, DECODED)
    table = data_end + 4 * pointer_count
    entries = []
    pos = table
    while pos + 8 <= len(data):
        address, name_offset = struct.unpack_from(">II", data, pos)
        if address >= SECTION_TABLE_SENTINEL:
            break
        entries.append((address + HEADER_SIZE, name_offset))
        pos += 8
    names = pos
    out = []
    for address, name_offset in entries:
        end = data.find(b"\0", names + name_offset)
        out.append((data[names + name_offset:end].decode("shift_jis", "replace"), address))
    out.sort(key=lambda e: e[1])
    return [(n, a, out[i + 1][1] if i + 1 < len(out) else data_end) for i, (n, a) in enumerate(out)]


def strings_and_padding(cov: FileCoverage, start: int, end: int) -> None:
    """Inside ``[start, end)``: unplaced NUL-terminated text is a string
    (pools hold only strings), unplaced zeros padding."""
    data, st = cov.data, cov.status
    i = start
    while i < end:
        if st[i] != UNCLASSIFIED:
            i += 1
            continue
        if data[i] == 0:
            cov.mark(i, 1, PADDING)
            i += 1
            continue
        j = data.find(b"\0", i, end)
        j = end if j < 0 else j + 1
        cov.mark(i, j - i, DECODED)
        i = j


# ------------------------------------------------------------------ containers

def _is_lz10(name: str, data: bytes) -> bool:
    return not name.endswith("#") and _ext(name) in ("cmp", "cms") and data[:1] == b"\x10"


@handles("lz10", _is_lz10)
def lz10_stream(cov: FileCoverage, walker: Walker) -> None:
    inner = lz10.decompress(cov.data)
    cov.mark(0, len(cov.data), DECODED)
    walker.child(cov.name + "#", inner)


@handles("pak", lambda name, data: data[:4] == b"pack")
def pak_archive(cov: FileCoverage, walker: Walker) -> None:
    data = cov.data
    entries = pak.read_pak_entries(data)
    cov.mark(0, 6, DECODED)
    cov.zero(6, 2, "header +6")
    for i, entry in enumerate(entries):
        base = 8 + 16 * i
        cov.zero(base, 4, "entry +0")
        cov.mark(base + 4, 12, DECODED)
        cov.mark(entry.offset, entry.length, DECODED)
        walker.child(f"{cov.name.rstrip('#')}:{entry.name}", pak.read_pak_file_content(data, entry))
    names_start = 8 + 16 * len(entries)
    names_end = min((e.offset for e in entries), default=len(data))
    strings_and_padding(cov, names_start, names_end)
    cov.fill(PADDING, only_zero=True)


# ------------------------------------------------------------------ textures

TPL_MAGIC = b"\x00\x20\xaf\x30"


@handles("tpl", lambda name, data: data[:4] == TPL_MAGIC)
def tpl_file(cov: FileCoverage, walker: Walker) -> None:
    """GX texture palette: header, image table, 0x24-byte image headers,
    0x0C-byte palette headers, texel data with its mip levels, palette data
    (public GX format)."""
    from .tpl import TplImageInfo

    data = cov.data
    count, table = _u32(data, 4), _u32(data, 8)
    cov.mark(0, 12, DECODED)
    cov.mark(table, 8 * count, DECODED)
    for i in range(count):
        image, palette = struct.unpack_from(">II", data, table + 8 * i)
        height, width, fmt, texels = struct.unpack_from(">HHII", data, image)
        cov.mark(image, 0x24, DECODED)
        # Mip levels follow the base level: header +0x21 min LOD, +0x22 max LOD.
        min_lod, max_lod = data[image + 0x21], data[image + 0x22]
        pos = texels
        for level in range(max(1, max_lod - min_lod + 1)):
            w, h = max(1, width >> level), max(1, height >> level)
            if fmt == 1:  # I8: 8x4 tiles of 32 bytes (zmap/common.tpl; tpl.py has no codec for it yet)
                length = ((w + 7) // 8) * ((h + 3) // 4) * 32
            else:
                length = TplImageInfo(i, w, h, fmt, pos, palette, 0, 0, 0, 0, 0.0).data_length
            cov.mark(pos, length, DECODED)
            pos += length
        if palette:
            entries, _unpacked, _pad, _fmt, pal_data = struct.unpack_from(">HBBII", data, palette)
            cov.mark(palette, 12, DECODED)
            cov.mark(pal_data, 2 * entries, DECODED)
    cov.fill(PADDING, only_zero=True)


# ------------------------------------------------------------------ models

def _gs_material_texture(cov: FileCoverage, rec: int, i: int) -> None:
    """28-byte material texture record (GRAPHICS_NOTES, materials): +0 bit 0
    identity texture matrix, bit 5 sampler override; +4 tex_id; +8..+0x1B the
    translation/scale/rotation floats of the non-identity branch."""
    cov.bits(rec, 2, known=0x0021, name="texture.flags0")
    cov.mark(rec + 2, 2, UNDECODED, "texture.flags1")
    cov.mark(rec + 4, 2, DECODED)
    cov.mark(rec + 6, 2, UNDECODED, "texture +6")
    cov.mark(rec + 8, 0x14, DECODED)


@handles("gs", lambda name, data: _ext(name) == "gs")
def gs_file(cov: FileCoverage, walker: Walker) -> None:
    from . import gs_file as gsf

    data = cov.data
    _roundtrip(cov, gsf.write_gs(gsf.read_gs(data)))
    _size, reloc_offset, reloc_count, n_exports, n_imports = struct.unpack_from(">5I", data, 0)
    cov.mark(0, 0x14, DECODED)
    cov.mark(0x14, 4, UNREAD, "header +0x14")  # same loader as every relocatable resource
    cov.mark(0x18, 8, DECODED)
    B = HEADER_SIZE
    body = data[B:]
    cov.mark(B, 8, DECODED)  # root name pointer, export date
    cov.mark(B + 8, 4, UNREAD, "model_id (id/hash?)")
    cov.mark(B + 0x0C, 0x18, UNREAD, "bbox")
    cov.mark(B + 0x24, 0x3B, DECODED)  # addrs, nums, fraction bytes
    cov.zero(B + 0x5F, 5, "header pad")
    addrs = struct.unpack_from(">10I", body, 0x24)
    nums = struct.unpack_from(">8H", body, 0x4C)
    for slot, stride in ((0, 6), (1, 3), (2, 4), (3, 4)):
        if addrs[slot]:
            cov.mark(B + addrs[slot], stride * nums[slot], DECODED)
    for i in range(nums[4] if addrs[4] else 0):
        m = B + addrs[4] + 0x20 * i
        cov.mark(m, 0x20, DECODED)  # name, texture count and pointer, color0 (x1.25 at load)
        cov.mark(m + 4, 2, UNDECODED, "material +4/+5")
        cov.mark(m + 7, 1, UNDECODED, "material +7")
        cov.mark(m + 0x0C, 8, PLAUSIBLE, "material color1/color2")
        cov.zero(m + 0x18, 8, "material +0x18 trailer")
        tex_ptr, tex_count = _u32(body, addrs[4] + 0x20 * i + 0x14), body[addrs[4] + 0x20 * i + 6]
        for t in range(tex_count if tex_ptr else 0):
            _gs_material_texture(cov, B + tex_ptr + 0x1C * t, t)
    if addrs[5] and addrs[5] != gsf.IMPORTED_POINTER:
        for i in range(nums[5]):
            m = B + addrs[5] + 0x24 * i
            cov.mark(m, 4, DECODED)
            cov.mark(m + 4, 0x18, UNREAD, "mesh bounds")
            cov.mark(m + 0x1C, 2, DECODED)
            cov.mark(m + 0x1E, 6, UNDECODED, "mesh extra (3 x u16)")
    for slot in (6, 7, 8):
        ptr = addrs[slot]
        while ptr:
            c = B + ptr
            cov.mark(c, 0x20, DECODED)
            cov.zero(c + 0x0E, 2, "shape +0x0E (runtime slot)")
            # flags: 0x0008/0x0200 undecoded; 0x6000 = (list index + 1) << 13, no reader
            cov.bits(c + 8, 2, known=0xFFFF & ~0x6208, plausible=0x6000, name="shape.flags")
            if body[ptr + 8] & 0x60 and not body[ptr + 8] & 0x02:
                cov.mark(c + 8, 1, UNREAD, "shape.flags 0x6000 (list index)")
            if _u32(body, ptr + 0x10) >> 29:
                cov.mark(c + 0x10, 1, DECODED)  # billboard mode bits (meaning per mode open)
                cov.mark(c + 0x10, 1, PLAUSIBLE, "shape.attr_mask billboard mode")
            dl_ptr, dl_size, bs_ptr = struct.unpack_from(">III", body, ptr + 0x14)
            cov.mark(B + dl_ptr, dl_size, DECODED)
            if bs_ptr:
                cov.mark(B + bs_ptr, 2 + body[bs_ptr + 1], DECODED)
            ptr = _u32(body, ptr + 4)
    if addrs[9]:
        c = addrs[9]
        w_off, v_off, n_w, n_v = struct.unpack_from(">IIHH", body, c)
        cov.mark(B + c, 0x0E, DECODED)
        cov.mark(B + c + 0x0E, 2, UNREAD, "composite.shared_record_count")
        cov.mark(B + c + w_off, 0x18 * n_w, DECODED)
        cov.mark(B + c + v_off, 0x0C * n_v, DECODED)
    reloc = B + reloc_offset
    cov.mark(reloc, len(data) - reloc, DECODED)  # relocations, symbols, names
    strings_and_padding(cov, B, reloc)


@handles("skeleton", lambda name, data: _ext(name) == "g")
def skeleton_file(cov: FileCoverage, walker: Walker) -> None:
    """``.g``: 16-byte header, 244-byte bones, name pool (GRAPHICS_NOTES,
    skeleton). Flags: the transform-term bits ``0x8``-``0x800`` and ``0x1``
    are decoded, ``0x2``/``0x4`` are not."""
    from . import skeleton

    data = cov.data
    _roundtrip(cov, skeleton.write_skeleton_file(skeleton.read_skeleton_file(data)))
    pool, count = _u32(data, 4), _u32(data, 8)
    cov.zero(0, 4, "header +0")
    cov.mark(4, 12, DECODED)
    for i in range(count):
        rec = 0x10 + 0xF4 * i
        cov.mark(rec, 0xF4, DECODED)
        cov.bits(rec + 0x0C, 4, known=0xFFFFFFFF & ~0x6, name="bone.flags")
    cov.mark(pool, len(data) - pool, DECODED)


#: Event codes with an engine meaning (animation.py): loop markers, battle flag, camera/light effects.
GA_EVENT_KNOWN = {3, 4, 0x1C, 0x1D, 0x28, 0x29}


@handles("animation", lambda name, data: _ext(name) == "ga")
def ga_file(cov: FileCoverage, walker: Walker) -> None:
    from . import animation

    data = cov.data
    anim = animation.read_animation_bytes(data)
    _roundtrip(cov, animation.write_animation(anim))
    words = anim.header.words
    cov.mark(0, 0x30, DECODED)
    for w in (1, 2, 10):
        cov.zero(4 * w, 4, f"header word {w}")
    cov.mark(words[8], words[9] - words[8], DECODED)
    for i in range((words[11] - words[9]) // 12):
        rec = words[9] + 12 * i
        cov.mark(rec, 12, DECODED)
        cov.zero(rec + 3, 1, "curve.scale low byte")
        cov.zero(rec + 8, 2, "curve +8")
    footer = words[0]
    cov.mark(words[11], (footer or len(data)) - words[11], DECODED)
    if not footer:
        return
    cov.mark(footer, 36, DECODED)
    cov.zero(footer + 36, 4, "footer pad")
    slots = struct.unpack_from(">9I", data, footer)
    used = sorted((a, s) for s, a in enumerate(slots) if a)
    water = "water" in cov.name.lower()
    for k, (addr, slot) in enumerate(used):
        end = used[k + 1][0] if k + 1 < len(used) else len(data)
        if slot == 0:
            _ga_events(cov, addr, end)
        elif slot == 3 and water:
            cov.mark(addr, end - addr, DECODED)  # map water scroll table (GRAPHICS_NOTES, "Map water")
        else:
            cov.mark(addr, end - addr, UNDECODED, f"footer slot {slot}")
    cov.fill(PADDING, only_zero=True)


def _ga_events(cov: FileCoverage, start: int, end: int) -> None:
    data = cov.data
    count = _u16(data, start)
    cov.mark(start, 8 + 2 * count, DECODED)
    pos = start + 8 + 2 * count
    for _ in range(count):
        n = _u16(data, pos + 2)
        cov.mark(pos, 4, DECODED)
        for c in range(n):
            code = _u16(data, pos + 4 + 2 * c)
            if code in GA_EVENT_KNOWN:
                cov.mark(pos + 4 + 2 * c, 2, DECODED)
            elif code == 1:
                cov.mark(pos + 4 + 2 * c, 2, PLAUSIBLE, "event code 1 (hit frame)")
            elif code >= 1000:
                cov.mark(pos + 4 + 2 * c, 2, PLAUSIBLE, "event code >= 1000 (sound id)")
            else:
                cov.mark(pos + 4 + 2 * c, 2, UNDECODED, f"event code {code}")
        pos += 4 + 2 * n
    if pos < end:
        cov.zero(pos, end - pos, "event track tail")


# ------------------------------------------------------------------ maps

@handles("map.bin", lambda name, data: _base(name) == "map.bin")
def map_bin(cov: FileCoverage, walker: Walker) -> None:
    """Chapter ``map.bin`` (CHAPTER_DATA_NOTES §5), and the battle-scenery
    ``zbg/*/*.cmp:map.bin`` whose sections carry a ``B`` suffix
    (``mapcapacityB`` ... ``maplightB``, no panel or link layers):
    ``load_map_data`` (``0x80041514``) reads those in a second pass with the
    same record code, so the same field rules apply."""
    data = cov.data
    found = labeled_sections(cov)
    suffix = "B" if any(n == "mapcapacityB" for n, _s, _e in found) else ""
    sections = dict((n[: len(n) - len(suffix)] if suffix and n.endswith(suffix) else n, (s, e)) for n, s, e in found)
    cap = sections["mapcapacity"][0]
    x_size, y_size, n_desc, n_inst = struct.unpack_from(">4H", data, cap)
    for name, (start, end) in sections.items():
        if name == "mapcapacity":
            cov.mark(start, 12, DECODED)
        elif name == "mapbuilddesc":
            for i in range(n_desc):
                r = start + 32 * i
                cov.mark(r, 32, DECODED)
                # flag word +0x18..+0x1B (CHAPTER_DATA_NOTES): a bits 7-6 base terrain;
                # b bits 4-2 battle-goal type (sub-values plausible), bit 5 roof and bit 0
                # rock plausible; c bit 1 animated, bits 4-7 plausible, bit 3 roof test.
                cov.bits(r + 0x18, 1, known=0xC0, name="flag_bits_a")
                cov.bits(r + 0x19, 1, known=0x00, plausible=0x3D, name="flag_bits_b")
                cov.bits(r + 0x1A, 1, known=0x0A, plausible=0xF0, name="flag_bits_c")
                cov.zero(r + 0x1B, 1, "effect_type", nonzero=UNDECODED)
        elif name == "mapbuildinst":
            cov.mark(start, 12 * n_inst, DECODED)  # footprint x2..end_y2: strong evidence
        elif name.startswith("panelindex"):
            cov.mark(start, 2 * x_size * y_size, DECODED)
        elif name.startswith("uniquepanel"):
            cov.mark(start, end - start, DECODED)
        elif name == "maplight":
            cov.mark(start, 12, DECODED)
            cov.mark(start + 1, 2, UNDECODED, "maplight +1/+2")
            cov.zero(start + 9, 3, "maplight +9")
        elif name == "mapfog":
            cov.mark(start, 7, DECODED)
            cov.zero(start + 7, 1, "mapfog +7")
        elif name == "mapgrid":
            cov.mark(start, 4, DECODED)
            cov.mark(start, 1, UNDECODED, "mapgrid +0")
        elif name == "mapextra":
            cov.mark(start, 6, DECODED)
            cov.zero(start + 6, 2, "mapextra +6")
            # tail word: 0x04/0x20 material callbacks and 0x10000000 roof test decoded;
            # 0x10 callback FUN_800EF1C0 and the 0xC0000/0x1F00000 mode fields not.
            cov.bits(start + 8, 4, known=0x10000024, name="mapextra flags")
        elif name.startswith("maplink"):
            count = _u16(data, start)
            cov.mark(start, 2, DECODED)
            for i in range(count):
                e = start + 2 + 3 * i
                cov.mark(e, 2, DECODED)
                # bits 0-3 passability openings decoded; maplinkAt writes bits 8-11
                # from its low nibble; the high nibble of maplink/maplinkAt is open.
                cov.bits(e + 2, 1, known=0x0F, name=f"{name} value")
        else:
            cov.mark(start, end - start, UNDECODED, f"section {name}")
    strings_and_padding(cov, HEADER_SIZE, HEADER_SIZE + _u32(data, 4))


@handles("dispos", lambda name, data: _base(name).startswith("dispos_"))
def dispos(cov: FileCoverage, walker: Walker) -> None:
    """Deployment (CHAPTER_DATA_NOTES §5.1): every field placed; flag 0x10/0x20
    are the AI Door/Chest Key bits."""
    from . import dispo

    _roundtrip(cov, dispo.build_dispo(dispo.parse_dispo(cov.data)))
    cov.fill(DECODED)


# ------------------------------------------------------------------ data tables

@handles("FE8Data.bin", lambda name, data: _base(name) == "fe8data.bin")
def fe8data_file(cov: FileCoverage, walker: Walker) -> None:
    from . import fe8data_coverage as fc

    # fe8data_coverage's "reserved" = no load found in main.dol; the live
    # watch that would make it reserved here has not run yet.
    status = {fc.DECODED: DECODED, fc.PLAUSIBLE: PLAUSIBLE, fc.UNDECODED: UNDECODED,
              fc.RESERVED: UNREAD, fc.PADDING: PADDING}
    for span in fc.build_coverage(cov.data).spans():
        cov.mark(span.start, span.end - span.start, status[span.status], f"{span.section}.{span.name}")


def _is_fe10_container(name: str, data: bytes) -> bool:
    return name.endswith(".cms#") and len(data) >= HEADER_SIZE and _u32(data, 0) == len(data)


@handles("fe10 container", _is_fe10_container)
def fe10_container(cov: FileCoverage, walker: Walker) -> None:
    """Radiant Dawn's decompressed ``.cms`` data files (``FE10Data``, ``FE10Anim``, ``cp_data``...):
    the same relocatable container as ``FE8Data.bin``. The container structure, every listed pointer
    and the text it points at are decoded; each exported section's records are not (their layouts
    belong to the format phases of the Radiant Dawn plan)."""
    data = cov.data
    sections = hsdarc(cov)
    data_end = HEADER_SIZE + _u32(data, 4)
    for name, start, end in sections:
        cov.mark(start, end - start, UNDECODED, f"{name} records")
    count = _u32(data, 8)
    for i in range(count):
        field = HEADER_SIZE + _u32(data, data_end + 4 * i)
        if field + 4 > data_end:
            continue
        cov.mark(data_end + 4 * i, 4, DECODED)
        cov.mark(field, 4, DECODED)
        target = HEADER_SIZE + _u32(data, field)
        if HEADER_SIZE <= target < data_end:
            end = data.find(b"\0", target, data_end)
            text = data[target:end] if end > target else b""
            if text and len(text) <= 256 and all(b >= 0x20 and b != 0x7F for b in text):
                cov.mark(target, end + 1 - target, DECODED)


@handles("FE8Anim.bin", lambda name, data: _base(name) == "fe8anim.bin")
def fe8anim(cov: FileCoverage, walker: Walker) -> None:
    sections = hsdarc(cov)
    start = sections[0][1]
    count = _u32(cov.data, start)
    cov.mark(start, 4 + 0x14 * count, DECODED)
    for i in range(count):
        r = start + 4 + 0x14 * i
        cov.zero(r + 0x0A, 1, "+0x0A")
        cov.mark(r + 0x0B, 1, UNREAD, "+0x0B")
    strings_and_padding(cov, start, sections[-1][2])


@handles("FE8Effect.bin", lambda name, data: _base(name) == "fe8effect.bin")
def fe8effect(cov: FileCoverage, walker: Walker) -> None:
    sections = hsdarc(cov)
    start = sections[0][1]
    count = _u32(cov.data, start)
    cov.mark(start, 4 + 12 * count, DECODED)
    for i in range(count):
        r = start + 4 + 12 * i
        cov.mark(r + 4, 1, PLAUSIBLE, "flags byte 0 (category enum)")
        cov.mark(r + 5, 1, PLAUSIBLE, "flags byte 1")
        cov.mark(r + 6, 1, PLAUSIBLE, "flags byte 2 (constant 5)")
        cov.zero(r + 7, 1, "flags byte 3")
    strings_and_padding(cov, start, sections[-1][2])


def _roundtrip_handler(module: str, parse: str, build: str):
    def handler(cov: FileCoverage, walker: Walker) -> None:
        mod = __import__(f"{__package__}.{module}", fromlist=[module])
        _roundtrip(cov, getattr(mod, build)(getattr(mod, parse)(cov.data)))
        cov.fill(DECODED)
    return handler


handles("cp_data.bin", lambda n, d: _base(n) == "cp_data.bin")(_roundtrip_handler("cp_data", "parse_cp_data", "build_cp_data"))
handles("shop", lambda n, d: _base(n).startswith("shopitem_"))(_roundtrip_handler("shop", "parse_shop", "build_shop"))
handles("soundroom.bin", lambda n, d: _base(n) == "soundroom.bin")(
    _roundtrip_handler("soundroom", "read_soundroom", "build_soundroom"))


@handles("facedata.bin", lambda name, data: _base(name) == "facedata.bin")
def facedata(cov: FileCoverage, walker: Walker) -> None:
    from . import face_data

    face_data.read_face_data(cov.data)
    cov.fill(DECODED)  # CONVERSATION_RENDERING: every byte decoded


def _is_rect(name: str, data: bytes) -> bool:
    base = _base(name)
    return base == "rect.bin" or base.startswith(("rectdesc", "rectbases", "rectunitlist", "rectfinale"))


@handles("rect", _is_rect)
def rect_file(cov: FileCoverage, walker: Walker) -> None:
    """``s/rect.bin`` and the ``window``/``ending`` rect files (RECT_NOTES)."""
    from . import rect

    data = cov.data
    _roundtrip(cov, rect.build_rect(rect.parse_rect(data)))
    for _name, start, _end in hsdarc(cov):
        cov.mark(start, 20, DECODED)
        cov.mark(start + 0x0D, 1, UNREAD, "descriptor +0x0D")
        count = data[start + 4]
        cov.mark(start + 20, 4 * count, DECODED)
        for i in range(count):
            layer = HEADER_SIZE + _u32(data, start + 20 + 4 * i)
            kind = data[layer]
            length = rect._layer_length(data, layer)
            cov.mark(layer, length, DECODED)
            if kind in (rect.KIND_QUAD, rect.KIND_COLOR_QUAD):
                cov.mark(layer + 0x11, 1, UNREAD, "quad layer +0x11 (overwritten at load)")
            elif kind == rect.KIND_TEXT:
                cov.mark(layer + 0x13, 1, UNREAD, "text layer +0x13")
            elif kind == rect.KIND_SEATS:
                for s in range(_u16(data, layer + 8)):
                    cov.mark(layer + rect.SEATS_HEADER_SIZE + rect.SEAT_SIZE * s + 7, 1, UNREAD,
                             "seat number")
    strings_and_padding(cov, HEADER_SIZE, HEADER_SIZE + _u32(data, 4))


@handles("tut_data", lambda name, data: _base(name).startswith("tut_data"))
def tut_data(cov: FileCoverage, walker: Walker) -> None:
    """Tutorial data (UNEXPLORED_SYSTEMS §10): TutDataHead (build time, author),
    three label tables, and TUT_DATA: a count then 24-byte rows whose bytes
    +1/+2/+4 key the browser's three groupings."""
    data = cov.data
    for name, start, end in labeled_sections(cov):
        if name == "TUT_DATA":
            count = _u32(data, start)
            cov.mark(start, 4, DECODED)
            for i in range(count):
                r = start + 4 + 24 * i
                cov.mark(r, 24, UNDECODED, "TUT_DATA row")
                for k in (1, 2, 4):
                    cov.mark(r + k, 1, PLAUSIBLE, f"TUT_DATA row +{k} (grouping key)")
        elif name in ("TutDataHead", "TUT_CHAPTER", "TUT_CATEGORY", "TUT_INITIAL"):
            cov.mark(start, end - start, DECODED)
        else:
            cov.mark(start, end - start, UNDECODED, f"section {name}")
    strings_and_padding(cov, HEADER_SIZE, HEADER_SIZE + _u32(data, 4))


@handles("client.bin", lambda name, data: _base(name) == "client.bin")
def client_bin(cov: FileCoverage, walker: Walker) -> None:
    """A GBA program (ARM branch, Nintendo logo, title ``FIREEMBLEM6``, code
    ``AFEJ01``): the image the game sends to a linked Game Boy Advance. The
    0xC0-byte cartridge header is the public GBA format; the program is not
    disassembled."""
    cov.mark(0, 0xC0, DECODED)
    cov.mark(0xC0, len(cov.data) - 0xC0, UNDECODED, "GBA program body (not disassembled)")


@handles("staffroll", lambda name, data: _base(name).startswith("staffroll"))
def staffroll(cov: FileCoverage, walker: Walker) -> None:
    for name, start, end in labeled_sections(cov):
        cov.mark(start, end - start, UNDECODED, f"section {name}")
    cov.fill(UNDECODED, "staffroll (never parsed)")


# ------------------------------------------------------------------ text and scripts

@handles("message", lambda name, data: _ext(name) == "m")
def message_file(cov: FileCoverage, walker: Walker) -> None:
    """A relocatable resource whose exports pair each message ID with its text
    (``message.engine_name_hash``). Every ``$`` control and markup is decoded
    (CONVERSATION_RENDERING); ``write_messages`` is a structural round trip
    only, so the bytes are placed here from the layout."""
    from . import message

    message.read_messages(io.BytesIO(cov.data))
    hsdarc(cov)
    strings_and_padding(cov, HEADER_SIZE, HEADER_SIZE + _u32(cov.data, 4))


@handles("cmb", lambda name, data: _ext(name) == "cmb")
def cmb_file(cov: FileCoverage, walker: Walker) -> None:
    """Event script (CHAPTER_DATA_NOTES, script layout; Radiant Dawn's bytecode
    differences in research/rd/SCRIPT_NOTES.md). Header +0x18 is the script
    compiler's build stamp, which the loader never reads (the codec picks the
    game's dialect from it); function record byte +0x0F is never read either."""
    from .cmb import binary

    data = cov.data
    _roundtrip(cov, binary.write_cmb(binary.read_cmb(data)))
    cov.fill(DECODED)
    cov.mark(0x18, 4, UNREAD, "header +0x18 (compiler build stamp)")
    cov.zero(0x1C, 4, "header +0x1C")
    table = struct.unpack_from("<I", data, 0x28)[0]
    pos = table
    while True:
        (addr,) = struct.unpack_from("<I", data, pos)
        pos += 4
        if not addr:
            break
        cov.zero(addr + 8, 4, "function +0x08")
        cov.zero(addr + 0x0F, 1, "function +0x0F", nonzero=UNREAD)


#: zdbx folders and files decoded field by field (zdbx.py and the battle_* modules).
DBX_DECODED = ("zu/", "xwp/", "zbg/", "xcam/", "zdbx/camera.dbx", "zdbx/joblist.dbx", "zdbx/weaponlist.dbx",
               "zdbx/skill.dbx", "zdbx/param.dbx", "zdbx/effectlist.dbx", "zdbx/classlist.dbx", "zdbx/bglist.dbx")
#: Field keys whose unit is unknown (UNDECODED_BYTES, zdbx).
DBX_UNITS_OPEN = ("移動速度".encode("shift_jis"), "間合い".encode("shift_jis"), b"time")


@handles("dbx", lambda name, data: _ext(name) == "dbx")
def dbx_file(cov: FileCoverage, walker: Walker) -> None:
    full = cov.name.lower().replace("\\", "/")
    path = full.split(":", 1)[-1]
    if not any(f"/{p}" in f"/{path}" or f"/{p}" in f"/{full}" for p in DBX_DECODED):
        cov.fill(UNDECODED, f"dbx {path.split('/')[0]}/{'*' if '/' in path else path}")
        return
    cov.fill(DECODED)
    data = cov.data
    pos = 0
    for line in data.split(b"\n"):
        stripped = line.strip()
        if any(stripped.startswith(key) for key in DBX_UNITS_OPEN):
            cov.mark(pos, len(line), PLAUSIBLE, "dbx field with unknown unit")
        pos += len(line) + 1


# ------------------------------------------------------------------ fonts, media, sound

@handles("gcf font", lambda name, data: _ext(name) == "gcf" or (_base(name).rstrip("#") == "system.cms" and name.endswith("#")))
def gcf_font(cov: FileCoverage, walker: Walker) -> None:
    from . import fe9_font

    fe9_font.GameFont(cov.data) if hasattr(fe9_font, "GameFont") else None
    cov.fill(DECODED)  # FONT_NOTES: every header and glyph byte labelled


@handles("stm", lambda name, data: _ext(name) == "stm")
def stm_file(cov: FileCoverage, walker: Walker) -> None:
    from . import stm

    stm.read_stm(io.BytesIO(cov.data))
    cov.fill(DECODED)


@handles("thp", lambda name, data: data[:4] == b"THP\0")
def thp_file(cov: FileCoverage, walker: Walker) -> None:
    from . import thp

    thp.read_info(io.BytesIO(cov.data))
    cov.fill(DECODED)


@handles("bnr", lambda name, data: _ext(name) == "bnr")
def banner(cov: FileCoverage, walker: Walker) -> None:
    if cov.data[:4] not in (b"BNR1", b"BNR2"):
        raise ValueError("not a BNR1/BNR2 banner")
    cov.fill(DECODED)  # public GameCube banner format


@handles("musyx samp", lambda name, data: _ext(name) == "samp")
def musyx_samp(cov: FileCoverage, walker: Walker) -> None:
    cov.fill(DECODED)  # DSP-ADPCM sample data addressed by the .sdir


@handles("musyx sdir", lambda name, data: _ext(name) == "sdir")
def musyx_sdir(cov: FileCoverage, walker: Walker) -> None:
    data = cov.data
    pos = 0
    while _u16(data, pos) != 0xFFFF:
        cov.mark(pos, 32, DECODED)
        cov.zero(pos + 2, 2, "record +2")
        cov.zero(pos + 8, 4, "record +8")
        info = _u32(data, pos + 28)
        cov.mark(info, 8, UNDECODED, "ADPCM info header")
        cov.mark(info + 8, 32, DECODED)
        pos += 32
    cov.mark(pos, 4, DECODED)
    cov.fill(PADDING, only_zero=True)


#: Sound-macro opcodes musyx.py reads: end, play macro, start sample.
MACRO_OPS_DECODED = {0x00, 0x08, 0x10}


@handles("musyx pool", lambda name, data: _ext(name) == "pool")
def musyx_pool(cov: FileCoverage, walker: Walker) -> None:
    """Four table offsets; the first is the sound-macro table. The other
    three (public MusyX: ADSR tables, keymaps, layers) are not parsed."""
    data = cov.data
    offsets = struct.unpack_from(">4I", data, 0)
    cov.mark(0, 16, DECODED)
    later = sorted(o for o in offsets[1:] if o)
    end = later[0] if later else len(data)
    pos = offsets[0]
    while pos + 4 <= end:
        size = _u32(data, pos)
        if size == 0xFFFFFFFF or size < 8:
            cov.mark(pos, 4, DECODED)
            break
        cov.mark(pos, 6, DECODED)
        cov.zero(pos + 6, 2, "macro pad")
        for c in range(pos + 8, pos + size - 7, 8):
            op = data[c + 3]
            cov.mark(c, 8, DECODED if op in MACRO_OPS_DECODED else UNDECODED, "" if op in MACRO_OPS_DECODED
                     else f"macro command op {op:#04x}")
        pos += size
    for i, off in enumerate(offsets[1:], 1):
        if off:
            stop = min([o for o in offsets if o > off] + [len(data)])
            cov.mark(off, stop - off, UNDECODED, f"pool table {i} (not parsed)")
    cov.fill(PADDING, only_zero=True)


@handles("musyx proj", lambda name, data: _ext(name) == "proj")
def musyx_proj(cov: FileCoverage, walker: Walker) -> None:
    """Group chain: header, FX tables, song pages and MIDI setups are parsed
    (musyx.py); the macro/sample/curve/keymap/layer id lists are not."""
    data = cov.data
    offset = 0
    while offset + 0x28 <= len(data):
        next_offset, _gid, gtype = struct.unpack_from(">IHH", data, offset)
        cov.mark(offset, 0x28, DECODED)
        stop = next_offset if next_offset and next_offset != 0xFFFFFFFF else len(data)
        if gtype == 1:
            table = _u32(data, offset + 0x1C)
            count = _u16(data, table)
            cov.mark(table, 4 + 10 * count, DECODED)
        elif gtype == 0:
            normal, drum, setups = struct.unpack_from(">3I", data, offset + 0x1C)
            for pages in (normal, drum):
                p = pages
                while p and p + 6 <= stop and data[p + 4] != 0xFF:
                    cov.mark(p, 6, DECODED)
                    p += 6
                if p:
                    cov.mark(p, 6, DECODED)
            s = setups
            while s and s + 4 <= stop and _u16(data, s) != 0xFFFF:
                cov.mark(s, 4 + 5 * 16, DECODED)
                s += 4 + 5 * 16
        for i in range(5):
            lst = _u32(data, offset + 8 + 4 * i)
            if lst and lst < stop:
                cov.mark(lst, 2, UNDECODED, f"group id list {i} (not parsed)")
        if not next_offset or next_offset == 0xFFFFFFFF or next_offset <= offset:
            break
        offset = next_offset
    cov.fill(UNDECODED, "proj (not parsed)")


@handles("musyx tables", lambda name, data: _ext(name) in ("stbl", "etbl"))
def musyx_tables(cov: FileCoverage, walker: Walker) -> None:
    cov.fill(DECODED)  # song and FX name tables (MUSIC_NOTES)


@handles("musyx slib", lambda name, data: _ext(name) == "slib")
def musyx_slib(cov: FileCoverage, walker: Walker) -> None:
    """Song blobs (musyx_song.py): headers, tracks and note/controller events
    decoded; the pitch-bend and modulation streams are not."""
    data = cov.data
    cov.fill(DECODED)
    pos = 0
    while pos + 0x20 <= len(data):
        size = _u32(data, pos)
        if not size:
            break
        song = pos + 0x20
        pattern_table = _u32(data, song + 4)
        patterns = []
        p = song + pattern_table
        while p + 4 <= pos + size:
            off = _u32(data, p)
            if not off or off >= size:
                break
            patterns.append(off)
            p += 4
        for off in patterns:
            base = song + off
            if base + 12 > len(data):
                continue
            bend, mod = _u32(data, base + 4), _u32(data, base + 8)
            for stream_off, label in ((bend, "pitch-bend stream"), (mod, "modulation stream")):
                if stream_off:
                    cov.mark(base + 4 + stream_off, 4, UNDECODED, label)
        pos += size
    cov.fill(DECODED)


@handles("gcfesnd.bin", lambda name, data: _base(name) == "gcfesnd.bin")
def gcfesnd_bin(cov: FileCoverage, walker: Walker) -> None:
    """Cue catalog (MUSIC_NOTES §7): BGM +0x06 volume-like, +0x07 constant 0x40;
    SFX +0x0C/+0x10 inferred from accessor offsets."""
    data = cov.data
    pos = HEADER_SIZE
    while pos < len(data) and data[pos + 4]:
        length = data[pos + 4]
        cov.mark(pos, length, DECODED)
        if length == 12:
            cov.mark(pos + 6, 1, PLAUSIBLE, "BGM +0x06 (volume?)")
            cov.mark(pos + 7, 1, UNDECODED, "BGM +0x07")
        elif length == 20:
            cov.mark(pos + 0x0C, 8, PLAUSIBLE, "SFX +0x0C..+0x13 (priority/range?)")
        else:
            cov.mark(pos, length, UNDECODED, f"cue record of length {length}")
        pos += length
    cov.mark(pos, 8, DECODED)
    cov.fill(DECODED)  # names, relocations, section table


# ------------------------------------------------------------------ memory card

@handles("gci save", lambda name, data: _ext(name) == "gci")
def gci_save(cov: FileCoverage, walker: Walker) -> None:
    """SAVE_NOTES: every byte stored and round-tripped; §8 lists the open ones."""
    from . import save_file as sf

    data = cov.data
    G = sf.GCI_HEADER_SIZE
    cov.mark(0, G + 0x2000, DECODED)  # directory entry, banner and icons
    for body, size in sf.BLOCK_LOCATIONS:
        off = G + body
        block = sf.SaveBlock.parse(data, off, size)
        if block is None or block.header.save_kind == 1 or block.party is None:
            cov.mark(off, size, PADDING if not any(data[off:off + size]) else DECODED)
            continue
        cov.mark(off, size, DECODED)
        cov.zero(off + 0x54, 4, "header +0x54")
        cov.zero(off + 0x67, 9, "header +0x67")
        s = off + sf.CRC_START
        cov.mark(s + 0x43, 2, UNDECODED, "SYSF +0x43/+0x44")
        cov.zero(s + 0x45, 2, "SYSF +0x45")
        p = off + sf.STREAM_START + 4
        cov.mark(p, 16, UNDECODED, "BMST +0x00..0x0F")
        cov.mark(p + 0x50, 2, UNDECODED, "BMST +0x50/+0x51")
        cov.mark(p + 0x94, 8, UNDECODED, "BMST +0x94..0x9B (objective state)")
        opts = p + 0x9C
        for i, known in enumerate((0x1E, 0x00, 0x0C, 0xE0)):
            cov.bits(opts + i, 1, known=known, name=f"option byte {i}")
        cov.zero(opts + 11, 1, "option byte 11")
        m = p + sf.PartyState.SIZE + 4
        cov.mark(m + 7, 10, UNDECODED, "MDST runtime bytes 7-16")
        cov.zero(m + 0x16, 10, "MDST pad")
        r = m + sf.MapState.SIZE + 4
        for unit in block.units:
            if unit is None:
                r += 2
                continue
            for rel, size_, label in ((0x0C, 1, "unit +0x19D"), (0x6A, 2, "unit +0x230"), (0x6C, 2, "unit +0x232"),
                                      (0x6F, 1, "unit +0x235"), (0x89, 2, "unit +0x15C")):
                cov.mark(r + rel, size_, UNDECODED, label)
            cov.zero(r + 0x8B, 4, "unit pad")
            r += sf.UNIT_RECORD_SIZE
        r += 4 + 4 * sf.CONVOY_SLOTS + 4
        for i in range(sf.FORGE_RECORDS):
            cov.mark(r + 0x18 * i + 0x14, 4, PLAUSIBLE, "FWEP +0x14..0x17 (appearance)")
        stream_end = off + sf.STREAM_START + len(block.build_stream())
        cov.zero(stream_end, off + size - stream_end, "after the stream")
