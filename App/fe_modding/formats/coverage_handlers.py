"""Per-format handlers of the disc-wide byte-coverage map (:mod:`coverage`).

Each handler places every byte of one file. A field gets the status its
topic note gives it (``research/*.md``); when a note changes a field's
confidence, the handler here changes with it. Formats the app rebuilds byte
for byte are checked by a round trip first: a file that does not rebuild is
reported as a failure instead of being counted as decoded.
"""

from __future__ import annotations

import io
import re
import struct

from . import lz10, pak
from .common import HEADER_SIZE, SECTION_TABLE_SENTINEL
from .coverage import (DECODED, PADDING, PLAUSIBLE, RESERVED, UNCLASSIFIED, UNDECODED, UNREAD, FileCoverage, Walker,
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


# ------------------------------------------------------------------ Wii HOME Menu (system/HomeButton)
#
# Radiant Dawn ships Nintendo's HOME Menu library resources (the menu every Wii
# game opens with the HOME button). They are SDK files in public formats, not
# game data: U8 archives of NW4R layouts, animations and a font, TPL textures,
# MIDI songs and the menu's sound banks.

U8_MAGIC = b"\x55\xaa\x38\x2d"


@handles("u8", lambda name, data: data[:4] == U8_MAGIC)
def u8_archive(cov: FileCoverage, walker: Walker) -> None:
    """A U8 archive: 0x20-byte header, 12-byte nodes (type, name offset, data
    offset or parent, size or next index), the name table, then the members."""
    data = cov.data
    root, header_size, data_offset = struct.unpack_from(">III", data, 4)
    cov.mark(0, 0x10, DECODED)
    cov.zero(0x10, 0x10, "U8 header reserved")
    count = _u32(data, root + 8)
    names = root + 12 * count
    if root + header_size > len(data) or names > root + header_size:
        raise ValueError("U8 node table runs past the header")
    cov.mark(root, 12 * count, DECODED)
    path: list[tuple[int, str]] = []  # (end index, directory name)
    for i in range(1, count):
        while path and i >= path[-1][0]:
            path.pop()
        kind_name, offset, size = struct.unpack_from(">III", data, root + 12 * i)
        start = names + (kind_name & 0xFFFFFF)
        name = data[start:data.index(b"\0", start)].decode("ascii", "replace")
        if kind_name >> 24:
            path.append((size, name))
            continue
        if offset + size > len(data):
            raise ValueError(f"U8 member {name} runs past the archive")
        cov.mark(offset, size, DECODED)
        member = "/".join([p for _e, p in path] + [name])
        walker.child(f"{cov.name.rstrip('#')}:{member}", data[offset:offset + size])
    strings_and_padding(cov, names, root + header_size)
    cov.fill(PADDING, only_zero=True)


_NW4R_MAGICS = (b"RLYT", b"RLAN", b"RFNT", b"RLPA", b"RLVC")


@handles("nw4r layout", lambda name, data: data[:4] in _NW4R_MAGICS and data[4:6] == b"\xfe\xff")
def nw4r_file(cov: FileCoverage, walker: Walker) -> None:
    """NW4R layout, animation and font files (``RLYT``, ``RLAN``, ``RFNT``): a
    header (magic, byte order, version, size, header size, section count), then
    sections that each start with a magic and their size. The section bodies are
    the SDK's public formats; the file counts as decoded when the chain of
    sections ends exactly at the file size the header gives."""
    data = cov.data
    size, header_size, sections = struct.unpack_from(">IHH", data, 8)
    if size != len(data):
        raise ValueError("NW4R file size does not match its header")
    at = header_size
    for _ in range(sections):
        length = _u32(data, at + 4)
        if length < 8 or at + length > size:
            raise ValueError(f"NW4R section at {at:#x} is malformed")
        at += length
    if at != size:
        raise ValueError("NW4R sections do not end at the file size")
    cov.mark(0, size, DECODED)


@handles("midi", lambda name, data: data[:4] == b"MThd")
def midi_file(cov: FileCoverage, walker: Walker) -> None:
    """A Standard MIDI File (the HOME Menu's songs): ``MThd`` then chunks, each a
    tag and a size. Decoded when the chunks end at the file's end (zero fill after)."""
    data = cov.data
    at = 0
    while at + 8 <= len(data) and data[at:at + 4] in (b"MThd", b"MTrk"):
        at += 8 + _u32(data, at + 4)
    if at > len(data):
        raise ValueError("MIDI chunk runs past the file")
    cov.mark(0, at, DECODED)
    cov.zero(at, len(data) - at, "MIDI trailing bytes")


@handles("build script", lambda name, data: _ext(name) == "bat")
def build_script(cov: FileCoverage, walker: Walker) -> None:
    """``Fonts/fontPack.bat`` and ``system/HomeButton/hbmPack.bat`` on the PAL
    disc: the developers' Windows packing scripts, left on the disc. Plain
    text; the game never opens them."""
    cov.data.decode("ascii")
    cov.mark(0, len(cov.data), DECODED)


@handles("home menu text", lambda name, data: _base(name) in ("home.csv", "config.txt")
         and "homebutton" in name.lower())
def home_menu_text(cov: FileCoverage, walker: Walker) -> None:
    """``home.csv`` (the menu's messages, UTF-16 with a byte-order mark) and
    ``config.txt`` (layout name and two numbers): text the SDK reads as text."""
    data = cov.data
    data.decode("utf-16") if data[:2] == b"\xfe\xff" else data.decode("ascii")
    cov.mark(0, len(data), DECODED)


@handles("home menu sound", lambda name, data: _ext(name) in ("wt", "pcm", "bwav") and "homebutton" in name.lower())
def home_menu_sound(cov: FileCoverage, walker: Walker) -> None:
    """The HOME Menu's synthesizer wave table, its PCM samples and the remote
    speaker sounds: SDK sound data whose layout is not described here."""
    cov.mark(0, len(cov.data), UNDECODED, f"HOME Menu sound data (.{_ext(cov.name)})")


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
    end, lengths, seen, repeats = 0, {}, set(), 0
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
        end = max(end, pos)
        lengths[image] = pos - texels
        repeats += image in seen
        seen.add(image)
        if palette:
            entries, _unpacked, _pad, _fmt, pal_data = struct.unpack_from(">HBBII", data, palette)
            cov.mark(palette, 12, DECODED)
            cov.mark(pal_data, 2 * entries, DECODED)
    # window/unitranking.cms: entries 13-15 repeat entry 12's header, and three
    # more images of that size follow the last texels. Nothing points to them.
    if repeats and end < len(data):
        last = max(lengths, key=lambda h: struct.unpack_from(">I", data, h + 8)[0])
        if lengths[last] and len(data) - end == repeats * lengths[last]:
            cov.mark(end, len(data) - end, UNREAD, "image data behind repeated image headers (unreachable)")
            # Their own 0x24-byte headers follow the last referenced one.
            for k in range(repeats):
                header = max(lengths) + 0x24 * (k + 1)
                if header + 0x24 <= len(data) and _u32(data, header + 8) == end + k * lengths[last]:
                    cov.mark(header, 0x24, UNREAD, "image header no table entry points to")
    cov.fill(PADDING, only_zero=True)


# ------------------------------------------------------------------ models

def _gs_material_texture(cov: FileCoverage, rec: int, i: int) -> None:
    """28-byte material texture record (GRAPHICS_NOTES, materials): +0 bit 0
    identity texture matrix, bit 5 sampler override, bit 7 keeps the stage's
    texcoord slot; +3 the stage kind (0-7, the switch at RFEE01 0x8001338C; 5
    and 6 also flag the material at 0x80012508); +4 tex_id; +8..+0x1B the
    translation/scale/rotation floats of the non-identity branch. +2 is the
    texcoord slot the loader writes (0x80012560). Flag bits 0x2/0x4/0x8 and
    +6 (two bytes 0-3 on Radiant Dawn) are read by no texture setup found in
    RFEE01 (0x80012F00, 0x800124D0) and are classified as such."""
    data = cov.data
    flags0 = struct.unpack_from(">H", data, rec)[0]
    cov.bits(rec, 2, known=0x00A1, plausible=0, name="texture.flags0")
    if not flags0 & ~0x00AF & 0xFFFF and flags0 & 0x000E:
        cov.mark(rec + 1, 1, UNREAD, "texture.flags0 0x2/0x4/0x8 (no reader)")
    cov.zero(rec + 2, 1, "texture +2 (texcoord slot, set in RAM)")
    if data[rec + 3] <= 7:
        cov.mark(rec + 3, 1, DECODED)
    else:
        cov.mark(rec + 3, 1, UNDECODED, "texture stage kind > 7")
    cov.mark(rec + 4, 2, DECODED)
    if data[rec + 6] | data[rec + 7]:
        cov.mark(rec + 6, 2, UNREAD, "texture +6 (no reader)")
    else:
        cov.mark(rec + 6, 2, PADDING, "texture +6")
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
        # +4 halfword flags (zero on Path of Radiance but bit 0, which
        # setup_gs_texcoord_and_material_color tests). RFEE01 tests 0xE000
        # blend mode and 0x0030 z mode (0x800186C8), 0x0008 (0x80018814),
        # 0x0001/0x0400 (0x80013EA0), 0x0040 (0x800145E0), 0x0080 (0x80013A84),
        # 0x0200 (0x800094CC), 0x0800 (0x80016944), 0x1000 (0x80013D1C),
        # 0x4000 (0x80012650), 0x8000 (0x800151EC). 0x0004 is only reachable
        # through the caller-masked search at 0x80014D68.
        flags = _u16(data, m + 4)
        cov.bits(m + 4, 2, known=0xFFFB, name="material flags")
        if flags & 0x0004 and cov.status[m + 5] == UNDECODED:
            cov.mark(m + 5, 1, UNREAD, "material flags 0x4 (no direct reader)")
        cov.zero(m + 7, 1, "material +7 (runtime flags, zero on disc)")
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
            cov.zero(m + 0x1E, 6, "mesh +0x1E trailer (zero on all 16,201 disc meshes)")
    for slot in (6, 7, 8):
        ptr = addrs[slot]
        while ptr:
            c = B + ptr
            cov.mark(c, 0x20, DECODED)
            cov.zero(c + 0x0E, 2, "shape +0x0E (runtime slot)")
            # 0x0008 skips the ordinary material/light setup; 0x0200 averages
            # two light colours. 0x6000 mirrors list membership without a reader.
            cov.bits(c + 8, 2, known=0xFFFF & ~0x6000, plausible=0x6000, name="shape.flags")
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
    are decoded. ``0x2`` makes the pose copy the curve quaternion and the
    matrix builder apply the bone's skin matrix (RFEE01 0x8000D1EC,
    0x8000DFC4, 0x8000ED5C); nothing in RFEE01 tests ``0x4``."""
    from . import skeleton

    data = cov.data
    _roundtrip(cov, skeleton.write_skeleton_file(skeleton.read_skeleton_file(data)))
    pool, count = _u32(data, 4), _u32(data, 8)
    cov.zero(0, 4, "header +0")
    cov.mark(4, 12, DECODED)
    for i in range(count):
        rec = 0x10 + 0xF4 * i
        cov.mark(rec, 0xF4, DECODED)
        cov.bits(rec + 0x0C, 4, known=0xFFFFFFFF & ~0x4, name="bone.flags")
        if data[rec + 0x0F] & 0x04 and cov.status[rec + 0x0F] == UNDECODED:
            cov.mark(rec + 0x0F, 1, UNREAD, "bone.flags 0x4 (no reader)")
    cov.mark(pool, len(data) - pool, DECODED)


#: Combat and effect-movement events (GRAPHICS_NOTES, "Rig contract" and
#: ".ga footer"; rig_contract.EVENT_NAMES). Codes 6/7 are confirmed no-ops.
GA_EVENT_KNOWN = ({0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 0x0F, 0x10, 0x11, 0x12,
                   0x13, 0x1C, 0x1D, 0x28, 0x29, 0x2A, 43, 44, 45, 46,
                   47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 60}
                  | set(range(0x14, 0x1C)) | set(range(0x1E, 0x28)))


@handles("animation", lambda name, data: _ext(name) == "ga")
def ga_file(cov: FileCoverage, walker: Walker) -> None:
    from . import animation

    data = cov.data
    anim = animation.read_animation_bytes(data)
    _roundtrip(cov, animation.write_animation(anim))
    words = anim.header.words
    cov.mark(0, 0x30, DECODED)
    for w in (1, 10):
        cov.zero(4 * w, 4, f"header word {w}")
    # Radiant Dawn's loader (0x8000bc20) drops the footer unless header byte 8
    # is at least 1; files with and without a footer set it.
    if data[8] == 1:
        cov.mark(8, 1, DECODED)
        cov.zero(9, 3, "header word 2")
    else:
        cov.zero(8, 4, "header word 2")
    cov.mark(words[8], words[9] - words[8], DECODED)
    for i in range((words[11] - words[9]) // 12):
        rec = words[9] + 12 * i
        cov.mark(rec, 12, DECODED)
        cov.zero(rec + 3, 1, "curve.scale low byte")
        cov.zero(rec + 8, 2, "curve +8")
    footer = words[0]
    if footer and anim.footer is not None and anim.footer.compact_raw is not None:
        _ga_fe10_footer(cov, anim, footer)
        return
    cov.mark(words[11], (footer or len(data)) - words[11], DECODED)
    if not footer:
        return
    cov.mark(footer, 36, DECODED)
    cov.zero(footer + 36, 4, "footer pad")
    slots = struct.unpack_from(">9I", data, footer)
    used = sorted((a, s) for s, a in enumerate(slots) if a)
    for k, (addr, slot) in enumerate(used):
        end = used[k + 1][0] if k + 1 < len(used) else len(data)
        if slot == 0:
            _ga_events(cov, addr, end)
        elif slot == 8:
            _ga_particle_table(cov, addr, end)
        elif slot in (1, 2, 3, 4):
            # Material alpha/colour and U/V tracks share this decoded key table.
            # The U/V readers scale values by 0.001; water uses slot 3.
            # Keep malformed blocks open rather than assuming their bytes are tracks.
            try:
                animation.read_material_tracks(data[addr:end])
            except (ValueError, struct.error):
                cov.mark(addr, end - addr, UNDECODED, f"footer slot {slot} malformed material tracks")
            else:
                cov.mark(addr, end - addr, DECODED)
        else:
            cov.mark(addr, end - addr, UNDECODED, f"footer slot {slot}")
    cov.fill(PADDING, only_zero=True)


def _ga_fe10_footer(cov: FileCoverage, anim, footer: int) -> None:
    """Radiant Dawn's footer chain: keyframes, then the slot blocks, then the
    12-byte descriptors. Slot numbers follow ``animation.FE10_FOOTER_SLOT_NAMES``:
    0 bone visibility, 5 events, 6-12/14/15 material key tables, 13 particle
    emitters."""
    from . import animation

    data = cov.data
    keys_end = footer - len(anim.body_trailing)
    words = anim.header.words
    cov.mark(words[11], keys_end - words[11], DECODED)
    chain = animation.fe10_footer_chain(data, footer)
    points = sorted([(block, slot, False) for _, slot, block in chain] +
                    [(at, slot, True) for at, slot, _ in chain])
    for i, (at, slot, is_descriptor) in enumerate(points):
        end = points[i + 1][0] if i + 1 < len(points) else len(data)
        if is_descriptor:
            cov.mark(at, 12, DECODED)
            continue
        if slot == animation.FE10_PARTICLE_SLOT:
            # Same emitter table as PoR's slot 8 (read_particle_table_layout).
            _ga_particle_table(cov, at, end, fe10=True)
            continue
        block = data[at:end]
        try:
            if slot == animation.FE10_EVENT_SLOT:
                animation.read_fe10_event_block(block)
            elif slot in animation.FE10_MATERIAL_TRACK_SLOTS | animation.FE10_OPEN_TRACK_SLOTS:
                if len(block) < 8:
                    raise ValueError
                animation.read_material_tracks(block)
            else:
                raise ValueError
        except (ValueError, struct.error, animation.AnimationError):
            cov.mark(at, end - at, UNDECODED, f"RD footer slot {slot} block")
            continue
        if slot == animation.FE10_EVENT_SLOT:
            _ga_fe10_events(cov, at, end)
        elif slot in animation.FE10_OPEN_TRACK_SLOTS:
            cov.mark(at, end - at, PLAUSIBLE, f"RD footer slot {slot} key table")
        else:
            _ga_material_tracks(cov, at, end)
    cov.fill(PADDING, only_zero=True)


# Event codes whose Radiant Dawn reader is identified: 3 and 4 are looked up
# by the playback loop (0x800081d4, 0x80009ef8 with code 3); 0x1F's parameter
# is compared with a battle index (0x800e2c38). Other codes keep PoR's
# numbering by assumption, so they stay plausible. Codes from 1000 up are
# sound cues: the event handler 0x800e4b20 looks each one up in
# sound_data's SND_SFX_MAYA_DATA (0x800f14b4) and plays the match.
GA_FE10_EVENT_SFX = 1000
GA_FE10_EVENT_KNOWN = frozenset((3, 4, 0x1F))


def _ga_fe10_events(cov: FileCoverage, start: int, end: int) -> None:
    data = cov.data
    count = _u16(data, start)
    cov.mark(start, 8 + 2 * count, DECODED)
    last = start + 8 + 2 * count
    for k in range(count):
        offset = _u16(data, start + 8 + 2 * k)
        if offset == 0xFFFF:
            continue
        key = start + offset
        n = data[key + 3]
        cov.mark(key, 4, DECODED)
        for c in range(n):
            at = key + 4 + 4 * c
            code = _u16(data, at)
            if code in GA_FE10_EVENT_KNOWN or code >= GA_FE10_EVENT_SFX:
                cov.mark(at, 4, DECODED)
            else:
                cov.mark(at, 4, PLAUSIBLE, f"RD event code {code:#x}")
        last = max(last, key + 4 + 4 * n)
    if last < end:
        cov.zero(last, end - last, "event track tail")


def _ga_material_tracks(cov: FileCoverage, start: int, end: int) -> None:
    """A per-material key table: count, pad, runtime pointer, u16 offsets,
    then per track u16 key count, u16 mode and ``(u16 frame, s16 value)`` keys."""
    data = cov.data
    count = _u16(data, start)
    cov.mark(start, 8 + 2 * count, DECODED)
    last = start + 8 + 2 * count
    for k in range(count):
        offset = _u16(data, start + 8 + 2 * k)
        if offset == 0xFFFF:
            continue
        n = _u16(data, start + offset)
        cov.mark(start + offset, 4 + 4 * n, DECODED)
        last = max(last, start + offset + 4 + 4 * n)
    if last < end:
        cov.zero(last, end - last, "material track tail")


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
            elif code >= 1000:
                # play_actor_sfx_cue_array passes these through
                # lookup_sfx_name_by_event_code, which binary-searches gcfesnd.bin's
                # SFXTable and plays the returned symbolic cue name.
                cov.mark(pos + 4 + 2 * c, 2, DECODED)
            else:
                cov.mark(pos + 4 + 2 * c, 2, UNDECODED, f"event code {code}")
        pos += 4 + 2 * n
    if pos < end:
        cov.zero(pos, end - pos, "event track tail")


def _ga_particle_table(cov: FileCoverage, start: int, end: int, fe10: bool = False) -> None:
    """Place only slot-8 fields confirmed by GParticle.cpp's init/update readers.
    ``fe10`` is Radiant Dawn's slot 13: the same table, where RFEE01 also reads
    +0x1C as the emitter's bone index (0x80015368 -> 0x8000f3d4) and draw-flag
    bit 0x10 makes setup take the min/max of the stage start frames
    (0x8001558c)."""
    from . import animation

    data = cov.data
    cov.mark(start, end - start, UNDECODED, "particle table details")
    try:
        layout = animation.read_particle_table_layout(data, start)
    except (animation.AnimationError, struct.error):
        return
    if layout is None or layout.block_offset != start:
        return
    cov.mark(start, 8, DECODED)  # magic, relocation bit, emitter count
    first_stage_index = 0
    for emitter_index, emitter in enumerate(layout.emitters):
        rec = emitter.record_offset
        cov.mark(rec, 4, DECODED)  # name-path pointer
        if emitter.local_index == emitter_index:
            cov.mark(rec + 4, 2, PLAUSIBLE, "particle emitter local index")
        if emitter.first_stage_index == first_stage_index:
            cov.mark(rec + 8, 2, PLAUSIBLE, "particle emitter first global stage")
        first_stage_index += emitter.stage_count
        # draw_actor_material_batches: low three bits select the draw path;
        # 0x0600 selects the orientation/matrix branch (0x0400 faces the camera,
        # 0x0600 applies an extra transform); 0x0800 gates actor visibility;
        # 0x1000/0x2000 choose blending, 0x4000 disables depth, and 0x8000
        # selects the alternate TEV order.
        cov.bits(rec + 6, 2, known=0xFE17 if fe10 else 0xFE07, name="particle draw flags")
        cov.mark(rec + 0x0A, 2, DECODED)  # .gs material index
        if fe10:  # no load of +0x0C in RFEE01's particle code (0x80015000-0x80017400)
            cov.mark(rec + 0x0C, 2, UNREAD, "particle emitter +0x0C (no reader)")
        else:
            cov.mark(rec + 0x0C, 2, UNDECODED, "particle emitter +0x0C")
        # Six signed /64 control slots. Modes 1, 2 and 4 read different
        # subsets; inactive slots contain defaults on the shipped disc.
        # +0E: mode-1 common S/T scale; +10: mode-2 GX point/line width;
        # +12: mode-2 common S/T scale; +14: mode-2 alpha factor;
        # +16/+18: mode-4 initial S and T scale.
        cov.mark(rec + 0x0E, 12, DECODED)
        cov.mark(rec + 0x1A, 2, DECODED)  # initial stage Z rotation, degrees / 64
        if fe10:
            cov.mark(rec + 0x1C, 2, DECODED)  # bone index
        else:
            cov.zero(rec + 0x1C, 2, "particle emitter +0x1C pad")
        cov.mark(rec + 0x1E, 2, DECODED)  # stage count
        cov.mark(rec + 0x20, 16, DECODED)  # four file-relative table pointers
        cov.zero(rec + 0x30, 4, "particle emitter tail pad")
        name_ptr = struct.unpack_from(">I", data, rec)[0]
        cov.mark(name_ptr, data.index(0, name_ptr) + 1 - name_ptr, DECODED)
        for stage in range(emitter.stage_count):
            at = emitter.stages_offset + stage * 12
            cov.mark(at, 2, PLAUSIBLE, "particle stage local index")
            cov.mark(at + 2, 10, DECODED)  # start/end frame, initial XYZ / 64
            at = emitter.stage_curves_offset + stage * 8
            cov.mark(at, 2, DECODED)  # global stage index
            cov.zero(at + 2, 2, "particle stage curve-range pad")
            cov.mark(at + 4, 4, DECODED)  # first curve, curve count
        # One shipped emitter (EID_FIRE_LONG) retains a curve-range record
        # despite having zero active stages. Its fields match the usual
        # global-stage index and full curve span, but runtime use is unproven.
        if (emitter.stage_count == 0 and
                emitter.stages_offset == emitter.stage_curves_offset and
                emitter.curves_offset == emitter.stage_curves_offset + 8 and
                struct.unpack_from(">4H", data, emitter.stage_curves_offset) ==
                (emitter.first_stage_index, 0, 0, emitter.curve_count)):
            cov.mark(emitter.stage_curves_offset, 8, PLAUSIBLE,
                     "orphan particle curve-range record")
        for curve in range(emitter.curve_count):
            at = emitter.curves_offset + curve * 12
            cov.mark(at, 2, DECODED)  # target channel 0..10
            cov.bits(at + 2, 1, known=0x3F, name="particle curve scale/flags")
            cov.zero(at + 3, 1, "particle curve descriptor pad")
            cov.mark(at + 6, 6, DECODED)  # key count and key-data offset
            n = struct.unpack_from(">H", data, at + 6)[0]
            first = struct.unpack_from(">I", data, at + 8)[0]
            if n and _u16(data, at + 4) == _u16(data, emitter.keys_offset + (first + n - 1) * 4):
                cov.mark(at + 4, 2, PLAUSIBLE, "particle curve last key frame")
            cov.mark(emitter.keys_offset + first * 4, n * 4, DECODED)

    # Once every table, string and emitter record has been placed, zero bytes
    # left between those structures are alignment fill. Keep any nonzero gap
    # open: EID_FIRE_LONG.ga has three such bytes.
    records = [(em.record_offset, em.record_offset + 0x34) for em in layout.emitters]
    rec_index = 0
    for pos in range(start, end):
        while rec_index < len(records) and pos >= records[rec_index][1]:
            rec_index += 1
        in_record = rec_index < len(records) and records[rec_index][0] <= pos
        if not in_record and cov.status[pos] == UNDECODED and data[pos] == 0:
            cov.mark(pos, 1, PADDING, "particle table alignment gap")


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
    if any(n.endswith(":mapdata") for n, _s, _e in found):
        _rd_map_bin(cov, found)
        return
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
                # b bit 0 skips placed-object drawing, bit 1 initializes
                # hidden state, bit 4 excludes footprint testing; c bit 1
                # loads .ga, bit 2 advances its timer, bits 3/4 enter the
                # footprint test, bit 5 selects a projected texture callback.
                # Effect bit 1 also copies roof height to the base layer;
                # bits 0/3/4/5/6/7 have operational render, sorting,
                # culling or hit-test roles. Their visual themes may be open.
                cov.bits(r + 0x18, 1, known=0xC0, name="flag_bits_a")
                cov.bits(r + 0x19, 1, known=0x13, plausible=0x2C, name="flag_bits_b")
                cov.bits(r + 0x1A, 1, known=0x3E, plausible=0xC0, name="flag_bits_c")
                cov.bits(r + 0x1B, 1, known=0xFB, name="effect flags")
        elif name == "mapbuildinst":
            cov.mark(start, 12 * n_inst, DECODED)  # footprint x2..end_y2: strong evidence
        elif name.startswith("panelindex"):
            cov.mark(start, 2 * x_size * y_size, DECODED)
        elif name.startswith("uniquepanel"):
            cov.mark(start, end - start, DECODED)
        elif name == "maplight":
            cov.mark(start, 12, DECODED)
            cov.zero(start + 9, 3, "maplight +9")
        elif name == "mapfog":
            cov.mark(start, 7, DECODED)
            cov.zero(start + 7, 1, "mapfog +7")
        elif name == "mapgrid":
            cov.mark(start, 4, DECODED)
            cov.mark(start, 1, UNREAD, "stored grid alpha; draw replaces it with SetGrid intensity")
        elif name == "mapextra":
            cov.mark(start, 6, DECODED)
            cov.zero(start + 6, 2, "mapextra +6")
            # Sight code (bits 18-19), weather ID (bits 20-24), material
            # callback selects 0x04/0x10/0x20, footprint test 0x10000000,
            # and object-sort-done/file-order flag 0x20000000.
            cov.bits(start + 8, 4, known=0x31FC0034, name="mapextra flags")
        elif name.startswith("maplink"):
            count = _u16(data, start)
            cov.mark(start, 2, DECODED)
            for i in range(count):
                e = start + 2 + 3 * i
                cov.mark(e, 2, DECODED)
                # Bits 0-3 are directional: maplink ground openings,
                # maplinkAt threat-range cost reduction, maplinkAbs ground
                # openings with complementary flying blocks. Every US source
                # value is <= 15; upper source bits remain unassigned.
                cov.bits(e + 2, 1, known=0x0F, name=f"{name} value")
        else:
            cov.mark(start, end - start, UNDECODED, f"section {name}")
    strings_and_padding(cov, HEADER_SIZE, HEADER_SIZE + _u32(data, 4))


def _rd_bits(cov: FileCoverage, offset: int, known: int, unread: int, name: str) -> None:
    """One flag byte: ``known`` bits have a traced reader, ``unread`` bits are
    classified but nothing in RFEE01 reads them; any other set bit stays open."""
    byte = cov.data[offset]
    if byte & ~(known | unread):
        cov.mark(offset, 1, UNDECODED, f"{name} bits {byte & ~(known | unread):#x}")
    elif byte & unread:
        cov.mark(offset, 1, UNREAD, f"{name} bits without a reader")
    else:
        cov.mark(offset, 1, DECODED)


def _rd_map_bin(cov: FileCoverage, found) -> None:
    """Radiant Dawn's map.bin (research/rd/MAP_NOTES.md): every section is
    prefixed with the map folder; ``zbg`` battle scenery keeps only mapdata,
    mapdesc, mapinst, maplight, mapfog and mapshader."""
    data = cov.data
    sections = {n.rpartition(":")[2]: (s, e) for n, s, e in found}
    head = sections["mapdata"][0]
    version, _zero, x_size, y_size, n_desc, n_inst = struct.unpack_from(">BBBBHH", data, head)
    for name, (start, end) in sections.items():
        if name == "mapdata":
            size = {2: 0x20, 3: 0x24, 4: 0x28}.get(version, 0x20)
            cov.mark(start, size, DECODED)
            cov.zero(start + 1, 1, "mapdata +1")
            cov.zero(start + 0x12, 2, "mapdata extra +6")
            cov.bits(start + 0x14, 4, known=0x31FC0034, name="mapdata extra flags")
            cov.mark(start + 0x18, 1, UNREAD, "stored grid alpha; draw replaces it with SetGrid intensity")
        elif name == "mapdesc":
            for i in range(n_desc):
                r = start + 36 * i
                cov.mark(r, 36, DECODED)
                # construct_rd_map_object packs A, B, C, effect into runtime +0xB8.
                # A1, A2 and effect 6 have readers but no retail carrier.
                _rd_bits(cov, r + 0x18, known=0x7F, unread=0x80, name="flag_bits_a")
                _rd_bits(cov, r + 0x19, known=0xC7, unread=0x38, name="flag_bits_b")
                _rd_bits(cov, r + 0x1A, known=0x7E, unread=0x81, name="flag_bits_c")
                _rd_bits(cov, r + 0x1B, known=0xF2, unread=0x0D, name="effect flags")
                cov.zero(r + 0x22, 2, "mapdesc footprint pad")
        elif name == "mapinst":
            for i in range(n_inst):
                r = start + 20 * i
                cov.mark(r, 16, DECODED)
                cov.mark(r + 16, 4, UNREAD, "mapinst +0x10 (read and discarded)")
        elif name.endswith("index"):
            cov.mark(start, 2 * x_size * y_size, DECODED)
        elif name in ("uniquepanel", "roofpanel", "basepanel"):
            cov.mark(start, end - start, DECODED)
        elif name == "maplight":
            cov.mark(start, 32, DECODED)
            cov.zero(start, 2, "maplight skipped prefix")
        elif name == "mapfog":
            cov.mark(start, 8, DECODED)
            cov.zero(start, 1, "mapfog skipped prefix")
            cov.mark(start + 8, 4, UNREAD, "mapfog +8 (not read)")
        elif name == "mapshader":
            shader = data[start]
            size = {0: 14, 1: 18}.get(shader, 24)
            cov.mark(start, size, DECODED)
        elif name in ("maplink", "maplinkAt"):
            count = _u32(data, start)
            cov.mark(start, 4, DECODED)
            for i in range(count):
                e = start + 4 + 3 * i
                cov.mark(e, 2, DECODED)
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


@handles("cp_data", lambda name, data: _base(name) == "cp_data.cms" and name.endswith("#"))
def fe10_cp_data(cov: FileCoverage, walker: Walker) -> None:
    """Radiant Dawn's decompressed CP resource.

    This handler must precede the generic FE10-container handler: Phase 4 has a
    lossless codec for the complete resource, so its records are decoded rather
    than merely recognized as opaque labeled sections.
    """
    from . import cp_data

    _roundtrip(cov, cp_data.build_cp_data(cp_data.parse_cp_data(cov.data)))
    cov.fill(DECODED)


@handles("FE10Data.cms", lambda name, data: _base(name) == "fe10data.cms" and name.endswith("#"))
def fe10data_file(cov: FileCoverage, walker: Walker) -> None:
    """Radiant Dawn's game database; must precede the generic FE10-container handler."""
    from . import fe10data_coverage as fc

    # As for FE8Data.bin: "reserved" there is a static finding, not a live watch, so UNREAD here.
    status = {fc.DECODED: DECODED, fc.PLAUSIBLE: PLAUSIBLE, fc.UNDECODED: UNDECODED,
              fc.RESERVED: UNREAD, fc.PADDING: PADDING}
    for span in fc.build_coverage(cov.data).spans():
        cov.mark(span.start, span.end - span.start, status[span.status], f"{span.section}.{span.name}")


