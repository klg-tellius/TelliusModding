---
id: "endings"
title: "Endgame & Ending Cards"
description: "How the completed campaign selects, orders, and presents the finale and character epilogues"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Campaign", "Dialogue", "Records"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/endings.md"
system_entries: ["FE9-SYS-036", "FE9-SYS-302"]
system_reviewed: ["FE9-SYS-036", "FE9-SYS-302"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Endgame & Ending Cards

The ending is a campaign transition, not a single movie. After the final battle commits victory, the game leaves tactical state, runs the authored finale, selects epilogues from persistent campaign facts, presents credits, and writes completion state used by later menus and playthroughs. A mod that changes only the visible text can therefore leave eligibility, ordering, unlocks, or clear-data creation untouched.

## Mental model and worked example

Think of the ending as a report generated from the final save. Recruitment and survival decide who is eligible; relationship and story state can choose among variants; the ending script orders presentation; credits and clear-data code close the campaign. If a recruited character survived but a paired variant loses to a higher-priority story ending, the selector must choose one card—not show every text asset that happens to exist. Skipping the card should advance the same selector and reach the same completed save as watching it.

For example, adding a new epilogue requires more than a message key. The character must be admitted by the eligibility filter, the new variant must have an explicit priority against ordinary and paired variants, its card must be inserted into a deterministic order, and both watched and skipped paths must converge before the completion write.

## Endgame and ending selection

<span id="fe9-sys-036"></span> Final-chapter victory reaches the normal completion boundary first: the chapter script sets the victory flag and the battle controller records the clear. Campaign routing then selects the special finale path rather than incrementing into an ordinary next map. The authored ending script (`ending.cmb`, including its `Ending` function references) owns scene sequencing, while persistent roster, death/retreat, recruitment, support/relationship, story-flag, difficulty, and playthrough state provide selection inputs.

Selection must distinguish three operations. **Eligibility** decides whether a character or special ending may appear. **Variant choice** chooses the one applicable text/illustration when several candidates describe the same character. **Ordering** places the chosen results into the presentation sequence. Treating those as one unordered asset scan creates duplicates and unstable results.

The retail route is fixed at the campaign boundary: chapter number 32 invokes the finale over chapter 31's map, runs `GrandFinale`, then calls `Ending` from `Scripts/ending.cmb` before returning to title. This keeps final-battle clear, authored ending selection, credits, and persistent clear-data writes in distinct owners. Presentation skip can advance an ending child, but cannot synthesize or reorder those campaign operations.

The output side also has boundaries. Message and portrait/illustration resources render a chosen record; music, fades, and input control its presentation; credits consume their own ordered resources; completion code writes clear and unlock facts. The presentation layer should not invent survival or relationship state, and the save writer should not infer completion merely because the credits scene was opened in a debugger.

## Ending-card system

<span id="fe9-sys-302"></span> An ending card is the presentation record selected for one eligible character or ending subject. It combines a message identity with the visual and timing context needed to display it. The currently established boundary is that cards consume campaign state rather than owning it: roster membership, survival, departure, and relationships come from persistent systems, while the card process owns layout, fades, input, and advancement.

Candidate enumeration, substitution, and order are authored by the ending script/data path, not inferred from disc asset order. Each selected card owns one presentation lifetime and advances the established sequence on completion or skip. A missing optional visual may fall back or fail that card's presentation, but cannot make an ineligible character eligible or write clear data early.

## Files in Path of Radiance

| Part | Owner |
| --- | --- |
| Sequence | `Scripts/ending.cmb`, exported function `Ending`: credit names (`RID_END_STAFFCREDIT`…), 22 artworks with labels (`RID_END_GR01`–`GR22`, `RID_END_LBL01`–`LBL22`) over `BGM_ED_STAFF1`, the song `BGM_ED_SONG1` with `StaffRoll` and 12 lyric images, copyright and *Fin*, then `WarRecord(15000)` and `IndividualWarRecord(15000)` |
| Images | `ending/RectFinale_en.bin` (US) and `ending/RectFinale.bin` (Japanese), textures in `ending/` |
| War record labels | `Mess/ending.m`: `MED_CHAPnn_TAG` / `MED_CHAPnn_TITLE` per chapter slot, `MED_DIED_CHAPnn`, column headers `MED_REC_LV`, `MED_REC_WIN`, `MED_REC_TURN`; retail has slots 01–31 |
| Character cards | `RID_END_` + the PID without `PID_` (`PID_BOLE` → `RID_END_BOLE`, `ending/bole_en.tpl`, 528 × 376). The name is drawn into the picture; the US cards carry no epilogue text |

The modding app writes the three labels for a chapter it adds and removes them with it. See [Edit the ending and the war record](../modding/79-ending-and-war-record.md).

## Rules and lifecycle

1. Final battle logic commits victory through the ordinary objective/chapter boundary.
2. Clear processing freezes the chapter result and selects the finale route.
3. The ending script runs required story scenes and establishes any last campaign flags.
4. The selector enumerates eligible subjects from persistent state.
5. For each subject it chooses at most one applicable variant according to authored priority.
6. The presenter shows the ordered cards and credits; skip accelerates presentation without omitting required state changes.
7. Completion code records the clear and unlock consequences, then routes to the proper postgame/title destination.

Cancellation is not a normal semantic outcome once final victory has committed. A presentation skip may bypass waiting, animation, or text display, but it must not bypass selector advancement, credits cleanup, completion flags, or the clear-data write. Likewise, replaying or debugging a presentation should not grant duplicate completion effects.

## Inputs, persistence, and interactions

The selector can consume current chapter identity, persistent party membership, character death/retreat state, story/event flags, support or bond state, difficulty, playthrough count, and other completion records. Exact use is variant-specific and must be proven from the selector rather than guessed from the prose of an ending.

Endgame routing interacts with [Chapters](./chapters.md), [Objectives](./objectives.md), [Support System](./support-system.md), [Battle Reports & Performance Records](./battle-reports-records.md), [Events & Scripting](./events-scripting.md), and save data. Music, message formatting, portraits, fades, and credits are downstream presentation consumers. These links matter when changing an ending: a new relationship variant may require support-state access, while a new clear unlock belongs to save/campaign logic rather than the card renderer.

## Edge cases and implementation trail

Dead, unrecruited, departed, trial-only, duplicate, or story-excluded characters must not enter the ordinary card list. A paired ending should not accidentally suppress both characters if its partner becomes ineligible. Equal-priority candidates need deterministic tie behavior. Missing text or illustration resources should fail as a presentation problem without corrupting the completion state. A skipped finale and a fully watched finale should produce byte-equivalent campaign consequences.

The reproducible trail starts at final chapter completion and special campaign routing, continues through `ending.cmb`/`Ending`, then follows roster and relationship readers into card selection, card presentation, credits, and the clear-data writer. Useful differential tests hold the final save constant while changing exactly one fact: survival, recruitment, one support rank, one story flag, difficulty, or playthrough number. A second test compares watched and skipped outcomes before and after the completion write.

## Review boundary

FE9-SYS-036 and FE9-SYS-302 are reviewed without a blocking research gap. Final-battle routing, script-owned eligibility/variant/order, card presentation, credits handoff, skip convergence, and completion-state ownership define the end-to-end contract. A literal census of every retail epilogue candidate is content reference work rather than an unknown engine rule. No additional primary article is needed.
