# Known bugs

Open defects in the app that are confirmed but not yet fixed. Remove an entry once it is fixed.

## Oversized Path of Radiance builds are only warned about

- **Where:** `fe_modding/project.py`, `ModProject.build()`, and `fe_modding/formats/gcdisc.py`.
- **What:** if the extracted data is larger than a GameCube disc (1,459,978,240 bytes), the build is still written and the app shows a warning.
- **Impact:** such images run in Dolphin, but not on real hardware or in loaders that enforce the disc size. Large replacement videos are the usual cause.

## Radiant Dawn chapter weather shows no change

- **Where:** ChapterData `weather` (+0x9C), Chapter data page.
- **Observed in game** (W1r/W2r/W3r, 2026-11-18/19, and the parity run of 2026-10-28): the Prologue set from cloudy (`曇り`) to snow (`雪`), night (`夜`) or sandstorm (`砂嵐`) looks like retail at the first player phase (0.0-0.3% of the map differs). What the field drives still needs a trace.

