---
id: "runtime-engine-architecture"
title: "Runtime Engine Architecture"
description: "How scenes, scheduled work, global services, rules, scripts, simulation, presentation, and persistence divide responsibility"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Engine", "Executable", "Architecture"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/runtime-engine-architecture.md"
system_entries: ["FE9-SYS-009", "FE9-SYS-010", "FE9-SYS-011", "FE9-SYS-012", "FE9-SYS-377", "FE9-SYS-378", "FE9-SYS-379", "FE9-SYS-380", "FE9-SYS-382", "FE9-SYS-383", "FE9-SYS-384"]
system_reviewed: ["FE9-SYS-009", "FE9-SYS-010", "FE9-SYS-011", "FE9-SYS-012", "FE9-SYS-377", "FE9-SYS-378", "FE9-SYS-379", "FE9-SYS-380", "FE9-SYS-382", "FE9-SYS-383", "FE9-SYS-384"]
system_reviewed_with_gaps: ["FE9-SYS-009", "FE9-SYS-012"]
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: ["FE9-SYS-009: Heap selection and ownership are not mapped for every allocation family or scene transition.", "FE9-SYS-012: The complete global-service inventory and mutation ownership map have not been reconstructed."]
system_gap_work: ["FE9-SYS-009: Traced the process pool, recursive process teardown, MSL allocation, one-shot actor allocation, and representative menu/map resource cleanup; allocator/free ownership is not complete for every family.", "FE9-SYS-012: Surveyed boot initialization, party globals, chapter state, registries, audio, resources, and save reconstruction; remaining writable globals lack a complete writer/lifetime census."]
---
# Runtime Engine Architecture

Path of Radiance is not one uninterrupted “game mode.” It is a collection of processes and services that create short-lived objects around longer-lived playthrough state. This matters to modders because changing the right data at the wrong lifetime can appear to work, then vanish at the next scene or leave a stale object behind. A useful model has four layers: **definitions** describe reusable content, **instances** hold mutable gameplay state, **scheduled work** advances actions and presentation, and **persistence** selects what survives reconstruction.

The US executable provides a concrete backbone for that model. Its main game flow is encoded as process scripts, not as one giant native loop. The top-level `GameController` starts child processes for title, file selection, the base, preparations, the tactical map, saves, game over, and the ending. Native routines and chapter event scripts supply work to those processes. Long-lived databases and party state remain available while temporary UI, map, actor, and effect objects are created and destroyed around them.

## Objects and scenes

<span id="fe9-sys-009"></span> **FE9-SYS-009 — Memory allocation and object lifetime.** Boot resources and databases can outlive many scenes; chapter maps, widgets, model instances, script frames, and battle effects are created for a narrower context. The process system uses a fixed 256-slot pool at `0x802A66D8`, with `0x70` bytes per process. A process links to its child at `+0x1C`; `destroy_process_node_and_children` (`0x8000C6AC`) recursively tears the tree down in post-order, calls each node's destructor, and returns the slots to the free list at `0x80367148`. This is observable ownership rather than a naming convention: a parent may wait for a child and later destroy its whole subtree.

Other objects use their own allocation patterns. For example, `load_and_apply_combat_animation_temp` (`0x8013B064`) allocates a `GActor`, loads and applies one combat animation, rebuilds its buffers, and destroys the actor before returning. File-menu chapter-name textures are queued for the menu and explicitly released by its cleanup routines. Master database records, by contrast, are built during boot and retained in global tables for later lookup. These examples establish at least three lifetimes: one-call temporaries, scene/process-owned resources, and application- or playthrough-lived state.

Destroying a scene must release its temporary objects without erasing party state. A leaked object wastes scarce console memory; a prematurely released shared resource leaves later users holding an invalid reference. A mod should therefore identify an object's owner and teardown path before retaining a pointer or injecting new allocations.

