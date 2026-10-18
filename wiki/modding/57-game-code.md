---
id: "modding-game-code"
title: "Apply engine tweaks"
description: "A safe workflow for recognized executable revisions, Game Code catalog entries, parameters, byte-site detection, conflicts, focused testing, selective and full reset, and release documentation"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Game Code", "Executable", "Patches"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/57-game-code.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-check-project", "modding-dolphin-setup"]
verification: ["source-reviewed", "unknown"]
---
# Apply engine tweaks

**Route:** Tools → Game Code

## What you will make

You will install one narrowly testable executable tweak on a recognized `main.dol`, prove its direct and unaffected cases, reopen/detect it, revert it selectively, and document revision, parameters, compatibility, and residual uncertainty.

## Before you begin

Use a project copy and clean matching executable. Record game region/revision/hash/recognition status, patch entry name, description, original detected state/value, intended parameter, and a focused baseline scenario. Never copy offsets between revisions.

## How the editor fits together

The Game Code catalog contains reviewed byte-pattern/site definitions plus UI parameters. The page detects whether the executable is vanilla, patched, conflicting, or unknown. A control changes executable instructions/data, not the chapter/table that happens to expose a related concept.

Unknown builds are read-only because a coincidental offset is not evidence of the same code. Entries can overlap or depend on assumptions; the checker/detector is the authority for supported states.

## Guided walkthrough

Open the page and confirm revision recognition with no conflict. Read the full entry description, scope, defaults, parameter units/range, known interactions, and verification status. Capture baseline behavior in Dolphin.

Enable only this entry or change one parameter. Save/apply through the page, reopen it, and verify detection reports the intended state/value. Run project checks and inspect the change log.

Build and test: direct trigger, lower/upper boundary if parameterized, save/reload when persistent state is involved, and a neighboring behavior that must remain unchanged. Test the inverse/disable route. Reopen Game Code after all runs.

Use the entry-specific reset/disable where available. **Reset everything to vanilla** restores every catalog-managed site and is appropriate only when that broad effect is intended; it can remove unrelated tweaks.

## Understand every control

- **Recognition/status:** executable revision and whether bytes match known vanilla/patched forms.
- **Entry enable/disable:** installs/removes one catalog transformation.
- **Parameter fields:** encode documented constants; validation limits input, not gameplay proof.
- **Description/confidence:** owns scope, interactions, and verification warning.
- **Reset everything to vanilla:** catalog-wide destructive-to-patches restore, not a selective undo.

## Interactions and precedence

Executable rules can override or consume authored data, but do not automatically rewrite it. Two patches touching overlapping sites are incompatible unless the catalog explicitly composes them. Save files may retain state produced while a tweak was enabled.

## Test matrix

| Case | Evidence |
| --- | --- |
| baseline | clean executable and original behavior |
| detection after apply | exact installed state/value |
| direct trigger | intended rule changes |
| boundary inputs | no overflow/off-by-one |
| unaffected neighbor | scoped behavior remains vanilla |
| save/reload | persistent state remains coherent |
| selective revert | baseline returns without removing other tweaks |
| clean release build | expected catalog state re-detected |

## Troubleshooting

**Page is read-only.** Use a supported clean region/revision; do not force-write guessed offsets.

**Entry reports conflict.** Restore the exact original or identify the other executable modification before proceeding.

**Value saves but behavior does not change.** Confirm rebuilt image, trigger path, parameter units, and whether data/event policy controls the observed case.

## Save, build, and revert

Keep the clean executable and patch manifest. Apply one entry, check, build, and test. Revert selectively and verify detection plus baseline. Before release, review every enabled entry and include it in compatibility/known-issues notes.

## Limits and confidence

Catalog detection and writes are source-reviewed. Most entries lack exhaustive Dolphin coverage, and unknown builds remain unsupported. A successfully encoded value proves byte transformation, not every gameplay path.

## Related tutorials and references

- [Use the game's debug menus](60-debug-menus.md)
- [Package and share a mod](61-share-a-patch.md)
- [main.dol](../formats/main-dol.md)
- [Runtime Engine Architecture](../systems/runtime-engine-architecture.md)

---

[← Previous: Simulate and render a fight](56-battle-simulator.md) · [All tutorials](index.md) · [Next: Play and rewind a chapter in the app →](58-play-chapter.md)
