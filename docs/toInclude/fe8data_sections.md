# FE8Data.bin: every section placed

Summary for the documentation (full tables in `research/FE8DATA_NOTES.md` §4.1–4.11).

- The file is a labeled-section container with 13 named sections; each table symbol points at a record count. Skills start at `0xE398`, not `0xE394` (the count word).
- **Character record**: `0x18` is a personal weapon-rank string; the three skills are at `0x1C`/`0x20`/`0x24`; `0x32` biorhythm pattern (0 = random), `0x35` biorhythm phase.
- **Class record**: `0x10` innate laguz weapon, `0x3C`/`0x3D` build and weight, `0x40` skill capacity, `0x41` fog-of-war vision (Torch adds to it), `0x5C`–`0x63` signed growth modifiers.
- **Skill record**: `0x20` → the scroll item that teaches it (mastery skills: Occult scroll `IID_ESOTERIC`); `0x24` → restriction list of `0x1C` labels (Astra → Swordmasters, Aether → Hero/Hero_G, Keen Ear → Ulki…).
- **GameData**: seven difficulty rows (EXP constants, laguz growth bonus, class critical bonus).
- **ChapterData**: map, script, message file, BGM, objective texts with Hard/Maniac overrides, preparation and conversation backgrounds, class-change scene map and sky, trial-map A–D grade thresholds (turns, losses, score).
- **GroupData**: the 31 army-group name keys (`MG_`).
- **BattleTerrData**: for each map, the battle-scene map shown per terrain type (row `Map6` is the default). **BattleSkyData**: the sky per weather id.
- **DatabaseHead**: build time `2005/06/29 10:11:21`, author 金子 (Kaneko).
- **Container**: a HAL sysdolphin archive (`HSDArc`, as in Super Smash Bros. Melee). Header `+0x10` import count, `+0x14` unused, `+0x18`–`+0x1F` written only in RAM (the `HSDArc` relocated stamp and a symbols-registered flag).
- **Character record**: `0x30` is the recruitment order, the unit lists' default sort; `0x34` the starting laguz transform gauge (16 on Giffca, Lethe, Tibarn, Janaff, Naesala; 10 on Ranulf; 5 on Mordecai, Ena, Nasir, Ulki).
- **ChapterData** `0x3D`–`0x40`: bonus levels for auto-levelled enemies, one per difficulty (vanilla 0, 0, 2, 2 on story chapters); `0x00` the chapter title. The trial score grade counts the player army's kills on the map (unit `+0x22C`, reset at deployment; `+0x22A` is lifetime kills, shown as wins on the ending roster).
- **Skill record**: `0x08` the name key; `0x1B` is set on exactly the skills that have a scroll but the game never reads it.
- No byte is left undecoded. Reserved (never read by the game, values documented): header `+0x14`, `DatabaseHead` word 0, character `0x08`, class `0x3F` and `0x43` (a movement category: foot, armour, cavalry, pegasus, wyvern, beast, dragon, bird), skill `0x1B` and `0x1D`–`0x1F`. The class `MJID_` name key is the only field still unconfirmed.
