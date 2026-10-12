# FE9 chapter and promotion choices

Scope: US Path of Radiance (`GFEE01`). The executable addresses below were checked in the local Ghidra project in read-only mode on 2026-10-09. Chapter call sites come from `main_dol/notes/script_reference_observations.json`; that index records calls from an extracted project and is not a full control-flow dump.

## Endgame royal ally

`C31.cmb` function `func_18` calls `Dialog4Items("MS_31_DLG_TIBARN", "MS_31_DLG_NAESALA", "MS_31_DLG_GIFFCA", "MS_31_DLG_NO")`. The generic `Dialog4Items` native waits for selection; `DialogResult()` reads the selected entry value. A different chapter can use the same dialog and branch on the result, with its own loaded message keys and recruitment/deployment actions. The observed call index does not establish the exact branch bodies or choice-number mapping in `func_18`; inspect the full decompiled C31 function before copying it.

## Chapter 17 auxiliary units

`C18.cmb` calls `SelectAuxiliary("bmap18_mikata_zoen_02_c")` in `Opening18_2`, and analogous `_03_c`/`_04_c` groups in `Opening18_3`/`Opening18_4`. Later, `func_60` calls `DisposAuxiliary` on these same groups. `SelectAuxiliary(group)` opens the unit selector and waits; `DisposAuxiliary(group)` places the selected reserve units on that group's tiles and transfers them to the player force. To use this in another chapter, provide a valid deployment section in its loaded map's `dispos.cmp`, call `SelectAuxiliary` at the desired event point, then `DisposAuxiliary` with the same name when they join. Chapter 17's `Complete18(part)` multipart flow is reusable but is only needed when the selection occurs between battle parts.

## Promotion weapon choice

This is executable/UI logic rather than a chapter `.cmb` dialog.

1. `build_job_data_table` (`0x8001A5E4`) reads the class's nine-character `weapon_ranks` string from `FE8Data.bin` JobData field `+0x14`. It stores decoded rank bytes at runtime `ClassData+0x2C` and retains a pointer to the original string at `ClassData+0x34`.
2. `promote_unit_to_linked_class` (`0x8003D2C4`) follows the source class's `promotes_to` link (`+0x0C`), swaps class skill flags and raises each of the actor's eight numeric weapon-rank bytes (`CombatActor+0x20C..0x213`) to at least the new class default. Existing Ghidra names `current_stat_caps` and `get_stat_cap_with_skill_bonus` for this byte range are misleading: the class source is the rank string, the checks gate sword/lance/axe/bow/staff use, and the numeric thresholds match weapon-rank progression.
3. In state 6, `update_class_change_sequence` (`0x801EE0C8`) checks all **nine** characters of the promoted class string. `check_char_field_less_than_0x2a` (`0x800A8504`) returns true when the character equals ASCII `*` (`0x2A`). If any position is marked, the sequence starts the picker process at `0x8029A780`.
4. The picker uses option labels `MCA_SW`, `MCA_LA`, `MCA_AX`, `MCA_BW`, `MCA_FI`, `MCA_TH`, `MCA_WD`, `MCA_RD`, `MCA_KN` in index order. Its `validate_char_field_and_conditionally_assign` (`0x801F1644`) offers a row only when that class rank character is `*`; `store_pending_action_param8` (`0x801F16D4`) stores the chosen index.
5. `cleanup_combat_actors_and_apply_overrides` (`0x801EDBC0`) grants a permission flag for the choice, then calls `apply_stat_cap_skill_overrides` (`0x80092438`, another misleading name) to initialize a missing rank byte to 1 for sword/lance/axe/bow/staff. The result mapping is:

   | Index | Menu key | Resulting skill/flag ID | Numeric rank byte |
   |---:|---|---:|---|
   | 0 | `MCA_SW` Sword | `0x24` | `+0x20C` |
   | 1 | `MCA_LA` Lance | `0x25` | `+0x20D` |
   | 2 | `MCA_AX` Axe | `0x26` | `+0x20E` |
   | 3 | `MCA_BW` Bow | `0x27` | `+0x20F` |
   | 7 | `MCA_RD` Staff | `0x28` | `+0x213` |
   | 8 | `MCA_KN` Knife | `0x22` | none in the eight-byte rank block |

   Indices 4–6 have labels but **no grant case** in the retail result switch. The Game Code patch **Grant Fire, Thunder, or Wind on promotion** redirects those three results to handlers that start the corresponding numeric rank (`+0x210`, `+0x211`, or `+0x212`) at 1 if it is zero. The patch is available for US, PAL, and JP executables. Its bytes and reset path have been checked against all three retail DOLs; promotion in the running game still needs a live test.

### Reuse in another promotion

In Game Code, enable **Grant Fire, Thunder, or Wind on promotion** when offering any of those three choices. In Game Data → Classes, edit the **promoted target class** rank string. Mark the desired choice positions with `*`; keep its fixed rank letters and other positions as intended. The source class must link to that target through `promotes_to`, and the unit must reach the normal promotion process (level-up or Master Seal). The class editor writes a new string and repoints only the edited class, so a shared old string does not change sibling classes. The offered options are class-wide; each unit stores its own selected rank or permission flag. The app's playthrough and battle previews do not yet model that per-unit choice, so use the game to verify weapon usability. This mechanism has not yet been live-tested on a custom promotion.

`UnitClassChange(unit)` is not a general promotion-choice trigger: its script handler requires `SID_EVENTCC` and has no target or weapon argument. For an arbitrary mid-chapter promotion event, either arrange the normal promotion process or patch the executable to expose a new script operation.
