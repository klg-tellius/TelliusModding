"""The retail builds of Path of Radiance whose ``main.dol`` the game-code tab understands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dol import Dol


@dataclass(frozen=True)
class GameVersion:
    code: str          # disc id, as in sys/boot.bin
    region: str
    label: str
    dol_sha1: str      # SHA-1 of the retail, unmodified main.dol
    text1_size: int    # size of the main text section; patches never resize it


VERSIONS: dict[str, GameVersion] = {v.code: v for v in (
    GameVersion("GFEE01", "US", "Path of Radiance (USA)",
                "9d00d7d407750b82cb1cfccc56f8aa8a89cc8851", 0x2623E0),
    GameVersion("GFEP01", "EU", "Path of Radiance (Europe)",
                "1cf18d42d52c745d533715895c3a6649802324e9", 0x26B140),
    GameVersion("GFEJ01", "JP", "Souen no Kiseki (Japan)",
                "9ef55736e1c0968f00aeeafbee5a34ffdb7bba88", 0x25C400),
)}


@dataclass(frozen=True)
class Identification:
    version: GameVersion | None
    pristine: bool     # True when the DOL is byte-identical to the retail one
    note: str = ""


def read_boot_code(extracted_dir: Path | str) -> str | None:
    """Game code (``GFEE01``...) from ``sys/boot.bin``, or None."""
    boot = Path(extracted_dir) / "sys" / "boot.bin"
    if not boot.is_file():
        return None
    header = boot.read_bytes()[:6]
    return header.decode("ascii", "replace") if len(header) == 6 else None


def identify(dol: Dol, boot_code: str | None = None) -> Identification:
    """Which retail build ``dol`` is, whether or not patches have already been applied.

    The SHA-1 recognises an untouched DOL. A modified one is recognised by the disc's game
    code (``boot_code``), cross-checked against the main text section size, which patches do
    not change; without a boot code the section size alone decides."""
    sha1 = dol.sha1()
    for version in VERSIONS.values():
        if version.dol_sha1 == sha1:
            return Identification(version, True)
    text1 = max((s.size for s in dol.text_sections), default=0)
    if boot_code is not None:
        version = VERSIONS.get(boot_code)
        if version is None:
            return Identification(None, False, f"Unsupported disc {boot_code}.")
        if version.text1_size != text1:
            return Identification(None, False, f"main.dol does not match {version.label} (different code size).")
        return Identification(version, False, "Modified main.dol.")
    for version in VERSIONS.values():
        if version.text1_size == text1:
            return Identification(version, False, "Modified main.dol.")
    return Identification(None, False, "Unrecognised main.dol.")
