---
id: "modding-common-ai-orders"
title: "Create common AI orders"
description: "Build and test stationary bosses, aggro enemies, patrols, thieves, healers, talkers, escape units, and target-filtered AI with explicit attack, move, heal, route, and equipment requirements"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "AI", "Enemies", "Maps"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/44-common-ai-orders.md"
tutorial_kind: "task"
tutorial_track: "ai-economy-and-media"
tutorial_stage: "draft"
prerequisites: ["modding-ai-language", "modding-deployment-by-difficulty", "modding-event-flags"]
verification: ["source-reviewed", "unknown"]
---
# Create common AI orders

**Route:** Game Data → AI (CP); Chapter → Deployment; Chapter → Scripts

## What you will make

You will turn one controlled test enemy into several common roles by changing one policy layer at a time: a stationary boss, an enemy that wakes when targets approach, a waypoint patrol, a thief, a healer/support unit, a talker, and an escape unit. Each recipe identifies the required sequence operation, deployment fields, supporting table or event, and inventory/skill prerequisites.

These are recipes, not magic labels. A class called Thief does not steal without `SID_STEAL`, a legal item, and a Steal operation. A stationary attack operation does not prevent the Move sequence from walking away. Build each role from explicit parts.

## Before you begin

Create a small test map with open ground, one obstacle, one healing tile, and enough space for a short route. Add one test enemy and two player targets. Keep a baseline deployment section that you can reload.

Record the enemy's four policy identities: Attack, Move, Heal, and Movement type. Give it an ordinary usable weapon. Add special equipment only for the matching recipe. Use copied `SEQ_*` records and unique `TBL_MAP*_ROUTE*` or `TBL_PID_*` tables so retail maps keep their original behavior.

## How the editor fits together

An AI role is an assembly:

| Layer | Supplies | Typical failure when missing |
| --- | --- | --- |
| deployment | starting Attack, Move, Heal, Movement type, equipment, skill/class | correct script never reaches the unit |
| event script | wake condition or later `set_scripts` replacement | unit starts active, never wakes, or changes at the wrong time |
| Attack sequence | attacks, staff, steal, skill, talk, object actions | unit moves or waits but never performs the role action |
| Move sequence | pursuit, hold, route, talk destination, escape goal | unit finds no in-range action and then behaves unexpectedly |
| Heal profile | enter/release recovery mode and recovery priority | wounded unit ignores combat or never seeks recovery |
| Movement type | ranks legal attack target/weapon/tile combinations | unit attacks a surprising eligible target |
| route/target table | ordered coordinates or PID filter | movement has no goal or targets the wrong population |
| map events | talk pair, escape point, village/object trigger | AI reaches the location but cannot commit its action |

## Guided walkthrough

### Recipe 1: stationary boss that attacks in range

Copy an Attack sequence and use `attack_in_place(chance=100)`. Branch on `found` to the terminating success path. Pair it with a Move sequence that registers no movement, normally a copy of `SEQ_NOMOVE`, and assign both to the boss.

“In place” restricts candidate construction to the occupied tile. If the boss is shoved or otherwise displaced, its next decision holds the new tile; it does not remember the throne coordinate. If the boss must return to a particular coordinate, use a coordinate goal or event-driven reset instead.

Test with a target in range, one outside range, and after displacement. Then lower the boss below its Heal threshold. A recovery policy can still pre-empt the hold attack, so use `SEQ_NOHEAL` only if the design truly forbids recovery and staff targeting.

### Recipe 2: attack only after a target enters a radius

Start from a retail range-wake Move sequence. Its structure is:

```text
r0 = count_units(range=1.5, weapon_range=True)
if r0 > 0: goto L1
nop202()
stop()
L1:
set_scripts(move=SEQ_NEARESTUNITMOVE)
stop(resume=L1)
```

`range` is a 16.16 factor of the unit's Mov; `weapon_range=True` adds usable weapon reach. The operation counts eligible targets—it does not attack them. When the count becomes positive, `set_scripts` installs an active pursuit sequence. Because the transition changes persistent AI state, saving and reloading should not restore the dormant deployment policy.

Test just outside and just inside the boundary, with and without a usable weapon, and across save/reload after activation. For a coordinated group, author the event/group propagation explicitly; one unit waking does not imply a universal hidden aggro link.

### Recipe 3: waypoint patrol

Open **Routes & targets**, choose **New route…**, and name a `TBL_MAP..._ROUTE...` table. Add points as `x,y` in visit order. Use the map grid's coordinates, not screen pixels. In a copied Move sequence insert:

```text
follow_route(route=TBL_MAP_TUTORIAL_ROUTE, budget=-1, reach=0)
stop()
```

Negative `budget` uses the unit's Mov; a positive value caps movement spent per turn. `reach` is the Manhattan distance that counts as arriving. The route loops after its final waypoint. An attack permitted by the Attack policy may interrupt the current turn, after which route state resumes. A blocked waypoint produces fallback/no action rather than teleportation or automatic skipping.

Test every point, the loop back to the first, an occupied destination, a temporarily blocked corridor, and an attack opportunity beside the path.

### Recipe 4: thief that prioritizes selected loot

Give the unit `SID_STEAL`, strictly more Speed than the victim, and a free slot of the correct inventory kind. In **Steal items**, add the eligible IIDs and order them with **▲ Up** / **▼ Down**; earlier entries have better priority.

In the Attack sequence, call `steal(chance=100)` before ordinary attack, then branch on `found`. If steal fails, fall through to a normal attack. Pair it with movement that can reach a tile adjacent to a victim.

The thief examines a victim's inventory in slot order and keeps the first stealable instance it sees; it does not scan later slots for a globally better item. This means a low-priority eligible item in an early slot can mask a high-priority card in a later slot. Weight, protected-instance state, capacity, Speed, table membership, and adjacency all gate legality.

Test equal Speed, full inventory, reversed victim slots, reversed Steal-table order, protected loot, and a victim reachable only after movement.

### Recipe 5: healer or status staff user

Put a usable staff in one of the unit's first four item slots and call `use_staff(chance=100)` or `use_staff_in_place(...)` in the Attack sequence. The in-place version prevents walking to cast; it does not extend range.

Assign Heal profiles to potential patients. Healing staves target only allies whose needs-healing flag is set. **Retreat below HP %** sets that flag when HP is strictly below the threshold; **Stop retreating at HP %** clears it only after recovery reaches that value. This hysteresis prevents oscillation. **Try healing items first** being non-zero enables the acting wounded unit's pre-attack recovery layer.

Staff selection is deterministic: item slots are scanned in order, later equal-or-higher-rank qualifying staves can replace earlier ones, and a healing result prevents the non-healing family from taking priority. Torch, Hammerne, and Unlock have no retail AI routine. Fortify needs at least three qualifying allies anywhere on the map.

Test a patient one point below and exactly at the retreat threshold, partial recovery below the resume threshold, no valid patient, Silence on the caster, staff out of range, and competition between two equipped staves.

### Recipe 6: move to and talk to a named character

Create an unseen talk event for the exact actor/target pair. In a Move sequence use `talk_move(pid=PID_...)`; it paths next to the character and queues action 7 only when the event exists. `move_to_talk(...)` only approaches and reports that it is adjacent; `talk(...)` attempts the conversation from the current tile.

Test target absent/reserve, target already adjacent, blocked adjacency tiles, wrong talk pair, and the event after it has already been consumed. Result code `3` means talk queued; `9` means the talk target/event was not found.

### Recipe 7: escape unit

Place an escape event of kind 44 and assign a Move sequence containing `escape()`. The operation chooses the nearest escape point, paths under normal occupancy and safety rules, and commits action 44 on arrival. The map event owns unit removal and optional-objective consequences.

Healing can pre-empt escape for a turn. An occupied or unreachable exit does not teleport the unit. Replacing scripts clears escape mode, so event-driven policy changes must be tested before and after reaching the exit.

### Recipe 8: include or exclude named targets

Under **Routes & targets**, create a target list beginning with `TBL_PID_` and add PIDs. On an action operation:

- no `targets` list means all hostile units;
- `targets=TABLE, exclude=False` considers listed characters regardless of allegiance;
- `targets=TABLE, exclude=True` considers hostile units not in the list.

The second rule is deliberately strong: a positive list is not automatically “listed hostiles.” Use it only when targeting those identities independent of side is intended. Test a listed ally, listed enemy, unlisted enemy, dead/absent member, and changed allegiance.

## Understand every choice