<span id="fe9-sys-010"></span> **FE9-SYS-010 — Frame scheduler and game loop.** The process system is the confirmed cooperative scheduler for game-flow work. A process record stores its script base at `+0x00`, program counter at `+0x04`, per-frame wait routine at `+0x10`, name at `+0x14`, and an owner-available field at `+0x60`. Its word-coded instructions include sleep until a later frame, call a routine, repeat a routine each frame, wait until another named process ends, start a child and block the parent, and jump to a label. `get_frame_counter` (`0x800067B4`) exposes a free-running tick count.

`start_child_process_blocking` (`0x8000CAA0`) starts a child, marks it blocking, and increments a wait byte on the parent. This mechanism appears on the combat path: `execute_pending_map_action` creates authoritative battle context, calculates EXP, prepares result/presentation state, and then starts a blocking child that carries the visible battle and post-battle sequence. Dialogue, movement, fades, and event calls use the same broad pattern—schedule work, yield, and resume after a completion condition—instead of freezing the console in a synchronous function.

The retail `main` loop at `0x80014B34` establishes the enclosing order. Its loop is deliberately render-first: it presents state produced by the preceding logic tick, samples input, then advances logic for the next presentation.

| Order | Main-thread stage | Confirmed work |
|---:|---|---|
| 1 | Frame/display setup | Begin frame accounting, set the view/frustum and dispatch process queue 5 |
| 2 | Camera and diagnostic overlay preparation | Update the active camera; optionally enqueue performance, safe-frame, sound, process-tree and Prim2D diagnostics |
| 3 | Render submission | Reset counters, apply cached camera/GX state, initialize the render pipeline, then apply perspective state |
| 4 | Late presentation queues | Dispatch process queues 6 then 7; these own transition/global presentation work such as screen transitions and persistent display helpers |
| 5 | Present/finalize | Complete the frame; a display-suppressed branch clears camera lists but rejoins here |
| 6 | Frame pacing and controller sample | `pad_process_frame_input` waits for the target interval, calls `PADRead`, clamps four channels, computes held/pressed/released and repeat state, and services rumble expiry |
| 7 | Logic preparation | Reset the immediate 2D state, then dispatch process queues 2, 3 and 4 in that exact order. Queue census places battle-map/tutorial/event roots in 2, ordinary game/UI/script work mainly in 3, and actor/effect/resource work mainly in 4 |
| 8 | Commit frame timing | Finish performance totals, prepare graphics state for the next pass, increment the frame counter, sample `OSGetTime`, and update debug-input state |

Each queue is a doubly linked list of roots. `start_process(script, queue)` appends a root when the second argument is 0–7; a process pointer instead appends a child. The dispatcher walks each root's linked process tree, executes script opcodes until they yield, invokes an installed wait/per-frame routine when eligible, then invokes the process callback and visits children. A blocking child prevents its parent from advancing but does not reorder the other roots or queues.

Queues 0 and 1 are not dispatched by the retail main loop; the direct-call census finds one queue-0 creation and no queue-1 creation, so they are reserved/inactive for ordinary scheduled work. The six live phases are 5→6→7 before input and 2→3→4 after input. This is stronger than an incidental observation: `conditional_state_transition_callback` has exactly six direct callers, all in `main`, with those literal indices.

Audio is the deliberate concurrency exception. `main` constructs the audio engine entry as a separate OS-thread/run-queue object, and the sequencer/DSP callbacks advance independently of the six main-thread process queues. Game code submits named play/fade/stop requests; it must use the audio owner's handles/completion rules rather than assuming audio runs between any two main-thread callbacks. Input, process logic, camera preparation, render submission, and frame-counter update now have an exact main-thread order, while audio is explicitly asynchronous rather than left “unknown.”

<span id="fe9-sys-011"></span> **FE9-SYS-011 — Scene/state machine.** `GameController` (`0x802832FC`) is the top process, started at boot by `0x80005C60`. Other code writes its next-label field and `game_controller_goto_next_label` advances to that state. Decoded labels cover boot and title, file and trial menus, chapter loading, opening story, base, preparations, `E_BMapMain`, chapter-part continuation, save routing, game over, reload, trial resume, finale, and return to title.

