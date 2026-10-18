---
id: "modding-share-a-patch"
title: "Package and share a mod"
description: "A release workflow for metadata, checks, reproducible builds, text exports, base-disc fingerprints, tpatch creation, clean-room application, smoke testing, permissions, documentation, and rollback"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Release", "Patch", "Distribution"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/61-share-a-patch.md"
tutorial_kind: "task"
tutorial_track: "test-and-release"
tutorial_stage: "draft"
prerequisites: ["modding-check-project", "modding-dolphin-setup", "modding-known-limits"]
verification: ["source-reviewed", "unknown"]
---
# Package and share a mod

**Route:** Disc & Patch; File → Apply patch to a disc…

## What you will make

You will produce a versioned `.tpatch`, apply it to a clean matching retail image in a separate environment, compare the result with the release candidate, run the defined smoke matrix on that output, and package precise requirements, compatibility, credits, permissions, and known issues—without distributing a built disc.

## Before you begin

Freeze a release candidate. Record mod name/version, author/credits, source project revision, supported game region/revision and clean base fingerprint, save compatibility, enabled Game Code entries, unresolved warnings, and third-party asset permissions. Keep the clean source disc/image available.

## How the editor fits together

**Check** validates project relationships. Build produces the test image. **Mod details…** supplies user-visible metadata. **Export as text…** creates a review/version-control representation and replaces the chosen export folder's previous contents. **Create patch…** records changed files against base hashes. **Apply patch to a disc…** verifies the recipient's base and constructs output without a project.

## Guided walkthrough

Run Check and disposition every warning. Build the exact frozen project, test changed content plus title/boot/save/load/transition, and record the artifact hash/version. Review enabled executable patches and debug state.

Fill Mod details with stable version, credits, description, requirements, and known issues. Export as text into a dedicated versioned folder if desired; never point it at a folder containing unrelated work because export replaces its contents.

Create the `.tpatch` from the frozen candidate. In a clean-room test, use an untouched supported base and a separate output path. Apply through **File → Apply patch to a disc…**. A rejection usually means wrong region/revision or modified base; do not weaken hash validation.

Launch the newly applied output—not the working build—and repeat a compact release matrix. Compare important changed-file hashes or behavior with the candidate. Package only the patch and documentation, not copyrighted disc content.

## Understand every control

- **Mod details…:** embedded/release-facing identity and credits.
- **Check:** structural diagnostics; passing is necessary, not gameplay proof.
- **Build:** candidate image used for testing, not distribution.
- **Export as text…:** destructive replacement of chosen export folder contents.
- **Create patch…:** base-hash-specific changed-file package.
- **Apply patch to a disc…:** recipient workflow and clean-room reproducibility test.

## Interactions and precedence

Patch reproducibility depends on an exact base, complete changed-file set, and no hidden dependence on project originals or temporary files. Save compatibility depends on data-table identity and campaign changes, not patch success. Asset redistribution rights apply to payload content regardless of extension.

## Test matrix

| Release check | Required result |
| --- | --- |
| project Check/build | no undispositioned error; exact version |
| clean base match | patch accepts documented region/revision |
| wrong/modified base | clear rejection without output corruption |
| boot/title | correct mod identity and no debug menu |
| changed content | representative feature works |
| transition/save/load | declared compatibility holds |
| executable/media | enabled tweaks and large assets work |
| clean-room output | independent of working project |

## Troubleshooting

**Base rejected.** Verify region, revision, dump integrity, and that it is unmodified.

**Applied output differs from working build.** The project changed after patch creation or a needed file was outside the captured workflow; refreeze and recreate.

**Export removed files.** It replaces its destination by design; use a dedicated folder and restore unrelated files from version control/backup.

## Save, build, and revert

Archive source revision, metadata, patch, checksums, release notes, and test record together. A withdrawn release is replaced with a new versioned patch; users revert by applying no patch to a clean base or restoring their own backup, not by distributing a reverse disc image.

## Limits and confidence

Patch hashing/application and export behavior are source-reviewed. Cross-platform emulator settings, hardware media, third-party permissions, and every gameplay path remain release responsibilities. `.tpatch` is base-specific and is not a license to redistribute source assets.

## Related tutorials and references

- [Know the current limits](63-known-limits.md)
- [Contributing](../meta/contributing.md)
- [Disc layout](../meta/disc-layout.md)

---

[← Previous: Use the game's debug menus](60-debug-menus.md) · [All tutorials](index.md) · [Next: Build a three-chapter mini-campaign →](62-mini-campaign.md)
