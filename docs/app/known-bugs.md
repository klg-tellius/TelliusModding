# Known bugs

Open defects in the app that are confirmed but not yet fixed. Remove an entry once it is fixed.

## Oversized Path of Radiance builds are only warned about

- **Where:** `fe_modding/project.py`, `ModProject.build()`, and `fe_modding/formats/gcdisc.py`.
- **What:** if the extracted data is larger than a GameCube disc (1,459,978,240 bytes), the build is still written and the app shows a warning.
- **Impact:** such images run in Dolphin, but not on real hardware or in loaders that enforce the disc size. Large replacement videos are the usual cause.

## A sword made into a fire wave blade ends its fight with a magenta flash

- **Where:** Battle Weapons (`xwp/<NAME>.dbx`) on Path of Radiance.
- **Observed in game** (E1/E1c/E1k/E1s, 2026-11-24): the Iron Sword's table set like the Sonic Sword's but in fire (`kind` 8, `missile` 2, `EID_K_FIRE2` / `EID_K_FIRE2_WP`) with range 2 sends a fire wave from two tiles and deals damage. As the fight ends, the screen goes flat magenta for about 2.5 seconds (11 frames at four a second; longer after a critical kill), then the map comes back. The retail Sonic Sword attacking and killing from range has no such flash. Not traced: the Iron Sword's model may lack something the wave blade's end needs, or the fire wave wants an effect variant the wind one has.
- **Related, now warned about:** a weapon that reaches 2 tiles with a melee table (`missile` 0) and no gale effect turns the screen magenta at any ranged attack, for good; the project check reports it.