The tactical map is another process state machine. `E_BMapMain` polls `gf_complete` and `gf_gameover`; completion routes through its clear label, advances the chapter, and returns control to `GameController`, while failure starts `E_GameOver`. Its quit label frees map and actor state and unloads common battle-map resources. The active-scene resolver checks named phases in priority order—`E_BMapPlph`, `E_CP_PhaseMain`, `E_BMapMain`, then `GameController`—and a generic recursive walker visits the selected process and its children. These details explain why “scene” in FE9 often means a named process subtree rather than a single monolithic C++ class.

Title, file selection, story, base, preparation, map, full battle, clear, Extras, and trial maps therefore own different UI and transient resources. A transition has an exit path, destination construction, and resume context. The saved resume point chooses which `GameController` label reconstructs state; it is not a snapshot of old C++ objects, process PCs, widgets, or loaded textures.

The decoded process descriptors close the major-scene ownership map. A live tree is dynamic—menus and effects add short-lived descendants—but its root and destruction contract are fixed by these parent/child edges:

| Route | Constructing owner and child | Exit/destruction contract | Continuation |
|---|---|---|---|
| Title | `GameController` label 2 starts `E_Title` (`0x8028C8E0`) as a blocking child | Descriptor installs `0x800A8AE4` as `on_end`; its terminal state ends the child subtree | Controller label 5, the file menu |
| File selection/save | Controller labels 5, 6, 19, and 20 start `E_FileMenu` (`0x80299CC4`) through mode-specific wrappers | Descriptor installs `0x801D3BD0` as `on_end`; the wrapper stores the requested mode in child state | Selected load/resume label, new chapter, or the caller's post-clear/part route |
| Opening story | Controller labels 10–15 invoke `Opening0`, optional `Opening1`, and optional `Opening2` through the event VM | No independent scene root exists to preserve: each script call blocks/yields through its own presentation children and returns to the controller | Base/preparations/map according to which openings exist |
| Base | Controller label 14 starts `BasesProc` (`0x80293D8C`) as a blocking child | Descriptor installs `0x80169870` as `on_end`; its internal labels own the base submenus and converge on label 17/end | Opening1 or preparations/map |
| Preparations | Controller label 15 starts `BMapSallyProc` (`0x8028F814`) as a blocking child | Descriptor installs `0x8011A184` as `on_end`; its menu states converge on labels 18–19/end | Opening2, then tactical map |
| Tactical map | Controller label 16 starts `E_BMapMain` (`0x80284E78`), plus its opening-BGM child | Clear, chapter-part, defeat, and quit converge on label 6, which frees map/actor state and unloads common map resources before ending | Controller labels 19, 20, 25, or a sender-selected transition |
| Full battle | `execute_pending_map_action` owns the blocking battle child beneath the active tactical process after resolving the authoritative exchange | Battle presentation and post-battle consequences drain, then the child subtree ends; it is not a sibling controller scene | Resume the waiting tactical action/turn process |
| Game over | `E_BMapMain` label 3 starts `E_GameOver` (`0x8029B198`) as a blocking child | The descriptor's final calls/fade end the child; `E_BMapMain` then selects controller label 25 and performs common map teardown | Title route |
| Extras/trial selection | Controller label 30 starts `E_TrialMenu` (`0x8029B1F8`) as a blocking child | Its menu states converge on the terminal cleanup call and end | Selected trial initializes a fresh party and enters chapter label 10; cancel returns through the file/Extras route |
| Trial result | Controller label 32 starts `E_TrialResult` (`0x8029B27C`) as a blocking child | Result display converges on label 99, cleanup, and end | Controller label 6, returning to Extras/file flow |
| Ending | Controller label 24 starts `Finale` (`0x8029B438`) as a blocking child | Its fixed call chain forces Endgame context, runs finale/ending work, records completion, and ends | Controller label 3/title |

Generic process destruction supplies the final invariant: ending a node recursively destroys its descendants in post-order and calls each installed destructor before returning all process slots to the free list. Consequently, transient descendants do not need a controller-specific edge to have named ownership—their nearest process parent owns them. The table is the complete major-state topology; runtime tree captures are diagnostics for leaks or a modded route, not missing evidence for the retail state machine.