@handles("fe10 sound data",lambda name, data: re.fullmatch(r"sound_data(_[a-z]{2})?\.cms", _base(name)) is not None
         and name.endswith("#"))
def fe10_sound_data(cov: FileCoverage, walker: Walker) -> None:
    """Radiant Dawn's cue registry and ``SND_*`` tables (``fe10_sound``):
    every field is named by ``fe10_sound.CUE_FIELDS`` / ``SND_TABLES`` after
    its RFEE01 reader. Strings the relocations point at are decoded."""
    from . import fe10_sound

    data = cov.data
    exports = hsdarc(cov)
    data_size, pointer_count = struct.unpack_from(">II", data, 4)
    pointers = struct.unpack_from(f">{pointer_count}I", data, HEADER_SIZE + data_size)
    cues = fe10_sound.read_sound_data(data)
    exported = set()
    for cue in cues:
        start = HEADER_SIZE + cue.record_offset
        exported.add(start)
        cov.fields(start, fe10_sound.CUE_FIELDS)
    tables = fe10_sound.SND_TABLES
    for name, start, _end in exports:
        if name.startswith("SND_GROUP_"):
            cov.mark(start, 8, DECODED)  # export name, BRSAR group label
        elif name in fe10_sound.SND_COUNTS:
            cov.mark(start, 4, DECODED)
        elif name in tables:
            row_size, layout = tables[name]
            count = _u32(data, start)
            cov.mark(start, 4, DECODED)
            for i in range(count):
                cov.fields(start + 4 + i * row_size, layout, f"{name} ")
    # Strings: every relocated pointer names a NUL-terminated label.
    for at in pointers:
        target = _u32(data, HEADER_SIZE + at)
        if not target:
            continue
        string = HEADER_SIZE + target
        end = data.find(b"\0", string)
        if end > string and cov.status[string] == UNCLASSIFIED:
            cov.mark(string, end + 1 - string, DECODED)
    # Two retail records repeat an exported cue's name; no export reaches them.
    for at in pointers:
        record = HEADER_SIZE + at
        if (cov.status[record] == UNCLASSIFIED and record not in exported
                and all(cov.status[record + k] == UNCLASSIFIED for k in range(fe10_sound.RECORD_SIZE))
                and fe10_sound.looks_like_cue(data, record)):
            cov.mark(record, fe10_sound.RECORD_SIZE, UNREAD, "cue record without an export (unreachable)")
    cov.fill(PADDING, only_zero=True)


