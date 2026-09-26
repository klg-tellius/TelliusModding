"""Compress/decompress the LZ10-style scheme used by every ``.cmp`` file.

This is Nintendo's classic "type 0x10" LZ77 variant (the same one used by
the GBA/DS BIOS decompression routines): a 4-byte header (0x10 marker + a
24-bit little-endian decompressed size), followed by chunks of one flag byte
per 8 tokens. A set flag bit means "2-byte back-reference" (12-bit offset-1,
4-bit length-3, so matches run 3..18 bytes over a 4096-byte window); a clear
bit means "1 literal byte".
"""

from __future__ import annotations

import struct
from pathlib import Path

MAGIC = 0x10
MAX_MATCH_LENGTH = 18  # 4-bit length field + 3
MAX_WINDOW = 0x1000  # 12-bit offset field + 1


class LZ10Error(Exception):
    pass


def decompress(data: bytes) -> bytes:
    if len(data) < 4 or data[0] != MAGIC:
        raise LZ10Error(f"Not an LZ10 stream (expected marker byte 0x{MAGIC:02X} first).")

    decompressed_length = data[1] | (data[2] << 8) | (data[3] << 16)
    out = bytearray(decompressed_length)
    out_pos = 0
    in_pos = 4

    while out_pos < decompressed_length and in_pos < len(data):
        flags = data[in_pos]
        in_pos += 1
        for bit in range(7, -1, -1):
            if out_pos >= decompressed_length:
                break
            if flags & (1 << bit):
                reference = (data[in_pos] << 8) | data[in_pos + 1]
                in_pos += 2
                length = min((reference >> 12) + 3, decompressed_length - out_pos)
                offset = (reference & 0xFFF) + 1
                start = out_pos - offset
                if offset >= length:
                    out[out_pos : out_pos + length] = out[start : start + length]
                else:
                    # overlapping match: the last `offset` bytes repeat
                    out[out_pos : out_pos + length] = (out[start:out_pos] * (length // offset + 1))[:length]
                out_pos += length
            else:
                out[out_pos] = data[in_pos]
                in_pos += 1
                out_pos += 1

    return bytes(out)


def compress(data: bytes) -> bytes:
    length = len(data)
    out = bytearray(struct.pack("<B", MAGIC) + struct.pack("<I", length)[:3])

    # position_by_key[3-byte sequence] -> list of positions where it occurs, oldest first.
    position_by_key: dict[int, list[int]] = {}
    last_indexed = -1
    pos = 0

    while pos < length:
        flags_byte_index = len(out)
        out.append(0)  # placeholder, filled in below
        flags = 0

        for bit in range(8):
            if pos >= length:
                break

            # Fewer than 3 bytes left: can't form a match key, so this last
            # byte or two always goes out as a literal.
            if pos > length - 3:
                out.append(data[pos])
                pos += 1
                continue

            key = (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]
            candidates = position_by_key.get(key)
            best_length = 0
            best_offset = 0

            if candidates:
                candidates[:] = [p for p in candidates if p >= pos - MAX_WINDOW]
                for candidate in reversed(candidates):
                    match_length = 3
                    while (
                        pos + match_length < length
                        and match_length < MAX_MATCH_LENGTH
                        and data[candidate + match_length] == data[pos + match_length]
                    ):
                        match_length += 1
                    if match_length > best_length:
                        best_length = match_length
                        best_offset = pos - candidate
                    if best_length == MAX_MATCH_LENGTH:
                        break

            if best_length >= 3:
                flags |= 1 << (7 - bit)
                out.append(((best_length - 3) << 4) | (((best_offset - 1) >> 8) & 0xF))
                out.append((best_offset - 1) & 0xFF)
                pos += best_length
            else:
                out.append(data[pos])
                pos += 1

            while last_indexed < pos - 2 and last_indexed + 3 < length:
                last_indexed += 1
                dict_key = (data[last_indexed] << 16) | (data[last_indexed + 1] << 8) | data[last_indexed + 2]
                position_by_key.setdefault(dict_key, []).append(last_indexed)

        out[flags_byte_index] = flags

    while len(out) % 4 != 0:
        out.append(0)

    return bytes(out)


def decompress_file(path: Path | str) -> bytes:
    return decompress(Path(path).read_bytes())


def compress_file(path: Path | str) -> bytes:
    return compress(Path(path).read_bytes())