<span id="fe9-sys-012"></span> **FE9-SYS-012 — Global service and singleton state.** Cross-scene facilities provide loaded resources, party/save state, options, audio, input, RNG, and current chapter/difficulty. Concrete examples include the master-data table pointers built by `load_master_game_database`, party state rooted at `0x80330708`, process and resource registries, the current turn and chapter fields, audio scene state, and fixed pools for units, processes, convoy items, and forge results. Named lookup services connect symbolic IDs to data records and loaded resources, allowing a newly built scene to recover the same definitions without embedding their addresses in save data.

“Global” does not mean immutable or ownerless. Party gold, BEXP, current chapter, resume point, and event flags are mutated during play and serialized. Audio and loaded-resource services hold runtime state but are reconstructed rather than copied verbatim into a save. Boot-built definition tables are read broadly but should be changed through their data-loading path if every consumer must see the change. Treating all three categories as interchangeable is a common source of mods that work only until reload or scene transition.

Global services are classified by lifetime and writer contract rather than by an exhaustive address list: boot definitions are loader-owned and broadly read; party/chapter/unit state has named mutation and serialization owners; runtime registries expose processes/resources/audio/input/RNG; and individual process trees own transient presentation/control objects. An unidentified writable address must be traced before editing, but it does not create another service-lifetime category.

## Lifecycle and ownership rules

The following sequence is the practical ownership model supported by the executable traces:

1. Boot initializes platform services, the process framework, shared resource registries, audio, and master game databases.
2. `GameController` chooses a major flow state and starts the appropriate child process, often waiting for that child to finish.
3. The child constructs its UI, map, actors, scripts, and other scene-local objects. Those objects may themselves own child processes or loaded resources.
4. Per-frame callbacks and process instructions advance the active work. A waiting parent does not continue until the blocking child releases it.
5. Authoritative gameplay changes are written to unit, party, chapter, flag, or tile state; presentation objects display those results.
6. On exit, cleanup releases the process subtree and scene resources. The next scene is built from surviving runtime state or, after loading, from serialized data.

This is a rule of evidence, not a guarantee that every allocation follows one allocator. Fixed pools, MSL allocation, resource handles, and subsystem-specific object factories coexist. The relevant question is always “who releases this object, and which state is expected to survive after that release?”

## Cross-cutting rule ownership

<span id="fe9-sys-377"></span> **FE9-SYS-377 — Randomness ownership.** FE9 has two separately seeded random streams. Gameplay uses the three-halfword state at `0x80367150..0x80367155`: `roll_true_hit` advances it twice for Hit, while `roll_percent_chance` advances it once for Critical, skill and status activation, random level-up growth, and Shove/Smite resistance. `roll_random_int` advances the same state for deployment autolevels and variance, character-table random initialization, pathfinding and CP-action choices, chapter initialization, damage-event variation, script `GetRnd`, mouth/window animation, and developer battle-test setup. Thus presentation calls made through `roll_random_int` can perturb later gameplay results. A separate one-word stream at `0x80367158`, advanced by `advance_prng_state_80367158`, supplies eye/list animation, rain, skeletal variation, snow, and related visual effects without perturbing the gameplay stream.

Both streams are seeded exactly once by `main`: two consecutive `OSGetTick` calls feed `prng_seed_from_state_table` and `prng_seed_direct_set`. An executable-wide direct-call and SDA-access census finds no other seed caller and no access to either state outside its seed/advance routines. Neither state appears in `SYSF`, `BMST`, `MDST`, `UNIP`, convoy, forge, tile, or script `AllPush` serialization. Consequently, a save records the consequences of earlier rolls but not the stream position. Loading, retrying, or resuming within the same running game does not roll the stream back to the save point and does not reseed it; it continues from whatever state is currently in RAM. Starting the executable again creates new tick-derived seeds. Request order is therefore the runtime order in which eligible branches reach these entry points, not a per-system sequence or a saved replay contract.

