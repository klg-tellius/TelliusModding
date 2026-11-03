# Radiant Dawn undecoded inventory

This is the canonical queue for RFEE01 decoding work. It tracks unknown data and behavior that can
affect editing or simulation; historical phase plans are not status documents. An item leaves this
file only after its meaning is documented, the implementation is updated, and the relevant tests
pass. Last reconciled: 2026-10-31.

## Status vocabulary

- **undecoded-bytes**: bytes are preserved, but their structure or boundaries are not fully known.
- **semantic-unknown**: structure and type are known, but the field's meaning is not established.
- **runtime-unknown**: on-disc data is understood, but executable behavior/order/state ownership is incomplete.
- **verification-gap**: an implementation exists but lacks a recorded corpus or Dolphin check.
- **inferred**: corpus correlation exists without a confirmed runtime reader.

Priority is based on corruption/editing risk first, then user-visible coverage.

## P0 — save integrity and framing

| ID | Status | Owner | Open evidence | Closure route | Exit test |
|---|---|---|---|---|---|
| SAVE-02 | verification-gap | `save_file_fe10.py`, Saves UI | The virtual payloads are confirmed as 16, 16, and 48 bytes; BMST flags are now structurally located at `+0x102` and editable by slot | Parse the complete tail and exercise edited flags in Dolphin | Located following state plus a recorded flag-on/flag-off load and re-save check |
| SAVE-03 | verification-gap | `save_file_fe10.py`, Saves UI | The eight saved bytes are now typed as signed Might/Hit/Critical/Weight-reduction steps plus RGBA; existing forged convoy entries are editable, including variable-length names | Load an edited copy in Dolphin and re-save it | Edited forged item retains name, stats and colour after load/re-save |
| SAVE-04 | semantic-unknown | `SAVE_NOTES.md` | `KZND` and `RELD` counted records plus the fixed `T  T`/`DEBU` framing now have tested codecs; FGPT's three words, the `T  T` fields, and RELD's value byte remain unnamed | Trace direct consumers of the structurally isolated fields | Semantic names or explicit reserved/unused findings plus mutation tests |
| SAVE-05 | verification-gap | `save_file_fe10.py`, Saves UI | chapter/phase/turn, convoy edits, and `move_to_chapter` write successfully but have incomplete recorded game checks | Exercise copied saves in Dolphin across early, split-army, and Endgame records | Recorded load, inventory, resume, and re-save checks with valid CRCs |

### 2026-10-30 save milestone

- Corrected the physical layout from rotating copies to six independent files plus six checkpoints.
- Confirmed variable forged-item framing: NUL-terminated name (24-byte limit) plus eight opaque bytes.
- Traced the shared unit vtable: each of the four virtual members writes 12 data bytes.
- Traced BMST vtables: the first two write 16 data bytes each and the final member writes 48.
- Added a guarded 128-bit BMST flag codec and a slot editor under Tools › Saves.
- Added a counted KZND runtime-bond codec with fixed-size in-place editing.
- Added codecs for `T  T`'s fixed 0x608-byte layout and RELD's counted five-byte records; the
  remaining work on those sections is semantic rather than boundary decoding.
- Closed SAVE-01: ITBL's eight counted tables and all 254 UNIP slots now parse structurally,
  including variable skills/items, forged names and the RelianceData-dependent support tail. Every
  active record in the real-save corpus rebuilds byte-for-byte and lands exactly on `SOKO` without
  scanning unit contents for tags.
- Decoded SAVE-03's payload from the typed `ForgeRecord` getters/setters: four signed step counts
  (Might, Hit, Critical, Weight reduction) and RGBA. Existing forged convoy entries can now be edited
  safely in the Saves UI; only the Dolphin persistence check remains.
- Synthetic tests and the available `G:\ROM` real-save corpus pass byte-identical round trips; a
  mutated-save Dolphin check is still required before SAVE-02/SAVE-05 close.

## P1 — map edit safety

| ID | Status | Owner | Open evidence | Closure route | Exit test |
|---|---|---|---|---|---|
| MAP-01 | semantic-unknown | `map_file.py`, `MAP_NOTES.md` | All three sections now have lossless typed readers/writers: fixed 32-byte light, fixed 12-byte fog, and shader's 16-byte header plus counted four-byte entries; several field roles remain neutral | Trace the RFEE01 map loader and renderer consumers | Semantic names plus controlled Dolphin scenes for lighting, fog and shader entries |
| MAP-02 | verification-gap | `map_file.py`, `MAP_NOTES.md` | Runtime tracing resolved +0x1C..1F as map-wrap enable/X/Y step/duration, +0x20 as an affinity-name pointer (`invalid` on every v4 retail map), and +0x24 as a terrain-height ceiling; typed parser fields and corpus validation are complete | Run controlled wrap, ceiling and affinity mutations in Dolphin | Controlled scenes confirm the traced semantics; semantic/runtime tracing is complete |
| MAP-03 | verification-gap | `map_file.py`, `MAP_NOTES.md` | The typed runtime reader proves +0x00 bit 0 is X mirroring, +0x04/+0x05 are signed 1/64-tile offsets, and +0x10 is loader-skipped reserved data; parser accessors, patch fields and transform math are implemented | Exercise mirror/sub-offset edits in Dolphin | Controlled mutation scenes match the app transform; semantic/runtime tracing is complete |
| MAP-04 | verification-gap | `map_file.py`, `map_props.py`, `MAP_NOTES.md` | Every flag is classified: 20 retail-active bits have exact constructor/update consumers, three non-retail bits have dormant executable paths, and nine bits are ignored/legacy; hidden bits remain preserved | Run targeted mutation scenes for animation, render-priority, bounds, house, marker, roof and door controls | Recorded Dolphin scenes match the 20 traced controls |

