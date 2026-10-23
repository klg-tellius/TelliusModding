---
id: "modding-hub-chapters"
title: "Create a hub and plan chapter unlocks"
description: "Create chapter entrance tiles and return points, register persistent unlock and completion flags, and understand the remaining menu and marker visibility work"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Chapters", "Flags", "Scripting"]
aliases: []
status: "draft"
last_reviewed: "2026-10-18"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/hub-chapters.md"
tutorial_kind: "task"
tutorial_track: "units-and-events"
tutorial_stage: "draft"
prerequisites: ["modding-script-editor", "modding-event-flags"]
verification: ["source-reviewed", "unknown"]
---
# Create a hub and plan chapter unlocks

**Routes:** Chapters → Create hub…; hub chapter → Build → Hub; Game Data → Flags; Chapter → Script

## What you will make

The hub tool creates a chapter in which an avatar walks to chapter entrances. **Arrive** enters a destination; **Visit** displays its description. Each link has a separate return point, and installing the hub places a visible Arrive-style map object on its action tile.

!!! warning "Conditional links are not implemented in the hub editor yet"
    The current link editor has no unlock flag or completion flag fields. Generated Arrive and Visit events are unconditional, and generated markers are initially present for every link. Registering or setting flags alone does **not** hide or disable an entrance. The setup steps below work today; the availability sections explain the flag design and the remaining integration needed before conditional links can be considered complete.

This guide is source-reviewed, not an assertion that every region and save path has passed in-game testing. Extended storage installation remains gated on regional validation in the normal editor; experimental playtest builds are a separate workflow.

## Before you begin

Use a Path of Radiance project with editable chapter assets and supported chapter routing. Back up the project and retain a save from before hub activation. Read the storage limitation above before choosing an extended installation.

## How the editor fits together

The hub is a chapter plus a saved link configuration. The Build tab edits a draft; **Install hub** generates the game-facing scripts, messages, markers, and routing. The Flags page manages named state separately. At present, no link configuration field connects that state to entrance availability.

## Guided walkthrough

### 1. Create the hub chapter

1. Back up the project. Complete [script editing](33-script-editor.md) and [event flags](34-event-flags.md) before adding custom progression logic.
2. Prepare a dedicated character in **Game Data → Characters** if no unused avatar is available. It must not be deployed in any other chapter. An Ike-looking avatar can be a separate character; do not reuse the campaign's deployed Ike record.
3. In Chapters, choose **Create hub…**. Select a free **Chapter number**, a **Title**, and a **Template chapter**. The template supplies chapter assets; its units and events are replaced for the hub.
4. Choose the **Avatar** and **Opens after** chapter. Winning that activation chapter opens the hub for the first time.
5. Choose **Copy the template's map** or **Blank map**, with the desired width and height. A blank map can use a
   chosen solid **Color** or an **Image**. **Stretch** draws the image once across the complete ground plane;
   **Tile** repeats it once per tactical tile. Images are converted to the game's texture format and resized to at
   most 1024 pixels per side. Click **Create hub**.
6. On the new chapter's Build tab, place the avatar's starting tile using Select. Keep the player army to the avatar alone, and keep the opening's deployment, camera, and fade sequence intact.

The hub remains an ordinary editable chapter: terrain, props, dialogue, and custom events can be edited normally. Its generated opening deploys the dedicated avatar group. Installing hub setup positions the avatar before the opening focus/fade on that generated opening, with a first-player-phase fallback. If you replace the opening, preserve the order **deploy avatar → position avatar → focus camera → reveal map** to avoid a visible teleport on return.

Use **Build → Hub → Edit ground…** to change a blank hub's solid color or image later. On a copied template
or subsequently replaced terrain, the editor instead offers to replace the 3D terrain with a flat image plane after
an explicit warning. Both paths preserve the tactical grid, tile terrain, prop records, links, and scripts,
participate in Build-tab undo/redo, and are written with the other map changes by **Save Chapter**. Flattening custom
terrain permanently removes its authored ground geometry when saved; props positioned for slopes or raised ground
may consequently float or intersect the plane.

The generated script also refreshes the avatar after every completed action: it clears the acted bit and rebuilds the map's movement ranges. The avatar can therefore move, choose **Wait**, and move again indefinitely during the same player phase, as well as use other actions repeatedly. Effective Movement itself is capped at **20** by the game, so values above 20 do not create a larger range. Choose a value up to 20 for each individual leg; do not add Canto or a custom infinite-action skill. Canto only spends movement left over from the current action, whereas the hub refresh grants a new full action.

### 2. Create chapter entrance tiles

