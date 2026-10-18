---
id: "modding-supports"
title: "Create supports and conversations"
description: "Create a symmetric support pair, explain thresholds and bonuses, author rank conversations, and test progression"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-character-model-slot"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Supports", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/13-supports.md"
---
# Create supports and conversations

**Route:** Character → Supports; Game Data → Supports

## What you will make

You will create one symmetric support pair with increasing C/B/A thresholds, author all three rank conversations, inspect both affinity rows, and test point gain, conversation unlock, rank activation, range, and the five-star cap.

## Before you begin

Choose two valid PIDs that can be deployed together. Record their affinities and existing partners/stars. Write three short scenes. Use a checkpoint: support-list slot positions are stored in unit save data, so restructuring existing lists can affect continued saves.

## How the editor fits together

Support lists, bonds, character affinities, and affinity bonus rows live in `FE8Data.bin`. Rank conversations live separately in `Mess/yell.m` under `MYELL_` identities. A pair is symmetric and must appear consistently for both PIDs. Removing a partner leaves an empty slot rather than shifting later slots because a save remembers points by slot index.

At chapter end, deployed player units gain one point with each deployed partner unless a threshold is waiting to be viewed or either unit has five support stars. Viewing the base conversation grants the final point to both. Rank comparison uses points beyond the stored C/B/A threshold. C/B/A cost 1/2/3 stars, with five stars maximum per unit.

## Guided walkthrough

1. Open character A → **Supports**. Select character B under **Add partner** and choose **Add**. Confirm the pair appears when viewing B too.
2. Select the pair and enter strictly increasing **C at**, **B at**, and **A at** thresholds. Choose small test values in a disposable save so all ranks can be observed.
3. Inspect each character's **Affinity**. In **Game Data → Supports → Affinities**, read the per-rank Attack, Defence, Hit, Avoid, Critical, and Critical avoid row; the last two stored bytes are unused.
4. Use **Conversation C**, author/save the `MYELL_` scene in `yell.m`, and repeat for B/A. Reopen each rank to verify the message identity survived independently.
5. Save `yell.m`, then **Save FE8Data.bin**. Run Check and resolve one-sided/missing-PID problems.
6. Deploy both as player units through chapter completion. In base, confirm only the expected rank conversation is available; view it and inspect the new rank/points.
7. Place the pair within three tiles and compare forecast/combat bonuses with one partner removed or farther away. Continue through B/A while observing the five-star limit.

## Understand every control

| Control | Meaning |
| --- | --- |
| Affinity | character's row used for support bonuses |
| Support partners | symmetric pair slots for the selected PID |
| C/B/A at | point thresholds; must increase and fit stored byte values |
| Conversation C/B/A | opens or creates the rank's `MYELL_` message |
| Remove partner | empties both sides without shifting later saved slots |
| Bonds | separate always-defined relationship records, not rank progression |
| Bond Effect kind 1 | adjacent same-army pair each gains configured Critical |
| Bond Effect kind 2 | when PID2 is adjacent to PID1, opponents have zero Critical against PID2 |
| Bond Value | signed magnitude used by the selected bond effect |
| Affinity table | bonuses per rank: Atk, Def, Hit, Avoid, Crit, Crit avoid |

## Interactions and precedence

Both partners' affinity rows contribute while they are in the same army and within three tiles. Current rank multiplies each row. Bonds require adjacency and operate separately. Chapter parts can cause the support-point pass to run again when configured by the game's flow/patch behavior, so multi-part chapters need explicit observation. Threshold waiting and five-star saturation stop ordinary point gain.

## Test matrix

| Scenario | Expected observation |
| --- | --- |
| Only A deployed | no pair point gain |
| A and B finish chapter | one ordinary point each when eligible |
| At threshold before viewing | no further ordinary gain |
| View C/B/A conversation | final point/rank applied to both |
| Same army within 3 tiles | affinity bonuses included |
| More than 3 tiles | rank exists but combat bonus absent |
| Five stars already held | further rank progression blocked |
| Bond adjacent/nonadjacent | bond effect toggles independently |

## Troubleshooting

If the pair appears on only one side, rerun Check and repair the symmetric data through the editor. If the conversation button exists but content is missing, inspect its `MYELL_` entry and save `yell.m`. If points stop, check pending conversation and total stars. If combat bonuses are absent, check rank, same-army allegiance, distance, and affinity rows rather than thresholds alone.

## Save, build, and revert

Save relationship/affinity/bond data to FE8Data and conversations to `yell.m`; reopen both. Use a fresh save for structural pair-list changes. Revert the pair and its three messages together, leaving empty support slots when removing from a save-sensitive list.

## Limits and confidence

Data structure, point/rank rules, star cost, range, affinity combination, bond semantics, and editor controls are source-reviewed. Exact multi-part timing and customized game-code patches require runtime verification. The editor/checker cannot prove every base-availability condition.

## Related tutorials and references

- [Create a character](10-create-character.md)
- [Write chapter dialogue](37-dialogue-editor.md)
- [Support System](../systems/support-system.md)
- [Dialogue Engine](../systems/dialogue-engine.md)

---

[← Previous: Give a character unique models](12-character-model-slot.md) · [All tutorials](index.md) · [Next: Recruit by talk and make a boss →](14-recruitment-and-bosses.md)
