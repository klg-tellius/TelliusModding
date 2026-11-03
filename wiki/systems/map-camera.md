---
id: "map-camera"
title: "Map Camera"
description: "How player focus, unit following, scripted shots, interpolation, and restoration control the tactical camera"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Maps", "Camera", "Presentation"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/map-camera.md"
system_entries: ["FE9-SYS-066"]
system_reviewed: ["FE9-SYS-066"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# Map Camera

The map camera turns tactical coordinates and scripted presentation requests into a view. It follows cursor or unit focus during play, temporarily yields to events and actions, interpolates between shots, enforces map/view limits, and returns control without changing the unit or tile state it displays.

## Mental model and worked example

Think of the camera as a temporary lease on one view object. Ordinary map input holds the lease and centers around cursor focus. Unit movement can replace that with a follow target. An event may acquire the lease for a scripted pan or shot, optionally wait until interpolation finishes, then release it so the previous tactical context can be reconstructed.

For example, a reinforcement event can hide player input, pan toward a doorway, spawn units, wait for the move/shot to finish, and then restore the cursor's area. If the scene is skipped, the reinforcements and final camera ownership must match the watched path even though intermediate interpolation is omitted. Saving unit coordinates does not automatically preserve the camera lease or an in-progress event wait.

## Camera ownership and state

<span id="fe9-sys-066"></span> Camera inputs include tactical focus, target unit or coordinate, map/world conversion, map extents, zoom/rotation mode, transition duration, event/script requests, and scene/input state. Output is presentation state: view center/orientation/scale and a completion signal used by scripts or processes waiting for motion.

The camera does not own cursor coordinates, unit positions, objective state, or event flags. It consumes them. This matters when debugging apparent desynchronization: a camera centered on an old location does not mean the unit is still there, while changing the camera target must not teleport the unit.

The event interface exposes the state transition directly. `SetMapCamera` writes target X/Y/Z and an interpolation constant; `InstantSetMapCamera` writes both current and target coordinates and snaps the camera. `CopyMapCamera` snapshots X/Y/Z into dedicated globals and marks the snapshot valid. `PastMapCamera` restores that snapshot through interpolation during normal playback but uses the immediate restoration path while an event is skipped; `InstantPastMapCamera` always restores both current and target and snaps. `SetCamSuspend` independently controls the suspension bit, so retaining a position and allowing camera updates are separate operations.

## Rules and lifecycle

1. Tactical map entry creates a camera from map bounds and an initial focus.
2. Ordinary input moves the cursor and requests centering or bounded tracking.
3. Unit movement/actions may install a temporary follow target.
4. Dialogue, combat presentation, or an event can suppress input and take camera ownership.
5. A request selects an immediate change or interpolation and exposes completion to wait logic.
6. Skip/cancel or normal completion resolves the request to its required final state.
7. Ownership returns to the tactical controller, which recenters or restores the appropriate focus.
8. Scene exit destroys transient camera processes; checkpoint/resume reconstructs a valid view from saved context.

Bounds should be applied after resolving the desired focus so the view cannot expose invalid space around small or irregular maps. Interpolation must start from the current view, not a stale default. A new higher-priority request must either replace, queue behind, or explicitly finish the old one; blending two owners without policy can strand a script wait.

## Player control and following

Player camera control is coupled to cursor navigation but remains a separate state machine. Cursor movement can request centering, edge scrolling, or tracking; unit cycling changes focus and may recenter. Zoom and rotation affect the view, not tactical coordinates. Map bounds and presentation safe areas constrain what the final transform may show.

During committed movement, the camera can follow the actor while authoritative path execution advances tile occupancy. Shove, rescue/drop, staff relocation, reinforcement entry, escape, death, and map-object animation can request their own focus. When the action ends, the tactical controller should restore a useful cursor/unit focus rather than keep a destroyed or removed actor as target.

## Scripted/event takeover

Event camera operations are authored presentation. They may point at a coordinate or actor, set a view immediately, interpolate over time, wait for completion, shake, or restore. Because event scripts can mutate units and map state during the shot, target resolution and restoration must tolerate a unit being removed or a tile becoming invalid.

Skipping is a convergence rule: intermediate camera motion may be discarded, but required final view state, ownership release, input restoration, and event continuation must occur exactly once. A camera wait that is removed without signalling completion can deadlock; signalling twice can advance the event past required mutations.

## Save, resume, and edge cases

Persistent tactical facts are sufficient to choose a safe default view. The suspend serializer does not preserve an in-progress interpolation lease; resume reconstructs a stable view from tactical/scene context. Editors should therefore not invent transient camera coordinates or interpolation state in a save editor.

Edge cases include tiny maps, targets at bounds, missing/hidden/removed actors, simultaneous unit and event focus, entering full battle presentation, returning from dialogue, map transformations, scene skip, suspend during motion, and debug camera controls. Each test should verify both the rendered view and ownership/input after completion.

## Implementation trail and interactions

The reproducible trail connects tactical cursor centering and map-input handlers to camera state/update processes, then follows unit-movement focus and event-call wrappers into interpolation and wait completion. Map coordinate conversion and extents provide constraints; event skip and scene teardown provide convergence boundaries. Differential traces should log requested target, owner, starting/final transform, duration, completion signal, and restored focus.

The camera interacts with [Tactical Map Interface](./tactical-interface.md), [Maps](./maps-system.md), [Coordinate Systems & Grids](./map-grid.md), [Events & Scripting](./events-scripting.md), [Map Actions](./map-actions.md), and combat presentation. Those systems decide what deserves focus; the camera decides how the view reaches it.

## Review boundary

FE9-SYS-066 is reviewed without a blocking research gap. The native handlers establish target versus current state, snapshot validity, interpolated versus immediate restore, skip convergence, and independent suspension; the suspend format establishes that transient interpolation is reconstructed rather than serialized. Per-shot tuning constants and action-specific composition remain implementation detail, not an unresolved ownership or persistence rule. No additional primary article is required.
