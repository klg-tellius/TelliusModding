---
id: "ai-healing-and-special-actions"
title: "AI Healing & Special Actions"
description: "How AI units decide to recover, borrow items, seek refuge, use staves, steal, chant, or consume items"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["AI", "Items", "Skills"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/ai-healing-and-special-actions.md"
system_entries: ["FE9-SYS-263", "FE9-SYS-264", "FE9-SYS-265", "FE9-SYS-266", "FE9-SYS-267", "FE9-SYS-268", "FE9-SYS-269", "FE9-SYS-270", "FE9-SYS-271"]
system_reviewed: ["FE9-SYS-263", "FE9-SYS-264", "FE9-SYS-265", "FE9-SYS-266", "FE9-SYS-267", "FE9-SYS-268", "FE9-SYS-269", "FE9-SYS-270", "FE9-SYS-271"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# AI Healing & Special Actions

The AI runs a recovery/special-action layer before ordinary attack behavior. Its ordering explains why a wounded enemy may retreat or trade for medicine instead of taking an available combat.

## Mental model and example

Recovery is a persistent mode, not a fresh “am I hurt?” check every frame. If a profile sets `retreat_below` to 40% and `resume_at` to 70%, a unit falling to 35% enters needs-healing state. Healing to 55% does not release it; reaching 70% does. While flagged, the AI tries increasingly indirect solutions: use its own medicine, borrow medicine, reach healing terrain or a helper, or accept staff support according to the active program. This hysteresis prevents the unit from alternating between attack and retreat around one threshold.

<span id="fe9-sys-263"></span> **Healing-need hysteresis.** A heal profile has `retreat_below` and `resume_at`. Falling below the first sets a needs-healing flag; it stays set until HP reaches the higher resume threshold, preventing turn-to-turn oscillation.

<span id="fe9-sys-264"></span> **Self-healing item AI.** The unit chooses Vulnerary/Elixir by closeness to missing HP, preferring the smaller on a tie and fewer uses between equal items, then uses it from the safest reachable tile.

<span id="fe9-sys-265"></span> **Ally item borrowing.** The receiver must have fewer than four personal items. The scan considers same-faction donors adjacent to a reachable tile, ranks their slot 4–7 healing items by the same missing-HP fit, transfers the chosen instance into the first free slot, and immediately registers use. If transfer/use revalidation fails, no action is registered and ownership remains with the donor; equal-choice behavior follows item/scan order.

<span id="fe9-sys-266"></span> **Healing-terrain/refuge AI.** If direct items fail, sources are tried in the executable's order: reachable healing terrain, approach toward distant healing terrain, approach toward a staff user, then toward a non-hostile medicine carrier. Replacement requires no more nearby hostiles and a shorter path, so equality retains the first source/tile. A blocked source yields the next branch or no recovery move; it never overrides occupancy/path legality.

<span id="fe9-sys-267"></span> **Healing staff AI.** It targets allies whose heal-need bit is set. Heal/Mend/Recover choose the lowest HP percentage within their range; Physic uses the same need ordering over extended range. Fortify requires at least three qualifying allies anywhere and evaluates reachable caster tiles by the count within distance 1..range, breaking a count tie by the established tile score. Target scans run row-major and `<=` replacement makes the last equal target win.

<span id="fe9-sys-268"></span> **Status/support staff AI.** Restore takes the highest-effective-level status target (last on an equal value). Ward takes the lowest-Resistance ally, also last on a tie. Silence requires a non-silenced hostile magic/staff user and maximizes hit + Magic; Sleep/Berserk require an item-bearing hostile with no status and maximize hit + effective level. All three require computed hit above 4. Warp takes the highest-effective-level unacted eligible ally and builds a low-threat destination near the phase side's path-nearest hostile. Torch, Hammerne, and Unlock routines return failure, so retail AI never uses them.

Staff slots 0–3 are scanned deterministically: within a family an equal-or-higher-rank later staff replaces the prior choice, and the healing family is dispatched before non-healing staff work. Warp destination comparison retains the first lowest-threat legal tile and rebuilds the deciding unit's threat map on every return. These rules close combined staff priority and destination ties.

<span id="fe9-sys-269"></span> **Steal AI.** The actor needs `SID_STEAL`. Reachable tiles are scanned row-by-row and legal adjacent victims up/right/down/left; the thief must have strictly greater Speed. Victim slots 0–7 are scanned in order, taking the first instance that is carryable, not protected by its instance flag, and listed in `TBL_STEALITEMS`. The list index is the score: lowest wins, and the first candidate wins a tie. The thief uses the best adjacent tile, increments its try counter, and commits action 17.

<span id="fe9-sys-270"></span> **Chant AI.** The checker scans the `SID_CHANT*` family, tests the matching per-variant validator, inspects the 3×3 neighborhood for compatible acted allies, and scores legal targets/positions before attack fallback. Its comparator supplies deterministic ties, then it registers action 18 with the selected coordinates and target. The ordinary action executor owns refresh state and presentation.

<span id="fe9-sys-271"></span> **Item-use AI.** Operation 502 locates the configured held item and asks its map-effect-specific `<IID><suffix>` usability handler, so the effect owner—not CP bytecode—defines need/target thresholds. With no prior move it registers action 4 on the current tile; otherwise it records move-then-use with that exact instance. Missing, unusable, or invalidated items clear the found-action flag and fall through without spending uses; ordinary item execution owns commit and acted state.

## Rules and lifecycle

HP changes update or expose the heal profile's two-threshold state. When the scheduler reaches a flagged unit, recovery operations run before its ordinary attack/move path. Candidate builders inspect its inventory, reachable safe tiles, nearby donors, healing terrain, staff users, and other configured sources. Each branch uses ordinary item legality, inventory transfer, pathfinding, danger, staff range, target state, durability, and action commitment rather than silently editing HP.

Successful recovery updates HP/status, item uses or both inventories, movement/action state, and the needs-healing flag when the higher threshold is reached. If no recovery candidate exists, the program falls back according to its operation—advance toward a refuge, remain safer, or continue to another action family. Save/load preserves HP, inventories, status, acted state, and interpreter progress so the decision can be reconstructed.

Steal, Chant, and generic item use occupy the same pre-attack layer. Their action IDs, candidate order, eligibility, ties, and commit boundaries are exact. Item-specific need checks deliberately remain delegated to the same effect handlers used by ordinary item legality; duplicating that complete table in CP documentation would create a second authority.

## Interactions and edge cases

Borrowing must be atomic: a failed transfer or unusable medicine cannot delete the donor's item or consume the receiver's action. Refuge search must not choose an unreachable or newly occupied tile. Fortify's target count and a hostile status staff's minimum accuracy must be revalidated at commitment. Silence, full inventories, broken staves, changed HP, dead targets, and danger-map replacement can invalidate candidates after enumeration.

## Interactions and limits

All nine recovery/special-action systems are reviewed without a blocking research gap. Inventory transfer rollback, refuge source order, staff target/tile ties, family/slot priority, Chant dispatch, generic item delegation, and Steal selection are established. Individual item effect predicates remain owned by the item/staff systems rather than duplicated here. No new primary article is needed.