<span id="fe9-sys-378"></span> **FE9-SYS-378 — Rule priority and overrides.** Priority belongs to each owning pipeline, not to one global override manager. The stable pattern is eligibility/hard gate → base/effective inputs → additive or multiplicative modifiers → clamps → documented late replacement → committed consequence. Final-boss/no-damage EXP gates, blessed-armor Attack zeroing, critical sealing, Parity/Nihil suppression, scripted results, and per-handler failure rules each occupy a named stage in their primary system. A new override must be inserted at that owner's intended stage rather than appended to a universal table.

The complete architectural matrix is below. It is exhaustive by **owner pipeline**, not by retail data row: adding another weapon, skill, chapter predicate, AI coefficient, or regional constant changes an input to one of these pipelines and does not create a new priority layer.

| Owning pipeline | Ordered priority and replacement contract | Examples of late or exceptional behavior |
|---|---|---|
| Build/content selection | Build executable and filesystem establish the available implementation → difficulty selects a table column or named resource → chapter data selects authored records → a script may request a chapter-local state change through a registered native | US/PAL/JP may supply different code or values; that regional comparison remains FE9-SYS-013/025/381 work, but it cannot override a live system except through the consumer named here |
| Command and item legality | Actor/action state → ownership/class/skill/status gates → item uses/rank/type → range, target, tile, path and occupancy → menu or AI choice → final revalidation → effect commit → durability/cost/action state → consequences | Silence removes tome/staff choices without deleting equipment; named items and form rules narrow access; a stale menu choice fails before spending resources |
| Movement and map topology | Map bounds and footprint → terrain/passability grid → sparse map-link overrides → tactical inset boundaries → caller-specific occupancy, allegiance, danger and endpoint filters → path/endpoint commit | Explicit `maplink` data can reopen a height-filtered edge before final map boundaries; AI policy can narrow legal destinations but cannot bypass common passability |
| AI decision | Eligible unit and saved program → recovery/special pre-attack dispatch → policy/activation/hold/route constraints → operation-specific candidate enumeration → common legality → score → comparator-local tie rule → execution revalidation | Healing can pre-empt an ordinary attack for that turn; script sequence replacement supersedes deployment defaults; first/last-on-tie behavior belongs to each comparator, not a global rule |
| Combat exchange construction | Legal combatants/equipment/range → Vantage/opening order → defender-counter eligibility → AS follow-up exchanges → Brave and proc-added strikes within each exchange → step-by-step survival/weapon/status revalidation | Cancel removes a counter step; breakage or death removes later scheduled work; scripted no-counter/forced-result flags replace only the stages they explicitly own |
| Effective stats and strike outcome | Definition/instance/unit inputs → effective getters → suppressors such as Parity, Nihil and effectiveness seals → triangle, terrain, support, status, equipment and skill modifiers at their owned stages → numeric clamps → documented late replacements → RNG where still required → committed damage/status/post-hit work | Status-target Hit can become 100; crit sealing forces final Critical to 0; blessed armor forces Attack to 0 without `weakA`; Wing Guard/Goddess protection can replace damage with 0; Miracle clamps lethal HP to survival before death |
| Item, staff and temporary-state effects | Effect-specific caster/item/target predicate → immunity/current-state/replacement rule → accuracy or activation roll where applicable → state write or movement → shared durability/progression/action wrapper → presentation | Invalid/cancelled targets consume nothing; Restore clears only its removable status family; reapplication replaces/refreshes the owned temporary field; unbreakable suppresses ordinary use loss |
| EXP, growth and promotion | Absolute eligibility gates → base terms and difficulty data → term-specific minima → additive bonuses → skill multipliers → award cap → current level/EXP/promotion allowance → commit → level/promotion consequence | Final-boss combat awards 0; no-damage combat is exactly 1; kill-only EXP terms require a defeat; Paragon/Blossom adjust before the 100 cap; story-class-change ownership excludes the generic promotion path |
| Death, drops and objectives | Survival replacements finish → zero-HP result → death/retreat policy → drop/counter/force consequences → ordered event predicates → `gf_complete`/`gf_gameover` write → battle-controller route | A boss trait does not itself win a map; chapter scripts may retreat or replace a unit; event table order and one-time flags decide among matching authored consequences |
| Persistence and presentation | Authoritative mutation commits → serializer records the owning fields when requested → presentation consumes the result → skip/alternate presentation rejoins the same consequence boundary | A visual, process, pointer or audio state cannot override saved gameplay state; resume initialization may deliberately supersede restored chapter-local fields as defined by FE9-SYS-382 |

