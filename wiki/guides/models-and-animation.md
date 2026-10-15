---
id: "models-and-animation"
title: "3D models and animation learning path"
description: "Export, modify, validate, and import Tellius meshes, skeletons, rigs, animations, and effects"
games: ["path-of-radiance"]
section: "guides"
article_type: "learning-path"
tags: ["Guide", "3D", "Animation"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["telliusmodding-source"]
cms_collection: "guides"
source_path: "guides/models-and-animation.md"
---
# 3D models and animation learning path

Export the existing set before replacing it. Its skeleton, anchor bones, textures, event tracks, and model-selection records form a contract with the engine.

## Route

1. [`.g`, `.gs`, and `.ga`](../formats/model-formats.md)
2. [Skeleton Posing & Skinning](../systems/posing.md)
3. [Combat & Battle Animation](../systems/combat-animation.md)
4. [`FE8Anim.bin`](../formats/fe8anim.md), [`FE8Effect.bin`](../formats/fe8effect.md), and [ZDBX & DBX](../formats/zdbx.md)
5. [Battle Staging & Camera](../systems/battle-staging.md)

Use the app's pre-write review. Treat missing required animation events, unsupported bow skinning, anchor-bone changes, and values beyond vanilla limits as test blockers.
