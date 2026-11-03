"""Size and precision figures of a ``.gs`` model, for reviewing an import.

:func:`model_stats` counts what the engine has to hold and draw (vertices,
triangles, shapes by skinning type, bones, materials) and states the
fixed-point precision of the stored data. The 3D Models import review
shows them next to the model being replaced. :data:`MAP_BODY_LIMITS` and
:data:`BATTLE_BODY_LIMITS` give the largest figures among the disc's map
models (``ymu/``) and battle models (``zu/``): sizes the game is known to
handle. No engine limit is known.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import gs_file
from . import model as model_fmt

FLAG_COMPOSITE = 0x1
FLAG_MULTI_MATRIX = 0x2


@dataclass(frozen=True)
class ModelStats:
    file_size: int
    positions: int
    normals: int
    uvs: int
    colors: int
    blended_vertices: int  # composite-buffer vertices (CPU skinned every frame)
    triangles: int
    single_bone_shapes: int
    multi_matrix_shapes: int
    composite_shapes: int
    bones_used: int
    materials: int
    position_step: float  # 1 / 2^fraction bits of the position array
    position_range: float  # largest storable coordinate
    blended_step: float | None  # the composite buffer's step, when it has one
    blended_range: float | None


def _triangles(data: bytes) -> int:
    """Visible triangles: strip triangles with three distinct positions (the
    degenerate ones only join strips) in shapes the engine draws."""
    parsed = model_fmt.read_model_bytes(data)
    count = 0
    for chunk in parsed.chunks:
        if chunk.hidden:
            continue
        for strip in chunk.strips:
            for i in range(len(strip) - 2):
                if len({strip[i].position, strip[i + 1].position, strip[i + 2].position}) == 3:
                    count += 1
    return count


def model_stats(data: bytes) -> ModelStats:
    """Figures for the ``.gs`` file ``data`` (see :class:`ModelStats`)."""
    gs = gs_file.read_gs(data)
    chunks = [chunk for chunk_list in gs.chunk_lists for chunk in chunk_list]
    bones: set[int] = set()
    single = multi = composite = 0
    for chunk in chunks:
        if chunk.flags & FLAG_COMPOSITE:
            composite += 1
        elif chunk.flags & FLAG_MULTI_MATRIX:
            multi += 1
            bones.update(chunk.bone_subset or ())
        else:
            single += 1
            bones.add(chunk.bone)
    blended = 0
    blended_step = blended_range = None
    comp = gs.composite
    if comp is not None and comp.weights:
        for record in comp.weights:
            bones.update(record[: record[11]])
            blended += record[12]
        shift = comp.unk0 >> 8
        blended_step, blended_range = 1 / (1 << shift), 32767 / (1 << shift)
    return ModelStats(
        file_size=len(data),
        positions=len(gs.positions),
        normals=len(gs.normals),
        uvs=len(gs.uvs),
        colors=len(gs.colors),
        blended_vertices=blended,
        triangles=_triangles(data),
        single_bone_shapes=single,
        multi_matrix_shapes=multi,
        composite_shapes=composite,
        bones_used=len(bones),
        materials=len(gs.materials),
        position_step=1 / (1 << gs.pos_frac),
        position_range=32767 / (1 << gs.pos_frac),
        blended_step=blended_step,
        blended_range=blended_range,
    )


#: The largest figures among the 86 map models (``ymu/<class>/body.gs``) of
#: the US Path of Radiance disc (the dragon ``dragon_2as`` for size,
#: ``knight2`` for bones). None has blended vertices. A body above these is
#: untested territory, not a known limit.
MAP_BODY_LIMITS = {
    "file_size": 19936,
    "positions": 715,
    "triangles": 853,
    "bones_used": 70,
    "blended_vertices": 0,
}

#: The largest figures among the chapter terrains (the land model of each
#: ``zmap/<map>/map.cmp``): ``bmap25`` for size. Terrains are static, on one
#: bone. Their ``texpack.tpl`` reaches ``MAP_TEXPACK_LIMIT`` bytes.
MAP_TERRAIN_LIMITS = {
    "file_size": 393868,
    "positions": 10664,
    "triangles": 20982,
    "bones_used": 1,
    "blended_vertices": 0,
}
MAP_TEXPACK_LIMIT = 1519072

#: The largest figures among the 93 battle models (``zu/<code>/<code>.gs``):
#: ``drm2`` for triangles, ``pal3`` for size and blended vertices, ``pal2``
#: for bones. Battle models draw almost everything as blended vertices.
BATTLE_BODY_LIMITS = {
    "file_size": 209636,
    "positions": 55,
    "triangles": 8840,
    "bones_used": 113,
    "blended_vertices": 5800,
}
