"""Proposed regional block-version edits; system-data dates remain retail.

These edits are deliberately separate from installation. All fragments must be
built against the same unchanged retail input before applying any of them.
"""
from . import ppc
from .catalog import Edit
from .dol import DolError
from .extended_flag_container import FILENAMES
from .extended_flag_runtime import NativeImage, _address
from .extended_flag_version_sites import SITES


def build_version_fragment(dol, version, core):
    if version not in SITES:
        raise ValueError("Unsupported block-version region")
    filename = FILENAMES[version][0]
    if "card_open_guard" not in core.functions or not any(e.address == filename for e in core.edits):
        raise ValueError("Block versions require a separate validated container")
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Version fragment requires matching retail inputs")
    sites = SITES[version]
    for kind, windows in sites.items():
        if kind == "finalize":
            windows = (windows,)
        for at, raw in windows:
            start = at - 12 if kind == "finalize" else at
            if dol.read(start, len(bytes.fromhex(raw))) != bytes.fromhex(raw):
                raise DolError("Block-version instruction window differs from retail")
    low = 0x102 if version == "GFEP01" else 0x101
    edits = list(core.edits)

    def add(at, word):
        if any(at < e.address + len(e.original) and e.address < at + 4 for e in edits):
            raise ValueError("Block-version edit overlaps another fragment")
        edits.append(Edit(at, dol.read(at, 4), word.to_bytes(4, "big")))

    for at, _ in sites["compare"]:
        add(at + 4, (dol.u32(at + 4) & 0xFFFF0000) | (-0x5446 & 0xFFFF))
        add(at + 8, (dol.u32(at + 8) & 0xFFFF0000) | low)
    for at, _ in sites["construct"]:
        add(at, (dol.u32(at) & 0xFFFF0000) | 0x5446)
        add(at + 8, (dol.u32(at + 8) & 0xFFFF0000) | low)

    # The following retail code reuses both the date register and CR0 for
    # system data. Replace only the block store and preserve that machine state.
    at, _ = sites["finalize"]
    offset = 0x3A00
    data = bytearray(core.data)
    if any(data[offset:offset + 0x200]):
        raise ValueError("Block-version code slot occupied")
    program = [ppc.stwu(1, -16, 1), ppc.stw(12, 8, 1),
               *_address(12, 0x54460000 | low), ppc.stw(12, 0x44, 29),
               ppc.lwz(12, 8, 1), ppc.addi(1, 1, 16), ("b", at + 4)]
    code = b"".join(w.to_bytes(4, "big") for w in ppc.assemble(core.base + offset, program))
    data[offset:offset + len(code)] = code
    add(at, ppc.b(at, core.base + offset))
    functions = dict(core.functions, block_version_finalize=core.base + offset)
    return NativeImage(core.base, bytes(data), tuple(edits), functions)
