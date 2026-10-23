---
id: "game-systems-inventory"
title: "Complete Game Systems Inventory"
description: "A detailed taxonomy of the engine, gameplay, presentation, and platform systems in Fire Emblem: Path of Radiance"
games: ["path-of-radiance"]
section: "meta"
article_type: "portal"
tags: ["Portal", "Coverage", "Engine", "Gameplay"]
aliases: []
status: "draft"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research", "telliusmodding-source", "path-of-radiance-us-manual"]
cms_collection: "meta"
source_path: "meta/game-systems-inventory.md"
---
# Complete Game Systems Inventory

*A system-level map of Fire Emblem: Path of Radiance (FE9), from boot and data loading through combat, the base, presentation, saving, and postgame unlocks*

This inventory defines a **system** as a coherent set of rules or engine responsibilities with its own inputs, state, and outputs. A single system may span executable code, data tables, scripts, assets, and UI. File formats are named only when they clarify ownership; a format is not automatically a game system.

Every entry has a permanent `FE9-SYS-NNN` identifier used by the [documentation review system](system-review.md). New systems are appended after review; existing identifiers are never renumbered or reused.

The scope is the **US release of Path of Radiance** unless a regional difference is stated. “Confirmed” means the repository has direct file, executable, or in-game evidence. “Partial” means the system boundary is known but at least one formula, field, or interaction still needs tracing. This is a coverage checklist, not a claim that every listed system already has a finished article.

## 1. Platform, boot, and executable systems

1. <span id="fe9-sys-001"></span> **FE9-SYS-001 — GameCube boot and apploader** — Starts the disc, loads the DOL executable, establishes the runtime memory layout, and transfers control to the game. It owns the earliest platform initialization before FE9-specific resources exist.
2. <span id="fe9-sys-002"></span> **FE9-SYS-002 — DOL section and address mapping** — Maps executable text, read-only data, and writable data into memory. Every native formula, hook, global table, and code patch ultimately belongs to this address space.
3. <span id="fe9-sys-003"></span> **FE9-SYS-003 — Disc filesystem and path lookup** — Resolves paths in the GameCube FST and reads loose files such as `FE8Data.bin`, chapter folders, music, movies, and archives.
4. <span id="fe9-sys-004"></span> **FE9-SYS-004 — Archive-first resource lookup** — Searches already loaded archives before loose disc files. This is why the copy of core data inside `system.cmp`, rather than an apparently identical loose file, can be the effective runtime source.
5. <span id="fe9-sys-005"></span> **FE9-SYS-005 — Compression and decompression** — Decodes LZ10/CMP resources and exposes their contents to higher-level loaders. Compression is a transport layer used by data, messages, UI, models, and other systems.
6. <span id="fe9-sys-006"></span> **FE9-SYS-006 — Pack/archive mounting** — Loads multi-file containers, registers their members by name, and keeps common resources available across scenes.
7. <span id="fe9-sys-007"></span> **FE9-SYS-007 — Labeled-section data loading** — Reads containers made of named sections, pointers/relocations, symbol tables, string pools, timestamps, and author metadata. Shops, AI data, and many engine tables use this shared loader pattern.
8. <span id="fe9-sys-008"></span> **FE9-SYS-008 — Runtime resource registry** — Maps identifiers such as `PID_`, `JID_`, `IID_`, `SID_`, `MID_`, `EID_`, and animation/model labels to loaded objects. It is the identity layer connecting otherwise separate data sets.
9. <span id="fe9-sys-009"></span> **FE9-SYS-009 — Memory allocation and object lifetime** — Creates runtime chapter, unit, map, UI, model, audio, and script objects, then releases or replaces them during scene transitions.
10. <span id="fe9-sys-010"></span> **FE9-SYS-010 — Frame scheduler and game loop** — Advances input, scripts, animation, UI, audio, battle presentation, and scene changes in a stable order. Pauses, skips, fades, and blocking script calls depend on this scheduler.
11. <span id="fe9-sys-011"></span> **FE9-SYS-011 — Scene/state machine** — Switches among title, file selection, story scene, base, battle preparation, tactical map, battle animation, chapter clear, extras, and trial-map states.
12. <span id="fe9-sys-012"></span> **FE9-SYS-012 — Global service and singleton state** — Owns cross-scene resources such as party data, options, RNG state, loaded archives, audio state, and the active chapter.
13. <span id="fe9-sys-013"></span> **FE9-SYS-013 — Region and revision handling** — Selects localized message/data variants and accommodates executable differences among Japanese, US, and PAL releases. Easy/Maniac availability and class critical bonuses are region-sensitive examples.
14. <span id="fe9-sys-014"></span> **FE9-SYS-014 — Crash, assertion, and debug output** — Emits internal diagnostics and supports development-only checks. Retail data still contains timestamps, author strings, debug messages, and dormant developer facilities.

## 2. Core data and runtime entity systems

15. <span id="fe9-sys-015"></span> **FE9-SYS-015 — Core database loading** — Loads the shared character, class, item, skill, terrain, support, chapter, group, and difficulty-constant tables from `FE8Data.bin`/`system.cmp`.
16. <span id="fe9-sys-016"></span> **FE9-SYS-016 — Character definition system** — Defines personal identity, default class, portrait, affinity, growths, personal bases, build/weight, skills, support list, animation overrides, and story-facing labels.
17. <span id="fe9-sys-017"></span> **FE9-SYS-017 — Class definition system** — Defines class bases and caps, movement type, weapon access, promotion link and bonuses, innate traits, skill capacity, model/animation identity, and class categories.
18. <span id="fe9-sys-018"></span> **FE9-SYS-018 — Runtime unit construction** — Combines a character template, class template, deployment record, and saved progression into one mutable unit with current HP, inventory, status, position, skills, AI, and counters.
19. <span id="fe9-sys-019"></span> **FE9-SYS-019 — Unit-slot and army-list management** — Maintains up to 159 serialized unit slots and linked lists for player, enemy, ally, other, reserve, inactive, removed, and free units.
20. <span id="fe9-sys-020"></span> **FE9-SYS-020 — Unit-state flags** — Tracks acted, dead, carried, hidden, under a roof, retreating, scripted, invulnerable, boss, drop-item, and other transient or persistent unit conditions.
21. <span id="fe9-sys-021"></span> **FE9-SYS-021 — Army and allegiance system** — Assigns units to player, enemy, partner, and other forces; determines hostility, phase ownership, target legality, colors, and some AI group behavior.
22. <span id="fe9-sys-022"></span> **FE9-SYS-022 — Commander and group system** — Associates deployed units with groups and commanders for AI orders, scripted movement, localized bonuses such as Charisma, and event targeting.
23. <span id="fe9-sys-023"></span> **FE9-SYS-023 — Identifier and label resolution** — Uses stable textual labels to connect characters, classes, items, skills, messages, effects, models, scripts, and chapters without hard-coding every relationship as an index.
24. <span id="fe9-sys-024"></span> **FE9-SYS-024 — Mutable party state** — Stores gold, BEXP, chapter, playthrough number, elapsed time, options, clear history, flags, forge use, convoy, and report counters across scenes.
25. <span id="fe9-sys-025"></span> **FE9-SYS-025 — Difficulty profile** — Selects mode-specific deployment, shop stock, tutorials, combat EXP constants, enemy stats/skills, and other content. US has Easy/Normal/Hard; Japanese substitutes Maniac for Easy.

## 3. Campaign and chapter-flow systems

26. <span id="fe9-sys-026"></span> **FE9-SYS-026 — New-game initialization** — Creates system and playthrough state, selects difficulty, initializes growth mode and options, seeds progression, and starts the Prologue flow.
27. <span id="fe9-sys-027"></span> **FE9-SYS-027 — Campaign ordering** — Maps chapter completion to the next chapter, including chapter parts, base chapters, alternate maps, trial maps, and the ending.
28. <span id="fe9-sys-028"></span> **FE9-SYS-028 — Chapter lifecycle** — Coordinates chapter load, opening story, base, prebattle story, preparation, map initialization, battle, clear/failure, postbattle story, report, save, and transition.
29. <span id="fe9-sys-029"></span> **FE9-SYS-029 — Multi-part chapter handling** — Carries selected state between consecutive maps that are presented as one chapter while allowing part-specific deployments, scripts, objectives, and saves.
30. <span id="fe9-sys-030"></span> **FE9-SYS-030 — Hub/base chapter routing** — Inserts the base scene between maps, gates its facilities by story progress, and returns to combat preparation or story as appropriate.
31. <span id="fe9-sys-031"></span> **FE9-SYS-031 — Chapter record system** — Supplies chapter names, map/resource identities, objective presentation, music and scenery associations, flags, and progression metadata.
32. <span id="fe9-sys-032"></span> **FE9-SYS-032 — Chapter-local state reset** — Clears or preserves the correct flags, temporary unit states, counters, and tile records when starting, restarting, or completing a map.
33. <span id="fe9-sys-033"></span> **FE9-SYS-033 — Checkpoint/resume routing** — Records whether a save should resume in the base, preparation screen, map, chapter part, checkpoint, or trial map.
34. <span id="fe9-sys-034"></span> **FE9-SYS-034 — Victory recognition** — Watches objective state and event flags, then schedules map completion, surviving-unit processing, BEXP awards, story events, records, and saves.
35. <span id="fe9-sys-035"></span> **FE9-SYS-035 — Defeat recognition** — Detects lord death, protected-unit death, turn limits, seized/defended positions, or script-defined loss conditions and routes to Game Over or retry behavior.
36. <span id="fe9-sys-036"></span> **FE9-SYS-036 — Endgame and ending selection** — Resolves final chapter state, character survival and relationships, ending text, records, credits, and post-clear unlocks.
37. <span id="fe9-sys-037"></span> **FE9-SYS-037 — Trial-map campaign flow** — Starts standalone unlocked maps with special roster and return behavior without advancing the main campaign.

## 4. Event, scripting, and flag systems

