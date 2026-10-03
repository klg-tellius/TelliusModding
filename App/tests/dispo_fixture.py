"""A minimal dispo file for tests (shared so tests need not import test_formats, which needs Tkinter)."""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import dispo


def build_minimal_dispo_bytes(names=(b"SECA", b"SECB")) -> bytes:
    """A minimal dispo file in the vanilla layout: a date link section at
    0x20 (pointing at the first label), then one-unit sections, the label
    pool, the relocation table and the section table."""
    from fe_modding.formats.common import HEADER_SIZE

    buf = bytearray(HEADER_SIZE)
    date_addr = len(buf)
    buf += bytes(4)  # link word, patched below
    section_addrs, unit_addrs = [], []
    for _name in names:
        section_addrs.append(len(buf))
        buf += struct.pack(">bBBB", 1, 4, 0, 2)
        unit_addrs.append(len(buf))
        buf += bytes(dispo.RECORD_SIZE)

    label_map_start = len(buf)
    buf += b"DATE\x00PID_TEST\x00JID_TEST\x00"
    buf += bytes(-len(buf) % 4)
    label_map_end = len(buf)

    date_key = label_map_start - HEADER_SIZE
    pid_key = date_key + len(b"DATE\x00")
    jid_key = pid_key + len(b"PID_TEST\x00")
    struct.pack_into(">I", buf, date_addr, date_key)
    for unit_addr in unit_addrs:
        struct.pack_into(dispo.RECORD_FORMAT, buf, unit_addr, *([pid_key, jid_key] + [0] * 46))

    relocations = [date_addr - HEADER_SIZE]
    for unit_addr in unit_addrs:
        relocations += [unit_addr - HEADER_SIZE, unit_addr - HEADER_SIZE + 4]
    buf += b"".join(struct.pack(">I", r) for r in relocations)

    all_names = [b"DATE"] + list(names)
    offsets, position = [], 0
    for name in all_names:
        offsets.append(position)
        position += len(name) + 1
    for address, offset in zip([date_addr] + section_addrs, offsets):
        buf += struct.pack(">II", address - HEADER_SIZE, offset)
    buf += b"".join(name + b"\x00" for name in all_names)

    struct.pack_into(">4I", buf, 0, len(buf), label_map_end - HEADER_SIZE, len(relocations), len(all_names))
    return bytes(buf)
