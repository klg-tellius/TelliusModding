---
id: "engine-resource-loading"
title: "Engine Boot & Resource Loading"
description: "How Path of Radiance moves from the GameCube executable and disc filesystem to named runtime data"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Engine", "Structure", "Resources"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/engine-resource-loading.md"
system_entries: ["FE9-SYS-001", "FE9-SYS-002", "FE9-SYS-003", "FE9-SYS-004", "FE9-SYS-005", "FE9-SYS-006", "FE9-SYS-007", "FE9-SYS-008", "FE9-SYS-015", "FE9-SYS-023"]
system_reviewed: ["FE9-SYS-001", "FE9-SYS-002", "FE9-SYS-003", "FE9-SYS-004", "FE9-SYS-005", "FE9-SYS-006", "FE9-SYS-007", "FE9-SYS-008", "FE9-SYS-015", "FE9-SYS-023"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# Engine Boot & Resource Loading

Before a chapter, character, or weapon can exist, Path of Radiance must turn bytes on the disc into named runtime objects. The useful mental model is a library opening for the day: the console opens the building, the executable installs the librarians and catalog rules, common archives place frequently used books on the desk, and later scenes request material by name. A file being present on the disc does not guarantee that it is the copy the game uses.

This pipeline has four distinct owners. The GameCube boot environment locates and starts the executable. Native code in `main.dol` asks for resources. Transport layers such as LZ10 and pack archives deliver bytes without interpreting game rules. Finally, format-specific loaders relocate pointers, register names, and construct definitions or mutable objects. Keeping those owners separate is the key to diagnosing a mod that parses correctly in a tool but fails in play.

## From power-on to native code

<span id="fe9-sys-001"></span> **FE9-SYS-001 — GameCube boot and apploader.** The GameCube boot process reads the disc metadata and apploader, then loads the game's DOL executable. FE9-specific systems do not yet exist at this point: the platform is establishing memory and handing control to the entry point. For modding, this boundary explains why files under `files/` cannot change the earliest executable setup and why native patches target `main.dol` rather than a chapter archive.

In order, `boot.bin` identifies the title and locates the FST and executable, `bi2.bin` contributes boot configuration, the apploader copies the executable sections, and control passes to the DOL entry point. The extracted `sys/` and `files/` folders are a tool convention rather than directories stored that way on disc. [GameCube Disc & FST](../formats/iso-fst.md) documents this boundary.

<span id="fe9-sys-002"></span> **FE9-SYS-002 — DOL section and address mapping.** A DOL header describes multiple code and initialized-data sections using file offsets, runtime addresses, and sizes. The loader copies those sections into memory and clears the BSS range for zero-initialized globals. A function address therefore names a position in one regional executable, not a portable file offset. PAL and US functions must be matched by instructions, callers, and data relationships rather than by assuming one constant address shift.

Three addresses must not be confused: a section's offset in the DOL file, its runtime address after loading, and an address relative to the start of the disc image. A patcher converts through the DOL section table; it cannot write to a runtime address as though that number were a file offset. [main.dol](../formats/main-dol.md) gives the layout and explains the repository's region-matching method.

## Finding and unwrapping a resource

<span id="fe9-sys-003"></span> **FE9-SYS-003 — Disc filesystem and path lookup.** The GameCube filesystem table maps paths to byte ranges on disc. FE9 organizes loose resources below `files/`: chapter messages in `Mess/`, scripts in `Scripts/`, maps below `zmap/`, audio below `Sound/`, movies below `Movie/`, and shared databases at the root. The filesystem supplies identity and bytes; it does not understand that `c01.m` is dialogue or that `map.cmp` contains terrain.

The caller supplies or constructs a path, the FST resolves that path to an offset and length, and the drive returns exactly those bytes. Content detection happens later. Consequently, changing a filename, its case, or a fixed directory prefix can break the request before a decompressor or semantic parser ever sees the resource.

<span id="fe9-sys-004"></span> **FE9-SYS-004 — Archive-first resource lookup.** Loaded archives participate in named lookup before the engine falls back to loose disc paths. `system.cmp` contains copies of `FE8Data.bin`, `FE8Anim.bin`, `FE8Effect.bin`, common messages, and other shared resources, and the archived copies are the effective boot-time inputs. Editing only the loose duplicate can therefore produce a perfectly valid file that appears to do nothing. A troubleshooting pass should always identify every mounted copy and the lookup order before blaming the parser.

This precedence is confirmed by the executable trace and by resources such as `FE8Data.bin` and `window/icon.tpl`, whose effective copies are inside `system.cmp`. It is not a universal statement that every same-named file is shadowed forever: only archives currently registered with the lookup system can win. Scene-specific archives enter and leave that set as their owners load and unload them.

<span id="fe9-sys-005"></span> **FE9-SYS-005 — Compression and decompression.** Compression is an outer transport layer. Many `.cmp` resources begin as Nintendo LZ10 streams; decompression produces either one payload or a `pack` archive. The decompressor owns lengths and back-references but has no knowledge of maps, models, or units. Rebuilding must proceed inside-out: serialize the semantic child, rebuild its container, then apply outer compression.

An LZ10 stream declares its uncompressed size. Literal tokens append bytes and back-references copy already produced bytes, including overlapping copies. Reaching the declared length ends decompression; it does not prove what the output means. A `pack` magic identifies one possible next layer, while portraits can expand directly to texture data. [LZ10](../formats/lz10.md) documents the token rules and the overlapping-copy pitfall.

<span id="fe9-sys-006"></span> **FE9-SYS-006 — Pack/archive mounting.** A pack archive groups named children using filename, offset, and length records, with payloads aligned to 32-byte boundaries. Chapter deployment packs, map packs, and model packs use the same grouping mechanism for unrelated child formats. Mounting exposes those children to resource lookup; it does not parse their contents.

The directory's recorded length excludes alignment padding. An extractor should verify the `pack` magic, bounds-check every offset and length, and return the child bytes under the recorded name. A builder must recalculate directory locations after any child changes size and align each payload start again. [Pack Archive](../formats/pack-archive.md) shows the real `dispos.cmp` nesting.

<span id="fe9-sys-007"></span> **FE9-SYS-007 — Labeled-section data loading.** Many semantic children share a different container: a header followed by records, a NUL-terminated label pool, relocation positions, and named section entries. On disc, pointer fields are offsets into the label pool. The loader relocates them into usable runtime references. Shop, deployment, AI, map, and core database data can therefore share container rules while having completely different records.

Relocation is an in-memory transition, not a reason to write RAM pointers back to disc. Each relocation entry identifies a field whose stored offset must have the loaded data base added to it. The section table then publishes named record regions. Adding a string or moving a record can shift the label pool and both trailing tables, so a safe writer regenerates pointers, relocation positions, sections, and total sizes together. The exact header and the engine's `HSDArc` stamp are in [Labeled Section Format](../formats/labeled-section.md).

## Names become runtime relationships

<span id="fe9-sys-008"></span> **FE9-SYS-008 — Runtime resource registry.** Once common resources are loaded, registries connect stable labels to runtime objects. Prefixes describe namespaces rather than types in the programming-language sense: `PID_` identifies a character definition, `JID_` a class, `IID_` an item, `SID_` a skill, `MID_` a message, and `EID_` an effect. Other resources use names such as `BGM_*` or chapter/map identifiers. Lookup can use hashed buckets internally, but the readable label is the relationship a modder should preserve.

Registration and resolution are separate moments. A loader first publishes a label and its object; a later consumer asks for that label. A structurally valid deployment can therefore fail semantically when it refers to a definition that was never loaded, was registered under a misspelled name, or was shadowed by another mounted resource. The executable's named-resource implementation uses a two-hash bucket table, but consumers should treat the complete label—not a bucket position—as identity.

<span id="fe9-sys-015"></span> **FE9-SYS-015 — Core database loading.** The boot-loaded core database supplies reusable definitions for characters, classes, items, skills, terrain, supports, chapters, groups, and difficulty constants. Loading creates definitions, not a playthrough: it knows what an Iron Sword is but not who currently owns one or how many uses remain. Runtime-unit and inventory-instance construction happen later from chapter or save state.

`FE8Data.bin` is itself a labeled-section resource. Its named tables include `PersonData`, `JobData`, `ItemData`, `SkillData`, `TerrainData`, `ChapterData`, `GroupData`, and support and difficulty sections. The loader relocates their label references and exposes reusable definitions to downstream systems. [FE8Data.bin](../formats/fe8data.md) documents the tables and distinguishes definitions from save data.

<span id="fe9-sys-023"></span> **FE9-SYS-023 — Identifier and label resolution.** Cross-file references succeed only when producer and consumer agree on a label. A deployment can name `PID_IKE`; the database resolves that name to a character definition, which names a class, portrait, skills, and animation identity. Renaming a label without updating every consumer produces a missing relationship even if every individual file remains structurally valid. Reordering indexed tables is a separate hazard because saves serialize several definitions by table position rather than label.

Labels and indices therefore form two identity regimes. Live file-to-file relationships usually use readable labels; serialized units store character, class, and item identities as one-based positions in the corresponding core tables. A label-preserving reorder can keep new chapter loads working while silently changing what an existing save reconstructs. Table order is part of save compatibility.

## Inputs, owned state, and outputs

| Stage | Inputs | State it owns | Output or consumer |
|---|---|---|---|
| Boot and apploader | Disc header, `boot.bin`, `bi2.bin`, apploader, DOL header | Initial memory map and loaded executable sections | DOL entry point |
| Disc lookup | FST and requested path | Path-to-offset/length mapping | Raw resource bytes |
| Archive lookup | Registered archives and requested child name | Mounted archive set and name directory | Child bytes, or a loose-file fallback |
| Transport decode | LZ10 stream or `pack` directory | Temporary decoded buffers and child boundaries | A semantic child resource |
| Relocatable loader | Header, label pool, relocation and section tables | Relocated references and named sections | Registered tables or resources |
| Core database | `FE8Data.bin` definitions | Character/class/item/skill and related definition registries | Unit construction, combat, UI, scripts, and saves |
| Label resolver | A namespace label and loaded registries | Name-to-object relationship | The definition or asset requested by a consumer |

The exact allocation owner and lifetime vary by resource. Boot databases are shared broadly; chapter maps and deployment data are chapter-scoped; effects and UI assets may be scene-scoped. Those lifetime rules are taught by [Runtime Engine Architecture](runtime-engine-architecture.md). This page owns the path from persistent bytes to a registered resource.

## Rules and lifecycle

For a typical resource request, the engine follows this conceptual order:

1. Native code constructs a path or symbolic resource name.
2. The lookup layer checks applicable registered archives, then falls back to the disc filesystem when the request allows it.
3. The FST or archive directory returns a bounded byte range.
4. A wrapper-specific loader removes LZ10 if present and opens a pack when the decompressed magic and expected path require one.
5. The semantic loader validates its own header, relocates pointer fields, and finds named sections or exports.
6. Definitions or assets are registered under labels.
7. Later systems resolve those labels and combine immutable definitions with chapter or save state.
8. The owning scene or service releases temporary buffers and unregisters scene-scoped resources; shared boot data remains available.

This is a model of responsibility rather than one universal function call. A loose message file skips the pack step; a compressed portrait does not become a labeled-section resource; a native table embedded in the DOL skips disc resource lookup entirely.

## Worked example: loading a chapter enemy

When a chapter requests its deployment, the engine locates `zmap/bmapNN/dispos.cmp`, removes LZ10, opens the pack, selects the difficulty child such as `dispos_n.bin`, and parses its labeled sections. A unit record names a `PID_`, `JID_`, inventory `IID_` values, AI sequences, and group. Those names resolve against already loaded registries. The resulting runtime unit receives mutable HP, position, inventory uses, allegiance, and AI state. Graphics and messages are resolved later from their own registries when the map or UI needs them.

Suppose a mod changes an enemy's first item from `IID_IRONSWORD` to a new `IID_TESTSWORD`. The edit works only if the child deployment is rebuilt with a valid label pointer and relocation entry, the pack directory reflects the child's new size, the outer LZ10 stream is regenerated, and the effective boot database—normally the copy in `system.cmp`—registers `IID_TESTSWORD`. Missing any one layer produces a different symptom: parse failure, a missing pack child, a stale deployment, or an unresolved item.

## Interactions, failures, and safe edits

- A valid inner file can be hidden by an older copy in a mounted archive.
- A correct payload can fail because outer compressed size, pack offsets, alignment, relocation entries, or section names were not rebuilt.
- A missing or misspelled label can leave a consumer without a definition even though both files are structurally valid.
- A label can resolve correctly in a new game while an existing save reconstructs the wrong definition after a core table was reordered.
- Executable addresses are region-specific; names and behavior are more durable documentation than bare addresses.
- Decompressed output must be identified by its magic or expected path; not every LZ10 stream contains a pack.
- Empty archives, out-of-bounds child spans, invalid relocation positions, and duplicate labels should be rejected by tools instead of trusted as runtime behavior.
- Boot resources affect every chapter, so structural edits need new-game and existing-save tests.

A safe verification sequence is: parse the rebuilt inner child; unpack the rebuilt pack and compare every child; decompress the rebuilt `.cmp`; confirm the intended archive copy contains it; validate cross-file labels; then test one new game and one pre-existing save. The repository implements these layers separately in `App/fe_modding/formats/lz10.py`, `pak.py`, and the format-specific readers, while `App/fe_modding/project.py` and `App/fe_modding/patch.py` synchronize effective archive copies during a build.

## Evidence and implementation trail

- [GameCube Disc & FST](../formats/iso-fst.md) supplies the boot sequence and path-to-disc-span model for FE9-SYS-001 and FE9-SYS-003.
- [main.dol](../formats/main-dol.md) supplies DOL mapping, region-address cautions, and the executable resource-table trail for FE9-SYS-002 and FE9-SYS-008.
- [LZ10](../formats/lz10.md), [Pack Archive](../formats/pack-archive.md), and [Labeled Section Format](../formats/labeled-section.md) give reproducible layouts for FE9-SYS-005 through FE9-SYS-007; their corresponding application readers and tests exercise extraction and rebuilding.
- [FE8Data.bin](../formats/fe8data.md) inventories the boot database sections behind FE9-SYS-015 and documents both archive precedence and index-based save identity behind FE9-SYS-004 and FE9-SYS-023.
- [Save Format](../formats/save-format.md) confirms that saved character, class, and item identities use table positions, which is why a structurally valid reorder is not save-compatible.

The container layouts, relocation rule, FST mapping, DOL section mapping, effective `system.cmp` copies, and table-index save relationships are treated as confirmed because repository parsers, executable traces, or in-game tests reproduce them. The generalized lifecycle above is a synthesis across those confirmed paths. It deliberately does not claim that every resource takes every step or that all registered resources share one unload policy.

## Known gaps

No known gap prevents using or reproducing the systems reviewed on this page. Exact heap selection, reference ownership, and scene-by-scene unloading are intentionally outside this article's boundary and belong to [Runtime Engine Architecture](runtime-engine-architecture.md). Individual payload fields belong to their format and gameplay-system articles; successful container loading alone is not evidence that those fields are understood.

