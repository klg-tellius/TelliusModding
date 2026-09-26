# Item record (`FE8Data.bin` ItemData) — fully decoded

Every one of the 96 bytes of an item record is now known. The game's loader `build_item_data_table` (`0x80019FC4`) reads each record field by field into a 72-byte runtime item; checked against all 189 vanilla records.

## Layout

| Offset | Field | Meaning |
|---|---|---|
| `0x00` | IID | Item ID label; the runtime item is registered under it |
| `0x04` | MIID | Name key |
| `0x08` | MH_I | Description key |
| `0x0C` | weapon type token | `sword lance axe bow flame thunder wind rod knife fang item acc` (0–11): rank trained, who can equip |
| `0x10` | attack type token | Same tokens; `flame thunder wind rod` attack with Mag against Res (Runesword `sword`/`rod`, Flame Lance `lance`/`flame`) |
| `0x14` | rank token | `E D C B A S` → min weapon EXP 1/31/71/121/181/251; `N` or null → none |
| `0x18`–`0x2C` | 6 property tokens | OR-ed into two flag words (36 tokens: `twice` brave, `infinity` unbreakable, `crit0`, `poison`, `resire`, `magsw`, user locks `eqA`–`eqD`, `heroonly`…); unknown tokens (`areaattack`, `absolutehit` on the Onager) are ignored |
| `0x30`, `0x34` | 2 category tokens | What the weapon is effective against (`fly` bows/wind, `beast` fire, `dragon` thunder, `armor`, `knight`, `alize`…) plus `doorbreak` on axes; same tokens/bits classes use |
| `0x38`, `0x3C` | EID labels | Use/spell effect, weapon effect (`EID_..._WP`) |
| `0x40` | u16 cost | Price per use (shop price = cost × uses) |
| `0x42`–`0x48` | uses, might, hit, weight, crit, min range, max range | Max range 255 = Mag/2 |
| `0x49` | icon | Item icon (list rows draw glyph icon + 0x61) |
| `0x4A` | weapon EXP | Weapon EXP per use |
| `0x4B`–`0x54` | stat bonuses (signed) | HP Str Mag Skl Spd Lck Def Res Mov Con while equipped; permanent on stat boosters |
| `0x55`–`0x5C` | growth modifiers (signed) | Growth-rate changes while equipped |
| `0x5D` | trail colour | One of 9 RGBA attack-trail colours (table at `0x80368D38`); forged weapons use their forge colour |
| `0x5E`–`0x5F` | padding | Never read |

Full per-token flag bits and runtime offsets: `research/FE8DATA_NOTES.md` §4.3. Loader walk-through: `research/MAIN_DOL_NOTES.md`, "ItemData loader".

## Corrections to earlier documentation

- `0x49` is the icon number, not a "rank tier" — the rank is the token at `0x14`.
- Weight (`0x45`) is confirmed (read by `get_item_weight`).
- The "effectiveness flags around `0x55`–`0x5C`" are growth modifiers; effectiveness is the two category tokens at `0x30`/`0x34`.

## Open

- What `sealcrit`, `stormsw`, `weakA`, `valuable`, `JH`, `noneart`, `flutter` change in play (only their vanilla carriers are known).
