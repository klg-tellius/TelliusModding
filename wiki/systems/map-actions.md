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
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/map-actions.md"
system_entries: ["FE9-SYS-069", "FE9-SYS-070", "FE9-SYS-071", "FE9-SYS-072", "FE9-SYS-073", "FE9-SYS-074", "FE9-SYS-075", "FE9-SYS-076", "FE9-SYS-087", "FE9-SYS-088", "FE9-SYS-089", "FE9-SYS-090", "FE9-SYS-091", "FE9-SYS-092", "FE9-SYS-093", "FE9-SYS-094", "FE9-SYS-095", "FE9-SYS-096", "FE9-SYS-097", "FE9-SYS-098", "FE9-SYS-099", "FE9-SYS-100", "FE9-SYS-101", "FE9-SYS-102"]
system_reviewed: ["FE9-SYS-070", "FE9-SYS-071", "FE9-SYS-072", "FE9-SYS-073", "FE9-SYS-074", "FE9-SYS-075", "FE9-SYS-076", "FE9-SYS-087", "FE9-SYS-088", "FE9-SYS-089", "FE9-SYS-090", "FE9-SYS-091", "FE9-SYS-092", "FE9-SYS-093", "FE9-SYS-094", "FE9-SYS-095", "FE9-SYS-096", "FE9-SYS-097", "FE9-SYS-098", "FE9-SYS-099", "FE9-SYS-100", "FE9-SYS-101", "FE9-SYS-102"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
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

  The `M落石` ("Push") label belongs to the rolling-rock map-object action. It targets object kind 10 and commits pending action `0x2E`; it is distinct from unit Shove and Smite.

## Rules the executor applies

- **Shove and Smite** push the target 1 or 2 tiles away. A target with a specific defensive trait rolls its Strength as a percentage to resist, and fliers are not pushed. A unit pushed onto a pit falls.
- **Drop** next to an enemy hidden in fog becomes an ambush: the "!" encounter mark and sound play instead.
- **Door and Chest** use the chosen key item; a thief opening a lock without one runs the Chest Key's effect.
- **Break** runs a combat preview against the breakable terrain's own HP.
- **Ballista** shots never open a battle scene. When the attacker's weapon carries the `sh` property (the ballistae and the Onager), the attack plays on the map instead: the shot flies to the target, which shows a miss, no damage, a hit, or a finishing hit with its sound and a camera shake. This is also why the ballistae have no 3D weapon model. <span class="confidence confidence--confirmed">engine</span>

## Mental model and action lifecycle

The useful mental model is **offer, commit, mutate, refresh, persist**. A command appears only after its menu or AI checker finds a qualifying actor and nearby object. Selection records an action id, object tile, item or target. The common executor consumes any required item or ammunition, runs the authored event or combat-like resolution, updates the compact tile-object record, and refreshes the affected map state. A checkpoint serializes that record, so presentation must be reconstructed from the saved result rather than replaying the reward or destruction event.

## FE9-SYS-070 — Doors and keys

<span id="fe9-sys-070"></span> A closed door is both a flagged placed object and a blocked passage. The adjacent Door command uses action 11. An ordinary unit needs the selected Door Key; a unit with the lock-opening skill can take the thief path without carrying one. Enemy AI treats those as separate permissions: deployment flag `0x10` allows Door Key use, while a `SID_KEY0` thief sets unlock eligibility internally.

On commit, the executor runs the chosen key effect and records type `0x21` at the door tile. `DoorOpen` and its instant counterpart move the object to its open visual state and alter the door's breakable-terrain entry; closing reverses that state. A map refresh makes the changed passage visible to pathfinding and occupancy consumers. Save restoration reapplies `0x21`, preventing an opened door from closing after resume. Supplying a door-looking model alone is insufficient: the object flag, terrain/link state, command target, and persistent coordinate must agree.

## FE9-SYS-071 — Chests and rewards

<span id="fe9-sys-071"></span> An adjacent unopened chest exposes action 12 through the same lock-command family. A Chest Key is the ordinary item path; thieves may invoke the Chest Key effect without consuming such an item. AI Chest Key use requires deployment flag `0x20`, while thief eligibility is derived from `SID_KEY0`.

Opening transfers control to the chest's authored event, which is why contents are not a universal field on the 3D model. The event awards the chapter-specific item or dialogue result, then the map records type `0x23` and moves the chest to its opened presentation. That record is serialized so reload does not award the contents twice. Modders must keep the event, chest coordinate, object flag, and reward handling synchronized. Reward delivery delegates to the shared delivery transaction: a full unit destination follows the convoy/prompt/failure route atomically, and an invalid item is rejected before the persistent chest record is committed.

## FE9-SYS-072 — Villages and houses

<span id="fe9-sys-072"></span> A visitable house is recognized on its tile or a neighboring tile and offers Visit, action 9, when its authored event is eligible. `VisitIn` is a no-op in this build; the meaningful work is authored dialogue/reward logic followed by `VisitOut`, which closes the village presentation, waits for it, and marks it visited. The map stores type `0x24`, so the visit cannot be repeated after a checkpoint reload.

Destroyed buildings use the related `0x25` state. This separates three concerns: the object supplies the visual and footprint, the event supplies who may visit and what happens, and the tile record supplies persistent completion. A house model therefore does not invent a Visit command, and changing the dialogue without maintaining its final state call can leave a visually closed, repeatable village.

## FE9-SYS-073 — Breakable walls and buildings

<span id="fe9-sys-073"></span> `SetFragile(x, y, hp)` creates type 4 with current and maximum HP. A valid adjacent attacker receives Break, action 39; resolution uses a combat preview against the object's HP rather than treating the wall as an allegiance-bearing unit. AI operation 212 searches for the nearest intact type-4 object and registers the same action. Damage persists in the tile record, and destruction can change terrain or object animation and fire authored follow-up work; destroyed buildings additionally use type `0x25`.

The important hazard is sequencing: lowering HP, playing a collapse, opening a route, and setting an event flag are distinct operations. An event must converge on the same final terrain, object, and persistent state when skipped. Weapon and attack eligibility is supplied by the breakable object's authored rule/event, while the common destruction commit owns HP exhaustion, terrain/object refresh, flagging, and skip convergence.

## FE9-SYS-074 — Bridges and scripted transformations

<span id="fe9-sys-074"></span> There is no single universal “bridge switch.” Map transformation composes object animation and persistent state (`BuildInstAnim`, door/roof open/close), visual enablement (`SetRoofEnable`), tactical rules (`SetTerrain` and link/occupancy refresh), and an authored event flag. `MapUpdate` is required when the rule change affects occupancy, range, or danger caches. Animation modes can run forward, reverse, jump to either end, or animate without recording; event skip converts recorded animations to their matching end state.

For example, lowering a bridge may animate a model and replace formerly blocked terrain, while opening a roof records `0x22` and reveals an interior. These are related through their lifecycle, not one data type. Individual gates, bridges, roofs, and chapter pieces are authored event/resource combinations rather than a second transformation engine; new transformations should copy a known sequence and test normal play, skip, checkpoint, and reload.

## FE9-SYS-075 — Ballistae and siege objects

<span id="fe9-sys-075"></span> `SetShooter(x, y, facing, iid)` creates type 7, storing the placed weapon's item number and remaining uses. Supported vanilla IDs include Long, Iron and Killer ballistae and the Onager; facing values are directional bits. The map also needs a matching placed model. A valid operator with `SID_SHOOT` can receive Shoot, using action 42 or 49, after range and target checks. AI operation 112 performs the corresponding reachability check.

Firing consumes the tile object's ammunition rather than a carried inventory slot. Save serialization preserves the item and uses, and `ShooterBulletCheck` totals `5 - remaining uses` across shooters for event logic. Its five-shot baseline is an assumption of that helper, so a modded shooter initialized above five produces a negative contribution. Actions 42 and 49 are caller/presentation variants that reach the same shooter-object and ammunition commit path; operator eligibility and range use the shared action-legality queries.

## FE9-SYS-076 — Hidden items

<span id="fe9-sys-076"></span> A hidden item is an authored tile/event reward record rather than a property of the visible map model. Entering or searching the eligible tile evaluates the current unit against that record's discovery predicate and chance. Failure leaves the collected state unset, so retry behavior follows the authored event policy; success delegates to the shared reward-delivery transaction and only then commits the collected marker that save restoration observes. AI can pursue the reward only when its behavior exposes the corresponding tile action. Chapter coordinates, reward IDs, unit modifiers, and chances are authored data, not separate system ownership.

## FE9-SYS-087 — Wait

<span id="fe9-sys-087"></span> Wait is the minimal complete unit action. Its player command is always available once the unit has a destination and commits action 1 without selecting a second target. The AI's `check_wait_action` uses the same action id at the unit's current tile when the actor is not busy; AI movement routines can first select a better reachable tile and then register that same wait action.

Execution commits the chosen movement, closes the command sequence, and leaves the unit with acted state. It does not invent an attack, target, or map-object effect. The `taikitk` script native starts a token that deliberately lasts until the player's next Wait command, demonstrating that Wait is also an observable event boundary rather than merely “nothing happened.” Canceling before commit returns to destination or movement selection; after commit, ordinary selection cannot grant another full action until refresh.

## FE9-SYS-088 — Canto and post-action movement

<span id="fe9-sys-088"></span> Canto is a controlled handoff after the main action, not a second full turn. An eligible mounted or flying actor that has movement left may enter a post-action destination step. The unit's main operation and its consequences—item use, trade, combat, experience, death, events—remain committed; only unused movement becomes available. Finishing or canceling to the current tile leaves the unit acted.

Eligibility combines actor capability, the completed action type, and remaining movement. The item property `movtw` supplies the Knight Ring's Canto behavior, while class/skill capability supplies the ordinary mounted/flying route. The destination search must use the current map after the action: a killed blocker, opened door, revealed fog enemy, carried unit, or event-driven terrain change can alter legal tiles. A save cannot represent Canto as an unspent normal action or reload would duplicate the committed command. The caller's committed action type and capability determine whether the continuation is offered; interruptions finalize the unit as acted, while the per-action allow list remains executor data.

## FE9-SYS-089–091 — Rescue, Drop, Take, and Give

<span id="fe9-sys-089"></span><span id="fe9-sys-090"></span><span id="fe9-sys-091"></span> Rescue uses action 25 and links a carrier to a carried unit; unit-state bits `0x2` and `0x4` distinguish the two roles, and the carrier's saved slot points to the carried slot. Drop uses action 26, breaks that link, and starts a motion process toward the selected adjacent tile. A Drop next to an enemy hidden by fog becomes the “!” encounter action instead. Give and Take use actions 27 and 28, but perform the transfer in their menus, so their cases in the common executor intentionally do nothing. State bit `0x100000` can disable Give and Drop.

Scripts expose `UnitPairup` and `UnitBreakup`, and removing or escaping a carrier first drops its passenger. Saves preserve the relationship. Availability queries compose actor/target allegiance, effective Build/carry capacity, existing carry links, action state, and a legal adjacent destination. The executor revalidates those predicates before changing either unit, so a failed Drop/Take/Give leaves both links unchanged. Removing or escaping a carrier resolves the passenger first, and invalid edited links are save-validation concerns. Exact thresholds and movement modifiers are supplied by the effective-stat and class getters rather than duplicated in this action system.

## FE9-SYS-092 — Shove

<span id="fe9-sys-092"></span> Shove is command action 19, normally supplied by `SID_TACKLE`. It selects an adjacent unit and attempts a one-tile displacement directly away from the actor. Availability must establish an eligible actor/target pair and a usable destination; execution rechecks the result before starting the shove motion. AI operation 115 can select the lowest-level candidate and register the same action.

The target may resist when it has `SID_IMPREGNABLE`: the executor rolls the target's Strength as a percentage and reduces displacement to zero on success. Fliers follow a separate no-displacement branch. A unit pushed onto a type-9 pit triggers the fall consequence. `UnitTackle(actor, target, 1)` exposes the motion to scripts, with event skip moving the unit instantly. Availability and execution share the effective-weight, direction, terrain, occupancy, and boundary predicates; class/item values are inputs owned by their definition systems.

## FE9-SYS-093 — Smite

<span id="fe9-sys-093"></span> Smite is the two-tile sibling: `SID_TACKLE2`, command action 20, and the same executor family with an initial displacement of two. It shares the resistance and flying branches, then computes the aligned destination and launches the common shove/smite motion process. `UnitTackle(actor, target, 2)` is the script-facing equivalent.

Two tiles introduce a separate legality problem: both the intervening tile and final destination must pass the same boundary, terrain, and occupancy checks. Failure leaves the target unmoved; a pit consequence is evaluated only on the tile where the target actually lands. Effective-weight thresholds come from the same getters used by Shove.

## FE9-SYS-094 — Trade

<span id="fe9-sys-094"></span> Trade mutates two adjacent allied inventories through a dedicated exchange UI. It can be entered as command action 6 or as action `0x28` from the Items submenu. The UI moves eight-byte item instances—not just IDs—so current uses, forge index, drop flag, and equipped bit travel with the item. Closing the exchange commits both inventories before the action controller decides acted/Canto state.

Because equipped state is stored on the instance, moving an equipped weapon requires the recipient and donor to be revalidated: a unit cannot keep combat access merely because an illegal weapon still has bit `0x80`. Empty slots and the separation between four weapon/staff slots and four ordinary item/accessory slots constrain placement. The command's availability query owns adjacency and faction eligibility, the transfer validates both destination halves, and the shared equipment refresh repairs illegal equip state; repeat/Canto behavior follows the committed action state.

## FE9-SYS-095 — On-map Supply

<span id="fe9-sys-095"></span> The party convoy is a 200-instance array and is unavailable through the early chapters; script transfer becomes available in chapter 0 or internal chapter 9 onward. Full-inventory rewards can open a convoy-or-discard flow, and `UnitItemSendtoWarehouse` can send a slot when the facility is unlocked. If that low-level call meets a full convoy it deletes the least valuable stored item to make room.

The player-facing Supply command adds a chapter/access gate and an eligible supply owner or adjacent access object before opening the same storage UI. Transfers preserve complete item instances between the unit's eight slots and the 200-entry convoy, reject or prompt before an over-capacity commit, compact the source deterministically, and return through the ordinary pending-action/Canto state. Chapter-specific access rows are authored policy; storage ownership remains in [Economy](./economy.md).

## FE9-SYS-096 — Item use

<span id="fe9-sys-096"></span> Items opens a submenu; Use commits action 4 after filtering the selected inventory instance through its definition and current-unit conditions. An item record supplies its use effect and capabilities, while the instance supplies remaining uses and forge/equip flags. The executor dispatches the matching effect, waits for required presentation or target selection, decrements durability only on a committed successful use, removes an exhausted instance, repairs relevant equipment state, and ends or hands off the action according to the command rules.

The AI reaches the same action through usability and behavioral-need checks; it does not treat every carried consumable as useful. Healing, status cures, stat boosters, promotion items, keys, bands, transformation items, and special effects each add their own target and failure rules, many of which have later inventory entries. Each effect-specific handler supplies its predicate and result; the common wrapper guarantees that rejection or cancellation occurs before consumption and that a committed effect refreshes state before action finalization.

## FE9-SYS-097 — Equip and automatic fallback

<span id="fe9-sys-097"></span> An inventory instance's flag byte uses bit `0x80` for equipped state. Equip and Unequip live in the Items submenu. Weapon slots 0–3 and item/accessory slots 4–7 each have at most one active instance. `UnitSetEquip(unit, slot)` clears the current equipped bit in the selected half, validates the requested instance, and sets it if usable; passing `-1` chooses the first usable weapon. An invalid requested slot can therefore leave the unit unequipped rather than restoring the old choice. Laguz units with the innate-weapon path are deliberately not changed.

Equipping a weapon refreshes the weapon held by the map model, and the bit is serialized with the item. Combat and forecast still recheck rank, class/skill access, status, range, and uses; an equipped bit is a preference, not permission. After removal or invalidation, the shared refresh scans legal weapon slots in deterministic inventory order and otherwise leaves the unit unequipped; inventory mutations call that refresh before returning control.

## FE9-SYS-098 — Talk

<span id="fe9-sys-098"></span> Talk is action 7 and appears only when the acting/target pair matches an eligible type-8 Talk event whose completion flag is not already set. The command records both units and delegates the conversation and any recruitment, item, flag, or force-transfer consequences to the event system. Completion marks the event so the pair cannot repeat it after a checkpoint or reload.

The menu is not the source of recruitment rules. Directionality, alternate speakers, chapter flags, and story outcomes are authored in the event registry; [Events & Scripting](./events-scripting.md#fe9-sys-049) owns that lifecycle. If the event removes or transfers either unit, action cleanup observes the resulting runtime state rather than assuming both original actors remain selectable.

## FE9-SYS-099 — Tile-sensitive command family

<span id="fe9-sys-099"></span> Visit (9), Door (11), Chest (12), Seize (13), Escape (14), and Arrive (41) are separate menu classes sharing one design: availability combines the candidate destination with an adjacent object, invisible goal marker, or eligible event; execution records the action and delegates the consequence. Visit/Door/Chest then use the persistent object lifecycles above. Seize, Arrive, and Escape hand control to objective/event logic rather than setting victory unconditionally.

Escape removes the actor through the authored path; player units enter reserve with the escaped bit, and scripts can count them or require every force-0/reserve actor to be escaped. Seize/Arrive validate their authored actor/tile/objective predicates before an event sets `gf_complete`. Failure leaves the actor and objective unchanged, while the committed command finalizes ordinary action/Canto state. Leader restrictions and objective coordinates are chapter data consumed by those command classes.

## FE9-SYS-100 — Partner orders

<span id="fe9-sys-100"></span> Order and Direct use actions 50 and 51 and change policy for partner/yellow units rather than granting direct control. The partner phase still runs AI action enumeration and scoring. Current coverage does not map every displayed choice to its saved runtime value, AI sequence override, target/destination priority, chapter gate, reset boundary, or behavior when the partner force is empty. Expand [AI Activation, Routes & Orders](./ai-activation-and-orders.md#fe9-sys-272); no additional article is needed.

## FE9-SYS-101 — End Turn

<span id="fe9-sys-101"></span> End Turn belongs to the map command menu, not the selected-unit command table. It closes player input, cancels or waits for transient child UI, finalizes any pending selection/Canto state, and hands control to the phase controller. A phase with no eligible units uses the same handoff. Suspend/save records either side of that boundary rather than a half-committed menu action; detailed phase events and force ordering belong to [Turn, Phase & Unit-Action Cycle](./turn-phase-action-cycle.md).

## FE9-SYS-102 — Dynamic action-menu construction

<span id="fe9-sys-102"></span> Each unit command is a small menu-entry class with label, help, availability, and execute methods. From a candidate destination, the builder asks every entry whether current unit traits, inventory, skills, remaining movement, adjacent units, targets, objects, events, and objective markers make it legal. Only qualifying entries are offered; selection writes the action id and parameters, then the executor revalidates and commits.

The AI does not instantiate this menu, but its checker functions populate the same pending-action shape and reach the same executor. Rebuilding matters after movement, Trade, fog discovery, event mutation, Canto handoff, or target death because a previously visible command can become illegal. The command-vtable list supplies deterministic menu order, availability hides entries that do not apply, and the executor revalidates the chosen entry before committing.

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

## Interactions and review boundary

All map-action systems on this page are reviewed without a blocking research gap. Menu-entry availability, action IDs, the shared executor, object-event delegation, persistent tile records, Canto, carry/displacement, trade/supply/item transactions, partner policy, End Turn, and command rebuilding establish each ownership and commit boundary. Chapter rewards, hidden-item declarations, command labels, and per-item predicates remain authored content tables rather than unknown action-system rules. No new primary article is needed.
