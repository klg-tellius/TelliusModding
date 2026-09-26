# Script global variables

How the event-script VM's global variables (`global name @ slot` in `.fe9s`, opcodes `0x0D`–`0x18`) work in the US Path of Radiance executable. Research reference: `research/MAIN_DOL_NOTES.md`, "Script global variables".

## Storage — Confirmed

- At boot `init_event_script_system` calls `init_script_global_state(0x20, 0x1a0)`. It allocates `script_global_value_table` as **32 words** (pointer at `0x80367198`, `0x80924060` in every RAM dump) and sets the capacity `0x80367194` to 32.
- The allocation is **not zeroed**. Every RAM dump, the main menu included, shows the same leftover heap values in the slots no script has written.
- No other code writes the table. Nothing clears it on a chapter load, nothing reallocates it, and none of the save-stream serializers (`BMST` … `"T  T"`, `AllPush`/`AllPop`) include it.

## Addressing — Confirmed

- Every global opcode reads or writes `script_global_value_table[operand]` (or `[operand + index]` for the array forms) directly. **Slot numbers are absolute and shared by every loaded script.**
- Each call path also computes `table + header+0x20` and saves/restores it in the call frame, but no opcode reads that value. It is dead bookkeeping.
- There is no bounds check. The 8-bit operand forms are signed (−128..127), and a slot outside 0–31 reaches into neighbouring heap memory.

## Reservation — Confirmed

- Header `+0x22` is the number of slots a script reserves; vanilla sets it to the highest slot it declares + 1.
- On load, `load_script_buffer_and_fixup` writes the running total (`0x80367196`) into header `+0x20` and adds `+0x22` to it. If the total passes 32, it sets status `0x803671a8` = 8 and skips the whole function-table fixup, so none of that script's functions can be called.
- `cm_free_script` subtracts the count again. Scripts are freed last-loaded first.
- Vanilla reservations: C01, C19 and C90 reserve 6; C20 reserves 8; C30 and C31 reserve 4; every other script reserves 0, `startup.cmb` included.

## Lifetime

A value lasts from the write until power-off or the next write to that slot by any script. It survives chapter changes in memory but is not saved. After a save is loaded, the slot holds whatever happened to be in memory, either from earlier in the session or leftover data after a fresh boot.

## Vanilla usage

- **C01 / C90:** an `@on_select` or exported function stores Ike's and the selected units' tile coordinates; `@after_action` functions compare against them.
- **C31:** `@on_death(PID_ASHNARD)` stores Ashnard's and the killer's positions; the next `@after_action` uses them to stage the second phase.
- **C30:** `Startup` zeroes slots 0–3.
- **C20:** `@on_death(PID_NAESALA)` writes slots 6 and 7, and no script ever reads them.

All vanilla reads follow a write in the same action or chapter session; nothing relies on a global surviving a save.

## Modding guidance

- Treat globals as scratch memory shared between events of one chapter session: write before reading, ideally in `Startup`.
- Use slots 0–31 only. The app's compiler rejects any other slot and sets the header reservation to the highest declared slot + 1, keeping a larger existing reservation.
- For values that must survive a save or a chapter change, use event flags (`docs/toInclude/event_flags_and_save_blocks.md`). A number can be stored as several flags, one per bit.

## Open

- Nothing further: the second allocation made by `init_script_global_state` is the native handler registry (`script_native_registry_and_trigger_names.md`).
