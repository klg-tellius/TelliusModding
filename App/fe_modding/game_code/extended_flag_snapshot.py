"""RAM-only AllPush/AllPop state hooks, separate from the card save format.

The retail engine has one snapshot buffer. Mirror it with one reserved shadow
of the extended record and live masks, owned by that buffer's base pointer.
Restore after the retail deserializer restores the party/chapter. Ordinary local
resets preserve the shadow; boot/new-playthrough reset invalidates its owner.
"""
import hashlib

from . import ppc
from .catalog import Edit
from .dol import DolError
from .extended_flag_runtime import (
    NativeImage, _address, RECORD_OFFSET, SNAPSHOT_OFFSET, SNAPSHOT_SIZE, SNAPSHOT_OWNER_OFFSET,
)

SITES = {
    "GFEE01": {
        "snapshot_read": (0x801E3654, 328, "41bbc627023dc32488e5447cfd1384664854e1e38370a2544db60b367528b23c"),
        "snapshot_write": (0x801E38E0, 384, "0706e9fdac6d168aba27aac30ea919e46b4708e1a5b2b464668188b10283ec5d"),
    },
    "GFEP01": {
        "snapshot_read": (0x801E6890, 328, "224448d46f5035424453dcdf5001788510dde1b6e8c2858bcdfce65c01a4ebe9"),
        "snapshot_write": (0x801E6B1C, 384, "10dd2d478710474fbd9f87f7646adaa4638034463a163ad3d654410cb3a1d261"),
    },
    "GFEJ01": {
        "snapshot_read": (0x801E0010, 328, "a499924cea65aa6e2e2c418888ed64fb5ec9708d8b40b175ac94082f4fb0ddd7"),
        "snapshot_write": (0x801E029C, 384, "200ac995ae27c69fa9c7fae8ff002d2b85e6a5fc439d2222f3a4c91d6b462ed4"),
    },
}


def build_snapshot_fragment(dol, version, core):
    if version not in SITES:
        raise ValueError("Unsupported snapshot region")
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Snapshot hooks require the matching retail core")
    data, edits, functions = bytearray(core.data), list(core.edits), dict(core.functions)
    for name, (address, size, digest) in SITES[version].items():
        if hashlib.sha256(dol.read(address, size)).hexdigest() != digest:
            raise DolError(f"{name}: retail code differs")
        reading = name == "snapshot_read"
        offset = 0x2400 if reading else 0x2200
        site = address + (0x100 if reading else 0x138)
        source = core.base + (SNAPSHOT_OFFSET if reading else RECORD_OFFSET)
        destination = core.base + (RECORD_OFFSET if reading else SNAPSHOT_OFFSET)
        program = [*_address(4, core.base + SNAPSHOT_OWNER_OFFSET), ppc.lwz(5, 8, 1)]
        if reading:
            program += [ppc.lwz(6, 0, 4), ppc.cmpwi(6, 0), ("eq", "done"),
                        ppc.cmplw(5, 6), ("ne", "done")]
        program += [*_address(7, source), *_address(8, destination), ppc.li(9, SNAPSHOT_SIZE // 4),
                    "copy", ppc.lwz(10, 0, 7), ppc.stw(10, 0, 8),
                    ppc.addi(7, 7, 4), ppc.addi(8, 8, 4), ppc.addi(9, 9, -1),
                    ppc.cmpwi(9, 0), ("ne", "copy")]
        if reading:
            program += [ppc.li(5, 0)]
        program += [ppc.stw(5, 0, 4), "done", dol.u32(site), ("b", site + 4)]
        code = b"".join(word.to_bytes(4, "big") for word in ppc.assemble(core.base + offset, program))
        if len(code) > 0x200 or any(data[offset:offset + 0x200]):
            raise ValueError("Snapshot code slot occupied or too small")
        data[offset:offset + len(code)] = code
        functions[name] = core.base + offset
        edits.append(Edit(site, dol.read(site, 4), ppc.b(site, core.base + offset).to_bytes(4, "big")))
    return NativeImage(core.base, bytes(data), tuple(edits), functions)
