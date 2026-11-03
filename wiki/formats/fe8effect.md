---
id: "fe8effect"
title: "FE8Effect.bin"
description: "The visual-effect registry for combat, spell, and environmental presentation"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics","Animation","Registry"]
aliases: ["tellius_archive.html#/fe8effect"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/fe8effect.md"
---
# FE8Effect.bin

*The visual-effect registry for combat, spell, and environmental presentation*

The registry contains 263 **`EID_`** (Effect ID) entries covering combat and spell visuals: `EID_FIRE`/`FIRE2`/`FIRE3`/`FIRE4` (spell tiers), `EID_BREATHRED`/`BREATHWHITE` (dragon breath), `EID_CLASSCHANGE`, `EID_COUNTER`, `EID_GODDESS`, and environmental effects such as `EID_CLOUDOFDUST`/`CLOUDOFSNOW`.

## How an effect ID becomes a visual sequence

A combat, spell, skill, or environment system requests an `EID_`. The registry supplies flags and, for chained effects, a pointer to the next stage. Following those links produces the ordered visual sequence while the underlying gameplay calculation remains in its owning system.

## Example: Fire4

`EID_FIRE4` advances through `EID_FIRE4_2` and `EID_FIRE4_3` before reaching terminal `EID_FIRE4_2D`. These are stages of one presentation chain, not four independent damage applications.

  Uses the same container as [FE8Anim.bin](./fe8anim.md): its data section starts with the record count (263). 263 &times; 12-byte records, each with a name pointer (263/263 resolve, zero exceptions), a flags word, and an optional second pointer.

<div class="table-wrap">
<table class="tight"><thead><tr><th>Byte</th><th>Values seen</th><th>Reading</th></tr></thead><tbody>
    <tr><td>0</td><td>0, 2, 4, 5, 6</td><td>Plausible category enum</td></tr>
    <tr><td>1</td><td>0&amp;ndash;66, continuous</td><td>Unconfirmed — structurally similar to a <a class="wl" href="../../systems/skills/">skill's confirmed ID space</a></td></tr>
    <tr><td>2</td><td><strong>always 5</strong></td><td>Constant — a fixed record-type tag</td></tr>
    <tr><td>3</td><td>mostly 0; rare 2/3/5/7/10</td><td>Too rare a signal to name</td></tr>
  </tbody></table>
</div>

!!! info "The second pointer is a chain, not a sibling"
    53 of 263 records carry a nonzero second pointer. Following it repeatedly from a tiered spell always eventually reaches a `_2D`-suffixed terminal entry — real chains found up to 3 hops long: `EID_FIRE4` &rarr; `EID_FIRE4_2` &rarr; `EID_FIRE4_3` &rarr; `EID_FIRE4_2D`. Simpler cases are a single hop straight to a `_2D` sibling. Read as “next effect stage/fallback to play.” <span class="confidence confidence--confirmed">confirmed</span>

  Battles play the `EID_K_` packs: a weapon table in `xwp/` names its spell (`effectId EID_K_WIND`), and the hit, miss and death marks are `EID_K_ATTACK`, `EID_MISS`, `EID_K_DEATH` and so on (see [Battle Staging & Camera](../systems/battle-staging.md)). Each pack's animation fades its materials with one alpha track per material and can move the effect to its target with markers 0x11–0x13.

  See [Combat & Battle Animation](../systems/combat-animation.md) for where these effects fit relative to a unit's own battle animation.