### 2026-10-30 map milestone

- Reconciled the implementation with the research: the checked-in parser previously recognized only
  Path of Radiance names and sizes despite the status note claiming RFEE01 support.
- Added automatic prefixed-section handling, versioned `mapdata`, 36-byte `mapdesc`, 20-byte
  `mapinst`, RFEE01 roof/base aliases and u32 sparse-link counts.
- Parsed all 128 extracted RFEE01 maps with declared counts and terrain dimensions.
- Made existing placement edits patch-in-place so RD-only lead/sub-tile/trailing bytes survive.
- Added native-size object/instance growth tests and retained the full FE9 format suite.
- Structurally closed MAP-01's byte boundaries: every retail light and fog record is 32/12 bytes,
  and every shader is exactly a 16-byte header plus four bytes per byte-zero entry count. Typed
  readers/writers reproduce all three sections byte-for-byte across all 128 maps; remaining work is
  assigning renderer semantics and checking mutations in Dolphin.
- Traced the RFEE01 mapdata and placement constructors. Added semantic affinity/terrain-ceiling
  fields, decoded fractional placement and mirror behavior, classified the trailing placement word
  as reader-skipped reserved data, and applied verified map structures/function names to Ghidra.
- Traced RFEE01 mapdesc flag packing and its terrain/animation accessors. The editor now offers
  20 directly traced, retail-active RD bits and preserves every unexposed bit, instead of presenting PoR's
  visibility/objective labels. Corpus analysis also disproved PoR's A6+A7 terrain identity for RD;
  Ghidra now carries the 36-byte descriptor type and named flag consumers. Dolphin was intentionally
  skipped, so MAP-04 remains a verification gap rather than closed.
- Resolved B7 independently: it selects a random starting entry from animation track `0x37` before
  the normal C2 update. All 79 retail carriers also have C1+C2 and are ambient animated actors or
  effects. C6 only removes the final entry from that random set; its other 3,199 placements never
  enter a C6 test and are inert legacy tags.
- Resolved B6 from the same runtime loop: it delays the next animation reseed by an animation-length
  countdown and, when paired with B7, randomizes two orientation inputs before rebuilding the model
  transform. Its sole retail carrier is `bmap0309/boco01`, with 16 zero-angle placements.
- Completed the full constructor/update matrix. A0/A3-A6, B0-B2, C5/C6 and effect E5/E7 now have
  exact runtime roles. A1/A2/E6 have dormant executable consumers but no retail carriers; A7,
  B3-B5, C0, C7, E0, E2 and E3 have no effective RFEE01 reader and remain preserved.

## P2 — FE10Data semantics

| ID | Status | Owner | Open evidence | Closure route | Exit test |
|---|---|---|---|---|---|
| DATA-01 | semantic-unknown | `fe10data.py`, `FE10DATA_NOTES.md` | Loader tracing named the extra skill, biorhythm selector/increment and withdrawal mask, and proved `+0x01/+27` reserved; only tail `+18` / runtime `PersonData +0x20` remains unknown | Trace consumers of runtime `PersonData +0x20` | Name the last byte or prove it reserved/unused |
| DATA-03 | semantic-unknown | same | `ItemData +12` is the signed English-article selector, `+13..+15` are skipped zero padding, and `+16` is the nine-colour palette index; optional-flags bit 1 adds an eight-byte block absent from all retail records whose runtime fields `+0x2D..+0x34` remain unnamed | Trace producers or readers of the second optional block | Name the eight bytes or prove the block is unused exporter residue |

### 2026-10-30 JobData milestone

- Closed DATA-02 from executable readers: `+0` is base weight; `+1/+2` and `+3/+4` are
  kind/signed-value weight modifiers; `+7` is the promotion threshold; `+8` is the TerrainData
  movement-cost column; `+0x0B` is base vision; and `+0x0C..+0x0F` is a skipped zero word.
- Corrected the tactical-data adapter, which had hard-coded RD movement type to zero and read the
  old mislabeled `weight` byte instead of base weight.
- Applied `/FE10_RE/JobDataRuntime` and loader/reader comments in Ghidra; the read-only verifier
  reports zero failures.

### 2026-10-30 ItemData milestone

- Named the article selector and display-colour index from `get_item_article` and `get_item_colour`;
  classified the intervening three zero bytes as loader-skipped padding.