“Late” is local to a row. Critical sealing does not run after objective routing, and a script does not automatically outrank native legality merely because it executes later in wall-clock time. A script bypass exists only where its registered handler defines one. When two rules occupy different rows, their owners compose through explicit state—AI selects an action, ordinary execution revalidates it, combat commits a death, and the objective event then observes that death. This owner-to-owner handoff is the cross-system priority rule.

<span id="fe9-sys-379"></span> **FE9-SYS-379 — Legality before execution.** Player menus and AI first enumerate legal actions, but execution validates again before committing. The general transaction is: gather candidates → preview/score → validate chosen inputs → mutate authoritative state → spend uses/resources → schedule presentation → fire events/objectives. Revalidation protects against a target, tile, item, or unit state changing after the menu was built.

<span id="fe9-sys-380"></span> **FE9-SYS-380 — Definition, instance, and runtime separation.** `IID_IRONSWORD` defines shared properties. A unit's Iron Sword instance owns uses/equip/forge flags. A battle weapon object is a transient interpretation used for forecast and animation. Changing one layer does not automatically rewrite the others. The same pattern applies to character definition → saved unit → map actor and model definition → animated model instance.

## Boundaries between systems

<span id="fe9-sys-382"></span> **FE9-SYS-382 — Serialization boundary.** Saves include console/system settings and unlocks, playthrough/party progression, unit/item/support state, chapter identity/flags/counters, and the mutable map/tile/action state required by the selected resume route. They store stable identifiers, values, and records—not arbitrary pointers, process PCs, loaded textures, animation frames, audio handles, or widget focus objects. Loading initializes services and definitions, selects a `GameController` resume label, reconstructs the owning scene, then restores that route's saved authoritative state.

The card format makes that boundary exhaustive rather than illustrative. After the replicated `SYSF` record, the tagged state stream contains only `BMST`, `MDST`, `UNIP`, `SOKO`, `FWEP`, and `T  T`; every byte in those records has been assigned to a field or confirmed padding/unused storage. The following matrix describes the lifetime of those fields. “Restored then superseded” is important: the decoder may copy a value into RAM before the selected route deliberately initializes a new chapter or scene over it.

| State family | Stored representation | Base/preparations and chapter-part continuation (resume 1, 2, 5–7) | Mid-map checkpoint/Suspend (resume 8) | New chapter, after-clear, and trial entry (resume 3, 4, 10) |
|---|---|---|---|---|
| Console-wide settings and unlocks | Replicated `SYSF` in every block | Restored from the newest valid block overall | Restored from the newest valid block overall | Restored from the newest valid block overall |
| Party/campaign progression | `BMST`: gold, BEXP, playthrough, reports, clear history, tutorial masks, options, persistent flags and related counters | Restored | Restored | Restored; values owned by the new chapter are then initialized by that chapter's entry path |
| Chapter identity and tactical counters | `BMST`: chapter/map, phase, turn, objectives, cursor, faction orders, reinforcements and resume point | Restored for the selected base, preparation, or multipart-map route | Restored as the current tactical state | Used to choose the route, then reset or derived by chapter/trial initialization where that route owns a fresh map |
| Event flags | Twelve `BMST` bit bytes; names are never saved | `Startup` rebuilds names first, then all 96 saved bits are restored | Existing names and all bits remain live | Global slots survive; chapter-local names/bits are reset and the saved local bits are stale/discarded |
| Map display/environment | `MDST`: camera, sight, weather, fog and lighting values | Restored for the reconstructed map-bearing route | Restored | Restored by the decoder, then superseded by the new map's initialization where applicable |
| Units, items, supports and AI programs | `UNIP`: up to 159 indexed unit records | Restored; empty-link units are reattached to their army list | Restored, including acted/state flags, position, rescue links and AI PCs | Persistent roster state is restored; army lists and chapter deployments are rebuilt for the destination |
| Convoy and forge state | `SOKO` and `FWEP` | Restored | Restored | Restored |
| Mutable map objects | `T  T`: 64 wall, overlay, ballista, pit, rock, door, roof, chest, village or building records | Restored after that map's registrations | Restored | Cleared and rebuilt by the new chapter's `Startup`/`RegistLocationTT` path |
| RNG streams | No card or script-snapshot field | Current in-process streams continue | Current in-process streams continue | Current in-process streams continue; a fresh executable boot reseeds from ticks |
| Definitions and resource identity | Stable table numbers and symbolic IDs only | Definitions are loaded and IDs resolved | Definitions are loaded and IDs resolved | Definitions are loaded and IDs resolved |
| Processes and presentation | Not stored | Scene, UI, actors, resources and audio are reconstructed | Tactical scene is reconstructed at label 18 | Destination scene is constructed at label 10 |

