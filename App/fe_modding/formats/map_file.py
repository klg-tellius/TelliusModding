"""Parse a chapter's ``map.bin``.

Getting one: each chapter's ``zmap/bmapNN/map.cmp`` is LZ10-compressed (see
:mod:`fe_modding.formats.lz10`) - but what it decompresses *to* is a ``pack``
archive (see :mod:`fe_modding.formats.pak`), not map.bin directly. map.bin is
one of the files inside that archive, alongside the chapter's 3D models
(terrain, trees, water, ...) referenced by mapbuilddesc below::

    map.cmp --lz10.decompress--> pack archive --pak.read_pak_entries--> map.bin (+ models)

Confirmed against a real file (bmap01): mapbuilddesc's placed-object names
(``tree_01``, ``flower_01``, ``bmap01_water0``, ...) matched actual model
entries in that same archive.

map.bin itself is a generic labeled-section container: a header gives the size and
where the section table starts; the section table is a list of
(address, name) pairs terminated by a sentinel address, with the names
themselves stored as NUL-terminated strings after the table. Each named
section is then parsed according to what's known about that section - sizes
for the grid-shaped sections (panel index, roof/base variants, the three
link grids) come from the capacity section, which must exist and is always
read first.

Everything below was reverse-engineered by inspecting the game's files
directly - field names like "extra" or "grid" describe where the data lives,
not necessarily what it means. Where a field's purpose isn't understood it's
kept as a raw tuple of ints/floats rather than guessed at.

Field-level semantics for every section (what each byte actually means, not
just its offset) were added later, sourced from the user's own prior
research (``mapData.xlsx``, in the same external FE9 research folder as
`dispo.py`'s original source scripts, the "map.bin entry" sheet) the same
way `dispo.py`'s original reverse-engineering and
`event_script.py`'s trigger-type table were carried over from that same
external FE9 folder - not independently re-derived here. Confidence varies
by field: `MapObject`'s six floats and `UniquePanel`'s four elevations are
unambiguous (the byte math lines up exactly with the struct formats already
used below), but several flag-bit meanings in `mapbuilddesc` are hedged by
the source itself ("unclear", "sometimes not used", "unsure why, pretty
random") and are kept as raw per-byte ints with the known bit meanings only
in comments, rather than being turned into named boolean fields that would
overstate how settled they are.

Write support (added still later, for a viewer/editor GUI) follows the same
patch-in-place discipline as every other editable format here:
`patch_*_field()` overwrites one field's existing bytes at that record's own
`address`, never changing the file's size or any other record. Two kinds of
field are deliberately left out of every patch table: pointers
(`MapObject.filename`'s backing `name_ptr`, `UniquePanel.terrain_type_ptr`)
and structural counts (`MapCapacity.x_size`/`y_size`/`build_desc_count`/
`build_inst_count`, which every other section's array lengths and grid
dimensions are derived from at read time - changing one after the fact
would desync it from data that's already been sized against the old value).
Grid-shaped sections (`panel_index*`, `link`/`link_at`/`link_abs`) are
rewritten together by :func:`resize_grid`; unlike ordinary field edits,
changing the dimensions is a structural operation.

Applying this caught one real bug: `MapCapacity`'s fifth field was being read
as a plain uint32 and treated as "unknown" - the source material's map.bin
sheet just called it "Scale unit? (always 2000...)", but a separate note
(the same research folder's LoadMapNote.txt, an independent PowerPC
disassembly of the game's actual map-loading code) said this word gets
*interpreted as a float* at runtime. Reading the real value as a big-endian
float32 instead of an int gives exactly `2000.0` on a real chapter file,
confirmed against `zmap/bmap01/map.cmp` - so `scale_unit` is a float field,
fixed here rather than left as a suspiciously large integer.

Radiant Dawn's map.bin is the same container with renamed sections, each
prefixed with the map folder (``bmap0101:mapdata``), wider records and a
merged header section; :class:`MapLayout` describes both games and
:func:`map_layout` picks one from a file's own section names. Every function
here takes Path of Radiance's section names (``mapcapacity``,
``panelindexRoof``...) and resolves them through the file's layout, so the
editors work on either game. See ``research/rd/MAP_NOTES.md``.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Optional

from .common import HEADER_SIZE, read_section_table


class MapFileError(Exception):
    pass


@dataclass(frozen=True)
class MapLayout:
    """Where a game keeps each map.bin section and how wide its records are.

    ``sections`` maps Path of Radiance's section name (the name every
    function in this module takes) to ``(name in the file, byte offset in
    that section)``; Radiant Dawn keeps the capacity, ``mapextra`` and
    ``mapgrid`` records together in one ``mapdata`` section."""
    game: str
    sections: dict
    prefix: str = ""          # Radiant Dawn: "bmap0101:"
    size_format: str = ">HH"  # x_size, y_size at size_at in the capacity record
    size_at: int = 0
    desc_size: int = 32       # mapbuilddesc record
    inst_size: int = 12       # mapbuildinst record
    link_count: str = ">H"    # record count heading maplink/maplinkAt/maplinkAbs
    half_round_up: bool = True  # mapextra half sizes: ceil (FE9) or floor (FE10) of the size / 2
    decoded_light: bool = True  # maplight / mapfog in FE9's layout

    def __hash__(self) -> int:
        return hash((self.game, self.prefix))

    def file_name(self, name: str) -> str:
        """The section name stored in the file for ``name`` (a PoR name or already a file name)."""
        if self.prefix and name.startswith(self.prefix):
            return name
        return self.prefix + self.sections.get(name, (name, 0))[0]

    def offset(self, name: str) -> int:
        return self.sections.get(name, (name, 0))[1]

    def canonical(self, file_name: str) -> str:
        """Path of Radiance's name for a section name read from the file."""
        short = file_name[len(self.prefix):] if self.prefix and file_name.startswith(self.prefix) else file_name
        for name, (stored, offset) in self.sections.items():
            if stored == short and offset == 0:
                return name
        return short


_FE9_SECTIONS = {name: (name, 0) for name in (
    "mapcapacity", "mapbuilddesc", "mapbuildinst", "panelindex", "uniquepanel", "panelindexRoof",
    "uniquepanelRoof", "panelindexBase", "uniquepanelBase", "maplight", "mapfog", "mapgrid", "mapextra",
    "maplink", "maplinkAt", "maplinkAbs")}

POR_LAYOUT = MapLayout("fe9", _FE9_SECTIONS)

# Radiant Dawn: mapdata = version byte (2/3/4), 0, x_size u8, y_size u8, desc count u16, inst count u16,
# scale f32, then FE9's mapextra (12 bytes at +0x0C) and mapgrid (4 bytes at +0x18); versions 3 and 4
# append one and two more words. Its mapdesc records add 4 bytes and mapinst records grow to 20.
_FE10_SECTIONS = {
    "mapcapacity": ("mapdata", 0), "mapextra": ("mapdata", 0x0C), "mapgrid": ("mapdata", 0x18),
    "mapbuilddesc": ("mapdesc", 0), "mapbuildinst": ("mapinst", 0),
    "panelindex": ("panelindex", 0), "uniquepanel": ("uniquepanel", 0),
    "panelindexRoof": ("roofindex", 0), "uniquepanelRoof": ("roofpanel", 0),
    "panelindexBase": ("baseindex", 0), "uniquepanelBase": ("basepanel", 0),
    "maplight": ("maplight", 0), "mapfog": ("mapfog", 0),
    "maplink": ("maplink", 0), "maplinkAt": ("maplinkAt", 0), "maplinkAbs": ("maplinkAbs", 0),
}


def rd_layout(prefix: str = "") -> MapLayout:
    """Radiant Dawn's layout; ``prefix`` is the map folder plus a colon (``bmap0101:``)."""
    return MapLayout("fe10", _FE10_SECTIONS, prefix=prefix, size_format=">BB", size_at=2, desc_size=36,
                     inst_size=20, link_count=">I", half_round_up=False, decoded_light=False)


def _layout_from_names(names) -> MapLayout:
    for name in names:
        head, colon, tail = name.rpartition(":")
        if tail == "mapdata":
            return rd_layout(head + colon)
    return POR_LAYOUT


def map_layout(data: bytes) -> MapLayout:
    """The layout of a map.bin, recognised from its section names."""
    named = read_section_table(io.BytesIO(data), _sections(data)[1], len(data))
    return _layout_from_names(name for _address, name in named)


@dataclass(frozen=True)
class MapCapacity:
    x_size: int
    y_size: int
    build_desc_count: int
    build_inst_count: int
    scale_unit: float  # a float32, always seen as 2000.0; the engine uses 1/scale_unit elsewhere
    address: int = 0


