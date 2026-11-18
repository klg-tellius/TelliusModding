"""How much of an extracted disc the corpus tests walk.

Tests that loop over every file of a kind (every model, map, texture, message...) take most of
the suite's time. By default they check a fixed sample; ``TELLIUS_CORPUS=full`` makes them walk
everything, which is what to run before a pull request:

    set TELLIUS_CORPUS=full        (PowerShell: $env:TELLIUS_CORPUS = "full")

A test samples with :func:`sample` and checks counts that only hold for the whole disc under
``if FULL``.
"""

from __future__ import annotations

import os
from typing import Callable, Iterable, Sequence, TypeVar

T = TypeVar("T")

#: True when the corpus tests walk every file (``TELLIUS_CORPUS=full``).
FULL = os.environ.get("TELLIUS_CORPUS", "sample").strip().lower() == "full"
#: Files a sampled loop checks, besides the ones it names to keep.
SAMPLE_SIZE = 12


def sample(items: Iterable[T], keep: Sequence[str] = (), size: int = SAMPLE_SIZE,
           key: Callable[[T], str] = str) -> list[T]:
    """``items`` in order: all of them under ``TELLIUS_CORPUS=full``, else ``size`` of them evenly
    spread (always the first and the last) plus every item whose ``key`` contains one of
    ``keep``. The choice is the same on every run."""
    items = list(items)
    if FULL or len(items) <= size:
        return items
    step = (len(items) - 1) / (size - 1)
    chosen = {round(i * step) for i in range(size)}
    chosen |= {i for i, item in enumerate(items) if any(k in key(item) for k in keep)}
    return [items[i] for i in sorted(chosen)]


def disc_id(files) -> str:
    """The retail disc ID of an extracted ``files/`` folder (``RFEE01``...), from ``sys/boot.bin``
    beside it; ``""`` when there is none. A Radiant Dawn disc test runs on whichever region
    ``FE10_EXTRACTED`` points at."""
    from pathlib import Path
    try:
        boot = Path(files).parent / "sys" / "boot.bin"
        raw = boot.read_bytes()[:6].decode("ascii", "replace")
    except (OSError, TypeError):
        return ""
    from fe_modding.games import retail_disc_id
    return retail_disc_id(raw)


def per_disc(files, us, eu=None, jp=None):
    """``us``, ``eu`` or ``jp`` by the region of ``files`` (``eu``/``jp`` default to ``us``)."""
    region = disc_id(files)[3:4]
    if region == "P" and eu is not None:
        return eu
    if region == "J" and jp is not None:
        return jp
    return us


def require_us(test, files, what: str = "the US disc's own values") -> None:
    """Skip ``test`` unless ``files`` is the US disc (a check of US-only content)."""
    code = disc_id(files)
    if code and code[3:4] != "E":
        test.skipTest(f"checks {what}; this is {code}")
