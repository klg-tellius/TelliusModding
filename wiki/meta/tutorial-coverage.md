---
id: "tutorial-coverage"
title: "Modding tutorial coverage ledger"
description: "Migration and verification ledger for the in-depth Tellius Modding curriculum"
games: ["path-of-radiance"]
section: "meta"
article_type: "reference"
tags: ["Coverage", "Contributing", "Modding app"]
aliases: []
status: "published"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "meta"
source_path: "meta/tutorial-coverage.md"
---
# Modding tutorial coverage ledger

This is the handoff and acceptance ledger for the [modding curriculum](../modding/index.md). `legacy` means that the existing page remains available but has not passed the [deep tutorial standard](tutorial-authoring-standard.md). `draft` means its field/action inventory and new prose exist. Only `verified` or `published` means another reviewer executed the lesson.

## Tracks and migration state

| Lessons | Curriculum track | Primary surfaces | Stage |
| --- | --- | --- | --- |
| 01–05 | Start safely | launcher, workspace shell, project/check/build workflows | all five lessons are deep drafts |
| 06–09 | Campaign foundations | chapter records, campaign wizard and routing | all four lessons are deep drafts |
| 10–20 | Characters and game data | character, portrait, support, class, item, skill, terrain and army editors | all eleven lessons are deep drafts |
| 21–28 | Maps | Build tab, terrain/heights/props, model import and map settings | all eight lessons are deep drafts |
| 29–36 | Units and events | deployment, scripts, flags, functions and shared scripts | all eight lessons are deep drafts |
| 37–42 | Dialogue and text | dialogue stage, messages, backgrounds, movies and fonts | all six lessons are deep drafts |
| 43–50 | AI, economy and media | AI tools, shops, audio, video and graphics | all eight lessons are deep drafts |
| 51–55 | Models and battle presentation | model viewer/importer, rigs, animations, battle resources | all five lessons are deep drafts |
| 56–64 | Test and release | simulator, code patches, Play, saves, debug, packaging and diagnosis | all nine lessons are deep drafts |

## Lesson ledger

The **evidence owner** is the first source an author must inspect, not the only source allowed. The reviewer adds exact files, symbols, tests, app build, and observations to the article while migrating it.

