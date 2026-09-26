# Native handler registry, trigger names and the talk/battle direction flag

The second table allocated by `init_script_global_state`, the debug dump that reads it, and what that dump says about event triggers. Research reference: `research/MAIN_DOL_NOTES.md`, "Native handler registry and the C-minor function dump".

## The native handler registry — Confirmed

- `init_script_global_state(0x20, 0x1a0)` allocates, besides the 32-word global table, `script_native_entry_table` (`0x803671a0`): **416 records of 16 bytes**.
- Every `register_native_handler(name, handler, argc)` call appends one record:

  | Offset | Content |
  |---|---|
  | `+0x0` | Name string |
  | `+0x4` | Native handler |
  | `+0x8` | Script info, 0 for a native |
  | `+0xD` | Argument count |

  The record is also hashed by name, so `externCall("Name")` finds it the same way it finds script functions.
- Vanilla registers 406 natives; 10 records are free. Registering past 416 sets script status 9 and silently drops the handler.

## The developers' names — Confirmed

The table's only reader is a debug-console dump, `debug_dump_cminor_registered_functions` (`0x800C221C`), headed **`C-minor登録関数一覧`** ("C-minor registered function list"). **C-minor** is the developers' name for the event-script language. The dump lists every native as `Ｃ関数/Name(arg, arg)`, then every loaded script function with its module and trigger type, using these names:

| Type | Engine name | App decorator |
|---|---|---|
| 0 | local | *(none)* |
| 1 | Complete | `@on_complete` |
| 2 | Gameover | `@on_gameover` |
| 3 | Turn | `@before_phase` |
| 4 | Area | `@on_area` |
| 5 | Poke | `@on_location` |
| 6 | TurnAfter | `@on_phase` |
| 7 | Taiki (待機, "wait") | `@after_action` |
| 8 | Talk | `@on_talk` |
| 9 | BossTalk | `@on_battle` |
| 10 | Die | `@on_death_map` |
| 11 | LocalDie | `@on_death` |
| 12 | Achieve | `@on_scenario_end` |
| 13 | Yell | `@on_support` |
| 14 | BaseTalk | `@on_base_talk` |
| 15 | Pickup | `@on_select` |

Support levels print as `YL_` + `"NCBA"[level]`: level 1 is C, 2 is B, 3 is A. This matches the `MYELL_` support message IDs.

## The talk/battle direction flag — Confirmed

The dump prints the third parameter of Talk and BossTalk triggers as `true`/`false`. The event predicates read it (event `+0x18`) as a direction flag:

- **Talk (8):** with 0, the event fires only when character 1 talks to character 2; with 1, either can start it. Vanilla uses 0 on 37 talk events and 1 on 15.
- **Battle (9):** with 0, character 1 must be the acting unit (the attacker) and character 2 its target; with 1, each named character may be on either side. An empty character matches any unit in both modes. All 271 vanilla battle events use 1.
- Both skip the event while the flag named by its label (`+0x1A`) is set.

## Still open

- Which event wins when several battle events match the same fight.
