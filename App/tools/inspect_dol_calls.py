"""List direct PowerPC call edges for selected functions in an FE9 DOL.

Run from the repository root::

    python App/tools/inspect_dol_calls.py 801a0434 801a05f4

The function names and sizes come from the committed US executable maps.  This
small static helper is intentionally limited to direct ``bl`` instructions;
process-script pointers and other indirect calls still require separate review.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research" / "main_dol"
DEFAULT_DOL = RESEARCH / "dols" / "GFEE01.dol"


def load_sections(blob: bytes) -> list[tuple[int, int, int]]:
    offsets = struct.unpack(">18I", blob[:72])
    addresses = struct.unpack(">18I", blob[72:144])
    sizes = struct.unpack(">18I", blob[144:216])
    return [(address, size, offset) for offset, address, size
            in zip(offsets, addresses, sizes) if offset and size]


def load_functions() -> tuple[list[tuple[int, str]], dict[int, tuple[int, str]]]:
    starts = []
    with (RESEARCH / "function_starts.tsv").open(encoding="utf-8") as stream:
        for line in stream:
            address, name = line.rstrip().split("\t", 1)
            starts.append((int(address, 16), name))

    sizes = {}
    with (RESEARCH / "us_eu_function_map.tsv").open(
            newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            sizes[int(row["src_addr"], 16)] = (
                int(row["size"], 16), row["src_name"])
    return starts, sizes


def direct_target(pc: int, word: int) -> int | None:
    if word >> 26 != 18 or not word & 1:
        return None
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return ((0 if word & 2 else pc) + displacement) & 0xFFFFFFFF


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("addresses", nargs="+", type=lambda value: int(value, 16))
    parser.add_argument("--dol", type=Path, default=DEFAULT_DOL)
    parser.add_argument("--reverse", action="store_true",
                        help="list every direct caller and raw aligned pointer to each address")
    args = parser.parse_args()

    blob = args.dol.read_bytes()
    sections = load_sections(blob)
    functions, mapped = load_functions()
    starts = [address for address, _ in functions]

    if args.reverse:
        for address in args.addresses:
            print(f"references to {address:08X}")
            pointer = struct.pack(">I", address)
            for base, size, file_offset in sections:
                for relative in range(0, size, 4):
                    pc = base + relative
                    word = struct.unpack_from(">I", blob, file_offset + relative)[0]
                    if direct_target(pc, word) == address:
                        position = bisect.bisect_right(starts, pc) - 1
                        name = functions[position][1] if position >= 0 else "?"
                        start = starts[position] if position >= 0 else 0
                        print(f"  call {pc:08X} in {name}@{start:08X}")
            cursor = 0
            while True:
                cursor = blob.find(pointer, cursor)
                if cursor < 0:
                    break
                for base, size, file_offset in sections:
                    if file_offset <= cursor < file_offset + size:
                        print(f"  pointer {base + cursor - file_offset:08X}")
                        break
                cursor += 1
        return

    for address in args.addresses:
        position = bisect.bisect_right(starts, address)
        if address in mapped:
            size, name = mapped[address]
        else:
            if not position or position == len(starts):
                raise SystemExit(f"unknown function address {address:08X}")
            size = starts[position] - address
            name = functions[position - 1][1]
        section = next((entry for entry in sections
                        if entry[0] <= address < entry[0] + entry[1]), None)
        if section is None:
            raise SystemExit(f"address {address:08X} is outside the DOL")
        base, _, file_offset = section
        print(f"{name}@{address:08X} size=0x{size:X}")
        for pc in range(address, address + size, 4):
            word = struct.unpack_from(">I", blob, file_offset + pc - base)[0]
            target = direct_target(pc, word)
            if target is None:
                continue
            target_position = bisect.bisect_right(starts, target) - 1
            target_name = "?"
            if target_position >= 0 and starts[target_position] == target:
                target_name = functions[target_position][1]
            print(f"  {pc:08X} -> {target:08X} {target_name}")


if __name__ == "__main__":
    main()