def _fe10_growth(cov: FileCoverage) -> None:
    """``FE10Growth.cms`` (``fe10growth``): count, 12-byte records, per-level stat lines."""
    from . import fe10growth

    data = cov.data
    start = HEADER_SIZE + fe8data_symbols(data)["FE10PersonGrowth"]
    cov.mark(start, 2, DECODED)
    cov.zero(start + 2, 2, "growth count pad")
    for record in fe10growth.read_growth(data):
        at = start + 4 + fe10growth.RECORD_SIZE * record.index
        cov.mark(at, 12, DECODED)
        cov.zero(at + 6, 2, "growth record pad")
        cov.mark(record.lines_at, fe10growth.LINE_SIZE * len(record.lines), DECODED)


def _fe10_effects(cov: FileCoverage) -> None:
    """``FE10Effect.cms`` (``fe10_effect_registry``): the flag word and the four
    parameter bytes have readers but no traced meaning; the rest is named."""
    from . import fe10_effect_registry as reg

    data = cov.data
    registry = reg.read_fe10_effect_registry(data)
    symbols = fe8data_symbols(data)
    cov.mark(HEADER_SIZE + symbols["EffectData"], 4, DECODED)
    for record in registry.records:
        cov.mark(record.address, reg.RECORD_SIZE, DECODED)
        cov.mark(record.address + 8, 4, UNDECODED, "EffectData flags")
        cov.mark(record.address + 0x0C, 4, UNDECODED, "EffectData parameters")
    eid = HEADER_SIZE + symbols["EIDTable"]
    cov.mark(eid, 4 + reg.EID_RECORD_SIZE * len(registry.eid_table), DECODED)