@dataclass(frozen=True)
class MapObject:
    """One entry of mapbuilddesc: a placed object (prop/building/decoration).

    The three offset/size float triples are in (x, y, z) order - a Y-up 3D
    engine where x/z are the horizontal plane and y is height, same
    convention as `skeleton.py`'s bind-pose data. This corrects an earlier
    (x, z, y) labeling that was carried over unverified from the source
    research's own spreadsheet column headers (`mapData.xlsx`'s "map.bin
    entry" sheet labels the columns "offset z for origin" then "offset y for
    origin", in that order) - the byte *positions* read were always right
    (every value round-trips correctly), only the *names* attached to the
    2nd and 3rd float of each triple were swapped from what the data itself
    shows. Caught by two independent, converging checks: (1) terrain/water
    objects' `size_x` and `size_z` both correlate with `mapcapacity`'s grid
    dimensions (`x_size`/`y_size` respectively) at a comparable (noisy, but
    same order of magnitude) scale across 30 real chapters, while `size_y`
    (the file's middle float of the triple) doesn't correlate with either
    and runs an order of magnitude smaller (tens, not hundreds) - consistent
    with being height, which has no reason to track a 2D tile-grid's row/
    column counts; (2) ordinary props confirm the same pattern independently
    - e.g. a real `woods_selinos_02` entry has size (26.96, 8.81, 26.40) by
    file order: the 1st and 3rd floats are close to each other (a roughly
    round horizontal footprint) and the 2nd is visibly smaller - exactly
    what a bush's (width, height, depth) would look like, not
    (width, depth, height). This relabeling is about which name attaches to
    which already-correctly-read byte, not about the `mapbuildinst`
    placement transform - that was a separate, later investigation, now
    resolved (see `MapBuildInstance.world_transform()`).

    flag_bits_a/b/c are the three raw flag bytes rather than named booleans,
    since several of their bit meanings are hedged by the source research
    itself:
      - flag_bits_a: bit 7-6 = map-wide object; other bits unused. CONFIRMED
        (a follow-up pass) to specifically mean "this object *is* the map's
        own base terrain/water-plane model", not just "a large object" as
        the vague name suggested - checked against all 79 real objects with
        either bit set across every real chapter map in the game, and every
        single one is literally named after its own map (`bmap07`,
        `bmap07_water0`, ...) or the placeholder name `test`; both bits are
        always set together (raw value 3), never independently. Real object
        *size* doesn't discriminate this at all (some ordinary props are far
        larger than these "map-wide" entries) - filename is what does.
      - flag_bits_b: bit 5 places an actor in render sub-list 2 and occurs
        only on castle roofs; bits 2-4 commonly co-occur on invisible goal
        markers across dozens of chapters,
        each literally named after its own win condition -
        `ascendancy_01`, `defense_01`, `attainment_01`, `secession_01`,
        `visit_01`. Bit 3 is their common victory-objective marker. Bit 4
        independently excludes footprint testing, and bit 2 sets actor
        flag 0x400, making material setup use the constant ambient colour
        rather than the map's light record. Bits 6-7 are never set in the
        US, PAL or Japanese retail map corpus.
        bit 1 sets the instance's initial hidden state (all 11 shipped
        users are destroyed-house models); bit 0 suppresses placed-object
        drawing (the four shipped users are rock models).
      - flag_bits_c: bit 7 = ballista/catapult; bit 6 = thicket; bit 5 =
        wall/building (possibly impassable terrain); bit 4 = openable door;
        bit 2 advances the .ga animation timer on each map update and
        staggers identical adjacent instances across animation frames;
        bit 1 = has a matching .ga file - CONFIRMED with zero exceptions:
        checked against every real object across every real chapter map (873
        objects), cross-referenced against the actual archive contents
        (does a `<filename>.ga` really exist alongside this map.bin) - bit 1
        set means "yes" in 268/268 real cases, bit 1 clear alongside bit 0
        also clear means "no" in 18/18 real cases, no exceptions either way.
        The old "bit 0 = no .ga file" reading is refuted by a later
        876-object US archive census: the bit occurs both with and without
        a matching `.ga` file. Reader scans found no direct or immediate-
        mask test of bit 0 in the US, PAL or Japanese map code, so it is
        treated as ignored legacy data; preserve it for file compatibility.
    effect_type is a bitfield, not an enum. Bit 0 selects one of two actor
    update passes; bit 1 copies roof-panel corner heights into the base
    elevation buffer as well as the combined buffer in
    ``load_uniquepanel_sections``; bit 3 selects an extended frustum-overlap test and is
    also set by the engine for a footprint wider than one tile; bit 4
    excludes footprint and tile-object hit tests; bit 6 suppresses
    placed-object drawing; bit 7 excludes tile-object lookup. Bit 5 selects
    render sub-list 2 and bits 4/5/7 contribute to the optional object sort
    key. Bit 2 is never set in the US, PAL or Japanese retail map corpus.
    """

    offset_x: float
    offset_y: float
    offset_z: float
    size_x: float
    size_y: float
    size_z: float
    flag_bits_a: int
    flag_bits_b: int
    flag_bits_c: int
    effect_type: int
    filename: str
    address: int = 0
    #: Radiant Dawn's 4 extra bytes: footprint tiles along x and z (``round(size / 5)`` on most
    #: records, see :func:`footprint_tiles`), then two zero bytes. Empty on Path of Radiance.
    footprint: tuple = ()


