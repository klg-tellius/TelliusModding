---
id: "cp-data-format"
title: "cp_data.bin"
description: "The computer player's data: AI scripts, movement-scoring weights, heal thresholds, waypoint and target tables"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Combat","Editable"]
aliases: ["tellius_archive.html#/cp-data-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/cp-data-format.md"
---
# cp_data.bin

*The computer player's data: AI scripts, movement-scoring weights, heal thresholds, waypoint and target tables*

`cp_data.bin` is the data of the enemy and NPC AI (&ldquo;CP&rdquo; is *computer player*, not support points). It uses the [Labeled Section Format](./labeled-section.md): every section name is registered in the engine's name hash table at load, so a unit's [dispo record](./dispo-format.md) (`seq_attack`, `seq_move`, `seq_heal`, `mtype`) and the `UnitSetCp*` script calls find their section by name. <span class="confidence confidence--confirmed">confirmed</span>

## Sections

<div class="table-wrap">
<table><thead><tr><th>Sections</th><th>Count</th><th>Holds</th></tr></thead><tbody>
    <tr><td><code>CP_DataHead</code></td><td>1</td><td>Build timestamp and author, then pointers to the defaults (<code>TBL_STEALITEMS</code>, <code>MTYPE_NORMAL</code>, <code>SEQ_NOATTACK</code>, <code>SEQ_NOMOVE</code>, <code>SEQ_NOHEAL</code>, <code>ATK_SEQID_LIST</code>)</td></tr>
    <tr><td><code>TBL_STEALITEMS</code></td><td>1</td><td>67 <code>IID_</code> names an AI thief may steal (skill scrolls, rings, drops, keys, healing items)</td></tr>
    <tr><td><code>TBL_PID_*</code></td><td>14</td><td>Character lists used as target filters by AI scripts</td></tr>
    <tr><td><code>TBL_MAP*_ROUTE*</code></td><td>10</td><td>Waypoints, one word <code>(x &lt;&lt; 16) | y</code> each, ended by <code>0xFFFF0000</code></td></tr>
    <tr><td><code>MTYPE_*</code></td><td>32</td><td>24-byte movement-scoring weight tables</td></tr>
    <tr><td><code>SEQ_*</code> scripts</td><td>69</td><td>AI scripts: 31 attack, 38 move</td></tr>
    <tr><td><code>SEQ_*HEAL*</code></td><td>6</td><td>8-byte heal behaviours</td></tr>
    <tr><td><code>*_SEQID_LIST</code>, <code>MTYPE_TABLEID_LIST</code></td><td>4</td><td>Name lists; a record's position is its id in the save file</td></tr>
  </tbody></table>
</div>

## AI scripts

  A script is an array of 28-byte entries of seven words: an opcode and six fields `a`&ndash;`f`. The first two entries are a header carrying the script's own name and its id. Each unit keeps one program counter per script kind (one byte each, saved in the save file), so a script resumes on the next turn where its last `END` sent it. The engine runs the entry the counter points at by looking its opcode up in a 52-entry handler table (`0x80273000` US, `0x8027C2C0` PAL, `0x8026CAF0` JP, the same opcodes in all three). <span class="confidence confidence--confirmed">confirmed</span>

  Before the handler runs, a non-zero `b` word is copied into the *threat limit*: the move checks then only stop on tiles whose *threat* (the summed expected damage of every hostile unit that can strike the tile, described under *The threat map* below) is at most that value; `0xFFFF` means no limit. Handlers advance the counter by one; jumps move it to the first label entry (opcode 0) whose `c` is the wanted label, label 0 meaning the first entry. The label search does not stop at the end of the script: it reads on into the sections that follow. <span class="confidence confidence--confirmed">confirmed</span>

### A unit's turn

  The AI runs a fixed list of steps for each unit: retreat and heal (driven by the heal record), the **attack script**, then the **move script**, stopping at the first step that found an action. A script step calls entries until one ends the run (`END`, or a `SET_SCRIPTS` that replaces the running script); after 256 entries without that, a built-in script runs instead (attack with 100% chance, or move toward the nearest foe). Action entries register a candidate action and set a *found* flag; a later action entry replaces the candidate, so vanilla scripts follow every action with a jump to label 99 when one was found. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Opcode</th><th>Name</th><th>Effect</th></tr></thead><tbody>
    <tr><td class="num">0</td><td>LABEL</td><td>Jump target <code>c</code></td></tr>
    <tr><td class="num">1</td><td>COMPARE</td><td>If register <code>a</code> compared with <code>c</code> by <code>b</code> (0 <code>&gt;</code>, 1 <code>&gt;=</code>, 2 <code>==</code>, 3 <code>&lt;=</code>, 4 <code>&lt;</code>, 5 <code>!=</code>) holds, jump to label <code>d</code></td></tr>
    <tr><td class="num">2</td><td>CALL</td><td>Call the function registered under the name <code>e</code> (unused)</td></tr>
    <tr><td class="num">3</td><td>SET_SCRIPTS</td><td>Give the unit attack script <code>e</code> and/or move script <code>f</code></td></tr>
    <tr><td class="num">4 / 6 / 7</td><td>GOTO / JUMP_IF_FOUND / CLEAR_FOUND</td><td>Jump to <code>d</code>; jump when an action was found (or, <code>a</code> = 0, when none was); forget the found action</td></tr>
    <tr><td class="num">5</td><td>EVENT_ACTION</td><td>Turn the pending move into the action of an event on the destination tile (unused)</td></tr>
    <tr><td class="num">100&amp;ndash;104</td><td>ATTACK family</td><td>Weapon attack (action 15) on the named character (100), on any target (101), without moving (103), on a class (104)</td></tr>
    <tr><td class="num">105 / 106</td><td>USE_STAFF</td><td>Use a staff: heal, Restore, Silence, Sleep, Berserk, Warp, Rescue or Ward (+ without moving)</td></tr>
    <tr><td class="num">107 / 108</td><td>STEAL</td><td>Steal an item listed in <code>TBL_STEALITEMS</code> (needs <code>SID_STEAL</code>; + without moving)</td></tr>
    <tr><td class="num">110 / 111</td><td>USE_SKILL</td><td>Use skill <code>f</code>: Gamble (attack, action 21), Fairness, Flutter, Tackle, Tackle 2, Snarl, Earth / Sky Blessing</td></tr>
    <tr><td class="num">112</td><td>SHOOT</td><td>Fire a ballista (actions 49 / 42)</td></tr>
    <tr><td class="num">113 / 114</td><td>ROCK_ATTACK</td><td>Use a map object of kind 10, the rocks (action 46); 114 without a roll, from a tile list <span class="badge strong">strong evidence</span></td></tr>
    <tr><td class="num">115</td><td>TACKLE</td><td>Shove (action 19) an adjacent unit</td></tr>
    <tr><td class="num">116</td><td>ATTACK_DIRECT</td><td>Weapon attack with a simpler choice of tile <span class="badge strong">strong evidence</span></td></tr>
    <tr><td class="num">200&amp;ndash;218</td><td>Movement</td><td>Move to a tile (200), toward a character to talk (201, 215), toward a class (203), destroy a village (204), safest tile (205), toward the nearest target (206, 207, 217), to an event (209), random tile (210), escape (211), to the nearest breakable terrain and attack it (212), along a waypoint route (216), talk in place (218)</td></tr>
    <tr><td class="num">500 / 501 / 600</td><td>Registers</td><td>Count the targets within a multiple of the unit's Mov (16.16 factor in <code>b</code>); test skill #9; change the Mov bonus and read Mov</td></tr>
    <tr><td class="num">502</td><td>USE_ITEM</td><td>Use the item <code>e</code> (action 4)</td></tr>
    <tr><td class="num">1000 / 1001</td><td>STOP / END</td><td>End the run; the next run starts at label <code>d</code> (identical code)</td></tr>
    <tr><td class="num">102, 109, 202, 208, 213, 214</td><td>NOP</td><td>Nothing</td></tr>
  </tbody></table>
</div>

  The action opcodes share their fields: `a` is a percent chance (the handler acts when a roll of 0&ndash;99 is at most `a`), `e` an optional `TBL_PID_*` character list and `d` its mode. With no list they target every hostile unit; with a list they target its characters whatever their side, or, with `d` set, every hostile unit not in it (`SEQ_ALLATK100_NOLAGU`). Movement and talk opcodes leave a result code in register 0: 1 not on the map, 2 next to the target, 3 talk queued, 8 arrived, 9 nothing found, 10 try limit reached, 11 has the skill. <span class="confidence confidence--confirmed">confirmed</span>

### Example

  The app shows every entry as one line of readable code. `SEQ_ATTACK1.5RANGEMOVE`, the move script of units that wait until a foe comes within one and a half times their move range, reads:

```text
r0 = count_units(range=1.5, weapon_range=True)
if r0 > 0: goto L1
nop202()
stop()
L1:
set_scripts(move=SEQ_NEARESTUNITMOVE)
stop(resume=L1)
```

  `SEQ_USECHANGE_ATRANGE` has no `END`, and the labels it jumps to are not in it: the label search finds them in `SEQ_USECHANGE_1.5ATRANGE`, the next section in the file, whose code it then runs. <span class="confidence confidence--confirmed">confirmed</span>

## Movement types: the attack score

  When an attack entry looks for a target, the game scores every pairing of a foe and a tile the unit could attack it from, and the pairing with the highest score wins. The unit's `MTYPE_*` table supplies the weight of each term. A table is 24 bytes: a name pointer, its id (its position in `MTYPE_TABLEID_LIST`) at `+4`, then signed weight bytes. <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table><thead><tr><th>Byte</th><th>Weight of</th><th>Term value</th><th class="num"><code>MTYPE_NORMAL</code></th></tr></thead><tbody>
    <tr><td><code>+5</code></td><td>Damage dealt</td><td>The attacker's expected damage (below), with the kill bonus</td><td class="num">64</td></tr>
    <tr><td><code>+6</code></td><td>Foe already wounded</td><td><code>10 &amp;times; (max HP &amp;minus; HP) &amp;divide; max HP</code> of the foe before the attack, 0&amp;ndash;10</td><td class="num">16</td></tr>
    <tr><td><code>+7</code></td><td>Company</td><td>Units around the attack tile that are <em>not hostile</em> to the attacker (its own side, or two non-enemy armies), each worth 3 next to the tile and less up to 3 tiles away, from a fixed 24-tile diamond</td><td class="num">32</td></tr>
    <tr><td><code>+8</code></td><td>Class bonus</td><td>Sum of the bytes <code>+0xE</code>&amp;ndash;<code>+0x17</code> for each category the foe's class has</td><td class="num">32</td></tr>
    <tr><td><code>+9</code></td><td>Turn</td><td>The turn number</td><td class="num">32</td></tr>
    <tr><td><code>+0xA</code></td><td>Skill</td><td>+50 when the foe has Provoke, &amp;minus;50 when it has Shade (Shade wins when it has both), else 0</td><td class="num">32</td></tr>
    <tr><td><code>+0xB</code></td><td>Damage taken</td><td>The foe's expected counter (below), with the death penalty; subtracted</td><td class="num">32</td></tr>
    <tr><td><code>+0xC</code></td><td>Threat</td><td>The threat map at the attack tile divided by 16 (below); subtracted</td><td class="num">32</td></tr>
    <tr><td><code>+0xD</code></td><td>Own wounds</td><td><code>10 &amp;times; (max HP &amp;minus; HP) &amp;divide; max HP</code> of the attacker; subtracted</td><td class="num">16</td></tr>
    <tr><td><code>+0xE</code>&amp;ndash;<code>+0x16</code>, <code>+0x17</code></td><td>Class categories</td><td>Bonus values, not weights: one per bit of the foe's class category mask, bits 0&amp;ndash;8 then 10: <code>mage</code>, <code>fly</code>, <code>knight</code>, <code>armor</code>, laguz (<code>alize</code>), <code>human</code>, <code>beast</code>, <code>dragon</code>, <code>bird</code>, <code>hero</code></td><td class="num">mage 5, hero 10</td></tr>
  </tbody></table>
</div>

  Each term is turned into points the same way, `points = (int)(value &times; weight &divide; 32)`: weights are in 32nds, so 32 counts a term once, 64 doubles it and a negative weight reverses it. Then

```text
score = dealt + wounded + company + class + turn + skill
        &minus; taken &minus; threat &minus; own wounds
```

  The "killer" tables weight their namesake category (`MTYPE_ARMORKILLER` armor, `MTYPE_MAGEKILLER` mage, `MTYPE_ANIMALKILLER` laguz…) and `MTYPE_ARCHER` gives fliers 40. Because each term is truncated to a whole number, a small value with a small weight adds nothing: a foe at 15/20 HP is 2 wounded, worth `int(2 &times; 16 &divide; 32)` = 1 point.

### Expected damage

  Both damage terms start from the battle forecast between the two units at that tile: the damage of one hit (attack minus defence, at least 0) and the hit rate *p* as a fraction from 0 to 1. The attacker's side uses the exponent 1.75, the counter 2.125, so the AI rates uncertain hits lower than their average and its own risk lower still:

```text
single attack:  E = damage &times; p^k
double attack:  E = 2 &times; damage &times; (1 &minus; (1 &minus; p)&sup2;)^k      (attack speed &ge; the other's + 4, or weapon flag 0x20)
k = 1.75 for the attacker, 2.125 for the counter; E is truncated to a whole number
```

  **Damage dealt** is `v = int(E &times; weight &divide; 32)`. If `v` is below 1 (the attack is expected to do nothing), it becomes minus the foe's expected counter, at most 15, after adding 50 to that counter when it would kill the attacker. Then, if the foe's current HP is at most `v`, 50 more points are added: the *kill bonus*. The weighted value is what is compared, so with the usual weight 64 the bonus already fires when twice the expected damage reaches the foe's HP.

  **Damage taken** is the mirror image: the foe's expected counter, 0 when the attack tile is outside its weapon's range, weighted. If that is below 1, it becomes minus the attacker's expected damage (at most 15, +50 first when it would kill the foe), so an attack without risk *gains* up to 15 points. Then 50 is added when the attacker's current HP is at most the value: an expected death costs 50 points. The term is subtracted. <span class="confidence confidence--confirmed">engine</span>

### Example

  An enemy Fighter (30/30 HP) under `MTYPE_NORMAL` on turn 2 considers a Mage at 10/20 HP from a tile next to one other enemy. Its axe would hit for 8 at 80%; the Mage's tome would answer for 4 at 50%, and three player units could each strike that tile for 18, 12 and 10 expected damage.

<div class="table-wrap">
<table class="tight"><thead><tr><th>Term</th><th>Value</th><th class="num">Points</th></tr></thead><tbody>
    <tr><td>Dealt</td><td>E = int(8 &amp;times; 0.8^1.75) = 5; int(5 &amp;times; 64 &amp;divide; 32) = 10; the Mage has 10 HP, so +50</td><td class="num">60</td></tr>
    <tr><td>Wounded</td><td>10 &amp;times; 10 &amp;divide; 20 = 5; int(5 &amp;times; 16 &amp;divide; 32)</td><td class="num">2</td></tr>
    <tr><td>Company</td><td>One enemy next to the tile: 3</td><td class="num">3</td></tr>
    <tr><td>Class</td><td>The Mage has the <code>mage</code> category: 5</td><td class="num">5</td></tr>
    <tr><td>Turn</td><td>2</td><td class="num">2</td></tr>
    <tr><td>Taken</td><td>E = int(4 &amp;times; 0.5^2.125) = 0, below 1, so minus the Fighter's 5: &amp;minus;5, subtracted</td><td class="num">+5</td></tr>
    <tr><td>Threat</td><td>18 + 12 + 10 = 40; 40 &amp;divide; 16 = 2, subtracted</td><td class="num">&amp;minus;2</td></tr>
    <tr><td>Own wounds</td><td>Full HP</td><td class="num">0</td></tr>
    <tr><td colspan="2"><strong>Score</strong></td><td class="num"><strong>75</strong></td></tr>
  </tbody></table>
</div>

  The kill bonus is most of the score, so the Fighter will prefer any foe it can expect to finish. The same Mage with Shade would score 25 instead, and with Provoke 125.

### The threat map

  Just before each AI unit decides, the game builds a *threat map* for that unit: one value per tile, the summed expected damage that the unit would take there from every hostile unit. <span class="confidence confidence--confirmed">engine</span>

1. Every hostile unit on the map is listed, except units that are carried, dead, in the reserve, under a roof or marked as having acted (status bits `0x9D`), with two weapons from its first four items: its best close weapon (maximum range 1, highest might) and its best ranged one (the longest reach, then the highest might).
2. A weapon is kept only if the hostile could plausibly reach the deciding unit: their distance in tiles is at most the sum of both units' Mov plus the weapon's maximum range.
3. Its value is the hostile's forecast against the deciding unit where that unit stands now: `damage &times; hit%` &divide; 100, or `2 &times; damage &times; (1 &minus; (1 &minus; p)&sup2;)` when it doubles, truncated and capped at 255. A weapon worth 0 is dropped. Unlike the attack score, the hit chance is not raised to a power here.
4. The hostile's own movement range is searched. Every tile within the weapon's range of a tile it can stop on (an unoccupied tile, or its own, that is not an object tile) is a tile it can strike.
5. On each tile the deciding unit itself can move to and that the hostile can strike, the larger of the hostile's two weapon values is added to the map. Each tile is capped at 255.

  During an allied phase, tiles of terrain types 38 (Objective), 39 (Target), 40 (Sanctuary) and 42 (Visit) are left out. The attack score reads the map divided by 16, so threats under 16 cost nothing and a full 255 costs 15 points at weight 32. The move entries read the raw value: they stop only where it is at most the script's threat limit, and "move to the safest tile" picks the tile with the lowest value. <span class="confidence confidence--confirmed">engine</span>

  A second map, built once per phase from each hostile's weapon might plus Strength (Magic for magic weapons) without the reach test, is overwritten by the per-unit map before any script runs.

## Heal records and the heal step

  A heal record holds three bytes after its name and id: `retreat_below`, `resume_at` and `priority`. The game turns them into a per-unit *needs healing* flag (unit `+0x254` bit 0). <span class="confidence confidence--confirmed">engine</span>

- HP% is computed as `(int)(100 &times; HP &divide; max HP)`.
- When the flag is clear, it is set as soon as HP% is under `retreat_below`. When it is set, it is cleared once HP% reaches `resume_at`. A unit at 75% with `SEQ_NORMALHEAL` (30 / 80) is therefore still flagged if it fell under 30% earlier and has not recovered to 80%.
- The flag is refreshed for every unit at the start of each phase, for the acting unit and its target after every action, and by the heal step.
- Healing staves only ever target flagged units. A unit whose record never flags it (`SEQ_NOHEAL`, 0 / 0) is never healed by an AI staff user.

  The **heal step** runs before the attack script, and only for a flagged unit whose record has a non-zero `priority` (every vanilla record except `SEQ_BEARHEAL_NOACT`). It stops at the first option that works: <span class="confidence confidence--confirmed">engine</span>

1. **Its own healing item.** Among its Vulneraries (10 HP) and Elixirs (full HP), the unit takes the one whose heal is closest to the HP it is missing; on a tie, the smaller. Between two equal items it keeps the one with fewer uses. It walks to the reachable tile with the lowest threat and uses the item there.
2. **An ally's healing item.** If it has a free item slot, it takes the best healing item (same rule) from a unit of its own side next to a tile it can reach, then uses it.
3. **A refuge.** If it is not escaping, it looks for, in order:

      A candidate replaces the best one only when it has *both* no more hostile units within 3 tiles *and* a strictly lower path cost. The unit then walks toward it as far as it can.
  - an empty healing tile it can reach this turn (a fort, a throne, any terrain with a heal value);
  - anywhere on the map, a healing tile that is empty or held by its own side, or the tile of an ally that carries a usable healing staff;
  - an ally that holds a Vulnerary or Elixir.

  After such a move, from the tile it reached, the unit tries Chant, then Steal, then a weapon attack on a hostile in range.

## Staves

  An AI unit walks its four weapon slots in order. <span class="confidence confidence--confirmed">engine</span>

- A **healing staff** (Heal, Mend, Recover, Physic, Fortify) is tried when its rank is at least that of the last healing staff that found a target.
- **Any other staff** is tried only while no healing staff has found a target, and when its rank is at least that of the last other staff that did.
- Each staff that finds a use replaces the previous one, so the last one in this order wins.
- A silenced unit uses no staff.

  Torch, Hammerne and Unlock have no AI routine, so the AI never uses them. Each other staff has its own rule:

<div class="table-wrap">
<table class="tight"><thead><tr><th>Staff</th><th>Target</th><th>Where the caster stands</th></tr></thead><tbody>
    <tr><td>Heal, Mend, Recover</td><td>A unit of its own side (not itself) that needs healing, with the lowest HP%</td><td>Next to the target</td></tr>
    <tr><td>Physic, Rescue</td><td>The same</td><td>Any tile within the staff's range</td></tr>
    <tr><td>Fortify</td><td>Used only when at least 3 units of its own side need healing anywhere on the map</td><td>The reachable tile with the most of them in range (1 to Mag/2 tiles); on a tie, the better-scored tile</td></tr>
    <tr><td>Restore</td><td>A unit of its own side with a status, the highest effective level (level + 20 when promoted)</td><td>Next to the target</td></tr>
    <tr><td>Ward</td><td>A unit of its own side with the lowest Resistance</td><td>Next to the target</td></tr>
    <tr><td>Silence</td><td>A foe that is not silenced, holds a usable tome or staff, and can be hit (hit chance above 4); the highest hit + Magic</td><td>Any tile within range</td></tr>
    <tr><td>Sleep, Berserk</td><td>A foe with no status that holds a usable weapon, hit chance above 4; the highest hit + effective level</td><td>Any tile within range</td></tr>
    <tr><td>Warp</td><td>A unit of its own side that has not acted, doesn't need healing and isn't escaping, with the highest effective level</td><td>Next to the target</td></tr>
  </tbody></table>
</div>

- **Hit chance of a status staff:** `(Mag &minus; Res) &times; 5 + Skl + 30 &minus; 2 &times; distance`, clamped to 0&ndash;100. When choosing, the AI measures the distance from where the caster stands before it moves.
- **Mag/2 range:** a staff or tome whose maximum range is stored as 255 reaches Mag &divide; 2 tiles, but never fewer than 5 or more than 15. Warp's range is the same.
- **Warp destination:**
  1. The game takes the last unit of the acting side that stands in danger. Danger here means the per-phase map of the target's foes: each foe's might + Strength, or + Magic for magic.
  2. It finds that unit's nearest foe by path.
  3. Among the empty tiles the warped unit could reach from that foe's tile and that are within the Warp range of the warped unit, it sends the unit to the one with the lowest danger.

  **Choosing among equals.** Targets are examined row by row, top to bottom and left to right, in a box of Mov + the staff's range around the caster. When two targets are equally good, the one examined *last* wins. <span class="confidence confidence--confirmed">engine</span>

  **Tile score.** A tile is scored as the sum of three parts. <span class="confidence confidence--confirmed">engine</span>

1. The terrain's avoid, defence, resistance and heal values added up and halved. Flying units use the terrain's flier values.
2. Plus the weights of the 24 tiles within 3 steps (the attack score's table): plus the weight for each unit of the caster's side standing there, the caster itself included, and minus it for each hostile unit.
3. Minus the tile's threat &divide; 16.

  The caster stands on the best-scored tile; on a tie, the first one examined wins. Next to a target, it tries right, left, below, then above.

## Steal

  A unit with `SID_STEAL` considers every unit next to a tile it can reach (through the map's links) that it is **strictly faster** than. <span class="confidence confidence--confirmed">engine</span>

1. For each such unit, it walks the inventory in slot order (weapons first, then items) and picks the *first* item that `TBL_STEALITEMS` lists and that it can carry: the item's weight must be below its Strength, and it needs a free slot of that kind.
2. That item's position in `TBL_STEALITEMS` is its priority. The lowest wins, so the list's order is the thieves' order of preference: Member Card and Silver Card first, then skill scrolls, gems, rings, stat drops, keys and healing items.
3. On a tie, the first unit found wins.
4. The thief steals from the best-scored tile next to the target.

  The thief only ever looks at the first stealable item of each unit. A unit carrying a Vulnerary in an earlier slot and a Member Card in a later one counts as a Vulnerary. <span class="confidence confidence--confirmed">engine</span>

## Items and skills

  `use_item(iid)` uses the named item when the unit holds it and the item is usable now. <span class="confidence confidence--confirmed">engine</span>

- If the script has already registered a move, the unit uses the item where that move ends.
- Otherwise it uses the item where it stands.
- When the item is missing or unusable, the entry clears the found flag, which cancels an action registered earlier.

  `use_skill` acts only for skills that have an AI routine:

- Gamble: a normal weapon attack, flagged as a Gamble.
- Flutter: an action aimed at an ally.
- Fairness, Tackle, Snarl and the two Blessings: the AI never uses them.

  Open: how many turns Sleep, Silence and Berserk last. The per-item "usable now" checks are also not documented here. <span class="confidence confidence--open">open</span>

  Open: the order among pairings with exactly equal scores, and which entries use the two simpler variants of the scorer (one of them leaves out damage taken and threat), are not documented here. <span class="confidence confidence--open">open</span>

!!! info "Editing"
    The app's *Game Data &rsaquo; AI (CP)* tab edits scripts (as readable code or as raw entries), heal records, movement weights, the steal list and the routes. New scripts are appended to their id list so existing ids never move; the build copies the file into `system.cmp`.

  The Japanese, European and US releases ship the same `cp_data.bin`, byte for byte.