| Lesson | Primary explanation owns | Evidence owner | Required execution |
| --- | --- | --- | --- |
| 01 | installation, extraction, project identity and failure recovery | project/launcher source | clean project creation |
| 02 | navigation, search, history, status and editor ownership | workspace shell source | locate one record and return |
| 03 | Apply/save/build boundaries, backups and restoration | editor/project writers | save, reload and restore |
| 04 | image building, Dolphin configuration and clean baseline | build workflow | boot unmodified build |
| 05 | every check category and warning disposition | project checker | baseline plus induced failure |
| 06 | chapter slot, part, map and resource relationships | chapter index and records | trace one real chapter |
| 07 | IDs, story order, transitions and non-numbered slots | campaign routing | controlled route comparison |
| 08 | every campaign-wizard choice and generated resource | campaign wizard | generate and inspect skeleton |
| 09 | table, slot, flag, disc and save constraints | format/system references | boundary checklist |
| 10 | every character-record control and link | character form and FE8Data | copied character round trip |
| 11 | portrait records, image requirements and assignment | portrait viewer/writer | import and resolve portrait |
| 12 | character/class model override resolution | model tables and ZDBX | map and battle resolution |
| 13 | support pairs, ranks, points, dialogue and availability | support editor/system | unlock one support |
| 14 | talk recruitment, allegiance, boss markers and persistence | scripts/deployment | recruit and boss defeat |
| 15 | reference search, safe deletion and save compatibility | reference checker | blocked and safe removal |
| 16 | every class control, promotion and model boundary | class form, FE8Data and class systems | source/app/simulator; Dolphin gaps labeled |
| 17 | every item/weapon control and battle-weapon presentation | item form and battle tables | forecast plus render |
| 18 | every skill control, restrictions, capacity and scroll linkage | skill form/system | teach/equip/trigger comparisons |
| 19 | every terrain definition and movement-cost column | terrain form and movement engine | multiple movement types |
| 20 | difficulty records, armies and allegiance effects | general data/army systems | cross-difficulty comparison |
| 21 | Build-tab navigation, layers, tools, selection and undo | map builder | non-destructive map edit |
| 22 | terrain paint, sample, fill, layers and pathing separation | map builder/map format | blocked and costly routes |
| 23 | height values, slopes, links and movement/display effects | map builder/map grid | traversable height transition |
| 24 | every prop operation, placement field and import warning | map objects tools | place, copy, reopen and trigger |
| 25 | terrain-mesh export/import contract | model/map formats | minimal visible round trip |
| 25+ (terrain-sculpt-paint) | terrain kits, paint layers, swatch table, compiled texturing | terrain_paint/terrain_kit and the Tellius Terrain add-on | sculpt, paint, import and Dolphin check |
| 26 | water geometry, material and flow controls | model/material tools | preview and built-game check |
| 27 | every map-setting control and objective linkage | map settings/chapters | app preview plus game check |
| 28 | terrain-to-scenery assignment and fallback | battle terrain/staging | explicit and fallback scene |
| 29 | section identity, role, callers and ordering | deployment editor/scripts | load intended section only |
| 30 | difficulty variants, coordinates and personal/class data | deployment editor | three-difficulty comparison |
| 31 | every unit inventory, drop, ring and flag control | deployment format/form | inventory and drop test |
| 32 | reinforcement section, trigger, repeat guard and arrival | deployment/scripts/flags | first and repeat trigger |
| 33 | every script-editor command, form, diagnostic and save boundary | script editor/compiler | edit, check, save and trigger |
| 34 | chapter/campaign flag creation, lifetime and collisions | flags editor/event system | set, gate and reload |
| 35 | event recipes and their conditions/state convergence | script catalog | execute each documented recipe |
| 36 | startup helpers, exports, endings and cross-file dependencies | script sources/compiler | caller/callee verification |
| 37 | every dialogue command, speaker, seat and preview control | dialogue/scene editor | authored scene playback |
| 38 | background import, identity, display and clearing | background/dialogue tools | show and replace background |
| 39 | inline controls, encoding, layout and font availability | message/font formats | render boundary cases |
| 40 | base/world-map message ownership and callers | message/script systems | trigger each context |
| 41 | title/movie IDs, playback and skip/fallback behavior | chapter records/video | chapter-opening playback |
| 42 | font import, glyph mapping, metrics and overflow | font tools/formats | representative glyph set |
| 43 | AI syntax, operands, state and execution lifecycle | AI VM/editor | controlled decision |
| 44 | common orders with parameters and target semantics | AI catalog | execute every recipe family |
| 45 | trace/log controls and score interpretation | AI inspection | explain one chosen target |
| 46 | shop identity, stock, forge, price and gold wiring | shop editor/economy | buy and forge transaction |
| 47 | music cue/track controls, loop data and context | music editors/system | preview and in-context playback |
| 48 | SFX banks, macros, cues and replacement constraints | SFX tools/MusyX | trigger replaced cue |
| 49 | video import requirements, replacement and disc budget | video viewer/THP | playback and size comparison |
| 50 | image/archive controls, palettes and texture constraints | graphics viewers/formats | reopen in consuming context |
| 51 | export/import controls, Blender contract and import review | model viewer/importer | minimal geometry round trip |
| 52 | rig names, hierarchy, weights and fit constraints | model/animation formats | pose and animation matrix |
| 53 | animation import/events/timing controls | animation/model tools | idle, move and attack checks |
| 54 | weapon/scenery model controls and hard budgets | model/battle tables | normal/forged and scenery render |
| 55 | battle table, camera, effect and staging controls | battle viewers/staging | same fight before/after |
| 56 | every simulator input, roll mode, forecast/log and render boundary | battle simulator | deterministic comparison |
| 57 | every exposed patch, compatibility and revert behavior | game-code catalog | install, detect and revert |
| 58 | Play setup, controls, logs, rewind and unsupported behavior | playthrough tools | repeatable chapter action |
| 59 | save selection, units, flags, checksums and backup | save editor/format | copy, edit, load and restore |
| 60 | debug-menu installation, controls and persistence risks | game-code/debug systems | enable and invoke safely |
| 61 | patch inputs, clean-disc requirement, metadata and verification | patch workflow | apply to clean matching input |
| 62 | integration of three chapters and cross-chapter state | all prerequisite tutorials | fresh-save campaign run |
| 63 | unsupported features, approximations and evidence level | source/system gap inventory | link every stated limit |
| 64 | symptom-led diagnosis across check/build/boot/runtime | diagnostics and checker | reproduce representative failures |

## Discrepancy log

| Topic | Accounts to reconcile | Publication rule |
| --- | --- | --- |
| Class growth rows | Class-form tooltip, FE8Data comments, growth system article and runtime consumers | Do not state how the class growth row combines with personal growth until the accounts agree or the uncertainty is explicit. |
| Promotion result | Class reference, simulator implementation and executable evidence | Separate simulator coverage from confirmed game behavior. |
| Model import | Importer review, preview renderer and Dolphin behavior | Keep rigged/blended import labeled untested until a recorded game test passes. |
| Painted terrain | Compiled preview, app renderer and Dolphin | Keep painted texturing, custom atlases and baked light labelled untested until a recorded game test passes. |
| Map collision | Visible props, terrain costs, height links and scripted object interaction | Test each ownership layer independently instead of calling all of them “collision.” |

## Batch acceptance record

For each migrated batch, record reviewer, app/source revision, disposable project checkpoint, articles executed, validation commands, unresolved gaps, and acceptance date here. Do not change a lesson to `verified` or `published` without that record.