In **Build → Hub**, confirm **Opens after** and **Flag storage**. Extended storage gives routing its own saved bank, but is unavailable for ordinary installation until validation permits it. Vanilla storage consumes the shared vanilla flag budget. Do not select Vanilla simply to bypass a full-budget error; check the busiest chapter first. Initial extended installation or migration requires a fresh playthrough; existing saves are not converted.

For each destination:

1. Select the destination in **Chapter links** and click **Add link**.
2. Click its **Action tile** on the map. Arrive and, when configured, Visit use this tile.
3. Click its **Return point**. This is where the avatar should stand after finishing that destination. Choose a walkable, unoccupied tile that remains usable even if the entrance later disappears.
4. Enter a **Description** if the player should be able to choose Visit for information. Leave it empty to omit Visit entirely. Descriptions allow up to 240 characters.
5. Drag the green square or blue circle, or use the corresponding **Place** button, to adjust the action tile or return point.
6. Click **Install hub**. Repeat installation after editing links; saving the draft alone does not update game events.

For example, internal destination `02` could use action tile `(4, 4)` and return point `(5, 6)`. Use the chapter picker rather than assuming internal IDs match displayed chapter numbers: the retail prologue is internal `01`.

Installation writes routing, hub flags, chapter events, description messages, and entrance map objects. The map object is a visual marker; it does not itself create an Arrive or Visit action. **Remove link**, followed by installation, removes that configured entrance for every playthrough. This is different from hiding it conditionally in one save.

### 3. Register persistent progression flags

For a chapter that starts locked and should disappear after victory, reserve two **campaign** flags through **Game Data → Flags → Campaign flags → Add campaign flag…**:

| Example name | Meaning | Where to write it |
| --- | --- | --- |
| `G_C02_UNLOCKED` | The prerequisite was met | The event that grants access |
| `G_C02_COMPLETED` | The destination was successfully finished | The destination's actual victory sequence |

Use campaign scope because both the destination and the hub must read the values across chapter changes. Chapter-local flags are unsuitable for this state. Choose Extended when the project's verified runtime supports it; otherwise respect the shared vanilla budget. The hub's reserved routing storage is not a general-purpose overflow bank: leave `HUB_ACTIVE`, `HUB_STARTED`, and the destination/pending routing flags to hub setup.

Registration allocates a name; it does not unlock a chapter. Confirm both names are registered unconditionally, retain stable slots, and compile before adding reads or writes. Do not clear these flags in the hub's Startup or opening: doing so would erase progression whenever the player returns.

### 4. Set unlock and completion state

After the prerequisite succeeds, add this statement to that existing event:

```python
set("G_C02_UNLOCKED")
```

The prerequisite can be another chapter's victory, a conversation, recruitment, or any supported event condition. The flag records that the condition was satisfied so that the hub does not have to reconstruct it.

In the destination's successful victory sequence, before it hands control back to chapter routing, add:

```python
set("G_C02_COMPLETED")
```

These are statements to insert in existing event functions, not complete standalone scripts. Set completion on victory, not when choosing Arrive, opening Visit, or entering the destination. Defeat or an unfinished visit must not permanently remove the chapter. When a victory also unlocks another chapter, set that chapter's unlock flag in the same successful sequence before leaving.

## Interactions and precedence

### Apply one availability rule to all three surfaces

The intended condition is:

```python
get("G_C02_UNLOCKED") and not get("G_C02_COMPLETED")
```

| Unlocked | Completed | Arrive | Visit, if description exists | Marker |
| --- | --- | --- | --- | --- |
| No | No | Hidden/unavailable | Hidden/unavailable | Hidden |
| Yes | No | Available | Available | Visible |
| Yes | Yes | Hidden/unavailable | Hidden/unavailable | Hidden |
| No | Yes | Hidden/unavailable | Hidden/unavailable | Hidden |

For a chapter open from the start, omit the unlock requirement and test only `not get("G_C02_COMPLETED")`. For a repeatable chapter, omit the completion restriction. These are availability policies; the current editor does not yet offer controls to select them.

### Arrive and Visit must be filtered before the menu is shown

A complete implementation must use the rule when deciding whether each location action is offered, and check it again before running the handler. Both Arrive and Visit need the same rule. Leaving a description empty removes Visit permanently, but does not provide conditional visibility.

Putting an `if` inside `HubGoTo2` or `HubDescribe2` can stop their effects after selection. It does **not** establish that the command disappears from the unit menu. Likewise, the `name` field in `@on_location` is an event/debug label, not a supported unlock-condition field. Do not put a flag name there expecting availability filtering.

There is currently no verified, paste-ready hub recipe for conditional location-menu filtering in the editor. That integration remains necessary to meet the table above. Do not treat a no-op Visit option as a finished hidden entrance.

### Marker visibility is separate