@dataclass(frozen=True)
class MapBuildInstance:
    """One entry of mapbuildinst: one placed instance of a mapbuilddesc
    object.

    ``angle``, despite being stored as a single byte, is read by the game as
    **unsigned** (0-255), not the signed -128..127 range this project
    originally assumed - confirmed by reading `main.dol`'s own conversion
    code directly (`GAME_NOTES.md` §12, Twentieth finding):
    ``angle_degrees = 360 - (angle * 360) / 256``.

    ``unused``, despite the name (kept for backwards compatibility - it's
    not actually unused), is **not** 4 separate values: the game reads all
    4 bytes together as one big-endian 32-bit word. That combined value is
    the placed object's vertical (Y) world-position input - see
    :meth:`world_transform`. This was previously documented as "never
    independently explained"; it's now confirmed by reading the
    placement-record constructor (`FUN_8001b84c` in `main.dol`) directly.

    **The word is a raw float32 bit pattern, not an integer that gets
    numerically converted** - this corrects the disassembly session's own
    first reading (which took Ghidra's decompiled `(float)value` cast at
    face value as a numeric int-to-float conversion - a well-known
    decompiler ambiguity for the common "store an int, then load it back
    through a float register from the same address" pattern, which Ghidra
    can render as a plain cast either way). Caught by cross-checking
    against real chapter data, this project's standing discipline for any
    finding before it goes in as fact: numeric conversion of `height_raw()`
    produced placement heights in the *billions* of world units on real,
    ordinary props (physically impossible - every other confirmed
    height/offset value in this format, e.g. `MapObject.offset_y`, is
    O(1) units); reinterpreting the same 4 bytes as a big-endian float32's
    raw bits instead gives small, physically sensible values (-0.01 to
    -0.38 across every distinct real sample in `bmap01`) matching that same
    scale exactly. `height()` (not `height_raw()`) is what
    :meth:`world_transform` actually uses.

    The (x2, y2) through (end_x2, end_y2) bytes give an inclusive tile
    footprint. The engine tests this rectangle for selected roof, door,
    house, and rock objects when mapextra bit 0x10000000 is set. See
    CHAPTER_DATA_NOTES.md for the engine reader and corpus evidence; the
    older second-placement-point hypothesis has been ruled out.
    """

    x: int  # from the left
    y: int  # from the top
    angle: int  # unsigned 0-255; degrees = 360 - (angle * 360) / 256
    desc_index: int  # index into build_desc
    x2: int
    y2: int
    end_x2: int
    end_y2: int
    unused: tuple[int, int, int, int]  # read together as one big-endian int32 - see world_transform()
    address: int = 0
    # Radiant Dawn's 20-byte record only (0 on Path of Radiance): a lead byte (0 or 1), a signed sub-tile
    # offset along x and y (its scale is not decoded) and a trailing word (0x40000000 on most records).
    lead: int = 0
    offset_x: int = 0
    offset_y: int = 0
    tail: int = 0

    def height_raw(self) -> int:
        """The 4 ``unused`` bytes combined into one big-endian unsigned
        32-bit integer, not 4 separate values - a debugging/round-trip
        accessor. Not what ``world_transform()`` uses for the actual height
        input - see :meth:`height`, and this class's own docstring for why
        a plain numeric conversion of this value is wrong."""
        b0, b1, b2, b3 = (v & 0xFF for v in self.unused)
        return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3

    def height(self) -> float:
        """The 4 ``unused`` bytes reinterpreted as a big-endian float32's
        raw bits (not a numeric conversion of :meth:`height_raw` - see this
        class's own docstring for how that distinction was caught against
        real data). This is the actual vertical (Y) world-position input
        :meth:`world_transform` uses."""
        return struct.unpack(">f", struct.pack(">I", self.height_raw()))[0]

    def world_transform(self, map_scale: float, parent_matrix=None):
        """The confirmed placement transform (`GAME_NOTES.md` §12, Twentieth
        finding) as a 4x4 row-major matrix (list of 4 lists of 4 floats),
        composed the same way `main.dol`'s own `FUN_80045d50` builds it:

            world = ParentMatrix @ Translate(pos) @ Scale(map_scale) @
                     Translate(+pivot) @ RotateY(angle_rad) @ Translate(-pivot)

        i.e. the object rotates around the center of its own 5x5-unit tile
        cell, not around its raw placement origin. ``map_scale`` is the
        map-state `+0x6C`: `load_map_data` sets 0.2 for chapter maps and 3.0 for
        battle backdrops (not `MapCapacity.scale_unit`). ``parent_matrix``, if
        given, must be a 4x4 row-major matrix (defaults to identity); the engine's
        is map-state `+0x70`, a 270-degree rotation about X for chapter maps
        (identity for backdrops). The app draws chapter maps at scale 1.0 with no
        rotation, the same picture up to one global transform.

        Confirmed constants: tile scale = 5.0 world units/tile, pivot = 2.5
        (half the tile scale).
        """
        import math

        angle_deg = 360.0 - (self.angle * 360.0) / 256.0
        angle_rad = math.radians(angle_deg)

        tile_scale = 5.0
        pivot = tile_scale / 2.0

        pos_x = tile_scale * self.x
        pos_y = -tile_scale * self.height()
        pos_z = tile_scale * self.y

        def _identity():
            return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]

        def _translate(tx, ty, tz):
            m = _identity()
            m[0][3], m[1][3], m[2][3] = tx, ty, tz
            return m

        def _scale(s):
            m = _identity()
            m[0][0] = m[1][1] = m[2][2] = s
            return m

        def _rotate_y(rad):
            m = _identity()
            c, s = math.cos(rad), math.sin(rad)
            m[0][0], m[0][2] = c, s
            m[2][0], m[2][2] = -s, c
            return m

        def _matmul(a, b):
            return [
                [sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
                for i in range(4)
            ]

        local = _translate(pos_x, pos_y, pos_z)
        local = _matmul(local, _scale(map_scale))
        local = _matmul(local, _translate(pivot, 0.0, pivot))
        local = _matmul(local, _rotate_y(angle_rad))
        local = _matmul(local, _translate(-pivot, 0.0, -pivot))

        if parent_matrix is None:
            return local
        return _matmul(parent_matrix, local)


@dataclass(frozen=True)
class UniquePanel:
    """One entry of uniquepanel/uniquepanelRoof/uniquepanelBase: a tile's
    four corner elevations (signed 16-bit; the terrain mesh height is
    ``-elevation / 400``, exact on every ``uniquepanelBase`` corner of
    bmap01/bmap02; a 400-unit difference between adjacent tiles is
    impassable) plus a trailing field that's only meaningful on the
    base ``uniquepanel`` section itself - there, it's a pointer used to look
    up the tile's terrain type; on the Roof/Base elevation *variant*
    sections it's unused/unconfirmed.

    Per the source research: plain `uniquepanel` holds combined ground+
    object elevation, `uniquepanelBase` is ground elevation alone, and
    `uniquepanelRoof` is building/roof elevation - i.e. the three sections
    are three different elevation layers for the same grid, not duplicates.
    """

    top_left_elevation: int
    top_right_elevation: int
    bottom_left_elevation: int
    bottom_right_elevation: int
    terrain_type_ptr: int
    address: int = 0


@dataclass(frozen=True)
class MapLight:
    enabled: int  # always seen as 1
    angle_y: int  # signed degrees; negated for the renderer's Y rotation
    angle_z: int  # signed degrees; renderer's Z rotation
    model_red: int
    model_green: int
    model_blue: int
    light_red: int
    light_green: int
    light_blue: int
    unused: tuple[int, int, int]
    address: int = 0


@dataclass(frozen=True)
class MapFog:
    enabled: int
    # 0 linear, 1 exponential, 2 exponential-squared, 3 reverse-exponential,
    # 4 reverse-exponential-squared; runtime GX-facing type is code + 1.
    mode_code: int
    start_distance: int  # signed, scaled by 5 * map scale for rendering
    end_distance: int  # signed, scaled by 5 * map scale for rendering
    red: int
    green: int
    blue: int
    unused2: int
    address: int = 0


@dataclass(frozen=True)
class MapGrid:
    unknown: int  # stored RGBA alpha; the known draw path replaces it with SetGrid intensity
    red: int
    green: int
    blue: int
    address: int = 0


@dataclass(frozen=True)
class MapExtra:
    """The source research's column layout (a 2-byte "model_grid_offset"
    field, a 1-byte/2-byte split for half_x_size/half_y_size) was WRONG,
    corrected via real main.dol disassembly (GAME_NOTES.md's Thirtieth
    finding) - the runtime loader (renamed load_map_data, FUN_80041514)
    reads every one of this section's first 8 bytes as eight completely
    independent bytes (lbz/stb, never a combined 16-bit load), only the
    trailing 4 bytes are read as one real uint32.

    Confirmed against all 41 real chapter maps with a resolvable capacity:
    half_x_size == ceil(x_size/2) and half_y_size == ceil(y_size/2) with
    zero exceptions once byte 3 (half_y_size) is read on its own instead of
    merged with byte 4 - the old merged reading is exactly why this never
    correlated cleanly with y_size before. grid_buffer is now fully
    confirmed too (not just a source-notes label): the runtime map-state
    struct's own grid_buffer field (get_map_grid_buffer, FUN_80047af8) is
    read by load_map_panel_data to compute the tactical grid's own usable
    tile bounds - min_x=min_y=grid_buffer, max_x=x_size-grid_buffer,
    max_y=y_size-grid_buffer - a real inset margin around the map edge, not
    a placement/positioning value.

    panel_offset_x/panel_offset_y (bytes 0-1, the old "model_grid_offset")
    are read together by a function (FUN_800efee0, uncalled by direct
    reference - reached only through the same kind of indirect dispatch
    documented elsewhere in this project) that feeds them through the
    map's own transform matrix into what reads as a 2D UI panel/window
    draw call, not a 3D world-position calculation - genuinely unconfirmed
    whether this has anything to do with where the tactical grid sits in
    the world (the name is kept only for continuity with prior docs; do
    not treat it as confirmed to mean "grid world-space offset").
    texture_projection_extent_x2 (byte 4) is a real, independent field -
    not part of half_y_size as previously modeled. The global last-record
    map texture callback reads the map-state copy of this byte and uses
    `(value >> 1)` as its projection extent; for bmap01, 0x40 produces the
    live-captured texture6 matrix extent 32. unknown_tail (bytes 8-11)
    contains a 2-bit sight-mode code at bits 18-19 and a 5-bit weather ID
    at bits 20-24. apply_map_extra_flags maps sight codes 0/1/2/3 to
    runtime modes 0/3/1/2, with nonzero modes enabled only on difficulty 1.
    Weather IDs 0-17 are accepted; larger values fall back to 0. Bit 29
    marks the placed-object order as ready; when clear, the engine sorts
    instances and then sets this bit. All 58 US chapter maps ship with it
    set. Bit 0x02 is set on all 58 US chapter maps, but a second executable
    reader scan found no test of it. It is probably unused in the US build
    and remains raw for every region. Other bits control texture callbacks
    and footprint tests or remain open."""

    panel_offset_x: int  # byte 0 - purpose NOT confirmed, see docstring (old name: model_grid_offset high byte)
    panel_offset_y: int  # byte 1 - purpose NOT confirmed, see docstring (old name: model_grid_offset low byte)
    half_x_size: int  # byte 2 - CONFIRMED == ceil(x_size/2)
    half_y_size: int  # byte 3 - CONFIRMED == ceil(y_size/2)
    texture_projection_extent_x2: int  # byte 4 - global last-record texture projection extent is this byte >> 1
    grid_buffer: int  # byte 5 - CONFIRMED: the tactical grid's own inset margin (see docstring)
    unused: tuple[int, int]  # bytes 6-7
    unknown_tail: int  # bytes 8-11 - CONFIRMED consumed as two bitfields, see docstring
    address: int = 0

    @property
    def field_4(self) -> int:
        """Backward-compatible name for byte 4 used by older research scripts."""
        return self.texture_projection_extent_x2

    @property
    def sight_code(self) -> int:
        return (self.unknown_tail >> 18) & 3

    @property
    def weather_id(self) -> int:
        return (self.unknown_tail >> 20) & 31

    @property
    def preserve_object_order(self) -> bool:
        return bool(self.unknown_tail & MAP_EXTRA_OBJECT_ORDER_MASK)


MAP_EXTRA_SIGHT_MASK = 0x000C0000
MAP_EXTRA_WEATHER_MASK = 0x01F00000
MAP_EXTRA_OBJECT_ORDER_MASK = 0x20000000


def patch_extra_mode(data: bytes, record: MapExtra, field: str, value: int) -> bytes:
    """Patch one confirmed mapextra mode while preserving every other bit."""
    masks = {"sight_code": (MAP_EXTRA_SIGHT_MASK, 18, 3),
             "weather_id": (MAP_EXTRA_WEATHER_MASK, 20, 17),
             "preserve_object_order": (MAP_EXTRA_OBJECT_ORDER_MASK, 29, 1)}
    if field not in masks:
        raise MapFileError(f"Unknown mapextra mode {field!r}.")
    mask, shift, maximum = masks[field]
    if not isinstance(value, int) or not 0 <= value <= maximum:
        raise MapFileError(f"{field} must be between 0 and {maximum}.")
    current = struct.unpack_from(">I", data, record.address + 8)[0]
    word = (current & ~mask) | (value << shift)
    return patch_extra_field(data, record, "unknown_tail", word)


Grid = list[list[int]]  # indexed [x][y]

#: Conservative per-axis gameplay limit. Native terrain, movement and link
#: buffers use a fixed 0x40 row stride; the largest shipped chapter map is
#: bmap31 at 63 x 63. Although the on-disk capacity fields are u16 and sparse
#: link coordinates are u8, those encodings are not the runtime capacity.
MAX_GRID_SIZE = 63

LINK_PASS_WEST = 0x01
LINK_PASS_EAST = 0x02
LINK_PASS_SOUTH = 0x04
LINK_PASS_NORTH = 0x08
#: A tile ``maplink`` does not list starts open in every direction. The sections only list the
#: exceptions (``bmap03`` lists 8 of its 1,156 tiles, mostly with one or two directions closed), 43
#: retail maps have no ``maplink`` at all and units move on them, and walls between unlisted tiles come
#: from the height filter, which runs before the sparse overrides.
LINK_DEFAULT_OPEN = LINK_PASS_WEST | LINK_PASS_EAST | LINK_PASS_SOUTH | LINK_PASS_NORTH
LINK_PASS_DIRECTIONS = (
    ("west", LINK_PASS_WEST),
    ("east", LINK_PASS_EAST),
    ("south", LINK_PASS_SOUTH),
    ("north", LINK_PASS_NORTH),
)
LINK_HEIGHT_BLOCK_THRESHOLD = 400


@dataclass
class MapData:
    capacity: Optional[MapCapacity] = None
    build_desc: list[MapObject] = field(default_factory=list)
    build_inst: list[MapBuildInstance] = field(default_factory=list)
    panel_index: Optional[Grid] = None
    unique_panel: list[UniquePanel] = field(default_factory=list)
    panel_index_roof: Optional[Grid] = None
    unique_panel_roof: list[UniquePanel] = field(default_factory=list)
    panel_index_base: Optional[Grid] = None
    unique_panel_base: list[UniquePanel] = field(default_factory=list)
    light: Optional[MapLight] = None
    fog: Optional[MapFog] = None
    grid: Optional[MapGrid] = None
    extra: Optional[MapExtra] = None
    # link/link_at/link_abs together build one per-tile "tile status" value,
    # each grid contributing a different bit range:
    # maplink sets bits 0-7, maplinkAt sets bits 8-11, and maplinkAbs sets
    # bits 0-3 to its value and bits 4-7 to that value's bitwise inverse.
    # Native code confirms low bits 0-3 are directional passability openings
    # west/east/south/north, height-filtered against adjacent tile edges.
    link: Optional[Grid] = None
    link_at: Optional[Grid] = None
    link_abs: Optional[Grid] = None
    unknown_sections: dict[str, int] = field(default_factory=dict)  # name -> file offset, for sections not handled below
    layout: MapLayout = POR_LAYOUT


def is_base_terrain_object(obj: MapObject) -> bool:
    """Whether a mapbuilddesc object IS the map's own base terrain or
    water-plane model, rather than a placed prop - flag_bits_a's top two
    bits, always set together. See MapObject's docstring for how this was
    confirmed (every real match is literally named after its own map)."""
    return (obj.flag_bits_a & 0b11000000) == 0b11000000


def has_ga_animation(obj: MapObject) -> bool:
    """Whether this object references a matching `.ga` animation file -
    flag_bits_c bit 1. See MapObject's docstring for how this was confirmed
    with zero exceptions against real archive contents (and why bit 0,
    previously guessed to mean "no .ga file", does not track this)."""
    return bool(obj.flag_bits_c & 0b00000010)


def compose_link_status_grid(data: "MapData", apply_height_rules: bool = True) -> Grid:
    """Build the native per-tile link/status grid from the three sparse link
    sections, indexed ``[x][y]``.

    This mirrors the real loader at ``build_maplink_grid`` (0x80045604):
    ``maplink`` writes the low byte, ``maplinkAt`` writes bits 8-11, and
    ``maplinkAbs`` runs last and replaces the cell with ``value`` in the low
    nibble plus its inverse in bits 4-7. Unlisted tiles start as :data:`LINK_DEFAULT_OPEN`.
    With ``apply_height_rules``, mirror the native setup order: mark outer
    boundaries, filter openings by the 400-unit edge-height rule, apply the
    sparse overrides, then mark the tactical-grid inset boundary. Explicit
    maplink openings therefore take precedence over the height filter.
    """
    if data.capacity is None:
        raise MapFileError("link status grid requires mapcapacity.")
    width, height = data.capacity.x_size, data.capacity.y_size
    status: Grid = [[LINK_DEFAULT_OPEN] * height for _ in range(width)]
    if apply_height_rules:
        _set_link_boundary_flags(status, 0, width - 1, 0, height - 1)
        _apply_link_height_rules(data, status)

    if data.link is not None:
        for x in range(min(width, len(data.link))):
            for y in range(min(height, len(data.link[x]))):
                value = data.link[x][y]
                if value != -1:
                    status[x][y] = value & 0xFF

    if data.link_at is not None:
        for x in range(min(width, len(data.link_at))):
            for y in range(min(height, len(data.link_at[x]))):
                value = data.link_at[x][y]
                if value != -1:
                    status[x][y] = (status[x][y] & 0xF0FF) | ((value & 0xFF) << 8)

    if data.link_abs is not None:
        for x in range(min(width, len(data.link_abs))):
            for y in range(min(height, len(data.link_abs[x]))):
                value = data.link_abs[x][y]
                if value != -1:
                    status[x][y] = (value & 0xFF) + (((~value) << 4) & 0xF0)

    if apply_height_rules:
        inset = data.extra.grid_buffer if data.extra is not None else 0
        _set_link_boundary_flags(status, inset, width - inset - 1,
                                 inset, height - inset - 1)
    return status


def _set_link_boundary_flags(status: Grid, left: int, right: int,
                             top: int, bottom: int) -> None:
    """Replace outward ground openings with flying-block edge flags."""
    width = len(status)
    height = len(status[0]) if width else 0
    if not (0 <= left <= right < width and 0 <= top <= bottom < height):
        return
    for x in range(left, right + 1):
        status[x][top] = (status[x][top] & ~0x88) | 0x80
        status[x][bottom] = (status[x][bottom] & ~0x44) | 0x40
    for y in range(top, bottom + 1):
        status[left][y] = (status[left][y] & ~0x11) | 0x10
        status[right][y] = (status[right][y] & ~0x22) | 0x20


def link_passable_directions(value: int) -> tuple[str, ...]:
    """Return the confirmed low-nibble directional openings in a composed
    link/status value. These are passability bits: the native height filter
    clears them before the sparse overrides are applied."""
    return tuple(name for name, bit in LINK_PASS_DIRECTIONS if value & bit)


def link_threat_edge_base_cost(value: int, direction_bit: int) -> int | None:
    """Cost of crossing one edge in native threat-range search.

    Returns ``None`` when its boundary flag blocks the edge. Otherwise an
    ordinary opening or matching ``maplinkAt`` bit costs 1, and an edge with
    neither costs 2. Terrain type 0x1C can raise the 1-cost case to 3.
    """
    if direction_bit not in (LINK_PASS_WEST, LINK_PASS_EAST, LINK_PASS_SOUTH, LINK_PASS_NORTH):
        raise ValueError("Invalid map-link direction bit.")
    if value & ((direction_bit << 4) | (direction_bit << 12)):
        return None
    return 1 if value & (direction_bit | (direction_bit << 8)) else 2


def link_tiles_are_adjacent_passable(status: Grid, from_x: int, from_y: int, to_x: int, to_y: int) -> bool:
    """Native-style adjacency predicate for a composed link/status grid.

    Mirrors ``check_maplink_adjacent_passable`` (0x80100BA4): returns false
    unless the two tiles are Manhattan-adjacent, then checks only the source
    tile's matching low-nibble direction bit.
    """
    dx = to_x - from_x
    dy = to_y - from_y
    if abs(dx) + abs(dy) != 1:
        return False
    if from_x < 0 or from_y < 0 or from_x >= len(status):
        return False
    if from_y >= len(status[from_x]):
        return False
    value = status[from_x][from_y]
    if dy == -1:
        return bool(value & LINK_PASS_NORTH)
    if dy == 1:
        return bool(value & LINK_PASS_SOUTH)
    if dx == -1:
        return bool(value & LINK_PASS_WEST)
    return bool(value & LINK_PASS_EAST)


def _apply_link_height_rules(data: "MapData", status: Grid) -> None:
    if data.panel_index is None or not data.unique_panel:
        return
    width, height = data.capacity.x_size, data.capacity.y_size
    checks = (
        (LINK_PASS_WEST, -1, 0, ("top_left_elevation", "bottom_left_elevation"), ("top_right_elevation", "bottom_right_elevation")),
        (LINK_PASS_EAST, 1, 0, ("top_right_elevation", "bottom_right_elevation"), ("top_left_elevation", "bottom_left_elevation")),
        (LINK_PASS_SOUTH, 0, 1, ("bottom_left_elevation", "bottom_right_elevation"), ("top_left_elevation", "top_right_elevation")),
        (LINK_PASS_NORTH, 0, -1, ("top_left_elevation", "top_right_elevation"), ("bottom_left_elevation", "bottom_right_elevation")),
    )
    for x in range(width):
        for y in range(height):
            value = status[x][y]
            if (value & 0x0F) == 0:
                continue
            panel = _panel_at(data, x, y)
            if panel is None:
                continue
            for bit, dx, dy, edge_fields, neighbor_fields in checks:
                if (value & bit) == 0:
                    continue
                neighbor = _panel_at(data, x + dx, y + dy)
                if neighbor is None or not _edges_close_enough(panel, neighbor, edge_fields, neighbor_fields):
                    value &= ~bit
            status[x][y] = value


def _panel_at(data: "MapData", x: int, y: int) -> UniquePanel | None:
    if data.capacity is None or data.panel_index is None:
        return None
    if x < 0 or y < 0 or x >= data.capacity.x_size or y >= data.capacity.y_size:
        return None
    index = data.panel_index[x][y]
    if not 0 <= index < len(data.unique_panel):
        return None
    return data.unique_panel[index]


def _edges_close_enough(
    panel: UniquePanel,
    neighbor: UniquePanel,
    edge_fields: tuple[str, str],
    neighbor_fields: tuple[str, str],
) -> bool:
    for own_field, neighbor_field in zip(edge_fields, neighbor_fields):
        if abs(getattr(panel, own_field) - getattr(neighbor, neighbor_field)) >= LINK_HEIGHT_BLOCK_THRESHOLD:
            return False
    return True


def read_map(stream: BinaryIO) -> MapData:
    header = stream.read(32)
    filesize, sec_table_ptr, sec_table_count = struct.unpack(">III", header[:12])
    section_table_start = sec_table_ptr + 4 * sec_table_count + HEADER_SIZE

    sections = sorted(read_section_table(stream, section_table_start, filesize))
    layout = _layout_from_names(name for _address, name in sections)

    data = MapData(layout=layout)
    for address, file_name in sections:
        name = layout.canonical(file_name)
        if name == "mapcapacity":
            data.capacity = _read_capacity(stream, address, layout)
            if layout.offset("mapextra"):  # Radiant Dawn's mapdata also holds mapextra and mapgrid
                data.extra = _read_extra(stream, address + layout.offset("mapextra"))
                data.grid = _read_grid_colors(stream, address + layout.offset("mapgrid"))
        elif name == "mapbuilddesc":
            data.build_desc = _read_build_desc(stream, address, data.capacity, layout)
        elif name == "mapbuildinst":
            data.build_inst = _read_build_inst(stream, address, data.capacity, layout)
        elif name == "panelindex":
            data.panel_index = _read_grid_u16(stream, address, data.capacity)
        elif name == "uniquepanel":
            data.unique_panel = _read_unique_panel(stream, address, _max_index(data.panel_index))
        elif name == "panelindexRoof":
            data.panel_index_roof = _read_grid_u16(stream, address, data.capacity)
        elif name == "uniquepanelRoof":
            data.unique_panel_roof = _read_unique_panel(stream, address, _max_index(data.panel_index_roof))
        elif name == "panelindexBase":
            data.panel_index_base = _read_grid_u16(stream, address, data.capacity)
        elif name == "uniquepanelBase":
            data.unique_panel_base = _read_unique_panel(stream, address, _max_index(data.panel_index_base))
        elif name == "maplight" and layout.decoded_light:
            data.light = _read_light(stream, address)
        elif name == "mapfog" and layout.decoded_light:
            data.fog = _read_fog(stream, address)
        elif name == "mapgrid":
            data.grid = _read_grid_colors(stream, address)
        elif name == "mapextra":
            data.extra = _read_extra(stream, address)
        elif name == "maplink":
            data.link = _read_link_grid(stream, address, data.capacity, layout)
        elif name == "maplinkAt":
            data.link_at = _read_link_grid(stream, address, data.capacity, layout)
        elif name == "maplinkAbs":
            data.link_abs = _read_link_grid(stream, address, data.capacity, layout)
        else:
            data.unknown_sections[name] = address

    return data


def read_map_file(path: Path | str) -> MapData:
    with open(path, "rb") as stream:
        return read_map(stream)


def read_map_bytes(data: bytes) -> MapData:
    return read_map(io.BytesIO(data))


def _max_index(grid: Optional[Grid]) -> int:
    if not grid:
        return 0
    return max(max(row) for row in grid)


def _read_capacity(stream: BinaryIO, address: int, layout: MapLayout = POR_LAYOUT) -> MapCapacity:
    stream.seek(address)
    record = stream.read(12)
    x, y = struct.unpack_from(layout.size_format, record, layout.size_at)
    desc_count, inst_count, scale_unit = struct.unpack_from(">HHf", record, 4)
    return MapCapacity(x, y, desc_count, inst_count, scale_unit, address=address)


def _get_string(stream: BinaryIO, pointer: int) -> str:
    stream.seek(pointer + HEADER_SIZE)
    chunks = []
    while True:
        byte = stream.read(1)
        if not byte or byte == b"\x00":
            break
        chunks.append(byte)
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError:
        return b"".join(chunks).decode("latin-1")


def _read_build_desc(stream: BinaryIO, address: int, capacity: Optional[MapCapacity],
                     layout: MapLayout = POR_LAYOUT) -> list[MapObject]:
    if capacity is None:
        raise MapFileError("mapbuilddesc section found before mapcapacity.")
    result = []
    pos = address
    for _ in range(capacity.build_desc_count):
        stream.seek(pos)
        record = stream.read(layout.desc_size)
        ox, oy, oz, sx, sy, sz, fa, fb, fc, effect_type, name_ptr = struct.unpack_from(">ffffffBBBBI", record)
        result.append(
            MapObject(ox, oy, oz, sx, sy, sz, fa, fb, fc, effect_type, _get_string(stream, name_ptr), address=pos,
                      footprint=tuple(record[32:]))
        )
        pos += layout.desc_size
    return result


# Radiant Dawn's 20-byte mapbuildinst record: lead, x, y, angle, sub-tile offset x/y, desc index u16,
# the footprint rectangle, the height float's 4 bytes and a trailing word.
_FE10_INST = ">BbbBbbHbbbbbbbbI"


def _read_build_inst(stream: BinaryIO, address: int, capacity: Optional[MapCapacity],
                     layout: MapLayout = POR_LAYOUT) -> list[MapBuildInstance]:
    if capacity is None:
        raise MapFileError("mapbuildinst section found before mapcapacity.")
    result = []
    pos = address
    for _ in range(capacity.build_inst_count):
        stream.seek(pos)
        if layout.inst_size == 20:
            (lead, x, y, angle, off_x, off_y, desc_index, x2, y2, end_x2, end_y2,
             u0, u1, u2, u3, tail) = struct.unpack(_FE10_INST, stream.read(20))
            result.append(MapBuildInstance(x, y, angle, desc_index, x2, y2, end_x2, end_y2, (u0, u1, u2, u3),
                                           address=pos, lead=lead, offset_x=off_x, offset_y=off_y, tail=tail))
        else:
            x, y, angle, desc_index, x2, y2, end_x2, end_y2, u0, u1, u2, u3 = struct.unpack(
                ">bbbbbbbbbbbb", stream.read(12)
            )
            result.append(
                MapBuildInstance(x, y, angle, desc_index, x2, y2, end_x2, end_y2, (u0, u1, u2, u3), address=pos)
            )
        pos += layout.inst_size
    return result


def _read_grid_u16(stream: BinaryIO, address: int, capacity: Optional[MapCapacity]) -> Grid:
    if capacity is None:
        raise MapFileError("grid section found before mapcapacity.")
    stream.seek(address)
    grid: Grid = [[0] * capacity.y_size for _ in range(capacity.x_size)]
    for y in range(capacity.y_size):
        for x in range(capacity.x_size):
            (grid[x][y],) = struct.unpack(">H", stream.read(2))
    return grid


def _read_unique_panel(stream: BinaryIO, address: int, max_index: int) -> list[UniquePanel]:
    stream.seek(address)
    result = []
    pos = address
    # Panel indices are 0-based: every panel section on the disc holds
    # exactly (largest index + 1) records. Elevations are signed.
    for _ in range(max_index + 1):
        result.append(UniquePanel(*struct.unpack(">hhhhI", stream.read(12)), address=pos))
        pos += 12
    return result


def _read_light(stream: BinaryIO, address: int) -> MapLight:
    stream.seek(address)
    enabled, angle_y, angle_z, mr, mg, mb, lr, lg, lb, ua, ub, uc = struct.unpack(">BbbBBBBBBBBB", stream.read(12))
    return MapLight(enabled, angle_y, angle_z, mr, mg, mb, lr, lg, lb, (ua, ub, uc), address=address)


def _read_fog(stream: BinaryIO, address: int) -> MapFog:
    stream.seek(address)
    enabled, mode_code, start_distance, end_distance, r, g, b, unused2 = struct.unpack(">BBbbBBBB", stream.read(8))
    return MapFog(enabled, mode_code, start_distance, end_distance, r, g, b, unused2, address=address)


def _read_grid_colors(stream: BinaryIO, address: int) -> MapGrid:
    stream.seek(address)
    return MapGrid(*struct.unpack(">BBBB", stream.read(4)), address=address)


def _read_extra(stream: BinaryIO, address: int) -> MapExtra:
    stream.seek(address)
    b0, b1, half_x, half_y, b4, buffer_, u0, u1, tail = struct.unpack(">BBBBBBBBI", stream.read(12))
    return MapExtra(b0, b1, half_x, half_y, b4, buffer_, (u0, u1), tail, address=address)


def _read_link_grid(stream: BinaryIO, address: int, capacity: Optional[MapCapacity],
                    layout: MapLayout = POR_LAYOUT) -> Grid:
    if capacity is None:
        raise MapFileError("link section found before mapcapacity.")
    stream.seek(address)
    (num_entries,) = struct.unpack(layout.link_count, stream.read(struct.calcsize(layout.link_count)))
    grid: Grid = [[-1] * capacity.y_size for _ in range(capacity.x_size)]
    for _ in range(num_entries):
        x, y, value = struct.unpack(">BBB", stream.read(3))
        if 0 <= x < capacity.x_size and 0 <= y < capacity.y_size:
            grid[x][y] = value
    return grid


# -- write support ---------------------------------------------------------
# (relative_byte_offset, struct_format) per editable field, keyed by field
# name - deliberately excludes pointers and structural counts, see the
# module docstring's "Write support" section for why.
_CAPACITY_FIELDS = {"scale_unit": (8, ">f")}

_OBJECT_FIELDS = {
    "offset_x": (0, ">f"),
    "offset_y": (4, ">f"),
    "offset_z": (8, ">f"),
    "size_x": (12, ">f"),
    "size_y": (16, ">f"),
    "size_z": (20, ">f"),
    "flag_bits_a": (24, ">B"),
    "flag_bits_b": (25, ">B"),
    "flag_bits_c": (26, ">B"),
    "effect_type": (27, ">B"),
}

_BUILD_INST_FIELDS = {
    "x": (0, ">b"),
    "y": (1, ">b"),
    "angle": (2, ">b"),
    "desc_index": (3, ">b"),
    "x2": (4, ">b"),
    "y2": (5, ">b"),
    "end_x2": (6, ">b"),
    "end_y2": (7, ">b"),
}

_UNIQUE_PANEL_FIELDS = {
    "top_left_elevation": (0, ">h"),
    "top_right_elevation": (2, ">h"),
    "bottom_left_elevation": (4, ">h"),
    "bottom_right_elevation": (6, ">h"),
}

_LIGHT_FIELDS = {
    "enabled": (0, ">B"),
    "angle_y": (1, ">b"),
    "angle_z": (2, ">b"),
    "model_red": (3, ">B"),
    "model_green": (4, ">B"),
    "model_blue": (5, ">B"),
    "light_red": (6, ">B"),
    "light_green": (7, ">B"),
    "light_blue": (8, ">B"),
}

_FOG_FIELDS = {
    "enabled": (0, ">B"),
    "mode_code": (1, ">B"),
    "start_distance": (2, ">b"),
    "end_distance": (3, ">b"),
    "red": (4, ">B"),
    "green": (5, ">B"),
    "blue": (6, ">B"),
    "unused2": (7, ">B"),
}

_GRID_FIELDS = {"unknown": (0, ">B"), "red": (1, ">B"), "green": (2, ">B"), "blue": (3, ">B")}

_EXTRA_FIELDS = {
    "panel_offset_x": (0, ">B"),
    "panel_offset_y": (1, ">B"),
    "half_x_size": (2, ">B"),
    "half_y_size": (3, ">B"),
    "texture_projection_extent_x2": (4, ">B"),
    "field_4": (4, ">B"),
    "grid_buffer": (5, ">B"),
    "unknown_tail": (8, ">I"),  # map flags: 0x04/0x10/0x20 pick material callbacks (0x20 = water)
}


def _patch_field(data: bytes, address: int, field_name: str, value, field_table: dict, label: str) -> bytes:
    if field_name not in field_table:
        raise MapFileError(f"{field_name!r} is not an editable field on a {label} record.")
    offset, fmt = field_table[field_name]
    out = bytearray(data)
    struct.pack_into(fmt, out, address + offset, value)
    return bytes(out)


def patch_capacity_field(data: bytes, record: MapCapacity, field_name: str, value) -> bytes:
    """Only `scale_unit` is editable - x_size/y_size/build_desc_count/
    build_inst_count are structural counts every other section is sized
    against (see module docstring)."""
    return _patch_field(data, record.address, field_name, value, _CAPACITY_FIELDS, "mapcapacity")


def patch_object_field(data: bytes, record: MapObject, field_name: str, value) -> bytes:
    """Every field except `filename` (backed by a pointer, not patchable in
    place) is editable."""
    return _patch_field(data, record.address, field_name, value, _OBJECT_FIELDS, "mapbuilddesc")


_FE10_BUILD_INST_FIELDS = {
    "x": (1, ">b"),
    "y": (2, ">b"),
    "angle": (3, ">B"),
    "offset_x": (4, ">b"),
    "offset_y": (5, ">b"),
    "desc_index": (6, ">H"),
    "x2": (8, ">b"),
    "y2": (9, ">b"),
    "end_x2": (10, ">b"),
    "end_y2": (11, ">b"),
}


def patch_build_inst_field(data: bytes, record: MapBuildInstance, field_name: str, value) -> bytes:
    table = _FE10_BUILD_INST_FIELDS if map_layout(data).inst_size == 20 else _BUILD_INST_FIELDS
    return _patch_field(data, record.address, field_name, value, table, "mapbuildinst")


def patch_unique_panel_field(data: bytes, record: UniquePanel, field_name: str, value) -> bytes:
    """The four elevation fields are editable; `terrain_type_ptr` is a
    pointer and isn't."""
    return _patch_field(data, record.address, field_name, value, _UNIQUE_PANEL_FIELDS, "uniquepanel")


def patch_light_field(data: bytes, record: MapLight, field_name: str, value) -> bytes:
    return _patch_field(data, record.address, field_name, value, _LIGHT_FIELDS, "maplight")


def patch_fog_field(data: bytes, record: MapFog, field_name: str, value) -> bytes:
    return _patch_field(data, record.address, field_name, value, _FOG_FIELDS, "mapfog")


def patch_grid_field(data: bytes, record: MapGrid, field_name: str, value) -> bytes:
    return _patch_field(data, record.address, field_name, value, _GRID_FIELDS, "mapgrid")


def patch_extra_field(data: bytes, record: MapExtra, field_name: str, value) -> bytes:
    return _patch_field(data, record.address, field_name, value, _EXTRA_FIELDS, "mapextra")


# -- section writers --------------------------------------------------------------

def _sections(data: bytes) -> tuple[list[tuple[int, int]], int]:
    """``([(data-relative address, name offset), ...], table offset)`` of the
    section table, whose length is header word 3."""
    _size, data_size, pointer_count, section_count = struct.unpack(">IIII", data[:16])
    table = HEADER_SIZE + data_size + 4 * pointer_count
    entries = [struct.unpack(">II", data[table + 8 * i : table + 8 * i + 8]) for i in range(section_count)]
    return entries, table


def section_bytes(data: bytes, name: str) -> tuple[int, int]:
    """``(file offset, length)`` of a named section; its length runs to the
    next section, or to the string pool / pointer list for the last one.
    ``name`` is Path of Radiance's name, resolved through the file's layout."""
    named = read_section_table(io.BytesIO(data), _sections(data)[1], len(data))
    layout = _layout_from_names(n for _a, n in named)
    if layout.offset(name):
        raise MapFileError(f"{name} is part of the {layout.file_name(name)} section in this map.")
    wanted = layout.file_name(name)
    for address, section in sorted(named):
        if section == wanted:
            starts = sorted(a for a, _ in read_section_table(io.BytesIO(data), _sections(data)[1], len(data)))
            later = [a for a in starts if a > address]
            pointers = _pointer_offsets(data)
            targets = [HEADER_SIZE + struct.unpack(">I", data[HEADER_SIZE + p : HEADER_SIZE + p + 4])[0] for p in pointers]
            data_end = HEADER_SIZE + struct.unpack(">I", data[4:8])[0]
            end = later[0] if later else min([t for t in targets if t > address] + [data_end])
            return address, end - address
    raise MapFileError(f"No section {name!r}.")


def _pointer_offsets(data: bytes) -> list[int]:
    _size, data_size, pointer_count = struct.unpack(">III", data[:12])
    at = HEADER_SIZE + data_size
    return list(struct.unpack(f">{pointer_count}I", data[at : at + 4 * pointer_count]))


def replace_section(data: bytes, name: str, payload: bytes, pointer_fields: list[int] = ()) -> bytes:
    """Replace a named section's bytes, growing or shrinking the file.

    Everything after the section moves by the size difference: stored
    pointers into that part, pointer-list entries and section addresses are
    shifted to match. The old section's pointer-list entries are dropped and
    ``pointer_fields`` (offsets inside ``payload`` holding pointers) are
    listed instead. ``payload`` must keep 4-byte alignment."""
    if len(payload) % 4:
        raise MapFileError("A section must be a multiple of 4 bytes.")
    start, length = section_bytes(data, name)
    end = start + length
    delta = len(payload) - length
    size, data_size, pointer_count, section_count = struct.unpack(">IIII", data[:16])
    entries, table = _sections(data)

    def moved(file_offset: int) -> int:
        return file_offset + delta if file_offset >= end else file_offset

    body = bytearray(data[: HEADER_SIZE + data_size])
    body[start:end] = payload
    pointers = []
    for rel in _pointer_offsets(data):
        at = rel + HEADER_SIZE
        if start <= at < end:
            continue
        new_at = moved(at)
        target = struct.unpack(">I", data[at : at + 4])[0]
        struct.pack_into(">I", body, new_at, moved(target + HEADER_SIZE) - HEADER_SIZE)
        pointers.append(new_at - HEADER_SIZE)
    for field in pointer_fields:
        target = struct.unpack(">I", payload[field : field + 4])[0]
        struct.pack_into(">I", body, start + field, moved(target + HEADER_SIZE) - HEADER_SIZE)
        pointers.append(start - HEADER_SIZE + field)
    pointers.sort()
    tail = bytearray(struct.pack(f">{len(pointers)}I", *pointers))
    for address, name_offset in entries:
        tail += struct.pack(">II", moved(address + HEADER_SIZE) - HEADER_SIZE, name_offset)
    tail += data[table + 8 * section_count :]
    new_data_size = data_size + delta
    header = struct.pack(">IIII", HEADER_SIZE + new_data_size + len(tail), new_data_size, len(pointers), section_count)
    return header + bytes(body[16:]) + bytes(tail)


def insert_section_before(data: bytes, before_name: str, name: str, payload: bytes) -> bytes:
    """Add a pointer-free section before an existing section.

    Section data and the pointer table use data-relative addresses. Existing
    section names stay in place; the new name is appended after them.
    """
    if len(payload) % 4:
        raise MapFileError("A section must be a multiple of 4 bytes.")
    named = read_section_table(io.BytesIO(data), _sections(data)[1], len(data))
    layout = _layout_from_names(n for _a, n in named)
    name, before_name = layout.file_name(name), layout.file_name(before_name)
    if any(existing == name for _address, existing in named):
        raise MapFileError(f"Section {name!r} already exists.")
    match = next((address for address, existing in named if existing == before_name), None)
    if match is None:
        raise MapFileError(f"No section {before_name!r}.")
    _size, data_size, _pointer_count, section_count = struct.unpack_from(">IIII", data)
    entries, table = _sections(data)
    delta = len(payload)
    body = bytearray(data[:HEADER_SIZE + data_size])
    body[match:match] = payload
    pointer_offsets = []
    for relative in _pointer_offsets(data):
        old_at = HEADER_SIZE + relative
        new_at = old_at + (delta if old_at >= match else 0)
        target = struct.unpack_from(">I", data, old_at)[0]
        new_target = target + (delta if HEADER_SIZE + target >= match else 0)
        struct.pack_into(">I", body, new_at, new_target)
        pointer_offsets.append(new_at - HEADER_SIZE)
    old_tail = data[table + section_count * 8:]
    if len(old_tail) < 8:
        raise MapFileError("Missing section table sentinel.")
    name_offset = len(old_tail)
    tail = bytearray(struct.pack(f">{len(pointer_offsets)}I", *pointer_offsets))
    for address, offset in entries:
        tail += struct.pack(">II", address + (delta if HEADER_SIZE + address >= match else 0), offset)
    tail += struct.pack(">II", match - HEADER_SIZE, name_offset)
    tail += old_tail + name.encode("ascii") + b"\x00"
    new_data_size = data_size + delta
    header = struct.pack(">IIII", HEADER_SIZE + new_data_size + len(tail), new_data_size,
                         len(pointer_offsets), section_count + 1)
    return header + bytes(body[16:]) + bytes(tail)


def set_link_openings(data: bytes, x: int, y: int, openings: int) -> bytes:
    """Edit a tile's confirmed directional openings in sparse ``maplink``.

    Existing high bits, other records and the optional maplinkAt section are
    preserved. A maplinkAbs record overrides maplink, so such a tile is
    rejected until its override semantics are better understood.
    """
    parsed = read_map_bytes(data)
    cap = parsed.capacity
    if cap is None or not (0 <= x < cap.x_size and 0 <= y < cap.y_size):
        raise MapFileError(f"Tile ({x}, {y}) is outside the map.")
    if not isinstance(openings, int) or not 0 <= openings <= 15:
        raise MapFileError("Openings must be a four-bit value (0-15).")
    if parsed.link_abs is not None and parsed.link_abs[x][y] != -1:
        raise MapFileError("This tile has a maplinkAbs override; its maplink openings cannot be edited here.")
    layout = parsed.layout
    head = struct.calcsize(layout.link_count)
    if parsed.link is None:
        if openings == LINK_DEFAULT_OPEN:
            return data
        payload = struct.pack(layout.link_count, 1) + bytes((x, y, openings))
        payload += bytes(-len(payload) % 4)
        named = read_section_table(io.BytesIO(data), _sections(data)[1], len(data))
        names = [layout.canonical(name) for _address, name in named]
        before = next((name for name in ("mapextra", "maplinkAt", "maplinkAbs") if name in names), named[-1][1])
        return insert_section_before(data, before, "maplink", payload)
    start, length = section_bytes(data, "maplink")
    count = struct.unpack_from(layout.link_count, data, start)[0]
    if head + 3 * count > length:
        raise MapFileError("maplink record count exceeds section length.")
    payload = bytearray(data[start:start + length])
    for i in range(count):
        at = head + 3 * i
        if payload[at] == x and payload[at + 1] == y:
            payload[at + 2] = (payload[at + 2] & 0xF0) | openings
            return data[:start] + bytes(payload) + data[start + length:]
    if openings == LINK_DEFAULT_OPEN:
        return data
    if count >= 0xFFFF:
        raise MapFileError("maplink has too many records.")
    if length - (head + 3 * count) > 3 or any(payload[head + 3 * count:]):
        raise MapFileError("maplink has trailing data beyond alignment padding; cannot safely add a record.")
    payload = payload[:head + 3 * count] + bytes((x, y, openings))
    struct.pack_into(layout.link_count, payload, 0, count + 1)
    payload += bytes(-len(payload) % 4)
    return replace_section(data, "maplink", bytes(payload))


def write_panel_layer(
    data: bytes, index_section: str, panel_section: str, grid: Grid, panels: list[tuple[int, int, int, int, int]]
) -> bytes:
    """Write one elevation layer: the ``[x][y]`` index grid (same size, in
    place) and its panel records ``(tl, tr, bl, br, terrain_type_ptr)``,
    resizing the panel section. Terrain-type pointers stay pointer fields."""
    start, length = section_bytes(data, index_section)
    width, height = len(grid), len(grid[0]) if grid else 0
    if not 0 <= length - width * height * 2 < 4:  # padded to 4 bytes
        raise MapFileError(f"{index_section} is {length} bytes, not {width}x{height} u16.")
    out = bytearray(data)
    for y in range(height):
        for x in range(width):
            struct.pack_into(">H", out, start + 2 * (y * width + x), grid[x][y])
    payload = b"".join(struct.pack(">hhhhI", *p) for p in panels)
    fields = [12 * i + 8 for i, p in enumerate(panels) if p[4]]
    return replace_section(bytes(out), panel_section, payload, fields)


def _resized_grid(grid: Grid, width: int, height: int) -> Grid:
    """Resize a dense grid, copying the overlap and extending edge cells.

    Edge extension gives newly added terrain the same terrain and corner
    elevations as its nearest old tile instead of silently turning it into
    panel record zero, which is not necessarily a map's ground panel.
    """
    old_width = len(grid)
    old_height = len(grid[0]) if old_width else 0
    if not old_width or not old_height:
        raise MapFileError("A map grid cannot be resized because it is empty.")
    return [[grid[min(x, old_width - 1)][min(y, old_height - 1)] for y in range(height)]
            for x in range(width)]


def _grid_u16_payload(grid: Grid) -> bytes:
    width, height = len(grid), len(grid[0]) if grid else 0
    payload = bytearray(2 * width * height)
    for y in range(height):
        for x in range(width):
            struct.pack_into(">H", payload, 2 * (y * width + x), grid[x][y])
    payload += bytes(-len(payload) % 4)
    return bytes(payload)


def _link_payload(grid: Grid, width: int, height: int, layout: MapLayout = POR_LAYOUT) -> bytes:
    records = [(x, y, grid[x][y]) for x in range(min(width, len(grid)))
               for y in range(min(height, len(grid[x]))) if grid[x][y] != -1]
    if len(records) > 0xFFFF:
        raise MapFileError("A link grid has too many explicit records.")
    payload = bytearray(struct.pack(layout.link_count, len(records)))
    for x, y, value in records:
        payload += struct.pack(">BBB", x, y, value)
    payload += bytes(-len(payload) % 4)
    return bytes(payload)


def resize_grid(data: bytes, width: int, height: int) -> bytes:
    """Change a chapter map's tile-grid dimensions.

    All present panel-index layers are resized from their top-left origin;
    newly added rows or columns repeat the nearest edge tile. Sparse link
    entries in the retained area are preserved and entries outside a
    shrunken grid are dropped. Placed objects are deliberately untouched,
    so shrinking may leave objects off-grid for the user to move or delete.
    """
    parsed = read_map_bytes(data)
    if parsed.capacity is None:
        raise MapFileError("This map has no mapcapacity section.")
    if (width, height) == (parsed.capacity.x_size, parsed.capacity.y_size):
        return data  # also for the vanilla 64-tile maps, past MAX_GRID_SIZE
    if (not isinstance(width, int) or not isinstance(height, int)
            or not (1 <= width <= MAX_GRID_SIZE and 1 <= height <= MAX_GRID_SIZE)):
        raise MapFileError(f"Map width and height must be whole numbers from 1 to {MAX_GRID_SIZE} tiles.")

    for section, grid in (("panelindex", parsed.panel_index),
                          ("panelindexRoof", parsed.panel_index_roof),
                          ("panelindexBase", parsed.panel_index_base)):
        if grid is not None:
            data = replace_section(data, section, _grid_u16_payload(_resized_grid(grid, width, height)))
    for section, grid in (("maplink", parsed.link), ("maplinkAt", parsed.link_at),
                          ("maplinkAbs", parsed.link_abs)):
        if grid is not None:
            data = replace_section(data, section, _link_payload(grid, width, height, parsed.layout))

    layout = parsed.layout
    capacity_at, _length = section_bytes(data, "mapcapacity")
    out = bytearray(data)
    struct.pack_into(layout.size_format, out, capacity_at + layout.size_at, width, height)
    data = bytes(out)
    current = read_map_bytes(data)
    if current.extra is not None:
        up = 1 if layout.half_round_up else 0
        data = patch_extra_field(data, current.extra, "half_x_size", (width + up) // 2)
        current = read_map_bytes(data)
        data = patch_extra_field(data, current.extra, "half_y_size", (height + up) // 2)
    return data


def patch_build_inst_height(data: bytes, record: "MapBuildInstance", height: float) -> bytes:
    """Set an instance's height float (``pos_y = -5 * height``)."""
    out = bytearray(data)
    struct.pack_into(">f", out, record.address + (12 if map_layout(data).inst_size == 20 else 8), height)
    return bytes(out)


# -- terrain types ------------------------------------------------------------------

TERRAIN_ENCODING = "shift_jis"


def pointer_string(data: bytes, pointer: int) -> str:
    """The Shift-JIS string a data-relative pointer points at (terrain-type
    names such as ``平地``)."""
    start = HEADER_SIZE + pointer
    return data[start : data.index(b"\x00", start)].decode(TERRAIN_ENCODING, errors="replace")


def terrain_grid(data: bytes) -> Optional[Grid]:
    """Each tile's terrain-type name (``[x][y]``), from the combined
    ``uniquepanel`` layer - the layer the game takes a tile's terrain from.
    The ground layer's names describe the ground under objects."""
    parsed = read_map_bytes(data)
    if parsed.capacity is None or parsed.panel_index is None:
        return None
    return [
        [pointer_string(data, parsed.unique_panel[i].terrain_type_ptr) if 0 <= i < len(parsed.unique_panel) else ""
         for i in column]
        for column in parsed.panel_index
    ]


def add_pool_string(data: bytes, text: str) -> tuple[bytes, int]:
    """``(data, pointer)`` for a NUL-terminated Shift-JIS string: an existing
    copy in the data section, or one appended to the end of the data section
    (the pointer list and section table after it hold data-relative offsets
    below that point, so only the header's sizes change)."""
    raw = text.encode(TERRAIN_ENCODING)
    size, data_size = struct.unpack(">II", data[:8])
    body = data[HEADER_SIZE : HEADER_SIZE + data_size]
    at = body.find(b"\x00" + raw + b"\x00")
    if at >= 0:
        return data, at + 1
    added = raw + b"\x00"
    added += bytes(-(data_size + len(added)) % 4)
    out = bytearray(data[: HEADER_SIZE + data_size] + added + data[HEADER_SIZE + data_size :])
    struct.pack_into(">II", out, 0, size + len(added), data_size + len(added))
    return bytes(out), data_size


def set_tile_terrains(data: bytes, terrains: dict[tuple[int, int], str]) -> bytes:
    """Set the terrain type (a ``TerrainData`` name such as ``砦``) of tiles
    ``(x, y)`` on the combined ``uniquepanel`` layer. Changed tiles keep
    their corner elevations and get records of their own when needed; the
    names are added to the string pool when the map has no copy yet."""
    pointers = {}
    for name in dict.fromkeys(terrains.values()):
        data, pointers[name] = add_pool_string(data, name)
    parsed = read_map_bytes(data)
    if parsed.capacity is None or parsed.panel_index is None:
        raise MapFileError("This map has no panel layer.")
    records = [(p.top_left_elevation, p.top_right_elevation, p.bottom_left_elevation, p.bottom_right_elevation, p.terrain_type_ptr)
               for p in parsed.unique_panel]
    index_of = {r: i for i, r in reversed(list(enumerate(records)))}
    grid = [list(column) for column in parsed.panel_index]
    for (x, y), name in terrains.items():
        if not (0 <= x < parsed.capacity.x_size and 0 <= y < parsed.capacity.y_size):
            raise MapFileError(f"Tile ({x}, {y}) is outside the map.")
        tl, tr, bl, br, _ptr = records[grid[x][y]]
        record = (tl, tr, bl, br, pointers[name])
        if record not in index_of:
            index_of[record] = len(records)
            records.append(record)
        grid[x][y] = index_of[record]
    return write_panel_layer(data, "panelindex", "uniquepanel", grid, records)


# -- placed objects -------------------------------------------------------------------

TILE_UNITS = 5.0


def _set_counts(data: bytes, desc_count: int, inst_count: int) -> bytes:
    start, _length = section_bytes(data, "mapcapacity")
    out = bytearray(data)
    struct.pack_into(">HH", out, start + 4, desc_count, inst_count)
    return bytes(out)


def _desc_payload(data: bytes, objects: list[MapObject], pointers: list[int]) -> tuple[bytes, list[int]]:
    size = map_layout(data).desc_size

    def tail(o: MapObject) -> bytes:
        if size == 32:
            return b""
        return bytes(o.footprint) if len(o.footprint) == size - 32 else bytes((*footprint_tiles(o), 0, 0))

    payload = b"".join(
        struct.pack(">ffffffBBBBI", o.offset_x, o.offset_y, o.offset_z, o.size_x, o.size_y, o.size_z,
                    o.flag_bits_a, o.flag_bits_b, o.flag_bits_c, o.effect_type, p) + tail(o)
        for o, p in zip(objects, pointers)
    )
    return payload, [size * i + 28 for i in range(len(objects))]


def add_build_object(data: bytes, obj: MapObject) -> tuple[bytes, int]:
    """Append a ``mapbuilddesc`` record for ``obj`` (its ``filename`` is the
    model's name in ``map.cmp``, added to the string pool when missing) and
    return ``(data, index)``. The bounds are the model's bounding box:
    ``offset`` its minimum corner, ``size`` its maximum corner."""
    data, name_pointer = add_pool_string(data, obj.filename)
    parsed = read_map_bytes(data)
    start, _length = section_bytes(data, "mapbuilddesc")
    pointers = [struct.unpack(">I", data[o.address + 28 : o.address + 32])[0] for o in parsed.build_desc]
    payload, fields = _desc_payload(data, [*parsed.build_desc, obj], [*pointers, name_pointer])
    data = replace_section(data, "mapbuilddesc", payload, fields)
    return _set_counts(data, len(parsed.build_desc) + 1, len(parsed.build_inst)), len(parsed.build_desc)


def footprint_tiles(obj: MapObject) -> tuple[int, int]:
    """Tiles an object covers along x and z: ``round(max / 5)``, at least 1
    (vanilla ``mapbuildinst`` end coordinates follow this)."""
    return max(1, round(obj.size_x / TILE_UNITS)), max(1, round(obj.size_z / TILE_UNITS))


def instance_record(obj: MapObject, desc_index: int, x: int, y: int, angle: int, height: float) -> bytes:
    """A ``mapbuildinst`` record: position, angle byte (degrees =
    360 - angle * 360 / 256, so 64 = 270), the tiles the object covers after
    rotation (``(x2, y2)``-``(end_x2, end_y2)``, as vanilla props store it
    for quarter turns) and the height float (``pos_y = -5 * height``)."""
    w, d = footprint_tiles(obj)
    quarter = round((angle % 256) / 64) % 4
    x2, y2, x_end, y_end = (
        (x, y, x + w - 1, y + d - 1),
        (x - (d - 1), y, x, y + w - 1),
        (x - (w - 1), y - (d - 1), x, y),
        (x, y - (w - 1), x + d - 1, y),
    )[quarter]
    return struct.pack(">bbBbbbbbf", x, y, angle % 256, desc_index, x2, y2, x_end, y_end, height)


#: Trailing word of a new Radiant Dawn mapbuildinst record (the value most vanilla records hold).
FE10_INST_TAIL = 0x40000000


def fe10_instance_record(record: bytes) -> bytes:
    """A Path of Radiance 12-byte ``mapbuildinst`` record (:func:`instance_record`) as Radiant Dawn's
    20 bytes: no sub-tile offset and the common trailing word."""
    if len(record) == 20:
        return record
    x, y, angle, desc_index, x2, y2, end_x2, end_y2 = struct.unpack_from(">bbBBbbbb", record)
    head = struct.pack(">BbbBbbHbbbb", 0, x, y, angle, 0, 0, desc_index, x2, y2, end_x2, end_y2)
    return head + record[8:12] + struct.pack(">I", FE10_INST_TAIL)


def set_build_instances(data: bytes, records: list[bytes]) -> bytes:
    """Replace every ``mapbuildinst`` record and the count. Records are the file's own
    (:func:`instance_records`) or new ones from :func:`instance_record`, widened to the file's layout."""
    parsed = read_map_bytes(data)
    if parsed.layout.inst_size == 20:
        records = [fe10_instance_record(r) for r in records]
    data = replace_section(data, "mapbuildinst", b"".join(records))
    return _set_counts(data, len(parsed.build_desc), len(records))


def instance_records(data: bytes) -> list[bytes]:
    parsed = read_map_bytes(data)
    size = parsed.layout.inst_size
    return [data[i.address : i.address + size] for i in parsed.build_inst]
