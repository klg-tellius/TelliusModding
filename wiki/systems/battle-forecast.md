---
id: "battle-forecast"
title: "Battle Targeting & Forecast"
description: "How the map turns a chosen attacker, tile, target, and weapon into the pre-combat forecast"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Combat", "UI", "Balance"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/battle-forecast.md"
system_entries: ["FE9-SYS-113", "FE9-SYS-114", "FE9-SYS-115", "FE9-SYS-116"]
system_reviewed: ["FE9-SYS-113", "FE9-SYS-114", "FE9-SYS-115", "FE9-SYS-116"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Battle Targeting & Forecast

The forecast is a **preview of one legal combat setup**, not combat itself. The map first chooses a destination, weapon, target, and distance; only then can it calculate the numbers shown to the player. Confirmation later revalidates the setup and consumes RNG, durability, HP, skills, and experience.

## Mental model and lifecycle

Treat the forecast as a pure snapshot between two mutable stages. Before it, movement and command construction choose legal inputs. After it, confirmation rechecks them and builds the authoritative combat log. The preview may calculate with current unit/item/map state, but it must not spend durability, change HP, mark units acted, or advance the combat random generator. Cancel discards the snapshot.

## FE9-SYS-113 — Target selection

<span id="fe9-sys-113"></span> Candidate targets must be alive/on-map, hostile under current allegiance, visible where fog rules require it, and within the selected weapon's legal range from the actor's committed destination. Objects such as breakable walls use their own action/target rules rather than becoming ordinary hostile units.

Target order matters to UI and AI tie-breaking but does not change legality. If a script changes allegiance, hides/removes a unit, or opens terrain after the menu was built, execution must reject the stale selection or rebuild candidates.

## FE9-SYS-114 — Weapon selection

<span id="fe9-sys-114"></span> A weapon is a usable inventory instance whose shared definition passes class/skill/character restrictions, whose rank is no higher than the unit's WEXP, whose uses remain, and whose range covers the target distance. Silence removes applicable tomes/staves; untransformed laguz cannot use their transformed natural strike. The currently equipped weapon is a default, not permission to attack outside its range.

The UI may let the player choose among legal weapons and updates forecast for each. Choosing a different weapon can alter Attack Speed through weight, triangle, effectiveness, attack stat/type, range, hit/critical, stat bonuses, skill conditions, and defender counter eligibility.

## FE9-SYS-115 — Defender weapon selection

<span id="fe9-sys-115"></span> The defender counters only with a usable weapon that reaches the actual distance. In runtime/save inventory, one item can carry the equipped flag, but a counter still needs current legality. If no equipped weapon can counter, the forecast shows no defender attack even though the defender is armed.

The game's exact automatic fallback priority among multiple usable defender weapons needs a dedicated trace. TelliusModding's simulator chooses the first usable in-range weapon as an approximation; the article must not promote that implementation choice to confirmed retail behavior without comparison.

## FE9-SYS-116 — Battle forecast

<span id="fe9-sys-116"></span> For each side, forecast combines effective stats, chosen weapon, terrain, support/bond, biorhythm, triangle, effectiveness, statuses, passive skills, range, and special protection. It presents HP and weapon plus the combat-facing values generally understood as damage, hit, critical, and strike/follow-up information.

The calculation layers are:

1. Resolve current stats and weapon legality.
2. Determine physical versus magical attack and applicable defense.
3. Apply weapon triangle, effectiveness, terrain/support/biorhythm, and passive modifiers.
4. Compute Attack Speed and the +4 follow-up test.
5. Clamp displayed hit/critical and apply hard overrides such as crit sealing, status-hit behavior, or blessed armor.
6. Determine whether the defender can counter at this distance.

The forecast cannot promise an outcome. Hit and critical still roll, proc skills can alter strikes/damage/order, weapons can break during a multi-strike exchange, and death can prevent later scheduled exchanges. Brave strikes and speed follow-ups are separate quantities.

## Worked examples

If an attacker at range 2 selects a 1-range sword, the sword is not a legal candidate and no forecast exists. Selecting a 1–2 range weapon may create a forecast, while the defender with only a 1-range weapon shows no counter.

If switching from Iron to a heavier Steel weapon increases Attack but lowers Attack Speed below the +4 threshold, displayed damage per strike can rise while the expected total number of exchanges falls. If the weapon is effective, its might is doubled before defense; if the target has Full Guard, that branch is suppressed.

## Interactions and safe interpretation

- The forecast reads current state and should not advance combat RNG.
- Parity can suppress defined terrain/support/skill contributions.
- Vantage changes exchange order, not the displayed base damage formula.
- Cancel can remove a counter after the forecast has shown the defender's capability.
- Forced/scripted battles may bypass ordinary selection or force outcomes.
- UI rounding/clamping must be distinguished from internal intermediate values.

## Implementation trail and failure behavior

The trail begins with runtime faction and visibility grids, the acting unit's candidate destination, eight inventory instances, class/skill access, weapon EXP, and item definition fields for type, rank, uses, might, hit, weight, critical, and range. Forecast construction produces combat-actor records and a proposed exchange log. The player UI reads that snapshot; AI scoring reads closely related predicted damage, hit, kill, and counter-risk values. Final combat rebuilds or validates the setup before consuming RNG.

An empty target list returns to command selection. An empty weapon list suppresses Attack. A defender with no legal in-range weapon remains a valid target but has no ordinary counter. A target that dies, moves, changes force, becomes hidden, or becomes unreachable before confirmation invalidates the stale setup. Forced event battles can deliberately bypass menu selection, but their forecast-like inputs must still respect whatever outcomes the script does not override.

## Interactions and review boundary

All forecast systems are reviewed without a blocking research gap. Target enumeration, weapon legality/range, defender counter selection, effective-stat formulas, exchange construction, and read-only UI/AI consumption share inputs with the authoritative resolver. Mid-battle procs or breakage can alter later strikes because resolution revalidates each step; the forecast remains an initial snapshot rather than a promise. No new primary article is needed.

