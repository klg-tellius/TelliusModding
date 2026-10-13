---
id: "map-actions"
title: "Map Actions"
description: "The player's command menu, the enemy AI's action checkers, and the action ids both hand to one executor"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure","Combat"]
aliases: ["tellius_archive.html#/map-actions"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/map-actions.md"
---
# Map Actions

*The player's command menu, the enemy AI's action checkers, and the action ids both hand to one executor*

A map action is identified by a small number, the *action id*. Two different front ends produce it. The player's command menu is a list of menu entries, one class per command; the enemy and NPC AI uses separate checker functions. Both store the chosen id, its target and its tile in the same pending-action slots, and one executor then runs it. <span class="confidence confidence--confirmed">confirmed</span>

## The player's command menu

  Each command (Attack, Staff, Rescue&hellip;) is a small class with four methods: its label (an `MMM_` message key), its help text (an `MH_` key), an availability test and an execute method. When the menu opens, every entry's availability test decides whether it is shown; choosing it stores its action id. The full list:

<div class="table-wrap">
<table><thead><tr><th>Command</th><th>Label key</th><th>Action id</th><th>Notes</th></tr></thead><tbody>
    <tr><td>Wait</td><td><code>MMM_TAIKI</code></td><td class="num">1</td><td>always available</td></tr>
    <tr><td>Items</td><td><code>MMM_ITEM</code></td><td class="num">2</td><td>opens the item sub-menu (Use, Equip, Unequip, Trade, Drop)</td></tr>
    <tr><td>Use (item)</td><td><code>MMM_IUSE</code></td><td class="num">4</td><td></td></tr>
    <tr><td>Trade</td><td><code>MMM_ITRADE</code></td><td class="num">6</td><td><code>0x28</code> when chosen from the item sub-menu</td></tr>
    <tr><td>Talk</td><td><code>MMM_TALK</code></td><td class="num">7</td><td></td></tr>
    <tr><td>Visit</td><td><code>MMM_VISIT</code></td><td class="num">9</td><td></td></tr>
    <tr><td>Door / Chest</td><td><code>MMM_DOOR</code> / <code>MMM_TBOX</code></td><td class="num">11 / 12</td><td>one shared class with two labels</td></tr>
    <tr><td>Seize</td><td><code>MMM_CONQ</code></td><td class="num">13</td><td></td></tr>
    <tr><td>Escape</td><td><code>MMM_ESC</code></td><td class="num">14</td><td></td></tr>
    <tr><td>Attack</td><td><code>MMM_ATTACK</code></td><td class="num">15</td><td></td></tr>
    <tr><td>Staff</td><td><code>MMM_ROD</code></td><td class="num">16</td><td></td></tr>
    <tr><td>Steal</td><td><code>MMM_STEAL</code></td><td class="num">17</td><td></td></tr>
    <tr><td>Chant</td><td><code>MMM_CHANT</code></td><td class="num">18 / 43</td><td></td></tr>
    <tr><td>Shove / Smite</td><td><code>MMM_TACKLE1</code> / <code>MMM_TACKLE2</code></td><td class="num">19 / 20</td><td>push an adjacent unit 1 or 2 tiles</td></tr>
    <tr><td>Gamble</td><td><code>MMM_GAMBLE</code></td><td class="num">21</td><td></td></tr>
    <tr><td>Rescue</td><td><code>MMM_RESCUE</code> (<code>MMM_RESCUEP</code> "Savior")</td><td class="num">25</td><td></td></tr>
    <tr><td>Drop</td><td><code>MMM_DROPOFF</code></td><td class="num">26</td><td></td></tr>
    <tr><td>Give / Take</td><td><code>MMM_CSEND</code> / <code>MMM_CRECV</code></td><td class="num">27 / 28</td><td>the transfer happens in the menu; the executor does nothing</td></tr>
    <tr><td>Vortex</td><td><code>MMM_FLUTTER</code></td><td class="num">29</td><td>an attack with the Vortex as weapon</td></tr>
    <tr><td>Roar</td><td><code>M咆哮</code></td><td class="num">30</td><td>"Paralyze an enemy unit", once per map</td></tr>
    <tr><td>Reinforce</td><td><code>MMM_ZOEN</code></td><td class="num">32</td><td>deploys a named reinforcement group</td></tr>
    <tr><td>Sky Boon</td><td><code>M天</code></td><td class="num">33</td><td>the Heal effect over a range (Blessing skill)</td></tr>
    <tr><td>Earth Bounty</td><td><code>M地</code></td><td class="num">34</td><td>the Restore effect with an earth-blast animation (Boon skill)</td></tr>
    <tr><td>Break</td><td><code>MMM_DBR</code></td><td class="num">39</td><td>attack breakable terrain</td></tr>
    <tr><td>Arrive</td><td><code>MMM_ARR</code></td><td class="num">41</td><td></td></tr>
    <tr><td>Ballista</td><td><code>MMM_SH</code></td><td class="num">42 / 49</td><td>two siege-weapon variants</td></tr>
    <tr><td>Order / Direct</td><td><code>MMM_ORDER</code> / <code>MMM_DEMAND</code></td><td class="num">50 / 51</td><td>army orders (follow, safety, move&amp;hellip;)</td></tr>
  </tbody></table>
</div>

  A further label, `M落石` ("Push"), sits among these keys; which command class uses it is not traced. <span class="confidence confidence--open">open</span>

## Rules the executor applies

- **Shove and Smite** push the target 1 or 2 tiles away. A target with a specific defensive trait rolls its Strength as a percentage to resist, and fliers are not pushed. A unit pushed onto a pit falls.
- **Drop** next to an enemy hidden in fog becomes an ambush: the "!" encounter mark and sound play instead.
- **Door and Chest** use the chosen key item; a thief opening a lock without one runs the Chest Key's effect.
- **Break** runs a combat preview against the breakable terrain's own HP.

## The AI's checkers

  Enemy and NPC units don't use the menu. About forty checker functions each answer "can this unit do X here", and every one that succeeds calls the same small register function, which stores the action id, its target and tile and sets an "action found" flag. The [AI scripts](../formats/cp-data-format.md) call these checkers. Notable ones:

<div class="table-wrap">
<table><thead><tr><th>Checker</th><th>What it does</th></tr></thead><tbody>
    <tr><td>Chant</td><td>Pairs each Chant variant the unit knows with its own validator, scores nearby allies and registers the best one.</td></tr>
    <tr><td>Steal</td><td>Scans nearby enemy inventories against the AI's steal list.</td></tr>
    <tr><td>Unlock (thieves)</td><td>Walks to the nearest door or chest, or opens one next to it (actions 11 / 12).</td></tr>
    <tr><td>Door Key / Chest Key</td><td>Only for units deployed with the matching <a class="wl" href="../../formats/dispo-format/">deployment flag</a> (<code>0x10</code> doors, <code>0x20</code> chests).</td></tr>
    <tr><td>Holy Water / Torch</td><td>Always answer no: the AI never uses these items.</td></tr>
    <tr><td>Wait</td><td>Registers the unit's own tile.</td></tr>
  </tbody></table>
</div>

  Which units count as allies or enemies for these checks is decided by the army-relation system — see [Armies & Allegiance](./armies-allegiance.md).