The researched native calls `BuildInstHide(x, y)` and `BuildInstShow(x, y)` hide or show a **hideable** map prop at a tile. They return whether a suitable prop was found. An illustrative marker refresh for the example tile is:

```python
if get("G_C02_UNLOCKED") and not get("G_C02_COMPLETED"):
    BuildInstShow(4, 4)
else:
    BuildInstHide(4, 4)
```

This is a marker-only integration example, not a complete conditional-link implementation. Confirm that the actual installed marker is hideable and that the intended object is affected, especially when several props share the tile. These calls do not remove location actions.

Refresh marker visibility after the hub map loads and before it becomes visible; refresh again after any hub event changes the relevant flags. A player-phase-only refresh can show stale markers during the opening. Availability must also remain correct after suspend/reload, rather than relying solely on an opening that may not rerun.

### Preserve generated code

Hub installation regenerates the block between `# BEGIN TELLIUS HUB SETUP` and `# END TELLIUS HUB SETUP`. Manual guards inside that block will be overwritten on the next installation. Keep custom helpers outside it, but remember that a helper has no effect unless something calls it. Durable conditional links require the generator and action-availability logic to support these flags; this guide does not claim that support already exists.

Keep destination ChapterData records and return points even when hiding completed entrances. Completion should change availability, not delete the destination chapter or strand the returning avatar.

## Understand every choice

| Choice | Effect |
| --- | --- |
| Opens after | Selects the first victory that activates the hub; it is not a per-link unlock rule. |
| Action tile / Return point | Separates where a chapter is entered from where the avatar returns. |
| Description | Nonempty creates Visit; empty omits Visit for all states. |
| Flag storage | Chooses hub routing storage, subject to runtime support and budget. |
| Unlock flag | Records a prerequisite; requires availability integration to control a link. |
| Completion flag | Records victory; can exclude a one-time chapter once availability is integrated. |

## Save, build, and revert

Save and compile custom scripts with **Check** before exporting the project through its normal build workflow. Install changed hub links before building, then inspect any custom integration that regeneration might replace. Keep the exported build and its matching save/runtime layout together. To revert an installation or storage change, restore the project backup as a whole rather than restoring only a chapter script; routing, registrations, map objects, and generated messages must agree.

## Test matrix

First export and test the unconditional hub with a compatible fresh playthrough. Enter through **Opens after**, check the marker and optional Visit text, use Arrive, win the destination, and verify the return point. For modified openings, check the avatar's position before the player-phase banner as well as afterward.

Once conditional availability is implemented, test every row of the state table. For each unavailable state, walk onto the former entrance tile and open the action menu: **neither Arrive nor Visit should be offered, and the marker should be absent**. Merely seeing an empty tile is not sufficient.

Also verify:

- Unlocking from another chapter persists on return to the hub.
- Unlocking from an event inside the hub updates actions and the marker immediately.
- Visit does not set completion; actual victory does.
- A completed entrance stays hidden after normal save/reload and suspend/reset/reload.
- The return point works even when its entrance has become hidden.
- Initially open and repeatable chapters follow their chosen policies.
- Reinstalling hub setup does not silently remove custom progression behavior.

Use [the Flags guide](34-event-flags.md) to inspect names, storage, and values. Save editing can prepare test states, but also test the real prerequisite and victory events. Record the game region and build when testing; successful host compilation alone does not verify in-game menu visibility.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Flag is true but the entrance stays available | Current generated links are unconditional; flag-to-link integration is still required. |
| Marker disappears but Visit remains | Map props and location actions are separate. Menu filtering is missing. |
| Visit remains but does nothing | A handler guard prevents effects, but does not hide the command. |
| No Visit even for an available link | Check that Description is nonempty and reinstall the hub. |
| Progress is forgotten on return | Check campaign scope, registration, and accidental clears in hub startup. |
| Entrance briefly appears while loading | Refresh visibility before the opening fade, after map loading. |
| Avatar visibly jumps at player phase | Check positioning after deployment and before focus/fade in the opening. |
| Custom link checks vanish after editing links | Installation replaced the generated block. |

## Limits and confidence

The setup controls and generated events described here were checked against `hub_tool.py`, `hub_dialog.py`, `hub.py`, and `hub_creation.py`. Marker calls are documented in the repository's native-contract research. Conditional action-menu filtering is not provided by the current hub generator, and the marker example still needs verification against the installed prop in game. This page therefore documents a working basic hub and a progression integration design, not a completed conditional-link feature.

## Related tutorials and references

- [Use the map Build tab](21-map-build-basics.md)
- [Edit and compile event scripts](33-script-editor.md)
- [Design, register, and test event flags](34-event-flags.md)
- [Build reliable chapter events](35-event-recipes.md)
- [All tutorials](index.md)
