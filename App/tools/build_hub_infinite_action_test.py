"""Build a US experimental CISO whose hub units can act repeatedly.

This is deliberately a guarded playtest patch, not a production installer.  The
source executable is restored byte-for-byte after the image has been composed.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fe_modding.formats import gcdisc
from fe_modding.game_code import ppc
from fe_modding.game_code.dol import Dol


REGION = b"GFEE01"
HUB_CONFIG = 0x800021F0
PARTY_CHAPTER = 0x80330718

# These addresses and original words are verified against the US executable.
NORMAL_SITE = 0x8002805C
NORMAL_ORIGINAL = bytes.fromhex("60000001900301a0")  # ori/stw actor acted bit
NORMAL_RETURN = NORMAL_SITE + len(NORMAL_ORIGINAL)
NORMAL_STUB = 0x80001A60

ASYNC_SITE = 0x80028CBC
ASYNC_ORIGINAL = bytes.fromhex("60000001900501a0")   # ori/stw pending actor acted bit
ASYNC_RETURN = ASYNC_SITE + len(ASYNC_ORIGINAL)
ASYNC_STUB = 0x80001AA0

CLEAR_ACTED_R0 = 0x5400003C  # rlwinm r0,r0,0,0,30
SET_ACTED_R0 = 0x60000001    # ori r0,r0,1


def _words(origin: int, program) -> bytes:
    return b"".join(struct.pack(">I", word) for word in ppc.assemble(origin, program))


def _chapter_guarded_store(origin: int, actor_register: int, return_address: int) -> bytes:
    """Store r0 to actor+0x1a0, clearing bit zero in the configured hub."""
    # The asynchronous finalizer keeps the actor pointer in r5.  Do not use
    # that register as scratch while reading HUB_CONFIG: doing so turns the
    # final stw into a write near address 0x1a0 + the hub chapter number.
    config_register = 6 if actor_register == 5 else 5
    high = (PARTY_CHAPTER >> 16) & 0xFFFF
    low = PARTY_CHAPTER & 0xFFFF
    return _words(origin, [
        ppc.lis(4, high), ppc.lbz(4, low, 4),
        ppc.lis(config_register, (HUB_CONFIG >> 16) & 0xFFFF),
        ppc.lbz(config_register, HUB_CONFIG & 0xFFFF, config_register),
        ppc.cmplw(4, config_register), ("ne", "normal"),
        CLEAR_ACTED_R0, ("b", "store"),
        "normal", SET_ACTED_R0,
        "store", ppc.stw(0, 0x1A0, actor_register),
        ("b", return_address),
    ])


def patched_executable(original: bytes, hub_chapter: int | None = None) -> bytes:
    dol = Dol(original)
    normal = _chapter_guarded_store(NORMAL_STUB, 3, NORMAL_RETURN)
    async_ = _chapter_guarded_store(ASYNC_STUB, 5, ASYNC_RETURN)
    checks = (
        (NORMAL_SITE, NORMAL_ORIGINAL, "normal action finalizer"),
        (ASYNC_SITE, ASYNC_ORIGINAL, "asynchronous action finalizer"),
        (NORMAL_STUB, bytes(len(normal)), "normal action code cave"),
        (ASYNC_STUB, bytes(len(async_)), "asynchronous action code cave"),
    )
    for address, expected, label in checks:
        found = dol.read(address, len(expected))
        if found != expected:
            raise ValueError(f"Unexpected {label} bytes at {address:08X}: {found.hex()}")
    installed_chapter = dol.read(HUB_CONFIG, 1)[0]
    if hub_chapter is None:
        hub_chapter = installed_chapter
    if not 33 <= hub_chapter < 90:
        raise ValueError(f"Hub configuration is missing or invalid (chapter {hub_chapter}).")
    if installed_chapter not in (0, hub_chapter):
        raise ValueError(
            f"Requested hub chapter {hub_chapter} conflicts with installed chapter {installed_chapter}.")

    dol.write(NORMAL_STUB, normal)
    dol.write(ASYNC_STUB, async_)
    dol.write(NORMAL_SITE, struct.pack(">II", ppc.b(NORMAL_SITE, NORMAL_STUB), ppc.NOP))
    dol.write(ASYNC_SITE, struct.pack(">II", ppc.b(ASYNC_SITE, ASYNC_STUB), ppc.NOP))
    # An uninstalled hub draft has no router configuration in main.dol.  The
    # guarded playtest only needs its first byte for the chapter comparison.
    dol.write(HUB_CONFIG, bytes((hub_chapter,)))
    return bytes(dol.data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Project root containing extracted/sys/main.dol")
    parser.add_argument("output", type=Path, help="New CISO path")
    parser.add_argument("--hub-chapter", type=int,
                        help="Hub draft chapter (33-89) when routing is not installed in main.dol")
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    executable = root / "extracted" / "sys" / "main.dol"
    boot = root / "extracted" / "sys" / "boot.bin"
    original = executable.read_bytes()
    if boot.read_bytes()[:6] != REGION:
        raise ValueError("This guarded test patch supports only the US GFEE01 fixture.")
    patched = patched_executable(original, args.hub_chapter)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")

    try:
        executable.write_bytes(patched)
        gcdisc.build_gamecube_ciso(root / "extracted", output)
    finally:
        executable.write_bytes(original)
    if executable.read_bytes() != original:
        raise RuntimeError("Failed to restore the source executable.")
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest().upper()
    print(f"Built {output}")
    print(f"SHA-256 {digest}")


if __name__ == "__main__":
    main()
