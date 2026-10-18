---
id: "modding-debug-menus"
title: "Use the game's debug menus"
description: "A disciplined workflow for enabling development title or pause-menu tools, isolating debug-created state, recording operations, reproducing findings normally, and removing patches before release"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Debug", "Game Code", "Testing"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/60-debug-menus.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-game-code", "modding-dolphin-setup"]
verification: ["source-reviewed", "unknown"]
---
# Use the game's debug menus

**Route:** Tools → Game Code → Developer tools

## What you will make

You will create a clearly labeled debug-only build, enable one developer entry path, record every state mutation made through it, reproduce the finding through ordinary gameplay, disable the patch, and prove the release candidate no longer exposes debug menus.

## Before you begin

Keep separate baseline, debug, and release output paths. Record executable revision/hash and the selected developer patch. Use a disposable save because debug commands can jump chapters, mutate units/flags/items, bypass initialization, or create impossible combinations.

## How the editor fits together

Developer tools are dormant executable UI/commands exposed by Game Code patches, commonly through the pause menu or development title flow. The patch changes reachability, not the safety of each command. Debug screens operate on live runtime structures and often assume internal prerequisites.

## Guided walkthrough

Baseline the ordinary title/pause menu and target bug. In Game Code, enable only the required developer option and verify patch detection. Build to the debug output and launch with the disposable save.

Open the menu using its documented entry. Before invoking a command, record chapter, phase, roster, flags, inventory, and save state. Afterward record exact command/parameters and changes. Use the command to observe or reach the diagnostic boundary, not to declare the resulting state valid.

Restart from a clean ordinary path and reproduce the underlying behavior without the debug mutation. If it cannot be reproduced, report it as debug-created. Disable the patch, rebuild separately, verify Game Code detection is vanilla/disabled, and check normal title, pause, chapter transition, save/load, and release smoke tests.

## Understand every choice

- **Development title entry:** changes boot/menu path and may bypass normal profile/campaign setup.
- **Pause-menu debug entries:** expose commands during live chapter state.
- **Chapter/unit/flag/item commands:** mutate authoritative runtime state without necessarily running normal events.
- **Patch detection/reset:** proves the release executable, not an older built image, is clean.

## Interactions and precedence

Debug mutation can skip registration, transition, reward, roster, or save-counter updates normally performed by events. Later failures may be consequences of that impossible state. A debug observation is useful evidence about runtime data, but ordinary initialization remains the validation authority.

## Test matrix

| Stage | Check |
| --- | --- |
| clean baseline | menu absent; ordinary scenario recorded |
| debug build | intended entry only; patch detected |
| one command | before/after state and parameters recorded |
| save/reload after command | used only to study risk on disposable save |
| ordinary reproduction | finding occurs without debug mutation |
| disabled rebuild | menu absent and patch detection clear |
| release smoke | title, pause, transition, load all normal |

## Troubleshooting

**Menu does not appear.** Confirm supported executable, applied entry, rebuilt output, and documented invocation context.

**Bug occurs only after a debug jump.** Treat the bypassed initialization as the cause until ordinary progression disproves it.

**Release still shows the menu.** You launched an older image or another developer entry remains installed; re-detect and rebuild to a clean path.

## Save, build, and revert

Never reuse the debug output or save as the release candidate. Disable the individual patch, use catalog reset only when all tweaks should be removed, rebuild, re-detect, and archive the debug-operation log separately.

## Limits and confidence

Patch wiring and known menu functions are source-reviewed. Debug commands can construct states outside retail invariants and are not a validation oracle. Their use never replaces an ordinary fresh-save path.

## Related tutorials and references

- [Apply engine tweaks](57-game-code.md)
- [Developer Debug Tools](../systems/developer-debug-tools.md)

---

[← Previous: Edit and test a save](59-save-editor.md) · [All tutorials](index.md) · [Next: Package and share a mod →](61-share-a-patch.md)
