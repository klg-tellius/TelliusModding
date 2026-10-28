"""Hue-band recolouring of textures: the colour maths behind character and
class colour variants (``colour_variants.py``).

A :class:`Recolour` picks the colours to change by hue (a band around
``hue``, fading out over ``feather`` degrees) and skips greys, whites and
blacks (``min_saturation``), so skin, hair and steel can stay as they were
while a red tabard turns blue. Matching colours get their hue turned by
``shift`` degrees and their saturation and brightness scaled.

:func:`recolour_tpl` applies it to a ``.tpl`` through
``tpl.map_colours``: a portrait's palette, a CMPR texture's block
endpoints, other formats pixel by pixel.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

import numpy as np

from .formats import tpl


@dataclass(frozen=True)
class Recolour:
    hue: float = 0.0  # centre of the hue band to change, degrees (0 red, 120 green, 240 blue)
    band: float = 30.0  # half-width of the band, degrees; 180 changes every hue
    shift: float = 0.0  # degrees added to the hue of matching colours
    saturation: float = 1.0  # saturation multiplier for matching colours
    brightness: float = 1.0  # brightness (HSV value) multiplier for matching colours
    feather: float = 15.0  # degrees over which the change fades out past the band
    min_saturation: float = 0.12  # colours greyer than this are left alone

    @classmethod
    def between(cls, source: tuple[int, int, int], target: tuple[int, int, int], band: float = 30.0,
                **fields) -> "Recolour":
        """The recolour taking ``source`` (RGB 0-255) to ``target``: the band
        is centred on the source's hue, the shift and the saturation and
        brightness ratios come from the target."""
        h0, s0, v0 = colorsys.rgb_to_hsv(*(c / 255 for c in source))
        h1, s1, v1 = colorsys.rgb_to_hsv(*(c / 255 for c in target))
        return cls(hue=h0 * 360, band=band, shift=((h1 - h0) * 360 + 180) % 360 - 180,
                   saturation=min(4.0, s1 / s0) if s0 > 0.01 else 1.0,
                   brightness=min(4.0, v1 / v0) if v0 > 0.01 else 1.0, **fields)

    @property
    def is_identity(self) -> bool:
        return self.shift % 360 == 0 and self.saturation == 1.0 and self.brightness == 1.0

    def describe(self) -> str:
        parts = [f"hues {self.hue:.0f}°±{self.band:.0f}°"]
        if self.shift % 360:
            parts.append(f"turned {self.shift:+.0f}°")
        if self.saturation != 1.0:
            parts.append(f"saturation x{self.saturation:.2f}")
        if self.brightness != 1.0:
            parts.append(f"brightness x{self.brightness:.2f}")
        return ", ".join(parts)

    def weights(self, hue: np.ndarray, saturation: np.ndarray) -> np.ndarray:
        """How much each colour changes, 0-1: 1 inside the band, fading to 0
        over the feather, and 0 for greys."""
        if self.band >= 180:
            by_hue = np.ones_like(hue)
        else:
            distance = np.abs((hue - self.hue + 180) % 360 - 180)
            by_hue = np.clip(1 - (distance - self.band) / max(self.feather, 1e-6), 0, 1)
        by_saturation = np.clip((saturation - self.min_saturation) / 0.06 + 0.5, 0, 1)
        return by_hue * by_saturation

    def apply(self, rgba: np.ndarray) -> np.ndarray:
        """``rgba`` (..., 4 uint8) recoloured; alpha is kept."""
        rgba = np.asarray(rgba, dtype=np.uint8)
        if self.is_identity:
            return rgba.copy()
        hue, sat, val = rgb_to_hsv(rgba[..., :3].astype(np.float64) / 255)
        weight = self.weights(hue, sat)
        hue = (hue + self.shift * weight) % 360
        sat = np.clip(sat * (1 + (self.saturation - 1) * weight), 0, 1)
        val = np.clip(val * (1 + (self.brightness - 1) * weight), 0, 1)
        out = rgba.copy()
        out[..., :3] = np.round(hsv_to_rgb(hue, sat, val) * 255).astype(np.uint8)
        changed = weight > 0
        out[..., :3] = np.where(changed[..., None], out[..., :3], rgba[..., :3])
        return out


def rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized ``colorsys.rgb_to_hsv`` with the hue in degrees."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    high, low = rgb.max(axis=-1), rgb.min(axis=-1)
    delta = high - low
    safe = np.where(delta > 0, delta, 1)
    hue = np.where(high == r, (g - b) / safe % 6, np.where(high == g, (b - r) / safe + 2, (r - g) / safe + 4))
    hue = np.where(delta > 0, hue * 60, 0.0)
    sat = np.where(high > 0, delta / np.where(high > 0, high, 1), 0.0)
    return hue, sat, high


def hsv_to_rgb(hue: np.ndarray, sat: np.ndarray, val: np.ndarray) -> np.ndarray:
    """Inverse of :func:`rgb_to_hsv` (hue in degrees), RGB 0-1."""
    sector = hue / 60
    chroma = val * sat
    x = chroma * (1 - np.abs(sector % 2 - 1))
    zero = np.zeros_like(hue)
    index = np.floor(sector).astype(int) % 6
    choices = [np.stack(c, axis=-1) for c in ((chroma, x, zero), (x, chroma, zero), (zero, chroma, x),
                                              (zero, x, chroma), (x, zero, chroma), (chroma, zero, x))]
    rgb = np.choose(index[..., None], choices)
    return rgb + (val - chroma)[..., None]


def recolour_tpl(tpl_bytes: bytes, recolour: Recolour) -> bytes:
    """``tpl_bytes`` with every image recoloured (see ``tpl.map_colours``)."""
    if recolour.is_identity:
        return tpl_bytes
    return tpl.map_colours(tpl_bytes, recolour.apply)
