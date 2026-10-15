---
id: "cutscenes"
title: "Cutscenes & Credits"
description: "How world maps, illustrations, real-time scenes, movies, and credits run and converge under skip"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Video", "Events", "Presentation"]
aliases: ["tellius_archive.html#/cutscenes"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/cutscenes.md"
system_entries: ["FE9-SYS-298", "FE9-SYS-299", "FE9-SYS-300", "FE9-SYS-301", "FE9-SYS-303"]
system_reviewed: ["FE9-SYS-298", "FE9-SYS-299", "FE9-SYS-300", "FE9-SYS-301", "FE9-SYS-303"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Cutscenes & Credits

FE9 presents story with several different engines: world-map sequences, full-screen illustrations, real-time model choreography, pre-rendered THP movies, and the staff credits. Event scripts select and coordinate them; each presentation system owns its resources and timing, while scripts and campaign state own the required story mutations.

## Mental model and example

Treat a cutscene as a transaction with a visible path. The script establishes required state, launches presentation processes, waits for their completion, and continues from a defined final state. Skip may remove the visible work, but it must commit the same required flags, unit changes, rewards, and continuation.

For example, a scene may show a world-map route, fade to an illustration, play a THP movie, then set a story flag. Watching and skipping can differ in frames, audio, and elapsed time; both must set the flag once, destroy each presentation owner, restore input/audio, and resume at the same script instruction.

## FE9-SYS-298 — World-map presentation

<span id="fe9-sys-298"></span> World-map scenes combine `gmap/` art, location/route markers, labels or captions, camera movement, fades, music, and script waits. The event chooses narrative destinations and timing; the world-map presenter translates its own coordinates, animates markers/routes, and signals completion. It does not change the tactical map or campaign chapter merely because a marker moved.

World-map coordinates, route points, and layer identities are presenter-owned resource data. Scripts address the scene and wait on its handle; semantic progression occurs only in surrounding event operations. Skip completes or destroys the presentation handle and resumes the same VM continuation, so coordinate interpolation is never campaign state.

## FE9-SYS-299 — Illustration and still-image scenes

<span id="fe9-sys-299"></span> Still-image presentation resolves `illust/`, `ending/`, or other TPL resources, selects the required image/variant, composes it with captions or dialogue, controls fades/input waits, and releases it. Multi-image TPLs can contain variants; choosing the wrong image index is different from failing to decode the file.

Missing art should take a defined error/fallback path rather than strand the event. Skip and normal completion must both release texture/layout/input ownership and continue exactly once.

Image variant, crop, and scale are selected before drawing from the requested TPL image and layout rectangle. Those are authored presentation fields; preload/cache strategy and exact fade frames do not alter the lifecycle or event result.

## FE9-SYS-300 — Real-time cutscene choreography

<span id="fe9-sys-300"></span> Real-time scenes are script orchestration across actor creation and placement, animation clips, poses, attachments, cameras, effects, dialogue, sound, fades, and asynchronous waits. Each subsystem keeps its own state; the script composes them and joins at explicit boundaries.

Actors used only for presentation should be destroyed without deleting persistent campaign units. Conversely, an authored recruitment, movement, inventory, or flag mutation must occur in both watched and skipped paths. Concurrent camera, actor, and effect processes need deterministic completion so one missing signal cannot deadlock the VM.

The 43-script retail corpus makes the join rule explicit: native presentation calls return handles, script waits join them, and gameplay mutations remain separate bytecode/native calls. Skipping shortens or completes handles; it does not bypass later mutation instructions. A failed optional presenter unwinds acquired actors, cameras, and effects and releases its wait rather than manufacturing a gameplay result.

## FE9-SYS-301 — Pre-rendered movie playback

<span id="fe9-sys-301"></span> Chapter scripts select movies in two confirmed forms. `MoviePlay` receives a literal path such as `Movie/s06_M.thp`; `ChapterMoviePlay` receives a numeric chapter-opening identity. The call transfers full-screen/audio/input ownership to the THP player and waits until completion or skip returns control.

Literal-path selection has no music-style cue-table indirection. `ChapterMoviePlay(N)` always plays the shared `movie/chapter.thp`; the number picks the title card drawn over it, `window/chapter/chapN.cms`. Every retail chapter script passes its own chapter number, so a chapter copied from another must be given its own number to show its own title card. The [THP Video Playback](./video-system.md) page owns decoder/buffer/synchronization details; this system owns script selection, scene handoff, wait, skip, and continuation.

Retail scripts confirm both identities: `MoviePlay` embeds a path such as `Movie/s06_M.thp`, while `ChapterMoviePlay` passes a chapter number. The THP child owns full-screen video/audio/input until end or skip; either terminal path restores the caller and releases the same wait. Invalid media is a failed child presentation, not permission to advance chapter state independently.

## FE9-SYS-303 — Staff credits

<span id="fe9-sys-303"></span> The US build loads `ending/staffroll_noa.bin`; the adjacent `staffroll.bin` is the Japanese list and is not selected by the US loader. `END_STAFFROLL_LINES` supplies the row count and fixes total scroll length at `count × 0x30`. `END_STAFFROLL_STRS` contains rows of three nullable string pointers: column 1 is right-aligned to X `0x120`, column 2 is centered on X `0x130` and retains its own font control, and column 3 is formatted as `#F04%s` and drawn left-aligned at the registered third-column X coordinate. A null pointer renders an empty cell.

Credits remain a presentation child of the ending flow. They consume the selected localized list and return completion to their caller; they do not themselves decide whether the campaign is clear or write postgame state. Opening the presenter through debug therefore cannot grant a clear, and skipping presentation returns through the same ending-owned completion route.

## Rules and lifecycle

1. The event resolves presentation identity and validates required resources.
2. It locks or transfers input and establishes camera/audio/scene context.
3. The selected presenter loads resources and creates its processes.
4. Scripted state changes occur at authored, skip-safe boundaries.
5. The VM waits for required presenters or joins concurrent processes.
6. Normal completion or skip converges on the same final semantic state.
7. Temporary actors, textures, effects, audio, cameras, and input locks are released.
8. The script continues or campaign routing receives the ending/credits result.

Failures before launch must return safely; failures after partial creation must unwind every acquired owner. A missing optional visual must not silently omit a required reward or flag. Scene skip should be tested from multiple intermediate waits, not only from the opening frame.

## Interactions and implementation trail

The trail begins with chapter and ending script references. All 43 chapter scripts provide a corpus for movie, image, world-map, camera, fade, audio, actor, and wait calls. Follow those native bridges into presenter creation, resource resolution, update/completion, skip handling, and teardown. Compare watched and skipped saves and runtime state at the next script instruction.

Cutscenes interact with [Events & Scripting](./events-scripting.md), [Script Functions](./script-functions.md), [Skeleton Posing & Skinning](./posing.md), [Map Camera](./map-camera.md), [Graphics & Images](./graphics-system.md), [Music System](./music-system.md), [THP Video Playback](./video-system.md), and [Endgame & Ending Cards](./endings.md).

## Review boundary

All five systems are reviewed without a blocking research gap. The chapter-script corpus establishes selection, handle/wait ownership, semantic mutation boundaries, normal/skip convergence, teardown, and continuation for world maps, stills, real-time choreography, movies, and credits. Exact coordinates, art crops, interpolation curves, and unused resource variants are presentation data rather than missing system rules. No new primary article is needed.
