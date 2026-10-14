---
id: "model-formats"
title: ".g / .gs / .ga"
description: "Skeleton, mesh, and battle animation — three sibling formats for every character and object model"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics","3D","Animation"]
aliases: ["tellius_archive.html#/model-formats"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/model-formats.md"
---
# .g / .gs / .ga

*Skeleton, mesh, and battle animation — three sibling formats for every character and object model*

Character and object models — `zbg/`'s 3D battle scenery, units' map models under `ymu/` and battle models under `zu/`, spell effects under `yme/`, weapons under `xwp/` and map props under `zmap/` — use three sibling formats, usually bundled together in a [pack archive](./pack-archive.md): `.g` (bone hierarchy), `.gs` (mesh geometry), and one `.ga` per animation. None are public, documented Nintendo formats — all three are proprietary to this game's engine.

## Two models per unit

  Every unit is drawn with two different models: a small one on the map, and a detailed one in the battle scenes. <span class="confidence confidence--confirmed">confirmed in game</span>

<div class="table-wrap">
<table><thead><tr><th>Folder</th><th>Model</th><th>Contents</th></tr></thead><tbody>
    <tr><td><code>ymu/&lt;class&gt;/</code></td><td>Map model, also used for combat on the map (at most 853 visible triangles)</td><td>An <a class="wl" href="../lz10/">LZ10-compressed</a> <code>pack.cmp</code> with <code>skeleton.g</code>, <code>body.gs</code>, the idle and move animations and one texture; the map-combat animations and more texture variants (one 128×128 image each) are loose files next to it</td></tr>
    <tr><td><code>zu/&lt;code&gt;/</code></td><td>Battle model (up to 8,840 visible triangles)</td><td>One uncompressed pack per weapon type (<code>fig1_ax.pak</code>, <code>fig1_ha.pak</code>, <code>fig1_no.pak</code>...), each holding the same mesh and skeleton plus that weapon's battle animations (attacks, criticals, dodge, damage, death...); loose texture files (two 256×256 images each), one per character or army variant</td></tr>
  </tbody></table>
</div>

  The battle engine's table `jobList.dbx` maps every class to its battle-model code — the Ranger to `reng`, the Fighter to `fig1`, Greil's Hero class to `helg`, the Cleric to `mist` — and can give one character or one animation ID its own code. The model's parameter table then names the texture file for the unit's character or army: in the Prologue, Boyd (`PID_BOLE_MAP1`, a separate record from later-chapter Boyd) uses `zu/fig1/bole_map1.tpl`. See [ZDBX & DBX](./zdbx.md). <span class="confidence confidence--confirmed">confirmed in game</span>

## How the three files become one model

  An in-game 3D actor holds four resources side by side: a skeleton, a mesh, an animation and a [TPL](./tpl-texture.md) texture file. The skeleton names bones and establishes their hierarchy, the mesh binds vertices to those bones, and animation curves change bone transforms over time. The first time each file is loaded, the engine turns its internal file offsets into memory pointers — each format has its own way of listing which fields need that.

<div class="table-wrap">
<table><thead><tr><th>File</th><th>Loader fix-up rule</th></tr></thead><tbody>
    <tr><td><code>.gs</code></td><td>Uses the generic relocatable-resource header; every nonzero pointer in the file is listed in the relocation table in ascending order.</td></tr>
    <tr><td><code>.g</code></td><td>Fixes a fixed set of fields: the name pool, bone array, and each bone's parent, sibling, child, and name references.</td></tr>
    <tr><td><code>.ga</code></td><td>Fixes header words 0, 1, 8, 9, 10, and 11 plus the nine optional footer slots.</td></tr>
  </tbody></table>
</div>

## .g — skeleton

  A 16-byte header (a zero word, the name-pool offset, the bone count, and the bone-array offset — always `0x10`), then one `0xF4`-byte (244) record per bone, then the name pool: a root name that no bone uses, followed by every bone's name in order. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Bone record</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>0x00</code>, <code>0x04</code>, <code>0x08</code></td><td>Parent, next sibling and first child, as bone indices (<code>-1</code> = none) — the hierarchy is a tree of first-child / next-sibling links <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x0C</code></td><td>Flags: which transform terms the bone uses (scale, rotation, translation, joint orient, pivots, rotate axis); the engine adds extra bits based on the bone's name (a bone named <code>persp</code> is marked specially) <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x10</code></td><td>The skinning matrix (3&amp;times;4): a draw call with a bone subset multiplies it after the bone's world matrix <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x40</code></td><td>The <strong>value block</strong>: 43 floats the animation system reads and overwrites (table below) <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0xEC</code>, <code>0xEE</code>, <code>0xF0</code></td><td>The bone's own index, its Euler rotation order (always X, then Y, then Z), then a name pointer <span class="badge confirmed">confirmed</span></td></tr>
  </tbody></table>
</div>

<div class="table-wrap">
<table><thead><tr><th>Value block</th><th>Meaning</th></tr></thead><tbody>
    <tr><td>0&amp;ndash;2</td><td>Scale</td></tr>
    <tr><td>3&amp;ndash;5</td><td>Rotation X/Y/Z, in degrees</td></tr>
    <tr><td>6&amp;ndash;8</td><td>Translation</td></tr>
    <tr><td>9&amp;ndash;11</td><td>Joint orient</td></tr>
    <tr><td>12&amp;ndash;14</td><td>Rotate pivot — on character rigs, the joint's position in the bind pose</td></tr>
    <tr><td>15&amp;ndash;26</td><td>Scale pivot, the two pivot offsets, and a rotate axis</td></tr>
    <tr><td>27&amp;ndash;30</td><td>A rotation quaternion (unused by any shipped animation)</td></tr>
    <tr><td>31&amp;ndash;42</td><td>The seed local matrix (3&amp;times;4) for bones no animation drives</td></tr>
  </tbody></table>
</div>

  **Anchor bones.** A bone whose name is wrapped in underscores — `_s1_`, `_sw1_`, `_cam_` — is flagged as an anchor when the skeleton loads, and anchors are the only bones the engine ever finds by name: it asks for the first anchor containing a token such as `s1`/`s2` (present on every class rig), a weapon-trail pair (`sw1`/`sw2`, `sp`, `ax`, `ja`, `ha`, `bw`, `ex`), `root`, `cam`, `sun`, `ref`, `tail`, `r_hand`/`l_hand` or the feet. Names containing `_bl_` and `_by_` receive two additional loader bits whose exact effects remain open. Every other bone name is free. <span class="confidence confidence--confirmed">confirmed</span>

  A replacement character skeleton can follow the vanilla convention directly: identity skinning matrix, rotate and scale pivots at the joint position, rest values elsewhere, flags `0x180`, an identity seed matrix, and X/Y/Z Euler order. Under that convention the bind pose draws stored vertices in place and each bone rotates about its joint.

  The engine builds each bone's matrix from these values the way Maya does: translation, then a rotation about the rotate pivot (joint orient, Euler rotation, rotate axis), then a scale about the scale pivot. The seed matrix at slots 31&ndash;42 is exactly that matrix built from the bone's own values on 56,463 of the 56,836 bones on the disc. <span class="confidence confidence--confirmed">confirmed</span>

## .gs — mesh

  A `.gs` file uses the engine's general **relocatable resource** header: file size, the location and length of a relocation table listing every pointer field in the file, and counts of named symbols the file exports or imports. After it comes a mesh header holding an export date (`0x20040723` on almost every model), a per-model id, a bounding box, and ten array pointers with their counts: positions, normals, UVs, vertex colors, materials, meshes, three draw-call lists, and a CPU-skinning buffer. <span class="confidence confidence--confirmed">confirmed</span>

  Draw calls ("shapes") are split into **three render passes**, each a linked list drawn in order with its own settings (see "Draw passes" below). Each shape names a mesh, a material and a bone, carries blend and depth flags (additive, subtractive, depth-off, hidden) and a GX vertex-attribute mask, and points to a ready-made GameCube **display list** that the engine hands to the GPU unchanged. Every vertex attribute in that list is a 16-bit index into the shared arrays, so a mesh can hold up to 65,535 positions. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Skinning mode</th><th>How a vertex follows the skeleton</th></tr></thead><tbody>
    <tr><td>Single bone</td><td>The whole shape moves with one bone</td></tr>
    <tr><td>Bone subset</td><td>The shape lists up to <strong>10</strong> bones; each vertex picks one of them (a GameCube hardware limit of 10 matrix slots)</td></tr>
    <tr><td>Blended</td><td>Vertices mix up to four bones by weight, computed on the CPU each frame — used by 324 models: every battle model (<code>zu/</code>), bows (<code>xwp/</code>) and ships (<code>zmap/</code>)</td></tr>
  </tbody></table>
</div>

  **The blended-vertex buffer.** Blended shapes do not use the shared position and normal arrays. They index a separate buffer of 12-byte vertex slots (a 16-bit position and a 16-bit normal, both scaled by the same power of two stored in the buffer header), grouped by weight records. Each record lists up to four bones with 8-bit weights (weight / 256, not renormalized) and a run of vertices that share them. Every frame the engine moves each record's vertices into the CPU's locked cache in whole 32-byte blocks, blends the record's bone matrices, transforms the positions and normals, and writes them to the same place in a per-actor output buffer. The shapes then draw that output with only the actor's own matrix. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Weight record field</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>0x00</code> bones[4]</td><td>Bone indices, <code>-1</code> when unused <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x08</code> weights[4]</td><td>8-bit weights out of 256; zero in one-bone records, which skip the blend <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x0C</code> block offset</td><td>32-byte-aligned start of the record's first block; every record begins a fresh block <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x10</code> block size</td><td>Bytes moved per record: a multiple of 32, at most 4 KiB <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x12</code> first vertex</td><td>Offset of the first vertex inside the block: the next multiple of 12 (0, 4 or 8) <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x13</code> bone count</td><td>1 to 4 <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x14</code> / <code>0x16</code></td><td>Vertex count; count of vertices that also carry a binormal and tangent (unused on the disc) <span class="badge confirmed">confirmed</span></td></tr>
  </tbody></table>
</div>

  The header's scale also applies to the *animated* output, so every posed coordinate must still fit a 16-bit value at that scale; shipped files use 5 to 10 fraction bits. The header's last field equals the number of records that hold more than one vertex, and no engine reader for it has been found. <span class="confidence confidence--strong">value pattern</span>

  **Battle models are fully blended.** Every visible shape of a battle model goes through the blended path, including vertices that follow a single bone. A battle model rebuilt with multi-bone hardware shapes instead drew parts out of place in battle. <span class="confidence confidence--confirmed">confirmed in game</span> The reason is how the game reuses matrix slots: when it draws the first single-bone or blended shape of a list, it also loads the matrices of the next shapes of that list (up to ten), and those shapes reuse them later without reloading. A multi-bone shape always loads its own bones into the same slots, so every single-bone or blended shape drawn after it in the list picks up the wrong bone. Drawing a list's multi-bone shapes first avoids it, which is what the app's importer now does. <span class="confidence confidence--plausible">traced in code, not yet re-tested in game</span>

  **Hidden shapes.** The draw routine skips any shape flagged hidden, and no code has been found that changes the flag. 81 battle models use it for weapon placeholders: meshes of the weapons the character can hold, each shape assigned to a bone named after its weapon type (Greil's model has a hidden sword on `SW` and a hidden axe on `AX`) while its vertices are weighted to the hand socket. The weapon actually shown in battle is the separate model of the equipped item. About half the shapes of the weapon models themselves are hidden too, for a purpose not yet known. <span class="confidence confidence--strong">engine + in game</span>

  **Weapon sockets.** The game attaches the equipped weapon to the body's hand bone by name — the left hand for bows, the right hand otherwise. <span class="confidence confidence--confirmed">engine</span> Inside the body, the hidden placeholders sit on socket bones wrapped in underscores (`_r_hand_`) or on bow and arrow bones (`BW001`, `_ar1_`); visible geometry essentially never uses them, and the camera, root and foot sockets carry none at all.

  **Two kinds of bone.** Most bones of a battle body are placed by an offset from their parent and have no rest rotation; a few (`Base`, `weapon`, `target`) turn about a pivot at their joint, which is how every bone of a map model works; sockets with no transform simply follow their parent. Animation keys are absolute values tied to bone numbers, so an animation can be moved to another skeleton by matching bones by name and shifting position keys by the difference in rest position. <span class="confidence confidence--strong">engine + files</span>

  **Named bones.** The game looks a bone up by name only when the name is wrapped in underscores and contains a token (`_r_hand_` answers to `r_hand`); every other name is free (a skeleton with entirely different names and proportions works in game once it has these). In battle, `_r_hand_` holds the weapon (`_l_hand_` for bows), `_root_` follows the hips so a step taken in one animation carries into the next, `_cam_` is a camera target, and the foot and `_pl_` sockets are optional. On the map, `_s1_`/`_s2_` place the feet and shadow and pairs like `_ax1_`/`_ax2_` mark the ends of a weapon's swing trail. <span class="confidence confidence--confirmed">engine + in game</span>

  **Battle situations.** Each battle model's `zu/<code>.dbx` names the animation for every situation and weapon (idle, ready, two attacks, two crits, dodge, damage, death, run, sidestep, throw, crit throw) and for follow-ups such as a crit followed by an attack. Situations may share a file: the Fighter's 29 files hold 14 distinct motions. <span class="confidence confidence--confirmed">files + engine</span>

  **Events combat waits for.** Melee attacks and crits carry event code 0 (the blow lands: damage, HP gauge) and code 1 (the swing, which moves the round on after a miss); throws carry code 2, which releases the thrown weapon. An attack without them leaves the round waiting; with them, retargeted and newly timed attacks play through in game. The other codes are cosmetic: footsteps and dust (50), weapon trails (0x14&ndash;0x1B, with 0x19 ending the trail), ground splashes, camera lights (0x28/0x29) and sounds (1000 and up). <span class="confidence confidence--confirmed">engine + files</span>

  **Map actions.** A map model plays one file per action and weapon (`wait`, `move`, `atk1`&hellip;); an action its record does not enable plays `tackle` instead. Map weapons are part of the body, each on its own bone, and each animation shows the weapon in use by scaling its bone to 1 and the others to 0. <span class="confidence confidence--confirmed">engine + files</span>

  **Draw passes.** The camera draws every model's first shape list, then every second list, then every third, each with fixed GPU settings. A shape's list decides how the transparency of its texture is treated. <span class="confidence confidence--confirmed">engine + in game</span>

<div class="table-wrap">
<table><thead><tr><th>List</th><th>Settings</th><th>Used for</th></tr></thead><tbody>
    <tr><td>1st &amp;mdash; opaque</td><td>No blending; texture alpha ignored; depth written</td><td>Solid geometry: weapons, ground, cliffs, most map models</td></tr>
    <tr><td>2nd &amp;mdash; alpha-tested</td><td>Pixels with alpha below 128 are discarded; depth tested after texturing and written</td><td>Cut-outs: leaves, grass cards, and about half of all battle-model shapes</td></tr>
    <tr><td>3rd &amp;mdash; blended</td><td>Blended by alpha; depth tested but not written</td><td>Translucent effects: 7,399 of the 7,515 spell-effect shapes, most of them also additive</td></tr>
  </tbody></table>
</div>

  Cut-out textures are stored as CMPR with 1-bit alpha, using the format's three-colour block mode, whose fourth colour is transparent. Scenery with its leaf shapes moved to the opaque list draws their transparent pixels as dark blocks. Some model states override the lists, drawing a whole model opaque, alpha-tested or blended.

  A shape that follows a single bone stores its vertices **in that bone's own space**: the engine draws them through the bone's world matrix. On an unanimated prop that is the chain of each ancestor's seed matrix — the map cursor's arrow, for example, is stored at unit size and scaled up and raised by its two bones. Character bodies store their vertices in model space: their bones turn about their pivots, and the animation rebuilds every driven bone's matrix each frame. The header's bounding box is in model space; each mesh record's bounds are in its bone's space. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Shape flag bits</th><th>Effect</th></tr></thead><tbody>
    <tr><td><code>0x1000</code></td><td>Back faces culled (single-sided) — 3,469 shipped shapes <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x0800</code></td><td>Front faces culled — unused on the disc <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x1800</code></td><td>Nothing culled (double-sided) — 13,686 shipped shapes <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td><code>0x6000</code></td><td>Always the shape's render pass + 1 (<code>0x2000</code>, <code>0x4000</code>, <code>0x6000</code>); no reader found <span class="badge strong">value pattern</span></td></tr>
  </tbody></table>
</div>

  The GameCube treats **clockwise** triangles as front-facing, and the shipped triangle strips are stored that way — the reverse of the counter-clockwise convention most modern 3D tools use. <span class="confidence confidence--confirmed">confirmed</span>

!!! info "Materials are brightened at load time"
    When a mesh is first loaded, the engine multiplies every material's primary color by 1.25 (capped at 255). A stored gray of `204` is therefore drawn as full white.

  Shape flags are part of the render contract, not just authoring metadata. Bits `0x1800` select the GX cull mode, while an actor-side `0x1000` flag swaps front and back and turns the double-sided case into culling everything. Bits `0x6000` mirror the render-pass list number, but no engine reader has been isolated for them.

## .ga — animation

<div class="table-wrap">
<table><thead><tr><th>Region</th><th>Location</th></tr></thead><tbody>
    <tr><td>Header</td><td><code>0x00</code>, 12 big-endian u32 words</td></tr>
    <tr><td><strong>Bone-group table</strong></td><td><code>0x30</code> &amp;hellip; <code>curve_table_addr</code> — 16B/record, header word 7 records</td></tr>
    <tr><td><strong>Curve table</strong></td><td><code>curve_table_addr</code> &amp;hellip; <code>keyframe_data_addr</code> — 12B/record</td></tr>
    <tr><td>Keyframe data</td><td><code>(frame: u16, value: int16)</code> pairs, one run per curve in curve order</td></tr>
    <tr><td>Footer</td><td>Header word 0, when nonzero — nine block pointers right after the keyframes</td></tr>
  </tbody></table>
</div>

!!! info "The curve count is derived from addresses"
    The header does not store the total curve count. The curve table runs from `curve_table_addr` to `keyframe_data_addr`; dividing that byte span by 12 gives the number of curve records.

  **Bone assignment** comes from the group table: each 16-byte record is `(bone_index, channel_mask, first_curve, curve_count)`, and every record names a real bone — usually starting at the hip (bone 1), just below the root locator. A curve's channel is the slot of the bone's value block it overwrites: 0&ndash;2 scale, 3&ndash;5 rotation (degrees), 6&ndash;8 translation, 12&ndash;14 rotate pivot. Values are **absolute** — a key's integer times 2<sup>&minus;shift</sup> — linear between keys and held before the first and after the last. Bones without a group keep their seed matrix. <span class="confidence confidence--confirmed">confirmed</span>

  The archer's bow bone is animated with a scale of 0 whenever the bow should not be seen. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Header word</th><th>Meaning</th></tr></thead><tbody>
    <tr><td>3</td><td>Format: <code>0x11</code> on every file (Euler rotation, 16-bit keys) <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td>4, 5</td><td>Loop flag and the frame a loop restarts at — only the idle <code>ready</code> animations loop <span class="badge confirmed">confirmed</span></td></tr>
    <tr><td>6</td><td>The frame playback ends at; it can run past the last key, holding the final pose <span class="badge confirmed">confirmed</span></td></tr>
  </tbody></table>
</div>

  Footer slot 0 is the **event track**: a list of frames, each with a few event codes. As the animation plays, the engine collects the codes of every frame it passes and hands them to the battle code. Codes 3 and 4 mark a loop's start and end, `0x1C`/`0x1D` raise and clear a battle flag, and `0x28`/`0x29` spawn camera and light effects <span class="confidence confidence--confirmed">confirmed</span>. Code 1 sits on the frame an attack connects, and codes from 1,000 up look like sound effects <span class="confidence confidence--strong">by placement</span>. That is why the track appears on attacks, criticals, spells and moves but never on `damage`, `dead`, `escape`, `ready` or `wait`.

  Footer slot 1 holds **material alpha tracks**, one per material of the `.gs`: the same head as the event track (a count, then one offset per material, `0xFFFF` for none), and per track a key count, a mode (0 linear, 1 step) and `(frame, value)` keys. The value, 0–255, replaces the material's alpha. Effects rest fully transparent and fade in this way: Wind's activation glow rises from 0 to 179 and back over its first 45 frames. Slot 2 has the same layout with RGB565 colours (no vanilla effect uses it), slots 3 and 4 scroll the textures, and slot 8 feeds the particle emitters <span class="confidence confidence--confirmed">engine</span>; slot 8's layout is not decoded <span class="confidence confidence--open">open</span>.

## Round-trip layout certainty

  The three formats are layout-complete enough to rebuild every shipped file byte-for-byte: 1,785 `.gs` meshes, 1,785 `.g` skeletons, and 4,422 `.ga` animations. That pins down block order, 32-byte display-list and bone-subset alignment, string-pool ordering, and curve-ordered keyframe runs. The remaining open questions are behavioral meaning for a few flags and event slots, not the physical layout of the files.

  See [Combat & Battle Animation](../systems/combat-animation.md) for how a `.ga` file is actually selected during a battle, via [FE8Anim.bin](./fe8anim.md).