38. <span id="fe9-sys-038"></span> **FE9-SYS-038 — Event bytecode virtual machine** — Executes compiled chapter/event instructions, manages call frames and parameters, and invokes native engine functions.
39. <span id="fe9-sys-039"></span> **FE9-SYS-039 — FE9 script source and compilation** — Represents scripts in `.fe9s` source form and compiles/decompiles them to the event format used by the game.
40. <span id="fe9-sys-040"></span> **FE9-SYS-040 — Script entry-point registry** — Exposes named chapter-start, turn, area, action, conversation, death, and utility functions to the engine.
41. <span id="fe9-sys-041"></span> **FE9-SYS-041 — Native script-call bridge** — Lets bytecode call engine functions for units, flags, maps, camera, dialogue, audio, battles, inventory, objectives, and scene changes.
42. <span id="fe9-sys-042"></span> **FE9-SYS-042 — Blocking and asynchronous script execution** — Distinguishes calls that complete immediately from scheduled movement, fades, dialogue, music, effects, and camera work that scripts must wait for.
43. <span id="fe9-sys-043"></span> **FE9-SYS-043 — Event trigger evaluation** — Tests turn, phase, unit, area, action, death, conversation, chapter state, and custom conditions, then enforces one-time or repeatable behavior.
44. <span id="fe9-sys-044"></span> **FE9-SYS-044 — Global event flags** — Persist story and unlock facts across chapters and saves.
45. <span id="fe9-sys-045"></span> **FE9-SYS-045 — Chapter event flags** — Store up to 96 map-local booleans used for reinforcements, conversations, opened objects, objectives, and one-time events.
46. <span id="fe9-sys-046"></span> **FE9-SYS-046 — Flag serialization and reset policy** — Saves flags in party state, preserves them at checkpoints, and clears chapter-local flags when the next map truly begins.
47. <span id="fe9-sys-047"></span> **FE9-SYS-047 — Area-event system** — Detects entry into rectangular or tile-based regions and fires ambushes, dialogue, reinforcements, objective changes, or scene work.
48. <span id="fe9-sys-048"></span> **FE9-SYS-048 — Turn/phase event system** — Runs events at specified turns and army phases, optionally with additional flags or unit conditions.
49. <span id="fe9-sys-049"></span> **FE9-SYS-049 — Talk and recruitment events** — Advertises Talk commands for valid unit pairs, plays the conversation, changes allegiance or unit state, and marks the interaction complete.
50. <span id="fe9-sys-050"></span> **FE9-SYS-050 — Death and retreat events** — Intercepts unit defeat to play quotes, substitute retreat for death, set story flags, remove units, alter objectives, or trigger consequences.
51. <span id="fe9-sys-051"></span> **FE9-SYS-051 — Scripted battle system** — Runs event-controlled combat with selected participants, weapons, damage/outcomes, presentation, and postbattle continuation.
52. <span id="fe9-sys-052"></span> **FE9-SYS-052 — Scripted unit manipulation** — Creates, removes, hides, reveals, moves, teleports, changes class/army, modifies inventory/HP/status, and assigns AI to units.
53. <span id="fe9-sys-053"></span> **FE9-SYS-053 — Script timing system** — Provides waits, synchronization, animation completion, message advancement, and skippable-sequence behavior.
54. <span id="fe9-sys-054"></span> **FE9-SYS-054 — Event skip/fast-forward** — Allows story scenes to be skipped while still applying required state changes and landing at a consistent continuation point.

## 5. Tactical map, geometry, and environment systems

55. <span id="fe9-sys-055"></span> **FE9-SYS-055 — Map loading and composition** — Loads terrain grids, height/link data, object placements, models, textures, lighting, weather, and chapter-specific overlays.
56. <span id="fe9-sys-056"></span> **FE9-SYS-056 — Tile coordinate system** — Converts between grid coordinates, world-space placement, model-space geometry, cursor positions, camera targets, and event areas.
57. <span id="fe9-sys-057"></span> **FE9-SYS-057 — Terrain-type system** — Assigns each tile one of 77 types with display name, avoid/Def/Res, healing, object status, and 15 movement-cost columns.
58. <span id="fe9-sys-058"></span> **FE9-SYS-058 — Movement-type system** — Selects a terrain-cost column from the unit's class, producing distinct infantry, armor, mage, cavalry, flying, thief/bandit, and laguz traversal.
59. <span id="fe9-sys-059"></span> **FE9-SYS-059 — Map link/passability grid** — Determines whether adjacent tiles are actually connected; height, walls, doors, cliffs, and composed link data can block a step independently of terrain cost.
60. <span id="fe9-sys-060"></span> **FE9-SYS-060 — Pathfinding** — Finds reachable tiles and shortest/weighted routes under movement budget, passability, occupancy, allegiance, and special movement traits.
61. <span id="fe9-sys-061"></span> **FE9-SYS-061 — Occupancy and collision** — Prevents illegal stops, permits or forbids passing through allied/hostile units, and finds nearest free tiles for scripted placement.
62. <span id="fe9-sys-062"></span> **FE9-SYS-062 — Movement-range display** — Paints legal destination tiles from current movement points and updates them for blockers and terrain.
63. <span id="fe9-sys-063"></span> **FE9-SYS-063 — Attack/staff range display** — Expands reachable positions by the chosen item's minimum/maximum range and colors attack, staff, or combined ranges.
64. <span id="fe9-sys-064"></span> **FE9-SYS-064 — Threat-range display** — Projects enemy movement and weapon ranges for player inspection; this UI concern is separate from the AI's numeric threat-map system.
65. <span id="fe9-sys-065"></span> **FE9-SYS-065 — Map cursor system** — Tracks tile selection, unit cycling, hover inspection, targeting, camera following, and the cursor position restored from a save.
66. <span id="fe9-sys-066"></span> **FE9-SYS-066 — Map camera system** — Supports pan, zoom, rotation, target following, scripted paths, bounds, and the alternate presentation used during events.
67. <span id="fe9-sys-067"></span> **FE9-SYS-067 — Map height and terrain conformance** — Places units and props on the rendered surface, adjusts their height/orientation, and connects tactical tiles to uneven 3D geometry.
68. <span id="fe9-sys-068"></span> **FE9-SYS-068 — Map-object system** — Instantiates doors, chests, villages, houses, roofs, walls, rocks, bridges, ballistae, decorations, and other interactive or visual objects.
69. <span id="fe9-sys-069"></span> **FE9-SYS-069 — Persistent tile-object state** — Serializes opened doors/roofs/chests, visited villages, destroyed buildings, wall HP, ballista ammunition, pits, and rolling rocks.
70. <span id="fe9-sys-070"></span> **FE9-SYS-070 — Door and key system** — Offers Unlock/Open when unit, item, skill, tile, and event conditions agree, then changes passability and persistent tile state.
71. <span id="fe9-sys-071"></span> **FE9-SYS-071 — Chest system** — Resolves chest contents through its event, awards or routes the item, marks the chest opened, and updates its model/UI.
72. <span id="fe9-sys-072"></span> **FE9-SYS-072 — Village/house visit system** — Offers Visit, runs the associated event, awards content or dialogue, and records visited or destroyed state.
73. <span id="fe9-sys-073"></span> **FE9-SYS-073 — Breakable-wall/building system** — Gives objects HP or a destroy action, accepts qualifying attacks, updates terrain/object state, and fires completion events.
74. <span id="fe9-sys-074"></span> **FE9-SYS-074 — Bridge and map-state transformation** — Changes traversability or visuals when bridges, roofs, gates, or scripted map pieces open/close.
75. <span id="fe9-sys-075"></span> **FE9-SYS-075 — Ballista and siege-object system** — Stores a placed weapon and uses, exposes Shoot to valid operators, computes range/targets, and persists remaining ammunition.
76. <span id="fe9-sys-076"></span> **FE9-SYS-076 — Hidden-item system** — Checks eligible units/tiles and discovery chances, then transfers the concealed item and marks it collected.
77. <span id="fe9-sys-077"></span> **FE9-SYS-077 — Fog-of-war system** — Hides enemy units and terrain information outside friendly vision, incorporates unit/class sight and torch effects, and changes targeting/inspection behavior.
78. <span id="fe9-sys-078"></span> **FE9-SYS-078 — Roof/interior visibility system** — Hides or reveals units and geometry beneath roofs and coordinates that state with movement, AI exclusion, and events.
79. <span id="fe9-sys-079"></span> **FE9-SYS-079 — Weather system** — Selects rain, snow, sandstorm, clear, night, or other map ambience and passes weather state to rendering, battle skies, saves, and scripts.
80. <span id="fe9-sys-080"></span> **FE9-SYS-080 — Lighting and ambience system** — Controls map lights, fog color/density, sky, time-of-day look, environmental effects, and chapter-specific atmosphere.
81. <span id="fe9-sys-081"></span> **FE9-SYS-081 — Terrain texture blending** — Blends terrain materials with masks, roads, shores, transitions, and texture layers rather than rendering every tile as an isolated square.
82. <span id="fe9-sys-082"></span> **FE9-SYS-082 — Water and animated environment** — Renders water/flow surfaces and animated props, with parameters independent of the tactical terrain grid.

## 6. Turn, phase, and action-economy systems

