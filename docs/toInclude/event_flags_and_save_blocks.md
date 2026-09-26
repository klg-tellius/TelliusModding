# Event flags and save blocks

How Path of Radiance's event scripts remember things (`regist`, `global`, `set`, `get`, `clr`), how that state reaches a memory-card save, and how to add new flags. Research reference: `research/SAVE_NOTES.md` §2 and §5; code: `App/fe_modding/formats/event_flags.py`.

## The flag table — Confirmed

One engine table, `event_flag_table` at `0x803307BC` (inside `party_data`, at `+0xB4`), holds every script flag:

| Offset | Size | Content |
|---|---|---|
| `+0x000` | 96 × 4 | Pointer to each slot's name (the string lives in the `.cmb` that registered it) |
| `+0x180` | 96 × 4 | Hash of each name: `h = h × 37 + c` over the Shift-JIS bytes, `c` sign-extended |
| `+0x300` | 12 | The 96 bits; slot `i` is byte `i >> 3`, bit `i & 7` (least significant bit first) |

A lookup compares hash, then string, slot 0 to 95; the first match wins.

| Script call | Engine function | Effect |
|---|---|---|
| `global(name)` | `event_flag_table_register_global` | Name into the lowest empty slot; bit cleared |
| `regist(name)` | `event_flag_table_register_local` | Name into the highest empty slot; bit untouched; ignored when the table is full |
| `set(name)` | `event_flag_table_set` | Bit on (unregistered name: nothing) |
| `clr(name)` | `event_flag_table_clear` | Bit off (unregistered name: nothing) |
| `get(name)` | `event_flag_table_is_set` | Bit value (unregistered or empty name: 0) |

## Lifecycle — Confirmed

1. **Power-on** (`init_event_script_system`): the table is wiped, then the engine registers `gf_canceled`, `gf_gameover`, `gf_complete`, `gf_reserved4`, `gf_reserved3`, `gf_reserved2`, `gf_triA`, `gf_triB` (slots 0–7) and runs `startup.cmb`'s `RegistGlobalFlags`, which registers 22 more (slots 8–29).
2. **Chapter start and mid-chapter resume** (`initialize_chapter_start_state`): the reset walks down from slot 95, clearing names until it meets an empty slot, then clears the bit of every slot without a name. `gf_gameover` and `gf_complete` are cleared, then the chapter's `Startup` runs; it registers the chapter's flags (directly and through `RegistLocationFlags`/`RegistBaseFlags`), always unconditionally, from slot 95 down. On a resume the saved bits are restored afterwards.
3. **Events:** talk, battle and base-conversation triggers skip their event while the flag named by the trigger's label is set, and the event body sets it. Completion-style events run only while their label flag is set.
4. **Trial maps:** `AllPush` saves the whole state, resets the table and party; `AllPop` resets and restores it.

Global bits therefore last the whole playthrough. Local bits last one chapter. RAM dumps of five chapter openings match the predicted slot-to-name map for all 96 slots, and every stored hash matches the formula.

## In the save file — Confirmed

A Path of Radiance `.gci` body (after the 0x40-byte GCI header) holds six 0x4000-byte blocks at `0x2000`–`0x16000` (three files × two copies) and two 0x6000-byte checkpoint blocks at `0x1A000` and `0x20000`. Every block starts with a header: magic `"FE8J"` at `+0x40`, version `0x20050201`, a sequence number (newest wins), the block size and a CRC-32 at `+0x50` over `block[0x70 : size]` (standard `zlib.crc32`). A block with `save_kind` 1 or a stored CRC of `0x12345678` skips the check. The state stream starts at `+0xB8` with the tag `BMST` (the `party_data` serialization), followed by `MDST`, `UNIP`, `SOKO`, `FWEP` and `"T  T"`.

**The flags are the 12 bytes at `BMST + 0xAC` (block `+0x164`)**, in every block type. Names are never saved: loading re-runs the registrations and gives each bit back by slot number.

The 40 sample saves agree: 311 of 320 blocks pass the CRC and the other 9 are all `save_kind` 1; the global bits follow the story (Volke's recruitment flag first appears in `chapter11.gci`, the Black Knight's defeat only in `chapter28.gci`); local bits decode to the chapter's own names (chests, boss conversations, reinforcements). A block's chapter flags belong to the script with its map's number (`bmap18` -> `C18.cmb`): 946 of the 991 set chapter bits fall on named slots, and the rest sit in saves made between chapters, which can still hold the previous chapter's flags.

## Vanilla global flags

| Slot | Name | Meaning |
|---|---|---|
| 0–7 | `gf_canceled` … `gf_triB` | Engine flags: cancel, game over, map complete, three reserved, and `gf_triA`/`gf_triB`, which make each triangle-attack message show only once |
| 8 | `G_シノン死亡` | Shinon died |
| 9 | `G_ガトリー死亡` | Gatrie died |
| 10 | `G_マーシャ死亡` | Marcia died |
| 11 | `G_レテ死亡` | Lethe died |
| 12 | `G_モウディ死亡` | Mordecai died |
| 13 | `G_リュシオン死亡` | Reyson died |
| 14 | `G_ＭＡＰ１２で漆黒とアイク戦闘` | Ike fought the Black Knight on map 12 |
| 15 | `G_ヤナフ死亡` | Janaff died |
| 16 | `G_ウルキ死亡` | Ulki died |
| 17 | `G_情報３兄弟` | Info conversation "three brothers" |
| 18, 19, 22 | `G_リザーブド` | Reserved, unused (only slot 18 is reachable by name) |
| 20 | `G_Map20の情報会話３` | Map 20 info conversation 3 |
| 21 | `G_ティバーン死亡` | Tibarn died |
| 23 | `G_Ｍａｐ４マーシャ会話` | Map 4 Marcia conversation |
| 24 | `G_フォルカ仲間` | Volke recruited |
| 25 | `G_Map31ネサラ使用` | Naesala used on map 31 |
| 26 | `G_ジル仲間条件` | Jill's recruitment condition met |
| 27 | `G_漆黒の騎士倒した` | Black Knight defeated |
| 28 | `G_クリミア忠臣イベント` | Crimean retainers event |
| 29 | `DBG_最初からやってる` | Debug marker "played from the start" (set in every sample) |

## Adding flags

- **Chapter flag:** `regist("name")` at the end of the chapter's `Startup`, then `set`/`get`/`clr`. Appending keeps older saves' slots meaning the same thing. Keep global + local registrations ≤ 95: the reset needs one empty slot to stop at, and a full table would also unregister every global flag. The most any vanilla chapter registers is 58 (C18, which registers two names twice), leaving 7 slots.
- **Campaign flag:** append `global("name")` to `RegistGlobalFlags` in `startup.cmb` (the decompiler writes it `extern("global", "name")`), or rename one of the unused `G_リザーブド` entries. Never register a global from a chapter script: its name would point into a script that is unloaded, and its slot would depend on play order. Each new global costs every chapter one local slot. Slots 30–31 are clear in every sample save; higher slots can pick up stale local bits from older saves.
- **Tooling:** the compiler warns on `set`/`get`/`clr` of unregistered names, `global` outside `RegistGlobalFlags`, duplicate registrations and a full table (the script editor uses the project's own `startup.cmb`). `python -m fe_modding.formats.event_flags save.gci --scripts <Scripts dir>` lists a save's flags by name; `--set`/`--clr` edit them and recompute the CRC.

## Open

- The meaning of each `save_kind`/`save_mode` value.
- Script global variables are a separate, unsaved mechanism: see `script_global_variables.md`.
