# Particle effect editor

Open a project, choose **Visual effects**, select an effect, then choose
**Edit particles**. The editor changes the effect's `.ga` member and saves it
back into its `yme/EID_*.cmp` pack. Other pack members are retained.

The tree exposes emitters, stages, curves, keys, animation timing events, and
material alpha, colour, U-scroll, and V-scroll tracks. Select an item, edit its
fields, and choose **Apply fields**. Structural actions add, duplicate, or
remove emitters; add, duplicate, move, or remove stages; add or remove curves;
and add or remove keys. The editor's 3D preview updates after each applied
change and keeps the selected playback frame. Selecting a stage or key seeks to
its frame. **Save effect** writes the pack
through the project's original-preserving save path. The Visual effects page
reloads the changed pack after saving. The page also supports
registry flags and chain links, whole-pack replacement, individual `.g`/`.gs`/
`.ga`/`.tpl` replacement, and texture image replacement.

## Format handling

- Existing fields are patched in place. Unknown control bytes and descriptor
  bits remain untouched unless the user explicitly edits the raw control.
- Structural particle edits append replacement tables and redirect the
  emitter's pointers. Earlier table bytes remain inert in the animation. This
  retains unknown data, though repeated structural edits grow the `.ga` file.
- Changes to events or material tracks rewrite the animation footer and rebase
  the particle table's file-absolute pointers. A no-change apply returns the
  original bytes.
- Integer fields use the game format's ranges. Scale and position controls
  are signed fixed-point values divided by 64; curve key values are signed
  integers divided by `2^shift` at playback.

## Current limits

The preview still approximates the game's particle geometry and GX rendering.
Emitter `+0x0C`, some draw flags, and several source-format fields lack
confirmed game semantics; the UI labels the unresolved control as raw. The
editor does not edit mesh or skeleton geometry in place. Use **Replace part**
for those members. The editor's write operations have been checked against
extracted FE9 effect packs, but the final appearance has not been compared in
Dolphin. Check the finished effect in game before distributing a mod.
