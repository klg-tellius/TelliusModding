"""Build a building roof over a rectangle of tiles (Map Builder > Props > Add roof).

The generated model is an ordinary static prop (``map_props.import_prop``): only a flat or
gabled roof, resting at ``wall_height`` on walls the map already has, textured once per tile
(the texture repeats). Walls are never generated. Its ``mapbuilddesc`` record gets the flags of the retail
mansion and castle roofs (flag byte c ``0x08``, effect ``0x09``), so the game treats it as one:

- while it is closed its tiles take the map's roof layer, which ``map_file.sync_door_terrain``
  fills with 屋根 at the top of the roof (the map's walls stay walls, doors stay 扉);
- a door inside its tiles or next to them lifts it when it opens (``DoorOpen`` looks for such a
  roof), showing the room's floor from the main layer. No script is needed.

Model coordinates follow ``map_props``: 5 units per tile, the placed tile's corner at the
origin, y up. Every face is double-sided.
"""

from __future__ import annotations

import io
import random
import struct
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import map_props
from .formats import gltf_export, map_file, pak

TILE = map_file.TILE_UNITS
#: A roof's top must clear this height to count as a building roof (``map_file.ROOF_MIN_HEIGHT``).
MIN_TOP = map_file.ROOF_MIN_HEIGHT
STYLES = ("gable", "flat")
TEXTURE_SIZE = 64


def _rows(base, line, rows=4, jitter=12, seed=0) -> Image.Image:
    """Overlapping tiles or slates: rows of rounded shingles with a darker edge."""
    rng = random.Random(seed)
    image = Image.new("RGB", (TEXTURE_SIZE, TEXTURE_SIZE), base)
    draw = ImageDraw.Draw(image)
    step = TEXTURE_SIZE // rows
    for r in range(rows):
        y = r * step
        offset = (step // 2) * (r % 2)
        for x in range(-step, TEXTURE_SIZE + step, step):
            shade = tuple(max(0, min(255, c + rng.randint(-jitter, jitter))) for c in base)
            draw.rounded_rectangle((x + offset, y, x + offset + step - 1, y + step - 1), radius=step // 3,
                                   fill=shade, outline=line)
        draw.line((0, y, TEXTURE_SIZE, y), fill=line)
    return image


def _planks(base, line, seed=0) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new("RGB", (TEXTURE_SIZE, TEXTURE_SIZE), base)
    draw = ImageDraw.Draw(image)
    for x in range(0, TEXTURE_SIZE, 8):
        shade = tuple(max(0, min(255, c + rng.randint(-14, 14))) for c in base)
        draw.rectangle((x, 0, x + 7, TEXTURE_SIZE - 1), fill=shade)
        draw.line((x, 0, x, TEXTURE_SIZE), fill=line)
    return image


def _straw(base, seed=0) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new("RGB", (TEXTURE_SIZE, TEXTURE_SIZE), base)
    draw = ImageDraw.Draw(image)
    for _ in range(420):
        x, y = rng.randrange(TEXTURE_SIZE), rng.randrange(TEXTURE_SIZE)
        shade = tuple(max(0, min(255, c + rng.randint(-40, 30))) for c in base)
        draw.line((x, y, x + rng.randint(-2, 2), y + rng.randint(4, 9)), fill=shade)
    return image


#: Built-in textures: name -> function making a 64x64 image that repeats once per tile.
PRESETS = {
    "Red tiles": lambda: _rows((178, 74, 48), (110, 40, 26), seed=1),
    "Slate": lambda: _rows((92, 100, 116), (52, 56, 66), rows=5, jitter=8, seed=2),
    "Blue tiles": lambda: _rows((60, 92, 150), (32, 50, 88), seed=3),
    "Green copper": lambda: _rows((96, 150, 128), (58, 96, 80), rows=3, jitter=8, seed=4),
    "Thatch": lambda: _straw((196, 164, 92), seed=5),
    "Wooden planks": lambda: _planks((132, 92, 56), (76, 50, 30), seed=6),
}
ROOF_PRESET = "Red tiles"


def preset_image(name: str) -> Image.Image:
    return PRESETS[name]()


@dataclass
class RoofSpec:
    """Tiles ``width`` x ``depth`` from the placed tile; heights in map units (5 per tile)."""

    width: int
    depth: int
    roof_image: Image.Image
    style: str = "gable"
    wall_height: float = 5.0  # height of the map's walls the roof rests on
    rise: float = 2.5  # how far a gable's ridge rises above the walls

    @property
    def top(self) -> float:
        return self.wall_height + (self.rise if self.style == "gable" else 0.0)


def _quad(points, uvs):
    """Two triangles of a quad given in order round its edge."""
    a, b, c, d = points
    ua, ub, uc, ud = uvs
    return [((a, b, c), (ua, ub, uc)), ((a, c, d), (ua, uc, ud))]


def roof_triangles(spec: RoofSpec) -> dict[str, list]:
    """Triangles of the roof as ((p0, p1, p2), (uv0, uv1, uv2)), UVs in tiles. A gable's two
    end triangles close it under the ridge, in the same texture."""
    w, d, h = spec.width * TILE, spec.depth * TILE, spec.wall_height
    t = TILE
    roof = []
    if spec.style == "flat":
        roof += _quad([(0, h, 0), (w, h, 0), (w, h, d), (0, h, d)], [(0, 0), (w / t, 0), (w / t, d / t), (0, d / t)])
        return roof
    r = spec.rise
    if w >= d:  # ridge along x, halfway across z
        m = d / 2
        slope = (m * m + r * r) ** 0.5 / t
        roof += _quad([(0, h, 0), (w, h, 0), (w, h + r, m), (0, h + r, m)], [(0, slope), (w / t, slope), (w / t, 0), (0, 0)])
        roof += _quad([(0, h, d), (w, h, d), (w, h + r, m), (0, h + r, m)], [(0, slope), (w / t, slope), (w / t, 0), (0, 0)])
        for x in (0, w):  # gable ends
            roof.append((((x, h, 0), (x, h, d), (x, h + r, m)), ((0, r / t), (d / t, r / t), (m / t, 0))))
    else:  # ridge along z
        m = w / 2
        slope = (m * m + r * r) ** 0.5 / t
        roof += _quad([(0, h, 0), (0, h, d), (m, h + r, d), (m, h + r, 0)], [(0, slope), (d / t, slope), (d / t, 0), (0, 0)])
        roof += _quad([(w, h, 0), (w, h, d), (m, h + r, d), (m, h + r, 0)], [(0, slope), (d / t, slope), (d / t, 0), (0, 0)])
        for z in (0, d):
            roof.append((((0, h, z), (w, h, z), (m, h + r, z)), ((0, r / t), (w / t, r / t), (m / t, 0))))
    return roof


def roof_glb(spec: RoofSpec) -> bytes:
    """The roof model as a binary glTF with one double-sided textured material."""
    triangles = roof_triangles(spec)
    binary = bytearray()
    views, accessors, primitives, materials, images, textures = [], [], [], [], [], []

    def view(data: bytes) -> int:
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary.extend(data + bytes(-len(data) % 4))
        return len(views) - 1

    for part, image in (("roof", spec.roof_image),):
        positions = [p for tri, _uv in triangles for p in tri]
        uvs = [uv for _tri, uv_tri in triangles for uv in uv_tri]
        lo = [min(p[k] for p in positions) for k in range(3)]
        hi = [max(p[k] for p in positions) for k in range(3)]
        pos = view(b"".join(struct.pack("<3f", *p) for p in positions))
        uv = view(b"".join(struct.pack("<2f", *q) for q in uvs))
        accessors.append({"bufferView": pos, "componentType": 5126, "count": len(positions), "type": "VEC3",
                          "min": lo, "max": hi})
        accessors.append({"bufferView": uv, "componentType": 5126, "count": len(uvs), "type": "VEC2"})
        png = io.BytesIO()
        image.convert("RGBA").save(png, format="PNG")
        images.append({"bufferView": view(png.getvalue()), "mimeType": "image/png"})
        textures.append({"source": len(images) - 1})
        materials.append({"name": f"roof_{part}", "doubleSided": True,
                          "pbrMetallicRoughness": {"baseColorTexture": {"index": len(textures) - 1}}})
        primitives.append({"attributes": {"POSITION": len(accessors) - 2, "TEXCOORD_0": len(accessors) - 1},
                           "material": len(materials) - 1})
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "roof", "mesh": 0}],
        "meshes": [{"primitives": primitives}],
        "materials": materials,
        "images": images,
        "textures": textures,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    return gltf_export._pack_glb(doc, bytes(binary))


