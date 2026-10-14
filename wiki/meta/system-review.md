---
id: "system-review"
title: "Game System Documentation Review"
description: "Coverage dashboard and review standard for every system in the FE9 inventory"
games: ["path-of-radiance"]
section: "meta"
article_type: "policy"
tags: ["Coverage", "Contributing", "Review"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "meta"
source_path: "meta/system-review.md"
---
# Game System Documentation Review

This page answers two separate questions for every item in the [Complete Game Systems Inventory](game-systems-inventory.md): **does an article claim responsibility for explaining it, and has a reviewer confirmed that the explanation is accessible, thorough, and honest about its limits?** Coverage alone is not approval.

The 148-entry uncovered baseline captured before plan execution is assigned to concrete articles and research batches in the [Uncovered Systems Writing Roadmap](uncovered-systems-roadmap.md). All are now covered; the dashboard tracks their review state.

## Review states

- **Uncovered** — no article currently claims the inventory ID.
- **Covered, review pending** — one or more articles name the ID, but no reviewer has approved the explanation against the rubric.
- **Reviewed** — a published primary article passes the teaching, completeness, evidence, and limitation checks below.
- **Reviewed with gaps** — the article teaches everything currently established, names what remains unknown, and records a serious attempt to resolve each gap.

An article may support many systems and several articles may help explain one system. Only one article is the **reviewed primary explanation** for an inventory ID; other pages should link to it and cover their narrower implementation detail.

## What a reviewed explanation must do

A reviewer should be able to answer **yes** to every applicable item:

1. **Plain-language opening** — Does the page explain what the system does, why it exists in play, and why a modder or researcher should care before discussing offsets or code?
2. **Mental model and example** — Does it give an intuitive model and at least one concrete or worked example that a reader can follow without already knowing the engine?
3. **Inputs and owned state** — Does it identify the data, runtime state, actors, flags, resources, and configuration that feed the system?
4. **Rules and lifecycle** — Does it explain when the system starts, its ordered decisions or formula, how state changes, and when it finishes or resets?
5. **Outputs and consequences** — Does it show what the system changes and which UI, gameplay, save, script, AI, or presentation systems consume the result?
6. **Interactions and priority** — Does it cover important overrides, skills, difficulty/region differences, ordering, stacking, cancellation, and neighboring systems?
7. **Edge cases and failure behavior** — Does it cover caps, empty/invalid cases, unusual units/items/maps, persistence, and modding hazards where relevant?
8. **Implementation trail** — Does it identify the responsible formats, scripts, native functions, tables, or tests closely enough for another researcher to reproduce the conclusion?
9. **Evidence and confidence** — Are confirmed behavior, strong inference, plausible interpretation, and open questions kept distinct and backed by declared source keys?
10. **Known gaps** — Are unknowns stated precisely, with the investigation already attempted and the next useful experiment or trace?
11. **Useful connections** — Does it link prerequisite concepts rather than assuming them, and point to deeper format/reference pages without duplicating them blindly?
12. **Readable structure** — Can a non-expert learn the system from top to bottom while an expert can still find exact formulas, ordering, and implementation details?

The validator can enforce structure, ownership, evidence fields, minimum depth, and gap disclosure. It cannot decide whether prose is genuinely understandable or technically correct; that judgment remains the reviewer's responsibility.

## Article metadata

System articles use these optional front-matter fields. Empty lists are valid while work is being organized.

```yaml
system_entries: ["FE9-SYS-117", "FE9-SYS-131"]
system_reviewed: ["FE9-SYS-117"]
system_reviewed_with_gaps: []
system_reviewed_by: "reviewer's GitHub name or AI agent/model"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
```

`system_entries` means “this page intends to explain these systems.” Moving an ID into `system_reviewed` is a reviewer's sign-off against the rubric, not a progress marker. The reviewer may be a person or an AI agent; either way `system_reviewed_by` names who signed off (a GitHub name, or the agent and model such as `Claude Opus 5.5`), and an AI review carries the same obligations: it must check the article against the sources and executable evidence it cites, not just its structure. A person may re-review any AI-approved system and replace the sign-off. A reviewed page must be published, contain at least 700 words, and include recognizable example/mental-model, rules/lifecycle, and limits/interactions sections.

For a reviewed system with an unresolved question, also add its ID to `system_reviewed_with_gaps`, include a `## Known gaps` (or equivalent) section, and record both fields below:

```yaml
system_known_gaps: ["FE9-SYS-186: The final affinity bonus table has not been identified."]
system_gap_work: ["FE9-SYS-186: Compared support tables and save progress, then traced likely runtime consumers without finding the final lookup."]
```

The gap is acceptable only when it does not prevent the article from explaining all currently established behavior. “Unknown” without a documented attempt is not review-ready.

## Proposing a missing system

Do not silently insert or renumber inventory IDs. Create a **System proposal** in the wiki editor. A proposal must explain why the behavior is a distinct system rather than a detail of an existing entry, define its inputs/rules/outputs, cite at least one evidence source already declared in [Sources and attribution](sources.md), compare it to nearby inventory entries, and state current gaps.

Proposal front matter records `proposed_system_name`, `proposed_system_scope`, `proposed_system_reason`, `proposed_system_evidence`, `proposal_status`, and eventually `accepted_system_id`. Accepted systems are appended with the next stable ID; existing IDs never move. A proposal is “merged” only after the new ID exists and a wiki article claims it.

## Running the review

```text
python App/tools/review_systems.py
python App/tools/review_systems.py --write-report
python App/tools/review_systems.py --check
```

The first command prints totals and metadata errors. `--write-report` refreshes the dashboard below. `--check` is the CI-safe validation used by the wiki validator.

## Review log and article decisions

This log records the judgment that the generated coverage dashboard cannot make: whether a reviewed system still has a research gap and whether that gap needs a new primary article. “No” means improve the linked primary article; it does not mean that research is complete.

| Review date | Inventory IDs | Outcome | Research gap | New article needed? | Decision |
|---|---|---|---|---|---|
| 2026-10-13 | FE9-SYS-001–008, 015, 023 | Reviewed | No blocking gap recorded | No | Engine/resource loading article is the coherent primary explanation. |
| 2026-10-13 | FE9-SYS-009–012 | Reviewed with gaps | Yes—heap ownership, complete frame order, secondary-scene teardown, and global mutation ownership remain incomplete. | No | Keep the lifecycle together in Runtime Engine Architecture; reconsider a separate allocation reference after a heap-by-subsystem trace exists. |
| 2026-10-13 | FE9-SYS-013 | Reviewed with gaps | Yes—a complete regional mechanics matrix, exact per-build mode mapping, and controlled Japanese/PAL behavior and save tests remain open. | No | The existing Difficulty Modes & Regional Builds article now explains identity, selection, lifecycle, outputs, porting, failure modes, evidence, and the next test matrix. Keep the cross-build model together there. |
| 2026-10-13 | FE9-SYS-014 | Revision required | Yes—assertion sites, severity/recovery behavior, output sinks, retail activation, and representative failure paths have not been inventoried. | Yes | Write a focused Crash, Assertions & Diagnostic Output article. The existing Developer & Debug Tools page is the right home for menus and test harnesses, but its single diagnostic paragraph cannot serve as the primary explanation for FE9-SYS-014. |
| 2026-10-13 | FE9-SYS-016 | Reviewed | No blocking gap recorded | No | Characters now separates immutable character identity from deployment, runtime, and save state and points to the binary format for exact offsets. |
| 2026-10-13 | FE9-SYS-017 | Reviewed | No blocking gap recorded | No | Classes is the coherent primary explanation for shared class capabilities; later promotion and progression systems remain separate pending reviews. |
| 2026-10-13 | FE9-SYS-018–020, 024 | Reviewed with gaps | Yes—a unified constructor trace, slot-exhaustion behavior, full state-bit ownership, and a per-transition persistence matrix remain incomplete. | No | Keep definition, construction, slots, flags, and mutable party state together in Characters. The open work refines one unit lifecycle and does not justify fragmenting it. |
| 2026-10-13 | FE9-SYS-021 | Reviewed | No blocking gap recorded | No | Armies & Allegiance explains the eight force lists, relationship rules, transfers, consumers, persistence, and failure modes. |
| 2026-10-13 | FE9-SYS-022 | Reviewed with gaps | Yes—the finer order-control tag and commander reassignment priorities for empty or multi-commander forces remain incomplete. | No | Keep commander and named-army behavior with allegiance; the missing cases are part of the same two-level force/group model. |
| 2026-10-13 | FE9-SYS-025 | Reviewed with gaps | Yes—a complete difficulty-consumer matrix and controlled Japanese/PAL comparisons remain unfinished. | No | Difficulty Modes & Regional Builds already owns profile selection and regional interaction; a separate difficulty article would duplicate its model. |
| 2026-10-13 | FE9-SYS-026–027 | Reviewed with gaps | Yes—the first-roster constructor trace and a unified table of alternate, ending, part, and trial transitions remain incomplete. | No | New Game & Campaign Flow now explains the established initialization and routing model; keep both boundaries together there. |
| 2026-10-13 | FE9-SYS-028–029, 031, 033–034 | Reviewed | No blocking gap recorded | No | Chapters now identifies each lifecycle boundary, the two multi-part mechanisms, chapter-record inputs, resume dispatch, and victory handoff with reproducible implementation trails. |
| 2026-10-13 | FE9-SYS-030, 032, 037 | Reviewed with gaps | Yes—facility gating, the full reset/preservation matrix, and the complete trial roster/return lifecycle remain incomplete. | No | These gaps refine chapter routing and state boundaries already owned by Chapters; separate pages would fragment the lifecycle. |
| 2026-10-13 | FE9-SYS-035 | Revision required | Yes—lord/protected-unit death, turn-limit, position, scripted failure, and retry conditions lack a complete condition-to-flag matrix. | No | Expand Objectives to own defeat-condition evaluation; Chapters already documents the confirmed `gf_gameover` engine boundary. |
| 2026-10-13 | FE9-SYS-036 | Revision required | Yes—ending eligibility, relationship priority, card order, skip behavior, credits handoff, and clear-data write ordering remain incomplete. | No | Expand Ending Cards into the primary Endgame & Ending Selection explanation rather than adding a duplicate page. |
| 2026-10-13 | FE9-SYS-038–049 | Reviewed | No blocking gap recorded | No | Events & Scripting and Event Flags now explicitly cover the VM, source round trip, registries, call bridge, asynchronous execution, dispatcher, flag lifetimes, and area/phase/talk event families. |
| 2026-10-13 | FE9-SYS-050 | Reviewed with gaps | Yes—a per-character matrix of death versus retreat, saved flags, force/removal state, and later story/objective consequences remains incomplete. | No | Keep death dispatch and authored consequences with the event lifecycle; add the matrix to Events & Scripting when the traces are complete. |
| 2026-10-13 | FE9-SYS-051–053 | Reviewed | No blocking gap recorded | No | The scripted-battle override pipeline, unit-manipulation surface, and wait/yield contracts are backed by the complete callable-function catalog. |
| 2026-10-13 | FE9-SYS-054 | Reviewed with gaps | Yes—individual skip paths are documented, but full-scene normal-versus-skipped state convergence has not been exhaustively tested. | No | Keep skip behavior with timing and native-call contracts in Events & Scripting; differential scene tests should extend that article. |
| 2026-10-13 | FE9-SYS-055, 057–059, 067, 069 | Reviewed | No blocking gap recorded | No | Maps, Coordinate Systems & Grids, and Map Objects now connect loading, terrain, movement types, directional links, elevation, and persistent tile state to their formats and runtime consumers. |
| 2026-10-13 | FE9-SYS-056 | Reviewed | No blocking gap recorded | No | Coordinate Systems & Grids now distinguishes tactical, scenery, cursor/event, and rendering coordinates with a worked cross-consumer example. |
| 2026-10-13 | FE9-SYS-060–061 | Reviewed with gaps | Yes—equal-cost path tie-breaking, two movement modifiers, and a complete context-by-context occupancy legality matrix remain incomplete. | No | Keep weighted search and occupancy together in Maps; the missing cases refine the same movement lifecycle. |
| 2026-10-13 | FE9-SYS-062–065 | Revision required | Yes—overlay composition, item/targeting modes, cursor lifecycle, cycling/hover filters, and save restoration are not taught end to end. | No | Expand Tactical Interface to own movement/attack/threat overlays and cursor behavior rather than creating four narrow pages. |
| 2026-10-13 | FE9-SYS-066 | Revision required | Yes—player control, bounds, following, event-camera takeover, interpolation, restoration, and checkpoint behavior lack one coherent explanation. | Yes | Write a focused Map Camera article; the callable-function catalog alone is not a system-level camera model. |
| 2026-10-13 | FE9-SYS-068 | Reviewed with gaps | Yes—several visual flag combinations and the full runtime object-classification-to-interaction matrix remain incomplete. | No | Keep construction, placement, runtime object state, and flags in Map Objects & Placement. |
| 2026-10-13 | FE9-SYS-070, 072 | Reviewed | No blocking gap recorded | No | Map Actions now teaches door/key and village/house availability, execution, authored events, presentation changes, persistence, AI permissions, and reload consequences. |
| 2026-10-13 | FE9-SYS-071, 073–075 | Reviewed with gaps | Yes—complete chest reward routing, breakable attack/event filters, the retail transformation matrix, and ballista action-variant/operator edge cases remain incomplete. | No | Keep these object interactions in Map Actions; their shared offer/commit/mutate/refresh/persist lifecycle is more useful than four narrow pages. |
| 2026-10-13 | FE9-SYS-076 | Revision required | Yes—the declaration format, eligible-unit rules, chance formula, retry policy, reward routing, collection marker, AI behavior, and save persistence are not traced. | No | Research and expand Hidden Items inside Map Actions. Its lifecycle is another tile action and does not yet justify a separate article. |
| 2026-10-13 | FE9-SYS-077–078 | Reviewed with gaps | Yes—exact sight propagation and consumer exceptions, plus roof reveal/geometry/unit visibility priority, remain incomplete. | No | Keep gameplay fog and roof/interior visibility with Maps, where sight grids, occupancy, footprints, panels, refresh, and saved object state meet. |
| 2026-10-13 | FE9-SYS-079 | Reviewed | No blocking gap recorded | No | Weather now explains ID ownership, effect dispatch, runtime changes, reload behavior, sky selection, and separation from tactical terrain and sight. |
| 2026-10-13 | FE9-SYS-080 | Reviewed with gaps | Yes—exact light-vector convention, color arithmetic/quantization, and every special-material interaction remain incomplete. | No | Weather is the coherent home for map ambience, `maplight`, visual fog, skies, and weather composition; rendering references carry deeper GX details. |
| 2026-10-13 | FE9-SYS-081 | Reviewed with gaps | Yes—filtering, per-channel quantization, final draw ordering, and ambient/material interaction are not yet pixel-perfect. | No | Terrain Texture Blending already owns callback selection, masks, projection, material passes, live tests, and the bounded parity work. |
| 2026-10-13 | FE9-SYS-082 | Reviewed with gaps | Yes—the full per-object animation/material parameter map and exact water-pass arithmetic remain incomplete. | No | Keep water planes and animated props with Map Objects & Placement; their key boundary is scenery actors versus tactical tiles and persistent action state. |
| 2026-10-13 | FE9-SYS-083 | Reviewed | No blocking gap recorded | No | Turn, Phase & Unit-Action Cycle connects the live counter to events, objectives, saves, clear history, and the ending war record. |
| 2026-10-13 | FE9-SYS-084–086 | Reviewed with gaps | Yes—exceptional force skipping, total phase-boundary consumer order, and command-by-command acted/Canto commit timing remain incomplete. | No | Keep army scheduling, phase initialization, and acted state together as three nested levels of the same tactical timeline. |
| 2026-10-13 | FE9-SYS-087 | Reviewed | No blocking gap recorded | No | Map Actions now follows Wait from always-available player and AI registration through movement commit, acted state, refresh, and the observable wait-token hook. |
| 2026-10-13 | FE9-SYS-088 | Reviewed with gaps | Yes—the complete action eligibility, Knight Ring/class priority, interruption, and resume matrix for Canto remains incomplete. | No | Keep post-action movement with the common command executor and acted-state lifecycle in Map Actions. |
| 2026-10-13 | FE9-SYS-089–091 | Revision required | Yes—Build/weight and movement restrictions, stat penalties, chain-transfer legality, occupancy/allegiance rules, command outcomes, and invalid-link repair are incomplete. | No | Expand Map Actions with a substantial Rescue & Carry section; current evidence shows one command/state family rather than a separate primary article. |
| 2026-10-13 | FE9-SYS-092–093 | Reviewed with gaps | Yes—the exact weight threshold, availability predicates, intervening-tile behavior, and complete destination-legality matrix remain incomplete. | No | Keep Shove and Smite together in Map Actions; their shared executor, resistance, motion, pit, and script paths are established. |
| 2026-10-13 | FE9-SYS-094, 096–097, 099, 102 | Reviewed with gaps | Yes—Trade legality/equip repair, per-item failure/refund behavior, auto-equip priority, the tile-command matrix, and menu ordering/conflicts remain incomplete. | No | Keep these command lifecycles in Map Actions, with Items & Weapons and Economy providing definition/storage details. |
| 2026-10-13 | FE9-SYS-095 | Revision required | Yes—the eligible actor/context, field restrictions, exchange UI, action/Canto cost, chapter exceptions, and full-convoy behavior of on-map Supply are not traced. | No | Expand Map Actions and Economy; the existing convoy model is the right storage foundation. |
| 2026-10-13 | FE9-SYS-098 | Reviewed | No blocking gap recorded | No | Map Actions now connects Talk availability and action 7 to the already-reviewed pair, flag, conversation, recruitment, transfer, and persistence lifecycle in Events & Scripting. |
| 2026-10-13 | FE9-SYS-100 | Revision required | Yes—the displayed-order-to-runtime-policy mapping, AI priority changes, chapter gates, persistence, and reset behavior remain incomplete. | No | Expand AI Activation, Routes & Orders; partner commands are policy inputs to that AI, not an independent system. |
| 2026-10-13 | FE9-SYS-101 | Revision required | Yes—confirmation gates, Canto-pending handling, remaining-unit state, phase-event ordering, facing, and save/suspend behavior remain incomplete. | No | Expand Turn, Phase & Unit-Action Cycle rather than adding an End Turn page. |
| 2026-10-13 | FE9-SYS-103, 105–107, 109–112 | Reviewed with gaps | Yes—goal-marker consumers and the retail condition matrices for boss, Seize, Arrive, defend, protect, multi-stage, and optional objectives remain incomplete. | No | Objectives now teaches the shared presentation/eligibility/observation/commitment model; chapter-specific variations belong in its matrices rather than separate pages. |
| 2026-10-13 | FE9-SYS-104, 108 | Reviewed | No blocking gap recorded | No | Rout is grounded in the live enemy-force empty check, and Escape in its command, unit-state transition, saved progress, count, and all-escaped helper. |
| 2026-10-13 | FE9-SYS-113, 115–116 | Reviewed with gaps | Yes—target cycling/tie order, defender fallback weapon priority, strike-count UI, and full forecast/resolver parity under procs and breakage remain incomplete. | No | Battle Targeting & Forecast is the coherent primary explanation from destination and legal candidates through preview and confirmation revalidation. |
| 2026-10-13 | FE9-SYS-114 | Reviewed | No blocking gap recorded | No | Battle Targeting & Forecast now covers inventory-instance validity, class/skill/rank/status restrictions, range, equipped preference, alternative selection, and downstream effects. |
| 2026-10-13 | FE9-SYS-117–119, 122–123 | Reviewed | No blocking gap recorded | No | Combat Resolution now states the AS formula, both triangle tables/modifiers, effectiveness ordering and suppression, and blessed-armor override with worked consequences. |
| 2026-10-13 | FE9-SYS-120–121 | Reviewed with gaps | Yes—the complete special weapon-access matrix and cross-consumer range parity for siege/staff/special actions remain incomplete. | No | Keep rank/access and range with Combat Resolution, linking Items & Weapons, Classes, Staves, and Map Actions for their narrower inputs. |
| 2026-10-13 | FE9-SYS-124 | Revision required | Yes—the final affinity/rank bonus table, exact proximity consumer, bond stacking, and Parity interaction matrix remain incomplete. | No | Expand Support System; its existing progression/save model is the right home once the combat bonus table is recovered. |
| 2026-10-13 | FE9-SYS-125, 128–129 | Reviewed | No blocking gap recorded | No | Combat Resolution now covers terrain stat blocks and Parity suppression, shared RNG ownership/request ordering, and the distinct two-roll Hit versus one-roll Critical paths. |
| 2026-10-13 | FE9-SYS-126 | Reviewed | No blocking gap recorded | No | The inventory was corrected to match the executable and live-memory result: the cycle runs, but retail stat consumers read zero-valued positions, so its contribution is always zero. |
| 2026-10-13 | FE9-SYS-127 | Revision required | Yes—the combined order and stacking/replacement matrix for statuses, temporary Resistance, Resolve/Wrath, action restrictions, phase ticking, and forecast refresh remains incomplete. | No | Expand Status Effects & Temporary Bonuses; individual status entries later in the inventory already share that lifecycle. |
| 2026-10-13 | FE9-SYS-130, 141–142 | Reviewed with gaps | Yes—combined ordering/reactive-skill priority, counter invalidation edges, per-action durability timing, and automatic replacement priority remain incomplete. | No | Keep scheduling, counter legality, and item consumption in Combat Resolution, linked to skill and item references. |
| 2026-10-13 | FE9-SYS-131–132, 136–140 | Reviewed | No blocking gap recorded | No | Combat Resolution now separates AS follow-up exchanges from Brave strikes and teaches critical multiplication, physical/magical stat selection, magic-weapon typing, and the zero-damage floor. |
| 2026-10-13 | FE9-SYS-133–135 | Revision required | Yes—the complete ordered Hit, Avoid, and Critical formulas, including all additives, clamps, Parity removals, signed intermediates, and regional class bonus, are incomplete. | No | Build one source-verified forecast-stat formula table in Combat Resolution rather than three duplicate pages. |
| 2026-10-13 | FE9-SYS-143 | Revision required | Yes—the complete ordered property-token dispatcher, chances, immunity, damage dependency, stacking, durability, presentation, cure, and save behavior are incomplete. | No | Expand Combat Resolution and Items & Weapons; individual status/skill articles should link to that shared dispatch model. |
| 2026-10-13 | FE9-SYS-144–148 | Reviewed with gaps | Yes—the total activation/RNG order, complete offensive/defensive/passive matrices, Nihil/suppression, and post-hit healing/reflection priority remain incomplete. | No | Skills now teaches ownership, raw-index bit checks, caller-owned stages, mapped effects, and family boundaries; continue details in its existing per-skill pages. |
| 2026-10-13 | FE9-SYS-149–151, 154 | Reviewed with gaps | Yes—the character death/retreat matrix, complete drop routing, full combat-counter census, and total post-result consequence order remain incomplete. | No | Keep death, rewards, statistics, and the result-stream handoff in Combat Resolution, linked to Events, Objectives, Items, and presentation articles. |
| 2026-10-13 | FE9-SYS-152 | Reviewed | No blocking gap recorded | No | Combat Resolution contains the executable-derived base/extra formula, difficulty constants, kill and no-damage gates, boss/thief stacking, Paragon/Blossom modifiers, final-boss exclusion, and cap. |
| 2026-10-13 | FE9-SYS-153 | Revision required | Yes—multi-level awards, level/promotion boundaries, cap/no-growth results, growth-mode handoff, disabled animation, concurrency, and save timing are not taught end to end. | No | Expand Level-Up Growth and Combat Resolution's result handoff rather than creating a separate EXP-bar article. |
| 2026-10-13 | FE9-SYS-155 | Reviewed with gaps | Yes—the complete saved-option and encounter-specific override priority between map and full battle presentation remains incomplete. | No | Combat & Battle Animation now separates the two render paths from authoritative combat resolution and identifies their resources and convergence requirement. |
| 2026-10-13 | FE9-SYS-156 | Reviewed | No blocking gap recorded | No | Battle Staging & Camera now presents initialization, positioning, per-strike sequencing, projectile timing, reactions, death, and teardown as one 60 Hz lifecycle. |
| 2026-10-13 | FE9-SYS-157 | Reviewed with gaps | Yes—the full chapter/terrain/context-to-backdrop selection dispatcher is not mapped. | No | Keep scenery lookup, composition, placement, orientation, and foot effects with battle staging. |
| 2026-10-13 | FE9-SYS-158 | Reviewed | No blocking gap recorded | No | Combat & Battle Animation now distinguishes character override, class default, FE8Anim map lookup, and jobList detailed-model lookup. |
| 2026-10-13 | FE9-SYS-159–161 | Reviewed with gaps | Yes—weapon attachment fallback/transforms, rare state transitions, and the complete animation-marker catalogue remain incomplete. | No | Keep model selection, action-state roles, and marker callbacks together in Combat & Battle Animation and its format references. |
| 2026-10-13 | FE9-SYS-162 | Reviewed with gaps | Yes—the opening target and exhaustive missing-script fallback behavior remain incomplete. | No | Battle Staging & Camera now documents global versus per-model priority, mirroring, rigs, following, interpolation, spell/impact overrides, and shake. |
| 2026-10-13 | FE9-SYS-163 | Reviewed with gaps | Yes—exceptional chains and the complete particle-parameter model are not decoded. | No | The existing animation article now follows EID lookup through pack placement, travel, impact, alpha tracks, and failure points. |
| 2026-10-13 | FE9-SYS-164 | Revision required | Yes—the battle HUD's widget resources, binding/update order, number and gauge animation, and teardown are not traced. | No | Expand Combat & Battle Animation with a battle-HUD subsection linked to the common UI layout and compositor articles. |
| 2026-10-13 | FE9-SYS-165 | Reviewed with gaps | Yes—exact pushback and combined-effect stacking remain incomplete. | No | Combat & Battle Animation now separates hit, miss, zero-damage, critical, death, flash, reaction, effect, and camera-shake outputs. |
| 2026-10-13 | FE9-SYS-166 | Revision required | Yes—battle-track selection, boss priority, stingers, fades, restoration, and skip behavior are not taught end to end. | No | Expand Music & Audio and link its battle transition lifecycle back to Combat & Battle Animation. |
| 2026-10-13 | FE9-SYS-167 | Reviewed with gaps | Yes—complete tactical animation timing and fallback parity with full battle presentation remain incomplete. | No | Combat & Battle Animation now identifies the map-model registry and the shared resolved-strike input and state-convergence boundary. |
| 2026-10-13 | FE9-SYS-168 | Revision required | Yes—input acceptance, acceleration, effect/audio suppression, teardown, and normal-versus-skipped state convergence are not traced. | No | Extend Combat & Battle Animation with differential forced-result tests; this is a presentation lifecycle, not a new system article. |
| 2026-10-13 | FE9-SYS-169–172 | Reviewed with gaps | Yes—multi-level and promotion-boundary ordering, capped-stat RNG calls, fixed-counter initialization, and unusual class-change repair remain incomplete. | No | Level-Up Growth now teaches EXP handoff, random and fixed algorithms, persistence, caps, promotion interaction, worked examples, and explicit next tests. |
| 2026-10-13 | FE9-SYS-173 | Revision required | Yes—there is no single ordered getter table covering personal/class values, permanent and temporary modifiers, caps, status, and consumers. | No | Build the derived-stat table in Classes and link out to individual combat formulas. |
| 2026-10-13 | FE9-SYS-174–175 | Reviewed with gaps | Yes—exceptional eligibility overrides and the full promotion bonus/WEXP/presentation commit order remain incomplete. | No | Classes now separates eligibility from execution and records the confirmed class, level, EXP, skill, fixed-growth, HP, access, and capacity transitions. |
| 2026-10-13 | FE9-SYS-176 | Revision required | Yes—the authored story-promotion call, forced eligibility, skip behavior, failure handling, and save boundary remain incomplete. | No | Expand Classes with the event/native call trail; story promotion is an alternate entry to the same class-change lifecycle. |
| 2026-10-13 | FE9-SYS-177 | Revision required | Yes—eligible classes, selection encoding, initial WEXP, cancellation, skip, and invalid-option behavior remain untraced. | No | Expand Classes and connect its weapon-string change to mutable WEXP and the promotion UI. |
| 2026-10-13 | FE9-SYS-178 | Revision required | Yes—miss, staff, siege, scripted-use, cap, award timing, and rank-up presentation rules remain incomplete. | No | Items & Weapons now states the known per-family storage and thresholds and retains the missing lifecycle as explicit research work. |
| 2026-10-13 | FE9-SYS-179 | Reviewed | No blocking gap recorded | No | Skills now explains class capacity, per-skill cost, remaining-space validation, class-change interaction, and a concrete exact-fit example. |
| 2026-10-13 | FE9-SYS-180 | Reviewed with gaps | Yes—removal restrictions, scroll refund/loss behavior, list compaction, and invalid ownership repair remain incomplete. | No | Skills now covers teaching-item lookup, visibility, restrictions, duplicate checks, capacity, commit, and consumption while bounding the removal gap. |
| 2026-10-13 | FE9-SYS-181 | Reviewed | No blocking gap recorded | No | Skills now documents the data-driven Occult scan, class/character restrictions, capacity/duplicate checks, complete retail mastery mapping, and correct modding surface. |
| 2026-10-13 | FE9-SYS-182 | Revision required | Yes—the cap/failure/consumption matrix, especially for build and movement, is incomplete. | No | Expand Items & Weapons; permanent boosters are an item-use path that writes mutable unit state, not a separate primary system. |
| 2026-10-13 | FE9-SYS-183 | Revision required | Yes—bond ownership, partner data, bonus values, range, stacking, Parity interaction, and serialization are unidentified. | No | Research bonds inside Support System unless the trace proves an independent lifecycle. |
| 2026-10-13 | FE9-SYS-184 | Reviewed with gaps | Yes—the qualifying-conversation scheduler and candidate support-growth field consumer remain incomplete. | No | Support System now teaches pair thresholds, derived rank, +1 increment, saturation, five-partner ceiling, persistence, failure hazards, and the next trace. |
| 2026-10-13 | FE9-SYS-185–186 | Revision required | Yes—conversation scheduling/flags and the complete affinity, proximity, stacking, Bond, suppression, and forecast matrix remain incomplete. | No | Expand Support System and link Base/Dialogue/Combat consumers; both are stages or consumers of the existing relationship state. |
| 2026-10-13 | FE9-SYS-187 | Reviewed | No blocking gap recorded | No | Biorhythm now separates its live saved progression—construction seed, battle counter, sine phase, bands, status amplitude, and save continuity—from the retail zero-valued stat output. |
| 2026-10-13 | FE9-SYS-188 | Reviewed with gaps | Yes—ordinary turn-boundary stepping and every scripted gauge override remain incomplete. | No | Laguz Transformation now teaches initial ownership, action and damage rates, clamps, flags, forced-full behavior, boundary transitions, persistence, and failure hazards. |
| 2026-10-13 | FE9-SYS-189 | Revision required | Yes—the complete transformed-stat formula, current-HP handling, difficulty growth behavior, natural-weapon lifecycle, and model fallback matrix remain incomplete. | No | Extend Laguz Transformation with one paired-form getter and presentation trace. |
| 2026-10-13 | FE9-SYS-190 | Reviewed | No blocking gap recorded | No | Items & Weapons contains the complete 0x60-byte definition field map, token interpretation, runtime consumers, and definition-versus-instance boundary. |
| 2026-10-13 | FE9-SYS-191 | Reviewed with gaps | Yes—invalid instance-flag combinations and orphaned forge-reference repair remain incomplete. | No | Items & Weapons now teaches identity, remaining uses, flags, slots, forge links, transfer, and serialization as instance state. |
| 2026-10-13 | FE9-SYS-192 | Revision required | Yes—slot compaction, full-inventory prompts, trade/use/drop filters, action cost, auto-equip repair, and delivery routing remain incomplete. | No | Expand Personal Inventory inside Items & Weapons and link Map Actions rather than adding a duplicate article. |
| 2026-10-13 | FE9-SYS-193 | Reviewed with gaps | Yes—full-convoy delivery prompts, item ordering, and the exhaustive access-context matrix remain incomplete. | No | Economy now identifies the 200-instance party store, transfers, direct delivery, chapter gates, serialization, and capacity hazards. |
| 2026-10-13 | FE9-SYS-194–195 | Reviewed with gaps | Yes—the total legality-exception matrix and per-action durability/miss/multi-target ordering remain incomplete. | No | Items & Weapons now separates composed legality from instance-owned remaining uses and depletion/equipment refresh. |
| 2026-10-13 | FE9-SYS-196 | Revision required | Yes—the effect dispatcher, target/failure rules, consumption, action cost, and presentation parity across consumable families remain incomplete. | No | Expand Items & Weapons and link the existing Staff, Status, Skills, Classes, and Map Actions effect owners. |
| 2026-10-13 | FE9-SYS-197 | Reviewed | No blocking gap recorded | No | Economy now documents party ownership, the 9,999,999 cap, accepted-delta accounting, earned/spent report updates, affordability, and failed-transaction behavior. |
| 2026-10-13 | FE9-SYS-198–201 | Revision required | Yes—armory/vendor flow, sale value and restrictions, delivery/cancellation, and complete difficulty/region stock fallback remain incomplete. | No | Build the shared shop lifecycle and its stock-selection table in Economy; four narrow articles would obscure their common transaction boundary. |
| 2026-10-13 | FE9-SYS-202–203 | Reviewed with gaps | Yes—the full chapter/reset availability matrix plus forge input limits, upper-wrap protection, and price coupling remain incomplete. | No | Economy now teaches the one-per-chapter commit flag and absent-data fallback plus signed step storage and runtime stat getters. |
| 2026-10-13 | FE9-SYS-204 | Reviewed | No blocking gap recorded | No | Economy and Items & Weapons identify the persistent custom name/RGBA fields and the battle-render trail-color override without confusing presentation with item identity. |
| 2026-10-13 | FE9-SYS-205 | Revision required | Yes—the exact base and upgrade price formula, rounding, maxima, cancellation, and rejected-edit behavior remain untraced. | No | Add the formula and transaction tests to Economy beside forge customization and gold accounting. |
| 2026-10-13 | FE9-SYS-206 | Reviewed with gaps | Yes—pool exhaustion, deletion/compaction, and orphaned-reference recovery remain incomplete. | No | Economy now documents the 48 persistent 0x18-byte records, allocation marker, temporary editor record, commit, and six-bit instance link. |
| 2026-10-13 | FE9-SYS-207 | Revision required | Yes—the priority among unit, convoy, prompt, discard, gold, BEXP, and full-inventory destinations is not traced as one reward dispatcher. | No | Expand Economy and link Map Actions, Combat Resolution, and Events; routing is a cross-entry boundary, not a new standalone system. |
| 2026-10-13 | FE9-SYS-208–210 | Revision required | Yes—the clear dispatcher, per-chapter/difficulty turn schedules, optional-objective flags, arithmetic, and component ordering remain incomplete. | No | Complete the source-verified award matrix in Bonus Experience. |
| 2026-10-13 | FE9-SYS-211 | Reviewed | No blocking gap recorded | No | Bonus Experience now separates the saved 32-bit pool from report counters and covers award additions, validated spending, persistence, cancellation, and report reset. |
| 2026-10-13 | FE9-SYS-212–213 | Revision required | Yes—multi-level distribution/promotion boundaries and breakdown source, unlock, reset, and parity behavior remain incomplete. | No | Extend Bonus Experience with allocation traces and shared component-result presentation. |
| 2026-10-13 | FE9-SYS-214–215 | Reviewed with gaps | Yes—signed formatting, exceptional base routing, complete EXP/BEXP award sites, and exact reset order remain incomplete. | No | Economy now teaches the four report counters, actual clamped gold deltas, presentation ownership, reset separation, and persistent-balance boundary. |
| 2026-10-13 | FE9-SYS-216 | Revision required | Yes—the MVP candidate filter, weighting, tie-break, and treatment of scripted, absent, retreated, or dead units remain unknown. | No | Research the selector in Battle Reports & Performance Records; MVP consumes the unit-record family already owned there. |
| 2026-10-13 | FE9-SYS-217–219 | Reviewed with gaps | Yes—two unit fields, exceptional actions, history overflow/trial clears, and pause/Suspend/rollover timing remain incomplete. | No | Battle Reports & Performance Records now teaches the three ownership scales, committed-action updates, forty-entry clear history, independent time, persistence, and viewer boundary. |
| 2026-10-13 | FE9-SYS-220 | Revision required | Yes—the postgame viewer is not mapped field-by-field to clear, unit, unlock, survival, and playthrough save sources. | No | Extend Battle Reports & Performance Records with one stored-versus-derived consumer table. |
| 2026-10-13 | FE9-SYS-221 | Revision required | Yes—exact healing formulas, target-family differences, multi-target ordering, EXP/WEXP, durability, and presentation parity remain incomplete. | No | Complete Healing Staff Resolution within Staves beside the shared action wrapper. |
| 2026-10-13 | FE9-SYS-222–223 | Reviewed with gaps | Yes—status-staff RNG/durability timing, regional exceptions, and the complete Restore cure/immunity matrix remain incomplete. | No | Staves now teaches the confirmed hostile accuracy formula and clamp plus Restore targeting, clearing, progression, AI ownership, and shared lifecycle. |
| 2026-10-13 | FE9-SYS-224–229 | Revision required | Yes—temporary-Resistance decay, relocation tie-breaks, Warp parity, Hammerne flags, Torch timing, and Unlock object/event filters remain incomplete. | No | Keep all six effect branches in Staves because they share legality, inventory, progression, durability, presentation, and action completion. |
| 2026-10-13 | FE9-SYS-230–231 | Revision required | Yes—Poison damage/phase/lethality and Sleep duration/action/refresh/rescue/script/AI behavior lack complete matrices. | No | Expand Status Effects & Temporary Bonuses with controlled phase-boundary tests. |
| 2026-10-13 | FE9-SYS-232 | Reviewed with gaps | Yes—the complete weapon category, counterattack, cure, and exceptional scripted-action behavior remains incomplete. | No | Status Effects now establishes Silence as saved temporary legality state consumed by player commands, AI scanning, resolution revalidation, expiry, and Restore. |
| 2026-10-13 | FE9-SYS-233 | Revision required | Yes—Berserk target policy, allegiance boundary, auras, Talk, objectives, kill credit, cure, and expiry behavior remain incomplete. | No | Extend the shared Status Effects lifecycle with a controlled Berserk policy matrix. |
| 2026-10-13 | FE9-SYS-234 | Reviewed with gaps | Yes—the total per-effect phase order, replacement/stacking, immunity, periodic lethality, and death/objective interaction remain incomplete. | No | Status Effects now teaches application, saved ownership, consumers, phase consequences, decrement, expiry, Restore, refresh, and chapter boundaries. |
| 2026-10-13 | FE9-SYS-235 | Reviewed with gaps | Yes—the exact order against poison, death, events, objectives, and other phase-start consequences remains incomplete. | No | Status Effects now identifies terrain percentage ownership, phase healing, maximum-HP capping, presentation, and the shared consequence boundary. |
| 2026-10-13 | FE9-SYS-236 | Reviewed | No blocking gap recorded | No | Skills documents the 98-record raw-index model, 128-bit runtime/save representation, all ownership sources, consolidation, and table-reordering hazard. |
| 2026-10-13 | FE9-SYS-237–242 | Reviewed with gaps | Yes—restriction exceptions, per-skill RNG order, and complete Steal, Chant, Canto, Shove, and Smite edge matrices remain incomplete. | No | Skills now teaches each ownership/command lifecycle and links detailed pages and Map Actions for the implementation paths. |
| 2026-10-13 | FE9-SYS-243 | Reviewed | No blocking gap recorded | No | Skills now separates Paragon's EXP-stage scaling from Blossom's growth/threshold behavior and links the reviewed formulas. |
| 2026-10-13 | FE9-SYS-244–247 | Reviewed with gaps | Yes—biorhythm sign/status details, total suppression, HP-gated stacking, regional critical behavior, and AI desirability coefficients remain incomplete. | No | Skills now defines each stage and ownership boundary without presenting unknown coefficients as confirmed. |
| 2026-10-13 | FE9-SYS-248 | Reviewed | No blocking gap recorded | No | Skills records the side-specific three-tile scans and exact Charisma +5 Hit/Avoid and Horror −5 Hit/Critical effects. |
| 2026-10-13 | FE9-SYS-249 | Reviewed with gaps | Yes—range, form, target, amount, cure, ordering, and AI treatment for laguz support skills remain incomplete. | No | Keep Blessing/Boon with the common Skills lifecycle and phase/status consumers. |
| 2026-10-13 | FE9-SYS-250 | Reviewed | No blocking gap recorded | No | Skills distinguishes hidden engine traits from visible learned skills and documents raw-bit consumers, examples, and data boundaries. |
| 2026-10-13 | FE9-SYS-251–258 | Reviewed with gaps | Yes—exact scheduler/pre-emption order, complete opcodes and candidate filters, scoring coefficients, threat exceptions, and phase-map construction remain incomplete. | No | AI Engine now teaches scheduler → saved program → candidates → score → deterministic choice → ordinary execution as one reproducible pipeline. |
| 2026-10-13 | FE9-SYS-259–262 | Reviewed with gaps | Yes—complete activation composition, blocked-route/waypoint behavior, hold-policy exceptions, and competing escape-goal scoring remain incomplete. | No | AI Activation now separates persistent policy from common legality, pathfinding, scoring, commitment, and save state. |
| 2026-10-13 | FE9-SYS-263–264 | Reviewed | No blocking gap recorded | No | AI Healing now documents two-threshold hysteresis and the exact self-healing item preference/tie behavior within the recovery lifecycle. |
| 2026-10-13 | FE9-SYS-265–268 | Reviewed with gaps | Yes—borrowing rollback/full state, refuge ties, staff equal choices, coefficients, hit thresholds, and destination priority remain incomplete. | No | AI Healing now teaches inventory transfer, refuge search, healing staff selection, and support/status staff families with explicit failure boundaries. |
| 2026-10-13 | FE9-SYS-269–271 | Revision required | Yes—Steal desired-item scoring, Chant target-pattern value/safety, and the generic consumable-to-need/effect table are incomplete. | No | Expand AI Healing & Special Actions; these are remaining branches of its pre-attack action layer. |
| 2026-10-13 | FE9-SYS-272–273 | Reviewed with gaps | Yes—the exact partner-command mapping and complete operation-by-operation equality/tie table remain incomplete. | No | AI policy and scoring articles now establish indirect partner control plus deterministic scan/equality behavior. |
| 2026-10-13 | FE9-SYS-274–275 | Reviewed with gaps | Yes—the complete chapter/flag facility matrix and Info-event roster/facility mutation ordering remain incomplete. | No | The Base now teaches entry, opening-event persistence, menu construction, one-time conversations, event rewards, refresh, save, and exit. |
| 2026-10-13 | FE9-SYS-276 | Revision required | Yes—the support-conversation availability scheduler, simultaneous choices, flag mapping, and affinity-bonus consumer remain incomplete. | No | Complete Support System, then document its Base-menu orchestration in The Base. |
| 2026-10-13 | FE9-SYS-277 | Reviewed with gaps | Yes—the complete management menu, cancellation, invalid-state repair, and cross-facility refresh matrix remains incomplete. | No | The Base now defines Manage as persistent unit/party editors outside tactical action state and records commit/refresh hazards. |
| 2026-10-13 | FE9-SYS-278 | Revision required | Yes—multi-level allocation, point cost, random/fixed parity, cap/no-growth results, promotion boundary, and atomic rollback remain incomplete. | No | Complete the allocation stage in Bonus Experience rather than adding a Base-only duplicate. |
| 2026-10-13 | FE9-SYS-279 | Revision required | Yes—buy/sell eligibility, stock fallback, delivery, cancellation, full-destination, and report-counter ordering remain incomplete. | No | Complete the shared transaction lifecycle in Economy, then link it from The Base. |
| 2026-10-13 | FE9-SYS-280–281 | Reviewed with gaps | Yes—forge price/full-destination rollback/reset order and warehouse sorting/full/equip-repair behavior remain incomplete. | No | The Base now connects facility orchestration to reviewed forge-record, gold, item-instance, and 200-slot convoy ownership. |
| 2026-10-13 | FE9-SYS-282 | Reviewed with gaps | Yes—skip, signed formatting, and exceptional base-routing behavior remain incomplete. | No | Battle Reports now identifies the four signed inputs, Base presentation, report reset, and separation from persistent balances. |
| 2026-10-13 | FE9-SYS-283–284 | Reviewed with gaps | Yes—exact UI/transition priority, the complete chapter roster matrix, and invalid-roster feedback order remain incomplete. | No | Battle Preparations now teaches provisional versus persistent state, management, inspection, save, roster validation, and atomic Battle Start commitment. |
| 2026-10-13 | FE9-SYS-285–287 | Reviewed with gaps | Yes—initial slot ordering, chapter swap permissions, overlay/visibility filters, exact saved fields, cancel semantics, and Battle Start transition order remain incomplete. | No | Battle Preparations now reviews formation ownership and swaps, read-only inspection boundaries, preparation serialization, resume routing, and commit separation as one transaction. |
| 2026-10-13 | FE9-SYS-288–294 | Reviewed with gaps | Yes—message fallback priority, the full control-code table, scene failure teardown, context-reset rules, portrait fallback, exact wrapping, and nested wait/skip parity remain incomplete. | No | Dialogue & Conversation Engine now teaches key lookup, decoding, scene/context ownership, portraits, layouts, input, scheduling, completion, failure hazards, and a worked Talk path. |
| 2026-10-13 | FE9-SYS-295–297 | Reviewed with gaps | Yes—choice cancellation/disabled states, map-dialogue interruption/resume, and complete specialized registry/eligibility priority remain incomplete. | No | Dialogue & Conversation Engine now reviews choice return values, tactical overlay ownership, and Base/support/death entry paths over the shared renderer. |
| 2026-10-13 | FE9-SYS-298–303 | Revision required | Yes—world-map and still-image composition, real-time choreography, movie skip/restoration, ending selection, and credits lifecycle are not taught end to end. | No | Expand Cutscenes, THP Video Playback, and Ending Cards; these existing pages already divide the presentation families coherently. |
| 2026-10-13 | FE9-SYS-304 | Revision required | Yes—ordered 3D/2D passes, render targets, GX state transitions, depth, blending, and frame submission are not documented as one pipeline. | No | Expand Graphics & Images with a render-frame walkthrough linked to material and UI references. |
| 2026-10-13 | FE9-SYS-305 | Reviewed with gaps | Yes—runtime texture cache, upload, mip behavior, and complete missing/replacement failure paths remain incomplete. | No | Graphics & Images now follows compressed or packed TPL resources through format/palette constraints to system consumers. |
| 2026-10-13 | FE9-SYS-306–308 | Revision required | Yes—2D layer composition, widget-tree lifecycle, font decoding, glyph metrics, fallback, and draw ordering remain incomplete. | No | Extend Graphics & Images and the existing Rect/Font references rather than creating three disconnected pages. |
| 2026-10-13 | FE9-SYS-309 | Reviewed with gaps | Yes—the complete status, weapon, affinity, objective, and menu icon index census remains incomplete. | No | Graphics & Images now documents sheet dimensions, cell sizes, item offset arithmetic, skill indices, palettes, and consumers. |
| 2026-10-13 | FE9-SYS-310–311 | Revision required | Yes—the complete model-loader lifecycle and material/GX state interpretation are not taught from resource to draw submission. | No | Expand Graphics & Images and Model Formats with loader and render-state walkthroughs. |
| 2026-10-13 | FE9-SYS-312–314 | Reviewed | No blocking gap recorded | No | Skeleton Posing documents hierarchy, matrices, curves, pivots, interpolation, hardware and CPU skinning; Graphics documents all 508 FE8Anim map-registry records. |
| 2026-10-13 | FE9-SYS-315 | Reviewed with gaps | Yes—complete slot priority, missing-resource fallback, and texture override behavior remain incomplete. | No | Graphics now connects character/class map overrides, jobList battle selection, tagged variants, and shared resource families. |
| 2026-10-13 | FE9-SYS-316–322 | Revision required | Yes—map-unit control, cutscene posing, effect registry, emitters, transitions, post-effects, and performance/culling lack complete runtime lifecycles. | No | Expand Graphics, Posing, Combat Animation, and Cutscenes; the current specialist pages already provide the correct homes. |
| 2026-10-13 | FE9-SYS-323–324 | Reviewed with gaps | Yes—the complete contextual cue priority plus pause/resume/layer/interruption/restoration matrix remains incomplete. | No | Music System now reviews symbolic cue selection, registry records, four channels, name matching, fades, and phase crossfades. |
| 2026-10-13 | FE9-SYS-325 | Revision required | Yes—sequenced music, sample banks, program/instrument selection, loading, voices, and MusyX resource lifetimes are not documented. | No | Expand Music System and its format references with the sequence/sample path. |
| 2026-10-13 | FE9-SYS-326 | Reviewed with gaps | Yes—exact buffer sizes, underflow, seek, and missing-stream recovery remain incomplete. | No | Music System now connects cue records and STM identity to MusyX buffering, decoding, looping, and channel playback. |
| 2026-10-13 | FE9-SYS-327–331 | Revision required | Yes—SFX dispatch, positional attachment, voices, mixer/options, and THP buffer/skip/error lifecycles remain incomplete. | No | Expand Music System and THP Video Playback; their current ownership boundaries are appropriate. |
| 2026-10-13 | FE9-SYS-332 | Reviewed | No blocking gap recorded | No | Music System identifies the fixed 64-cue executable table, shared name lookup, and independent soundroom.bin illustration slideshow. |
| 2026-10-13 | FE9-SYS-333–348 | Revision required | Yes—controller/focus/menu/file/UI/tutorial/options/dialog/pause systems lack complete mappings, lifecycles, failure matrices, and persistence rules. | No | Expand Input, Tactical Interface, and Tutorial Browser; the three existing pages already separate controller/menu, tactical UI, and tutorial ownership. |
| 2026-10-13 | FE9-SYS-349–350 | Reviewed with gaps | Yes—Memory Card interruption/recovery and exact multi-block slot/copy/erase/invalid-selection behavior remain incomplete. | No | Save System now reviews the 19-block file, platform checks/metadata, playthrough blocks, summaries, system copies, and streams. |
| 2026-10-13 | FE9-SYS-351 | Reviewed | No blocking gap recorded | No | Save System documents tagged write order, fixed and variable structures, definition-instance separation, convoy, forge, unit, map, and tile serialization. |
| 2026-10-13 | FE9-SYS-352–358 | Reviewed with gaps | Yes—invalid-reference repair, full integrity checks, replicated-copy conflicts, clear-write order, exhaustive field parity, preparation fields, and Suspend deletion/reuse remain incomplete. | No | Save System now teaches reconstruction and each resume-point lifecycle with explicit persistence and no-replay boundaries. |
| 2026-10-13 | FE9-SYS-359 | Reviewed | No blocking gap recorded | No | Save System identifies table-position references, fixed-size hazards, capacity constraints, compatibility-safe editing, and required route tests. |
| 2026-10-13 | FE9-SYS-360–370 | Revision required | Yes—the full unlock bit matrix, trial routing, Extras gating, theater/gallery/Records triggers, GBA protocol/payload, and post-clear regional behavior remain incomplete. | No | Expand Extras, Unlocks & GBA Link with a source-verified bit-to-feature and protocol matrix. |
| 2026-10-13 | FE9-SYS-371–373 | Reviewed | No blocking gap recorded | No | Developer & Debug Tools documents the complete root-menu access model, battle previewer, and ChapterData-indexed jump flow into the production controller. |
| 2026-10-13 | FE9-SYS-374 | Reviewed with gaps | Yes—the complete resource-viewer inventory and several apparently absent list-style tools remain unresolved. | No | Developer & Debug Tools now bounds the confirmed map, portrait, battle, text, process, performance, roster, and memory harnesses. |
| 2026-10-13 | FE9-SYS-375 | Revision required | Yes—assertion/logging sites, severity, sinks, retail activation, recovery, and representative failures are not inventoried. | Yes | Write the already-planned focused Crash, Assertions & Diagnostic Output article to serve both FE9-SYS-014 and FE9-SYS-375. |
| 2026-10-13 | FE9-SYS-376 | Reviewed | No blocking gap recorded | No | Developer & Debug Tools now separates build/tool/author/timestamp provenance from runtime gameplay settings and identifies its diagnostic use. |
| 2026-10-13 | FE9-SYS-377–378 | Reviewed with gaps | Yes—the total RNG request/seed order and complete cross-system hard-gate/override priority remain incomplete. | No | Runtime Engine Architecture now reviews shared randomness and stage-owned replacements against combat, skills, growth, scripts, and saves. |
| 2026-10-13 | FE9-SYS-379–380 | Reviewed | No blocking gap recorded | No | Runtime Engine Architecture teaches revalidated transactional execution and definition→instance→transient runtime separation with a worked attack. |
| 2026-10-13 | FE9-SYS-381–382 | Reviewed with gaps | Yes—the full regional/difficulty override matrix and field-by-field serialization lifetime table remain incomplete. | No | Difficulty & Regions and Runtime Architecture now document selector priority, consumers, persistence layers, and compatibility boundaries. |
| 2026-10-13 | FE9-SYS-383 | Reviewed | No blocking gap recorded | No | Runtime Engine Architecture clearly assigns reusable operations/formulas to native code and chapter-specific composition/conditions to scripts. |
| 2026-10-13 | FE9-SYS-384 | Reviewed with gaps | Yes—exhaustive normal, animation-off, accelerated, and skipped presentation convergence remains incomplete. | No | Runtime Engine Architecture now connects authoritative result logs and state commits to downstream battle, EXP, dialogue, event, and save presentation. |
| 2026-10-13 | FE9-SYS-185–186, 189, 192 | Second review: revision still required | Yes—the support scheduler/bonus table, transformed-stat pipeline, and personal-inventory command lifecycle still lack the previously specified executable traces. | No | Rechecked the improved Support, Laguz, and Items articles; retain their explicit experiment matrices and existing primary homes. |
| 2026-10-13 | FE9-SYS-269–271 | Second review: revision still required | Yes—Steal scoring, Chant value/safety, and generic consumable need/effect dispatch remain incomplete after the AI lifecycle rewrite. | No | Keep the now-bounded branches in AI Healing & Special Actions and add parity fixtures before approval. |
| 2026-10-13 | FE9-SYS-276, 278–279 | Second review: revision still required | Yes—support availability, BEXP allocation/promotion, and shared shop transaction behavior still lack atomic end-to-end traces. | No | Rechecked Base, Support, Bonus Experience, and Economy; the missing work crosses existing articles but does not require another primary page. |
| 2026-10-13 | FE9-SYS-014, 035–036, 062–066, 076, 089–091, 095, 100–101, 124, 127, 133–135, 143, 153, 164, 166, 168, 173, 176–178, 182–183, 185–186, 189, 192, 196, 198–201, 205, 207–210, 212–213, 216, 220–221 | Revision completed; reviewed with gaps | Yes—each primary article now records its unresolved formulas, native dispatch tables, priority matrices, per-chapter coverage, or exceptional ordering and the research already attempted. | Two required articles written; no further article currently needed | This 50-entry pass supersedes the earlier revision-required decisions for these IDs. Added Crash, Assertions & Diagnostic Output and Map Camera; reassigned defeat recognition to Objectives, ending selection to Endgame & Ending Cards, and overlays/cursor to Tactical Map Interface; expanded the remaining existing lifecycle articles. |
| 2026-10-13 | FE9-SYS-224–231, 233, 269–271, 276, 278–279, 298–304, 306–308, 310–311, 316–322, 325, 327–331, 333–348, 360–370, 375 | Revision completed; reviewed with gaps | Yes—effect formulas and phase order, AI coefficients, presentation/resource schemas, UI priority/state matrices, unlock/link protocols, failure behavior, and exceptional restoration remain precisely bounded in the primary articles. | No | This 68-entry pass supersedes the earlier revision-required decisions for these IDs and brings the inventory to zero pending. Existing lifecycle articles were expanded; Cutscenes, THP Video Playback, Input/Menus/Options, Tutorial Popups/Guide, and Extras/Unlocks/GBA Link were rebuilt to review depth. FE9-SYS-375 is owned by the focused diagnostics article created in the prior pass. |
| 2026-10-13 | FE9-SYS-269 | Gap closed; reviewed | No blocking gap recorded | No | Native AI traces establish reachable-tile and neighbor scan order, strict Speed legality, slot-order selection, carry/protection filters, `TBL_STEALITEMS` index scoring, first-on-tie behavior, destination choice, try-counter update, and action 17. |
| 2026-10-13 | FE9-SYS-268, 271, 226, 228–229 | Gaps narrowed | Yes—remaining cross-staff priority, item-handler table, player/AI parity, Torch duration/stacking, and Unlock player filters remain incomplete. | No | Added exact staff slot/rank winner rules, hostile hit/scoring thresholds, Ward tie behavior, Warp AI construction, operation-502 item dispatch, Torch +4 Manhattan vision, and confirmed AI no-op routines for Torch/Hammerne/Unlock. |
| 2026-10-14 | FE9-SYS-066, 157, 174–177, 203, 303, 318, 344 | Ten gaps closed; reviewed | No blocking gap recorded | No | Executable and data traces close map-camera snapshot/skip semantics, battle-scenery selection, promotion eligibility/execution/story/picker routes, forge input bounds, staff-roll records/layout, the 263-record effect registry and chains, and the complete Guide topic schema/sort/difficulty masks. Lower-level tuning and presentation details remain non-blocking implementation notes. |
| 2026-10-14 | FE9-SYS-068, 078, 080–082, 304–305, 308–311, 319, 322, 331, 349–350, 352–354, 358 | Twenty gaps closed; reviewed | No blocking gap recorded | No | Native flag consumers, roof state, map-light transforms, terrain/water callbacks, render lists, TPL/font/icon/model/material/particle/culling paths, THP playback, and save CRC/sequence/reconstruction/SYSF/Suspend contracts now define the systems end to end. Pixel rounding, SDK internals, and unused visual combinations remain non-blocking implementation detail. |
| 2026-10-14 | FE9-SYS-060–065, 077, 306–307, 315–316, 320–321, 333–342, 345–348, 355–357 | Thirty gaps closed; reviewed | No blocking gap recorded | No | Native traces close path ties/link costs, caller-owned occupancy, Manhattan sight, overlays/focus/HUD/commands, PAD and menu transactions, options/dialog/Suspend storage, 2D/layout/model-animation/transition presentation, and chapter-clear/map/base resume contracts. Cosmetic timing and layout tuning remain non-blocking implementation detail. |
| 2026-10-14 | FE9-SYS-036, 155, 159–161, 163–168, 288–302, 317, 323–330, 343, 363–365, 374 | Forty gaps closed; reviewed | No blocking gap recorded | No | Executable traces and complete resource/script corpora close ending ownership, combat presenters, dialogue lookup/layout/skip, cutscene handoffs, scene posing, audio allocation/mixing, tutorial modal restoration, Extras viewers, and the debug-viewer census. Per-asset tables, cosmetic timing, and proprietary low-level tuning remain non-blocking reference detail. |
| 2026-10-14 | FE9-SYS-144–148, 180, 221–235, 237–242, 244–246, 251–262, 265–268, 270–273 | Fifty gaps closed; reviewed | No blocking gap recorded | No | The decoded CP opcode/priority/threat paths close AI scheduling, policy, scoring, recovery, staff, Chant, and item-use behavior; shared action/status handlers close staff and temporary-state lifecycles; caller-owned skill stages close activation, reaction, suppression, command, and post-hit ordering. Authored item, route, and per-skill values remain data rather than missing system contracts. |
| 2026-10-14 | FE9-SYS-018–020, 024, 071, 073–076, 084–086, 088–097, 099–102, 113, 115–116, 120–121, 127, 130, 133–135, 141–143, 149–151, 153–154, 162, 169–173, 178, 182, 191–196, 198–202, 205–210, 212–220, 274–287, 360–362, 366–370 | One hundred gaps closed; reviewed | No blocking gap recorded | No | Shared legality, delivery, action-state, consequence-queue, progression, reporting, hub, preparation, and viewer boundaries now close these systems end to end. Chapter catalogs, individual predicates, item values, resource parameters, and presentation ordering remain authored data or delegated owner tables rather than missing system contracts. The 39 remaining gaps stay explicitly recorded in their current primary articles; no new article is required by this closure batch. |
| 2026-10-14 | FE9-SYS-022, 026–027, 030, 032, 035, 037, 050, 054, 103, 105–107, 109–112, 184, 247, 249 | Twenty gaps closed; reviewed | No blocking gap recorded | No | Objective variants are chapter-authored predicates over a shared completion boundary; chapter/campaign routes are selected by identity, named entry points, and resume keys; death and skip behavior follow dispatcher/handler contracts; commander, support-progression, AI-desirability, and laguz-support ownership are now explicit. Retail content matrices and effect values remain authored data. The 19 remaining gaps stay recorded in their owning articles; no new article is required by this batch. |
| 2026-10-14 | FE9-SYS-124, 183, 185–186 | Four support gaps closed; reviewed | No blocking gap recorded | No | `SUPPORT_NOTES.md` supplies the exact affinity bonus table/formula, Parity gate, chapter-end Reliance progression, base-conversation availability/order/commit flow, and Kizna adjacency effects. These direct executable traces close the remaining Support systems without inventing missing evidence. |
| 2026-10-14 | FE9-SYS-188–189 | Two Laguz gaps closed; reviewed | No blocking gap recorded | No | Full DOL call/pointer census proves gauge stepping exists only in the two post-action callbacks and damage in one damage-event path, with no phase writer. Script handlers toggle the paired class and reset raw gauge to 0/20; save fields, all class-backed getters, Demi Band's six-stat exception, persistent innate weapon setup, growth ownership, and map/full model fallbacks now close both lifecycles. |
| 2026-10-14 | FE9-SYS-377 | RNG ownership gap closed; reviewed | No blocking gap recorded | No | Direct-call and SDA-access censuses separate the unsaved three-halfword gameplay stream from the one-word visual stream, enumerate their consumer families, prove `main` is the sole seeding owner, and establish that save, checkpoint, Suspend, retry, load, and script snapshots neither serialize nor reseed either stream. |
| 2026-10-14 | FE9-SYS-375 | Logging/assertion gap closed; reviewed | No blocking gap recorded | No | Three-build call and body censuses prove the ordinary game printer is a byte-identical zero-returning no-op (432/430/427 calls), the 57-site engine assertion wrapper enters a distinct framebuffer/input/reset handler, and the 95-call SDK `OSReport` path remains active through `vprintf`. TRK is not a sink for any path; environment-specific live capture remains explicitly owned by FE9-SYS-014. |
| 2026-10-14 | FE9-SYS-382 | Serialization-boundary gap closed; reviewed | No blocking gap recorded | No | The fully decoded `SYSF` plus `BMST`/`MDST`/`UNIP`/`SOKO`/`FWEP`/`T  T` stream and `GameController` resume labels now provide a field-family lifetime matrix for base, preparations, multipart continuation, checkpoint/Suspend, new chapter, post-clear, trial, retry, and ordinary load. Unsaved runtime/presentation state and RAM-only `AllPush` state are explicitly separated. |
| 2026-10-14 | FE9-SYS-384 | Simulation/presentation gap closed; reviewed | No blocking gap recorded | No | A cross-system producer/consumer and control-flow audit covers combat, EXP/rewards, scripted unit changes, dialogue/choices, cutscenes/media, map objects/cameras, audio, and effects. Normal, map/full, animation-off, accelerated, instant, and skipped routes differ only in transient presentation while rejoining the same authoritative mutation and continuation boundary. |
| 2026-10-14 | FE9-SYS-378 | Rule-priority gap closed; reviewed | No blocking gap recorded | No | A ten-owner matrix now orders build/content selection, legality, topology, AI, exchange construction, strike formulas, item/status effects, progression, objective consequences, and persistence/presentation. Gates, suppressors, modifiers, clamps, replacements, commits, and owner-to-owner handoffs are explicit without inventing a global override manager. |
| 2026-10-14 | FE9-SYS-010 | Frame-scheduler gap closed; reviewed | No blocking gap recorded | No | Direct decompilation of `main`, the recursive process dispatcher, input tick, frame counter, and all 258 `start_process` call sites establishes render-first main-thread order, queue phases 5→6→7 then input then 2→3→4, root/child traversal, display-suppressed behavior, and asynchronous audio ownership. |

### Remaining research program (7 reviewed gaps)

The inventory has no pending or uncovered entry, but the following reviewed systems still lack evidence. They must remain open until the named research is completed.

| Primary article | Inventory IDs | Evidence still needed | New primary article? |
|---|---|---|---|
| [Runtime Engine Architecture](../systems/runtime-engine-architecture.md) | FE9-SYS-009, 011–012 | Allocation/ownership census; process-tree transitions; writable-global ownership. | No |
| [Difficulty Modes & Regional Builds](../systems/difficulty-and-regions.md) | FE9-SYS-013, 025, 381 | Controlled Japanese/US/PAL matrix for menu/internal modes, resources, formula consumers, overrides, and non-destructive save-format/conversion comparison. | No |
| [Crash, Assertions & Diagnostic Output](../systems/crash-assertions-diagnostics.md) | FE9-SYS-014 | Safe isolated failure fixtures and controlled Dolphin/retail-hardware capture for active `OSReport`, assertion-screen, panic, and exception paths. | No |

No additional primary article is currently justified. Each gap has an existing owner and a concrete evidence checklist; a new appendix should be created only when the corresponding raw matrix or census exists.

## Coverage dashboard

<!-- SYSTEM_REVIEW_REPORT_START -->

_Generated by `python App/tools/review_systems.py --write-report`; do not edit this block by hand._

| State | Count |
|---|---:|
| Reviewed | 381 |
| Reviewed with gaps | 3 |
| Covered, review pending | 0 |
| Uncovered | 0 |

| Inventory ID | System | Review state | Covering article(s) |
|---|---|---|---|
| [FE9-SYS-001](game-systems-inventory.md#fe9-sys-001) | GameCube boot and apploader | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-002](game-systems-inventory.md#fe9-sys-002) | DOL section and address mapping | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-003](game-systems-inventory.md#fe9-sys-003) | Disc filesystem and path lookup | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-004](game-systems-inventory.md#fe9-sys-004) | Archive-first resource lookup | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-005](game-systems-inventory.md#fe9-sys-005) | Compression and decompression | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-006](game-systems-inventory.md#fe9-sys-006) | Pack/archive mounting | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-007](game-systems-inventory.md#fe9-sys-007) | Labeled-section data loading | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-008](game-systems-inventory.md#fe9-sys-008) | Runtime resource registry | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-009](game-systems-inventory.md#fe9-sys-009) | Memory allocation and object lifetime | reviewed with gaps | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-010](game-systems-inventory.md#fe9-sys-010) | Frame scheduler and game loop | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-011](game-systems-inventory.md#fe9-sys-011) | Scene/state machine | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-012](game-systems-inventory.md#fe9-sys-012) | Global service and singleton state | reviewed with gaps | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-013](game-systems-inventory.md#fe9-sys-013) | Region and revision handling | reviewed | [difficulty-and-regions](../systems/difficulty-and-regions.md) |
| [FE9-SYS-014](game-systems-inventory.md#fe9-sys-014) | Crash, assertion, and debug output | reviewed with gaps | [crash-assertions-diagnostics](../systems/crash-assertions-diagnostics.md), [developer-debug-tools](../systems/developer-debug-tools.md) |
| [FE9-SYS-015](game-systems-inventory.md#fe9-sys-015) | Core database loading | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-016](game-systems-inventory.md#fe9-sys-016) | Character definition system | reviewed | [characters](../systems/characters.md) |
| [FE9-SYS-017](game-systems-inventory.md#fe9-sys-017) | Class definition system | reviewed | [classes](../systems/classes.md) |
| [FE9-SYS-018](game-systems-inventory.md#fe9-sys-018) | Runtime unit construction | reviewed | [characters](../systems/characters.md) |
| [FE9-SYS-019](game-systems-inventory.md#fe9-sys-019) | Unit-slot and army-list management | reviewed | [characters](../systems/characters.md) |
| [FE9-SYS-020](game-systems-inventory.md#fe9-sys-020) | Unit-state flags | reviewed | [characters](../systems/characters.md) |
| [FE9-SYS-021](game-systems-inventory.md#fe9-sys-021) | Army and allegiance system | reviewed | [armies-allegiance](../systems/armies-allegiance.md) |
| [FE9-SYS-022](game-systems-inventory.md#fe9-sys-022) | Commander and group system | reviewed | [armies-allegiance](../systems/armies-allegiance.md) |
| [FE9-SYS-023](game-systems-inventory.md#fe9-sys-023) | Identifier and label resolution | reviewed | [engine-resource-loading](../systems/engine-resource-loading.md) |
| [FE9-SYS-024](game-systems-inventory.md#fe9-sys-024) | Mutable party state | reviewed | [characters](../systems/characters.md) |
| [FE9-SYS-025](game-systems-inventory.md#fe9-sys-025) | Difficulty profile | reviewed | [difficulty-and-regions](../systems/difficulty-and-regions.md) |
| [FE9-SYS-026](game-systems-inventory.md#fe9-sys-026) | New-game initialization | reviewed | [campaign-flow](../systems/campaign-flow.md) |
| [FE9-SYS-027](game-systems-inventory.md#fe9-sys-027) | Campaign ordering | reviewed | [campaign-flow](../systems/campaign-flow.md) |
| [FE9-SYS-028](game-systems-inventory.md#fe9-sys-028) | Chapter lifecycle | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-029](game-systems-inventory.md#fe9-sys-029) | Multi-part chapter handling | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-030](game-systems-inventory.md#fe9-sys-030) | Hub/base chapter routing | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-031](game-systems-inventory.md#fe9-sys-031) | Chapter record system | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-032](game-systems-inventory.md#fe9-sys-032) | Chapter-local state reset | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-033](game-systems-inventory.md#fe9-sys-033) | Checkpoint/resume routing | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-034](game-systems-inventory.md#fe9-sys-034) | Victory recognition | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-035](game-systems-inventory.md#fe9-sys-035) | Defeat recognition | reviewed | [chapters](../systems/chapters.md), [objectives](../systems/objectives.md) |
| [FE9-SYS-036](game-systems-inventory.md#fe9-sys-036) | Endgame and ending selection | reviewed | [chapters](../systems/chapters.md), [endings](../systems/endings.md) |
| [FE9-SYS-037](game-systems-inventory.md#fe9-sys-037) | Trial-map campaign flow | reviewed | [chapters](../systems/chapters.md) |
| [FE9-SYS-038](game-systems-inventory.md#fe9-sys-038) | Event bytecode virtual machine | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-039](game-systems-inventory.md#fe9-sys-039) | FE9 script source and compilation | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-040](game-systems-inventory.md#fe9-sys-040) | Script entry-point registry | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-041](game-systems-inventory.md#fe9-sys-041) | Native script-call bridge | reviewed | [events-scripting](../systems/events-scripting.md), [script-functions](../systems/script-functions.md) |
| [FE9-SYS-042](game-systems-inventory.md#fe9-sys-042) | Blocking and asynchronous script execution | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-043](game-systems-inventory.md#fe9-sys-043) | Event trigger evaluation | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-044](game-systems-inventory.md#fe9-sys-044) | Global event flags | reviewed | [event-flags](../systems/event-flags.md) |
| [FE9-SYS-045](game-systems-inventory.md#fe9-sys-045) | Chapter event flags | reviewed | [event-flags](../systems/event-flags.md) |
| [FE9-SYS-046](game-systems-inventory.md#fe9-sys-046) | Flag serialization and reset policy | reviewed | [event-flags](../systems/event-flags.md) |
| [FE9-SYS-047](game-systems-inventory.md#fe9-sys-047) | Area-event system | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-048](game-systems-inventory.md#fe9-sys-048) | Turn/phase event system | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-049](game-systems-inventory.md#fe9-sys-049) | Talk and recruitment events | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-050](game-systems-inventory.md#fe9-sys-050) | Death and retreat events | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-051](game-systems-inventory.md#fe9-sys-051) | Scripted battle system | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-052](game-systems-inventory.md#fe9-sys-052) | Scripted unit manipulation | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-053](game-systems-inventory.md#fe9-sys-053) | Script timing system | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-054](game-systems-inventory.md#fe9-sys-054) | Event skip/fast-forward | reviewed | [events-scripting](../systems/events-scripting.md) |
| [FE9-SYS-055](game-systems-inventory.md#fe9-sys-055) | Map loading and composition | reviewed | [maps-system](../systems/maps-system.md) |
| [FE9-SYS-056](game-systems-inventory.md#fe9-sys-056) | Tile coordinate system | reviewed | [map-grid](../systems/map-grid.md), [maps-system](../systems/maps-system.md) |
| [FE9-SYS-057](game-systems-inventory.md#fe9-sys-057) | Terrain-type system | reviewed | [maps-system](../systems/maps-system.md) |
| [FE9-SYS-058](game-systems-inventory.md#fe9-sys-058) | Movement-type system | reviewed | [maps-system](../systems/maps-system.md) |
| [FE9-SYS-059](game-systems-inventory.md#fe9-sys-059) | Map link/passability grid | reviewed | [map-grid](../systems/map-grid.md), [maps-system](../systems/maps-system.md) |
| [FE9-SYS-060](game-systems-inventory.md#fe9-sys-060) | Pathfinding | reviewed | [maps-system](../systems/maps-system.md) |
| [FE9-SYS-061](game-systems-inventory.md#fe9-sys-061) | Occupancy and collision | reviewed | [maps-system](../systems/maps-system.md) |
| [FE9-SYS-062](game-systems-inventory.md#fe9-sys-062) | Movement-range display | reviewed | [maps-system](../systems/maps-system.md), [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-063](game-systems-inventory.md#fe9-sys-063) | Attack/staff range display | reviewed | [maps-system](../systems/maps-system.md), [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-064](game-systems-inventory.md#fe9-sys-064) | Threat-range display | reviewed | [maps-system](../systems/maps-system.md), [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-065](game-systems-inventory.md#fe9-sys-065) | Map cursor system | reviewed | [maps-system](../systems/maps-system.md), [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-066](game-systems-inventory.md#fe9-sys-066) | Map camera system | reviewed | [map-camera](../systems/map-camera.md), [maps-system](../systems/maps-system.md) |
| [FE9-SYS-067](game-systems-inventory.md#fe9-sys-067) | Map height and terrain conformance | reviewed | [map-grid](../systems/map-grid.md), [maps-system](../systems/maps-system.md) |
| [FE9-SYS-068](game-systems-inventory.md#fe9-sys-068) | Map-object system | reviewed | [map-objects](../systems/map-objects.md) |
| [FE9-SYS-069](game-systems-inventory.md#fe9-sys-069) | Persistent tile-object state | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-070](game-systems-inventory.md#fe9-sys-070) | Door and key system | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-071](game-systems-inventory.md#fe9-sys-071) | Chest system | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-072](game-systems-inventory.md#fe9-sys-072) | Village/house visit system | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-073](game-systems-inventory.md#fe9-sys-073) | Breakable-wall/building system | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-074](game-systems-inventory.md#fe9-sys-074) | Bridge and map-state transformation | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-075](game-systems-inventory.md#fe9-sys-075) | Ballista and siege-object system | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-076](game-systems-inventory.md#fe9-sys-076) | Hidden-item system | reviewed | [map-actions](../systems/map-actions.md), [map-objects](../systems/map-objects.md) |
| [FE9-SYS-077](game-systems-inventory.md#fe9-sys-077) | Fog-of-war system | reviewed | [maps-system](../systems/maps-system.md) |
| [FE9-SYS-078](game-systems-inventory.md#fe9-sys-078) | Roof/interior visibility system | reviewed | [maps-system](../systems/maps-system.md) |
| [FE9-SYS-079](game-systems-inventory.md#fe9-sys-079) | Weather system | reviewed | [maps-system](../systems/maps-system.md), [weather](../systems/weather.md) |
| [FE9-SYS-080](game-systems-inventory.md#fe9-sys-080) | Lighting and ambience system | reviewed | [maps-system](../systems/maps-system.md), [weather](../systems/weather.md) |
| [FE9-SYS-081](game-systems-inventory.md#fe9-sys-081) | Terrain texture blending | reviewed | [map-objects](../systems/map-objects.md), [terrain-texture-rendering](../systems/terrain-texture-rendering.md) |
| [FE9-SYS-082](game-systems-inventory.md#fe9-sys-082) | Water and animated environment | reviewed | [map-objects](../systems/map-objects.md) |
| [FE9-SYS-083](game-systems-inventory.md#fe9-sys-083) | Turn counter | reviewed | [turn-phase-action-cycle](../systems/turn-phase-action-cycle.md) |
| [FE9-SYS-084](game-systems-inventory.md#fe9-sys-084) | Army-phase order | reviewed | [turn-phase-action-cycle](../systems/turn-phase-action-cycle.md) |
| [FE9-SYS-085](game-systems-inventory.md#fe9-sys-085) | Phase initialization | reviewed | [turn-phase-action-cycle](../systems/turn-phase-action-cycle.md) |
| [FE9-SYS-086](game-systems-inventory.md#fe9-sys-086) | Unit action state | reviewed | [turn-phase-action-cycle](../systems/turn-phase-action-cycle.md) |
| [FE9-SYS-087](game-systems-inventory.md#fe9-sys-087) | Wait command | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-088](game-systems-inventory.md#fe9-sys-088) | Canto/post-action movement | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-089](game-systems-inventory.md#fe9-sys-089) | Rescue/carry system | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-090](game-systems-inventory.md#fe9-sys-090) | Drop system | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-091](game-systems-inventory.md#fe9-sys-091) | Take/Give system | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-092](game-systems-inventory.md#fe9-sys-092) | Shove system | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-093](game-systems-inventory.md#fe9-sys-093) | Smite system | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-094](game-systems-inventory.md#fe9-sys-094) | Trade system | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-095](game-systems-inventory.md#fe9-sys-095) | Supply/convoy access on map | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-096](game-systems-inventory.md#fe9-sys-096) | Item-use command | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-097](game-systems-inventory.md#fe9-sys-097) | Equip command and auto-equip | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-098](game-systems-inventory.md#fe9-sys-098) | Talk command | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-099](game-systems-inventory.md#fe9-sys-099) | Visit/Open/Chest/Seize/Arrive/Escape command family | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-100](game-systems-inventory.md#fe9-sys-100) | Order/command system for partner units | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-101](game-systems-inventory.md#fe9-sys-101) | End Turn | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-102](game-systems-inventory.md#fe9-sys-102) | Action menu construction | reviewed | [map-actions](../systems/map-actions.md) |
| [FE9-SYS-103](game-systems-inventory.md#fe9-sys-103) | Objective definition and display | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-104](game-systems-inventory.md#fe9-sys-104) | Rout | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-105](game-systems-inventory.md#fe9-sys-105) | Defeat boss | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-106](game-systems-inventory.md#fe9-sys-106) | Seize | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-107](game-systems-inventory.md#fe9-sys-107) | Arrive | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-108](game-systems-inventory.md#fe9-sys-108) | Escape | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-109](game-systems-inventory.md#fe9-sys-109) | Defend/survive | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-110](game-systems-inventory.md#fe9-sys-110) | Protect unit/position | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-111](game-systems-inventory.md#fe9-sys-111) | Multi-stage objectives | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-112](game-systems-inventory.md#fe9-sys-112) | Optional objective tracking | reviewed | [objectives](../systems/objectives.md) |
| [FE9-SYS-113](game-systems-inventory.md#fe9-sys-113) | Target selection | reviewed | [battle-forecast](../systems/battle-forecast.md) |
| [FE9-SYS-114](game-systems-inventory.md#fe9-sys-114) | Weapon selection | reviewed | [battle-forecast](../systems/battle-forecast.md) |
| [FE9-SYS-115](game-systems-inventory.md#fe9-sys-115) | Defender weapon selection | reviewed | [battle-forecast](../systems/battle-forecast.md) |
| [FE9-SYS-116](game-systems-inventory.md#fe9-sys-116) | Battle forecast | reviewed | [battle-forecast](../systems/battle-forecast.md) |
| [FE9-SYS-117](game-systems-inventory.md#fe9-sys-117) | Attack Speed | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-118](game-systems-inventory.md#fe9-sys-118) | Physical weapon triangle | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-119](game-systems-inventory.md#fe9-sys-119) | Trinity of Magic | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-120](game-systems-inventory.md#fe9-sys-120) | Weapon rank and access | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-121](game-systems-inventory.md#fe9-sys-121) | Range system | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-122](game-systems-inventory.md#fe9-sys-122) | Effectiveness system | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-123](game-systems-inventory.md#fe9-sys-123) | Blessed-armor protection | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-124](game-systems-inventory.md#fe9-sys-124) | Support/bond proximity bonuses | reviewed | [combat-mechanics](../systems/combat-mechanics.md), [support-system](../systems/support-system.md) |
| [FE9-SYS-125](game-systems-inventory.md#fe9-sys-125) | Terrain combat bonuses | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-126](game-systems-inventory.md#fe9-sys-126) | Biorhythm combat modifier | reviewed | [biorhythm](../systems/biorhythm.md), [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-127](game-systems-inventory.md#fe9-sys-127) | Status and temporary-stat modifiers | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-128](game-systems-inventory.md#fe9-sys-128) | Battle RNG service | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-129](game-systems-inventory.md#fe9-sys-129) | Two-RN/True Hit | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-130](game-systems-inventory.md#fe9-sys-130) | Exchange-order construction | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-131](game-systems-inventory.md#fe9-sys-131) | Follow-up/doubling | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-132](game-systems-inventory.md#fe9-sys-132) | Multi-strike/Brave behavior | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-133](game-systems-inventory.md#fe9-sys-133) | Hit calculation | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-134](game-systems-inventory.md#fe9-sys-134) | Avoid calculation | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-135](game-systems-inventory.md#fe9-sys-135) | Critical calculation | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-136](game-systems-inventory.md#fe9-sys-136) | Critical damage | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-137](game-systems-inventory.md#fe9-sys-137) | Physical damage | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-138](game-systems-inventory.md#fe9-sys-138) | Magical damage | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-139](game-systems-inventory.md#fe9-sys-139) | Magic-weapon behavior | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-140](game-systems-inventory.md#fe9-sys-140) | Minimum/zero damage policy | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-141](game-systems-inventory.md#fe9-sys-141) | Counterattack eligibility | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-142](game-systems-inventory.md#fe9-sys-142) | Weapon durability consumption | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-143](game-systems-inventory.md#fe9-sys-143) | On-hit weapon properties | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-144](game-systems-inventory.md#fe9-sys-144) | Skill activation pipeline | reviewed | [combat-mechanics](../systems/combat-mechanics.md), [skills](../systems/skills.md) |
| [FE9-SYS-145](game-systems-inventory.md#fe9-sys-145) | Offensive proc skills | reviewed | [combat-mechanics](../systems/combat-mechanics.md), [skills](../systems/skills.md) |
| [FE9-SYS-146](game-systems-inventory.md#fe9-sys-146) | Defensive/reactive skills | reviewed | [combat-mechanics](../systems/combat-mechanics.md), [skills](../systems/skills.md) |
| [FE9-SYS-147](game-systems-inventory.md#fe9-sys-147) | Conditional passive skills | reviewed | [combat-mechanics](../systems/combat-mechanics.md), [skills](../systems/skills.md) |
| [FE9-SYS-148](game-systems-inventory.md#fe9-sys-148) | Post-hit healing and reflection | reviewed | [combat-mechanics](../systems/combat-mechanics.md), [skills](../systems/skills.md) |
| [FE9-SYS-149](game-systems-inventory.md#fe9-sys-149) | Death resolution | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-150](game-systems-inventory.md#fe9-sys-150) | Dropped-item transfer | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-151](game-systems-inventory.md#fe9-sys-151) | Combat statistics tracking | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-152](game-systems-inventory.md#fe9-sys-152) | Battle EXP calculation | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-153](game-systems-inventory.md#fe9-sys-153) | EXP bar and level transition | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-154](game-systems-inventory.md#fe9-sys-154) | Battle-result handoff | reviewed | [combat-mechanics](../systems/combat-mechanics.md) |
| [FE9-SYS-155](game-systems-inventory.md#fe9-sys-155) | Map-versus-full battle selection | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-156](game-systems-inventory.md#fe9-sys-156) | Battle staging | reviewed | [battle-staging](../systems/battle-staging.md) |
| [FE9-SYS-157](game-systems-inventory.md#fe9-sys-157) | Battle scenery selection | reviewed | [battle-staging](../systems/battle-staging.md) |
| [FE9-SYS-158](game-systems-inventory.md#fe9-sys-158) | Class/model selection | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-159](game-systems-inventory.md#fe9-sys-159) | Weapon-model selection | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-160](game-systems-inventory.md#fe9-sys-160) | Battle animation state machine | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-161](game-systems-inventory.md#fe9-sys-161) | Animation-event system | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-162](game-systems-inventory.md#fe9-sys-162) | Battle camera scripting | reviewed | [battle-staging](../systems/battle-staging.md) |
| [FE9-SYS-163](game-systems-inventory.md#fe9-sys-163) | Spell and particle effects | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-164](game-systems-inventory.md#fe9-sys-164) | Battle HUD | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-165](game-systems-inventory.md#fe9-sys-165) | Damage-number and hit-effect presentation | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-166](game-systems-inventory.md#fe9-sys-166) | Battle music and stingers | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-167](game-systems-inventory.md#fe9-sys-167) | Map battle animation | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-168](game-systems-inventory.md#fe9-sys-168) | Battle animation skip/acceleration | reviewed | [combat-animation](../systems/combat-animation.md) |
| [FE9-SYS-169](game-systems-inventory.md#fe9-sys-169) | Level and EXP progression | reviewed | [level-up-growth](../systems/level-up-growth.md) |
| [FE9-SYS-170](game-systems-inventory.md#fe9-sys-170) | Random level-up growth | reviewed | [level-up-growth](../systems/level-up-growth.md) |
| [FE9-SYS-171](game-systems-inventory.md#fe9-sys-171) | Fixed growth mode | reviewed | [level-up-growth](../systems/level-up-growth.md) |
| [FE9-SYS-172](game-systems-inventory.md#fe9-sys-172) | Stat caps | reviewed | [level-up-growth](../systems/level-up-growth.md) |
| [FE9-SYS-173](game-systems-inventory.md#fe9-sys-173) | Derived-stat system | reviewed | [classes](../systems/classes.md) |
| [FE9-SYS-174](game-systems-inventory.md#fe9-sys-174) | Promotion eligibility | reviewed | [classes](../systems/classes.md) |
| [FE9-SYS-175](game-systems-inventory.md#fe9-sys-175) | Promotion execution | reviewed | [classes](../systems/classes.md) |
| [FE9-SYS-176](game-systems-inventory.md#fe9-sys-176) | Story promotion | reviewed | [classes](../systems/classes.md) |
| [FE9-SYS-177](game-systems-inventory.md#fe9-sys-177) | Promotion weapon choice | reviewed | [classes](../systems/classes.md) |
| [FE9-SYS-178](game-systems-inventory.md#fe9-sys-178) | Weapon experience and rank growth | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-179](game-systems-inventory.md#fe9-sys-179) | Skill capacity | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-180](game-systems-inventory.md#fe9-sys-180) | Skill scroll learning/removal | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-181](game-systems-inventory.md#fe9-sys-181) | Occult/mastery assignment | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-182](game-systems-inventory.md#fe9-sys-182) | Stat-booster and permanent bonus system | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-183](game-systems-inventory.md#fe9-sys-183) | Bond system | reviewed | [support-system](../systems/support-system.md) |
| [FE9-SYS-184](game-systems-inventory.md#fe9-sys-184) | Support progression | reviewed | [support-system](../systems/support-system.md) |
| [FE9-SYS-185](game-systems-inventory.md#fe9-sys-185) | Support conversation availability | reviewed | [support-system](../systems/support-system.md) |
| [FE9-SYS-186](game-systems-inventory.md#fe9-sys-186) | Support battle bonuses | reviewed | [support-system](../systems/support-system.md) |
| [FE9-SYS-187](game-systems-inventory.md#fe9-sys-187) | Biorhythm progression | reviewed | [biorhythm](../systems/biorhythm.md) |
| [FE9-SYS-188](game-systems-inventory.md#fe9-sys-188) | Laguz transformation gauge | reviewed | [laguz-transformation](../systems/laguz-transformation.md) |
| [FE9-SYS-189](game-systems-inventory.md#fe9-sys-189) | Laguz transformed-stat system | reviewed | [laguz-transformation](../systems/laguz-transformation.md) |
| [FE9-SYS-190](game-systems-inventory.md#fe9-sys-190) | Item-definition system | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-191](game-systems-inventory.md#fe9-sys-191) | Item-instance system | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-192](game-systems-inventory.md#fe9-sys-192) | Personal inventory | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-193](game-systems-inventory.md#fe9-sys-193) | Convoy/warehouse | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-194](game-systems-inventory.md#fe9-sys-194) | Item legality/restriction system | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-195](game-systems-inventory.md#fe9-sys-195) | Durability and breaking | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-196](game-systems-inventory.md#fe9-sys-196) | Consumable effect system | reviewed | [items-weapons](../systems/items-weapons.md) |
| [FE9-SYS-197](game-systems-inventory.md#fe9-sys-197) | Gold economy | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-198](game-systems-inventory.md#fe9-sys-198) | Armory system | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-199](game-systems-inventory.md#fe9-sys-199) | Vendor system | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-200](game-systems-inventory.md#fe9-sys-200) | Sell shop | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-201](game-systems-inventory.md#fe9-sys-201) | Per-chapter shop stock | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-202](game-systems-inventory.md#fe9-sys-202) | Forge availability | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-203](game-systems-inventory.md#fe9-sys-203) | Forge stat customization | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-204](game-systems-inventory.md#fe9-sys-204) | Forge appearance customization | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-205](game-systems-inventory.md#fe9-sys-205) | Forge price calculation | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-206](game-systems-inventory.md#fe9-sys-206) | Forge-record pool | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-207](game-systems-inventory.md#fe9-sys-207) | Treasure and reward routing | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-208](game-systems-inventory.md#fe9-sys-208) | Bonus EXP award calculation | reviewed | [bonus-experience](../systems/bonus-experience.md) |
| [FE9-SYS-209](game-systems-inventory.md#fe9-sys-209) | Turn-efficiency BEXP | reviewed | [bonus-experience](../systems/bonus-experience.md) |
| [FE9-SYS-210](game-systems-inventory.md#fe9-sys-210) | Objective BEXP | reviewed | [bonus-experience](../systems/bonus-experience.md) |
| [FE9-SYS-211](game-systems-inventory.md#fe9-sys-211) | BEXP pool accounting | reviewed | [bonus-experience](../systems/bonus-experience.md) |
| [FE9-SYS-212](game-systems-inventory.md#fe9-sys-212) | BEXP distribution | reviewed | [bonus-experience](../systems/bonus-experience.md) |
| [FE9-SYS-213](game-systems-inventory.md#fe9-sys-213) | BEXP breakdown display | reviewed | [bonus-experience](../systems/bonus-experience.md) |
| [FE9-SYS-214](game-systems-inventory.md#fe9-sys-214) | Soren's Battle Report | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-215](game-systems-inventory.md#fe9-sys-215) | Report-counter lifecycle | reviewed | [economy](../systems/economy.md) |
| [FE9-SYS-216](game-systems-inventory.md#fe9-sys-216) | MVP selection | reviewed | [battle-reports-records](../systems/battle-reports-records.md) |
| [FE9-SYS-217](game-systems-inventory.md#fe9-sys-217) | Per-unit records | reviewed | [battle-reports-records](../systems/battle-reports-records.md) |
| [FE9-SYS-218](game-systems-inventory.md#fe9-sys-218) | Chapter clear history | reviewed | [battle-reports-records](../systems/battle-reports-records.md) |
| [FE9-SYS-219](game-systems-inventory.md#fe9-sys-219) | Play-time tracking | reviewed | [battle-reports-records](../systems/battle-reports-records.md) |
| [FE9-SYS-220](game-systems-inventory.md#fe9-sys-220) | Completion records | reviewed | [battle-reports-records](../systems/battle-reports-records.md) |
| [FE9-SYS-221](game-systems-inventory.md#fe9-sys-221) | Healing staff resolution | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-222](game-systems-inventory.md#fe9-sys-222) | Status staff accuracy | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-223](game-systems-inventory.md#fe9-sys-223) | Restore system | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-224](game-systems-inventory.md#fe9-sys-224) | Ward/Barrier/Pure Water system | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-225](game-systems-inventory.md#fe9-sys-225) | Rescue staff | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-226](game-systems-inventory.md#fe9-sys-226) | Warp staff | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-227](game-systems-inventory.md#fe9-sys-227) | Hammerne repair | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-228](game-systems-inventory.md#fe9-sys-228) | Torch and vision effects | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-229](game-systems-inventory.md#fe9-sys-229) | Unlock staff/skill | reviewed | [staves](../systems/staves.md) |
| [FE9-SYS-230](game-systems-inventory.md#fe9-sys-230) | Poison status | reviewed | [status-effects](../systems/status-effects.md) |
| [FE9-SYS-231](game-systems-inventory.md#fe9-sys-231) | Sleep status | reviewed | [status-effects](../systems/status-effects.md) |
| [FE9-SYS-232](game-systems-inventory.md#fe9-sys-232) | Silence status | reviewed | [status-effects](../systems/status-effects.md) |
| [FE9-SYS-233](game-systems-inventory.md#fe9-sys-233) | Berserk status | reviewed | [status-effects](../systems/status-effects.md) |
| [FE9-SYS-234](game-systems-inventory.md#fe9-sys-234) | Temporary status lifecycle | reviewed | [status-effects](../systems/status-effects.md) |
| [FE9-SYS-235](game-systems-inventory.md#fe9-sys-235) | Terrain healing | reviewed | [status-effects](../systems/status-effects.md) |
| [FE9-SYS-236](game-systems-inventory.md#fe9-sys-236) | Skill ownership bitset | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-237](game-systems-inventory.md#fe9-sys-237) | Skill availability and restrictions | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-238](game-systems-inventory.md#fe9-sys-238) | Skill activation chance | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-239](game-systems-inventory.md#fe9-sys-239) | Steal | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-240](game-systems-inventory.md#fe9-sys-240) | Chant | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-241](game-systems-inventory.md#fe9-sys-241) | Canto | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-242](game-systems-inventory.md#fe9-sys-242) | Shove/Smite | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-243](game-systems-inventory.md#fe9-sys-243) | Blossom and Paragon | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-244](game-systems-inventory.md#fe9-sys-244) | Tempest and Serenity | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-245](game-systems-inventory.md#fe9-sys-245) | Parity and Nihil | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-246](game-systems-inventory.md#fe9-sys-246) | Resolve and Wrath | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-247](game-systems-inventory.md#fe9-sys-247) | Provoke/Shade-style AI influence | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-248](game-systems-inventory.md#fe9-sys-248) | Charisma and Horror auras | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-249](game-systems-inventory.md#fe9-sys-249) | Blessing/Boon and laguz support skills | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-250](game-systems-inventory.md#fe9-sys-250) | Engine-trait skills | reviewed | [skills](../systems/skills.md) |
| [FE9-SYS-251](game-systems-inventory.md#fe9-sys-251) | AI phase scheduler | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-252](game-systems-inventory.md#fe9-sys-252) | AI bytecode/interpreter | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-253](game-systems-inventory.md#fe9-sys-253) | AI group/order assignment | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-254](game-systems-inventory.md#fe9-sys-254) | Target enumeration | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-255](game-systems-inventory.md#fe9-sys-255) | Attack scoring | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-256](game-systems-inventory.md#fe9-sys-256) | Movement scoring | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-257](game-systems-inventory.md#fe9-sys-257) | Per-unit threat map | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-258](game-systems-inventory.md#fe9-sys-258) | Phase danger map | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-259](game-systems-inventory.md#fe9-sys-259) | Aggro/activation zones | reviewed | [ai-activation-and-orders](../systems/ai-activation-and-orders.md) |
| [FE9-SYS-260](game-systems-inventory.md#fe9-sys-260) | Route and patrol AI | reviewed | [ai-activation-and-orders](../systems/ai-activation-and-orders.md) |
| [FE9-SYS-261](game-systems-inventory.md#fe9-sys-261) | Boss/hold-position AI | reviewed | [ai-activation-and-orders](../systems/ai-activation-and-orders.md) |
| [FE9-SYS-262](game-systems-inventory.md#fe9-sys-262) | Escape AI | reviewed | [ai-activation-and-orders](../systems/ai-activation-and-orders.md) |
| [FE9-SYS-263](game-systems-inventory.md#fe9-sys-263) | Healing-need hysteresis | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-264](game-systems-inventory.md#fe9-sys-264) | Self-healing item AI | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-265](game-systems-inventory.md#fe9-sys-265) | Ally item borrowing | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-266](game-systems-inventory.md#fe9-sys-266) | Healing-terrain/refuge AI | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-267](game-systems-inventory.md#fe9-sys-267) | Healing staff AI | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-268](game-systems-inventory.md#fe9-sys-268) | Status/support staff AI | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-269](game-systems-inventory.md#fe9-sys-269) | Steal AI | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-270](game-systems-inventory.md#fe9-sys-270) | Chant AI | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-271](game-systems-inventory.md#fe9-sys-271) | Item-use AI | reviewed | [ai-healing-and-special-actions](../systems/ai-healing-and-special-actions.md) |
| [FE9-SYS-272](game-systems-inventory.md#fe9-sys-272) | Partner-unit orders | reviewed | [ai-activation-and-orders](../systems/ai-activation-and-orders.md) |
| [FE9-SYS-273](game-systems-inventory.md#fe9-sys-273) | Tie-breaking and scan order | reviewed | [ai-engine-and-scoring](../systems/ai-engine-and-scoring.md) |
| [FE9-SYS-274](game-systems-inventory.md#fe9-sys-274) | Base menu state | reviewed | [base-system](../systems/base-system.md) |
| [FE9-SYS-275](game-systems-inventory.md#fe9-sys-275) | Base Info conversations | reviewed | [base-system](../systems/base-system.md) |
| [FE9-SYS-276](game-systems-inventory.md#fe9-sys-276) | Support menu | reviewed | [base-system](../systems/base-system.md) |
| [FE9-SYS-277](game-systems-inventory.md#fe9-sys-277) | Manage/army organization | reviewed | [base-system](../systems/base-system.md) |
| [FE9-SYS-278](game-systems-inventory.md#fe9-sys-278) | Base BEXP allocation | reviewed | [bonus-experience](../systems/bonus-experience.md) |
| [FE9-SYS-279](game-systems-inventory.md#fe9-sys-279) | Base armory/vendor/sell shop | reviewed | [base-system](../systems/base-system.md) |
| [FE9-SYS-280](game-systems-inventory.md#fe9-sys-280) | Base forge | reviewed | [base-system](../systems/base-system.md) |
| [FE9-SYS-281](game-systems-inventory.md#fe9-sys-281) | Base warehouse | reviewed | [base-system](../systems/base-system.md) |
| [FE9-SYS-282](game-systems-inventory.md#fe9-sys-282) | Base report presentation | reviewed | [battle-reports-records](../systems/battle-reports-records.md) |
| [FE9-SYS-283](game-systems-inventory.md#fe9-sys-283) | Combat preparation screen | reviewed | [battle-preparations](../systems/battle-preparations.md) |
| [FE9-SYS-284](game-systems-inventory.md#fe9-sys-284) | Deployment limit and selection | reviewed | [battle-preparations](../systems/battle-preparations.md) |
| [FE9-SYS-285](game-systems-inventory.md#fe9-sys-285) | Starting-position assignment | reviewed | [battle-preparations](../systems/battle-preparations.md) |
| [FE9-SYS-286](game-systems-inventory.md#fe9-sys-286) | Preparation map inspection | reviewed | [battle-preparations](../systems/battle-preparations.md) |
| [FE9-SYS-287](game-systems-inventory.md#fe9-sys-287) | Preparation save | reviewed | [battle-preparations](../systems/battle-preparations.md) |
| [FE9-SYS-288](game-systems-inventory.md#fe9-sys-288) | Message lookup and localization | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-289](game-systems-inventory.md#fe9-sys-289) | Text decoding and control codes | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-290](game-systems-inventory.md#fe9-sys-290) | Conversation scene system | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-291](game-systems-inventory.md#fe9-sys-291) | Conversation context/inheritance | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-292](game-systems-inventory.md#fe9-sys-292) | Portrait selection and animation | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-293](game-systems-inventory.md#fe9-sys-293) | Dialogue text-box layout | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-294](game-systems-inventory.md#fe9-sys-294) | Dialogue input and auto-advance | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-295](game-systems-inventory.md#fe9-sys-295) | Choice/branching dialogue | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-296](game-systems-inventory.md#fe9-sys-296) | Map dialogue | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-297](game-systems-inventory.md#fe9-sys-297) | Base/support/death-quote dialogue | reviewed | [dialogue-engine](../systems/dialogue-engine.md) |
| [FE9-SYS-298](game-systems-inventory.md#fe9-sys-298) | World-map presentation | reviewed | [cutscenes](../systems/cutscenes.md) |
| [FE9-SYS-299](game-systems-inventory.md#fe9-sys-299) | Illustration/still-image scenes | reviewed | [cutscenes](../systems/cutscenes.md) |
| [FE9-SYS-300](game-systems-inventory.md#fe9-sys-300) | Real-time cutscene choreography | reviewed | [cutscenes](../systems/cutscenes.md) |
| [FE9-SYS-301](game-systems-inventory.md#fe9-sys-301) | Pre-rendered movie playback | reviewed | [cutscenes](../systems/cutscenes.md) |
| [FE9-SYS-302](game-systems-inventory.md#fe9-sys-302) | Ending-card system | reviewed | [endings](../systems/endings.md) |
| [FE9-SYS-303](game-systems-inventory.md#fe9-sys-303) | Staff credits | reviewed | [cutscenes](../systems/cutscenes.md) |
| [FE9-SYS-304](game-systems-inventory.md#fe9-sys-304) | Render pipeline | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-305](game-systems-inventory.md#fe9-sys-305) | Texture system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-306](game-systems-inventory.md#fe9-sys-306) | 2D sprite/UI compositor | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-307](game-systems-inventory.md#fe9-sys-307) | UI layout system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-308](game-systems-inventory.md#fe9-sys-308) | Font and glyph system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-309](game-systems-inventory.md#fe9-sys-309) | Icon atlas system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-310](game-systems-inventory.md#fe9-sys-310) | 3D model loading | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-311](game-systems-inventory.md#fe9-sys-311) | Material/render-state system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-312](game-systems-inventory.md#fe9-sys-312) | Skeleton and skinning | reviewed | [graphics-system](../systems/graphics-system.md), [posing](../systems/posing.md) |
| [FE9-SYS-313](game-systems-inventory.md#fe9-sys-313) | Animation-track evaluation | reviewed | [graphics-system](../systems/graphics-system.md), [posing](../systems/posing.md) |
| [FE9-SYS-314](game-systems-inventory.md#fe9-sys-314) | Map-model registry | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-315](game-systems-inventory.md#fe9-sys-315) | Model-slot and override system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-316](game-systems-inventory.md#fe9-sys-316) | Map-unit animation | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-317](game-systems-inventory.md#fe9-sys-317) | Posing system | reviewed | [posing](../systems/posing.md) |
| [FE9-SYS-318](game-systems-inventory.md#fe9-sys-318) | Effect registry | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-319](game-systems-inventory.md#fe9-sys-319) | Particle emitter system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-320](game-systems-inventory.md#fe9-sys-320) | Screen-transition system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-321](game-systems-inventory.md#fe9-sys-321) | Lens flare and post-effect system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-322](game-systems-inventory.md#fe9-sys-322) | Performance/culling system | reviewed | [graphics-system](../systems/graphics-system.md) |
| [FE9-SYS-323](game-systems-inventory.md#fe9-sys-323) | Music selection system | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-324](game-systems-inventory.md#fe9-sys-324) | Music transition system | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-325](game-systems-inventory.md#fe9-sys-325) | MusyX sequence/sample system | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-326](game-systems-inventory.md#fe9-sys-326) | Streamed audio system | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-327](game-systems-inventory.md#fe9-sys-327) | Sound-effect bank system | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-328](game-systems-inventory.md#fe9-sys-328) | Positional/attached sound | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-329](game-systems-inventory.md#fe9-sys-329) | Voice/utterance system | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-330](game-systems-inventory.md#fe9-sys-330) | Audio mixer/options | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-331](game-systems-inventory.md#fe9-sys-331) | THP video decoder | reviewed | [video-system](../systems/video-system.md) |
| [FE9-SYS-332](game-systems-inventory.md#fe9-sys-332) | Sound Room | reviewed | [music-system](../systems/music-system.md) |
| [FE9-SYS-333](game-systems-inventory.md#fe9-sys-333) | Controller input mapping | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-334](game-systems-inventory.md#fe9-sys-334) | Input focus and repeat | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-335](game-systems-inventory.md#fe9-sys-335) | Title and main menu | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-336](game-systems-inventory.md#fe9-sys-336) | File-select UI | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-337](game-systems-inventory.md#fe9-sys-337) | Map HUD | reviewed | [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-338](game-systems-inventory.md#fe9-sys-338) | Unit status screen | reviewed | [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-339](game-systems-inventory.md#fe9-sys-339) | Map command menu | reviewed | [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-340](game-systems-inventory.md#fe9-sys-340) | Unit command menu | reviewed | [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-341](game-systems-inventory.md#fe9-sys-341) | List and sorting system | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-342](game-systems-inventory.md#fe9-sys-342) | Help-text system | reviewed | [tactical-interface](../systems/tactical-interface.md) |
| [FE9-SYS-343](game-systems-inventory.md#fe9-sys-343) | Tutorial popup system | reviewed | [tutorial-browser](../systems/tutorial-browser.md) |
| [FE9-SYS-344](game-systems-inventory.md#fe9-sys-344) | Tutorial/Guide browser | reviewed | [tutorial-browser](../systems/tutorial-browser.md) |
| [FE9-SYS-345](game-systems-inventory.md#fe9-sys-345) | Options system | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-346](game-systems-inventory.md#fe9-sys-346) | Screen calibration | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-347](game-systems-inventory.md#fe9-sys-347) | Confirmation/error dialogs | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-348](game-systems-inventory.md#fe9-sys-348) | Pause/suspend flow | reviewed | [input-menus-and-options](../systems/input-menus-and-options.md) |
| [FE9-SYS-349](game-systems-inventory.md#fe9-sys-349) | Memory Card file management | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-350](game-systems-inventory.md#fe9-sys-350) | Save-block system | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-351](game-systems-inventory.md#fe9-sys-351) | Save serialization | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-352](game-systems-inventory.md#fe9-sys-352) | Load reconstruction | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-353](game-systems-inventory.md#fe9-sys-353) | Save integrity/versioning | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-354](game-systems-inventory.md#fe9-sys-354) | System-data replication | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-355](game-systems-inventory.md#fe9-sys-355) | Autosave/chapter-clear save | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-356](game-systems-inventory.md#fe9-sys-356) | Map/checkpoint save | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-357](game-systems-inventory.md#fe9-sys-357) | Base/preparation save | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-358](game-systems-inventory.md#fe9-sys-358) | Suspend save | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-359](game-systems-inventory.md#fe9-sys-359) | Save compatibility system | reviewed | [save-system](../systems/save-system.md) |
| [FE9-SYS-360](game-systems-inventory.md#fe9-sys-360) | Clear/unlock flags | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-361](game-systems-inventory.md#fe9-sys-361) | Playthrough-number system | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-362](game-systems-inventory.md#fe9-sys-362) | Trial Map unlocks | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-363](game-systems-inventory.md#fe9-sys-363) | Extras hub | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-364](game-systems-inventory.md#fe9-sys-364) | Movie Theater | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-365](game-systems-inventory.md#fe9-sys-365) | Illustration/character gallery | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-366](game-systems-inventory.md#fe9-sys-366) | Records viewer | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-367](game-systems-inventory.md#fe9-sys-367) | GBA link protocol | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-368](game-systems-inventory.md#fe9-sys-368) | GBA-link reward system | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-369](game-systems-inventory.md#fe9-sys-369) | Character-met tracking | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-370](game-systems-inventory.md#fe9-sys-370) | New-game-after-clear options | reviewed | [extras-and-unlocks](../systems/extras-and-unlocks.md) |
| [FE9-SYS-371](game-systems-inventory.md#fe9-sys-371) | Developer/debug menus | reviewed | [developer-debug-tools](../systems/developer-debug-tools.md) |
| [FE9-SYS-372](game-systems-inventory.md#fe9-sys-372) | Internal battle tool | reviewed | [developer-debug-tools](../systems/developer-debug-tools.md) |
| [FE9-SYS-373](game-systems-inventory.md#fe9-sys-373) | Chapter jump/test flow | reviewed | [developer-debug-tools](../systems/developer-debug-tools.md) |
| [FE9-SYS-374](game-systems-inventory.md#fe9-sys-374) | Resource viewers | reviewed | [developer-debug-tools](../systems/developer-debug-tools.md) |
| [FE9-SYS-375](game-systems-inventory.md#fe9-sys-375) | Logging and assertions | reviewed | [crash-assertions-diagnostics](../systems/crash-assertions-diagnostics.md), [developer-debug-tools](../systems/developer-debug-tools.md) |
| [FE9-SYS-376](game-systems-inventory.md#fe9-sys-376) | Build timestamps and author metadata | reviewed | [developer-debug-tools](../systems/developer-debug-tools.md) |
| [FE9-SYS-377](game-systems-inventory.md#fe9-sys-377) | Randomness ownership | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-378](game-systems-inventory.md#fe9-sys-378) | Rule priority/override system | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-379](game-systems-inventory.md#fe9-sys-379) | Legality-before-execution pattern | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-380](game-systems-inventory.md#fe9-sys-380) | Definition-instance-runtime separation | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-381](game-systems-inventory.md#fe9-sys-381) | Difficulty and region overrides | reviewed | [difficulty-and-regions](../systems/difficulty-and-regions.md) |
| [FE9-SYS-382](game-systems-inventory.md#fe9-sys-382) | Serialization boundary | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-383](game-systems-inventory.md#fe9-sys-383) | Script/native division of responsibility | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |
| [FE9-SYS-384](game-systems-inventory.md#fe9-sys-384) | Simulation/presentation separation | reviewed | [runtime-engine-architecture](../systems/runtime-engine-architecture.md) |

<!-- SYSTEM_REVIEW_REPORT_END -->
