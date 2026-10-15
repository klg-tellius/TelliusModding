---
id: "uncovered-systems-roadmap"
title: "Uncovered Systems Writing Roadmap"
description: "A dependency-ordered plan for giving every currently uncovered FE9 system a thorough explanatory article"
games: ["path-of-radiance"]
section: "meta"
article_type: "portal"
tags: ["Coverage", "Planning", "Contributing", "Review"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research", "telliusmodding-source", "path-of-radiance-us-manual"]
cms_collection: "meta"
source_path: "meta/uncovered-systems-roadmap.md"
---
# Uncovered Systems Writing Roadmap

This roadmap assigns all **148 systems that were uncovered at the 2026-10-13 review baseline** to 25 writing packages. A package is the smallest article-sized body of work that can teach a coherent subject: closely related inventory entries share an article, but every `FE9-SYS-NNN` ID must receive its own labeled section, evidence assessment, and review decision.

!!! success "Writing plan executed"
    All 25 packages now have destination articles and all 148 baseline IDs are claimed. The live dashboard reports **0 uncovered**. The remaining stage is technical and teaching review: claims must be checked, research gaps must be worked, and a second person must approve IDs individually before they move from **covered, review pending** to **reviewed** or **reviewed with gaps**.

The plan is ordered by prerequisites. It deliberately distinguishes **synthesis**—where reliable findings already exist in format pages, source code, or tests—from **focused trace** and **research-heavy** work that needs executable analysis or controlled in-game experiments. A stub does not count as filling a gap: an ID leaves “uncovered” when an article claims it, and reaches completion only after the article passes the [Game System Documentation Review](system-review.md).

## Definition of done for every package

A package is complete only when all of these are true:

1. Every assigned ID appears in the destination article's `system_entries` metadata and beside the exact section that explains it.
2. The article opens in plain language, supplies a mental model and worked example, and then covers inputs/state, ordered rules, outputs, interactions, edge cases, persistence, and modding consequences.
3. Claims identify their evidence trail: format fields, executable functions, script calls, tests, controlled observations, or official player documentation.
4. Regional and difficulty differences are stated or explicitly ruled out.
5. Known gaps record what was tried, what the attempt established, and the next useful experiment. Uninvestigated uncertainty is not review-ready.
6. Related format pages remain technical references; the system article explains how those pieces behave together rather than copying layouts.
7. A second person applies the review rubric, records reviewer/date metadata, and approves each ID separately.
8. `review_systems.py --write-report`, `review_systems.py --check`, and `validate_wiki.py` all pass.

## Work packages

| Package | Primary destination | Inventory IDs | Work type | Required result |
|---|---|---|---|---|
| P01 | New `engine-resource-loading.md` | FE9-SYS-001–008, FE9-SYS-015, FE9-SYS-023 | Synthesis + focused trace | Explain boot-to-resource flow, FST/archive precedence, compression/container layers, database initialization, and label resolution as one understandable pipeline. |
| P02 | New `runtime-engine-architecture.md` | FE9-SYS-009–012, FE9-SYS-377–380, FE9-SYS-382–384 | Research-heavy | Establish object lifetime, frame scheduling, scene ownership, global services, RNG ownership, rule priority, serialization boundaries, script/native responsibilities, and simulation/presentation separation. |
| P03 | New `difficulty-and-regions.md` | FE9-SYS-013, FE9-SYS-025, FE9-SYS-381 | Comparative synthesis | Separate localization from mechanical revision differences and map every difficulty/region override to its data or native owner. |
| P04 | Expand `developer-debug-tools.md` | FE9-SYS-014 | Synthesis | Add crash/assertion/debug-output behavior, retail remnants, logging destinations, and practical diagnostic value. |
| P05 | New `campaign-flow.md` | FE9-SYS-026, FE9-SYS-027 | Focused trace | Follow New Game initialization through chapter selection, next-chapter routing, alternate parts, ending, and trial-map diversion. |
| P06 | New `turn-phase-action-cycle.md` | FE9-SYS-083–086 | Focused trace | Explain turn/phase ordering, phase initialization hooks, unit refresh/acted state, and exact boundaries at which events/statuses/AI run. |
| P07 | New `battle-forecast.md` | FE9-SYS-113–116 | Synthesis + parity tests | Explain target and weapon filtering, defender equipment selection, forecast construction, and where displayed values intentionally differ from resolved outcomes. |
| P08 | Expand `items-weapons.md` | FE9-SYS-178, FE9-SYS-182 | Synthesis | Add WEXP/rank accumulation and permanent stat/build/movement bonuses, including serialization, caps, promotion interaction, and item-use edge cases. |
| P09 | New `bonus-experience.md` | FE9-SYS-208–213, FE9-SYS-278 | Research-heavy | Recover chapter/difficulty award inputs, turn thresholds, event/objective bonuses, pool accounting, base allocation, level transitions, and the unlocked breakdown display. |
| P10 | New `battle-reports-records.md` | FE9-SYS-216–220, FE9-SYS-282 | Research-heavy | Explain Soren's report presentation, MVP selection, unit counters, clear history, play time, and completion records; isolate any still-unknown MVP weighting. |
| P11 | New `staves.md` | FE9-SYS-221–229 | Focused trace | Cover healing/status accuracy, Restore, Ward/Barrier, Rescue, Warp, Hammerne, Torch, Unlock, durability/WEXP/EXP, targeting, range, and AI/player differences. |
| P12 | New `status-effects.md` | FE9-SYS-230–235 | Research-heavy | Establish application, duration/tick boundary, action restrictions, recovery, display, serialization, immunity, terrain healing, and status/skill interactions. |
| P13 | New `ai-engine-and-scoring.md` | FE9-SYS-251–258, FE9-SYS-273 | Research-heavy | Teach the phase scheduler, AI interpreter, group assignment, candidate enumeration, attack/movement scoring, both danger maps, deterministic tie-breaking, and scan order. |
| P14 | New `ai-activation-and-orders.md` | FE9-SYS-259–262, FE9-SYS-272 | Focused trace | Explain aggro triggers, routes, hold-position/boss behavior, escape behavior, and player-issued partner orders as script-level policies over the AI engine. |
| P15 | New `ai-healing-and-special-actions.md` | FE9-SYS-263–271 | Synthesis + parity tests | Explain heal hysteresis, item borrowing/use, refuge selection, healing/status staves, Steal, Chant, and the order in which those actions pre-empt attacks or movement. |
| P16 | New `base-system.md` | FE9-SYS-274–277, FE9-SYS-279–281 | Synthesis + focused trace | Explain base entry/gating, Info/support/manage flows, shops, forge, warehouse, state persistence, and exit into preparation. BEXP/report internals link to P09/P10. |
| P17 | New `battle-preparations.md` | FE9-SYS-283–287 | Focused trace | Cover preparation menus, deployment eligibility/limits, starting slots, inspection, inventory/skill changes, save/resume state, and battle-start commit. |
| P18 | New `dialogue-engine.md` | FE9-SYS-288–295 | Evidence-rich synthesis | Connect message lookup, encoding/control codes, conversation layout/context, portraits, text boxes, input/advance behavior, and choices into one reader-first lifecycle. |
| P19 | Expand `dialogue-engine.md` | FE9-SYS-296, FE9-SYS-297 | Synthesis | Add map, base, support, and death-quote entry paths and explain what state/layout they share or override. |
| P20 | New `endings.md` | FE9-SYS-302 | Focused trace | Explain ending-card selection, survival/relationship conditions, text substitution, order, records inputs, and transition to credits/unlocks. |
| P21 | New `video-system.md` linked to `thp-format.md` | FE9-SYS-331 | Evidence-rich synthesis | Explain the runtime THP load/decode/buffer/synchronization/skip lifecycle while leaving byte-level codec details in the format article. |
| P22 | New `input-menus-and-options.md` | FE9-SYS-333–336, FE9-SYS-341, FE9-SYS-345–348 | Focused trace | Cover controller mapping, focus/repeat, title/file-select navigation, reusable lists, options, screen calibration, dialogs, and pause/suspend routing. |
| P23 | New `tactical-interface.md` | FE9-SYS-337–340, FE9-SYS-342 | Synthesis + focused trace | Explain the map HUD, status pages, map/unit command construction, help lookup, contextual visibility, and how UI reflects authoritative map state. |
| P24 | New `save-system.md` linked to `save-format.md` | FE9-SYS-349–359 | Evidence-rich synthesis | Teach Memory Card operations, blocks, serialization/reconstruction, integrity/versioning, system-data replication, save types, resume points, and mod compatibility. |
| P25 | New `extras-and-unlocks.md` | FE9-SYS-360–370 | Synthesis + targeted experiments | Explain clear flags, playthrough numbers, Trial Maps, Extras, Theater, gallery, Records, GBA protocol/rewards, character-met tracking, and post-clear New Game options. |

## Phase 1 — establish shared vocabulary and lifecycle

Complete P01, P03, P05, P06, and P24 first. These articles establish resource identity, regional/difficulty context, campaign routing, turn boundaries, and persistence—the concepts repeatedly needed by later gameplay pages. P02 begins in parallel as a research track but should not block evidence-rich writing; publish it only when scheduler and ownership claims are supported.

Deliverables:

- one consistent diagram of boot → archives → definitions → runtime instances;
- one campaign/scene lifecycle used by later base, preparation, battle, report, and extras pages;
- one turn/phase timeline that status, AI, events, and healing pages can cite;
- one save-boundary table distinguishing system, playthrough, chapter, map, unit, and presentation state.

## Phase 2 — finish player-facing tactical rules

Complete P07–P12. Start P07 and P08 with existing combat/item evidence. Run P09 and P10 as dedicated reverse-engineering tracks because BEXP thresholds and MVP weighting must not be filled from community assumptions. P11 establishes staff behavior; P12 consumes its application rules and the P06 phase timeline to explain status duration.

Required experiments and traces:

- compare displayed forecast with logged combat inputs across range, status, effectiveness, support, and unusable-counter cases;
- trace WEXP and permanent bonus writes into the serialized unit record;
- collect BEXP output across turn thresholds/difficulties, then connect each change to script flags or native tables;
- hold report inputs constant while varying kills, battles, EXP, movement, and unit identity to isolate MVP scoring;
- save/reload every status at each likely tick boundary and test Restore, death, transform, and chapter transition.

## Phase 3 — document AI as policies over common primitives

Complete P13 before P14 and P15 receive final review. P13 defines interpreter state, candidate generation, scoring maps, and tie-breaking; the later articles should reuse those primitives instead of restating them inconsistently.

Build a small parity corpus for each AI article:

- one target tie, one weapon tie, one movement tie, and one map-edge scan-order case;
- dormant-to-active, route interruption, hold-position, escape, and partner-order examples;
- each heal threshold transition, self-item choice, borrowed item, refuge, healing staff, status staff, Steal, and Chant behavior;
- expected action and final tile compared against both the game and TelliusModding's simulator where supported.

## Phase 4 — base, preparation, and narrative presentation

Complete P16–P21. P16 and P17 cite the campaign lifecycle and save boundaries. P18 is the prerequisite for P19 and P20. P21 converts the existing THP format knowledge into a system-level explanation rather than duplicating codec details.

Each article needs a start-to-finish worked path:

- enter base → run opening/Info event → manage inventory → shop/forge → leave;
- load preparation save → choose roster/slots → inspect map → commit battle start;
- message key → decoded controls → scene/context → portrait/text layout → input → script resumes;
- final state → ending-card selection → records/credits → clear unlocks;
- script requests movie → stream/decode audio/video → skip or finish → return to script.

## Phase 5 — UI and postgame shell

Complete P22, P23, and P25 after the underlying systems they display are stable. UI articles must explain both what the player sees and which authoritative state owns the value; they should not infer mechanics from labels alone. P25 depends on P10, P20, and P24 for records, ending, and persistence facts.

Test with controller and save-state matrices:

- focus/repeat/cancel behavior for nested menus, disabled actions, full inventory, and destructive confirmation;
- HUD/status/help values matched to underlying unit/map data;
- option persistence across save blocks and new playthroughs;
- each clear difficulty and connected GBA title mapped to exact unlock-bit changes and visible Extras entries.

## Research and writing workflow

For each package:

1. **Open a research brief.** Copy the assigned IDs, inventory definitions, related wiki links, known files/functions, and current uncertainty into a working checklist.
2. **Collect existing evidence first.** Search format pages, source readers, tests, scripts, and executable notes before starting new reverse engineering.
3. **State hypotheses as tests.** For every unknown, identify the controlled inputs, expected distinguishing outcomes, saved/runtime fields, and trace point.
4. **Capture reproducible results.** Preserve function addresses/symbols, file sections, script names, regional build, difficulty, chapter, input state, and observed output.
5. **Write from player model to implementation.** Opening → mental model/example → inputs/state → lifecycle/rules → interactions/edge cases → implementation/evidence → gaps.
6. **Claim coverage.** Add the IDs to `system_entries`, add in-body `FE9-SYS-NNN` labels/anchors, and refresh the dashboard.
7. **Run technical review.** Verify formulas, order, region/difficulty behavior, links, metadata, and reproducibility.
8. **Run teaching review.** Have a reader unfamiliar with the subsystem explain it back using the page; revise anything they had to infer.
9. **Record gaps honestly.** Use `system_reviewed_with_gaps`, `system_known_gaps`, and `system_gap_work` only after serious investigation.
10. **Approve per ID.** Add an ID to `system_reviewed` only when its exact section meets the rubric; one weak subsection must not block unrelated IDs in the same article.

## Progress policy

- Work in dependency order, but publish completed evidence-rich packages while research-heavy work continues.
- Never mark a package complete merely because every ID appears in metadata.
- Never copy uncertain community formulas into the archive as confirmed behavior.
- Split an article if it can no longer maintain a clear mental model or a reviewer cannot evaluate each assigned ID independently.
- Merge a proposed new system through the proposal workflow; append a new stable ID and update this roadmap if it changes package scope.
- Refresh the [coverage dashboard](system-review.md#coverage-dashboard) after every coverage or review change.

## Recommended first queue

Start with P24 (**Save System**), P01 (**Engine Resource Loading**), P06 (**Turn, Phase, and Action Cycle**), P07 (**Battle Forecast**), and P18 (**Dialogue Engine**). They have strong existing evidence and unlock vocabulary for many later pages. Run P09 (**Bonus Experience**), P10 (**Battle Reports and Records**), P02 (**Runtime Engine Architecture**), and P13 (**AI Engine and Scoring**) as the first long-running research tracks.
