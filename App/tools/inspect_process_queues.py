"""Census direct ``start_process`` calls by constant scheduler queue.

The FE9 process API overloads its second argument: values 0..7 select one of
eight root queues, while a process pointer creates a child.  This helper scans
the retail US DOL for direct calls and recognizes a nearby ``li r4, N`` so the
main-loop phase queues can be audited without relying on decompiler guesses.
"""

from __future__ import annotations

import bisect
import struct

from inspect_dol_calls import DEFAULT_DOL, direct_target, load_functions, load_sections


START_PROCESS = 0x8000CAF0


def main() -> None:
    blob = DEFAULT_DOL.read_bytes()
    sections = load_sections(blob)
    functions, _ = load_functions()
    starts = [address for address, _ in functions]
    groups: dict[int | None, list[tuple[int, str]]] = {}

    for base, size, file_offset in sections:
        for relative in range(0, size, 4):
            pc = base + relative
            word = struct.unpack_from(">I", blob, file_offset + relative)[0]
            if direct_target(pc, word) != START_PROCESS:
                continue

            queue: int | None = None
            # Direct callers conventionally load r4 immediately before the call.
            # Stop at the first nearby instruction that writes r4.
            for back in range(1, 9):
                if relative < back * 4:
                    break
                prior = struct.unpack_from(">I", blob, file_offset + relative - back * 4)[0]
                opcode = prior >> 26
                rt = (prior >> 21) & 31
                if rt != 4:
                    continue
                if opcode == 14 and ((prior >> 16) & 31) == 0:  # addi r4,r0,imm = li
                    value = prior & 0xFFFF
                    queue = value - 0x10000 if value & 0x8000 else value
                break

            position = bisect.bisect_right(starts, pc) - 1
            owner = functions[position][1] if position >= 0 else "?"
            groups.setdefault(queue, []).append((pc, owner))

    for queue in sorted(groups, key=lambda value: (value is None, value if value is not None else 99)):
        calls = groups[queue]
        label = "dynamic/child" if queue is None or not 0 <= queue < 8 else f"queue {queue}"
        print(f"{label}: {len(calls)} direct calls")
        owners: dict[str, int] = {}
        for _, owner in calls:
            owners[owner] = owners.get(owner, 0) + 1
        for owner, count in sorted(owners.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {count:3}  {owner}")


if __name__ == "__main__":
    main()
