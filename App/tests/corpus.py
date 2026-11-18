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