def _fe10_rows(cov: FileCoverage, start: int, count: int, size: int, table: str, layout: dict) -> None:
    """Fixed rows of a Radiant Dawn table. ``layout`` maps a row offset to
    ``(size, kind, name)``: kind ``label`` (a string pointer, null or not),
    ``bits`` (``name`` is ``(known, unread)`` for :func:`_rd_bits`), ``flags``
    (a big-endian field; ``name`` is ``(known, plausible)`` for
    :meth:`FileCoverage.bits`), ``zero`` (a pad or a pointer the loader
    fills in RAM: decoded only while zero), or a coverage status. Relocated words are already marked by the container. Each
    byte left unplaced in a row stays undecoded, named by its row offset."""
    for i in range(count):
        row = start + i * size
        for off, (length, kind, name) in layout.items():
            if kind == "label":
                cov.mark(row + off, length, DECODED)
            elif kind == "bits":
                _rd_bits(cov, row + off, known=name[0], unread=name[1], name=f"{table} +{off:#x}")
            elif kind == "flags":
                cov.bits(row + off, length, known=name[0], plausible=name[1], name=f"{table} +{off:#x}")
            elif kind == "zero":
                cov.zero(row + off, length, f"{table} {name}")
            elif kind == DECODED:
                cov.mark(row + off, length, DECODED)
            else:
                cov.mark(row + off, length, kind, f"{table} {name}")
        off = 0
        while off < size:
            if cov.status[row + off] != UNCLASSIFIED:
                off += 1
                continue
            end = off
            while end < size and cov.status[row + end] == UNCLASSIFIED:
                end += 1
            cov.mark(row + off, end - off, UNDECODED, f"{table} +{off:#x}")
            off = end


