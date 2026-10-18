---
id: "weather"
title: "Weather"
description: "One controller process per map, dispatching to a different child effect by weather id"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Graphics","Structure"]
aliases: ["tellius_archive.html#/weather"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/weather.md"
system_entries: ["FE9-SYS-079", "FE9-SYS-080"]
system_reviewed: ["FE9-SYS-079", "FE9-SYS-080"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# Weather

*One controller process per map, dispatching to a different child effect by weather id*

A chapter map can carry ambient weather, implemented as one small parent process that reads the map's stored weather id and starts whichever concrete effect that id maps to. Loading a map — including a mid-chapter map change — re-checks the id and swaps effects if it changed, rather than baking the choice in once at chapter start.

## Mental model: a scene recipe, not a terrain rule

Weather and lighting describe how the battlefield is presented. Weather selects a long-lived effect process and battle-sky family; `maplight` colors ordinary models; `mapfog` controls camera-distance haze. They do not change movement costs or gameplay visibility by themselves. A rain texture cannot make a tile harder to cross unless an event separately changes terrain, and visual fog cannot reveal or conceal a tactical enemy—the [Maps](./maps-system.md#fe9-sys-077) sight grid owns that rule.

## Weather lifecycle

<span id="fe9-sys-079"></span> The weather id occupies five bits of `mapextra`'s flag word, allowing values 0–17; an invalid value is normalized to 0. Map load creates a controller, reads the active id, and dispatches the matching child effect. `SetWeather(weather)` replaces the byte at runtime, refreshes weather, lighting, and visibility rendering, and yields so scripts do not race the transition. Map changes and save reconstruction re-enter the same setup path.

## Dispatch table

<div class="table-wrap">
<table><thead><tr><th>Weather id</th><th>Effect</th></tr></thead><tbody>
    <tr><td><code>2</code>–<code>4</code></td><td>Falling rain at three intensity settings</td></tr>
    <tr><td><code>5</code>–<code>7</code></td><td>Snow through stronger blizzard variants</td></tr>
    <tr><td><code>8</code></td><td>Dedicated sandstorm effect</td></tr>
    <tr><td><code>10</code></td><td>Water/wave environmental effect</td></tr>
    <tr><td><code>1</code>, <code>17</code></td><td>A shared moving overlay rather than two independent implementations</td></tr>
  </tbody></table>
</div>

  The rain intensities are the same underlying effect started with different opacity values, not separate implementations — a general pattern for this system: distinct *ids* don't always imply distinct *effects*.

Weather is state, while the child particles are presentation. On unload or id change the old child must be stopped before the new one is installed. On resume the controller derives the effect from stored map state instead of serializing individual raindrops or snowflakes. This is also why a modder should change weather through the setter or load data, not merely spawn a visual effect that will disappear at the next reconstruction.

## The sky in battle

  The map's weather id also picks the sky of the battle scenes, from a list in [FE8Data.bin](../formats/fe8data.md): clear sky, clouds, night, sunset, sandstorm or mountain sky. <span class="confidence confidence--confirmed">engine</span>

## Relationship to terrain rendering

  The shared moving-overlay effect is the same visual resource as the optional third overlay step described in [Terrain Texture Blending](./terrain-texture-rendering.md) — weather and terrain rendering share this one moving-cloud-shadow texture rather than each maintaining its own copy.

## Lighting, ambience, and visual fog

<span id="fe9-sys-080"></span> Each map's 12-byte `maplight` record is a compact lighting recipe: signed Y and Z direction angles at `+1/+2`, ambient RGB at `+3..+5`, and directional/diffuse RGB at `+6..+8`. The loader copies those bytes to live map state. Camera-light setup converts both angles to radians, applies the Z rotation directly, and applies the negated Y rotation; this is the exact vector convention. Ordinary static materials bind their first texture and modulate it by the resulting raster/material color, so edits affect terrain and props without rewriting their textures. The record's enabled byte is always 1 in the retail corpus; unused tail bytes remain raw data rather than inputs to the system.

Scripts can change the two color contributions independently. `SetAmbient(red, green, blue)` replaces the ambient/model color; `SetDiffuse(red, green, blue)` replaces the directional color. Both refresh the map and yield. Values are byte-sized colors, so a script or editor should validate the 0–255 range rather than expecting HDR or floating-point intensity. These calls alter current map presentation; they do not change the source `map.bin` on disc.

`mapfog` is another presentation record: enabled state, a mode code, signed start and end distances, and RGB color. At runtime an enabled mode becomes stored code + 1, while distances are scaled by `5 × map scale`. `SetFog` changes those values. This is camera-distance haze only and is deliberately separate from `SetSight` gameplay visibility. A night scene can therefore use dark ambient light and dense blue distance fog while retaining ordinary tactical sight, or a fog-of-war chapter can conceal enemies while using no distance fog at all.

The final look composes static light, distance fog, sky, weather particles, terrain callbacks, and special object materials. Default materials use texture-times-raster modulation; projected terrain, additive waves, and particles deliberately install their own TEV/blend state. These are separate material paths, not ambiguous alternate meanings of the maplight bytes.

## Example

  A chapter flagged with the heavy-rain id starts the rain effect at its higher intensity automatically when its map loads; a save resumed mid-chapter on the same map performs the same check and reaches the same result, so the effect is a property of the map's stored data rather than a one-time scripted event.

For a dusk transition, an event can set warmer ambient and diffuse colors, adjust visual fog, then change the weather id. Each setter refreshes or yields according to its native contract. If the scene is skippable, its final calls must still execute or an instant path must install the same colors and weather; otherwise normal and skipped play reach different presentation state.

## Inputs, outputs, and modding limits

Inputs come from `mapextra`, `maplight`, `mapfog`, weather resources, sky tables in `FE8Data.bin`, and event-script setters. Outputs are controller processes, renderer light/fog state, selected battle sky, and material callbacks. Tactical terrain, pathfinding, and visibility consume none of these values directly.

 FE9-SYS-079 has no blocking research gap: dispatch families, setter behavior, reload lifecycle, sky linkage, and effect ownership are established.

## Review boundary

FE9-SYS-080 is reviewed without a blocking gap. The signed angle convention, ambient/diffuse byte ownership, fog scaling and colors, script setters, save fields, ordinary-material modulation, and special-callback separation are executable-derived. Hardware quantization differences are renderer fidelity work, not an unresolved lighting-system contract.
