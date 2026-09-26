# Known bugs

Open defects in the app that are confirmed but not yet fixed. Remove an entry once it is fixed.

## Script global declarations do not reserve storage

- **Where:** `fe_modding/formats/cmb/compiler.py`, `_ModuleCompiler.run()`.
- **What:** `global name @ slot` contributes to name resolution, but the generated header preserves the base file's global count or defaults to zero; declarations do not increase it.
- **Impact:** a new global declaration can compile without reserving corresponding runtime storage. Existing global-table indices must not be treated as free space.
- **Workaround:** preserve established global use; use registered event flags for ordinary event state. New global allocation needs an explicit engine-wide allocation design.

## Some existing edited CMB files do not round-trip byte-identically

- **Where:** `fe_modding/formats/cmb/binary.py`, binary read/write preservation.
- **Observed:** the current project's `C90.cmb` (7,935 bytes) stores its function-table offset as 2,635; read/write emits 2,636 and changes the file bytes. The separately backed-up `originals/files/Scripts/C01.cmb` also fails an untouched binary round-trip. These files' provenance as pristine retail data is not established.
- **Scope:** the other 43 `.cmb` files in the current extracted project pass both binary and decompile/compile round-trips. The optional corpus test fails when run on all 44 project files because of `C90.cmb`.
- **Impact:** do not promise byte-identical preservation for arbitrary previously edited files. Runtime impact of the normalized output has not been tested; the precise preservation defect still needs investigation.
- **Workaround:** check untouched round-trip results before editing and keep the original file. No game files were changed during this documentation check.

## THP encoder puts all leftover audio in the last frame

- **Where:** `fe_modding/formats/thp.py`, `_compute_audio_chunks()`.
- **What:** every frame except the last gets about `sample_rate / fps` samples, rounded down to a multiple of 14. The last frame gets *all* remaining samples. When the source audio runs longer than the frames account for, that last frame becomes oversized, and the header's `audioMaxSamples` (offset 0x0C) grows with it.
- **Observed:** a 10,670-frame replacement `Movie/opening.thp` had 4,337 samples in its last frame and `audioMaxSamples = 4337`. The retail `opening.thp` never goes above 1,078 samples per frame, last frame included.
- **Impact:** not yet seen to crash anything. The game's THP player sizes its audio buffers from `audioMaxSamples`, so the file asks for about 4× the retail audio buffer memory. This is a plausible cause of allocation failures, and the file doesn't match how THPConv lays out audio.
- **Fix direction:** make the audio exactly as long as the video (`num_frames * sample_rate / fps`) by trimming or padding the PCM before chunking, so that no frame goes much above the normal per-frame count.

## STM writer stores a partial final ADPCM frame

- **Where:** `fe_modding/formats/stm.py`, `write_stm()`.
- **What:** the per-channel data size at header 0x08 (repeated at 0x10 and 0x14) is `bytes_for_adpcm_samples(num_samples)`. When the sample count isn't a multiple of 14, this size doesn't end on an 8-byte ADPCM frame boundary.
- **Observed:** an imported `Sound/ex_32k.stm` (4,984,704 samples) has data size `0x2b7693`, which is an odd byte count. All 81 retail tracks have data sizes that are multiples of 8, and all looping retail tracks have sizes that are multiples of 32.
- **Impact:** not yet tested in game. The music streamer reads the track in chunks sized from this field, and a size that isn't block-aligned may produce misaligned DVD/ARAM transfers or cut the last block short when the track plays.
- **Fix direction:** pad the PCM with silence up to a multiple of 14 samples (the retail looping tracks suggest padding to a multiple of 56 samples, so the size is 32-byte aligned) before encoding.

## Oversized Path of Radiance builds are only warned about

- **Where:** `fe_modding/project.py`, `ModProject.build()`, and `fe_modding/formats/gcdisc.py`.
- **What:** if the extracted data is larger than a GameCube disc (1,459,978,240 bytes), the build is still written and the app shows a warning.
- **Impact:** such images run in Dolphin, but not on real hardware or in loaders that enforce the disc size. Large replacement videos are the usual cause.