def _table_head(cov: FileCoverage, start: int, name: str) -> int:
    """A ``u16 count, u16 0`` table head; returns the row count."""
    cov.mark(start, 2, DECODED)
    cov.zero(start + 2, 2, f"{name} count pad")
    return _u16(cov.data, start)


L = "label"

#: FE10Battle.cms rows (``fe10_battle``, ``fe10_battle_units``, ``fe10_battle_weapons``,
#: ``fe10_battle_scenery``; wiki ``meta/radiant-dawn``). Offsets not listed stay open.
FE10_BATTLE_LAYOUTS = {
    "FE10BAnimData": {0: (4, L, ""), 4: (4, L, ""), 8: (4, L, ""), 12: (4, L, ""), 16: (4, L, "")},
    "FE10BFlags": {0: (4, L, "")},
    "FE10BParam": {0: (4, L, "")},
    "FE10BTex": {0: (4, L, ""), 4: (4, L, "")},
    "FE10BFootEffect": {o: (4, L, "") for o in range(0, 0x18, 4)},  # name, up to five effect IDs
    "FE10BSFXData": {o: (4, L, "") for o in range(0, 0x14, 4)},  # name, up to four cues
    "FE10BSkill": {o: (4, L, "") for o in range(0, 0x14, 4)},  # name, SID, up to three effect IDs
    "FE10BSky": {0: (4, L, ""), 4: (4, L, "")},
    # +0x04: eight s16 FE10BSFXData rows, one per ground column (0x800BA2C8).
    "FE10BSFXList": {0: (4, L, ""), 4: (16, DECODED, "")},
    # +0x04: s32 value in 1/65536, looked up by name (0x800A84A4).
    "FE10BSetup": {0: (4, L, ""), 4: (4, DECODED, "")},
    # +0x21: 0x01/0x02/0x04/0x08 tested by the weapon actor (0x800BC590, 0x800BF394,
    # 0x800C0900, 0x800C0F94); +0x22: u16 scale read at 0x800BFD60.
    "FE10BWeapon": {**{o: (4, L, "") for o in range(0, 0x20, 4)}, 0x20: (1, DECODED, ""),
                    0x21: (1, "bits", (0x0F, 0x00)), 0x22: (2, DECODED, "")},
    # +0x08: 0x01 and 0x08 are tested on the motion row (0x800B2178), +0x0A is read
    # at 0x800B21DC. The other set bits and +0x0B are read through an object field
    # shared with the camera-file row, so they stay plausible.
    "FE10BMotion": {0: (4, L, ""), 4: (4, L, ""), 8: (2, "flags", (0x0009, 0xFFF6)),
                    10: (1, DECODED, ""), 11: (1, PLAUSIBLE, "+0xb")},
    # +0x08: camera-file flags, every set bit tested by 0x800A4420 / 0x800A6150
    # (0xE000 is the target mode copied to the camera); +0x0B: chain id.
    "FE10BCamFile": {0: (4, L, ""), 4: (4, L, ""), 8: (2, "flags", (0xEFFE, 0x0000)),
                     10: (1, "zero", "pad"), 11: (1, DECODED, "")},
    # +0x04: five s16 FE10BCamGroup rows by context (0x800A6D08), +0x0E pad.
    "FE10BCamEffect": {0: (4, L, ""), 4: (10, DECODED, ""), 0x0E: (2, "zero", "pad")},
    # +0x08 choice count; +0x0C/+0x10 are filled in RAM with the group's slices of
    # FE10BCamFileIndex and FE10BCamFileRate (0x800A88F4).
    "FE10BCamGroup": {0: (4, L, ""), 4: (4, L, ""), 8: (4, DECODED, ""), 0x0C: (8, "zero", "RAM pointers")},
    # +0x08: sixteen pointers into FE10BCamGroupIndex, written in RAM (0x800A8A84).
    "FE10BCamList": {0: (4, L, ""), 4: (4, L, ""), 8: (64, "zero", "RAM pointers")},
    # FE10BCamType is loaded (0x800A8754) and never read.
    "FE10BCamType": {0: (4, L, ""), 4: (4, UNREAD, "+0x4 (table without a reader)")},
    # +0x08: map model flags. 0x02 indoors, 0x08 mirrored, 0x10/0x20/0x40 the run-in;
    # 0x01 and 0x04 have no reader.
    "FE10BMapModel": {0: (4, L, ""), 4: (4, L, ""), 8: (1, "bits", (0x7A, 0x05)),
                      9: (5, DECODED, ""), 0x0E: (10, DECODED, "")},
    "FE10BMapData": {0: (4, L, ""), 4: (10, DECODED, ""), 0x0E: (2, "zero", "pad")},
    "FE10BWeaponType": {4: (4, L, "")},
    # +0x08/+0x0C: trail and aura effect IDs. +0x10: bit i tests FE10BFlags row i (18 rows,
    # 0x800A7460); +0x14: bit i = FE10BWeaponType row i picks a random attack variant
    # (0x800BEED8 from 0x800B78BC); +0x18: the 20 FE10BParam values; +0x40: per weapon
    # type a 128-bit FE10BMotion set (0x800A7324); +0x140: six s16 FE10BCamList rows
    # (0x800A6F34); +0x150 is set in RAM to the unit's FE10BTex rows.
    "FE10BUnit": {0: (4, L, ""), 4: (4, L, ""), 8: (4, L, ""), 0x0C: (4, L, ""),
                  0x10: (1, "bits", (0x00, 0x00)), 0x11: (1, "bits", (0x03, 0x00)),
                  0x12: (1, "bits", (0xFF, 0x00)), 0x13: (1, "bits", (0xFF, 0x00)),
                  0x14: (4, "flags", (0xFFFF, 0)), 0x18: (40, DECODED, ""), 0x40: (256, DECODED, ""),
                  0x140: (12, DECODED, ""), 0x14C: (2, DECODED, ""), 0x14E: (2, "zero", "pad"),
                  0x150: (4, "zero", "RAM pointer")},
}

#: FE10Anim.cms rows (``fe10_anim``): labels, the header's ordinal and model
#: link, and the model's weapon-by-motion variant matrix.
FE10_ANIM_LAYOUTS = {
    "FE10AnimHeader": {0: (4, L, ""), 4: (4, L, ""), 8: (2, DECODED, ""), 10: (2, UNDECODED, "flags"),
                       12: (4, L, ""), 16: (4, L, "")},
    "FE10AnimData": {0: (4, L, ""), 4: (4, L, ""), 8: (4, L, ""), 12: (4, L, ""),
                     16: (8, UNDECODED, "parameters"), 0x18: (432, DECODED, "")},
    "FE10AnimMotion": {0: (4, L, ""), 4: (4, L, ""), 8: (4, UNDECODED, "flags")},
    "FE10AnimWeapon": {0: (4, L, ""), 4: (4, L, "")},
}


