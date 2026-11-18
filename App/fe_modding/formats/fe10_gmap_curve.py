"""Radiant Dawn's world-map route lines: ``gmap/curve/<name>.bin`` and ``gmap/curve/linedefine<n>.bin``.

A world-map event draws an army's route as a textured line along a curve. The loader
``0x8018277C`` reads ``gmap/curve/%s.bin`` into one of eight route slots; the drawer
``0x80182D24`` builds the line strip.

A curve file is big-endian, 0x30 bytes of header, then its points:

====  ====================================================================================
+00   u32 0
+04   the curve's name, NUL-padded to 24 bytes (the file name without ``.bin``)
+1C   u32 frames: how long the line takes to draw (65-300 in retail)
+20   u32 point count
+24   u32 line style 0-7: the picture in ``gmap/tpl/gmap.tpl`` and ``linedefine<style+1>.bin``
+28   u32 colour 0, 1, 2 or other (four colour pairs in the DOL; retail uses 0, 1 and 2)
+2C   u32 0 on disc; the loader stores the points' address there
====  ====================================================================================

A point is six f32: x, y, z and the tangent x, y, z (z is 0 everywhere), in 608 x 448 screen
pixels. Between two points the line follows the cubic Hermite curve of their positions and
tangents (:func:`sample`; the game's own interpolation was not traced in full).

``linedefine<n>.bin`` (eight files, loaded by ``0x80181470``) holds two **little-endian** doubles,
which the game byte-swaps once and marks by setting the word at +0x10 (absent on the Japanese
disc): the line's half width (multiplies the drawer's base width) and the length one repeat of
the line texture covers.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

HEADER_SIZE = 0x30
POINT_SIZE = 24
NAME_SIZE = 24
STYLES = 8
SCREEN = (608, 448)


class CurveError(ValueError):
    pass


@dataclass
class CurvePoint:
    x: float
    y: float
    tx: float = 0.0
    ty: float = 0.0
    z: float = 0.0
    tz: float = 0.0


@dataclass
class Curve:
    name: str
    frames: int = 90
    style: int = 3
    colour: int = 2
    points: list[CurvePoint] = field(default_factory=list)
    lead: int = 0
    runtime: int = 0


@dataclass
class LineDefine:
    width: float
    texture_length: float
    tail: bytes = b"\0\0\0\0"


def read_curve(data: bytes) -> Curve:
    if len(data) < HEADER_SIZE:
        raise CurveError("A curve file is at least 0x30 bytes.")
    lead = struct.unpack_from(">I", data, 0)[0]
    raw_name = data[4:4 + NAME_SIZE]
    name = raw_name.split(b"\0", 1)[0].decode("ascii")
    if raw_name[len(name):].strip(b"\0"):
        raise CurveError("The curve name field holds bytes after its end.")
    frames, count, style, colour, runtime = struct.unpack_from(">5I", data, 0x1C)
    if len(data) != HEADER_SIZE + POINT_SIZE * count:
        raise CurveError(f"{name}: {count} points need {HEADER_SIZE + POINT_SIZE * count} bytes, "
                         f"the file has {len(data)}.")
    points = []
    for i in range(count):
        x, y, z, tx, ty, tz = struct.unpack_from(">6f", data, HEADER_SIZE + POINT_SIZE * i)
        points.append(CurvePoint(x, y, tx, ty, z, tz))
    return Curve(name, frames, style, colour, points, lead, runtime)


def build_curve(curve: Curve) -> bytes:
    name = curve.name.encode("ascii")
    if not name or len(name) >= NAME_SIZE:
        raise CurveError(f"A curve name is 1-{NAME_SIZE - 1} ASCII characters.")
    if not 0 <= curve.style < STYLES:
        raise CurveError(f"The line style is 0-{STYLES - 1}.")
    out = bytearray(struct.pack(">I", curve.lead) + name.ljust(NAME_SIZE, b"\0"))
    out += struct.pack(">5I", curve.frames, len(curve.points), curve.style, curve.colour, curve.runtime)
    for p in curve.points:
        out += struct.pack(">6f", p.x, p.y, p.z, p.tx, p.ty, p.tz)
    return bytes(out)


def read_line_define(data: bytes) -> LineDefine:
    if len(data) < 16:
        raise CurveError("A linedefine file holds two doubles.")
    width, length = struct.unpack_from("<2d", data, 0)
    return LineDefine(width, length, data[16:])


def build_line_define(line: LineDefine) -> bytes:
    return struct.pack("<2d", line.width, line.texture_length) + line.tail


def sample(curve: Curve, steps: int = 16) -> list[tuple[float, float]]:
    """Screen points along the curve (cubic Hermite between neighbouring points)."""
    pts = curve.points
    if len(pts) < 2:
        return [(p.x, p.y) for p in pts]
    out = [(pts[0].x, pts[0].y)]
    for a, b in zip(pts, pts[1:]):
        for k in range(1, steps + 1):
            s = k / steps
            h00, h10 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s
            h01, h11 = -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
            out.append((h00 * a.x + h10 * a.tx + h01 * b.x + h11 * b.tx,
                        h00 * a.y + h10 * a.ty + h01 * b.y + h11 * b.ty))
    return out
