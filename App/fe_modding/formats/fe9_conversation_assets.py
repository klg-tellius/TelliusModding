"""Project-backed FE9 conversation resources (no Tk dependency or asset guesses)."""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageOps
from . import lz10, pak, tpl, message
from .fe9_portraits import FaceAsset, read_face_table
from .fe9_font import GameFont


@dataclass(frozen=True)
class RectPart:
    kind: int
    raw: bytes
    resource: str = ""
    window: str = ""
    panel: str = ""
    marker: str = ""


@dataclass(frozen=True)
class RectResource:
    name: str
    parts: tuple[RectPart, ...]


def read_rect_resources(data: bytes) -> dict[str, RectResource]:
    if len(data) < 32:
        raise ValueError("Truncated rect resource")
    size, reloc, reloc_count, exports = struct.unpack_from(">4I", data)
    table = 32 + reloc + 4 * reloc_count
    strings = table + 8 * exports
    if size != len(data) or strings > size:
        raise ValueError("Invalid rect resource bounds")

    def cstring(offset: int) -> str:
        end = data.find(b"\0", offset)
        if offset < 32 or not offset <= end < size:
            raise ValueError("Invalid rect string pointer")
        return data[offset:end].decode("shift_jis")

    def pointer_string(raw: bytes, offset: int) -> str:
        pointer = struct.unpack_from(">I", raw, offset)[0]
        return cstring(pointer + 32) if pointer else ""

    result = {}
    for index in range(exports):
        offset, name_offset = struct.unpack_from(">II", data, table + index * 8)
        offset += 32
        name = cstring(strings + name_offset)
        if offset + 20 > table:
            raise ValueError(f"Invalid descriptor: {name}")
        count = data[offset + 4]
        if offset + 20 + 4 * count > table:
            raise ValueError(f"Truncated descriptor: {name}")
        parts = []
        for i in range(count):
            p = 32 + struct.unpack_from(">I", data, offset + 20 + 4 * i)[0]
            if not 32 <= p < 32 + reloc:
                raise ValueError(f"Invalid part pointer: {name}")
            kind = data[p]
            lengths = {0: 24, 1: 36, 2: 40, 3: 24, 5: 32, 6: 52}
            length = 10 + 8 * struct.unpack_from(">H", data, p + 8)[0] if kind == 4 else lengths.get(kind, 8)
            raw = data[p:p + length]
            if len(raw) != length:
                raise ValueError(f"Truncated part: {name}")
            if kind in (1, 6):
                parts.append(RectPart(kind, raw, resource=pointer_string(raw, 8)))
            elif kind == 2:
                parts.append(RectPart(kind, raw, window=pointer_string(raw, 8),
                                      panel=pointer_string(raw, 12), marker=pointer_string(raw, 16)))
            else:
                parts.append(RectPart(kind, raw))
        result[name] = RectResource(name, tuple(parts))
    return result


