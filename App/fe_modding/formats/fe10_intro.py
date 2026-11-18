"""Radiant Dawn's ``FE10Intro.bin``: the Extras class introductions.

A :mod:`pool_file` file with one symbol, ``FE10Intro`` (offset 0): a u16 count, two zero bytes,
then 64-byte records. The intro scene (``0x8026A9D4``) loads ``FE10Intro.bin``, the picture
``intro/intro.cms`` and the texts ``intro.m``, finds the first record of the current group and
stages each class in battle. Per record:

====  =====================================================================================
+00   u8 list group (0-6; the scene starts at the first record of the selected group), 3 zero bytes
+04   battle unit (``剣士一般``, ``光の賢者ミカヤ``...: the unit the battle stage shows)
+08   class JID
+0C   battle scenery (``bg0104平地2``, a ``zbg/`` backdrop) / +10 sky (``曇り``...)
+14   camera distance (``近距離`` close, ``上空近`` close from above for fliers)
+18   picture: ``intro/<name>.cms``, an LZ10 TPL
+1C   description message (``MS_INTRO_...`` in ``intro.m``)
+20   ``兵種紹介`` on every record / +24 weapon by Japanese name (``なし`` for none)
+28   u32, 300 on every record (not traced)
+2C   up to five motions played in turn (``攻撃１``, ``構え``...), zero after the last
====  =====================================================================================
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .pool_file import PoolFile, TableWriter, build_pool_file, read_pool_file

SYMBOL = "FE10Intro"
RECORD_SIZE = 64
MOTION_SLOTS = 5
TEXT_FIELDS = ("unit", "jid", "scenery", "sky", "camera", "picture", "text", "kind", "weapon")


class IntroError(ValueError):
    pass


@dataclass
class ClassIntro:
    group: int
    unit: str | None
    jid: str | None
    scenery: str | None
    sky: str | None
    camera: str | None
    picture: str | None
    text: str | None
    kind: str | None = "兵種紹介"
    weapon: str | None = "なし"
    frames: int = 300
    motions: list[str] = field(default_factory=list)
    group_pad: int = 0

    @property
    def motion_list(self) -> str:
        return ", ".join(self.motions)

    @motion_list.setter
    def motion_list(self, value: str | None) -> None:
        motions = [m.strip() for m in (value or "").replace("、", ",").split(",") if m.strip()]
        if len(motions) > MOTION_SLOTS:
            raise IntroError(f"At most {MOTION_SLOTS} motions.")
        self.motions = motions


@dataclass
class IntroData:
    entries: list[ClassIntro] = field(default_factory=list)
    count_pad: int = 0
    trailer: bytes = b""
    header_tail: bytes = bytes(12)


def read_intros(data: bytes) -> IntroData:
    doc = read_pool_file(data)
    if doc.symbols != [(SYMBOL, 0)]:
        raise IntroError("FE10Intro.bin should export FE10Intro at offset 0.")
    body, pointers = doc.body, doc.pointers
    count, pad = struct.unpack_from(">HH", body, 0)
    out = IntroData(count_pad=pad, header_tail=doc.header_tail)
    at = 4
    if at + count * RECORD_SIZE > len(body):
        raise IntroError("FE10Intro.bin ends inside its records.")
    for _ in range(count):
        group, group_pad = body[at], int.from_bytes(body[at + 1:at + 4], "big")
        texts = [pointers.get(at + 4 + 4 * k) for k in range(len(TEXT_FIELDS))]
        (frames,) = struct.unpack_from(">I", body, at + 0x28)
        motions = []
        for k in range(MOTION_SLOTS):
            value = pointers.get(at + 0x2C + 4 * k)
            if value is None:
                if struct.unpack_from(">I", body, at + 0x2C + 4 * k)[0]:
                    raise IntroError(f"Expected a motion name or zero at {at + 0x2C + 4 * k:#x}.")
                break
            motions.append(value)
        out.entries.append(ClassIntro(group, *texts, frames=frames, motions=motions, group_pad=group_pad))
        at += RECORD_SIZE
    out.trailer = body[at:]
    return out


def build_intros(document: IntroData) -> bytes:
    w = TableWriter()
    w.pack(">HH", len(document.entries), document.count_pad)
    for e in document.entries:
        if len(e.motions) > MOTION_SLOTS:
            raise IntroError(f"{e.jid}: at most {MOTION_SLOTS} motions.")
        w.raw(bytes([e.group & 0xFF]) + (e.group_pad & 0xFFFFFF).to_bytes(3, "big"))
        for name in TEXT_FIELDS:
            w.text(getattr(e, name))
        w.word(e.frames)
        for k in range(MOTION_SLOTS):
            w.text(e.motions[k] if k < len(e.motions) else None)
    w.raw(document.trailer)
    return build_pool_file(PoolFile(bytes(w.body), w.pointers, [(SYMBOL, 0)], document.header_tail))