| Operation | Main use | Key parameter/result |
| --- | --- | --- |
| `attack` / `attack_in_place` | ordinary combat | filters targets; in-place exposes only current tile |
| `use_staff` / `use_staff_in_place` | healing and supported status staves | needs valid staff routine and target |
| `steal` / `steal_in_place` | action 17 theft | skill, Speed, item table, capacity, adjacency |
| `move_to(x,y)` | fixed coordinate | `near` defines arrival distance; `r0=8` on arrival |
| `move_nearest` | pursue lowest path-cost target | `fallback` permits progress when no tile under threat limit gets closer |
| `move_safest` | lowest reachable threat | uses raw threat value, not attack score alone |
| `follow_route` | looping patrol | ordered route, movement budget, arrival radius |
| `talk_move` / `talk` | reach and execute a talk event | requires a matching unseen event |
| `escape` | reach escape event and leave | event kind 44 owns completion |
| `destroy_village` | doors/chests, then village destruction | requires village-destroy skill for village action; optional try limit |
| `break_object` | approach/act on breakable object | documented with tentative executable confidence |
| `set_scripts` | transition policy | changing running sequence resets its counter; both resets route/tries |

## Interactions and precedence

Within a unit's turn, recovery and special dispatch can precede ordinary Attack and Move interpretation. Within a script, the last successfully registered action wins unless a branch or stop protects an earlier candidate. Within candidate construction, range, path, occupancy, item use, status, allegiance, and operation-specific predicates remove illegal choices before scoring.

Routes, try counters, sequence program counters, and activation/escape state persist. A later chapter event can replace policy and reset some of that state. Equipment and map events are hard prerequisites: no sequence can make an unusable staff work or invent a missing talk/escape event.

## Test matrix

| Role | Success case | Boundary case | Failure case |
| --- | --- | --- | --- |
| stationary boss | attacks target already in range | displaced to another tile | target only reachable after movement |
| radius wake | target just inside count radius | target exactly on boundary | no eligible target / no weapon range contribution |
| patrol | visits all points and loops | attack beside route | next waypoint blocked |
| thief | steals preferred eligible instance | two eligible victims/items | equal Speed, full inventory, protected item |
| healer | heals flagged lowest-HP ally | HP exactly at each threshold | silenced, broken staff, no flagged ally |
| talker | reaches and triggers valid pair | target starts adjacent | event absent/consumed or adjacency blocked |
| escape | reaches kind-44 point and leaves | healing need on same turn | exit occupied/unreachable |
| filtered attack | intended included/excluded population | allegiance changes | table typo or absent PID |

Run each role for several turns, then save/reload after its state changes. Change one input per replay so the cause remains visible.

## Troubleshooting

**The unit has the right class but never performs the special action.** Check the explicit skill, item, event, target eligibility, and action operation. Class labels alone do not create policies.

**A boss attacks correctly, then walks away.** The attack candidate failed or was not protected, and the Move sequence registered movement. Inspect both sequences and recovery.

**A healer ignores a wounded ally.** The ally's Heal profile may not have set its needs-healing flag, the caster may be silenced/out of range, or another staff won the slot/rank scan.

**A thief chooses “worse” loot.** Check the victim's first eligible inventory slot, then Steal-table order. These are two different priority passes.

**A patrol freezes at one point.** Verify the coordinate, occupancy, path, budget, and reach radius. The interpreter does not skip an unreachable waypoint automatically.

**Talk or escape reaches the tile but never completes.** Confirm the corresponding unseen event and exact actor/target or event-kind wiring.

## Save, build, and revert

Press **Save AI data**, save deployments, and compile/save any event scripts. Run project checks and restart Play so it reloads those resources. Build and test in Dolphin after the app matrix passes.

To revert one recipe, restore the unit's original four policy identities and equipment/skills, then remove or disable only the added event/table when no other record uses it. Delete an appended CP record only when it is last and reference search is empty; otherwise leaving it unused preserves numeric IDs.

## Limits and confidence

The recipes use source-reviewed editor behavior and executable-backed AI operations. Core attack, movement, healing, route, target-filter, talk, steal, and escape semantics are confirmed. Operations labeled tentative in Raw entries remain unsuitable as the sole basis for a critical objective without Dolphin testing. Play does not simulate every skill and adjacent-unit scoring detail, so final parity belongs to the built game.

## Related tutorials and references

- [Read and edit AI scripts](43-ai-language.md)
- [Inspect why AI chose a target](45-inspect-ai-decisions.md)
- [Design, register, and test event flags](34-event-flags.md)
- [AI Activation, Routes & Orders](../systems/ai-activation-and-orders.md)
- [AI Healing & Special Actions](../systems/ai-healing-and-special-actions.md)
- [CP data format](../formats/cp-data-format.md)

---

[← Previous: Read and edit AI scripts](43-ai-language.md) · [All tutorials](index.md) · [Next: Inspect why AI chose a target →](45-inspect-ai-decisions.md)
