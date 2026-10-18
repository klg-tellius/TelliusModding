---
id: "modding-portraits"
title: "Create and assign a portrait"
description: "Build a small/large portrait pair, align facial parts, manage palettes, and connect it to a character"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-create-character"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Portraits", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/11-portraits.md"
---
# Create and assign a portrait

**Route:** Assets → Portraits → New portrait…

## What you will make

You will create paired `FID_TUTORIAL_GUARD` and `FID_L_TUTORIAL_GUARD` portraits, assemble optional eye/mouth animation, assign the small FID to the tutorial character, and inspect it in character, menu, and dialogue contexts.

## Before you begin

Prepare lossless source images with clean transparency. Small body is fitted to 192×128. A supplied large body is kept at its source size (retail examples reach 256×296); if omitted, the small body is enlarged. Mouth and eye inputs must each contain exactly six separately chosen images. Keep a working retail portrait open for coordinate comparison.

## How the editor fits together

Portrait `.cms` files contain TPL pictures. `Face/facedata.bin` maps FIDs to a file, nameplate MPID, feature coordinates, flags, and menu placement. The game pairs small `FID_NAME` with large `FID_L_NAME`. A character record stores the small FID. Picture bytes, face-record metadata, and character assignment have separate save boundaries.

## Guided walkthrough

1. Select **New portrait…**. Enter only `TUTORIAL_GUARD` in **Name**; the dialog creates both prefixed IDs. Choose the independent MPID and select the tutorial PID under **Use for character**.
2. Choose the small body. Optionally choose six mouth frames: two sets of three, with frames 3 and 6 closed. Choose six eye frames: left eye frames 1–3, right eye frames 4–6.
3. Enter left-eye, right-eye, and mouth `(x,y)` anchors for the small face. Start from a retail face with comparable framing and iterate in the assembled preview.
4. Supply large components/coordinates or allow the small body to enlarge. Choose an optional 64×64 menu face; otherwise it is cut from the small body.
5. Select **Create**. If a PID was chosen, the in-memory character FID changes; use **Save FE8Data.bin** on the character/Game Data page to persist that assignment.
6. In Portraits, inspect individual **Pictures** and **As the game assembles it**. Use **Preview** for face-record coordinate/flag changes, then **Save face record**. For replaced picture bytes, select **Save pictures** separately.
7. Add a short dialogue with eye/mouth changes and inspect the character header/menu face. Build and test in Dolphin before claiming runtime success.

## Understand every control

| Control | Effect |
| --- | --- |
| Name | creates `FID_NAME` and `FID_L_NAME`; must be unused |
| Name key | MPID used for portrait nameplate metadata |
| Use for character | patches that PID's FID in unsaved FE8Data session |
| Body picture | principal small/large art |
| Mouth frames (6) | two three-frame sets; third/sixth are closed |
| Eye frames (6) | left 1–3, right 4–6 |
| Feature x,y | places each feature pair; `-1` represents absent/unset placement |
| Menu face | explicit 64×64 image or crop from small body |
| Has eyes / Has mouth | face-record flags enabling animated parts |
| Default mouth | starting mouth choice |
| Depth | portrait layering/depth value |
| Menu offset | lowers tall faces in menus |
| Replace picture… | stretches new source to the selected picture dimensions |
| New palette | rebuilds compatible C8 pictures so replacement colors survive |
| Preview | assembles metadata without saving it |
| Save face record | writes facedata metadata |
| Save pictures | writes compressed picture container |

## Interactions and precedence

Coordinates only matter when the corresponding feature flag and pictures exist. **New palette** is available only when all pictures use the compatible indexed format; without it, replacement colors are fitted to the existing palette. Assigning a character in the creation dialog does not save FE8Data. Replacing a shared face file affects every character and dialogue using it.

## Test matrix

| Context | Inspect |
| --- | --- |
| Assembled preview | transparent seams, eye/mouth anchors |
| Character page | small FID resolution and cache refresh |
| Menu/list | 64×64 crop and vertical offset |
| Dialogue idle | body, facing, eye state |
| Dialogue speaking | both mouth sets/closed frames |
| Large-face context | paired `FID_L_` resource |
| Dolphin | load, colors, animation, no missing asset |

## Troubleshooting

Wrong colors usually indicate palette mismatch; compare **New palette** before moving features. Transparent holes indicate source alpha or anchor errors. If Preview changes but reopening does not, save the face record. If pictures revert, use **Save pictures**. If the character still uses the old face, save FE8Data and rebuild. A successful app preview does not prove the new pair loads in game.

## Save, build, and revert

Save picture bytes, face metadata, and FE8Data assignment independently, then reopen all three. Preserve the original pair and checkpoint. Removing a mod-added portrait removes its small/large records and files; first repoint every consuming character/dialogue.

## Limits and confidence

Dimensions, pairing, frame ordering, palette behavior, controls, and save ownership are source-reviewed. Newly added portrait pairs remain **unknown in Dolphin** until the exact build is exercised. Preview composition cannot certify every dialogue transition or hardware renderer.

## Related tutorials and references

- [Create a character](10-create-character.md)
- [Write chapter dialogue](37-dialogue-editor.md)
- [Face Data](../formats/face-data.md)
- [Dialogue Engine](../systems/dialogue-engine.md)

---

[← Previous: Create a character](10-create-character.md) · [All tutorials](index.md) · [Next: Give a character unique models →](12-character-model-slot.md)