83. <span id="fe9-sys-083"></span> **FE9-SYS-083 — Turn counter** — Advances after the army-phase cycle, feeds timed events/objectives/BEXP, and is written into chapter clear history.
84. <span id="fe9-sys-084"></span> **FE9-SYS-084 — Army-phase order** — Runs Player, Partner, Enemy, and Other phases in order, skipping absent forces while preserving event hooks.
85. <span id="fe9-sys-085"></span> **FE9-SYS-085 — Phase initialization** — Refreshes units, updates phase-bound statuses and terrain healing, rebuilds AI maps, runs phase events, and starts phase music/presentation; the FE9 Laguz gauge instead advances after actions and damage.
86. <span id="fe9-sys-086"></span> **FE9-SYS-086 — Unit action state** — Marks whether a unit has acted, supports selection cycling, prevents duplicate full actions, and changes the unit ring to gray.
87. <span id="fe9-sys-087"></span> **FE9-SYS-087 — Wait command** — Commits movement and ends the unit's action without another operation.
88. <span id="fe9-sys-088"></span> **FE9-SYS-088 — Canto/post-action movement** — Gives eligible mounted/flying units remaining movement after certain actions, with restrictions determined by action type and remaining movement.
89. <span id="fe9-sys-089"></span> **FE9-SYS-089 — Rescue/carry system** — Tests unit weight/build and movement category, links carrier and carried unit, applies stat penalties, hides the carried unit from normal targeting, and persists the relationship.
90. <span id="fe9-sys-090"></span> **FE9-SYS-090 — Drop system** — Places a carried unit on a legal adjacent tile and ends or continues the actor's action according to command rules.
91. <span id="fe9-sys-091"></span> **FE9-SYS-091 — Take/Give system** — Transfers a carried unit between adjacent eligible allies, allowing rescue chains while enforcing weight and occupancy rules.
92. <span id="fe9-sys-092"></span> **FE9-SYS-092 — Shove system** — Tests the Shove trait and relative weight, then moves an adjacent unit one tile if the destination is legal.
93. <span id="fe9-sys-093"></span> **FE9-SYS-093 — Smite system** — Extends shove-like displacement to two tiles and handles intervening/destination legality.
94. <span id="fe9-sys-094"></span> **FE9-SYS-094 — Trade system** — Exchanges inventory slots between adjacent allied units, updates equipped state, and participates in the action/canto rules.
95. <span id="fe9-sys-095"></span> **FE9-SYS-095 — Supply/convoy access on map** — Allows eligible units or contexts to move items between personal inventory and the party's 200-slot convoy.
96. <span id="fe9-sys-096"></span> **FE9-SYS-096 — Item-use command** — Filters usable consumables, applies healing/stat/status/key effects, spends durability, plays an effect, and ends or modifies the action.
97. <span id="fe9-sys-097"></span> **FE9-SYS-097 — Equip command and auto-equip** — Selects a legal weapon, stores the equipped flag, and falls back to another usable weapon when the current one breaks or becomes invalid.
98. <span id="fe9-sys-098"></span> **FE9-SYS-098 — Talk command** — Appears only for valid scripted pairs and delegates to the talk/recruitment event system.
99. <span id="fe9-sys-099"></span> **FE9-SYS-099 — Visit/Open/Chest/Seize/Arrive/Escape command family** — Builds tile-sensitive commands from event/objective data and commits their corresponding script and map-state transitions.
100. <span id="fe9-sys-100"></span> **FE9-SYS-100 — Order/command system for partner units** — Lets the player set coarse behavior for yellow units where the chapter permits it; AI interprets the chosen order on the partner phase.
101. <span id="fe9-sys-101"></span> **FE9-SYS-101 — End Turn** — Marks remaining player units as finished and transfers control to subsequent army phases after confirmation.
102. <span id="fe9-sys-102"></span> **FE9-SYS-102 — Action menu construction** — Dynamically builds commands from unit traits, inventory, target adjacency, tile events, chapter state, skills, and remaining movement.

## 7. Objectives and map-completion systems

103. <span id="fe9-sys-103"></span> **FE9-SYS-103 — Objective definition and display** — Stores up to four objective text keys and presents the current victory/defeat conditions in map UI.
104. <span id="fe9-sys-104"></span> **FE9-SYS-104 — Rout** — Completes when required hostile units are defeated, excluding or specially treating retreating/script-protected units.
105. <span id="fe9-sys-105"></span> **FE9-SYS-105 — Defeat boss** — Tracks one or more boss-flagged or specifically named units and completes when the required target is defeated.
106. <span id="fe9-sys-106"></span> **FE9-SYS-106 — Seize** — Requires the designated unit, normally Ike, to stand on the objective tile and choose Seize.
107. <span id="fe9-sys-107"></span> **FE9-SYS-107 — Arrive** — Completes when an eligible unit reaches and activates the target tile; eligibility may be script-defined.
108. <span id="fe9-sys-108"></span> **FE9-SYS-108 — Escape** — Removes or marks units as escaped and resolves completion/failure according to whether Ike, all units, or specific units must leave.
109. <span id="fe9-sys-109"></span> **FE9-SYS-109 — Defend/survive** — Counts turns or phases while protecting a tile/unit and completes after the scripted duration.
110. <span id="fe9-sys-110"></span> **FE9-SYS-110 — Protect unit/position** — Fails when a named NPC, allied group, or defended location is lost even if Ike survives.
111. <span id="fe9-sys-111"></span> **FE9-SYS-111 — Multi-stage objectives** — Changes objective text, targets, enemy groups, music, or completion logic during the same map.
112. <span id="fe9-sys-112"></span> **FE9-SYS-112 — Optional objective tracking** — Records chapter-specific accomplishments such as saving priests, avoiding kills, escaping extra units, or meeting turn thresholds for BEXP and events.

## 8. Combat setup and forecast systems

113. <span id="fe9-sys-113"></span> **FE9-SYS-113 — Target selection** — Filters attackable units by allegiance, visibility, range, weapon rules, and special object targeting.
114. <span id="fe9-sys-114"></span> **FE9-SYS-114 — Weapon selection** — Determines which inventory items are legal at the current range and class/skill/rank state.
115. <span id="fe9-sys-115"></span> **FE9-SYS-115 — Defender weapon selection** — Chooses the defender's equipped usable weapon for a counter at the actual distance, or produces no counter.
116. <span id="fe9-sys-116"></span> **FE9-SYS-116 — Battle forecast** — Calculates displayed damage, hit, critical, HP, weapon, and expected number of strikes before the player commits.
117. <span id="fe9-sys-117"></span> **FE9-SYS-117 — Attack Speed** — Computes effective speed as Speed minus uncompensated weapon weight; Strength offsets weapon weight, and the result drives avoid and follow-ups.
118. <span id="fe9-sys-118"></span> **FE9-SYS-118 — Physical weapon triangle** — Applies sword over axe, axe over lance, and lance over sword, modifying hit and weapon might/damage.
119. <span id="fe9-sys-119"></span> **FE9-SYS-119 — Trinity of Magic** — Applies Fire over Wind, Wind over Thunder, and Thunder over Fire; Light is outside the triangle.
120. <span id="fe9-sys-120"></span> **FE9-SYS-120 — Weapon rank and access** — Compares class/skill permissions and accumulated weapon EXP against E–S requirements and special restrictions.
121. <span id="fe9-sys-121"></span> **FE9-SYS-121 — Range system** — Enforces minimum/maximum range, adjacent/ranged-only behavior, siege range, and Mag/2 dynamic range clamped to 5–15 for applicable tomes/staves.
122. <span id="fe9-sys-122"></span> **FE9-SYS-122 — Effectiveness system** — Matches weapon/item category masks against class categories such as flying, beast, dragon, armor, knight, or laguz and doubles weapon might; Full Guard and related properties suppress it.
123. <span id="fe9-sys-123"></span> **FE9-SYS-123 — Blessed-armor protection** — Sets attack to zero against the Black Knight/Ashnard armor trait unless the weapon has the allowed blessed property, and also constrains Counter.
124. <span id="fe9-sys-124"></span> **FE9-SYS-124 — Support/bond proximity bonuses** — Adds pair/affinity or innate bond modifiers when eligible units are within the required distance and the battle is not neutralized by Parity.
125. <span id="fe9-sys-125"></span> **FE9-SYS-125 — Terrain combat bonuses** — Adds tile avoid, Defense, and Resistance from terrain, using alternate bonuses for the relevant movement trait where applicable.
126. <span id="fe9-sys-126"></span> **FE9-SYS-126 — Biorhythm combat modifier** — Advances a per-unit battle cycle, selects a wave band, and applies status-scaled table values; in retail Path of Radiance the live stat consumers read positions that are zero in every band, so the computed contribution is always zero.
127. <span id="fe9-sys-127"></span> **FE9-SYS-127 — Status and temporary-stat modifiers** — Applies Barrier/Pure Water, Resolve/Wrath conditions, silence, sleep, berserk, poison, and other temporary state to legal actions or forecasts.
128. <span id="fe9-sys-128"></span> **FE9-SYS-128 — Battle RNG service** — Advances the shared three-word RNG state and supplies percentage rolls to combat, skills, levels, and other chance-based systems.
129. <span id="fe9-sys-129"></span> **FE9-SYS-129 — Two-RN/True Hit** — Rolls twice and averages for normal hit checks, producing a curved real probability while displayed critical uses a single roll.

## 9. Combat-resolution systems