- Corrected the final byte from a block count to flags: bit 0 adds ten stat bytes and bit 1 adds a
  separate eight-byte block, followed by record alignment. The codec now preserves the second block
  when adding or removing stat bonuses instead of multiplying a supposed count by twelve.

### 2026-10-30 SkillData milestone

- Closed DATA-04: `get_skill_article` identifies `+0x1D` as the signed English article selector,
  with the same -1/0/1/2/3 convention as items. `+0x22/+0x23` are zero alignment bytes between the
  two one-byte list counts and the aligned list pointers; all 142 retail records are zero.

### 2026-10-30 ChapterData milestone

- Closed DATA-05. `get_chapter_enemy_level_bonus` selects `+0x85/+0x86/+0x87/+0x88` for the save
  difficulty byte Easy/Normal/Hard/Maniac respectively, so the last unknown setting is the Maniac
  enemy-level bonus. The editor now exposes all four values rather than only `+0x88` as unknown.

## P3 — gameplay parity

The detailed breadth dashboard remains `GAMEPLAY_SYSTEMS_INVENTORY.md`; the rows below are the
execution order, not a duplicate function catalogue.

| ID | Status | Scope | Required closure |
|---|---|---|---|
| GAME-01 | runtime-unknown | combat-unit construction, authority, triangle/rank/ledge order and clamping | Typed call chain plus isolated combat comparisons |
| GAME-02 | runtime-unknown | strike queue: Vantage, brave, Adept, mastery, doubling | Typed queue writers/consumer and controlled ordering cases |
| GAME-03 | runtime-unknown | RNG initialization, save/load ownership, forced-outcome consumption | Reproduce sequences across boot, save, load, and combat branches |
| GAME-04 | runtime-unknown | random/BEXP growth assembly, caps, Blossom, fallback and tie-breaking | Equal-growth and cap-boundary test matrix |
| GAME-05 | runtime-unknown | Laguz transition gates and save ownership | Battle/turn/rescue/status/death/save transition matrix |
| GAME-06 | runtime-unknown | status, fog/sight/torch, objectives, action lifecycle | Native traces plus map-level Dolphin scenarios |
| GAME-07 | runtime-unknown | forge, gold/warehouses, army split/rejoin, BEXP, battle records | Trace ownership and transfer at every part boundary |
| GAME-08 | runtime-unknown | recruitment, defeat, endings, clear data and New Game initialization | Story-state/save comparisons across representative endings |

## P4 — regional text and scripts

| ID | Status | Owner | Open evidence | Closure route | Exit test |
|---|---|---|---|---|---|
| TEXT-01 | undecoded-bytes | `fe10_message.py`, `TEXT_NOTES.md` | EU `d_`, `f_`, `s_`, and `i_` messages use custom single-byte text tables | Recover runtime tables and select codec by language prefix | Every byte round-trips and accented text renders correctly in Dolphin |
| TEXT-02 | semantic-unknown | `TEXT_NOTES.md` | command `01 '='`, one glyph-path command, talk-window art composition | Trace command dispatch and window resource construction | Named commands/layers or explicit inert classification |
| SCRIPT-01 | verification-gap | `SCRIPT_NOTES.md` | PAL/JP native tables and region-specific scripts are not checked | Diff native tables and rerun compiler/corpus suites per region | Region-specific byte-identical script round trips and native catalogues |

## P5 — graphics and registry residue

| ID | Status | Owner | Open evidence | Closure route | Exit test |
|---|---|---|---|---|---|
| GFX-01 | undecoded-bytes | `3D_PIPELINE_STATUS.md`, particle codec | 581 emitter `+0x0C` controls, 1,162 bytes total | Runtime watchpoint or confirmed producer evidence | Named field or demonstrated unused/exporter-residue classification |
| GFX-02 | inferred | `gs_file.py`, model pipeline | texture descriptor `+6` and texture flags `0x2/0x4` correlate imperfectly with wrap modes | Trace authoring input or every material consumer | Semantic classification without relying on corpus correlation alone |
| GFX-03 | semantic-unknown | `skeleton.py` | skeleton flags `0x2/0x4` and seed-matrix behavior | Trace bone matrix builder and nonzero samples | Named flags/matrices with animation regression tests |
| GFX-04 | semantic-unknown | `fe10_anim.py`, `fe10_battle.py` | many records are structurally relocatable but retain opaque metadata | Trace table-specific runtime consumers, starting with editable/high-variance fields | Per-field schemas instead of broad raw-record editing |
| GFX-05 | semantic-unknown | `fe10_faces.py`, `soundroom.py` | portrait halfwords and FE10 Sound Room's extra word are preserved | Trace their direct consumers | Named fields or proven reserved values |

## Completion rules

Closing an item requires all applicable evidence:

1. Runtime reader/writer or producer evidence, not a name inferred only from value correlation.
2. Ghidra names, types, and comments applied with a read-only verifier.
3. Format/research documentation updated.
4. Synthetic boundary tests and byte-identical corpus round trips.
5. A copied-save/disc Dolphin check when behavior or persistence changes.
6. Removal of the corresponding `unknown_*` label, or a documented reserved/unused classification.


