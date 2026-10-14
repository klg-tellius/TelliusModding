---
id: "battle-staging"
title: "Battle Staging & Camera"
description: "Where the fighters and the backdrop stand, how each blow is timed, and how the battle camera films it"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Combat","Battle Graphics"]
aliases: ["tellius_archive.html#/battle-staging"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/battle-staging.md"
---
# Battle Staging & Camera

*Where the fighters and the backdrop stand, how each blow is timed, and how the battle camera films it*

Once [combat resolution](./combat-mechanics.md) has decided every strike, the battle scene stages them one at a time. Everything runs on a 60-per-second clock: battle clips advance one frame per tick, and the waits and camera moves are counted in the same ticks. The timing values come from `zdbx/param.dbx`; each battle model adds its own speed, range and jump flags from its `zu/<code>_prm.dbx` table (see [ZDBX & DBX](../formats/zdbx.md)).

## Where everyone stands

  The attacker starts at x = −20 and the defender at x = +20 (`InitPosL` / `InitPosR`), each turned 90° about the vertical axis so that they face each other along X. The backdrop is a small map of its own, `zbg/<name>/bf.cmp`, loaded in a battle mode of the [map system](./maps-system.md): its `map.bin` lists the models and where each instance sits, in tiles. A battle backdrop's tiles are 15 units wide (5 × a scale of 3), and an instance turns about the centre of its tile, so each backdrop is shifted and turned until its open ground lies along the fighters' line. For example, `map03_ground01` sits at tile (−28, −5), turned 22.5°.

## One strike, tick by tick

<div class="table-wrap">
<table><thead><tr><th>Step</th><th>What happens</th><th>Ticks</th></tr></thead><tbody>
    <tr><td>Opening</td><td>Both units idle while the camera zooms in between them</td><td><code>WaitInit</code> = 120</td></tr>
    <tr><td>Turn change</td><td>Pause before the other unit's strike (none between two strikes of the same unit)</td><td><code>WaitAtk2</code> = 20</td></tr>
    <tr><td>Run in</td><td>A melee striker further than its range + 3 from its target plays its run clip <code>走り回数</code> times, moving <code>移動速度</code> units a tick toward the spot its range (<code>間合い</code>) short of the target. Models whose attack clip leaps in by itself (<code>ジャンプ攻撃</code>…) skip it.</td><td>run clip × run count</td></tr>
    <tr><td>Wind-up</td><td>Before a normal attack</td><td><code>WaitAtk0</code> + 1</td></tr>
    <tr><td>Attack</td><td>The attack clip plays; the blow lands on the clip's first combat marker (a miss is dodged on the swing marker). Damage makes the target flinch, flashes the screen and shakes the camera.</td><td>clip length</td></tr>
    <tr><td>Recover</td><td>After the attack clip ends</td><td><code>WaitAtk1</code> = 1</td></tr>
    <tr><td>Death</td><td>The death clip plays under the death camera, then a pause</td><td>death clip + <code>WaitDie1</code></td></tr>
  </tbody></table>
</div>

  The attack clip follows the strike: `攻撃1` (attack), `攻撃2` for a unit's second blow, `必殺1` (critical), `必殺2` for a critical that kills, `奥義` when an attack skill triggers, and `投げ` / `必殺投げ` / `奥義投げ` for thrown weapons; a missing clip falls back to the plain attack or critical. When a model has a variant named after its previous action — `必殺1_攻撃1`, a critical that flows out of an attack, or `回避_回避`, a second dodge — that variant plays instead.

  Bows and thrown weapons let go of their missile on the clip's release marker. Arrows travel 6 units a tick, thrown spears 5, hand axes 4.5 and knives 2.8, and they strike 2.8 units short of the target. A shot is followed by a 20-tick pause (`WaitShoot1`).

## The camera

  Each kind of strike has a camera script in `xcam/`: `atk_l` for attacks and skill strikes, `crit_l`, `crit2_l` for a killing critical, `ded_l` for a death, `mag_at_l` for tomes and bows, `mag_crit_l`, `mag_skill_l`, `atk_hand_sp_l` / `atk_hand_ax_l` for thrown spears and axes, and `bow_impact_l`, which follows the arrow or spear once it is released. Only the left-side scripts exist. When the defender strikes, the same script plays mirrored: every keyframe's turn becomes 360° minus itself and its sideways offset changes sign.

  Most class models also carry their own cameras, in `xcam/<model>/cam.cmp`: one script per battle clip, named like the clip (`fig1_at1_ax` for the Fighter's axe attack, `mgm1_at1_no` for the Mage's cast), covering attacks, criticals, skill strikes, ranged strikes, the run-in and the shuffle step. Whenever a unit switches clip, the script named by the clip's first 11 characters starts, if the model has one, following that unit (mirrored for the defender). The kind-of-strike script above is then skipped, so these per-clip cameras film most strikes. Idle, damage, dodge and death clips have none. `bow_impact_l`, `ded_l` and the spell cameras always play.

  A script drives one camera rig of `camera.dbx`. The rig looks at a unit's `cam` bone plus an offset (7 units up for the strike rigs), from `dist` units away, turned by the keyframe's pitch and yaw; a yaw of 180° films the fight side-on from in front. The rig's unit list decides who is followed: `camCharaL0` follows the striker, `camCharaR0` the one being struck. Keyframes play in order. Each one glides to its offset, angles and distance over its `time` in ticks along a smooth curve that carries the previous move's momentum, and a time of 0 cuts straight to it. The next keyframe starts as soon as the last move has finished.

  A blow that deals damage shakes every camera sideways. The shake's strength is 1.8 × the strike's quake value (0.5 for an attack, 1.8 for a critical or skill, 0.5 for a shot, 1.2 for magic). It swings once per tick and fades by 0.06 × the quake value each tick, for 60 ticks.

  The fight opens on the free camera `cam1`, pointed at the midpoint between the two units 9 units up, playing `standby`: a zoom from 170 down to 70 units. At range it plays `standby2` instead. The picture is a 30° vertical field of view at 4:3. When the Combat Camera option is set to "Fixed", the whole fight is filmed this way from the side: `cam1` plays `sideview` and keeps looking at the midpoint between the units, backing off to 1.4 × their distance plus `SideCamLen` (clamped by `SideCamMin`/`SideCamMax`). <span class="confidence confidence--confirmed">engine</span>

## Effects

  Every effect is a `yme/EID_*.cmp` pack (see [FE8Effect.bin](../formats/fe8effect.md)) that plays its own animation where it was put; battles use the `EID_K_` versions. Unless noted, an effect starts on the ground under the unit's root bone, turned the way the unit faces. <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table><thead><tr><th>Moment</th><th>Effect</th><th>Where and when</th></tr></thead><tbody>
    <tr><td>A blow deals damage</td><td><code>EID_K_ATTACK</code>, or <code>EID_K_SP_ATTACK</code> for a critical or skill strike</td><td>On the struck unit, <code>DamageEffWait</code> (1) tick after the blow. A missile weapon with a <code>damageEffId</code> in its <code>xwp/</code> table (Flame Lance, Lightning Bow, Sonic Axe) uses that instead</td></tr>
    <tr><td>A blow deals no damage</td><td><code>EID_NODAMAGE</code> and <code>EID_K_SPARK_ND</code></td><td>6 units above the struck unit</td></tr>
    <tr><td>A miss</td><td><code>EID_MISS</code></td><td>6 units above the unit that dodges</td></tr>
    <tr><td>A kill</td><td><code>EID_K_DEATH</code></td><td><code>DeathEffTime</code> (30) ticks before the death clip's fade marker</td></tr>
    <tr><td>A skill triggers</td><td>The skill's own effect</td><td>On the unit</td></tr>
    <tr><td>Dust</td><td><code>EID_CLOUDOFDUST</code> 1–5, or the <code>WATERSPLASH</code> / <code>CLOUDOFSNOW</code> sets</td><td>On markers in dramatic clips (codes 0x2B–0x2E and 0x3C), chosen by the backdrop's <code>footEffect</code> in <code>zbg/&lt;name&gt;/param.dbx</code>: 1 dust, 2 water, 3 snow, 0 or 4 none</td></tr>
  </tbody></table>
</div>

  A tome's spell is the `effectId` of its `xwp/` table (Wind is `EID_K_WIND`). It appears on the cast clip's release marker, at the caster for missile weapons (tomes, magic swords) and on the target otherwise, aimed at the target. The effect's own markers carry it across: code 0x11 jumps to the target, codes 0x12 to 0x13 move it there over the frames between them (Wind: frames 44–45). The blow lands on the effect's marker 0 (Wind: frame 90), and a miss on its marker 1, so a spell's timing comes from its effect, not the caster. Each tome has two cameras in `xcam/magic/cam.cmp`, named after the item: `<NAME>_at0` (`WIND_at0`) starts as the spell leaves the caster, and `<NAME>_at1` cuts to the target as the blow lands, filming it take the hit. A miss stays on `_at0`. Magic swords play `mag_impact_l` instead. The disc's `xcam/magic/magic.cmp` holds older variants (`_cr0`, `_sk0`…) that the game never loads.

  Effect materials rest fully transparent; the effect's animation fades each one in and out with one alpha track per material (see [.g / .gs / .ga](../formats/model-formats.md)).

  <span class="confidence confidence--open">Open</span> Which unit the opening camera turns to after its zoom, and the exact pushback distances on damage and dodges, are not decoded.