130. <span id="fe9-sys-130"></span> **FE9-SYS-130 — Exchange-order construction** — Builds attacker action, defender counter, and follow-up exchanges; Vantage can reverse the opening order and Cancel can remove a counter step.
131. <span id="fe9-sys-131"></span> **FE9-SYS-131 — Follow-up/doubling** — Grants an additional exchange when effective Attack Speed exceeds the opponent's by at least 4.
132. <span id="fe9-sys-132"></span> **FE9-SYS-132 — Multi-strike/Brave behavior** — Doubles strikes inside an exchange independently of speed-based follow-ups and can stack with skill-added strikes.
133. <span id="fe9-sys-133"></span> **FE9-SYS-133 — Hit calculation** — Combines weapon hit, Skill, Luck, triangle, biorhythm, support, and other modifiers; subtracts Avoid and clamps the final rate.
134. <span id="fe9-sys-134"></span> **FE9-SYS-134 — Avoid calculation** — Combines twice Attack Speed, Luck, biorhythm, support, terrain, and applicable modifiers with a floor of zero.
135. <span id="fe9-sys-135"></span> **FE9-SYS-135 — Critical calculation** — Combines weapon critical, Skill, support/bonuses, class bonus outside the Japanese release, enemy Dodge, and crit-sealing properties.
136. <span id="fe9-sys-136"></span> **FE9-SYS-136 — Critical damage** — Multiplies resolved damage by 3 after a successful critical unless a special effect replaces the ordinary result.
137. <span id="fe9-sys-137"></span> **FE9-SYS-137 — Physical damage** — Uses Strength and weapon might against Defense after triangle, effectiveness, support, terrain, and protection rules.
138. <span id="fe9-sys-138"></span> **FE9-SYS-138 — Magical damage** — Uses Magic and weapon might against Resistance; weapon attack type, not merely displayed weapon family, selects the stat pair.
139. <span id="fe9-sys-139"></span> **FE9-SYS-139 — Magic-weapon behavior** — Allows physical-looking swords/lances/axes with a magical attack type to use Magic/Resistance and their configured range/effects.
140. <span id="fe9-sys-140"></span> **FE9-SYS-140 — Minimum/zero damage policy** — Resolves negative damage to zero and feeds “did damage” gates used by experience and some after-hit effects.
141. <span id="fe9-sys-141"></span> **FE9-SYS-141 — Counterattack eligibility** — Tests survival, weapon, range, status, attack suppression, and skill effects before scheduling retaliation.
142. <span id="fe9-sys-142"></span> **FE9-SYS-142 — Weapon durability consumption** — Decrements uses under weapon-type/action rules, breaks exhausted items, and selects a replacement where appropriate.
143. <span id="fe9-sys-143"></span> **FE9-SYS-143 — On-hit weapon properties** — Applies poison, life drain, stat/status effects, brave behavior, crit suppression, unbreakable state, and other property-token logic.
144. <span id="fe9-sys-144"></span> **FE9-SYS-144 — Skill activation pipeline** — Checks the actor's skill bitset at specific combat stages, rolls chance-bearing skills, and dispatches their effects in caller-defined order.
145. <span id="fe9-sys-145"></span> **FE9-SYS-145 — Offensive proc skills** — Includes Aether, Astra, Luna, Sol, Lethality, Colossus, Stun, Flare, Roar, and Vortex; each changes strikes, defense, damage, healing, status, or outcome.
146. <span id="fe9-sys-146"></span> **FE9-SYS-146 — Defensive/reactive skills** — Includes Counter, Cancel, Miracle/Pray, Vantage, Guard/Wing Guard, and damage/protection traits.
147. <span id="fe9-sys-147"></span> **FE9-SYS-147 — Conditional passive skills** — Includes Wrath, Resolve, Gamble, Deadeye, Insight, Parity, Nihil, shade/provoke-style targeting modifiers, and other formula/eligibility changes.
148. <span id="fe9-sys-148"></span> **FE9-SYS-148 — Post-hit healing and reflection** — Applies Sol/Aether healing, Counter retaliation, Miracle survival, weapon drain, and similar effects after damage is known.
149. <span id="fe9-sys-149"></span> **FE9-SYS-149 — Death resolution** — Marks zero-HP units, runs death/retreat events, transfers drop items, removes or preserves the unit, updates counters, and checks objectives.
150. <span id="fe9-sys-150"></span> **FE9-SYS-150 — Dropped-item transfer** — Gives the defeated holder's flagged item to the victor or routes it according to inventory capacity/convoy rules.
151. <span id="fe9-sys-151"></span> **FE9-SYS-151 — Combat statistics tracking** — Updates battles, lifetime kills, kills this map, chapter of last kill, movement, EXP, and other per-unit counters used by reports/records.
152. <span id="fe9-sys-152"></span> **FE9-SYS-152 — Battle EXP calculation** — Builds base and kill components from effective-level differences and difficulty constants, then applies boss/thief bonuses, Paragon/Blossom modifiers, damage/no-damage gates, final-boss exclusion, and a 100-point cap.
153. <span id="fe9-sys-153"></span> **FE9-SYS-153 — EXP bar and level transition** — Animates the award, rolls over at 100, invokes level-up/promotion rules, and returns control to postbattle processing.
154. <span id="fe9-sys-154"></span> **FE9-SYS-154 — Battle-result handoff** — Separates numerical resolution from presentation and later consequences such as EXP animation, dialogue, deaths, victory, and event continuation.

## 10. Battle presentation systems

155. <span id="fe9-sys-155"></span> **FE9-SYS-155 — Map-versus-full battle selection** — Chooses map animation, full 3D battle, or disabled/conditional presentation based on options and context.
156. <span id="fe9-sys-156"></span> **FE9-SYS-156 — Battle staging** — Places attacker and defender on left/right marks, selects spacing and orientation, and aligns models with terrain/scenery.
157. <span id="fe9-sys-157"></span> **FE9-SYS-157 — Battle scenery selection** — Combines chapter/map and tile terrain to select 3D backdrop, ground, weather, and sky resources.
158. <span id="fe9-sys-158"></span> **FE9-SYS-158 — Class/model selection** — Maps runtime class, character overrides, weapon type, promotion state, and army texture to the correct battle model package.
159. <span id="fe9-sys-159"></span> **FE9-SYS-159 — Weapon-model selection** — Chooses and attaches the visible weapon or natural strike model, including forged-weapon visual parameters.
160. <span id="fe9-sys-160"></span> **FE9-SYS-160 — Battle animation state machine** — Plays approach, attack, hit/miss, critical, dodge, counter, skill, damage, death, return, and idle sequences in combat-log order.
161. <span id="fe9-sys-161"></span> **FE9-SYS-161 — Animation-event system** — Fires timed effects, sounds, hit numbers, camera changes, weapon trails, and gameplay presentation events from animation tracks.
162. <span id="fe9-sys-162"></span> **FE9-SYS-162 — Battle camera scripting** — Selects camera presets and interpolated shots for normal attacks, ranged attacks, criticals, skills, misses, deaths, and special bosses.
163. <span id="fe9-sys-163"></span> **FE9-SYS-163 — Spell and particle effects** — Resolves `EID_` effect identities into models, emitters, textures, colors, blend modes, timing, and target attachment.
164. <span id="fe9-sys-164"></span> **FE9-SYS-164 — Battle HUD** — Draws names, weapons, HP numbers and gauges, sides, damage transitions, and the EXP display over the 3D scene.
165. <span id="fe9-sys-165"></span> **FE9-SYS-165 — Damage-number and hit-effect presentation** — Synchronizes impact flashes, screen effects, numeric damage, HP gauge motion, and sound with the resolved strike.
166. <span id="fe9-sys-166"></span> **FE9-SYS-166 — Battle music and stingers** — Selects ordinary, boss, special-character, victory, death, and skill audio while preserving/restoring map music state.
167. <span id="fe9-sys-167"></span> **FE9-SYS-167 — Map battle animation** — Presents combat using map models, effects, sounds, numbers, and timings without loading full battle scenery.
168. <span id="fe9-sys-168"></span> **FE9-SYS-168 — Battle animation skip/acceleration** — Lets user options or input abbreviate presentation without changing the already resolved combat outcome.

## 11. Growth, class, and long-term unit progression

169. <span id="fe9-sys-169"></span> **FE9-SYS-169 — Level and EXP progression** — Stores level/EXP, applies the level cap, handles 100-point rollover, and interacts with promotion and no-EXP units.
170. <span id="fe9-sys-170"></span> **FE9-SYS-170 — Random level-up growth** — Rolls each stat's growth rate, grants guaranteed points for rates above 100%, applies modifiers, and respects class caps.
171. <span id="fe9-sys-171"></span> **FE9-SYS-171 — Fixed growth mode** — Uses saved per-stat accumulators and deterministic growth arithmetic rather than independent random rolls.
172. <span id="fe9-sys-172"></span> **FE9-SYS-172 — Stat caps** — Limits HP, Str, Mag, Skl, Spd, Lck, Def, and Res by class and affects level-up/promotion results.
173. <span id="fe9-sys-173"></span> **FE9-SYS-173 — Derived-stat system** — Produces current/max HP, Attack Speed, Hit, Avoid, Critical, Dodge, weight, movement, vision, capacity, and combat values from personal/class/item/state data.
174. <span id="fe9-sys-174"></span> **FE9-SYS-174 — Promotion eligibility** — Allows most beorc units to use a Master Seal at level 10+ or auto-promote after level 20; story and special-character exceptions use separate routes.
175. <span id="fe9-sys-175"></span> **FE9-SYS-175 — Promotion execution** — Changes class, adds promotion bonuses and weapon access, updates caps/models/skills, may request a secondary weapon, and preserves appropriate unit state.
176. <span id="fe9-sys-176"></span> **FE9-SYS-176 — Story promotion** — Promotes Ike and specific special units through chapter scripts rather than the generic seal/level route.
177. <span id="fe9-sys-177"></span> **FE9-SYS-177 — Promotion weapon choice** — Lets eligible cavalry or other classes select an additional weapon family and stores the resulting access/rank state.
178. <span id="fe9-sys-178"></span> **FE9-SYS-178 — Weapon experience and rank growth** — Awards WEXP per qualifying use, accumulates separate ranks for eight weapon families, and unlocks E–S equipment thresholds.
179. <span id="fe9-sys-179"></span> **FE9-SYS-179 — Skill capacity** — Adds the capacity costs of removable skills, enforces a unit/class limit, and exempts or protects innate/unit-specific skills as required.
180. <span id="fe9-sys-180"></span> **FE9-SYS-180 — Skill scroll learning/removal** — Converts scroll items into learned skills, validates restrictions/capacity, and allows eligible removable skills to be discarded.
181. <span id="fe9-sys-181"></span> **FE9-SYS-181 — Occult/mastery assignment** — Maps promoted classes to mastery skills and uses Occult scroll restrictions to grant the appropriate one.
182. <span id="fe9-sys-182"></span> **FE9-SYS-182 — Stat-booster and permanent bonus system** — Applies item-based permanent stat, build, or movement gains and serializes the changed unit values.
183. <span id="fe9-sys-183"></span> **FE9-SYS-183 — Bond system** — Gives fixed innate relationship bonuses independently of ordinary support progression.
184. <span id="fe9-sys-184"></span> **FE9-SYS-184 — Support progression** — Tracks compatible partners, chapter/conversation progress, C/B/A thresholds, a maximum of five concurrent supports, and rank state.
185. <span id="fe9-sys-185"></span> **FE9-SYS-185 — Support conversation availability** — Enables base conversations when chapter progress, partner survival/availability, current rank, and one-time flags permit.
186. <span id="fe9-sys-186"></span> **FE9-SYS-186 — Support battle bonuses** — Converts support ranks and affinities into proximity-based combat modifiers. The current archive still marks the complete affinity bonus table as unresolved.
187. <span id="fe9-sys-187"></span> **FE9-SYS-187 — Biorhythm progression** — Advances each character along a configured rhythm curve over chapter time/turns and exposes the current high/middle/low state to combat and skills.
188. <span id="fe9-sys-188"></span> **FE9-SYS-188 — Laguz transformation gauge** — Charges/depletes the gauge, triggers transform/revert, gates attacks, and stores current gauge state.
189. <span id="fe9-sys-189"></span> **FE9-SYS-189 — Laguz transformed-stat system** — Applies linked-class or transformation stat changes, model/animation/weapon changes, and difficulty-dependent growth handling.

