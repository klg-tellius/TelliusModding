---
id: "map-objects"
title: "Map Objects & Placement"
description: "What can be placed on a map, and the formula that puts it in the right spot"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Graphics","Structure"]
aliases: ["tellius_archive.html#/map-objects"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/map-objects.md"
system_entries: ["FE9-SYS-068", "FE9-SYS-069", "FE9-SYS-070", "FE9-SYS-071", "FE9-SYS-072", "FE9-SYS-073", "FE9-SYS-074", "FE9-SYS-075", "FE9-SYS-076", "FE9-SYS-081", "FE9-SYS-082"]
system_reviewed: ["FE9-SYS-068", "FE9-SYS-069", "FE9-SYS-082"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# Map Objects & Placement

*What can be placed on a map, and the formula that puts it in the right spot*

A map object is reusable scenery or an invisible marker; an instance is one placement of that object in the chapter's 3D world. Keeping definition and placement separate lets one model appear many times with different positions and rotations.

## Mental model: definition, instance, and tile state

Read the object description to learn model, footprint, and flags, then read each instance that refers to it to obtain position, angle, and height. Rendering combines those values with the map's terrain anchor and scale.

Interactive scenery often has a third layer: a compact runtime tile-object record stores opened, visited, damaged, or remaining-use state. The model/instance says what can be drawn and where; the tile record says what changed during play. A decorative tree may need only the first two layers, while a door combines all three.

## How the map-object system loads

<span id="fe9-sys-068"></span>

  Every distinct "thing" a chapter's map can contain is one `mapbuilddesc` record: a filename (or none, for an invisible marker), the model's bounding box (its minimum and maximum corners in world units — the second triple is the maximum corner, not a size), and a set of flag bits. Two of those flags are confirmed with zero exceptions across every real chapter map in the game:

- **Is this the map's own base terrain or water plane?** — every object with this flag set is literally named after its own map (e.g. `bmap07`, `bmap07_water0`). A chapter typically has one or two of these.
- **Is this object animated?** — when set, the map loader gives the object its `.ga` [animation file](../formats/model-formats.md) and plays it like a unit's animation (a moving water plane, a flickering candle, a collapsing house). <span class="confidence confidence--confirmed">engine + files</span>

  The remaining runtime classification is a bitfield, not one opaque object type. In the descriptor's presentation byte, bit `0x01` selects the alternate actor-update pass, `0x02` copies eligible roof corner heights into both elevation buffers, `0x08` requests the extended frustum test, `0x10` excludes footprint/tile-object tests, `0x40` suppresses drawing, and `0x80` excludes tile-object lookup. A separate flag byte initializes hidden state, can suppress drawing, and can exclude footprint testing. The goal bits are carried by invisible marker objects. Interaction still comes from the matching tile/action record: a visible model or familiar filename alone never grants Door, Visit, Break, or objective behavior.

## Instances — where they actually go

  An object only appears in the world once something places it: a `mapbuildinst` record, giving a tile-grid position (`x`, `y`), a rotation angle, the rectangle of tiles the object covers once rotated, and a packed value that turns out to encode vertical position. A single object can have several instances — the same tree model planted a dozen times across a forest, for example.

  The game reads that rectangle only for roofs, houses, doors and rocks, on maps that switch the test on: a unit standing inside one is marked, most plausibly as being under the roof, and the game never picks such a tile when it looks for a free place to put a unit. <span class="confidence confidence--confirmed">engine</span>

  For quarter turns the covered rectangle follows one rule: an object *w* tiles wide and *d* deep (its maximum corner divided by 5, rounded, at least 1) covers *w*&times;*d* tiles from its position at angle 0, and the rectangle swings around the placed tile for 90&deg;, 180&deg; and 270&deg;; the rule reproduces 95% of the game's own placements, the rest being mostly wave effects set at free angles. <span class="confidence confidence--strong">files</span> Vanilla props sit at the terrain surface of their tile centre.

  New objects work like the game's own: a prop model added to a chapter's archive with its object record, then placed by new instance records, drew textured, rotated and standing on the ground in the Prologue. A prop does not change how its tiles play — the tiles' [terrain types](../formats/fe8data.md) do. <span class="confidence confidence--confirmed">in game</span>

  Every model of a chapter map — terrain, water and props — takes its images from one shared [TPL](../formats/tpl-texture.md) file in the map archive, `texpack.tpl`, by image number. Every vanilla map uses each image of its file, and nothing else in the archive refers to the numbers: an image can be removed as long as every model's numbers are shifted with it, and the map draws unchanged. <span class="confidence confidence--confirmed">in game</span> Nearly every image in it carries one half-size [mip level](../formats/tpl-texture.md), drawn when the ground or prop is seen from afar.

  The native world-space placement formula is:

  world = Translate(position) · Scale(map_scale) · Translate(+pivot) · Rotate(angle) · Translate(−pivot)

  Two details make this less obvious than it looks. First, an object rotates around the **center of its own 5-unit-wide tile cell**, not around its raw placement origin — the pivot term above. Second, a placed object's terrain isn't rendered at the origin the way you'd expect: a terrain mesh's own raw geometry sits in a corner-anchored box starting at `(0, 0)`, while every other object's position is computed in a space centered on wherever the terrain's *own instance* says the terrain should sit. The fix is symmetric: every non-terrain object gets shifted by the exact negative of the terrain's own placement offset, compensating for the terrain being drawn unshifted. In every real chapter checked, this puts every ordinary prop inside the terrain's own physical footprint, with zero exceptions.

  This placement math is independent of, and should not be confused with, the tactical grid a player actually moves units on — see [Coordinate Systems & Grids](./map-grid.md).

## Units under a roof

  On maps whose map data turns roofs on (most story maps, the tutorials and the trial maps), a unit whose tile lies inside an active covered object's area receives state bit `0x80` every time the units are refreshed. The bit is better understood as **interior inactive** than merely "under a roof": it does not hide the model, but both the player activation scan and the AI turn-order builder reject the unit in the same mask as an acted, carried, dead or reserve unit. `CheckAttackable` answers no for it, next/previous-unit cycling skips it, and targeting, reinforcement and deployment checks pass over it. Opening a door or roof rebuilds the map-object state and immediately refreshes every unit, clearing the bit and admitting the revealed occupants to activation and targeting; closing it recomputes the exclusion. <span class="confidence confidence--confirmed">engine</span>

At load, object descriptions become runtime actors and each instance supplies placement, footprint, initial visibility/state, animation, and draw/update classification. Doors, houses, roofs, rocks, water, and goal markers opt into different native tests through flags and companion tile records; merely giving a decorative model a familiar filename does not create an Unlock, Visit, or Break command.

## Persistent tile-object state

<span id="fe9-sys-069"></span> The live map owns up to 64 compact `T  T` records. Types 4 and 7 hold breakable-wall HP and ballista item/uses; types 9 and 10 cover pits and rolling rocks; types `0x21`–`0x25` record opened doors, opened roofs, opened chests, visited villages, and destroyed buildings. Scripts and action executors create or update these records when the interaction commits.

Checkpoint and map saves serialize the count and all 64 records after units, convoy, and forges. Reload reconstructs the chapter map, then restores this changed state so a door does not close, a chest refill, a wall heal, or a ballista regain ammunition. Visual animation and state mutation are distinct: during event skip an object can jump directly to its final appearance, but the same persistent record still must be written.

The record coordinates use the tactical grid and must remain valid for the loaded map. Replacing map geometry without migrating live save records can attach old state to a different object or empty tile. Conversely, editing only a visual instance does not create persistence; the action or script must update the tile-object system.

## Water and animated environment

<span id="fe9-sys-082"></span> Water and environmental animation belong to the scenery actor layer, not the tactical terrain grid. A chapter commonly defines its base terrain and a separate water plane as map objects, places both with instance transforms, and draws them from the same `texpack.tpl`. The tile panels still determine where units stand and what terrain rules apply; raising a wave mesh or changing its texture does not raise a unit or make a tile aquatic.

Animated objects carry the animation flag and load a matching `.ga` resource when one exists. The loader creates runtime actors, the map update advances their timers, and the draw pass evaluates the resulting model pose or material state. Across the retail corpus, 96 props are animated, 50 use bone animation, and 86 have matching `.ga` resources. Waves and candles illustrate looping ambience; houses and thickets include one-shot state changes. Repeated instances can stagger their timers so a field of identical props does not move in lockstep.

Water also exercises a special render path. `mapextra` bit `0x20` installs the water callback. It reads four values from the water animation's footer slot 3 (channel 0 at keys 0 to 3, through the same signed frame/value interpolation used by other material tracks, at a scale of `0.001`): the scroll speeds of the water's two texture layers. Effect actors do not consume that slot. The shore waves are props of their own. `wave_99` strips stretch toward the shore and fade in and out through their animation's alpha tracks, drawn with ordinary alpha blending. Ship wakes (`ship_wave_01`/`_02`) use source-alpha/one additive blending, so black contributes nothing and pale foam brightens the surface beneath it instead of drawing a black rectangle. Terrain blending and water rendering share callback installation but have distinct texture-stage formulas; see [Terrain Texture Blending](./terrain-texture-rendering.md).

For example, placing a new wave requires more than a textured model: the object description must select the appropriate animation and draw classification, its instance must use the scenery coordinate transform and suitable height, its animation resource must match, and the map flags must enable the required callback. None of that creates collision, movement cost, or save state. A destructible animated house separately needs the action/event and persistent tile record described in [Map Actions](./map-actions.md).

The lifecycle ends when the map unloads; transient animation time is reconstructed on load rather than serialized like door or ballista state. Authored one-shot changes that must survive use the persistent object-state records and rebuild the proper endpoint. Unknown names for unused flag combinations do not change this contract: the executable-level consumers, update/draw selection, water-track ownership, tactical separation, and persistence boundary are established.

## Interactions and limits

FE9-SYS-068 and FE9-SYS-082 are reviewed without blocking gaps. Object construction, transforms, footprint gates, every operational descriptor bit, tile-action separation, animation loading, water callback selection, U/V track ownership, blend family, teardown, and saved-versus-transient state are established. Pixel-level appearance of unused combinations remains rendering experimentation rather than an unresolved system rule.

FE9-SYS-070–075 are now reviewed in [Map Actions](./map-actions.md). FE9-SYS-076 remains revision-required there because the hidden-item declaration, chance, retry, transfer, collection, AI, and save rules have not been recovered.
