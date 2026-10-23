# Path of Radiance 3D pipeline status (US GFEE01, updated 2026-10-21)

The `.g`, `.gs`, and `.ga` readers and writers round-trip the shipped files, but byte-for-byte preservation does not establish the meaning of every field or visual parity with the game. The coverage command is:

```text
cd App
python -m fe_modding.formats.coverage <extracted-files-directory> --saves <gci-directory> --markdown-out <report.md>
```

The latest full-disc scan (1,780 `.g`, 1,780 `.gs`, and 4,421 `.ga` files) measures:

| Format | Undecoded bytes |
|---|---:|
| Skeleton `.g` | 38,083 |
| Model `.gs` | 15,907 |
| Animation `.ga` | 1,162 |

The 184 particle tables have a decoded header, pointers, stage windows, curve ranges, and keys. Their duplicated emitter/stage indices and cached last-key frames are classified **plausible** because they match throughout the corpus but runtime use is not confirmed. The remaining undecoded `.ga` bytes are the 581 emitter controls at `+0x0C` (1,162 bytes). Event codes 6 and 7 in `EID_MSHIELD.ga` are confirmed inert markers; their original authoring labels are unknown. The primary `.gs` unknown is texture descriptor `+6` (15,696 bytes); texture flags `0x2`/`0x4` remain open. Skeleton flags and seed-matrix behavior remain open. Nonzero custom data at fields that are zero throughout the shipped disc is still reported undecoded.

The battle animation dispatchers identify event codes 5, 9–19, 28–49, 55, 56, and 60 (including effect travel `0x11`–`0x13` and controller rumble `0x2F`/`0x30`). `zdbx/param.dbx` and its loader identify codes 51–54 as laguz jump/landing markers and 58 as the small weapon flash marker. Codes at least 1000 resolve through `gcfesnd.bin`'s `SFXTable`. The particle update path reads emitter `+0x0E` as a mode-1 shared texture scale, while the draw path uses flags `0x0600` to select orientation matrix branches.

The three nonzero bytes in `EID_FIRE_LONG.ga` form a curve-range record for an emitter with zero active stages and are classified plausible. With the Ward markers classified, the full-disc total is exactly 1,162 undecoded `.ga` bytes, with no handler failures in any of the three 3D formats. The Visual Effects page shows the unresolved `+0x0C` value in hex. Its values resemble 8.8 fixed point, but no runtime reader or effect meaning has been confirmed.

Further reader and corpus checks: the known particle initialization, update, and draw paths read emitter `+0x0E` through `+0x1A`, but no halfword load of emitter `+0x0C` appears in those paths. A disassembly-wide offset search found no obvious other particle consumer; this is a negative result, not proof that the value is unused. For `.gs` texture descriptor `+6`, a matched sample of 6,799 material textures and their `.tpl` images found 800 records with `0x0000`, all paired with clamp/clamp; 5,681 records with `0x0101` paired with repeat/repeat, and 162 with `0x0101` paired with other wrap modes (mostly effects). Scenery also contains text-like nonstandard values such as `0x6D73` (`ms`). This supports a possible legacy U/V wrap hint or exporter residue, but the traced material binder reads the `.tpl` sampler settings and never reads descriptor `+6`. Its exact source meaning remains undecoded, as do texture flags `0x2`/`0x4` and skeleton flags `0x2`/`0x4`.

Reproduce the texture comparison with `python App/tools/profile_gs_texture_fields.py <extracted-files-directory>`. It covers 533 single-TPL packs and prints a source file and material for every observed combination. Texture flag `0x2` occurs with repeat/repeat in 131 matched records; flag `0x4` occurs with mirrored/mirrored in 41 and repeat/repeat in 37. Neither flag uniquely specifies the TPL wrap mode. A broader load-offset search found no direct descriptor `+6` read in the `GMaterial` code. The traced bone local-matrix builder uses the established transform bits, without testing bone bits `0x2` or `0x4` separately. These negative findings do not identify the fields' source meaning, so their coverage remains **undecoded**.

The load-offset search was repeated with byte loads as well as halfword and word loads. Two apparent `+6` hits in `.gs` material setup resolve to a lighting record and an actor/light index, not the texture descriptor. Likewise, the known particle initialization/update/draw functions do not load emitter `+0x0C` as a byte, halfword, or word; stage count is at `+0x1E`, while the draw path derives line width from emitter `+0x10` and point size from per-stage runtime data. The `+0x0C` corpus has 20 observed values among 574 emitters in `yme` packs, mostly multiples of `0x80` (e.g. `0x0600`, `0x1E00`, `0x0780`) plus an outlier `0x0E95`. This looks like fixed-point source data but does not establish its purpose.

`EID_MSHIELD.ga` alone has event codes 6 and 7: code 6 accompanies code 0 at frame 79, and code 7 occurs at frame 94. The complete Ward effect path closes them as inert. `spawn_ui_effect` installs `FUN_8019cd40`, which tests only codes 0 and `0x12`; the generic actor dispatcher tests the documented flag and camera/light codes; and the sound dispatcher rejects codes below 1000. Neither marker affects the Ward status counter—the gameplay routine writes that separately—so the four bytes are decoded as retained no-ops.

Run `python App/tools/manifest_3d_unknowns.py <extracted-files-directory> <output.jsonl>` to reproduce a per-instance manifest with archive member path, offset, raw bytes, field, and SHA-256. With codes 6/7 classified, `.ga` contributes only the emitter `+0x0C` spans (1,162 bytes). The earlier 2026-10-10 run reported four additional event-code bytes; regenerate the manifest to apply the current classification. The JSONL is reproducible and is not checked in.

`python App/tools/scan_3d_field_loads.py` lists direct byte, halfword, word, and floating-point load candidates for the main model, texture, and particle functions in the US, PAL, and JP DOLs. PAL lacks a high-confidence mapping for the material binder and draw path; JP lacks one for the skeleton relocator. The US/JP material-binder load at `+4` overlaps descriptor `+6` by width, but its base pointer is an image-table entry, not the `.gs` descriptor. The local-matrix builder's `+0x0C` flag read refers to an animation parameter, not the `.g` bone record. These are pointer-provenance findings only; indexed loads, block copies, other call paths, and live reads remain to be checked. No Dolphin GDB session was available during this run, so no field qualifies as proven reserved.

The model preview displays mesh triangles and skeleton poses, and effect playback uses the header end frame and material-alpha tracks. The Visual Effects page exposes particle emitters, stages, every curve key, and sampled key interpolation. Animation playback now draws active particle stages with their texture, material colour, alpha, scale, rotation, and integrated velocity curves; camera-facing cards stand in for the game's point, line, and textured stage geometry. Meshless effects are fitted to the first visible particle frame. The preview does not reproduce every GX TEV, blend, depth, lighting, or billboard branch. glTF can preserve some FE9 extras, but glTF and the preview are not a proof of game-equivalent rendering.

For visual closure, compare particle position accumulation, stage geometry, material/GX state, and billboard transforms against captured game frames. Resolve the remaining bytes against engine readers or runtime watchpoints, then rerun coverage; do not promote corpus correlations to decoded semantics alone.
