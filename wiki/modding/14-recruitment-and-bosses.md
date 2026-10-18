---
id: "modding-recruitment-and-bosses"
title: "Recruit by talk and make a boss"
description: "Wire deployment, talk availability, guarded recruitment, boss AI, quotes, and objective state"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-supports", "modding-script-editor", "modding-deployment-by-difficulty"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Recruitment", "Bosses", "Events", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/14-recruitment-and-bosses.md"
---
# Recruit by talk and make a boss

**Route:** Chapter → Deployment; Chapter → Script; Chapter → Dialogue

## What you will make

You will create a talk-recruitable unit whose event runs once and persists, plus a stationary boss whose placement, AI, equipment, quotes, death state, and victory condition agree. Each behavior will be tested independently before integration.

## Before you begin

Choose exact speaker, recruit, and boss PIDs; deployment difficulty/section names; one unused chapter flag for recruitment; and a working chapter talk/boss pattern to compare. Checkpoint scripts, dialogue, and all deployment variants.

## How the editor fits together

Deployment creates an actor with PID/JID, army allegiance, coordinates, inventory, and AI/order fields. Script code decides when a talk option is registered, what function runs, whether `Join` changes the target to the player army, and which flag prevents repetition. Dialogue is a separate message resource. Boss identity/class does not create boss behavior: AI, equipment, quote triggers, death/defeat state, and objective logic are independent owners.

## Guided walkthrough

1. Add the recruit to an enemy or NPC deployment section for the intended difficulty. Give it valid coordinates, a usable inventory, and survivable behavior. Save and verify it appears before adding recruitment.
2. In Script, copy the structure of a working talk registration. Set exact speaker and target PIDs; direction matters if the registration distinguishes initiator/target.
3. Create the event function: test the unused chapter flag first; show the intended dialogue; call `Join` on the recruit PID; set the flag only after successful state change; then return. Compile and resolve diagnostics.
4. Save dialogue and script. Run Check, then test no-talk, valid talk, invalid speaker, and second-attempt paths. Confirm the recruited unit joins the roster/army and persists after save/reload.
5. Add the boss in the correct army/section with intended stats/class, equipment, drop behavior, and coordinates. Assign a hold-position or controlled activation AI/order rather than relying on the boss label.
6. Wire battle quote conditions, death quote, defeated flag/state, and the chapter objective or seize/defeat logic. Make each quote's PID/condition exact.
7. Put a player just outside the intended boss range, end turns, enter range, attack with quote and non-quote units, defeat the boss, and complete the objective. Repeat on every supported difficulty.

## Understand every choice

| Choice | Controls | Does not control |
| --- | --- | --- |
| Deployment army | initial allegiance | permanent recruitment |
| Section name | group loaded by exact script string | whether caller executes |
| Talk speaker/target | interaction availability | dialogue or Join result |
| Chapter flag | one-chapter repeat guard | campaign-wide persistence unless explicitly different |
| `Join` target | unit changed to player side/roster | talk registration removal by itself |
| AI/order | movement, targeting, activation | boss quotes/objective |
| Boss class/stats | combat properties | stationary behavior |
| Battle/death quote triggers | presentation on conditions | defeat state/objective completion |
| Defeat/objective logic | chapter progression | inventory/drop behavior |

## Interactions and precedence

The actor must exist before the talk can target it. A flag set too early can permanently suppress recruitment after an interrupted body; set it after success. Allegiance can change while AI/order fields remain unsuitable, so inspect the recruited unit's next action and later roster state. Boss death must converge with objective logic; a quote alone does not mark victory.

## Test matrix

| Test | Expected result |
| --- | --- |
| Chapter start | recruit/boss appear in correct sections |
| Wrong speaker | no recruitment talk |
| Correct speaker/target | dialogue, Join, then guard set |
| Repeat attempt | body cannot run twice |
| Save/reload | recruited state persists as intended |
| Boss target outside range | boss respects hold/activation design |
| Enter activation condition | intended movement/attack begins or stays fixed |
| Quote/non-quote attacker | quote fires only for intended condition |
| Boss defeat | death event and objective converge once |
| All difficulties | matching units, sections, equipment, and triggers |

## Troubleshooting

If talk is absent, confirm both deployed PIDs, registration timing, direction, and guard flag. If dialogue plays but the unit remains hostile, inspect the `Join` target and execution log. If it recruits then repeats, verify the same flag is tested and set after success. If the boss moves, inspect AI/order fields. If victory stalls, trace defeated-state and objective functions separately from the death quote.

## Save, build, and revert

Save each deployment variant, script, and dialogue owner; rerun Check and compile diagnostics. Build and use a fresh chapter state. Revert all coordinated resources together because an orphaned talk trigger, absent actor, or stale victory condition can crash or softlock.

## Limits and confidence

Ownership boundaries and guard/state logic are source-reviewed; exact available script commands and AI behavior depend on the chapter/compiler catalog. Play simulation may not implement every native. Dolphin tests are required for roster persistence, AI edge cases, quotes, and objectives.

## Related tutorials and references

- [Edit chapter scripts](33-script-editor.md)
- [Use chapter and campaign flags](34-event-flags.md)
- [AI Activation And Orders](../systems/ai-activation-and-orders.md)
- [Events Scripting](../systems/events-scripting.md)

---

[← Previous: Create supports and conversations](13-supports.md) · [All tutorials](index.md) · [Next: Remove records without corrupting saves →](15-remove-records.md)
