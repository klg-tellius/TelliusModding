# Changelog

Each release's full notes are on the
[GitHub Releases page](https://github.com/klg-tellius/TelliusModding/releases); the
notes of the release being prepared are in [release/RELEASE-NOTES.md](release/RELEASE-NOTES.md).
Version numbers come from `App/fe_modding/__init__.py`.

## v1.0.0.1

Tellius Patcher fixes.

- WIT download: retries, then falls back to the `tools-mirror` release copy; a WIT
  next to the patcher, on the PATH or chosen by hand (`wit.exe` or the `.zip`) is used.
- `.rvz` discs: DolphinTool is also found in the usual Dolphin folders, next to the
  patcher and on the PATH, or asked for once.

## v1.0.0.0

First stable release.

- Radiant Dawn on the US, European and Japanese discs: Game Code, chapter jump, hub
  routing, text encodings, multi-track movies and the staff roll per disc.
- One Saves, Battle Data and Battle Cameras page for both games. Radiant Dawn saves
  edit units (copy and remove included), map objects, flags and the whole system
  record, on all three regions.
- New Radiant Dawn Game Code rows: class critical multiplier, promotion items on story
  units, animated ally and NPC battles, animation speed, analog camera rotation.
- New Radiant Dawn editors: glossary, Conversation Room, endings, class introductions,
  movie subtitles, world-map route lines, Wii banner.
- Radiant Dawn maps and models: map wrapping, height ceiling, mirrored and offset
  props, blank hub maps, new skeletons on map units.
- Decoding coverage on the US discs: about 0.003 % of Path of Radiance and 0.0006 % of Radiant
  Dawn left undecoded or unclassified.
- Chapter pages gain a Roster tab on both games (fixed team or player's army, set the
  others aside, join/leave at the end, turn 1 check with a new save and a full army).
- Tellius Archive: Radiant Dawn sections in the lessons and systems pages.
- 3D Models and Map Models show only the buttons that work on the selected model, with
  plainer names (Export to Blender, Replace with my character, Duplicate as new model...):
  the skeleton tools sit in one Skeleton menu, the clip tools under the Animations tab's list.
- Faster test runs (affected tests, disc samples, parallel runs) and a Dolphin input
  driver for in-game checks.
- The app shows its version in the window title, on the start screen and in Help >
  About; Tellius Patcher shows it in its title.
- The code is released under the MIT License.
- 3D Models: the Animations tab lists each weapon's clips with their role, length and
  combat events, plays them at the game's speed (with 0.5x and 0.25x) and marks event
  frames under the slider. An imported clip shared by several weapons now changes in
  each of them. Clips go to and from Jade's Tellius Forge Blender add-on as `.ga` files,
  which Settings > Preferences can download and install.
- 3D Models: Copy clip from another model... replaces a clip with another model's, from
  the same game or the other one (Path of Radiance <-> Radiant Dawn), played on the set's
  own skeleton.
- Path of Radiance doors and building roofs placed with the Map Builder work as in the
  retail game: a closed door blocks its tile, a roof hides its room and lifts when a door
  in or next to it opens. The editor fills the roof layer the game reads for them.
- Map Builder: new **Add roof** tool. Drag a rectangle over a room whose walls are already
  built, pick a texture (built-in presets or an image file) and a gable or flat shape: a
  roof model is generated on top of the walls and placed as a working building roof.
- Every chapter map gets **Edit ground…** and **New blank map…**; **Free unused flags…**
  frees chapter flags that nothing uses.
- 3D Models: **New character model…** (new slot and rig fit in one go).
- New weapons and weapon effects on both games (**Battle Weapons › New weapon…**,
  **Visual Effects › Recolour…**).
- Assets: tiles for Tutorials, Staff Credits and Soundroom Tracks.
- A guide for agents and scripts driving the app from Python (`docs/app/agent-modding-api.md`).

## v0.2.0 (2026-11-15)

Foundational Radiant Dawn support; campaign-building tools (chapters, hubs, phases,
deployment, AI, shops, flags, supports, validation); battle simulation, Dolphin
playtests, save editing and Path of Radiance Game Code patches; editors for dialogue,
maps, terrain, models, animations, particles, audio, video and DBX; Excel import and
export; the standalone patcher; the expanded Tellius Archive.

## v0.1.0

Initial Windows build.
