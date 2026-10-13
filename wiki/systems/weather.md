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
---
# Weather

*One controller process per map, dispatching to a different child effect by weather id*

A chapter map can carry ambient weather, implemented as one small parent process that reads the map's stored weather id and starts whichever concrete effect that id maps to. Loading a map — including a mid-chapter map change — re-checks the id and swaps effects if it changed, rather than baking the choice in once at chapter start.

## Dispatch table

<div class="table-wrap">
<table><thead><tr><th>Weather id</th><th>Effect</th></tr></thead><tbody>
    <tr><td>Rain (light)</td><td>Falling-rain particle effect at reduced intensity</td></tr>
    <tr><td>Rain (heavy)</td><td>The same rain effect at higher intensity</td></tr>
    <tr><td>Snow / blizzard</td><td>A separate snow/blizzard particle effect</td></tr>
    <tr><td>Sandstorm</td><td>A dedicated sandstorm effect</td></tr>
    <tr><td>Water / waves</td><td>A moving-water effect layered over the terrain</td></tr>
    <tr><td>Shared overlay</td><td>A moving cloud-shadow overlay, reused by two separate weather ids rather than each getting a dedicated effect of its own</td></tr>
  </tbody></table>
</div>

  The rain effect's two intensities are the same underlying effect started with a different opacity value, not two different implementations — a general pattern for this system: distinct *ids* don't always imply distinct *effects*.

## The sky in battle

  The map's weather id also picks the sky of the battle scenes, from a list in [FE8Data.bin](../formats/fe8data.md): clear sky, clouds, night, sunset, sandstorm or mountain sky. <span class="confidence confidence--confirmed">engine</span>

## Relationship to terrain rendering

  The shared moving-overlay effect is the same visual resource as the optional third overlay step described in [Terrain Texture Blending](./terrain-texture-rendering.md) — weather and terrain rendering share this one moving-cloud-shadow texture rather than each maintaining its own copy.

## Example

  A chapter flagged with the heavy-rain id starts the rain effect at its higher intensity automatically when its map loads; a save resumed mid-chapter on the same map performs the same check and reaches the same result, so the effect is a property of the map's stored data rather than a one-time scripted event.
