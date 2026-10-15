---
id: "events-scripting"
title: "Events & Scripting"
description: "How a chapter's logic is actually structured — functions the engine calls reactively, not a linear script"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/events-scripting"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/events-scripting.md"
system_entries: ["FE9-SYS-038", "FE9-SYS-039", "FE9-SYS-040", "FE9-SYS-041", "FE9-SYS-042", "FE9-SYS-043", "FE9-SYS-047", "FE9-SYS-048", "FE9-SYS-049", "FE9-SYS-050", "FE9-SYS-051", "FE9-SYS-052", "FE9-SYS-053", "FE9-SYS-054"]
system_reviewed: ["FE9-SYS-038", "FE9-SYS-039", "FE9-SYS-040", "FE9-SYS-041", "FE9-SYS-042", "FE9-SYS-043", "FE9-SYS-047", "FE9-SYS-048", "FE9-SYS-049", "FE9-SYS-050", "FE9-SYS-051", "FE9-SYS-052", "FE9-SYS-053", "FE9-SYS-054"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Events & Scripting

*How a chapter's logic is actually structured — functions the engine calls reactively, not a linear script*

A chapter's [compiled script](../formats/event-script.md) is not a single linear sequence — it's a set of independent functions, each one gated by its own **trigger**: a condition under which the engine calls that specific function. Nothing in the file itself calls these functions in order; the engine evaluates each function's trigger continuously and runs the function's body when it fires.

!!! info "Mental model: trigger → function → engine call → changed game state"
    A trigger answers *when*. Its bytecode function answers *what sequence to perform*. Native engine calls perform operations outside the bytecode machine, such as starting music or a movie. The resulting flags, spawned units, dialogue, or chapter state can make later triggers eligible.

## FE9-SYS-038 — VM rules and lifecycle

<span id="fe9-sys-038"></span> A loaded CMB module supplies a string pool, function table, trigger records, and stack-machine instructions. Starting a function creates a frame whose first slots are arguments and whose remaining locals are cleared. Opcodes push constants or addresses, read and write locals or the 32 shared global words, perform arithmetic and comparisons, branch, call script or native functions, yield, and return one value. Every call leaves one value on the stack and compiler-generated functions implicitly return zero when they reach the end.

The VM owns script execution state, not the tactical state it edits. A unit handle, flag name, dialogue key, or music identity is resolved by another subsystem. Long-running native work yields through engine processes and later resumes the script. Invalid registered-call lookup is deliberately nonfatal: an unknown `externCall` contributes zero and execution continues, which can turn a misspelling into a silent branch error rather than a crash.

## FE9-SYS-039 — FE9 script source and compilation

<span id="fe9-sys-039"></span> The editable `.fe9s` language is a readable, Python-style reconstruction of the original C-minor structures. The decompiler recovers structured conditionals and loops where it can prove them, retains `goto` or assembly-like forms when required for fidelity, and emits source that recompiles losslessly. The compiler rebuilds the string pool, trigger parameters, function frames, calls, branches, and mixed-endian CMB layout.

Source is a project sidecar, not data the game loads. The editor reuses a sidecar only while it still compiles to the current `.cmb`; if the binary changed elsewhere, it preserves the stale source as a backup and decompiles fresh. This prevents readable source from silently overwriting newer binary work. Exact bytes, trigger record fields, opcode forms, and command-line compile/decompile entry points are documented in [Event Script](../formats/event-script.md).

## Kinds of trigger

  Every function carries a trigger type plus a small number of parameters specific to that type. Several are confirmed by resolving a function's own parameters back through the script's own label pool:

- **Turn/phase** — fires at the start of a specific turn number, on a specific phase (player or enemy). A "turn number" of 0 with no phase restriction fires on every turn.
- **Character-pair** — fires on an interaction between two specific characters, referenced directly by their `PID_` character-ID label rather than a raw index.
- **A separate character-ID family** — at least one trigger type resolves its character reference through an `MPID_`-prefixed label instead of the usual `PID_` family, seen nowhere else in this archive.
- **Zone/position** — some trigger types resolve their parameter to an auto-generated debug name encoding the trigger's own map-zone coordinates, rather than a fixed label — evidence the trigger fires when a unit enters a specific map area.
- **Chapter start/end** — the two trigger types covered on [Objectives](./objectives.md), whose parameter is always the literal flag `gf_complete` or `gf_gameover`.

## FE9-SYS-041 — Native script-call bridge

<span id="fe9-sys-041"></span>

  A function's body is bytecode operating on the script's own local state, plus `externCall` — the mechanism for invoking engine-level functionality the script can't do on its own. Every real `externCall` target seen takes a name and a small number of arguments, resolved the same label-pool way as everything else:

- `Fade` — a screen transition.
- `BGMPlay("BGM_EVT_...")` — start a music track, by symbolic name (see [Music System](./music-system.md) for how that name resolves to a track).
- `MoviePlay("Movie/....thp")` — play a cutscene, by literal file path (see [Cutscenes](./cutscenes.md)).
- `ChapterMoviePlay(N)` — play the current chapter's own opening cutscene, by chapter number.

  Labels throughout the scripting system follow informal but consistent prefix conventions that make an operand's role identifiable at a glance: `PID_`/`JID_` for characters and classes, `SID_` for skills, `IID_` for items, `gf_` for engine flags, `BGM_`/`SFX_` for audio cues.

  Naming an `externCall` target that doesn't exist isn't fatal — the engine silently pushes `0` and continues rather than crashing. <span class="confidence confidence--confirmed">confirmed</span>

## Flags

  Scripts remember state through named on/off flags — a table of 96 shared by every script, some lasting one chapter and some the whole playthrough, all written into save files. See [Event Flags](./event-flags.md).

## FE9-SYS-040 — Script entry-point registry

<span id="fe9-sys-040"></span>

  `externCall` targets are registered by name at runtime. The core registration primitive stores a handler name, a native function pointer, and an argument count, then the bytecode interpreter resolves calls through that registry. Registration is spread across several hubs: general extern calls, unit and battle-map calls, event-arrow calls, map-scene calls, chapter-objective calls, and battle-map scene handlers.

  The engine registers **406** native functions this way into a table with room for 416, each with a fixed argument count, and every `externCall` in the 43 vanilla scripts passes exactly that many arguments. <span class="confidence confidence--confirmed">confirmed</span> Named script functions join the same table when their script loads: `startup.cmb` contributes 89 helpers (`UnitCheckLiveByPID`, `MindGetItem`, `DisposSetMode`, …) that every chapter calls exactly like natives.

  Two names the vanilla scripts call are registered nowhere, so they always return 0: `NormalOnly` (so the Normal-only deployment branch of `startup.cmb`'s `DisposSetMode` family never runs) and `Easy` (one check in the Prologue, `Normal() || Easy()` — harmless, since `Normal` already answers true on Easy). <span class="confidence confidence--confirmed">confirmed</span>

  Handler targets are identified by their registration names. Examples include `MapUpdate`, `DialogResult`, `BGMPlay`, `SFXPlay`, `MoviePlay`, `UnitAddItem`, `UnitClassChange`, `BMSetMoney`, `EventArrowAppend`, `DoorOpen`, `RoofOpen`, `UnitMovePos`, `Dispos`, `AchieveSet`, `PlayerDeadCheck`, `EnemyDeadCheck`, `PlayerEscapeCheck`, and `ShooterBulletCheck`. A handler name only says which native function answers that script-callable name; what each one does, with its arguments, skip behaviour and return value, is described on [Script Functions](./script-functions.md).

## Worked example: a turn-start scene

  A function with a turn/phase trigger becomes eligible at the requested turn boundary. Its bytecode can fade the screen, invoke `BGMPlay` with a symbolic cue, request dialogue from the chapter's message data, and update a flag. A second function can use that flag or a later unit interaction as its own condition. The functions are related through game state, not because one follows the other physically in the file.

## FE9-SYS-042 — Blocking and asynchronous execution

<span id="fe9-sys-042"></span> A native call may finish immediately, start work and return, or suspend the calling script until an engine process signals completion. The contract is per function. Dialogue, movies, some movements, and staged battles block internally; other calls start camera paths, arrows, effects, fades, or movement that require a matching wait before dependent work. `WaitF` and `WaitM` yield for authored time, while process- or subsystem-specific waits synchronize to actual completion.

The safe sequence is start → wait → consume the result or mutate dependent state. Omitting the wait can make later dialogue, camera, map-object, or unit work race the presentation. Waiting on work that was never started can deadlock if the corresponding wait lacks an empty-state exit. [Script Functions](./script-functions.md) records blocking, return, skip, and validation behavior for every registered native and shared helper.

## Do not confuse the three kinds of name

  A function name identifies script code; a label such as `PID_IKE` identifies game data; an `externCall` target such as `BGMPlay` identifies native functionality. All are stored as strings, but the interpreter resolves them in different namespaces and uses them for different purposes.

## Loaded scripts live in one global chain, not one per chapter

  Every compiled script file the engine has currently loaded — the current chapter's, plus any shared/system-wide ones — sits as a node in one global linked list, not scoped to "whichever chapter is active." Loading a script appends it to the end of that list; each node also gets its own header fields relocated from stored file offsets into real addresses, and every one of its named functions is registered immediately into the same global name-lookup table `externCall`/`localCall` read from. A script can be put to sleep rather than freed — its functions are unregistered from that lookup table (so its names briefly stop resolving) while the module itself stays loaded in memory, and a separate call re-registers every sleeping script's functions again all at once. Only the most-recently-loaded script can ever be freed outright — there's no way to free an arbitrary one by name.

  Looking up an event by name searches the current script's own function list first, then — if not found there — falls through to the next script in the global chain. This is very likely the actual mechanism behind content that has to stay reachable no matter which chapter is currently active (a shared base/system dialogue pool, for instance): it's simply another script sitting in the same chain, not a special case. <span class="confidence confidence--confirmed">confirmed</span>

## FE9-SYS-043 — Event trigger evaluation

<span id="fe9-sys-043"></span>

  The native trigger dispatcher now lines up with the documented trigger table. Type 13 handles support-conversation events. Type 14 handles base conversations, including runnable-state checks, event counts, message-label lookup, star counts, and the info/seen flag used to suppress repeats. Type 5 handles unseen location/action events; type 8 handles talks; type 9 handles battle-start events; type 10/11 handle death events; type 15 handles unit selection; type 7 handles after-action events; type 4 handles zone entry; type 1/2 test goal flags; and type 3/6 handle phase events.

  The seen/flag set is used in two ways. For goal events, the dispatcher starts the chapter-complete or game-over event only after the relevant `gf_complete` or `gf_gameover` flag is already set. For talk, location, battle, and base-conversation style events, the same set suppresses events that have already fired.

  When a moment comes (a phase starts, a unit finishes an action, and so on), the engine walks the loaded scripts in load order, each one's functions in file order, and runs each one of that trigger kind whose condition holds, one at a time: the next condition is only tested after the previous event has finished. Functions of a script put to sleep are skipped. Pressing Start while an event runs skips it (a fade-out cancels the rest). <span class="confidence confidence--confirmed">engine</span>

## FE9-SYS-047–050 — Area, phase, talk, and death events

<span id="fe9-sys-047"></span> **Area events (FE9-SYS-047)** use type 4 zone bounds and a triggering side. The dispatcher tests a unit's completed movement against the rectangle, then starts the associated function when its other conditions and seen-state permit it. The function can deploy reinforcements, change objectives, manipulate the map, or play dialogue; the rectangle itself owns only eligibility.

<span id="fe9-sys-048"></span> **Turn and phase events (FE9-SYS-048)** use types 3 and 6 for before/after phase boundaries, with first turn, last turn, and force parameters. A zero/open range expresses repetition. Additional script logic and flags refine the raw schedule, so “turn 3” can still depend on a living unit or an earlier event.

<span id="fe9-sys-049"></span> **Talk and recruitment events (FE9-SYS-049)** use type 8 character pairs and direction rules to make an interaction eligible. The one-time flag suppresses a consumed conversation. Recruitment is not implicit in the trigger: the function must transfer the actor's force and apply any inventory, AI, flag, or story changes. A valid character definition without a live unit cannot supply a Talk command.

<span id="fe9-sys-050"></span> **Death and retreat events (FE9-SYS-050)** prefer a matching type 11 in-battle death event, then a type 10 return-to-map death event when allowed, and finally the default death-talk handler. Matching uses the active unit's character identity. The selected function can replace death with retreat presentation, set durable story flags, alter objectives, transfer the unit to an inactive/reserve force, or arrange later removal. Those character-specific consequences are authored function bodies; the dispatcher owns only identity match, type priority, fallback, and continuation.

## FE9-SYS-051–054 — Scripted action, timing, and skipping

<span id="fe9-sys-051"></span> **Scripted battles (FE9-SYS-051)** clear and fill up to 32 strike-override slots with `NetuzoInit` and `NetuzoSet`, then `NetuzoBattle` resolves real combat between valid actors and suspends the event for the battle process. Overrides can force hit/critical/miss ordering and selected damage/effect rules. They are gameplay mutations, not visual previews, and stale slots or invalid actors can corrupt the intended exchange.

<span id="fe9-sys-052"></span> **Scripted unit manipulation (FE9-SYS-052)** is the combined native surface for resolving actors, deploying groups, moving or teleporting, hiding/revealing, transferring forces, changing class, editing HP/status/inventory/skills/AI, and releasing units. Each operation validates a different subset of inputs. Callers must preserve force-list, occupancy, carry, item, and presentation invariants rather than treating every field as independently writable.

<span id="fe9-sys-053"></span> **Script timing (FE9-SYS-053)** combines explicit frame/millisecond waits, subsystem completion waits, blocking calls, and the VM's yield/resume instruction. Milliseconds truncate to 60 Hz frames. A return of zero during skip often means “no wait was scheduled,” not “the requested end state failed.”

<span id="fe9-sys-054"></span> **Event skip and fast-forward (FE9-SYS-054)** makes presentation converge quickly while preserving required state. Waits return immediately; movement and fades jump to their end state; doors, villages, and similar objects apply their final mutation; active effects are removed; movies/dialogue exit; and new audio cues are commonly suppressed. `DisableSkip` protects critical spans and must be paired with `EnableSkip`. Essential flags, transfers, inventory changes, objective mutations, and continuation labels remain authoritative work outside presentation-only branches, so normal and skipped execution converge even though transient processes, audio, and animation differ.

## Base conversation list

  Base conversations are also surfaced through a real menu/list path. The base-conversation list screen scans runnable type-14 events, builds visible rows, draws the row name, seen-state marker, divider, and star count, then resolves the selected list node back to the event index and display name before opening a confirmation dialog or starting the selected event. The list UI is therefore not a static table of menu text; it is a view over runnable event records and their info flags.

## A few confirmed interpreter quirks

- An assignment instruction leaves its written value sitting on the evaluation stack afterward, rather than fully consuming it — ordinary compiler-generated "assignment as an expression" behavior.
- The bytecode's four conditional-branch instructions form two complementary pairs (branch-if-nonzero / branch-if-zero, each with a "keep the value on the stack" variant) — exactly the primitives a compiler needs for short-circuit `&&`/`||` as well as plain `if` branches. One of the four's own name doesn't match what it actually checks.
- A function can invoke a genuine native engine function directly, not just more script code — a function's own header marks which kind it is, and `externCall`/`localCall` reach either transparently through the same syntax.
- Every call — native or script — leaves exactly one value on the stack, and every function ends with an implicit `return 0`. A call used as a statement is followed by an explicit `pop`.
- A function's arguments occupy the first slots of its frame and its local variables the next ones; the interpreter zeroes the locals on entry.

## Global variables

  Besides its own locals, a script can use **32 global words**, numbered 0&ndash;31 and shared by every loaded script: slot 3 is the same word whichever chapter reads it. A script's header declares how many slots it needs (the highest slot it uses plus one); the engine keeps a running total, and a script that would push it past 32 is loaded without any of its functions being registered. <span class="confidence confidence--confirmed">confirmed</span>

  The table is created once at power-on and never cleared: an unwritten slot holds leftover memory, not zero. It is not part of a save either, so a global is only dependable between a write and a later read in the same play session. The chapter scripts use globals exactly like that — a unit's death or selection stores tile coordinates that the following after-action event reads — and keep anything lasting in [event flags](./event-flags.md) instead. <span class="confidence confidence--confirmed">confirmed</span>

## Interactions and review boundary

All event systems on this page are reviewed without a blocking research gap. The VM, editable source round trip, global registries, trigger dispatch, native-call contracts, death-event priority/fallback, and skip-aware handler contracts are established from all 43 retail chapter modules and the native/helper catalog. Per-character retreat consequences are authored event bodies, while scene-specific animation/audio differences are presentation content; persistent flags, units, inventory, map objects, objectives, and continuation state remain the convergence boundary. No new primary article is needed.
