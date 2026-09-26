# Item icons, skill icons and weapon models

## Icons: `window/icon.tpl`

The game's item and skill icons are one texture, `window/icon.tpl`. Path of Radiance also bundles a copy in `system.cmp`; that copy is the one the game reads, so an edited sheet must be written into it (the app's build does this).

The file holds two C8 (256-colour palette) images, each cut into a grid 32 cells wide:

| Image | Size | Cell | Contents |
|---|---|---|---|
| 0 | 768 x 216 | 24 x 24 | menu glyphs and buttons (cells 0-95), then the item icons from cell 96 |
| 1 | 1024 x 96 | 32 x 32 | 46 skill icons, blank frames, then status and unit-type badges |

**Item icons.** An item record's `icon` byte (`FE8Data.bin` item `+0x49`) is drawn by the item-list rows as glyph `icon + 0x61`, which is cell `96 + icon` of image 0. Icon 0 (Iron Sword) is the first cell of the fourth row; icon 186 (the coin) is cell 282. Several items can share a number: the `_KING` beaks use their base beak's icon. Confirmed on every vanilla item.

**Skill icons.** A skill record's byte `0x19` is its icon. The skill-list rows (`skill_list_draw_row_a`/`_b`) hand it to the icon renderer; icon `n` is cell `n - 1` of image 1, and 0 draws nothing. The 51 nonzero values are exactly 1-46. Skills with icon 0 are also left out of the lists of skills a unit can learn. Examples: Chant is the note, Steal the pouch, Counter the crossed arrows, Wing Shield the wing.

Each image has one palette shared by all its cells, so a new icon has to fit the colours left in it.

## Two more skill-record fields

- `0x1A` is the **capacity cost**. The skill-list rows print it and grey the skill out when it is more than the class's skill capacity (class `+0x40`) minus the capacity the unit's skills already use. Paragon costs 15, Counter 10, Nihil 5.
- `0x14` is a pointer to the skill's **effect** (`EID_`), set on 23 skills: Sol plays `EID_SP_SUN`, Counter `EID_COUNTER`, Vantage `EID_MACHIBUSE`, the triangle attack `EID_TRIATTACK`.

## Weapon models: `xwp/`

In battle, the game takes the equipped item's ID without `IID_` (`IRONSWORD`) and opens the table `xwp/IRONSWORD.dbx` inside `zdbx.cmp`. That table's `Model` block names the model: `folder xwp/IRONSWORD`, `model IRONSWORD`, so the pack is `xwp/ironsword/ironsword.cmp` (disc paths are case-insensitive). The LZ10 pack holds `<name>.g` (skeleton), `<name>.gs` (mesh) and `<name>.tpl` (texture), and no animation. Its `Weapon` block gives the kind (0 sword, 3 bow, 4 magic, 9 arrow) and whether it is a missile; a tome's table has only that block and an effect.

If the table is missing, no weapon is made: the debug log says "no weapon, so bare hands". In vanilla this is the case for the Devil Axe, which has a model folder but no table, and for the four ballistae.

The class-change scene and the forge preview build their paths straight from the name: `xwp/<name>/<name>.cmp`, and `xwp/forge/<name>_b.cmp` for the forged look.

There are 74 weapon folders and 16 forge models. Every sword, lance, axe, bow and knife has one except the four ballistae (Longarch, Ironarch, Killerarch, Onager). Seven folders belong to no item: `bronzesword`, `bronzeaxe`, `rapier`, `lightningsw`, `swd1`, `swd2` and `arrow`.

Bows are drawn through skinned (composite) shapes, so the string can bend. Every other weapon is rigid, with shapes on up to four bones.

Consequence for modding: a new item ID only gets a battle model if `zdbx.cmp` has an `xwp/<NAME>.dbx` table for it; renaming an item's ID changes which table, and so which model, it uses.