def _fe10_battle(cov: FileCoverage, sections) -> None:
    """``FE10Battle.cms``: table heads, the rows' named fields, the three camera
    arrays (each byte a file index, a weight or a group index, checked against
    the tables by the reader) and the string pool."""
    from . import fe10_battle

    data = cov.data
    fe10_battle.read_fe10_battle(data)  # raises on a file the reader does not accept
    symbols = fe8data_symbols(data)
    pool = 0
    for name, size in fe10_battle.TABLE_SIZES.items():
        start = HEADER_SIZE + symbols[name]
        count = _table_head(cov, start, name)
        _fe10_rows(cov, start + 4, count, size, name, FE10_BATTLE_LAYOUTS.get(name, {}))
        pool = max(pool, start + 4 + count * size)
    for name, start, end in sections:
        if name in fe10_battle.RAW_ARRAYS:
            cov.mark(start, end - start, DECODED)
    strings_and_padding(cov, pool, HEADER_SIZE + _u32(data, 4))


def _fe10_anim(cov: FileCoverage, sections) -> None:
    """``FE10Anim.cms``: four tables (the model table has no head) and the string pool."""
    from . import fe10_anim

    data = cov.data
    pool = 0
    for table in fe10_anim.read_fe10_anim(data).tables:
        if not table.records:
            continue
        first = table.records[0].address
        if table.name != "FE10AnimData":
            _table_head(cov, first - 4, table.name)
        _fe10_rows(cov, first, len(table.records), table.record_size, table.name, FE10_ANIM_LAYOUTS[table.name])
        pool = max(pool, first + len(table.records) * table.record_size)
    strings_and_padding(cov, pool, HEADER_SIZE + _u32(data, 4))


def _fe10_conversation(cov: FileCoverage, sections) -> None:
    """``FE10Conversation.cms`` (``fe10_conversation_data``, which reads every
    table and string back byte for byte): all fields are named but the info
    records' +0x2C number (1-3)."""
    from . import fe10_conversation_data as conv

    data = cov.data
    tables = conv.read_conversation_data(data)
    symbols = fe8data_symbols(data)
    data_end = HEADER_SIZE + _u32(data, 4)
    for record in tables.info:
        cov.mark(record.offset, conv.INFO_SIZE, DECODED)
        cov.mark(record.offset + 0x2C, 4, UNDECODED, "CONV_INFO_DATA +0x2C number (1-3)")
    for name in (conv.INFO_SYMBOL, conv.FE8_YELL_SYMBOL):
        cov.mark(HEADER_SIZE + symbols[name], 4, DECODED)
    start = HEADER_SIZE + symbols[conv.FE8_YELL_SYMBOL] + 4
    for i in range(len(tables.fe8_yells)):
        at = start + i * conv.FE8_YELL_SIZE
        cov.mark(at, conv.FE8_YELL_SIZE, DECODED)
        for gap in (0x0C, 0x14, 0x1C):
            cov.zero(at + gap, 4, "CONVERSATION_FE8_YELL_DATA null word")
    mini = HEADER_SIZE + symbols[conv.MINI_YELL_SYMBOL]
    cov.mark(mini, 4, DECODED)
    for character in tables.mini_yells:  # PID, partner count, file, then (partner, said, answered)
        cov.mark(character.offset, 12 + 12 * len(character.partners), DECODED)
    strings_and_padding(cov, HEADER_SIZE, data_end)


#: Radiant Dawn containers with a field-level rule, by a symbol they export.
_FE10_FIELD_RULES = {"FE10BUnit": _fe10_battle, "FE10AnimHeader": _fe10_anim,
                     "CONV_INFO_DATA": _fe10_conversation}


def fe8data_symbols(data: bytes) -> dict:
    from .fe8data import symbol_offsets

    return symbol_offsets(data)


@handles("fe10 container", _is_fe10_container)
def fe10_container(cov: FileCoverage, walker: Walker) -> None:
    """Radiant Dawn's decompressed ``.cms`` data files (``FE10Data``, ``FE10Anim``, ``cp_data``...):
    the same relocatable container as ``FE8Data.bin``. The container structure, every listed pointer
    and the text it points at are decoded. Files with a rule in :data:`_FE10_FIELD_RULES` (and
    ``FE10Growth``, ``FE10Effect``) get their records placed field by field; any byte of an export
    left unplaced is counted as undecoded under ``<export> records``."""
    data = cov.data
    sections = hsdarc(cov)
    data_end = HEADER_SIZE + _u32(data, 4)
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
    names = {name for name, _s, _e in sections}
    for symbol, rule in _FE10_FIELD_RULES.items():
        if symbol in names:
            rule(cov, sections)
    if "FE10PersonGrowth" in names:
        _fe10_growth(cov)
    if "EffectData" in names:
        _fe10_effects(cov)
    for name, start, end in sections:
        at = start
        while at < end:
            if cov.status[at] != UNCLASSIFIED:
                at += 1
                continue
            run = at
            while run < end and cov.status[run] == UNCLASSIFIED:
                run += 1
            cov.mark(at, run - at, UNDECODED, f"{name} records")
            at = run


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
@handles("soundroom.bin", lambda n, d: _base(n) == "soundroom.bin")
def soundroom_file(cov: FileCoverage, walker: Walker) -> None:
    from . import soundroom

    entries = soundroom.read_soundroom(cov.data)
    _roundtrip(cov, soundroom.build_soundroom(entries, cov.data))
    cov.fill(DECODED)


@handles("facedata.bin", lambda name, data: _base(name) == "facedata.bin")
def facedata(cov: FileCoverage, walker: Walker) -> None:
    from . import face_data

    face_data.read_face_data(cov.data)
    cov.fill(DECODED)  # CONVERSATION_RENDERING: every byte decoded


def _is_rect(name: str, data: bytes) -> bool:
    base = _base(name)
    return base == "rect.bin" or (base.startswith("rect") and _ext(name) == "bin")


@handles("rect", _is_rect)
def rect_file(cov: FileCoverage, walker: Walker) -> None:
    """``s/rect.bin`` and the ``window``/``ending`` rect files (RECT_NOTES)."""
    from . import rect

    data = cov.data
    try:
        rebuilt = rect.build_rect(rect.parse_rect(data))
    except rect.RectError:
        rebuilt = None
    if rebuilt != data:
        _rd_rect(cov)
        return
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


def _rd_rect(cov: FileCoverage) -> None:
    """Radiant Dawn's rect layouts (``fe10_rect``): the PoR container with a
    0x30-byte text box and a new kind 7. Blocks no export names (three forest
    copies in ``s/rect.bin``) are kept but never reached by a lookup."""
    from . import fe10_rect

    data = cov.data
    _roundtrip(cov, fe10_rect.build_editable_rect(fe10_rect.read_editable_rect(data)))
    for _name, start, _end in hsdarc(cov):
        cov.mark(start, 20, DECODED)
        cov.mark(start + 0x0D, 1, UNREAD, "descriptor +0x0D")
        count = data[start + 4]
        cov.mark(start + 20, 4 * count, DECODED)
        for i in range(count):
            layer = HEADER_SIZE + _u32(data, start + 20 + 4 * i)
            kind = data[layer]
            length = 10 + 8 * _u16(data, layer + 8) if kind == 4 else fe10_rect._SIZES[kind]
            cov.mark(layer, length, DECODED)
    end = HEADER_SIZE + _u32(data, 4)
    pool = max((i for i in range(HEADER_SIZE, end) if cov.status[i] != UNCLASSIFIED), default=HEADER_SIZE)
    for i in range(HEADER_SIZE, pool):
        if cov.status[i] == UNCLASSIFIED and data[i]:
            cov.mark(i, 1, UNREAD, "rect block no export names")
    strings_and_padding(cov, HEADER_SIZE, end)


@handles("tut_data", lambda name, data: _base(name).startswith("tut_data"))
def tut_data(cov: FileCoverage, walker: Walker) -> None:
    """Tutorial list (``tut_data.py``): head, three label tables and the 24-byte ``TUT_DATA``
    rows (20 bytes on the Japanese disc, which has no Easy mode) (id, category/chapter/initial keys, display order, per-difficulty start flags,
    title key, script and function), all read by the tutorial browser or ``reinit_party_struct``."""
    from . import tut_data as td

    _roundtrip(cov, td.build_tut_data(td.read_tut_data(cov.data)))
    cov.fill(DECODED)
    head = HEADER_SIZE + td._symbols(cov.data, _u32(cov.data, 4), _u32(cov.data, 8), 5)["TutDataHead"]
    cov.zero(head, 4, "TutDataHead +0")


@handles("client.bin", lambda name, data: _base(name) == "client.bin")
def client_bin(cov: FileCoverage, walker: Walker) -> None:
    """A GBA program (ARM branch, Nintendo logo, title ``FIREEMBLEM6``, code
    ``AFEJ01``): the image the game sends to a linked Game Boy Advance. The
    0xC0-byte cartridge header is the public GBA format; the program is not
    disassembled."""
    cov.mark(0, 0xC0, DECODED)
    cov.mark(0xC0, len(cov.data) - 0xC0, UNDECODED, "GBA program body (not disassembled)")