## 12. Items, inventory, weapons, and economy

190. <span id="fe9-sys-190"></span> **FE9-SYS-190 — Item-definition system** — Defines item identity, type, attack type, rank, properties, categories, effects, cost, uses, might, hit, weight, critical, range, icon, WEXP, and modifiers.
191. <span id="fe9-sys-191"></span> **FE9-SYS-191 — Item-instance system** — Stores an item number, remaining uses, equipped/drop flags, and optional forge-record reference in a unit or convoy slot.
192. <span id="fe9-sys-192"></span> **FE9-SYS-192 — Personal inventory** — Provides eight serialized slots per unit, with command filtering, equipment, trading, use, dropping, and capacity behavior.
193. <span id="fe9-sys-193"></span> **FE9-SYS-193 — Convoy/warehouse** — Stores up to 200 party items and supports deposits, withdrawals, shop delivery, and availability gates.
194. <span id="fe9-sys-194"></span> **FE9-SYS-194 — Item legality/restriction system** — Combines class weapon types, WEXP rank, character/class locks, skill requirements, race/form, range, silence, and hard-coded special cases.
195. <span id="fe9-sys-195"></span> **FE9-SYS-195 — Durability and breaking** — Consumes uses, preserves unbreakable weapons, removes depleted instances, and updates menus/equipment.
196. <span id="fe9-sys-196"></span> **FE9-SYS-196 — Consumable effect system** — Handles healing, antidotes, Pure Water/Barrier, keys, stat boosters, promotion seals, skill scrolls, and story items.
197. <span id="fe9-sys-197"></span> **FE9-SYS-197 — Gold economy** — Maintains a party balance capped at 9,999,999 and separately records gold earned and spent for the next report.
198. <span id="fe9-sys-198"></span> **FE9-SYS-198 — Armory system** — Loads chapter/difficulty weapon stock, calculates prices from cost-per-use and maximum uses, buys to unit/convoy, and sells eligible items.
199. <span id="fe9-sys-199"></span> **FE9-SYS-199 — Vendor system** — Uses the same commercial flow for staves, consumables, and non-armory stock.
200. <span id="fe9-sys-200"></span> **FE9-SYS-200 — Sell shop** — Lists the player's possessions, validates sale restrictions/value, transfers gold, and updates report counters.
201. <span id="fe9-sys-201"></span> **FE9-SYS-201 — Per-chapter shop stock** — Selects Normal/Easy, Hard, or Maniac inventory sections for each chapter's armory, vendor, and forge.
202. <span id="fe9-sys-202"></span> **FE9-SYS-202 — Forge availability** — Allows one completed forge per chapter, sets a saved used-this-chapter flag, and falls back to default stock if chapter forge data is absent.
203. <span id="fe9-sys-203"></span> **FE9-SYS-203 — Forge stat customization** — Adjusts might, hit in 5-point steps, critical in 3-point steps, and weight within pricing and limit rules.
204. <span id="fe9-sys-204"></span> **FE9-SYS-204 — Forge appearance customization** — Stores a custom weapon name and RGBA attack-trail color on the forged instance.
205. <span id="fe9-sys-205"></span> **FE9-SYS-205 — Forge price calculation** — Prices upgrades from base weapon and selected stat changes, charges gold, and records spending.
206. <span id="fe9-sys-206"></span> **FE9-SYS-206 — Forge-record pool** — Allocates one of 48 persistent forge records and links the inventory instance through six flag bits; an unchecked 49th allocation returns zero and overwrites convoy slots 198–200.
207. <span id="fe9-sys-207"></span> **FE9-SYS-207 — Treasure and reward routing** — Sends scripted, chest, drop, visit, or clear rewards to a unit, convoy, gold/BEXP pool, or discard/full-inventory prompt as appropriate.

## 13. Bonus EXP, reports, records, and performance systems

208. <span id="fe9-sys-208"></span> **FE9-SYS-208 — Bonus EXP award calculation** — Computes chapter-clear BEXP from chapter-specific turn thresholds and optional objectives such as protecting NPCs or escaping extra units, with difficulty/chapter-specific values. The current archive confirms the pool and counters but still needs a dedicated trace of every award formula/table.
209. <span id="fe9-sys-209"></span> **FE9-SYS-209 — Turn-efficiency BEXP** — Compares the clear turn to one or more chapter thresholds and reduces or eliminates the time component as turns increase.
210. <span id="fe9-sys-210"></span> **FE9-SYS-210 — Objective BEXP** — Adds or subtracts chapter-specific awards for optional conditions implemented by events/flags, including survival, restraint, escape, or protection goals.
211. <span id="fe9-sys-211"></span> **FE9-SYS-211 — BEXP pool accounting** — Adds chapter awards to the party's persistent BEXP balance, subtracts BEXP assigned at the base, and saves the result as a 32-bit party value.
212. <span id="fe9-sys-212"></span> **FE9-SYS-212 — BEXP distribution** — Lets the player choose a unit and spend points toward its next level, invoking normal level-up mode/caps and promotion eligibility when the threshold is crossed.
213. <span id="fe9-sys-213"></span> **FE9-SYS-213 — BEXP breakdown display** — After the relevant clear/unlock, can show how much BEXP each criterion contributed at chapter end; this is distinct from Soren's narrative report.
214. <span id="fe9-sys-214"></span> **FE9-SYS-214 — Soren's Battle Report** — Presents the previous chapter's performance in the base and consumes four signed counters: gold earned, gold spent, Combat EXP, and Bonus EXP.
215. <span id="fe9-sys-215"></span> **FE9-SYS-215 — Report-counter lifecycle** — Updates counters while gold/EXP/BEXP change, displays them after the chapter, and resets them for the next reporting period without changing current balances.
216. <span id="fe9-sys-216"></span> **FE9-SYS-216 — MVP selection** — Selects the chapter's “Most Valuable Player” from unit performance data such as participation/kills/EXP. The exact weighting remains a research item and must not be inferred solely from the saved counters.
217. <span id="fe9-sys-217"></span> **FE9-SYS-217 — Per-unit records** — Tracks battles, lifetime kills, map kills, distance moved, last-kill chapter, and other counters used by records, reports, or endings.
218. <span id="fe9-sys-218"></span> **FE9-SYS-218 — Chapter clear history** — Stores up to 40 entries containing chapter, part, turns, and elapsed time for records and postgame display.
219. <span id="fe9-sys-219"></span> **FE9-SYS-219 — Play-time tracking** — Maintains runtime tick counters and per-clear elapsed time independently of turn count.
220. <span id="fe9-sys-220"></span> **FE9-SYS-220 — Completion records** — Aggregates clears, difficulty, playthrough number, character use/survival, and related data for postgame Records.

## 14. Staff, healing, status, and map-effect systems

221. <span id="fe9-sys-221"></span> **FE9-SYS-221 — Healing staff resolution** — Calculates target legality, range, healing amount, WEXP/EXP, durability, animation, and HP cap for Heal, Mend, Recover, Physic, and Fortify.
222. <span id="fe9-sys-222"></span> **FE9-SYS-222 — Status staff accuracy** — Uses Magic, target Resistance, Skill, and distance, clamps the result, and rolls hit for Silence, Sleep, Berserk, and related effects.
223. <span id="fe9-sys-223"></span> **FE9-SYS-223 — Restore system** — Removes eligible negative statuses and applies the staff's normal use/EXP/presentation flow.
224. <span id="fe9-sys-224"></span> **FE9-SYS-224 — Ward/Barrier/Pure Water system** — Applies a temporary Resistance bonus and decay behavior, with combat forecast and save-state integration.
225. <span id="fe9-sys-225"></span> **FE9-SYS-225 — Rescue staff** — Selects a friendly target at range and relocates it to a valid tile near the caster.
226. <span id="fe9-sys-226"></span> **FE9-SYS-226 — Warp staff** — Selects a friendly target and legal destination within its configured dynamic range; AI uses its own destination-scoring routine.
227. <span id="fe9-sys-227"></span> **FE9-SYS-227 — Hammerne repair** — Selects a repairable item and restores durability under item-specific restrictions.
228. <span id="fe9-sys-228"></span> **FE9-SYS-228 — Torch and vision effects** — Expands fog-of-war visibility for a duration and updates the visible-map state.
229. <span id="fe9-sys-229"></span> **FE9-SYS-229 — Unlock staff/skill** — Opens eligible doors/chests at range or through the map-action rules.
230. <span id="fe9-sys-230"></span> **FE9-SYS-230 — Poison status** — Applies on hit, persists for a duration, deals phase-based damage, displays an icon/effect, and can be cured.
231. <span id="fe9-sys-231"></span> **FE9-SYS-231 — Sleep status** — Prevents ordinary actions for its duration while phase/status counters continue.
232. <span id="fe9-sys-232"></span> **FE9-SYS-232 — Silence status** — Disables tomes/staves and affects both player command construction and AI action selection.
233. <span id="fe9-sys-233"></span> **FE9-SYS-233 — Berserk status** — Transfers action control/target rules to hostile AI-like behavior for its duration.
234. <span id="fe9-sys-234"></span> **FE9-SYS-234 — Temporary status lifecycle** — Stores status type/duration/bonuses, ticks them at defined phase boundaries, displays icons, serializes active state, and restores normal capability on expiration.
235. <span id="fe9-sys-235"></span> **FE9-SYS-235 — Terrain healing** — Restores a percentage of maximum HP on healing terrain at phase start, with capped HP and presentation.