def check_spec(spec: RoofSpec) -> None:
    if spec.width < 1 or spec.depth < 1:
        raise map_file.MapFileError("A roof covers at least one tile each way.")
    if spec.width * spec.depth < map_file.ROOF_MIN_TILES:
        raise map_file.MapFileError(f"A roof covers at least {map_file.ROOF_MIN_TILES} tiles "
                                    "(smaller roof objects are not lifted by doors).")
    if spec.style not in STYLES:
        raise map_file.MapFileError(f"Roof style is one of {', '.join(STYLES)}.")
    if spec.top < MIN_TOP:
        raise map_file.MapFileError(f"The top of the roof must be at least {MIN_TOP:g} units high.")
    if spec.wall_height <= 0 or spec.rise < 0:
        raise map_file.MapFileError("Wall height must be above 0 and the rise 0 or more.")


def add_roof(entries: list[pak.PakEntry], files: dict[str, bytes], x: int, y: int, spec: RoofSpec,
             name: str | None = None) -> tuple[str, int, list[str]]:
    """Build the roof model, add it to the map as a roof prop and place it with its corner on
    tile ``(x, y)``. Updates ``entries``/``files`` (the unpacked ``map.cmp``) in place and returns
    ``(prop name, instance index, warnings)``; placing fills the roof layer
    (``map_props.sync_doors``)."""
    check_spec(spec)
    data = map_file.read_map_bytes(files["map.bin"])
    if data.layout.game == "fe10":
        raise map_file.MapFileError("Generated roofs are for Path of Radiance maps.")
    if data.capacity is not None and (x < 0 or y < 0 or x + spec.width > data.capacity.x_size
                                      or y + spec.depth > data.capacity.y_size):
        raise map_file.MapFileError("The roof must fit on the map.")
    name = name or map_props.free_prop_name(files, data, "roof")
    warnings = map_props.import_prop(entries, files, roof_glb(spec), name)
    data = map_file.read_map_bytes(files["map.bin"])
    obj = next(o for o in data.build_desc if o.filename == name)
    map_bin = map_file.patch_object_field(files["map.bin"], obj, "flag_bits_c", map_file.ROOF_OBJECT_FLAG)
    obj = next(o for o in map_file.read_map_bytes(map_bin).build_desc if o.filename == name)
    files["map.bin"] = map_file.patch_object_field(map_bin, obj, "effect_type", 0x09)
    index = map_props.place_prop(files, name, x, y, 0)
    warnings += map_props.sync_doors(files)
    return name, index, warnings