@handles("staffroll", lambda name, data: _base(name) == "staffrolldata.bin")
def rd_staffroll_timings(cov: FileCoverage, walker: Walker) -> None:
    """Radiant Dawn's ``StaffRollData.bin``: 16 named words (``fe10_staffroll.TIMINGS``)."""
    from . import fe10_staffroll as sr

    data = cov.data
    for name, start, _end in hsdarc(cov):
        cov.mark(start, 4, DECODED if name in sr.TIMINGS else UNDECODED, name)
    strings_and_padding(cov, HEADER_SIZE, HEADER_SIZE + _u32(data, 4))


@handles("staffroll", lambda name, data: _base(name).startswith("staffroll"))
def staffroll(cov: FileCoverage, walker: Walker) -> None:
    """Staff credits (``staffroll.py``): build time, author, line count, 12-byte rows of three
    string pointers, the sorted string pool; read by ``draw_staffroll_ui``."""
    from . import staffroll as sr

    _roundtrip(cov, sr.build_staffroll(sr.read_staffroll(cov.data)))
    cov.fill(DECODED)


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


#: zdbx folders and files decoded field by field (zdbx.py and the battle_* modules), and the UI /
#: scene layouts of research/docs/toInclude/dbx_ui_layouts.md (battle HUD, system desktop, lens
#: flare, the battle tool's windows and preview scene).
DBX_DECODED = ("zu/", "xwp/", "zbg/", "xcam/", "zdbx/camera.dbx", "zdbx/joblist.dbx", "zdbx/weaponlist.dbx",
               "zdbx/skill.dbx", "zdbx/param.dbx", "zdbx/effectlist.dbx", "zdbx/classlist.dbx", "zdbx/bglist.dbx",
               "zdbx/battle.dbx", "zdbx/system.dbx", "zdbx/lensflare.dbx", "ztool/")
#: ztool windows with no loader in the US executable (variants of the win4 layout).
DBX_NO_LOADER = ("ztool/batwin.dbx", "ztool/win4.dbx")


def _dbx_lines(data: bytes):
    pos = 0
    for line in data.split(b"\n"):
        yield pos, line
        pos += len(line) + 1


@handles("dbx", lambda name, data: _ext(name) == "dbx")
def dbx_file(cov: FileCoverage, walker: Walker) -> None:
    full = cov.name.lower().replace("\\", "/")
    path = full.split(":", 1)[-1]
    if not any(f"/{p}" in f"/{path}" or f"/{p}" in f"/{full}" for p in DBX_DECODED):
        cov.fill(UNDECODED, f"dbx {path.split('/')[0]}/{'*' if '/' in path else path}")
        return
    if any(f"/{p}" in f"/{path}" or f"/{p}" in f"/{full}" for p in DBX_NO_LOADER):
        cov.fill(PLAUSIBLE, "ztool window with no loader found (win4 layout variant)")
        return
    cov.fill(DECODED)
    for pos, line in _dbx_lines(cov.data):
        key = line.strip().split(b"\t", 1)[0].split(b" ", 1)[0]
        if key == b"current":        # button +0xB8: stored, never read
            cov.mark(pos, len(line), UNREAD, "Button current (never read)")
        elif key == b"flareNum":     # fetched, but the flare loop is fixed at 16
            cov.mark(pos, len(line), UNREAD, "LensFlare flareNum (loop fixed at 16)")


# ------------------------------------------------------------------ fonts, media, sound

def _is_font(name: str, data: bytes) -> bool:
    if _ext(name) == "gcf":
        return True
    # Radiant Dawn: every Fonts/*.cms (system, talk, alpha, ruby, debug...) is the same font file
    return name.endswith("#") and (_base(name) == "system.cms" or "fonts/" in name.replace("\\", "/").lower())


@handles("gcf font", _is_font)
def gcf_font(cov: FileCoverage, walker: Walker) -> None:
    from . import fe9_font

    fe9_font.GameFont(cov.data)
    cov.fill(DECODED)  # FONT_NOTES: every header and glyph byte labelled


@handles("stm", lambda name, data: _ext(name) == "stm")
def stm_file(cov: FileCoverage, walker: Walker) -> None:
    from . import stm

    stm.read_stm(io.BytesIO(cov.data))
    cov.fill(DECODED)


@handles("brstm", lambda name, data: data[:4] == b"RSTM")
def brstm_file(cov: FileCoverage, walker: Walker) -> None:
    from . import brstm

    brstm.read_info(cov.data)
    cov.fill(DECODED)


@handles("brsar", lambda name, data: data[:4] == b"RSAR")
def brsar_file(cov: FileCoverage, walker: Walker) -> None:
    from . import brsar

    archive = brsar.read_brsar(cov.data)
    cov.mark(0, 0x40, DECODED)
    for section in archive.sections:
        status = DECODED if section.magic == "SYMB" else UNDECODED
        cov.mark(section.offset, section.size, status, f"BRSAR {section.magic}")


@handles("thp", lambda name, data: data[:4] == b"THP\0")
def thp_file(cov: FileCoverage, walker: Walker) -> None:
    from . import thp

    thp.read_info(io.BytesIO(cov.data))
    cov.fill(DECODED)


@handles("bnr", lambda name, data: _ext(name) == "bnr")
def banner(cov: FileCoverage, walker: Walker) -> None:
    if cov.data[0x40:0x44] == b"IMET":
        _wii_banner(cov, walker)
        return
    if cov.data[:4] not in (b"BNR1", b"BNR2"):
        raise ValueError("not a BNR1/BNR2 banner")
    cov.fill(DECODED)  # public GameCube banner format


def _wii_banner(cov: FileCoverage, walker: Walker) -> None:
    """The Wii ``opening.bnr`` (``wii_banner``): IMET header, U8 archive, IMD5/LZ77 parts. The
    pictures are walked as TPLs; the layout, animation and BNS sound are the public Wii formats."""
    from . import wii_banner as wb

    data = cov.data
    _roundtrip(cov, wb.build_banner(wb.read_banner(data)))
    cov.fill(DECODED)
    banner = wb.read_banner(data)
    for part in ("icon.bin", "banner.bin"):
        for entry in banner.pictures(part):
            walker.child(f"{cov.name}:{part}:{entry.path}", entry.data)


_POOL_FILES = {"dictionary.bin", "dictionaryf.bin", "conversationroom.bin", "fe10epilogue.bin", "fe10intro.bin",
               "caption_data.bin"}


def _pool_base(name: str) -> str:
    """The pool file's name without the PAL language prefix (``d_caption_data.bin``)."""
    base = _base(name)
    return base[2:] if re.fullmatch(r"[defis]_caption_data\.bin", base) else base


@handles("fe10 tables", lambda name, data: _pool_base(name) in _POOL_FILES)
def fe10_tables(cov: FileCoverage, walker: Walker) -> None:
    """Radiant Dawn's sorted-pool table files (``pool_file``) and their codecs: the glossary,
    Conversation Room lists, endings, class introductions and movie subtitles."""
    from . import fe10_captions, fe10_conversation_room, fe10_dictionary, fe10_epilogue, fe10_intro

    data, base = cov.data, _pool_base(cov.name)
    codecs = {
        "dictionary.bin": (fe10_dictionary.read_dictionary, fe10_dictionary.build_dictionary),
        "dictionaryf.bin": (fe10_dictionary.read_dictionary_flags, fe10_dictionary.build_dictionary_flags),
        "conversationroom.bin": (fe10_conversation_room.read_conversation_room,
                                 fe10_conversation_room.build_conversation_room),
        "fe10epilogue.bin": (fe10_epilogue.read_epilogues, fe10_epilogue.build_epilogues),
        "fe10intro.bin": (fe10_intro.read_intros, fe10_intro.build_intros),
        "caption_data.bin": (fe10_captions.read_captions, fe10_captions.build_captions),
    }
    read, build = codecs[base]
    document = read(data)
    _roundtrip(cov, build(document))
    cov.mark(0, 0x14, DECODED)
    cov.mark(0x14, 4, UNREAD, "header +0x14")
    cov.mark(0x18, 8, DECODED)
    end = HEADER_SIZE + _u32(data, 4)
    cov.mark(end, len(data) - end, DECODED)
    if base == "dictionary.bin" and document.relation_size == 24:
        at = HEADER_SIZE + 4 + 8 * len(document.categories) + 4 + 20 * len(document.people) + 4
        for i in range(len(document.relations)):
            cov.mark(at + 24 * i + 0x10, 4, UNREAD, "relation Japanese label point (RFEE01 reads +0x14)")
    if base == "dictionary.bin":
        at = (HEADER_SIZE + 4 + 8 * len(document.categories) + 4 + 20 * len(document.people) + 4
              + document.relation_size * len(document.relations) + 4 + 16 * len(document.affiliations) + 4)
        for i, term in enumerate(document.terms):
            if term.picture:
                cov.mark(at + 16 * i + 12, 4, UNDECODED, "term picture name (no reader traced)")
    if base == "fe10intro.bin":
        for i in range(len(document.entries)):
            cov.mark(HEADER_SIZE + 4 + 64 * i + 0x28, 4, UNDECODED, "intro +0x28 (300 on every record)")
    for i in range(HEADER_SIZE, end):
        if cov.status[i] == UNCLASSIFIED:
            cov.mark(i, 1, PADDING if data[i] == 0 else DECODED)


