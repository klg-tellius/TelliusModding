---
id: "combat-animation"
title: "Combat & Battle Animation"
description: "How a class, a weapon, and a character combine into the animation actually shown in battle"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Graphics","Animation"]
aliases: ["tellius_archive.html#/combat-animation"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/combat-animation.md"
system_entries: ["FE9-SYS-155", "FE9-SYS-158", "FE9-SYS-159", "FE9-SYS-160", "FE9-SYS-161", "FE9-SYS-163", "FE9-SYS-164", "FE9-SYS-165", "FE9-SYS-166", "FE9-SYS-167", "FE9-SYS-168"]
system_reviewed: ["FE9-SYS-155", "FE9-SYS-158", "FE9-SYS-159", "FE9-SYS-160", "FE9-SYS-161", "FE9-SYS-163", "FE9-SYS-164", "FE9-SYS-165", "FE9-SYS-166", "FE9-SYS-167", "FE9-SYS-168"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Combat & Battle Animation

*How a class, a weapon, and a character combine into the animation actually shown in battle*

A map-model animation is a pipeline across four formats. [A class](./classes.md) selects the `ymu/<class>/` folder holding its map model's [skeleton, mesh, and animation clips](../formats/model-formats.md). [FE8Anim.bin](../formats/fe8anim.md) names each `.ga` clip and tags it with a weapon type, using the same category enum as the class's weapon-rank string.

## Map models and battle models

This registry drives the **map models** (`ymu/`): the units seen on the map and the combat played there. The battle scene uses a separate, detailed **battle model** from `zu/<code>/`, chosen through `jobList.dbx` by animation ID, character or class (see [ZDBX & DBX](../formats/zdbx.md)). Its animations sit in one pack per weapon type and are named by action and weapon — `fig1_at1_ax.ga` (first axe attack), `_at2_` (second attack), `_cr1_`/`_cr2_` (criticals), `_dog_` (dodge), `_dam_` (damage), `_ded_` (death), plus combined clips such as `_cr1_ax_dog`. <span class="confidence confidence--confirmed">confirmed in game</span> See [model formats](../formats/model-formats.md).

## How the visible battle is assembled

Class chooses the model family, weapon context chooses a compatible animation category, character tags may select an override, the `.ga` clip poses the model, and `EID_` chains add spell or skill visuals. Combat mechanics separately decide hits and damage.

## Map versus full-battle presentation

<span id="fe9-sys-155"></span> The presentation choice is resolved before playback from the saved animation option plus caller-imposed scene restrictions. Map presentation keeps tactical models/camera; full battle presentation constructs `zbg/` scenery, detailed `zu/` actors, weapon assets, scripted cameras, HUD, and effects. Both receive the same completed strike log. An encounter override replaces presentation policy only—it cannot change Hit, damage, durability, EXP, or strike order—and an unavailable full-scene path safely uses the map presenter.

## Model selection

<span id="fe9-sys-158"></span> **Class and character model selection.** Map presentation begins with the animation ID on the character when one exists and otherwise uses the class default. `FE8Anim.bin` resolves that ID to a model folder and compatible weapon categories. Full battle presentation performs the parallel lookup through `jobList.dbx`, where class and character keys can select a detailed `zu/` model. A character override changes appearance without changing the class record that supplies stats and weapon permissions.

<span id="fe9-sys-159"></span> **Weapon-model selection.** The equipped `IID_` is reduced to its item label and opens `xwp/<item>.dbx` from `zdbx.cmp`; its Model block names the pack attached to the chosen rig. `r_hand`, `l_hand`, and weapon-family anchors supply the parent matrices, while authored model-local transforms supply the remaining offset. A missing optional weapon visual leaves the combat actor usable without changing item mechanics; a missing required actor/model rejects full-scene construction and falls back to the map presentation path.

## Animation lifecycle and events

<span id="fe9-sys-160"></span> **Battle animation state machine.** The scene enters idle, chooses an action role from the resolved strike, optionally runs into range, plays wind-up and attack, reacts with dodge or damage, then returns or advances to death and teardown. Normal, second, critical, killing-critical, skill, and thrown attacks have distinct role names. A role can fall back to a simpler attack or critical clip, and a previous-action variant can preserve visual continuity across consecutive actions. The authoritative strike log remains the input; animation completion and markers control presentation timing, not whether the strike exists.

Actor parameters provide approach range/speed, jump and knockback tuning, and three blend durations. Zero duration selects global defaults of 15 general, 5 run, and 20 stand ticks. Transitions use a quadratic interpolation and release the old source at the requested tick count; interruption selects another legal presenter state but never removes an unresolved strike from the log.

<span id="fe9-sys-161"></span> **Animation events.** Markers embedded in `.ga` and effect animation tracks synchronize events that cannot be inferred from clip length alone. Combat and swing markers identify impact or dodge timing, release markers detach arrows or thrown weapons, effect markers move a spell to its target and identify hit or miss, and dramatic markers spawn dust, water, or snow. A marker is therefore an authored callback point in a running presentation object. Unknown marker codes must be treated as unknown rather than reordered or deleted during animation editing.

The marker contract is role-based rather than a global numeric effect table: the active actor/effect controller interprets only marker families it owns and ignores or diagnoses unsupported callbacks. This bounds custom-animation safety without requiring every unused code combination to be assigned a speculative meaning.

## Spells and particle effects

<span id="fe9-sys-163"></span> A weapon or skill selects an `EID_`, [FE8Effect.bin](../formats/fe8effect.md) resolves it to a `yme/` pack, and that pack supplies its model, animation, and any chained stages. Placement depends on the effect: a cast can begin at the user, an impact at the target, and ordinary hit/death effects at the affected unit. Spell animation markers own travel and impact timing, while material alpha tracks make otherwise transparent effect geometry appear and fade. This gives modders three separate failure points to check: registry lookup, pack contents, and the markers expected by the battle scene.

The retail registry has 263 resolved names and finite chains of at most three links before a terminal stage. Emitter curves and material tracks remain presentation parameters inside the selected pack; changing them cannot change the already-resolved magical hit or damage. A broken chain terminates visual construction rather than recursing or altering combat state.

## Output layers and alternate path

<span id="fe9-sys-164"></span> **Battle HUD.** Full battle constructs named left/right widgets including `NumAtk`, `NumHit`, `NumCrit`, `HpWindow`, and `NameWin`. They read the prepared combatant/result records, interpolate displayed HP at result boundaries, and release with the battle scene. Map presentation uses its own compact UI but consumes the same values; neither HUD writes the combat result or decides whether a displayed strike lands.

<span id="fe9-sys-165"></span> **Damage and hit presentation.** A resolved hit chooses ordinary or special impact effects, starts the defender's damage reaction, flashes the screen, and applies camera shake derived from a quake value. A miss instead uses the dodge path and `EID_MISS`; zero damage uses `EID_NODAMAGE` plus its spark; a kill schedules the death effect relative to the death clip's fade marker. These are consumers of the result and must never be used as the source of damage state.

<span id="fe9-sys-166"></span> **Battle music and stingers.** Scene setup selects contextual `BGM_BTL_*`/boss cues and named `SFX_BTL_*` effects through the shared audio registry. Battle owns temporary start/fade/stop requests while the map scene retains its restoration context. Normal completion and skip both release battle voices and return audio ownership before tactical focus resumes; audio priority cannot delay consequence processing.

<span id="fe9-sys-167"></span> **Map battle animation.** The tactical path uses `ymu/` models and the `FE8Anim.bin` action registry instead of constructing the full `zu/`/`zbg/` scene. It still consumes the same resolved strike sequence, weapon category, hit/miss outcome, and final unit state. This common input explains why changing display mode must converge on the same HP, durability, EXP, and death consequences even though the clips and cameras differ.

<span id="fe9-sys-168"></span> **Skip and acceleration.** Input can shorten waits or advance the presenter only after the strike log exists. The skip route drains remaining presentation records to their semantic endpoints, completes HP/death display, stops or releases effects and audio, signals scene waits, and hands the unchanged consequence queue to death/EXP/objective processing. Animation-off, accelerated, map, full, and skipped paths therefore converge on identical gameplay state.

## Example

A Knight using a sword resolves a sword-compatible `AID_` into the Knight folder, loads its skeleton and mesh, and plays the selected clip. If the unit has a character-tagged override, that clip can change pose without changing the unit's class stats or weapon definition.

  A subset of animations are further overridden per *character*, not just per class: a 2-letter tag embedded in the animation's own name (`AID_KNIGHT_KE_N` for Kieran) lets a specific named unit get a custom weapon-holding pose distinct from the rest of their class. This is the mechanism behind, for instance, a named Knight-class character visibly carrying their weapon differently from a generic Knight enemy.

  Spell and skill effects layer on top of a unit's own animation via [FE8Effect.bin](../formats/fe8effect.md)'s `EID_` registry — a tiered spell like Fire4 doesn't just play one effect, it chains through up to three stages before landing on its final visual, each stage a separate registry entry.

  Weapon trails and attachment points depend on anchor bones in the class rig. Every character rig supplies `_s1_` and `_s2_`; weapon-specific pairs appear only on classes that need them, such as sword, spear, hand-axe, axe, bow, javelin, and effect anchors. Hand anchors are named separately with `r_hand` and `l_hand`. The parent bone supplies the world matrix and the weapon resource supplies its authored local transform; exact values remain per-asset tuning.

!!! info "What's actually confirmed vs. inferred"
    The name→folder→weapon-type chain is confirmed with zero exceptions (508/508 records). Character-first then class fallback establishes the override boundary. For battle models, which clip plays for which action (attack, critical, dodge, death...) comes from the model's `zu/<code>.dbx` role table; the order of a strike and its timing are described in [Battle Staging & Camera](./battle-staging.md).

## Interactions and limits

All combat-presentation entries are reviewed without a blocking research gap. Model and weapon lookup, actor transitions, controller-owned markers, finite effect chains, HUD result consumption, hit/miss/death presentation, audio handoff, map/full parity, and skip convergence are established. Per-asset transforms, unused marker codes, particle tuning, and frame-perfect cosmetic timing are authoring reference details, not unresolved system ownership. No new primary article is needed.
