# Unit deployment (`dispos.cmp`)

Summary for the documentation: how a chapter decides which units appear, where, and how strong. Full tables: `research/CHAPTER_DATA_NOTES.md` §5.1; code path: `research/MAIN_DOL_NOTES.md`, "Reinforcement deployment".

## The four files

Each map folder (`zmap/bmapNN/`) has a `dispos.cmp` holding four files: `dispos_c.bin`, `dispos_n.bin`, `dispos_h.bin` and `dispos_m.bin`. The game loads all four with the map. Each holds named groups of units ("sections"): `bmap02_mikata_c` (the player army), `bmap02_first_n` (the enemies present at the start), `bmap02_z01_n` (a reinforcement wave)... The chapter's event script deploys a group by its name:

- a `_c` group is called directly, so it appears on every difficulty;
- the `_n`, `_h` and `_m` versions of a group are passed together to a helper that picks one by difficulty.

A group placed in a file but never named by the script never appears.

## One unit (108 bytes)

| What | Notes |
|---|---|
| Character, class | Names such as `PID_OSCAR`, `JID_LANCEKNIGHT`; no class means the character's own |
| Items (up to 8) and a flag per item | The flag is set on the items a boss drops |
| Skills (up to 5) | Added to the character's and the class's own |
| Stat bonuses | Eight signed numbers (HP, Str, Mag, Skl, Spd, Lck, Def, Res) added to the stats; Chapter 1's boss Zawanar has HP −11, Str +6, Skl +1, Spd −2, Def +3 |
| Laguz gauge | A starting value for the transformation gauge |
| AI | Attack, move and heal behaviours (`SEQ_…`) and a movement AI (`MTYPE_…`); player units use the "none" behaviours |
| Spawn tile, destination tile | The unit appears on the first and walks to the second (the nearest free tile). They are the same for units that stand still; the Prologue's Ike appears at (6, 7) and walks to (3, 9) |
| Level | If the class is the character's own and the character's base level is higher, the base level is used |
| Army | 0 player, 1 enemy, 2 ally/other |
| Flags | `0x01` autolevel (the unit grows from its base stats to its level with the class's growth rates); `0x02` hold position (the AI never moves the unit; it still attacks or heals from its tile); `0x04` commander of its group (Ike, each chapter's boss); `0x08` a reinforcement appears even if that character is not already in play; `0x40` the unit cannot step onto bridge-cover tiles (terrain 55). Every vanilla unit has `0x40` except fliers and a few cutscene actors |
| AI turn order | During the enemy phase, units with a lower number act first. 0 on player units; vanilla enemies use 0–81, with higher numbers on later waves and bosses |

Tiles use the map's full grid (border included), the same grid as the map's terrain types and props.

## Groups

Each group of units also names its **army**: the last byte of the group's header is an index into the list of army names in `FE8Data.bin` (1 Crimean Army, 2 Daein Army, 5 Bandits, 6 Pirates, 10 Greil Mercenaries, 15 Duke Tanas's army, 17 Kilvas Army… 30 entries). Every unit the group deploys joins that army. The map's army list sorts units by it, and the unit flagged as commander is that army's leader. A leader with the Charisma skill gives units of its own army within 3 tiles +5 to two combat values, and an enemy with Horror within 3 tiles takes 5 off two. Scripts can read and change a unit's army (`UnitGet`/`UnitSet` field 38).

## The file around the units

A header (length, sizes, counts), the groups one after another, a pool of the name strings the units refer to, a list of every place that refers to a name, then the group names. Because names are looked up by their text, a unit can use any character, class or item, including ones the chapter never used.

## Still open

Flag `0x10` (never used by the game) enables an extra AI action route whose effect is not known, and which battle values the Charisma and Horror bonuses change is not traced.