@handles("MovieCaptionData.bin", lambda name, data: _base(name) == "moviecaptiondata.bin")
def por_movie_captions(cov: FileCoverage, walker: Walker) -> None:
    """Path of Radiance's European movie subtitles (``por_captions``): the movie list and the
    16-byte caption rows (message key, start and end in milliseconds, placement), read by the THP
    player at ``0x802070EC`` (GFEP01)."""
    from . import por_captions as pc

    data = cov.data
    _roundtrip(cov, pc.build_captions(pc.read_captions(data)))
    cov.mark(0, 0x10, DECODED)
    cov.zero(0x10, 0x10, "header +0x10..+0x1F")
    end = HEADER_SIZE + _u32(data, 4)
    cov.mark(end, len(data) - end, DECODED)
    for i in range(HEADER_SIZE, end):
        if cov.status[i] == UNCLASSIFIED:
            cov.mark(i, 1, PADDING if data[i] == 0 and i >= end - 3 else DECODED)


@handles("gmap curve", lambda name, data: "gmap/curve/" in name.replace("\\", "/").lower() and _ext(name) == "bin")
def gmap_curve(cov: FileCoverage, walker: Walker) -> None:
    """World-map route curves and line styles (``fe10_gmap_curve``)."""
    from . import fe10_gmap_curve as gc

    data = cov.data
    if _base(cov.name).startswith("linedefine"):
        _roundtrip(cov, gc.build_line_define(gc.read_line_define(data)))
        cov.mark(0, 16, DECODED)
        cov.zero(16, len(data) - 16, "linedefine converted flag (set at load)")
        return
    curve = gc.read_curve(data)
    _roundtrip(cov, gc.build_curve(curve))
    cov.fill(DECODED)
    cov.zero(0, 4, "curve +0")
    name_end = 4 + len(curve.name)
    cov.zero(name_end, 0x1C - name_end, "curve name padding")
    cov.zero(0x2C, 4, "curve points address (set at load)")


@handles("filler", lambda name, data: _base(name) == "zzzzzzzz.zzz")
def disc_filler(cov: FileCoverage, walker: Walker) -> None:
    """``zzzzzzzz.zzz``: 32 KiB of zeros that no code names, sorted last on the disc."""
    cov.zero(0, len(cov.data), "disc filler", nonzero=UNDECODED)


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
        cov.mark(info, 40, DECODED)  # SNDADPCMinfo: count, initial/loop ps, loop history, coefficients
        pos += 32
    cov.mark(pos, 4, DECODED)
    cov.fill(PADDING, only_zero=True)


@handles("musyx pool", lambda name, data: _ext(name) == "pool")
def musyx_pool(cov: FileCoverage, walker: Walker) -> None:
    """Four chains (macros, curve tables, keymaps, layers), each of
    ``u32 size, u16 id, u16 pad`` entries ended by ``0xFFFFFFFF``. Every macro
    opcode the game's interpreter handles is decoded (musyx_macro.py); curve
    tables are linear ADSRs, layers 12-byte entries (musyx.py)."""
    from .musyx_macro import SPECS
    data = cov.data
    offsets = struct.unpack_from(">4I", data, 0)
    cov.mark(0, 16, DECODED)
    for kind, start in zip(("macro", "curve", "keymap", "layer"), offsets):
        pos = start
        while start and pos + 4 <= len(data):
            size = _u32(data, pos)
            if size == 0xFFFFFFFF or size < 8:
                cov.mark(pos, 4, DECODED)
                break
            cov.mark(pos, 6, DECODED)
            cov.zero(pos + 6, 2, f"{kind} pad")
            if kind == "macro":
                for c in range(pos + 8, pos + size - 7, 8):
                    op = data[c + 3] & 0x7F
                    cov.mark(c, 8, DECODED if op in SPECS else UNDECODED,
                             "" if op in SPECS else f"macro command op {op:#04x}")
            elif kind == "curve":
                cov.mark(pos + 8, size - 8, DECODED)  # little-endian linear ADSR
            elif kind == "layer":
                count = _u32(data, pos + 8)
                cov.mark(pos + 8, 4, DECODED)
                for e in range(pos + 12, pos + 12 + 12 * count, 12):
                    cov.mark(e, 9, DECODED)
                    cov.zero(e + 9, 3, "layer entry pad")
            else:
                cov.mark(pos + 8, size - 8, UNDECODED, "keymap")
            pos += size
    cov.fill(PADDING, only_zero=True)


@handles("musyx proj", lambda name, data: _ext(name) == "proj")
def musyx_proj(cov: FileCoverage, walker: Walker) -> None:
    """Group chain: header, id lists (musyx_macro.parse_id_list), FX tables,
    song pages and MIDI setups (musyx.py)."""
    from .musyx_macro import id_list_size
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
                cov.mark(lst, id_list_size(data, lst), DECODED)
        if not next_offset or next_offset == 0xFFFFFFFF or next_offset <= offset:
            break
        offset = next_offset
    # What is left: 0xFF end markers (page tables, group chain) and zero alignment.
    i = 0
    while i < len(data):
        if cov.status[i] == UNCLASSIFIED and data[i] == 0xFF:
            j = i
            while j < len(data) and cov.status[j] == UNCLASSIFIED and data[j] == 0xFF:
                j += 1
            cov.mark(i, j - i, DECODED)
            i = j
        else:
            i += 1
    cov.fill(PADDING, only_zero=True)
    cov.fill(UNDECODED, "proj (not parsed)")


@handles("musyx tables", lambda name, data: _ext(name) in ("stbl", "etbl"))
def musyx_tables(cov: FileCoverage, walker: Walker) -> None:
    cov.fill(DECODED)  # song and FX name tables (MUSIC_NOTES)


@handles("musyx slib", lambda name, data: _ext(name) == "slib")
def musyx_slib(cov: FileCoverage, walker: Walker) -> None:
    """Song blobs (musyx_song.py): headers, tracks, note/controller events and
    the pitch-bend/modulation delta streams. A stream that does not end
    inside its blob is left undecoded."""
    from .musyx_song import STREAM_END, parse_song, split_slib, stream_size
    data = cov.data
    for blob, size in split_slib(data):
        song = blob + 0x20
        pattern_table = _u32(data, song + 4)
        for i in range(len(parse_song(data, blob, size).patterns)):  # patterns the tracks use
            off = _u32(data, song + pattern_table + 4 * i)
            for stream_off, label in ((_u32(data, song + off + 4), "pitch-bend stream"),
                                      (_u32(data, song + off + 8), "modulation stream")):
                if stream_off:
                    n = stream_size(data, song + stream_off, blob + size)
                    ok = data[song + stream_off + n - 2:song + stream_off + n] == STREAM_END
                    cov.mark(song + stream_off, n, DECODED if ok else UNDECODED, "" if ok else label)
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
        # Initialized to zero and copied through save/load; no US gameplay reader.
        cov.mark(s + 0x43, 1, RESERVED, "unused SYSF +0x43")
        cov.zero(s + 0x45, 2, "SYSF +0x45")
        p = off + sf.STREAM_START + 4
        # Slots 5-7 are addressable through BMGetValue/BMSetValue, but no
        # shipped US script uses them and every sampled save leaves them zero.
        cov.mark(p + 0x0A, 6, RESERVED, "unused BMST value slots 5-7")
        opts = p + 0x9C
        for i, known in enumerate((0x1E, 0x00, 0x1D, 0xE0)):
            cov.bits(opts + i, 1, known=known, name=f"option byte {i}")
        cov.zero(opts + 11, 1, "option byte 11")
        m = p + sf.PartyState.SIZE + 4
        cov.zero(m + 0x16, 10, "MDST pad")
        r = m + sf.MapState.SIZE + 4
        for unit in block.units:
            if unit is None:
                r += 2
                continue
            # The US build does not consume either byte in gameplay. +0x19D
            # has a debug-editor setter; +0x235 has a dormant UnitGet selector.
            cov.mark(r + 0x0C, 1, RESERVED, "unused unit +0x19D (debug editor only)")
            cov.mark(r + 0x6F, 1, RESERVED, "unused unit +0x235 (UnitGet 34)")
            # Unused in the US build: zero-initialized and serialized, with no
            # gameplay writer or use in the available scripts. UnitGet can read them.
            cov.mark(r + 0x6A, 2, RESERVED, "unused unit +0x230 (UnitGet 28)")
            cov.mark(r + 0x6C, 2, RESERVED, "unused unit +0x232 (UnitGet 32)")
            cov.zero(r + 0x8B, 4, "unit pad")
            r += sf.UNIT_RECORD_SIZE
        stream_end = off + sf.STREAM_START + len(block.build_stream())
        cov.zero(stream_end, off + size - stream_end, "after the stream")
