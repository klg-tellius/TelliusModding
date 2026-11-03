"""Compositing helpers for dialogue portrait base faces and face parts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PIL import Image

from .face_data import FaceDataRecord


@dataclass(frozen=True)
class PortraitAsset:
    base: Image.Image
    parts: tuple[Image.Image, ...]
    face_data: Optional[FaceDataRecord] = None

    def render(self, expression: str | None = None, frame_ms: int = 0) -> Image.Image:
        out = self.base.convert("RGBA").copy()
        holes = _transparent_components(out)
        parts = tuple(part.convert("RGBA") for part in self.parts)
        if not parts:
            return out

        eye_parts = [p for p in parts if p.width >= p.height]
        mouth_parts = [p for p in parts if p.width < p.height or p.width <= 24]
        if not mouth_parts:
            mouth_parts = list(parts)
        if not eye_parts:
            eye_parts = list(parts)

        eye_holes = sorted([h for h in holes if h[2] - h[0] >= h[3] - h[1]], key=lambda h: h[1])
        mouth_holes = sorted([h for h in holes if h[2] - h[0] < h[3] - h[1]], key=lambda h: h[1])
        if not eye_holes and holes:
            eye_holes = [holes[0]]
        if not mouth_holes and len(holes) > 1:
            mouth_holes = [holes[-1]]

        expression_offset = _expression_offset(expression)
        blink_index = _cycle_index(frame_ms, 4200, len(eye_parts), hold_first=True)
        mouth_index = _cycle_index(frame_ms, 180, len(mouth_parts), hold_first=False)
        if expression_offset:
            blink_index = min(len(eye_parts) - 1, blink_index + expression_offset)
            mouth_index = min(len(mouth_parts) - 1, mouth_index + expression_offset)

        if eye_holes and eye_parts:
            _paste_centered(out, eye_parts[blink_index], _record_or_hole(self.face_data.eye if self.face_data else None, eye_holes[0]))
        if mouth_holes and mouth_parts:
            _paste_centered(
                out,
                mouth_parts[mouth_index],
                _record_or_hole(self.face_data.mouth if self.face_data else None, mouth_holes[-1]),
            )
        return out


def _transparent_components(image: Image.Image) -> list[tuple[int, int, int, int]]:
    alpha = image.getchannel("A")
    width, height = image.size
    seen: set[tuple[int, int]] = set()
    components: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if (x, y) in seen or alpha.getpixel((x, y)) != 0:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            min_x = max_x = x
            min_y = max_y = y
            count = 0
            while stack:
                px, py = stack.pop()
                count += 1
                min_x, max_x = min(min_x, px), max(max_x, px)
                min_y, max_y = min(min_y, py), max(max_y, py)
                for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in seen:
                        continue
                    if alpha.getpixel((nx, ny)) == 0:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if count >= 12:
                components.append((min_x, min_y, max_x + 1, max_y + 1))
    return components


def _record_or_hole(record_xy: Optional[tuple[int, int]], hole: tuple[int, int, int, int]) -> tuple[int, int]:
    if record_xy is not None:
        return record_xy
    return ((hole[0] + hole[2]) // 2, (hole[1] + hole[3]) // 2)


def _paste_centered(base: Image.Image, part: Image.Image, center: tuple[int, int]) -> None:
    x = int(center[0] - part.width / 2)
    y = int(center[1] - part.height / 2)
    base.alpha_composite(part, (x, y))


def _cycle_index(frame_ms: int, period_ms: int, count: int, hold_first: bool) -> int:
    if count <= 1:
        return 0
    if hold_first:
        phase = frame_ms % period_ms
        if phase < period_ms - (count - 1) * 80:
            return 0
        return min(count - 1, 1 + (phase - (period_ms - (count - 1) * 80)) // 80)
    return (frame_ms // period_ms) % count


def _expression_offset(expression: str | None) -> int:
    # main.dol confirms these commands feed expression animation parameters;
    # exact semantic names are still under research, so use a deterministic
    # frame-family offset that visibly changes the composited parts.
    return {"c": 0, "d": 1, "h": 2, "o": 3, "A": 4}.get(expression or "", 0)