## 15. Skill and special-command systems

236. <span id="fe9-sys-236"></span> **FE9-SYS-236 — Skill ownership bitset** — Represents learned, personal, class, and engine-trait skills by table position in a 128-bit runtime/save field.
237. <span id="fe9-sys-237"></span> **FE9-SYS-237 — Skill availability and restrictions** — Enforces character/class/weapon/form requirements and distinguishes removable skills from innate or hidden traits.
238. <span id="fe9-sys-238"></span> **FE9-SYS-238 — Skill activation chance** — Uses skill-specific parameters, unit stats, biorhythm where applicable, and the shared RNG at the combat/action stage chosen by native code.
239. <span id="fe9-sys-239"></span> **FE9-SYS-239 — Steal** — Adds a command when the thief/target/item/Speed/capacity rules permit, transfers a non-equipped item, and ends the action.
240. <span id="fe9-sys-240"></span> **FE9-SYS-240 — Chant** — Lets herons refresh eligible adjacent units, with form/target pattern and animation rules.
241. <span id="fe9-sys-241"></span> **FE9-SYS-241 — Canto** — Reopens movement after eligible actions for mounted/flying classes with remaining movement.
242. <span id="fe9-sys-242"></span> **FE9-SYS-242 — Shove/Smite** — Adds displacement commands and enforces unit type, weight, occupancy, and terrain limits.
243. <span id="fe9-sys-243"></span> **FE9-SYS-243 — Blossom and Paragon** — Modify earned EXP/growth behavior at the award/level-up stages rather than merely changing a displayed stat.
244. <span id="fe9-sys-244"></span> **FE9-SYS-244 — Tempest and Serenity** — Scale positive and negative biorhythm modifiers.
245. <span id="fe9-sys-245"></span> **FE9-SYS-245 — Parity and Nihil** — Suppress defined categories of terrain/support/skill bonuses or enemy combat skills during an exchange.
246. <span id="fe9-sys-246"></span> **FE9-SYS-246 — Resolve and Wrath** — Activate stat/critical changes under HP thresholds and feed the ordinary forecast/resolution formulas.
247. <span id="fe9-sys-247"></span> **FE9-SYS-247 — Provoke/Shade-style AI influence** — Changes how desirable a unit is as an AI target without altering allegiance or legality.
248. <span id="fe9-sys-248"></span> **FE9-SYS-248 — Charisma and Horror auras** — Apply local commander/group hit, avoid, or critical modifiers to units within three tiles under their side-specific rules.
249. <span id="fe9-sys-249"></span> **FE9-SYS-249 — Blessing/Boon and laguz support skills** — Apply phase-adjacent healing/status effects based on the owner's transformed state and nearby units.
250. <span id="fe9-sys-250"></span> **FE9-SYS-250 — Engine-trait skills** — Mark boss, final boss, promoted/higher class, laguz, flying, blessed armor, female, thief, transforming, weapon permission, and other native behaviors even when no player-facing skill appears.

## 16. Enemy and partner AI systems

251. <span id="fe9-sys-251"></span> **FE9-SYS-251 — AI phase scheduler** — Orders AI-controlled units, skips ineligible states, runs heal/attack/move/action steps, and advances to the next force.
252. <span id="fe9-sys-252"></span> **FE9-SYS-252 — AI bytecode/interpreter** — Executes per-unit behavior scripts from `cp_data.bin`, preserving script choices, steps, flags, and turn order in the save.
253. <span id="fe9-sys-253"></span> **FE9-SYS-253 — AI group/order assignment** — Gives deployed units behavior packages, commander relationships, destinations, activation conditions, and retreat/heal profiles.
254. <span id="fe9-sys-254"></span> **FE9-SYS-254 — Target enumeration** — Finds legal hostile, friendly, item, terrain, escape, and scripted targets based on the current AI step.
255. <span id="fe9-sys-255"></span> **FE9-SYS-255 — Attack scoring** — Scores candidate target/weapon/tile combinations from damage, hit, kill chance, counter risk, priorities, and script weights.
256. <span id="fe9-sys-256"></span> **FE9-SYS-256 — Movement scoring** — Combines path cost, destination goals, terrain, threat, target distance, formation, and script weights to choose a tile.
257. <span id="fe9-sys-257"></span> **FE9-SYS-257 — Per-unit threat map** — Estimates damage reachable by hostile weapons and lets AI avoid, tolerate, or minimize danger according to its script.
258. <span id="fe9-sys-258"></span> **FE9-SYS-258 — Phase danger map** — Builds broader opposing-force danger information used by healing, movement, Warp, and safety decisions.
259. <span id="fe9-sys-259"></span> **FE9-SYS-259 — Aggro/activation zones** — Keeps units stationary or on patrol until a turn, area, damage, unit, or script condition activates them.
260. <span id="fe9-sys-260"></span> **FE9-SYS-260 — Route and patrol AI** — Moves units through authored waypoints or toward map targets when no attack supersedes the route.
261. <span id="fe9-sys-261"></span> **FE9-SYS-261 — Boss/hold-position AI** — Restricts movement, prioritizes local targets, or defends a tile until script conditions change.
262. <span id="fe9-sys-262"></span> **FE9-SYS-262 — Escape AI** — Paths toward an escape/goal tile, evaluates danger, and removes/marks the unit when it completes the action.
263. <span id="fe9-sys-263"></span> **FE9-SYS-263 — Healing-need hysteresis** — Sets a needs-healing flag below one HP percentage and clears it only after a higher recovery threshold, preventing oscillation.
264. <span id="fe9-sys-264"></span> **FE9-SYS-264 — Self-healing item AI** — Chooses Vulnerary/Elixir based on missing HP and uses it from the safest reachable tile.
265. <span id="fe9-sys-265"></span> **FE9-SYS-265 — Ally item borrowing** — Takes a healing item from an adjacent/reachable ally when the unit has a free slot, then uses it.
266. <span id="fe9-sys-266"></span> **FE9-SYS-266 — Healing-terrain/refuge AI** — Seeks forts, healing tiles, staff users, or allies with healing items using path and danger comparisons.
267. <span id="fe9-sys-267"></span> **FE9-SYS-267 — Healing staff AI** — Prioritizes flagged wounded allies and selects Heal/Mend/Recover/Physic/Fortify by rank, inventory order, range, HP%, and count.
268. <span id="fe9-sys-268"></span> **FE9-SYS-268 — Status/support staff AI** — Selects Restore, Ward, Silence, Sleep, Berserk, Rescue, or Warp targets with staff-specific scoring and hit thresholds.
269. <span id="fe9-sys-269"></span> **FE9-SYS-269 — Steal AI** — Uses a configured desired-item list plus thief/action legality to choose theft targets.
270. <span id="fe9-sys-270"></span> **FE9-SYS-270 — Chant AI** — Searches valid refresh targets and evaluates the value and safety of a chant position.
271. <span id="fe9-sys-271"></span> **FE9-SYS-271 — Item-use AI** — Chooses usable consumables and special actions according to behavior script and current need.
272. <span id="fe9-sys-272"></span> **FE9-SYS-272 — Partner-unit orders** — Converts player-selected partner commands into AI priorities for yellow units.
273. <span id="fe9-sys-273"></span> **FE9-SYS-273 — Tie-breaking and scan order** — Resolves equal scores through deterministic candidate order, often map scan order or last-equal-candidate behavior.

## 17. Base, preparation, and between-battle systems

274. <span id="fe9-sys-274"></span> **FE9-SYS-274 — Base menu state** — Opens after Chapter 8 where allowed, tracks the opening event, and gates facilities by chapter and flags.
275. <span id="fe9-sys-275"></span> **FE9-SYS-275 — Base Info conversations** — Registers chapter-specific conversations, displays title/participants, runs each once, and records completion.
276. <span id="fe9-sys-276"></span> **FE9-SYS-276 — Support menu** — Lists available support conversations, plays them, raises rank/progress, and updates battle bonuses.
277. <span id="fe9-sys-277"></span> **FE9-SYS-277 — Manage/army organization** — Provides roster inspection, inventory, skills, supports, BEXP, and equipment operations outside a map action.
278. <span id="fe9-sys-278"></span> **FE9-SYS-278 — Base BEXP allocation** — Spends the shared BEXP pool on chosen units and invokes level/promotion behavior.
279. <span id="fe9-sys-279"></span> **FE9-SYS-279 — Base armory/vendor/sell shop** — Exposes the chapter/difficulty shop inventories and party storage/economy.
280. <span id="fe9-sys-280"></span> **FE9-SYS-280 — Base forge** — Runs base-weapon choice, stat customization, name/color selection, price confirmation, item delivery, and one-per-chapter lockout.
281. <span id="fe9-sys-281"></span> **FE9-SYS-281 — Base warehouse** — Provides unrestricted party/unit transfers where the convoy facility is available.
282. <span id="fe9-sys-282"></span> **FE9-SYS-282 — Base report presentation** — Plays Soren's report using the prior chapter's earned/spent and Combat/BEXP counters.
283. <span id="fe9-sys-283"></span> **FE9-SYS-283 — Combat preparation screen** — Allows deployment, unit positions, inventory, trade, supply, skills, map inspection, objectives, options, and battle start.
284. <span id="fe9-sys-284"></span> **FE9-SYS-284 — Deployment limit and selection** — Enforces mandatory units, prohibited units, maximum count, story availability, and surplus deployment state.
285. <span id="fe9-sys-285"></span> **FE9-SYS-285 — Starting-position assignment** — Maps selected player units to legal starting slots and supports swapping where the chapter permits.
286. <span id="fe9-sys-286"></span> **FE9-SYS-286 — Preparation map inspection** — Shows terrain, enemies, ranges, inventories, objectives, and formation before committing to the chapter.
287. <span id="fe9-sys-287"></span> **FE9-SYS-287 — Preparation save** — Serializes the exact roster, inventory, deployment, options, and chapter state for resumption before battle.

## 18. Dialogue, narrative, and cinematic systems

