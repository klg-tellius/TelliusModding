---
id: "zdbx"
title: "ZDBX & DBX"
description: "The battle engine's text tables: which model each unit uses, and how it animates and moves"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Container","Battle Graphics"]
aliases: ["tellius_archive.html#/zdbx"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/zdbx.md"
---
# ZDBX & DBX

*The battle engine's text tables: which model each unit uses, and how it animates and moves*

`zdbx.cmp` is [LZ10-compressed](./lz10.md) and expands to a [pack archive](./pack-archive.md) containing 449 mostly Shift-JIS text files. A DBX document uses braces, `#` comments, and whitespace-separated names and values. It is readable configuration rather than compiled fixed-record data.

<div class="table-wrap">
<table><thead><tr><th>Folder</th><th>Entries</th><th>Purpose</th></tr></thead><tbody>
    <tr><td><code>zu/</code></td><td>184</td><td>Two tables per battle-model code of <code>files/zu/</code>: the model table and the parameter table (see below)</td></tr>
    <tr><td><code>xwp/</code></td><td>91</td><td>One table per weapon, named by its item ID without <code>IID_</code>: the model the battle loads (<code>Model</code> block: folder and model name), its kind and whether it flies as a missile (see <a class="wl" href="../../systems/items-weapons/">Items &amp; Weapons</a>)</td></tr>
    <tr><td><code>zbg/</code></td><td>117</td><td>One <code>param.dbx</code> per battle scenery: indoor flag, footstep effect and sound (see below)</td></tr>
    <tr><td><code>xcam/</code></td><td>19</td><td>Camera scripts for attack, critical, impact, death, level-up, and class-change beats: keyframes that move one of the camera rigs of <code>camera.dbx</code> (see below)</td></tr>
    <tr><td><code>zdbx/</code></td><td>11</td><td>Master class, model, weapon, skill, effect, scenery, camera, and engine tables</td></tr>
    <tr><td><code>ztool/</code>, <code>ztex/</code></td><td>27</td><td>Window layouts of the in-game battle tool, and 2D textures: the battle screen's windows and digits (see below) and the tool's widgets</td></tr>
  </tbody></table>
</div>

## How DBX participates in battle presentation

  The battle engine (named “kiribato” in the files' own comments) opens `zdbx.cmp` when a battle starts and reads its tables by name. Global tables select class, weapon, effect, scenery, and camera resources; per-asset files then tune how those resources attach and play. DBX is configuration, not the model geometry or animation curves themselves.

## How a combatant's battle model is chosen

1. **`zdbx/jobList.dbx`** gives the model code. The engine tries the unit's animation ID (`AID_MAGE_TO mgm2`, Tormod's), then its class plus character (`JID_ARCHER PID_LOFA=arc2`, Rolf's; the code is cut to four characters), then its class alone (`JID_FIGHTER fig1`). <span class="confidence confidence--confirmed">engine + in game</span>
2. **`zu/<code>.dbx`** (the model table) names the model inside the packs and, for every weapon and action, the animation to play (`ax_攻撃1 fig1_at1_ax`: the first axe attack).
3. The packs are `zu/<code>/<code>_<weapon>.pak` (a `.cmp` of the same name would be tried first).
4. **`zu/<code>_prm.dbx`** (the parameter table) starts with `texnum` and that many texture lines. The texture is picked by the unit's animation ID, then its character, then its army (`自軍` player, `敵軍` enemy, `中立` other, `味方` ally), falling back to the model code; the file is `zu/<code>/<name>.tpl`. Tuning keys follow: move speed (`移動速度`), range (`間合い`), five jump variants of the attacks, flying type (`飛行系`), flying away after the finishing blow, run count (`走り回数`), knockback on damage (`ダメージ後退`), three animation blend durations and a large-model flag (`大型`). <span class="confidence confidence--confirmed">engine</span>

  A new battle model can be added without replacing one: a copied model folder under a new code, its two tables, and one job-list line. In the Prologue, Boyd was given `zu/bol2` (a copy of `fig1` with a recoloured texture) through the line `JID_FIGHTER PID_BOLE_MAP1=bol2`; the game drew it in battle while every other fighter kept `fig1`. <span class="confidence confidence--confirmed">in game</span>

## Important master tables

- `jobList.dbx` maps each `JID_` class to its battle-model code and contains character- and animation-ID-specific overrides.
- `weaponList.dbx` lists weapons in item-table order.
- `skill.dbx` links Japanese skill names with effect triggers.
- `effectList.dbx` catalogs spell, skill, status, environmental, and UI effects.
- `camera.dbx` defines the default battle-camera rig.
- `bgList.dbx` maps battle-scenery identifiers to locations: the Prologue (`MAP01`) fights in front of `zbg/map01_woods`, a separate 3D scene rather than the map terrain. <span class="confidence confidence--confirmed">confirmed in game</span>
- `param.dbx` contains global battle timing, fade, and camera parameters.

## Weapon, scenery, camera and unit-parameter tables

  These tables are short and fully read; every field is listed. Their numeric codes are checked against the shipped files and the battle engine's consumers.

- **`xwp/<NAME>.dbx`** has a `Model` block (`name`, `folder`, `model`; tomes have none) and a `Weapon` block: `show` (always 1), `kind`, `missile`, optional `effectId` (an `EID_` effect played with the weapon) and `damageEffId` (an `EID_..._WP` effect on the target). `kind`: 0 sword, 1 lance, 2 axe, 3 bow, 4 tome (no model), 5 knife, 6 thrown spear, 7 thrown axe or sword, 8 wave blade (Rune and Sonic swords), 9 arrow, 10 beast claw, 11 dragon breath. `missile`: 0 melee, 1 flies as a projectile, 2 special wave.
- **`zbg/<scenery>/param.dbx`** has one `Param` block: `name`, `roomFlag` (1 for indoor sceneries), `footEffect` and `footSound` (0 none, 1 dirt, 2 water, 3 snow, 4 grass; the sound follows the same order). Ships, bridges and floors use 0; rivers, seas and swamps use 2; Daein's snowy sceneries use 3.
- **`zdbx/camera.dbx`** has one `Camera` block per rig: `cam0` (scene camera), `cam1` (free orbit camera), `camCharaL0` and `camCharaR0` (follow an actor: `entityClass Actor`, then `charaAtk`, `charaDef`, `charaSup` in the order to try), `camCharaL1` and `camCharaR1` (follow a weapon: `weapon0` to `weapon2`, with a `speed`). Fields are `pos`, `rot` (degrees), `dist`, `offs` (look-at offset), `dest`, `attract`, `eyeCenter` and `enable`. Vanilla has a typo on `cam1`: `rot -2.-2, 180.0, 0.0`.
- **`xcam/<name>.dbx`** is one `CameraAnime` block: `name`, `caption` (Japanese description), optional `folder`, `camera` (the rig it moves), `num`, then `num` keyframes each written as `pos`, `rot`, `dist`, `time`. `time` is the keyframe's duration in ticks, 60 per second (0 cuts straight to it); how scripts are chosen and played is in [Battle Staging & Camera](../systems/battle-staging.md).
- **`zu/<code>_prm.dbx`** tuning keys follow the texture lines: floats `移動速度` (move speed, 0.15 to 1.0 world units per tick), `間合い` (attack range, 10 to 22 world units), `ルートスケール` (root scale), `ダメージ後退` (knockback, 0.1 or 1.0); whole numbers `走り回数` (run count) and the blend durations `補間速度`, `待機補間速度`, `移動補間速度` (10 to 30 ticks); and flags that are either `1` or absent: `ジャンプ攻撃`, `ジャンプ攻撃２`, `ジャンプ必殺`, `ジャンプ止め`, `ジャンプ奥義` (jumping attack variants), `飛行系` (flying), `大型` (large), `止め飛び去り` (flies away on the finishing blow).

## The battle screen's layout

  `zdbx/battle.dbx` lays out everything drawn over a battle scene, as widget blocks: `Layer` (`Window`, `Caption`, the two name plates, `Exp`), `Texture` (a cell of an image in `ztex/`), `Picture`, `Caption` (text), `Number`, `Gauge` and `Rect`. Each block has a `name`, a `layer`, `show` and a `pos` on a 640×480 screen. The two HP windows come from `ztex/btlwin.tpl` (a 600×224 sheet of window frames and gauge bars). The bars are the gauges `GaugeL` and `GaugeR`, each paired with its HP number (`numName`), and HP digits come from `ztex/number.tpl`. The names and weapon names are captions the game fills in at the start of the fight. The left side is always the attacker and the right side the defender. <span class="confidence confidence--confirmed">engine</span>

  The layout still holds a stat panel from development: a `ParamWin` picture and six `Number` widgets, `NumAtkL/R`, `NumHitL/R` and `NumCritL/R`, between the two HP windows, all with `show 0`. The game still writes each fighter's attack, hit and critical rate into them at the start of every battle. They can't simply be switched on: their digit texture `num1` (10×20 cells at row 28 of `number.tpl`) is outside the shipped 200×32 image, which only has the large HP digits, and the region `ParamPlate` points at in `btlwin.tpl` now holds other window art. <span class="confidence confidence--confirmed">engine + files</span>

  FE7Dragon's Battle Info Display patch turns the panel back on, and the editor's Game Code tab includes it as **Battle info window**. Three changes make it work:
  - **Digits:** `number.tpl` grows to 200×50 with a second row of 15×21 digits at y=28, and `num1` takes that cell size.
  - **Box:** `ParamPlate` points at a 164×100 parchment at (0,0) of a new `ztex/3sukumi.tpl`. `ParamWin` shows at (221,344), bottom middle.
  - **Numbers:** the six widgets show inside the box with `kerning -4`.

  The values the game writes are not the ones the box labels. `battle_preview_setup_forecast_number_widgets` (US `0x800CF5B8`) fills the widgets, so the patch hooks it to write damage (Atk minus the other side's Def, never below 0), hit and crit, read from the battle context's two fighters. <span class="confidence confidence--confirmed">files + code; not yet seen in game</span>

  The 15 `ztool/` DBX files define thirteen tool windows plus a system desktop and a seven-object preview scene. Eleven windows have direct constructors in the US executable; `batWin.dbx` and `win4.dbx` have no literal filename there. The camera-editor window is constructed even on the normal battle path. These blocks use the same runtime class factory as the battle HUD: windows, buttons, lists, captions, combo boxes, a slider, cameras, a model and an actor. Caption `nega` selects the alternate text mode and an added black pass. A button stores its `current` bit, but focus is set separately and no direct reader of that bit was found. `zdbx/lensflare.dbx` supplies sixteen pictures and sixteen `lengthN` factors that place them along the projected source-to-center line; their colour comes from the light record and their alpha falls as `1 − distance²`. The engine samples EFB depth at the source pixel to choose one of two flare-layer offsets. <span class="confidence confidence--confirmed">files + engine</span>

  The archive, its catalog tables and all of the tables above are understood. Speed is in world units per tick, range in world units, and camera times and animation blend durations in ticks (see [Battle Staging & Camera](../systems/battle-staging.md)). The three blend keys choose the general, moving and standing transition lengths; a missing value uses `BlendTime` (15), `BlendTimeRun` (5) or `BlendTimeStand` (20) from `zdbx/param.dbx`. The main `ztool/` window callbacks are traced; complete screen-by-screen use of the `ztex/` images and a few visual edge cases remain open.
