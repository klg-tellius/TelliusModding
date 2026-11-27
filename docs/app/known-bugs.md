# Known bugs

Open defects in the app that are confirmed but not yet fixed. Remove an entry once it is fixed.

## Oversized Path of Radiance builds are only warned about

- **Where:** `fe_modding/project.py`, `ModProject.build()`, and `fe_modding/formats/gcdisc.py`.
- **What:** if the extracted data is larger than a GameCube disc (1,459,978,240 bytes), the build is still written and the app shows a warning.
- **Impact:** such images run in Dolphin, but not on real hardware or in loaders that enforce the disc size. Large replacement videos are the usual cause.