288. <span id="fe9-sys-288"></span> **FE9-SYS-288 — Message lookup and localization** — Resolves `MID_` and other text keys from language-specific message resources with fallback/loading rules.
289. <span id="fe9-sys-289"></span> **FE9-SYS-289 — Text decoding and control codes** — Parses glyphs, line/page breaks, pauses, color, names, choices, variables, sound, portraits, and other inline commands.
290. <span id="fe9-sys-290"></span> **FE9-SYS-290 — Conversation scene system** — Creates a layout, background, portrait seats, text boxes, actors, and script-controlled entrances/exits.
291. <span id="fe9-sys-291"></span> **FE9-SYS-291 — Conversation context/inheritance** — Retains or replaces background, seats, portraits, expressions, and layout between dialogue calls.
292. <span id="fe9-sys-292"></span> **FE9-SYS-292 — Portrait selection and animation** — Resolves character/expression portraits and animates mouth, eyes, blink, transitions, and visibility.
293. <span id="fe9-sys-293"></span> **FE9-SYS-293 — Dialogue text-box layout** — Measures and wraps text, places speaker names/cursors, paginates, and draws windows for the active scene type.
294. <span id="fe9-sys-294"></span> **FE9-SYS-294 — Dialogue input and auto-advance** — Handles text speed, advance, fast scroll, pause codes, choice prompts, backlog-like behavior, and script continuation.
295. <span id="fe9-sys-295"></span> **FE9-SYS-295 — Choice/branching dialogue** — Presents options, returns a result to the script, and gates branches/flags where used.
296. <span id="fe9-sys-296"></span> **FE9-SYS-296 — Map dialogue** — Plays conversations over the tactical map while coordinating camera, unit focus, music, and input lock.
297. <span id="fe9-sys-297"></span> **FE9-SYS-297 — Base/support/death-quote dialogue** — Routes specialized conversation tables or entry points while using the common message/presentation stack.
298. <span id="fe9-sys-298"></span> **FE9-SYS-298 — World-map presentation** — Renders Tellius regions, markers, routes, labels, narration, camera moves, and traveling icons for interchapter story scenes.
299. <span id="fe9-sys-299"></span> **FE9-SYS-299 — Illustration/still-image scenes** — Displays full-screen or layered artwork with fades, text, music, and script timing.
300. <span id="fe9-sys-300"></span> **FE9-SYS-300 — Real-time cutscene choreography** — Combines posed 3D models, skeletal animation, camera, lighting, effects, dialogue, and audio under event-script control.
301. <span id="fe9-sys-301"></span> **FE9-SYS-301 — Pre-rendered movie playback** — Decodes THP video/audio, handles skip/end behavior, and returns to the scripted scene.
302. <span id="fe9-sys-302"></span> **FE9-SYS-302 — Ending-card system** — Chooses surviving-character and paired/special endings, inserts records/variables, and sequences epilogues.
303. <span id="fe9-sys-303"></span> **FE9-SYS-303 — Staff credits** — Runs credits presentation, music, images, names, and completion transition.

## 19. Graphics, models, animation, and effects systems

304. <span id="fe9-sys-304"></span> **FE9-SYS-304 — Render pipeline** — Submits 3D map/battle geometry and 2D UI in ordered passes with GameCube GX state, depth, blending, and render targets.
305. <span id="fe9-sys-305"></span> **FE9-SYS-305 — Texture system** — Loads TPL images and palettes, chooses formats/mipmaps, uploads textures, and binds them to UI/materials/effects.
306. <span id="fe9-sys-306"></span> **FE9-SYS-306 — 2D sprite/UI compositor** — Draws windows, icons, portraits, cursors, numbers, gauges, backgrounds, and text by layer and screen coordinates.
307. <span id="fe9-sys-307"></span> **FE9-SYS-307 — UI layout system** — Instantiates `Rect.bin`/DBX widget trees, positions/scales elements, applies visibility, and fills captions/numbers/gauges at runtime.
308. <span id="fe9-sys-308"></span> **FE9-SYS-308 — Font and glyph system** — Loads bitmap fonts, maps encoded characters to glyphs, applies metrics/spacing/color, and supports system/dialogue/numeric styles.
309. <span id="fe9-sys-309"></span> **FE9-SYS-309 — Icon atlas system** — Resolves item, skill, status, weapon, affinity, objective, and menu icon indices to cells in shared texture sheets.
310. <span id="fe9-sys-310"></span> **FE9-SYS-310 — 3D model loading** — Parses `.g`, `.gs`, and `.ga` resources into meshes, materials, skeletons, shapes, and animation data.
311. <span id="fe9-sys-311"></span> **FE9-SYS-311 — Material/render-state system** — Controls texture stages, colors, alpha/blending, culling, depth, lighting, and special surface behavior.
312. <span id="fe9-sys-312"></span> **FE9-SYS-312 — Skeleton and skinning** — Evaluates bone hierarchies and weights to deform character, creature, weapon, and prop meshes.
313. <span id="fe9-sys-313"></span> **FE9-SYS-313 — Animation-track evaluation** — Samples translation/rotation/scale tracks with interpolation, loops, transitions, and per-animation events.
314. <span id="fe9-sys-314"></span> **FE9-SYS-314 — Map-model registry** — Maps animation identities to folders, weapon types, army textures, actions, and map model resources through `FE8Anim.bin`.
315. <span id="fe9-sys-315"></span> **FE9-SYS-315 — Model-slot and override system** — Chooses character-specific versus class-default models, textures, rigs, and animations.
316. <span id="fe9-sys-316"></span> **FE9-SYS-316 — Map-unit animation** — Runs idle, move, selected, attack, damage, transform, action, and death sequences on tactical models.
317. <span id="fe9-sys-317"></span> **FE9-SYS-317 — Posing system** — Places and poses models for conversations/cutscenes independent of tactical unit state.
318. <span id="fe9-sys-318"></span> **FE9-SYS-318 — Effect registry** — Maps effect identifiers through `FE8Effect.bin` to reusable spell, skill, environment, and UI effects.
319. <span id="fe9-sys-319"></span> **FE9-SYS-319 — Particle emitter system** — Spawns timed particles with texture, motion, lifetime, color, scale, blend, attachment, and billboard behavior.
320. <span id="fe9-sys-320"></span> **FE9-SYS-320 — Screen-transition system** — Provides fades, wipes, flashes, letterboxing, color overlays, and scene-to-scene masking.
321. <span id="fe9-sys-321"></span> **FE9-SYS-321 — Lens flare and post-effect system** — Applies battle/cutscene overlays and EFB-based effects whose data lives in battle DBX resources.
322. <span id="fe9-sys-322"></span> **FE9-SYS-322 — Performance/culling system** — Avoids drawing off-screen or hidden geometry, manages model/texture lifetime, and keeps map/battle rendering within console limits.

## 20. Audio and video systems

323. <span id="fe9-sys-323"></span> **FE9-SYS-323 — Music selection system** — Chooses map, phase, base, battle, boss, story, victory, defeat, and menu tracks from script/chapter/context state.
324. <span id="fe9-sys-324"></span> **FE9-SYS-324 — Music transition system** — Starts, stops, pauses, fades, loops, and restores tracks across dialogue, battle, phase, and scene changes.
325. <span id="fe9-sys-325"></span> **FE9-SYS-325 — MusyX sequence/sample system** — Loads and plays sequenced music and sample resources through the GameCube audio engine.
326. <span id="fe9-sys-326"></span> **FE9-SYS-326 — Streamed audio system** — Decodes STM/DSP-ADPCM streams, loops at authored points, and buffers playback from disc.
327. <span id="fe9-sys-327"></span> **FE9-SYS-327 — Sound-effect bank system** — Resolves named/numbered effects from `gcfesnd.bin` and associated banks for UI, map, battle, dialogue, and ambience.
328. <span id="fe9-sys-328"></span> **FE9-SYS-328 — Positional/attached sound** — Associates effects with units, objects, animations, or world positions where applicable.
329. <span id="fe9-sys-329"></span> **FE9-SYS-329 — Voice/utterance system** — Plays short character vocals, battle cries, or cutscene voice assets synchronized to events/animations.
330. <span id="fe9-sys-330"></span> **FE9-SYS-330 — Audio mixer/options** — Applies music and sound volume settings and manages simultaneous channels/priorities.
331. <span id="fe9-sys-331"></span> **FE9-SYS-331 — THP video decoder** — Decodes JPEG-like frames and per-frame DSP audio, synchronizes them, handles padding/timing, and displays pre-rendered movies.
332. <span id="fe9-sys-332"></span> **FE9-SYS-332 — Sound Room** — Unlocks and plays a fixed table of 64 tracks while cycling configured background illustrations.

## 21. User interface, input, options, and help systems

