"""TPL textures embedded in the LZ10 pack archives used by ``sky`` and ``zbg``."""

from __future__ import annotations

from . import lz10, pak


def read_packed_tpl(raw: bytes) -> bytes:
    """Return the sole TPL member of an LZ10-compressed pack archive."""
    archive = lz10.decompress(raw)
    entries = pak.read_pak_entries(archive)
    textures = [entry for entry in entries if entry.name.lower().endswith(".tpl")]
    if len(textures) != 1:
        raise ValueError(f"Expected one TPL in the archive, found {len(textures)}.")
    return pak.read_pak_file_content(archive, textures[0])


def replace_packed_tpl(raw: bytes, replacement: bytes) -> bytes:
    """Replace a pack's sole TPL while retaining member order and reserved words."""
    archive = lz10.decompress(raw)
    entries = pak.read_pak_entries(archive)
    texture_indices = [i for i, entry in enumerate(entries) if entry.name.lower().endswith(".tpl")]
    if len(texture_indices) != 1:
        raise ValueError(f"Expected one TPL in the archive, found {len(texture_indices)}.")
    texture_index = texture_indices[0]
    files = [(entry.name, replacement if i == texture_index else pak.read_pak_file_content(archive, entry))
             for i, entry in enumerate(entries)]
    return lz10.compress(pak.pack_pak(files, [entry.reserved for entry in entries]))
