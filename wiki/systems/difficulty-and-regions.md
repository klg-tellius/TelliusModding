---
id: "difficulty-and-regions"
title: "Difficulty Modes & Regional Builds"
description: "How difficulty profiles and Japanese, US, and PAL revisions replace data, constants, content, and native behavior"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Difficulty", "Regions", "Compatibility"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/difficulty-and-regions.md"
system_entries: ["FE9-SYS-013", "FE9-SYS-025", "FE9-SYS-381"]
system_reviewed: ["FE9-SYS-013", "FE9-SYS-025", "FE9-SYS-381"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Difficulty Modes & Regional Builds

“Difficulty” and “region” are selectors that can change several independent layers. They are not single multipliers. A deployment may change while a formula stays constant; a localized message may change while the record layout stays identical; native executable code may differ even when two files share a name.

A useful mental model is a stack of transparent sheets. The common game design is the bottom sheet. A regional build places its own executable, text, fonts, and selected rule changes over it. The chosen difficulty then selects rows and resources inside that build. Finally, a chapter script can add a local exception. When two releases behave differently, compare the sheets one at a time instead of assuming that “region” or “difficulty” is a single switch.

For a modder, the practical consequence is that compatibility has to be claimed narrowly. A valid US executable address is not a PAL address. A deployment that works on Normal says nothing about the Hard group. A text edit that fits the English font may overflow a German window. Identify the build, selected mode, resource variant, and consumer before deciding that an edit is portable.

## Difficulty profile

<span id="fe9-sys-025"></span> `current_difficulty_id` uses the verified internal mapping `0 Normal, 1 Hard, 2 Maniac, 3 Easy` in the US and PAL executable correspondence. The byte survives party reinitialization and is serialized. Chapter packs commonly contain common plus Normal, Hard, and Maniac deployment groups; shop selection maps Normal/Easy to `shopitem_n.bin`, Hard to `_h`, Maniac to `_m`, with invalid values falling back to Normal. The loader selects authored content rather than scaling one universal enemy list.

`GameData` supplies four columns indexed by the same byte for battle EXP mode/level constants, boss and thief bonuses, a promoted-level adjustment, transformed-Laguz growth, and a class critical bonus. Native formulas read the selected column. Mode behavior is therefore the combination of authored content and selected constants, not “enemy stats × difficulty.”

The retail three-build audit resolves the table rather than assuming one region's layout applies everywhere. US and PAL have the same seven 4-byte rows and values; Japanese `GameData` ends after five rows, immediately before `TerrainData`:

| Row | Japan N/H/M/E-slot | US and PAL N/H/M/E |
|---|---|---|
| Battle-EXP mode bonus | 20 / 15 / 10 / 20 | 20 / 15 / 30 / 30 |
| Battle-EXP level constant | 20 / 20 / 0 / 0 | 20 / 20 / 30 / 30 |
| Promoted-level bonus base | 0 / 30 / 25 / 20 | 0 / 0 / 0 / 0 |
| Boss EXP bonus | 20 / 20 / 20 / 10 | 30 / 25 / 40 / 40 |
| Thief EXP bonus | 13 / 16 / 0 / 0 | 20 / 20 / 30 / 30 |
| Transformed-Laguz growth | absent | 10 / 13 / 10 / 10 |
| Class critical bonus | absent | 15 / 15 / 15 / 15 |

“E-slot” names the physical fourth byte; it does not claim that the Japanese retail menu exposes Easy. The missing Japanese rows agree with its executable: its forecast stops without the later class-critical consumer, and it has no row to supply the later transformed-Laguz growth addition. A regional editor must therefore discover the exported section boundary, not blindly assume seven rows. The repository reader/writer now does so and refuses writes to rows absent from that build.

The US manual exposes Easy, Normal, and Hard. The Japanese release has Normal, Hard, and Maniac instead of US Easy. A mod editor should name both the logical mode and the physical data column/file it changes, because an internal Maniac slot can be repurposed by localization.

## Region and revision handling

<span id="fe9-sys-013"></span> A regional build includes its own `main.dol`, disc identifier, localized messages, fonts/glyph coverage, and possibly altered data or rules. US executable addresses such as `0x801F19A0` are not portable identities. PAL code has growing address drift due in part to extra language support; matching instructions and call graphs is safer than adding a fixed offset.

The engine retains a six-language name table and a console-derived language byte in system save data. The shipped US script-facing `GetLanguage` handler and its options/status label are nevertheless fixed to English; PAL owns the multilingual resource-selection path. Regional text can change encoded byte tables, line wrapping, UI width requirements, and file suffixes without changing the gameplay system described by the message.

One confirmed native mechanical difference is the class critical bonus: the Japanese release does not apply the class-level +15 path used by later regional releases. This illustrates why copying a data file between regions cannot guarantee mechanical parity.

### Three-build consumer matrix

The executable matcher provides high-confidence US→PAL and US→Japanese correspondences for the shared fixed-growth level-up, deployment-record reader, chapter difficulty-field accessor, party/unit/camera/forge serializers and deserializers, and CRC32 routine. This establishes common contracts without assuming common addresses. The regional differences then sit in the selected data or in explicitly different native consumers.

| Subsystem | Shared contract across builds | Regional/difficulty layer | Proven consequence |
|---|---|---|---|
| Difficulty identity | Four-value byte and chapter-field indexing exist in all three executables | Retail menus expose different subsets; out-of-range accessors fall back to Normal where traced | Physical column identity and menu label must both be recorded |
| Battle EXP | Same broad actor/level/role pipeline | `GameData` values above differ substantially | Formula shape can match while awarded EXP differs |
| Fixed growth/autolevel | `apply_fixed_growth_level_up` and the chapter difficulty-field accessor match all three builds | Japanese lacks the later transformed-Laguz row/consumer; chapter bonus levels remain authored | Do not transplant the later seven-row table into Japan without porting code |
| Class critical | Normal weapon/skill forecast pipeline exists | US/PAL read a seventh-row value of 15; Japanese has neither the row nor that addend | This is a native-plus-data regional rule, not localization |
| Deployments | The deployment-record reader and script deployment handlers correspond | Chapter archives choose common and mode-specific authored groups | Native parsing does not make the groups' contents identical |
| Shops | The three retail `shopitem_n.bin`, `_h`, and `_m` files are byte-identical across JP/US/PAL | Current difficulty selects N/H/M; later-build Easy follows N | Inventory differences require a different selector/caller or a modified file, not localization alone |
| Text/tutorial/objective UI | Common selector concepts, build-specific resources and layouts | PAL adds language-specific messages/Rects; JP and US have different text/font surfaces | Localized content can differ while gameplay bytes match |
| Saves | Core party, unit, camera, forge, and CRC routines correspond across all three executables | System language, unlock meaning, definition-table positions, identifiers, and surrounding card metadata remain build-owned | Structural correspondence is not authorization to cross-load or proof that arbitrary saves are portable |

The corpus audit is reproducible with `App/tools/audit_regional_difficulty.py`; it also reports that 3,575 of 3,938 paths common to the extracted Japanese and PAL filesystems are byte-identical, while 363 differ and each build has unique paths. Region is therefore neither “everything differs” nor “only text differs.”

## Lifecycle, inputs, identity, and selection

Region handling starts before FE9 gameplay code interprets a chapter. The disc header supplies a game code such as `GFEE01` for the US build, `GFEP01` for PAL, or `GFEJ01` for Japan. That identity tells a tool which executable layout and resource set it is looking at; it does not convert one build into another. The executable, filesystem contents, and localized assets must agree as a set.

The US, PAL, and Japanese executables share large amounts of logic, but correspondence is established function by function. The repository's current PAL-to-US cross-reference matches bodies after masking relocated operands and checks their call relationships. Address drift grows through the executable rather than remaining one constant offset. Functions without a reliable match remain region-specific research targets, not safe patch sites. See [`main.dol`](../formats/main-dol.md) for the mapping method.

PAL also selects among language-specific resources. The six-name language table and script-facing language query show that language is an engine concept, while the US build's fixed-English behavior shows that not every build exposes the same selection lifecycle. Localized `Rect` resources use suffixes such as `_en`, `_de`, `_es`, `_fr`, and `_it`; their containers can share a format even when their text, glyph inventory, dimensions, and filenames differ. [Font Format](../formats/font-format.md) and [RECT Format](../formats/rect-format.md) describe the resource-level boundaries.

### Selection outputs

The build identity is effectively fixed for the whole run because it comes from the disc and executable being launched. A PAL language choice can select localized resources during boot and scene construction. The playthrough difficulty is chosen at new-game setup, stored in playthrough/save state, and read repeatedly by chapter loaders, scripts, shops, objectives, EXP rules, and unlock logic. These selectors do not rewrite master data; their consumers choose an executable path, table column, or named file when the relevant scene or rule runs.

For example, starting a map loads the common deployment file and the difficulty variants. A script or loader selects the appropriate `_n`, `_h`, or `_m` group for the current difficulty. Opening a shop independently chooses `shopitem_n.bin`, `shopitem_h.bin`, or `shopitem_m.bin`. Resolving an objective can use a Normal, Hard, or Maniac message slot. Calculating battle EXP reads the chosen `GameData` column. The visible chapter is the combined output of those separate decisions.

Region affects outputs at several boundaries: which native instructions execute, which language resource is requested, which glyphs can be drawn, how text wraps, and which mechanics or unlock conditions the build implements. These differences can propagate into UI layout, scripts, saves, and patches even when the underlying container format still parses correctly.

## Worked compatibility example

Suppose a US mod changes a chapter's Hard deployment and patches a native formula at a US address. Porting it to PAL requires two independent operations:

1. Copy or recreate the intended unit changes in the PAL chapter's Hard deployment resource, preserving that resource's labels and archive structure.
2. Locate the corresponding PAL function by its instructions, callers, and data relationships, then verify the patch against the PAL bytes.

Adding a guessed constant to the US address does not establish step 2. Likewise, copying the whole US chapter archive may overwrite localized or region-specific resources that were unrelated to the deployment change. The safe test launches the PAL build, enters the affected chapter on Hard, confirms the expected units and formula result, and checks adjacent UI and save/load behavior.

## Difficulty and region overrides

<span id="fe9-sys-381"></span> Override priority should be documented per subsystem:

1. Shared native logic defines the general rule.
2. The regional executable may replace that logic or its call graph.
3. Current difficulty selects a constant row or named resource.
4. Chapter/difficulty files select authored deployments, shops, or tutorials.
5. Scripts can add one-chapter exceptions through flags, units, items, or events.

For example, battle EXP uses native arithmetic but reads difficulty rows and opponent properties. Enemy composition comes from a difficulty-specific deployment. A boss scripted to retreat can alter the practical reward without changing the EXP formula.

## Compatibility checklist

- Identify disc/game code (`GFEE01`, `GFEP01`, Japanese equivalent) before applying executable offsets.
- Compare symbols, callers, strings, and behavior when porting a patch.
- Name the actual difficulty file/column affected.
- Test formulas separately from authored deployment and shop changes.
- Verify localized text widths, glyphs, and message resource selection.
- Do not assume a US “Easy” choice means Japanese Easy data exists.
- State whether a claim was checked on one build or across regions.

## Interactions, edge cases, and failure modes

- Easy commonly follows the Normal deployment/shop branch in the US build, while the internal difficulty value and formula column remain distinct. Treat “same file” and “same rules” as separate claims.
- Common deployment groups (`_c`) coexist with difficulty groups. Editing only `_n`, `_h`, or `_m` cannot change units that the chapter deploys from the common group.
- A resource can parse identically in all regions while containing different text, glyph references, table order, or authored values.
- A familiar difficulty byte does not make a save portable across builds. Cross-region import is outside the supported contract unless the tool explicitly converts and validates serializers, table indices, identifiers, language/system fields, and unlock semantics.
- Script helpers may recognize internal modes that a retail menu does not expose. Reachability through the shipped UI and existence in native code are different facts.
- A function that matches across regions can still refer to region-specific data. Port both the code site and every data assumption it consumes.

The most common failure pattern is partial portability: the mod boots because the file format is valid, but one consumer still reads the original regional resource, the wrong difficulty branch, or an incompatible table index. Test at the point where each selector is consumed rather than relying only on successful repacking.

## Evidence and confidence

Confirmed US evidence includes the four-value difficulty state, all seven `GameData` accessors, deployment/shop variants, script predicates, save serialization, and fixed-English script/UI behavior. PAL correspondence independently confirms the internal difficulty mapping, address drift, and multilingual resources. Japanese comparison confirms the different retail menu surface and absence of the later class-critical path.

## Evidence limits and validation

No unresolved gap blocks these three system descriptions. The executable correspondence, exact `GameData` section boundaries/values, retail shop hashes, filesystem comparison, selector traces, and save-component correspondences establish the ownership and precedence model. They do **not** promise arbitrary cross-region save portability: a converter remains a separate tool feature and needs non-destructive fixtures for every source/destination pair. Likewise, a mod that changes a regional caller, table, chapter archive, or localized resource should still run that exact build and difficulty; the matrix identifies which layer to test rather than predicting unmodified content from another build.