class ConversationAssets:
    def __init__(self, extracted: Path):
        direct = extracted / "files"
        candidates = [direct] if direct.is_dir() else list(extracted.glob("**/files"))
        if len(candidates) != 1:
            raise ValueError("Expected one extracted game files directory")
        self.files = candidates[0]
        self._signatures = {}
        self._archive = {}
        self._textures = {}
        self._faces = {}
        self._fonts = {}
        self._rect_images = {}
        self._colors = {}
        self.refresh()

    def _signature(self, path: Path):
        try:
            s = path.stat()
            return s.st_mtime_ns, s.st_size
        except FileNotFoundError:
            return None

    def refresh(self) -> bool:
        """Reload modified resources at message/load/play boundaries, not per frame."""
        paths = {self.files / "system.cmp", self.files / "Mess/common.m",
                 self.files / "s/rect.bin", self.files / "window/rectdesc.bin"}
        paths.update(self._signatures)
        for folder, pattern in (("Face", "*.cms"), ("Fonts", "*.gcf"), ("Fonts", "*.cms"), ("window", "*.tpl")):
            paths.update((self.files / folder).glob(pattern))
        changed = not self._signatures or any(self._signature(p) != self._signatures.get(p) for p in paths)
        if not changed:
            return False
        self._signatures = {p: self._signature(p) for p in paths}
        self._textures.clear(); self._faces.clear(); self._fonts.clear(); self._rect_images.clear(); self._colors.clear()
        packed = lz10.decompress((self.files / "system.cmp").read_bytes())
        self._archive = {e.name.replace("\\", "/").casefold(): pak.read_pak_file_content(packed, e)
                         for e in pak.read_pak_entries(packed)}
        self.faces = read_face_table(self.read("face/facedata.bin"))
        self.rects = {}
        for resource in ("s/rect.bin", "window/rectdesc.bin"):
            self.rects.update(read_rect_resources(self.read(resource)))
        self.names = {m.speaker: m.text for m in message.read_messages_path(self.files / "Mess/common.m")}
        return True

    def read(self, name: str) -> bytes:
        path = self.files / name
        if ".." in Path(name).parts or Path(name).is_absolute():
            raise ValueError("Invalid resource path")
        if path.is_file():
            self._signatures[path] = self._signature(path)
            return path.read_bytes()
        try:
            return self._archive[name.casefold()]
        except KeyError:
            raise ValueError(f"Missing game resource: {name}") from None

    def textures(self, name: str) -> tuple[Image.Image, ...]:
        if name not in self._textures:
            data = self.read(name)
            if data[:1] == b"\x10":
                data = lz10.decompress(data)
            self._textures[name] = tuple(i.convert("RGBA") for i in tpl.read_tpl_images(io.BytesIO(data)))
        return self._textures[name]

    def face(self, fid: str) -> FaceAsset:
        fid = fid if fid.startswith("FID_") else "FID_" + fid
        if fid not in self._faces:
            if fid not in self.faces:
                raise ValueError(f"Unknown portrait: {fid}")
            record = self.faces[fid]
            images = self.textures("Face/" + record.filename)
            self._faces[fid] = FaceAsset(record, images)
        return self._faces[fid]

    def font(self, name="talk") -> GameFont:
        if name not in self._fonts:
            if name == "system":  # load_system_font reads the compressed .cms; system.gcf is unused
                data = lz10.decompress(self.read("Fonts/system.cms"))
            else:
                data = self.read(f"Fonts/{name}.gcf")
            self._fonts[name] = GameFont(data)
        return self._fonts[name]

    def display_name(self, fid: str) -> str:
        face = self.faces.get(fid)
        if face is None or face.name_id not in self.names:
            raise ValueError(f"Missing portrait display name: {fid}")
        return self.names[face.name_id]

    def text_color(self, index: int) -> tuple[int, int, int, int]:
        """US main.dol's RGBA palette, used by #C in the glyph renderer."""
        if not 0 <= index <= 0x22 or index in (0x13, 0x14, 0x22):
            raise ValueError(f"Unsupported animated/unknown text color {index:02X}")
        if index in self._colors:
            return self._colors[index]
        boot = self.files.parent / 'sys/boot.bin'
        if boot.is_file() and boot.read_bytes()[:6] != b'GFEE01':
            raise ValueError("Text color palette lookup is currently verified only for US FE9")
        path = self.files.parent / 'sys/main.dol'
        self._signatures[path] = self._signature(path)
        data = path.read_bytes()
        address = 0x80296088 + index*4
        if len(data) < 0x100:
            raise ValueError("Truncated main.dol while resolving text colors")
        for section in range(18):
            offset = struct.unpack_from('>I',data,section*4)[0]
            start = struct.unpack_from('>I',data,0x48+section*4)[0]
            size = struct.unpack_from('>I',data,0x90+section*4)[0]
            if start <= address and address+4 <= start+size:
                colors = data[offset+address-start:offset+address-start+4]
                if len(colors)==4:
                    self._colors[index] = tuple(colors)
                    return self._colors[index]
        raise ValueError("US FE9 text color table is unavailable")

    def layout(self, name: str) -> RectResource:
        key = name if name.startswith("RID_") else "RID_" + name
        if key not in self.rects:
            raise ValueError(f"Unknown conversation layout/background: {key}")
        return self.rects[key]

    def seats(self, layout: str) -> tuple[tuple[int, int, bool], ...]:
        result = []
        for part in self.layout(layout).parts:
            if part.kind == 4:
                for i in range(struct.unpack_from(">H", part.raw, 8)[0]):
                    offset = 10 + i * 8
                    x, y = struct.unpack_from(">hh", part.raw, offset)
                    if part.raw[offset + 4] == 0:
                        result.append((x, y, bool(part.raw[offset + 6] & 1)))
        return tuple(result)

    def draw_resource(self, image: Image.Image, name: str, *, bounds=None,
                      brightness=255, frame=0) -> None:
        resource = self.layout(name)
        parts = resource.parts
        # Animated descriptors are arrays of frames, not composited layers.
        if name == "RID_PAGECUR":
            parts = (parts[(frame // 4) % len(parts)],)
        for index, part in enumerate(parts):
            raw = part.raw
            if part.kind == 5:
                x1, y1, x2, y2 = struct.unpack_from(">4h", raw, 8)
                if bounds:
                    x, y, w = bounds
                    x1, y1, x2, y2 = x + 2, y + 2, x + w - 4, y + 114
                colors = [tuple(raw[n:n+4]) for n in (16, 20, 24, 28)]
                if x2 <= x1 or y2 <= y1:
                    continue
                gradient = Image.new("RGBA", (2, 2))
                gradient.putdata(colors)
                gradient = gradient.resize((x2-x1, y2-y1), Image.Resampling.BILINEAR)
                image.alpha_composite(gradient, (x1, y1))
            elif part.kind == 1:
                x1, y1, x2, y2 = struct.unpack_from(">4h", raw, 20)
                u1, v1, u2, v2 = struct.unpack_from(">4H", raw, 28)
                if bounds:
                    x, y, w = bounds
                    if index == 1:
                        x1 = x2 = x; y1 = y2 = y
                    elif index == 2:
                        x1 = x2 = x + w - 50; y1 = y2 = y
                    elif index == 3:
                        x1, y1, x2, y2 = x + 50, y, x + w - 50, y + 118
                x2 = x1 + abs(u2-u1) if x1 == x2 else x2
                y2 = y1 + abs(v2-v1) if y1 == y2 else y2
                if x2 <= x1 or y2 <= y1:
                    continue
                textures = self.textures(part.resource)
                texture = textures[raw[18]]
                tile = texture.crop((min(u1,u2), min(v1,v2), max(u1,u2)+int(u1==u2), max(v1,v2)+int(v1==v2)))
                if u2 < u1: tile = ImageOps.mirror(tile)
                if v2 < v1: tile = ImageOps.flip(tile)
                tile = tile.resize((x2-x1, y2-y1), Image.Resampling.BILINEAR)
                if brightness != 255 or raw[19] != 255:
                    r,g,b,a = tile.split()
                    table = [i*brightness//255 for i in range(256)]
                    tile = Image.merge("RGBA", (r.point(table),g.point(table),b.point(table),a.point(lambda i:i*raw[19]//255)))
                image.alpha_composite(tile, (x1,y1))
            elif part.kind not in (2, 4):
                raise ValueError(f"{name}: unsupported descriptor part {part.kind}")
