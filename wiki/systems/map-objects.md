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
---
# Map Objects & Placement

*What can be placed on a map, and the formula that puts it in the right spot*

A map object is reusable scenery or an invisible marker; an instance is one placement of that object in the chapter's 3D world. Keeping definition and placement separate lets one model appear many times with different positions and rotations.

## How definition and placement cooperate

Read the object description to learn model, footprint, and flags, then read each instance that refers to it to obtain position, angle, and height. Rendering combines those values with the map's terrain anchor and scale.

## Objects — what can be placed

  Every distinct "thing" a chapter's map can contain is one `mapbuilddesc` record: a filename (or none, for an invisible marker), the model's bounding box (its minimum and maximum corners in world units — the second triple is the maximum corner, not a size), and a set of flag bits. Two of those flags are confirmed with zero exceptions across every real chapter map in the game:

- **Is this the map's own base terrain or water plane?** — every object with this flag set is literally named after its own map (e.g. `bmap07`, `bmap07_water0`). A chapter typically has one or two of these.
- **Is this object animated?** — when set, the map loader gives the object its `.ga` [animation file](../formats/model-formats.md) and plays it like a unit's animation (a moving water plane, a flickering candle, a collapsing house). <span class="confidence confidence--confirmed">engine + files</span>

  A third flag field is a 3-bit **battle-goal type**, carried by invisible, non-rendering marker objects rather than visible scenery — see [Objectives](./objectives.md) for what those markers represent.

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

  On maps whose map data turns roofs on (most story maps, the tutorials and the trial maps), a unit whose tile lies inside a roof object's area is marked as under a roof every time the units are refreshed. The mark does not hide the unit; it makes the game treat the unit as out of play for a few checks: the `CheckAttackable` script function answers no for it, the AI leaves it out when it ranks targets, the next/previous-unit buttons skip it, and reinforcement and deployment checks pass over it, as they do for a rescued or fog-hidden unit. <span class="confidence confidence--confirmed">engine</span>
