"""Keep ``map.bin``'s heights in step with a replaced terrain mesh.

Units stand on the corner elevations of ``map.bin``'s panel layers and props
on their instance height, not on the terrain mesh. On vanilla maps these
agree with the mesh: the ground layer (``uniquepanelBase``) sits at mesh
height ``-elevation / 400`` and props at their tile's surface. When a new
terrain moves the ground, :func:`follow_terrain` shifts every affected
corner of the combined and ground layers, and every prop, by the same
height change, so objects keep their offsets above the ground (a bridge
stays a bridge). Tiles share panel records; changed tiles get records of
their own and the panel sections grow (``map_file.write_panel_layer``).
The roof layer is left alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .formats import map_file, model

ELEVATION_PER_UNIT = -400.0  # elevation = height * ELEVATION_PER_UNIT
TILE_SIZE = 5.0
#: Height changes below this (mesh units) count as unchanged.
TOLERANCE = 0.02
#: A panel corner within this of the old terrain surface stands on it.
ON_SURFACE = 0.05
#: A prop whose base is within this of the old surface at its tile centre stands on it:
#: vanilla props sit near it, not exactly (Prologue: 105 of 228 within 0.05, 227
#: within 2, since a prop's footprint spans more than its centre).
PROP_ON_SURFACE = 2.0


def surface_heights(triangles: "np.ndarray", points) -> "np.ndarray":
    """Highest surface height of ``triangles`` (``(N, 3, 3)`` corner
    positions) above each ``(x, z)`` point; ``nan`` where none covers it."""
    points = list(points)
    out = np.full(len(points), np.nan)
    if len(triangles) == 0 or not points:
        return out
    tri = np.asarray(triangles, dtype=float)
    ax, az = tri[:, 0, 0], tri[:, 0, 2]
    bx, bz = tri[:, 1, 0] - ax, tri[:, 1, 2] - az
    cx, cz = tri[:, 2, 0] - ax, tri[:, 2, 2] - az
    det = bx * cz - cx * bz
    ok = np.abs(det) > 1e-9
    safe = np.where(ok, det, 1.0)
    for i, (x, z) in enumerate(points):
        px, pz = x - ax, z - az
        u = (px * cz - cx * pz) / safe
        v = (bx * pz - px * bz) / safe
        inside = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
        if inside.any():
            y = tri[inside, 0, 1] + u[inside] * (tri[inside, 1, 1] - tri[inside, 0, 1]) + v[inside] * (tri[inside, 2, 1] - tri[inside, 0, 1])
            out[i] = y.max()
    return out


def terrain_origin(map_data: map_file.MapData, terrain_name: str) -> tuple[int, int]:
    """Placement coordinates of the terrain instance: tile/prop ``(x, y)``
    sits at mesh ``5 * (x - origin_x)``."""
    for inst in map_data.build_inst:
        if 0 <= inst.desc_index < len(map_data.build_desc) and map_data.build_desc[inst.desc_index].filename == terrain_name:
            return inst.x, inst.y
    if map_data.extra is not None:
        return -map_data.extra.panel_offset_x, -map_data.extra.panel_offset_y
    return 0, 0


@dataclass
class HeightUpdate:
    map_bin: bytes
    corners_changed: int = 0
    tiles_changed: int = 0
    props_moved: int = 0
    largest_change: float = 0.0
    props_kept: int = 0  # props not standing on the old ground (sunk, floating, on a bridge) keep their height
    corners_on_props: int = 0  # corners kept because they sit on a bridge/floor, not the old terrain


def follow_terrain(map_bin: bytes, terrain_name: str, old_triangles, new_triangles) -> HeightUpdate:
    """``map_bin`` with its ground/combined elevations and prop heights moved
    by the change between the old and new terrain surfaces. A tile corner
    moves only when it lay on the old terrain surface: corners standing on
    a prop (a bridge, a castle floor; 14% of ``bmap07``'s and 23% of
    ``bmap12``'s playable corners) keep their height."""
    data = map_file.read_map_bytes(map_bin)
    cap = data.capacity
    if cap is None:
        return HeightUpdate(map_bin)
    ox, oy = terrain_origin(data, terrain_name)
    corners = [(x, y) for x in range(cap.x_size + 1) for y in range(cap.y_size + 1)]
    points = [(TILE_SIZE * (x - ox), TILE_SIZE * (y - oy)) for x, y in corners]
    old_surface = surface_heights(old_triangles, points)
    delta_list = surface_heights(new_triangles, points) - old_surface
    delta = {c: d for c, d in zip(corners, delta_list) if not np.isnan(d) and abs(d) > TOLERANCE}
    old_at = dict(zip(corners, old_surface))
    kept: set[tuple[int, int]] = set()
    result = HeightUpdate(map_bin, corners_changed=len(delta))
    if delta:
        result.largest_change = float(max(abs(d) for d in delta.values()))

    out = map_bin
    changed_tiles: set[tuple[int, int]] = set()
    for index_name, panel_name, grid, panels in (
        ("panelindex", "uniquepanel", data.panel_index, data.unique_panel),
        ("panelindexBase", "uniquepanelBase", data.panel_index_base, data.unique_panel_base),
    ):
        if grid is None or not panels or not delta:
            continue
        records = [(p.top_left_elevation, p.top_right_elevation, p.bottom_left_elevation, p.bottom_right_elevation, p.terrain_type_ptr) for p in panels]
        index_of = {r: i for i, r in reversed(list(enumerate(records)))}
        new_grid = [list(column) for column in grid]
        for x in range(cap.x_size):
            for y in range(cap.y_size):
                i = grid[x][y]
                if not 0 <= i < len(records):
                    continue
                tl, tr, bl, br, ptr = records[i]
                elevations = [tl, tr, bl, br]
                moved = False
                for k, corner in enumerate(((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))):
                    if corner not in delta:
                        continue
                    if abs(elevations[k] / ELEVATION_PER_UNIT - old_at[corner]) > ON_SURFACE:
                        kept.add(corner)
                        continue
                    elevations[k] = max(-32768, min(32767, elevations[k] + round(delta[corner] * ELEVATION_PER_UNIT)))
                    moved = True
                if not moved:
                    continue
                changed_tiles.add((x, y))
                record = (*elevations, ptr)
                if record not in index_of:
                    index_of[record] = len(records)
                    records.append(record)
                new_grid[x][y] = index_of[record]
        if len(records) > 0xFFFF:
            raise map_file.MapFileError(f"{panel_name} would need {len(records)} records (at most 65,536).")
        out = map_file.write_panel_layer(out, index_name, panel_name, new_grid, records)
    result.tiles_changed = len(changed_tiles)
    result.corners_on_props = len(kept)

    # Props: move each by the surface change at its tile's centre.
    placed = map_file.read_map_bytes(out)
    centres = []
    for inst in placed.build_inst:
        obj = placed.build_desc[inst.desc_index] if 0 <= inst.desc_index < len(placed.build_desc) else None
        if obj is None or map_file.is_base_terrain_object(obj):
            continue
        centres.append((inst, (TILE_SIZE * (inst.x - ox) + TILE_SIZE / 2, TILE_SIZE * (inst.y - oy) + TILE_SIZE / 2)))
    if centres:
        points = [p for _, p in centres]
        before = surface_heights(old_triangles, points)
        change = surface_heights(new_triangles, points) - before
        for (inst, _), d, ground in zip(centres, change, before):
            if np.isnan(d) or abs(d) <= TOLERANCE:
                continue
            # only a prop standing on the old ground (pos_y = -5 * height) follows it
            if abs(-TILE_SIZE * inst.height() - ground) > PROP_ON_SURFACE:
                result.props_kept += 1
                continue
            out = map_file.patch_build_inst_height(out, inst, inst.height() - d / TILE_SIZE)
            result.props_moved += 1
    result.map_bin = out
    return result


# -- one tile's corners ------------------------------------------------------------------

#: The panel layers: ``(index section, panel section, MapData grid, MapData records)``.
LAYERS = {
    "combined": ("panelindex", "uniquepanel", "panel_index", "unique_panel"),
    "ground": ("panelindexBase", "uniquepanelBase", "panel_index_base", "unique_panel_base"),
    "roof": ("panelindexRoof", "uniquepanelRoof", "panel_index_roof", "unique_panel_roof"),
}
#: A prop that doesn't raise the combined layer and is at most this tall
#: (mesh units) is a floor units walk on, such as a bridge deck.
FLOOR_HEIGHT = 1.0

Corners = tuple[int, int, int, int]  # top-left, top-right, bottom-left, bottom-right elevations


def _record(panel: map_file.UniquePanel) -> tuple[int, int, int, int, int]:
    return (panel.top_left_elevation, panel.top_right_elevation, panel.bottom_left_elevation,
            panel.bottom_right_elevation, panel.terrain_type_ptr)


def tile_corners(data: map_file.MapData, tile: tuple[int, int]) -> dict[str, Corners]:
    """The four corner elevations of ``tile`` on each layer the map has."""
    x, y = tile
    out = {}
    for layer, (_index, _panels, grid_attr, records_attr) in LAYERS.items():
        grid, records = getattr(data, grid_attr), getattr(data, records_attr)
        if grid is not None and records and 0 <= x < len(grid) and 0 <= y < len(grid[x]) and 0 <= grid[x][y] < len(records):
            out[layer] = _record(records[grid[x][y]])[:4]
    return out


def set_tile_corners(map_bin: bytes, changes: dict[tuple[int, int], dict[str, Corners]]) -> bytes:
    """``map_bin`` with the corner elevations of tiles set per layer
    (``{tile: {"combined": (tl, tr, bl, br), ...}}``). Tiles share panel
    records: a changed tile points at an identical record or a new one and
    keeps its terrain type (``map_file.write_panel_layer``)."""
    for layer, (index_name, panel_name, grid_attr, records_attr) in LAYERS.items():
        wanted = {tile: values[layer] for tile, values in changes.items() if layer in values}
        if not wanted:
            continue
        data = map_file.read_map_bytes(map_bin)
        grid, panels = getattr(data, grid_attr), getattr(data, records_attr)
        if grid is None or not panels:
            raise map_file.MapFileError(f"This map has no {panel_name} layer.")
        records = [_record(p) for p in panels]
        index_of = {r: i for i, r in reversed(list(enumerate(records)))}
        new_grid = [list(column) for column in grid]
        for (x, y), corners in wanted.items():
            if not (0 <= x < len(grid) and 0 <= y < len(grid[x])):
                raise map_file.MapFileError(f"Tile ({x}, {y}) is outside the map.")
            if len(corners) != 4 or any(not -32768 <= int(c) <= 32767 for c in corners):
                raise map_file.MapFileError("An elevation is a whole number from -32768 to 32767.")
            record = (*(int(c) for c in corners), records[grid[x][y]][4])
            if record not in index_of:
                index_of[record] = len(records)
                records.append(record)
            new_grid[x][y] = index_of[record]
        if len(records) > 0xFFFF:
            raise map_file.MapFileError(f"{panel_name} would need {len(records)} records (at most 65,536).")
        map_bin = map_file.write_panel_layer(map_bin, index_name, panel_name, new_grid, records)
    return map_bin


def prop_rise(name: str, obj: map_file.MapObject, model_top: float) -> float | None:
    """How far above its base a prop raises the combined layer of the tiles
    it covers (``prop_heights.RISE``; a copy named ``<name>_2`` counts as
    ``<name>``), or None when it leaves them alone. A prop vanilla doesn't
    have raises them to its model's top unless flag byte c has one of the
    bits ``0x5C`` (on vanilla maps those props almost never raise)."""
    from .prop_heights import RISE

    stem, _, suffix = name.rpartition("_")
    for key in (name, stem if suffix.isdigit() else None):
        if key in RISE:
            return RISE[key]
    return None if obj.flag_bits_c & 0x5C else model_top


def _elevation(height: float) -> int:
    return max(-32768, min(32767, round(height * ELEVATION_PER_UNIT)))


def _model_triangles(gs_bytes: bytes) -> "np.ndarray":
    m = model.read_model_bytes(gs_bytes)
    tris = [[v.position for v in (s[k], s[k + 1], s[k + 2])] for chunk in m.chunks for s in chunk.strips for k in range(len(s) - 2)]
    return np.array(tris, dtype=float).reshape(-1, 3, 3)


def deduce_corners(files: dict[str, bytes], data: map_file.MapData, tiles) -> dict[tuple[int, int], dict[str, Corners]]:
    """Corner elevations for ``tiles`` estimated from the terrain and the
    props, the way vanilla maps set them: the ground layer is the terrain
    surface, or the deck of a low prop over it (a bridge); the combined and
    roof layers are the ground, or flat at the top of the highest prop
    covering the tile (its base plus ``prop_rise``). A corner off the
    terrain keeps its value. An estimate: on vanilla maps about 80% of all
    tiles come out within 0.05 units of the stored corners on each layer
    (some props raise only part of what they cover)."""
    from . import map_props  # map_props imports this module

    terrain = next((o.filename for o in data.build_desc
                    if map_file.is_base_terrain_object(o) and "water" not in o.filename.lower()), "")
    ox, oy = terrain_origin(data, terrain)
    terrain_tris = map_props.terrain_triangles(files, data)
    tiles = list(tiles)
    covering: dict[tuple[int, int], list] = {t: [] for t in tiles}
    models: dict[str, "np.ndarray"] = {}
    for inst in data.build_inst:
        obj = data.build_desc[inst.desc_index] if 0 <= inst.desc_index < len(data.build_desc) else None
        if obj is None or map_file.is_base_terrain_object(obj) or f"{obj.filename}.gs" not in files:
            continue
        hit = [(x, y) for x in range(inst.x2, inst.end_x2 + 1) for y in range(inst.y2, inst.end_y2 + 1) if (x, y) in covering]
        if not hit:
            continue
        if obj.filename not in models:
            models[obj.filename] = _model_triangles(files[f"{obj.filename}.gs"])
        local = models[obj.filename]
        top = float(local[:, :, 1].max()) if len(local) else 0.0
        rise = prop_rise(obj.filename, obj, top)
        world = None
        if rise is None and top <= FLOOR_HEIGHT and len(local):
            matrix = np.array(inst.world_transform(1.0))
            points = np.concatenate([local.reshape(-1, 3), np.ones((len(local) * 3, 1))], axis=1) @ matrix.T
            world = points[:, :3].reshape(-1, 3, 3)
            world[:, :, 0] -= TILE_SIZE * ox  # into terrain mesh coordinates
            world[:, :, 2] -= TILE_SIZE * oy
        base = -TILE_SIZE * inst.height()
        for tile in hit:
            covering[tile].append((world, None if rise is None else base + rise))

    out = {}
    for tile in tiles:
        x, y = tile
        current = tile_corners(data, tile)
        points = [(TILE_SIZE * (cx - ox), TILE_SIZE * (cy - oy)) for cx, cy in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))]
        ground = surface_heights(terrain_tris, points)
        for world, _top in covering[tile]:
            if world is not None:
                deck = surface_heights(world, points)
                ground = np.where(np.isnan(ground), deck, np.fmax(ground, deck))
        fallback = current.get("ground", current.get("combined", (0, 0, 0, 0)))
        ground_el = tuple(fallback[k] if np.isnan(h) else _elevation(float(h)) for k, h in enumerate(ground))
        tops = [top for _world, top in covering[tile] if top is not None]
        combined = tuple(min(g, _elevation(max(tops))) for g in ground_el) if tops else ground_el
        result = {"ground": ground_el, "combined": combined, "roof": combined}
        out[tile] = {layer: values for layer, values in result.items() if layer in current}
    return out