333. <span id="fe9-sys-333"></span> **FE9-SYS-333 — Controller input mapping** — Converts GameCube buttons/sticks into cursor motion, confirmation, cancellation, unit cycling, zoom, camera rotation, status, skip, and shortcuts.
334. <span id="fe9-sys-334"></span> **FE9-SYS-334 — Input focus and repeat** — Routes input to the active menu/widget, handles held-button repeat, locks input during scheduled work, and restores focus on return.
335. <span id="fe9-sys-335"></span> **FE9-SYS-335 — Title and main menu** — Exposes New Game, Continue, Copy/Erase-style file operations, Extras, and unlocked options according to system data.
336. <span id="fe9-sys-336"></span> **FE9-SYS-336 — File-select UI** — Reads save summaries, validates blocks, shows chapter/difficulty/play time, and launches/copies/deletes the selected playthrough.
337. <span id="fe9-sys-337"></span> **FE9-SYS-337 — Map HUD** — Displays terrain, unit, phase, turn, cursor, objective, help, and contextual command information.
338. <span id="fe9-sys-338"></span> **FE9-SYS-338 — Unit status screen** — Pages through stats, weapons, skills, supports, biorhythm, biography, conditions, and help descriptions.
339. <span id="fe9-sys-339"></span> **FE9-SYS-339 — Map command menu** — Provides Unit, Status, Options, Objective, Guide, Suspend, End, and context-specific entries.
340. <span id="fe9-sys-340"></span> **FE9-SYS-340 — Unit command menu** — Builds move/action commands dynamically and shows unavailable/invalid choices through omission or feedback.
341. <span id="fe9-sys-341"></span> **FE9-SYS-341 — List and sorting system** — Displays army/unit/item lists with cursor memory, sort keys, paging, icons, and help text.
342. <span id="fe9-sys-342"></span> **FE9-SYS-342 — Help-text system** — Resolves contextual descriptions for stats, skills, items, terrain, commands, objectives, and options.
343. <span id="fe9-sys-343"></span> **FE9-SYS-343 — Tutorial popup system** — Uses per-chapter trigger data and tutorial state to show timely instructional windows.
344. <span id="fe9-sys-344"></span> **FE9-SYS-344 — Tutorial/Guide browser** — Organizes unlocked topics into groups and entries, tracks read/unread bits, and presents diagrams/text.
345. <span id="fe9-sys-345"></span> **FE9-SYS-345 — Options system** — Stores message speed, unit/terrain windows, battle animation mode, unit movement speed, music/SFX volume, fixed growths, BEXP display, and related switches.
346. <span id="fe9-sys-346"></span> **FE9-SYS-346 — Screen calibration** — Stores horizontal/vertical screen position and brightness in system data shared across save blocks.
347. <span id="fe9-sys-347"></span> **FE9-SYS-347 — Confirmation/error dialogs** — Handles destructive choices, full inventory/convoy, insufficient gold/BEXP, invalid targets, unsaved exit, and other modal decisions.
348. <span id="fe9-sys-348"></span> **FE9-SYS-348 — Pause/suspend flow** — Saves or freezes permitted state, returns to title or resume point, and distinguishes temporary Suspend from ordinary saves.

## 22. Save, load, persistence, and integrity systems

349. <span id="fe9-sys-349"></span> **FE9-SYS-349 — Memory Card file management** — Creates one 19-block GameCube save file, checks card presence/space/errors, and manages file metadata/banner/icon.
350. <span id="fe9-sys-350"></span> **FE9-SYS-350 — Save-block system** — Stores multiple playthrough blocks plus duplicated system data and selects/validates the appropriate block on load.
351. <span id="fe9-sys-351"></span> **FE9-SYS-351 — Save serialization** — Writes tagged party/map/unit/convoy/forge/tile chunks with fixed and variable lengths in the exact runtime-to-save mapping.
352. <span id="fe9-sys-352"></span> **FE9-SYS-352 — Load reconstruction** — Rebuilds party, units, inventories, flags, map state, camera, weather, AI progress, and resume point from serialized chunks.
353. <span id="fe9-sys-353"></span> **FE9-SYS-353 — Save integrity/versioning** — Uses identifiers, version stamps, size/layout assumptions, and validation to avoid overwriting or loading incompatible data.
354. <span id="fe9-sys-354"></span> **FE9-SYS-354 — System-data replication** — Copies console-wide unlock/options data into every block and chooses the newest copy at boot.
355. <span id="fe9-sys-355"></span> **FE9-SYS-355 — Autosave/chapter-clear save** — Writes state at defined campaign transitions, including the intentional combination of next chapter number and just-cleared map name.
356. <span id="fe9-sys-356"></span> **FE9-SYS-356 — Map/checkpoint save** — Preserves turn, phase, cursor, units, tile objects, flags, fog/weather/camera, AI interpreter state, and active statuses.
357. <span id="fe9-sys-357"></span> **FE9-SYS-357 — Base/preparation save** — Preserves between-battle edits, deployment choices, forge/shops/report state, and the correct resume routing.
358. <span id="fe9-sys-358"></span> **FE9-SYS-358 — Suspend save** — Captures an in-battle resume point under Suspend-specific UI and lifecycle rules.
359. <span id="fe9-sys-359"></span> **FE9-SYS-359 — Save compatibility system** — Depends on stable table order and structural sizes; reordering character/class/item records or expanding serialized structures can reinterpret or break old saves.

## 23. Unlocks, extras, records, and external-link systems

360. <span id="fe9-sys-360"></span> **FE9-SYS-360 — Clear/unlock flags** — Records completed difficulties and unlocks Trial Maps, Records, Theater, Sound Room, galleries, and connection features.
361. <span id="fe9-sys-361"></span> **FE9-SYS-361 — Playthrough-number system** — Stores IDs of completed runs and displays the next playthrough count on a new file.
362. <span id="fe9-sys-362"></span> **FE9-SYS-362 — Trial Map unlocks** — Unlocks six trial maps according to completion difficulty and GBA-link conditions.
363. <span id="fe9-sys-363"></span> **FE9-SYS-363 — Extras hub** — Gates and launches Theater, Sound Room, Records, Trial Maps, illustrations, and connection features.
364. <span id="fe9-sys-364"></span> **FE9-SYS-364 — Movie Theater** — Lists unlocked pre-rendered movies and replays them outside the campaign.
365. <span id="fe9-sys-365"></span> **FE9-SYS-365 — Illustration/character gallery** — Displays unlocked artwork, including content obtained through GBA connection.
366. <span id="fe9-sys-366"></span> **FE9-SYS-366 — Records viewer** — Presents clear history, turns/time, character records, difficulty clears, and other accumulated statistics.
367. <span id="fe9-sys-367"></span> **FE9-SYS-367 — GBA link protocol** — Communicates through the GameCube–Game Boy Advance cable with Fire Emblem or The Sacred Stones after FE9 is cleared.
368. <span id="fe9-sys-368"></span> **FE9-SYS-368 — GBA-link reward system** — Unlocks character art and additional Trial Maps according to the connected GBA title/data.
369. <span id="fe9-sys-369"></span> **FE9-SYS-369 — Character-met tracking** — Sets one bit per deployed character for gallery/records/unlock purposes.
370. <span id="fe9-sys-370"></span> **FE9-SYS-370 — New-game-after-clear options** — Exposes post-clear configuration such as Fixed growth mode or BEXP breakdown where the relevant unlock permits it.

## 24. Developer, diagnostic, and content-tool systems

371. <span id="fe9-sys-371"></span> **FE9-SYS-371 — Developer/debug menus** — Dormant or retail-accessible internal screens inspect maps, battles, models, scripts, resources, and runtime state.
372. <span id="fe9-sys-372"></span> **FE9-SYS-372 — Internal battle tool** — Loads participants, models, scenery, cameras, and effects for battle testing independently of a campaign encounter.
373. <span id="fe9-sys-373"></span> **FE9-SYS-373 — Chapter jump/test flow** — Starts selected chapters or parts with development setup rather than normal campaign progression.
374. <span id="fe9-sys-374"></span> **FE9-SYS-374 — Resource viewers** — Display model, animation, texture, effect, sound, UI, or map resources for development verification.
375. <span id="fe9-sys-375"></span> **FE9-SYS-375 — Logging and assertions** — Separates the disabled game debug-print stub from the active engine assertion screen/reset handler and SDK `OSReport`/panic/exception output paths.
376. <span id="fe9-sys-376"></span> **FE9-SYS-376 — Build timestamps and author metadata** — Preserve provenance in data containers and can help distinguish retail resources and revisions.

## 25. Cross-cutting rule systems

377. <span id="fe9-sys-377"></span> **FE9-SYS-377 — Randomness ownership** — Shares one unsaved gameplay RNG stream across hit, critical, skills, growths, AI, scripts, and some presentation calls, while a separate visual stream drives rain and animation variation; call order within each stream is mechanically significant.
378. <span id="fe9-sys-378"></span> **FE9-SYS-378 — Rule priority/override system** — Applies hard overrides such as final-boss no-EXP, blessed armor, crit sealing, Parity/Nihil, forced scripted outcomes, and invulnerability at defined stages rather than as generic stat modifiers.
379. <span id="fe9-sys-379"></span> **FE9-SYS-379 — Legality-before-execution pattern** — Menus, AI, and scripts first test whether an action is legal, then resolve it, spend resources, update state, present it, and fire consequences.
380. <span id="fe9-sys-380"></span> **FE9-SYS-380 — Definition-instance-runtime separation** — Keeps reusable database definitions separate from inventory/unit instances and from transient battle/map objects; many modding mistakes come from confusing these layers.
381. <span id="fe9-sys-381"></span> **FE9-SYS-381 — Difficulty and region overrides** — Reuses common systems while replacing constants, data sections, deployments, tutorials, unlock conditions, and a few native rules.
382. <span id="fe9-sys-382"></span> **FE9-SYS-382 — Serialization boundary** — Distinguishes persistent progression from chapter-local state and unsaved presentation state, deciding what survives reload, map transition, or new game.
383. <span id="fe9-sys-383"></span> **FE9-SYS-383 — Script/native division of responsibility** — Uses native code for generic formulas and engine operations while scripts compose chapter-specific goals, BEXP criteria, recruitment, dialogue, reinforcements, and cinematic flow.
384. <span id="fe9-sys-384"></span> **FE9-SYS-384 — Simulation/presentation separation** — Resolves authoritative results before or independently of animations, UI, audio, and cinematics, allowing skips and alternative battle-display modes without changing outcomes.

## Coverage notes and known research gaps

The inventory is intentionally broader than the current set of published system articles. The largest remaining system-level gaps are:

- the exact table/native pipeline for every chapter's **Bonus EXP calculation**, including all difficulty and optional-objective adjustments;
- the exact **MVP/Battle Report selection and grading** logic beyond the four confirmed report counters;
- the complete **support affinity bonus table** and runtime consumer;
- a fully ordered matrix of **skill interactions and suppression priority**;
- exact player-side duration/tick rules for every **status and temporary bonus**;
- some **fog, hidden-item, partner-order, and postgame Records** details;
- several low-level graphics fields, battle-event codes, and developer-tool controls catalogued in [Open Questions](unexplored.md).

For the file-oriented editorial roadmap, see the [Master Topic Registry](topic-registry.md). For established technical findings, begin with [Combat Resolution](../systems/combat-mechanics.md), [Map Actions](../systems/map-actions.md), [Economy](../systems/economy.md), [Skills](../systems/skills.md), [Save Format](../formats/save-format.md), and [`cp_data.bin`](../formats/cp-data-format.md).