Retry and ordinary load are not additional serialization formats: they select one of these saved blocks and resume labels. Likewise, script `AllPush` uses the same tagged records plus a 21-byte dual-actor record in a RAM buffer; that extra record never crosses the memory-card boundary. A mod that adds persistent state therefore needs a field, serializer, deserializer, capacity/CRC handling, and a defined reset policy for every resume family. Keeping a pointer alive or adding a load-time initializer alone does not make state persistent.

<span id="fe9-sys-383"></span> **FE9-SYS-383 — Script/native division of responsibility.** Native code implements reusable operations and formulas; event scripts compose chapter-specific sequences. Native code knows how to create a unit, move a camera, award an item, run combat, or test a flag. A chapter script decides *which* unit, *when*, under what story condition, and what follows. Moving a generic rule into one chapter script makes other chapters inconsistent; hard-coding a story exception into a generic formula makes the engine brittle.

<span id="fe9-sys-384"></span> **FE9-SYS-384 — Simulation/presentation separation.** The authoritative result can exist before its animation finishes. Combat resolves strikes and state changes, then battle/map presentation consumes that log. EXP calculation precedes the bar animation; dialogue/object state can be committed while glyphs or motion are still playing. Animation-off selects another presenter, while fast-forward/skip shortens waits, jumps actors and fades to end transforms, suppresses transient effects/audio, and resumes at the same consequence/continuation boundary. A handler that owns gameplay mutation must commit it on both normal and skipped paths.

This separation is not limited to combat. An audit of every presentation family establishes the following convergence contracts:

| Family | Authoritative producer | Normal presentation | Alternate, accelerated, or skipped route | Common continuation/invariant |
|---|---|---|---|---|
| Combat | Exchange resolver builds the strike/result log; the action executor calculates EXP before starting its blocking child | Full battle consumes the log through detailed actors, HUD, effects and cameras | Map battle, animation-off, non-player instant resolution and battle skip consume or bypass presentation without rebuilding the exchange | The same HP, status, durability, EXP, death and consequence queue reach post-battle processing |
| EXP and rewards | Award handlers commit unit/party values and report counters | Bars, level-up panels and item/reward notices display committed deltas | Acceleration shortens waits; omitted display leaves the committed value intact | The waiting parent resumes after the same award transaction |
| Scripted unit changes | Native handlers write unit, inventory, allegiance, form, position or class state | A blocking movement, warp, death or class-change child depicts the mutation | Event skip applies the same endpoint synchronously or jumps the child to its terminal transform | The script VM resumes after the handler with the same mutable unit fields |
| Dialogue and choices | Event bytecode owns flags, recruitment, rewards and branches outside the text renderer | Text/portrait processes reveal pages and return a result | Fast input changes reveal delay; conversation skip releases the same wait; `$SD` prevents skipping where a choice/result is required | The VM continues exactly once; skip cannot fabricate a choice or bypass later mutation instructions |
| Cutscenes, stills and movies | Surrounding event/campaign code owns semantic state | World-map, model, image, THP and credits children own resources and timing | Skip completes or destroys the presentation handle and releases its wait | The same script continuation or ending-flow result runs after teardown |
| Map objects and cameras | Action/script handlers update the saved `T  T` record, unit/map state and requested camera endpoint | Door, roof, chest, building, actor and camera processes interpolate to that endpoint | Skip maps reversible animation modes to their terminal start/end modes and refuses presentation-only mode 2; camera/actors jump to final transforms | Persistent object/unit state is identical; only interpolation, particles and elapsed presentation frames differ |
| Audio and transient effects | The owning gameplay handler requests a cue after its result exists | Presenter starts voices, music, particles and fades | Skip/teardown stops or releases them | No audio/effect handle is an input to the authoritative result or serialized afterward |

