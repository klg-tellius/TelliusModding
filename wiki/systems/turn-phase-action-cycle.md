---
id: "turn-phase-action-cycle"
title: "Turn, Phase & Unit-Action Cycle"
description: "The tactical timeline that orders turns, armies, phase initialization, and acted state"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Maps", "Rules", "Events"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source", "path-of-radiance-us-manual"]
cms_collection: "systems"
source_path: "systems/turn-phase-action-cycle.md"
system_entries: ["FE9-SYS-083", "FE9-SYS-084", "FE9-SYS-085", "FE9-SYS-086"]
system_reviewed: ["FE9-SYS-083", "FE9-SYS-084", "FE9-SYS-085", "FE9-SYS-086"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Turn, Phase & Unit-Action Cycle

The tactical map has several clocks. A **turn** is the full cycle of armies; a **phase** belongs to one army; an **action** belongs to one unit. Keeping them separate is essential because events, statuses, healing, transformation, AI, and objectives may update at different boundaries.

## Mental model and lifecycle

Think of the controller as three nested loops. The outer loop owns the displayed turn. Inside it, the scheduler visits each normal army. Inside one army's phase, eligible units spend their individual actions. A phase can contain many actions, while a turn increments only after the army cycle reaches its boundary. Events may pause any loop, but resuming must return to the saved turn, army, and unit-state combination rather than restarting the chapter.

## Turn counter

<span id="fe9-sys-083"></span> The turn counter describes campaign time on the current map. It begins from the map's initialized state, is displayed in the HUD, feeds turn-triggered events and defend/survive objectives, contributes to chapter-clear records, and is a common input to turn-efficiency Bonus EXP. It should advance once per completed army cycle, not every time control changes hands.

The current turn is serialized with party/map state, so a checkpoint or suspend resumes timed events consistently. Scripts can also inspect turns and phases when deciding whether a one-time event is eligible. A mod must avoid incrementing the counter before all late phases have completed or the same authored trigger can move by one turn.

`BMSetTurn` can overwrite the live value for authored or debugging flows. Chapter clear copies the current turn into the first free eight-byte history entry alongside chapter identity, continuation flag, and elapsed time. The ending's war-record builder later merges continued parts and displays those totals. The value is therefore both live trigger input and durable campaign history; changing it affects more than the HUD.

## Army-phase order

<span id="fe9-sys-084"></span> The retail order is Player, Partner, Enemy, then Other. Blue units accept player commands only during Player phase; yellow, red, and green forces use AI or script control on their phases. A force with no eligible units can be skipped, but its phase boundary may still matter to events or scheduled state.

Army identity and hostility are separate questions. Partner and Other forces are not simply alternative enemy colors: alliances determine legal targets and pass-through rules, while phase ownership determines when their units act. An event can change allegiance or remove a force, so phase scheduling reads current runtime state rather than a fixed four-step animation.

The four normal force lists are runtime IDs 0 player, 2 partner/orderable, 1 enemy, and 3 other; their presentation order remains Player, Partner, Enemy, Other. Higher list IDs represent reserve, free, or inactive states and are not extra tactical phases. Saves keep the current phase plus four per-army phase-state bytes; a normal chapter-start block uses turn 1, player phase, and phase bytes `1/2/2/2`.

## Phase initialization

<span id="fe9-sys-085"></span> Entering a phase prepares the world before its first unit acts. Responsibilities can include refreshing the incoming side, advancing or clearing temporary state at its defined boundary, applying healing and status effects, rebuilding AI danger information, selecting phase music, presenting the banner, and dispatching phase/turn events. Not every subsystem ticks at the same moment, and the exact retail ordering must be preserved when interactions can kill, heal, wake, or trigger dialogue.

AI phases then run a scheduler over eligible units. Player phase instead unlocks input after initialization/event work has finished. If a start-of-phase event launches dialogue, reinforcement, weather, or objective changes, input should not race ahead of it.

Initialization operates on current units rather than the deployment file: recruitment, death, escape, carrying, reinforcement, and scripted transfers can all change eligibility. The phase controller dispatches registered boundary handlers in sequence; each handler commits its unit effects, and resulting death/objective consequences complete before the action scheduler considers that unit. Poison, terrain healing, status expiry, and authored start-of-phase events therefore use one ordered boundary rather than running from presentation code. FE9's Laguz gauge is a deliberate exception: its executable writers are post-action and damage handlers, not the idle phase boundary.

## Unit action state

<span id="fe9-sys-086"></span> A map unit has an acted/done state distinct from its army's phase. Selecting, moving, attacking, trading, using an item, waiting, or performing a tile action eventually commits that state. The map ring turns gray and ordinary selection cannot grant another full action until refresh.

Movement and action are staged. The engine first computes reachable destinations, previews commands/targets from a candidate destination, validates the chosen command again, applies movement and action, schedules consequences, and then marks the unit done. Validation must run at execution as well as menu construction because the target or map can change.

The authoritative acted marker is unit-state bit `0x1`; carrying and carried use `0x2` and `0x4`, while dead/inactive, reserve, off-screen, fog-hidden, and escaped states have separate bits. This separation lets a unit be carried without being treated as an ordinary selectable actor and lets scripts inspect or alter state without conflating it with force identity. Saves serialize the unit state, current army, turn, and map controller state so a resume cannot grant an extra action.

Canto is a controlled exception: after an eligible action, the unit is already considered to have spent its main action but may use remaining movement for one post-action move. Refresh/Chant clears acted state for an eligible unit without rewinding its HP, inventory, movement history, or earlier consequences.

## Worked timeline

At the start of turn 5, Player phase initialization runs and refreshes blue units. A turn-5 event may add enemies or change the objective before control returns. Ike moves and attacks; combat, death, experience, and event checks finish, then Ike becomes done. A mounted unit attacks and receives a Canto destination budget, completes that move, then remains done. End Turn closes player control. Partner, Enemy, and Other phases initialize and run in order. When the cycle finishes, the next turn begins and the displayed counter advances according to the controller's ordering.

## Interactions and edge cases

- Carried, dead, hidden, escaped, inactive, or scripted units are not ordinary eligible actors.
- A unit can die during phase initialization from an effect; objective/death handling must occur before it acts.
- Reinforcements may be eligible immediately or wait depending on when and how scripts create them.
- A forced/scripted action may deliberately bypass the player command menu while still updating acted state.
- Suspend/checkpoint must preserve current army, turn, and each unit's done state.
- Ending a phase early marks or bypasses remaining units without inventing extra actions.

## Interactions and review boundary

All three turn/phase/action systems are reviewed without a blocking research gap. The fixed army order, empty/disabled-force skip, phase initialization handlers, action preview-to-commit boundary, Canto continuation, acted-state finalization, events, objective/death checks, and serialized resume point define the nested timeline. Individual status and event handlers retain their own data and consequences. No new primary article is needed.

