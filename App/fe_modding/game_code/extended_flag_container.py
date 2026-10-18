"""Separate card filename for extended saves, without relocating string users.

Retail's shortest filename is ten characters. A ten-character ASCII name keeps
all existing references intact: X plus 45 bits of a hashed layout identity.
Full UUID validation remains authoritative if two shortened names ever collide.
"""
import base64
import hashlib

from .catalog import Edit
from .dol import DolError
from .extended_flag_runtime import NativeImage

FILENAMES = {
    "GFEE01": (0x80272648, b"FIREEMBLEM8J\0"),
    "GFEP01": (0x8027B909, b"FIREEMBLEM8\0"),
    "GFEJ01": (0x8026C145, b"FIREEMBLEM8J\0"),
}


def container_name(identity: bytes) -> str:
    if not isinstance(identity, bytes) or len(identity) != 16 or not any(identity):
        raise ValueError("Container identity must be a nonzero 16-byte UUID")
    digest = hashlib.sha256(b"FE9 extended flags v1\0" + identity).digest()
    return "X" + base64.b32encode(digest).decode("ascii")[:9]


def build_container_fragment(dol, version, core):
    if version not in FILENAMES:
        raise ValueError("Unsupported save-container region")
    if "card_open_guard" not in core.functions:
        raise ValueError("Separate container requires full-layout validation on open")
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Container fragment requires matching retail inputs")
    at, original = FILENAMES[version]
    if dol.read(at, len(original)) != original:
        raise DolError("Card filename differs from retail")
    relative_record = core.record_address - core.base
    name = container_name(core.data[relative_record + 8:relative_record + 24])
    patched = (name.encode("ascii") + b"\0").ljust(len(original), b"\0")
    if any(edit.address == at for edit in core.edits):
        raise ValueError("Container fragment already present")
    return NativeImage(core.base, core.data, core.edits + (Edit(at, original, patched),), core.functions)
