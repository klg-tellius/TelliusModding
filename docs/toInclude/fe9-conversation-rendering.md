# FE9 conversation renderer documentation integration

The authoritative topical specification is
[research/CONVERSATION_RENDERING.md](https://klg-tellius.github.io/TelliusModding/#/message-format).
It includes native coordinates, real file structures, engine addresses, command
semantics and a reproducible ten-screenshot validation manifest.

Replace previous claims that alpha-hole placement or guessed face coordinates
represent engine behavior. FE9 now uses real facedata records, fixed texture
indices, depth ordering, window descriptors and GCF glyphs. `$FS` selects a mouth
variant, `$cNname` loads a face, `$MC/$MD` control mouth movement, `$H` yields and
resumes, and `$wN` is 2^N frames. Large/small FIDs remain distinct.

Preview controls default to auto-advance, reset newly selected messages to the
first frame, and highlight the current source position without modifying text.
Chapter 2 ED continuations inherit their real background layout and large faces
from the CMB's preceding TalkEvent, when all possible paths agree. The initial
context panel remains available for ambiguous/event-owned context.

Validation: 263 distinct corpus face references; 261 concrete identities compose
successfully, ME/LME require actor context. All twelve c02 ED entries and their
wait checkpoints render without resource/layout diagnostics. New tests cover
native-format fixtures, command ordering, waits, expressions, seeking, real
assets and GUI reset/continuation. Full-suite testing also exposes an unrelated
existing model-viewer `_LoadedTexture.convert` error; do not report that suite
as wholly passing. Do not describe FE10 or emulator-level animation timing as
validated by this work; see the specification's remaining limits.