The convergence proof is based on producer/consumer and control-flow ownership, not on claiming that every route draws the same frames. A presentation route may differ in elapsed real time, camera, sound, effect population, animation frame, or temporary process tree. Those differences are expected and unsaved. A genuine gameplay divergence exists only if an alternate path reaches a different authoritative mutation or continuation; the audited paths above do not. Frame-perfect visual comparison remains useful regression testing for asset edits, but it is not missing evidence for the simulation/presentation system boundary.

## Worked example: one attack

The map scene owns unit instances and accepts input. The command builder finds a legal weapon and target. Forecast reads definitions plus mutable unit/item/terrain state without spending durability. On confirmation, combat consumes RNG and resolves a result log; unit HP, item uses, EXP, and death state become authoritative. The presentation layer chooses map or full battle and animates that log. Event/objective processing observes the committed result. A later save serializes unit/item/map state, not the battle camera or current animation frame.

At the scheduling boundary, `execute_pending_map_action` builds the battle context and starts a blocking child process. The tactical parent waits while that child presents combat and performs its post-battle sequence. When the child ends, the parent resumes with the same surviving units and chapter state, but without retaining the temporary battle camera, actors, effects, or HUD as saveable objects. This is the definition-instance-scheduled-work-persistence model in one concrete path.

## Interactions, limits, and modding hazards

- Process names and script addresses are separate. Some live process scripts are started by descriptor address, so an unreferenced name string is not proof that the scene is unused.
- A blocking child is part of game logic, not merely visual polish. Bypassing the battle child can skip post-battle dialogue, EXP presentation, death handling, or victory recognition even if HP was already changed.
- A saved resume point is an instruction to rebuild a flow state. Adding a new scene or chapter part requires a reconstruction path as well as an entry path.
- Fixed pools impose hard ceilings. Extending a process-heavy feature without auditing the 256-slot process pool and teardown behavior risks exhaustion or stale entries.
- Cleanup must follow every exit, including skip, cancel, game over, and scripted early return. Releasing only the ordinary completion path can leave a resource or child process alive in the next scene.
- Global state should not become a shortcut for scene ownership. A pointer that happens to remain reachable globally can still refer to an object whose owner has been destroyed.

## Known gaps and required evidence

The architecture model is useful, but two systems remain **reviewed with gaps**. Close them only after collecting the following evidence:

- **FE9-SYS-009:** census allocation and release sites across representative scene transitions. For each allocation family, identify the allocator or pool, owning object/process, destructor or free path, and exhaustion behavior.
- **FE9-SYS-012:** build a writable-global census recording initializer, writers, readers, reset boundary, serialization behavior, and owning service. Addresses without a writer/lifetime trace remain unresolved.

These results belong in this article and its executable/save evidence pages. No new primary article is currently required; an allocation or global-address appendix should be added only after the underlying census exists.

## Evidence trail

The primary executable trace is recorded in [Main DOL](../formats/main-dol.md) and the repository's `research/MAIN_DOL_NOTES.md`, especially “Scene tree architecture,” “Game flow process scripts,” the process/handle-table framework, and boot/master-data loading. Save reconstruction is detailed in [Save System](save-system.md), chapter flow in [Campaign Flow](campaign-flow.md) and [Chapters](chapters.md), resource lifetime in [Engine and Resource Loading](engine-resource-loading.md), and script scheduling in [Events and Scripting](events-scripting.md).

