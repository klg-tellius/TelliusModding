---
id: "objectives"
title: "Objectives"
description: "How a chapter knows it's been won or lost"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/objectives"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/objectives.md"
system_entries: ["FE9-SYS-035", "FE9-SYS-103", "FE9-SYS-104", "FE9-SYS-105", "FE9-SYS-106", "FE9-SYS-107", "FE9-SYS-108", "FE9-SYS-109", "FE9-SYS-110", "FE9-SYS-111", "FE9-SYS-112"]
system_reviewed: ["FE9-SYS-035", "FE9-SYS-103", "FE9-SYS-104", "FE9-SYS-105", "FE9-SYS-106", "FE9-SYS-107", "FE9-SYS-108", "FE9-SYS-109", "FE9-SYS-110", "FE9-SYS-111", "FE9-SYS-112"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Objectives

*How a chapter knows it's been won or lost*

Two layers combine to decide when a chapter ends and how: a pair of engine-level flags that actually end the chapter, and a per-chapter set of invisible marker objects that describe what condition the chapter is built around.

## Mental model and objective lifecycle

An objective is a contract assembled from **presentation, eligibility, observation, and commitment**. Chapter data supplies the displayed goal and defeat text. A menu entry, marker, turn trigger, death trigger, area trigger, or script helper observes live state. An eligible event performs any dialogue/map changes and sets a persistent flag. Only `gf_complete` or `gf_gameover` commits the battle result. The battle-map controller polls those flags and routes to chapter clear or Game Over.

## FE9-SYS-103 — Objective definition and display

<span id="fe9-sys-103"></span> A chapter record supplies four message slots: primary goal, one unused/secondary slot, defeat condition, and a second goal line. Hard and Maniac can select alternate goal text; Easy uses Normal. These strings describe the contract but do not execute it. Map goal objects and script trigger registrations provide machine-readable inputs, while current turn, unit state, positions, force lists, event flags, and map-object records provide live facts.

  Map data describes objective-related locations or markers, gameplay changes unit and map state, script triggers test the relevant condition, and the successful event sets `gf_complete` or `gf_gameover`. The flag—not the marker or displayed objective text—is the final chapter-ending signal.

## The flags that end a chapter

<span id="fe9-sys-035"></span> **FE9-SYS-035 — Defeat recognition.** Defeat is the loss-side instance of the same objective contract. A death, turn, phase, area, or scripted event observes live state and may set `gf_gameover`; the battle controller, rather than the observing event, owns the transition to Game Over. This means a lord reaching zero HP, a protected NPC disappearing, an enemy entering a defended area, or a turn limit expiring is not universally fatal by itself. The chapter script decides whether that fact commits defeat, permits a retreat substitute, or waits for a later phase boundary. Resume restores unit state, positions, turn, and saved flags before those observers continue, so it does not duplicate a one-shot failure event. Lord identities, turn limits, protected actors/areas, and retry destinations are chapter-authored condition rows rather than another defeat engine.

  [Event script](../formats/event-script.md) functions can be one of two specific trigger types whose sole parameter resolves, with zero exceptions across every real script checked, to one of two literal engine flags: `gf_complete` (the chapter is won) and `gf_gameover` (the chapter is lost). Setting one of these is the actual mechanism that ends a chapter — everything else in a chapter's script exists to decide *when* to do that.

## Battle-goal markers

  Separately, a chapter's own [map data](./map-objects.md) can include invisible, non-rendering objects carrying a confirmed 3-bit "battle goal" type field. These markers are consistently named after their own condition — recognizable real objective types recur across dozens of chapters sharing the same bit pattern, with names like `defense_01`, `attainment_01`, `secession_01`, and `visit_01` turning up on markers using exactly that objective's own type value. This is a real, structurally confirmed 3-bit enum — not a guess from a single chapter's data — though the exact player-facing meaning of each of its 8 possible values isn't independently confirmed beyond what the marker's own name implies. <span class="confidence confidence--strong">strong evidence</span>

## Objective text

  The goal and defeat lines shown to the player come from the chapter's record in [FE8Data.bin](../formats/fe8data.md): four text slots (the goal, an unused slot, the defeat condition and a second goal line), with separate goal texts for Hard and Maniac where they differ — a longer turn limit, for instance. Easy uses the Normal texts. <span class="confidence confidence--confirmed">engine</span>

## Trial map grades

  A trial map is graded A to E on three counts, each against four limits stored in its chapter record: the turns taken, the units lost, and the enemies killed. Each unit counts its kills on the current map (reset when it is deployed); the game sums them over the player's army, and more kills give a better grade. The final grade averages the three. <span class="confidence confidence--confirmed">engine</span>

## How they connect

  A chapter's script is what actually reads game state and fires `gf_complete`/`gf_gameover`—commonly through [turn/phase triggers](./events-scripting.md), unit state, command eligibility, or an area test. Battle-goal marker values categorize authored locations for UI and event lookup; they do not independently commit victory or defeat. The script registration and final flag remain authoritative even when a marker's label or enum value is unfamiliar.

## FE9-SYS-104 — Rout

<span id="fe9-sys-104"></span> Rout is normally an authored completion event gated by the enemy force becoming empty. `EnemyDeadCheck` returns 1 exactly when runtime force 1 has no unit left; it does not inspect deployment records, so defeated, removed, recruited, or transferred enemies affect the result through current force membership. When the event sets `gf_complete`, the battle controller enters its clear path.

This separation handles reinforcements: a script must not test and commit Rout before all intended spawns or gates are accounted for. Non-enemy hostile arrangements also require authored logic because the helper names force 1 specifically. Killing a boss does not automatically imply Rout if other force-1 actors remain, and deleting the last enemy by script can satisfy the same empty-list condition as combat.

## FE9-SYS-105 — Defeat boss

<span id="fe9-sys-105"></span> Boss defeat is event-authored rather than a global “boss flag means victory” rule. A Die or LocalDie trigger, character/state query, or chapter flag identifies the required actor and runs the completion event. That event may play dialogue, transform the map, advance a multi-stage fight, or set `gf_complete`. The runtime boss property can influence combat and rewards without owning objective completion.

Mods must distinguish death, scripted retreat, force transfer, disappearance, and substitution. A chapter with two bosses may require one, both, or a sequence; the engine does not infer that from class or commander status. Required PIDs, substitutes, retreat flags, and multi-boss combinations are authored event conditions consumed by this lifecycle.

## FE9-SYS-106 — Seize

<span id="fe9-sys-106"></span> Seize is unit command action 13. Its availability combines the candidate tile, a goal/event location, current chapter state, and an eligible actor. Selecting it delegates to the event; the command itself does not bypass dialogue or immediately advance the chapter. A typical event records any one-time flag and sets `gf_complete`, after which the normal clear controller runs.

The goal location may be represented by an invisible map marker and script registration. Moving the visible throne or gate model is therefore insufficient: the tactical coordinate and event condition must move too. The command asks the registered event/goal predicate whether the current actor and tile qualify; enabling Seize for another unit requires changing that authored predicate as well as the marker.

## FE9-SYS-107 — Arrive

<span id="fe9-sys-107"></span> Arrive is action 41 and follows the same destination-sensitive delegation pattern, but its authored condition can represent reaching a point or area rather than occupying a throne-like Seize tile. The event decides which actor qualifies, whether one or several units must arrive, what intermediate state changes occur, and whether the result is victory or merely progression.

Because the event owns completion, Arrive can coexist with map transformations or a second objective. A checkpoint preserves unit positions and event flags, allowing eligibility to be reconstructed. Point, rectangle, actor restriction, and multi-arrival behavior are parameters of the registered event condition; the command/executor lifecycle is unchanged across those variants.

## FE9-SYS-108 — Escape

<span id="fe9-sys-108"></span> Escape is command action 14 at an eligible exit. Removing a player unit moves it to reserve and sets escaped state rather than deleting its persistent character; carried units are dropped first. `PlayerEscapeCount` counts escaped actors in player force 0 and reserve force 5. `PlayerEscapeCheck` returns true only when every existing actor in those lists is escaped—and also returns true for an empty set—so a script must ensure the chapter's intended roster exists.

An authored event can require the lord, a threshold, or everyone, offer default escape dialogue, award optional BEXP, and finally set `gf_complete`. Saved unit state keeps escape progress across resume. Enemy or partner removal uses different lifetime consequences and should not be substituted for the player escape path.

## FE9-SYS-109 — Defend and survive

<span id="fe9-sys-109"></span> Defend/survive uses Turn or TurnAfter event triggers plus flags and, where relevant, a protected area or unit condition. The event compares the current turn/phase against the authored boundary and sets `gf_complete` only after any required enemy phase or final event. Difficulty-specific objective text can advertise a different limit, but the script condition must match it.

Off-by-one risk is the main modding hazard: “survive 10 turns” may commit at a phase boundary after actions on displayed turn 10, not when the counter first becomes 10. `BMSetTurn` changes the same live counter consumed by triggers and later clear history. Inclusivity, difficulty branches, and early-clear exceptions belong to each event's first/last-turn, phase, and flag parameters; modders should edit the displayed text and those authored values together.

## FE9-SYS-110 — Protect unit or position

<span id="fe9-sys-110"></span> Protection objectives are compositions, not one universal native. A unit variant observes a named actor's death/inactive/retreat state through a death event or query. A position variant observes area entry, occupancy, a map marker, or an event flag. On failure, the authored event sets `gf_gameover`; the battle controller then enters the Game Over scene.

This design permits exceptions—retreat instead of death, substitute defenders, enemies that do not count, temporary captures, or recovery before commitment—but means the displayed defeat text is not proof of the code path. Save flags, unit state, and positions reconstruct the same pending condition. The event's actor/area/state predicate and its `gf_gameover` write define the condition-to-failure mapping; retry routing is owned by the campaign controller.

## FE9-SYS-111 — Multi-stage objectives

<span id="fe9-sys-111"></span> A chapter can replace its active contract without ending the battle. An event sets a chapter flag, changes goal text/state, enables or animates map pieces, deploys units, and registers or exposes the next trigger. Only the final stage sets `gf_complete`. Chapter 17-style part transitions are a larger scene boundary; an in-map objective change can stay within one loaded battle controller.

Stages must be idempotent. Resume loads the saved flags, unit/map state, and current part, then reconstructs the correct objective rather than replaying rewards or transformations. Event skip reaches the same final stage. After the transition commits its flags/text/markers, the ordinary map/UI refresh presents the active contract; individual stage sequences are authored chapter data.

## FE9-SYS-112 — Optional objectives and achievement tracking

<span id="fe9-sys-112"></span> Optional goals normally write chapter flags or battle-map value slots as play unfolds. At chapter end, type-12 Achieve script functions evaluate those saved facts. Each successful `AchieveSet(message_id, amount)` appends one labeled Bonus EXP line; the report calculation still runs when the post-clear display option is hidden. The later BEXP pool receives the authored award rather than deriving every bonus from a universal formula.

This supports villages saved, units escaped, turns remaining, NPC survival, or chapter-specific counters without confusing them with victory. The flag/counter is updated when success or failure becomes irreversible and serialized if checkpoints are allowed. Each type-12 function owns its condition and raw amount; `AchieveSet` owns line collection, difficulty adjustment, display input, and the eventual BEXP award. Multi-part scripts decide whether their counters accumulate or reset.

The trial-map grades described above are a separate scored result: turns, losses, and kills are compared with chapter-record thresholds and averaged. They do not use `AchieveSet` as the normal campaign BEXP list.

## Interactions and review boundary

All objective systems are reviewed without a blocking research gap. Display records and markers describe the contract; command, death, turn/phase, area, and type-12 event predicates observe live state; `gf_complete` and `gf_gameover` commit the result; the chapter controller owns clear, retry, and Game Over routing. Per-chapter actors, coordinates, limits, stage flags, optional conditions, and BEXP amounts are authored event data, not missing objective-engine behavior. No new primary article is needed.
