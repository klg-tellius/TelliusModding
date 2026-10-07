"""Character, class, and item/weapon data (``FE8Data.bin``) - the tables that
drive unit stats, class definitions, and weapon/item stats. "FE8" is not a
typo: numerous internal Path of Radiance filenames use the FE8 prefix,
suggesting the game was originally slated to be the 8th mainline entry.

Unlike every other container in this package, ``FE8Data.bin`` sits directly
under ``extracted/files/`` uncompressed and outside any ``pack`` archive - no
``lz10``/``pak`` layer to unwrap, just read/patch/write the file directly.

This module has no prior reverse-engineering to build on (checked: none of
the user's old ``FE9/tools`` scripts touch this file) and no complete public
documentation either. What's here was reverse-engineered by a combination of:
a community forum thread (feuniverse.us, "[FE9] File structure notes") that
correctly identified the file's existence, the character record size (0x54
bytes) and its first several field offsets, and the class/item record sizes
(0x64 / 0x60 bytes) - and independent verification directly against a real
US-version file, which was needed anyway since the thread's byte offsets are
for the PAL version and don't transfer directly (different table start
addresses; only the exact IDENTICAL number 0x9E94 recurring at the same
in-context position gave a strong signal the item table's *relative* layout
carried over even though absolute offsets don't).

Verification method: every field below was confirmed structurally rather
than assumed - resolving a record's pointer fields back through the file's
own PID_/JID_/IID_/FID_/SID_/AID_ label pool and checking the result names
real Path of Radiance content (record 0 of the character table is
``PID_IKE``/``FID_IKE``/``JID_RANGER`` - Ike's known internal early-game
class name; record 1 is ``PID_TIAMAT``, Titania's original Japanese dev name,
the same un-translated-label pattern already seen in :mod:`rect`; the class
table's record 0, ``JID_RANGER``, has a "promotes to" field pointing at
``JID_HERO``, Ike's real promotion; the item table includes ``IID_ALONDITE``
and ``IID_RAGNELL``, Ike's two legendary swords). Item stat fields
(might/uses/hit/weight/rank) were confirmed by differencing Iron/Steel/Silver
Sword records and checking the bytes move in the direction real Fire Emblem
weapon tiers move (might rises 5/8/13, uses falls 46/35/25 - better weapons
break sooner - and a rank-tier byte rises 0/3/4).

A class record's movement/stat-cap/base-stat fields were found the same
structural way, using a different signal: every class's ``promotes_to``
pointer turned out to link BOTH directions (an unpromoted class points at its
promoted counterpart and vice versa, not a one-way pointer), which turns the
whole class table into 108 same-species pairs - and diffing every pair
against its counterpart shows movement (byte 0x3E) increasing by exactly 1
and the first stat-cap byte (0x4C, HP cap) jumping from 40 to 60 on literally
every human-class pair with zero exceptions (checked with a script, not by
eye) - the single well-known real Fire Emblem promotion bonus, found from
pure structure with no game knowledge assumed going in. Laguz/dragon/bird
classes gain movement the same way but keep the same HP cap across their
transformation tier, which is *also* correct (Tellius laguz transformation
isn't the same system as human promotion) rather than a counter-example.
The class stat blocks follow the engine's loader (``build_job_data_table``,
which copies file bytes 0x3C-0x5B one to one): 0x44-0x4B class base stats
(the HP getter adds class +0x44 to the unit's HP), 0x4C-0x53 caps, 0x54-0x5B
class growth rates (90 HP on the Ranger, 140 on the laguz birds). The loader
skips the Luck bytes of the bases and caps (0x49, 0x51). Byte 0x42 is the
movement type: the movement-cost grid reads terrain stats block byte
``8 + movement_type`` (``init_map_movement_cost_grid``), see
``MOVEMENT_TYPE_NAMES``.

**Character fixed_growth_start** (0x49-0x50): the starting accumulators of
the fixed ("Fraction") level-up mode, STAT_NAMES order - copied to the
unit's accumulators at deployment and consumed by
``apply_fixed_growth_level_up`` (FE8DATA_NOTES.md §4.1). A community
editor names the block ``supportgrowth``; it is not support data.

A related, ruled-out lead: cp_data.bin ("CP" = computer player, not support
"Compatibility Points") is the AI's data - scripts, movement weights, heal
thresholds, the thief steal list - and holds no support data
(research/CP_DATA_NOTES.md, formats/cp_data.py).

**Class weapon ranks and innate skills** (a follow-up pass, resolving two
items this docstring used to list as undecoded). `ClassEntry.weapon_ranks`
(field offset 0x14) is a 9-character string, one character per weapon
type in WEAPON_TYPE_NAMES order - confirmed, not just plausible, by
checking classes with a genuinely single weapon specialty: JID_FIGHTER
resolves to "--D------" (only position 2 set) and JID_ARCHER to
"---D-----" (only position 3), and the three element-specialist mage
subclasses pin the anima positions exactly - JID_MAGE_F/MAGE_T/MAGE_W
resolve to "----D----"/"-----D---"/"------D--" respectively (Fire/
Thunder/Wind, one D each, no ambiguity). Letters follow the standard FE
E/D/C/B/A/S order (confirmed by JID_BKNIGHT - the Black Knight, a known
elite swordsman - resolving to "SC-------", the only class sampled with
an S rank); a few classes (JID_PALADIN_S, JID_SAGE) show `*` instead of a
letter at one or more positions, read as "usable without a fixed rank
requirement" rather than a specific grade. Position 7 ("Staff" here) is
the one weaker link in this chain: Priest/Bishop/Valkyrie all carry a
rank there, consistent with Tellius's staff-healer archetype, but nothing
pins it down as confidently as positions 0-6; position 8 ("Light") was
never seen as anything but the `*` wildcard, so it's the single
lowest-confidence entry in WEAPON_TYPE_NAMES. Checked against
ItemEntry.rank on the chance the two were the same small enum - they are
NOT: real sword items span 0 (Iron) to 17 (Alondite, Ike's legendary
personal sword), far more granular than the letter grade's 6 values, so
item.rank is confirmed to be a different, more granular field, not
resolved further here. class.skills (offsets 0x18-0x2C, up to 5 SID_
pointers) are class-innate skills, granted automatically to every unit of
that class - confirmed the same way the Chant investigation above ruled
things out: JID_HERON/JID_BIRD_HE and their promotions resolve to
`SID_ANIMALIZE`/`SID_LYCANTHROPE`/`SID_FLY`/`SID_HIGHER` here, all
laguz-transformation traits, not player-visible "learned" skills. Neither
field has write support yet: weapon_ranks' pointer is shared across
multiple classes with an identical rank curve (JID_SWORDER and
JID_SWORDER/F both point at the exact same string), so patching it
in-place would silently change every class sharing that pointer - a real
footgun that needs its own guard before this is safe to expose as
editable.

**Character skills and weapon ranks**: ``build_person_data_table`` reads
the record word by word. 0x18 goes through ``map_byte_values_from_table``
into the unit's weapon-rank seed bytes - a 9-character rank string like the
class one (PID_IKE "D--------", PID_TIAMAT "-CA------") - and 0x1C, 0x20
and 0x24 through ``set_skill_flag_by_name``: those three are the personal
skills (104, 34 and 14 of the 340 records set them). The skill slots were
first read one word early, as 0x18/0x1C/0x20, which put the rank string in
"slot 0" and hid the third skill. Then 0x30 (u16 roster order -> runtime
+0x5A), 0x32 (u16 biorhythm pattern, 0 = random 0-365), 0x34 (starting
transform gauge -> runtime +0x56), 0x35 (biorhythm phase, 0 = 30), level,
build, weight and the stat blocks; the cursor is then aligned to 4, skipping
0x51-0x53. The roster order (1 = Ike, 2 = Titania, 3 = Oscar... in
recruitment order) is the unit lists' default sort key: every list-column
getter returns ``-order`` for column 0. The transform gauge (0/5/10/16, set
only on laguz) is copied into the unit's gauge (+0x19C) by
``initialize_transform_gauge_from_unit_flags`` when the unit has
SID_ANIMALIZE and not SID_LYCANTHROPE (which starts at the full 20). 0x08 is
null in every record and nothing reads its runtime copy.
Within a class record: 0x2C/0x30/0x34 resolve to plain (unprefixed)
labels like "human", "armor", "fly" that the loader turns into equipment and
ability flags; 0x38 is the class's animation ID; 0x3C/0x3D build and weight,
0x3E movement, 0x40 skill capacity, 0x41 vision, 0x42 movement type, 0x5C-0x63
growth modifiers. 0x3F (1-4: 3 on most classes, 4 on the transformed
beast/dragon/bird classes, 1-2 on citizens, healers, thieves and herons) and
0x43 (a movement category: 0 foot, 0x10 armour and heavy foot, 0x12
cavalry, 0x13 pegasus, 0x14 wyvern, 0x20 valkyrie, 0x60 beast, 0x70 dragon,
0x80 bird) are copied by the loader, but no load in main.dol reads them.
Table lengths (340 characters, 115 classes) come from each section's count
word.

**Container header**: FE8Data.bin is a HAL sysdolphin archive, loaded by
``load_relocatable_resource`` (the executable's signature string is
"HSDArc"). The 0x20-byte header holds the file size, the data size, the
relocation (pointer list) count, the export (symbol) count, an import count
at 0x10 (0 here), an unread word at 0x14, and 8 bytes the loader writes in
RAM: the 7-byte "HSDArc" stamp that marks the pointers as relocated
(0x18-0x1E) and a symbols-registered flag (0x1F). All zero on disc.

**Item record** (every one of the 0x60 bytes, from the engine's loader
``build_item_data_table`` at 0x80019FC4, which copies the record into a
0x48-byte runtime item; checked against all 189 vanilla records):

- 0x00/0x04/0x08: IID, name key (MIID) and description key (MH_I).
- 0x0C/0x10: two weapon-type *token strings* ("sword", "lance", "axe",
  "bow", "flame", "thunder", "wind", "rod", "knife", "fang", "item",
  "acc"), decoded by ``decode_item_weapon_type_token`` into runtime +0x12
  (the type ranks, class usability and default capability flags use) and
  +0x13 (the attack type: 4-7, the magic types, make the forecast use
  Mag/Res - the Runesword is "sword"/"rod", the Flame Lance "lance"/"flame").
- 0x14: the rank token "E"/"D"/"C"/"B"/"A"/"S" (or "N" / null: none),
  turned into the minimum weapon EXP 1/31/71/121/181/251 (0 for none).
- 0x18-0x2C: six property token strings ("infinity", "twice", "crit0",
  ...), each OR-ed into two flag words by ``apply_item_property_flag_token``
  (see ITEM_PROPERTY_TOKENS). Unknown tokens are ignored - vanilla's
  "areaattack"/"absolutehit" on the Onager are never matched.
- 0x30/0x34: two category tokens ("fly", "armor", "beast", "doorbreak",
  ...) OR-ed into the item's 16-bit category mask by the same
  ``apply_unit_category_flag_token`` the class loader uses: every bow and
  wind tome says "fly", fire says "beast", thunder "dragon", every axe
  "doorbreak" - what the weapon is effective against.
- 0x38/0x3C: EID_ effect labels - the use/spell effect (EID_FIRE, EID_LIVE)
  and a weapon effect (EID_FIRE2_WP on the "2" tomes).
- 0x40: u16 cost per use (Iron Sword 10 x 46 uses = 460 gold).
- 0x42-0x48: uses, might, hit, weight, critical, minimum and maximum range
  (255 = Mag/2, the long-range staves).
- 0x49: icon number (the _KING beaks reuse their base beak's icon).
- 0x4A: weapon EXP per use (1-2 for weapons, 3-8 for staves).
- 0x4B-0x54: signed stat bonuses HP, Str, Mag, Skl, Spd, Lck, Def, Res,
  Mov, Con (build) - applied while equipped (the stat getters add the
  equipped weapon's and item's bytes) and given permanently by the stat
  boosters (Seraph Robe +7 HP, Boots +2 Mov, Body Ring +2 Con).
- 0x55-0x5C: signed growth modifiers in STAT_NAMES order (Iron Sword -5
  Str, +5 Skl, +5 Spd, -5 Res; Knight Ward +30 Spd).
- 0x5D: attack trail colour, an index into a 9-entry RGBA table at
  0x80368D38 (a forged weapon's colour comes from its forge record).
- 0x5E-0x5F: alignment padding; the loader skips them.

Editing: like dispo.py, patch_*_field() overwrites specific bytes in a copy
of the file's own bytes - no structural change, so nothing else shifts.
Pointer fields can only be repointed at a label that already exists
somewhere in this same file (see label_index_by_prefix()); introducing a
brand new label string isn't supported, same limitation and same reason as
dispo.py.

**Skill table**: 98 records of 0x28 bytes. The ``SkillData`` symbol points
at the count word (98); the records start 4 bytes later, at
SKILL_TABLE_OFFSET, where each record's own ``SID_`` symbol points. (The
table was first read 4 bytes early, which made every record's first word
the previous record's last one and attached each restriction list to the
following skill.) Each record:

- 0x00: SID_ pointer - the skill's internal ID, e.g. "SID_COUNTER".
- 0x04: pointer to the untranslated Shift-JIS Japanese name.
- 0x08: MSID_ pointer - the menu name key.
- 0x0C / 0x10: the short/long help-text keys, "Mess_Help_skill_<Name>" and
  "Mess_Help2_skill_<Name>" (see read_skill_descriptions()). 57 records,
  the player-facing skills, have them; the 41 engine/unit-type flags
  (FEMALE, FLY, BOSS, the EQUIP* permissions...) have null pointers.
- 0x14: pointer to an EID_ effect (``effect``), set on 23 skills: the
  effect played when it triggers (SID_SUNTRICK -> EID_SP_SUN, SID_COUNTER
  -> EID_COUNTER); ``lookup_status_effect_by_flag`` also reads it.
- 0x18: the record's own table index (0-97).
- 0x19-0x1B: the three "params" bytes, below: the icon, the capacity
  cost and a has-a-scroll flag nothing reads.
- 0x1C: number of labels in the restriction list at 0x24.
- 0x1D-0x1F: zero, except 0x1F = 5 on SID_TELEGNOSIS and SID_BIGEAR; no
  load in main.dol reads them.
- 0x20: pointer to a one-entry list holding the IID_ of the scroll item
  that teaches the skill (IID_COUNTER, IID_GAMBLE...); every class mastery
  skill points at IID_ESOTERIC, the Occult scroll. 0 when no item teaches it.
- 0x24: pointer to the restriction list, 0x1C labels long: the PID_/JID_
  labels the skill is exclusive to. SID_STARTRICK (Astra) ->
  JID_SWORDMASTER(/F), SID_SUNTRICK (Sol) -> the paladins and Titania,
  SID_MOONTRICK (Luna) -> halberdiers and the general, SID_SUNMOON
  (Aether) -> JID_HERO/JID_HERO_G, SID_BIGEAR -> PID_VULCI (Ulki),
  SID_TELEGNOSIS -> PID_JANAFF, SID_REINFORCEMENTS -> PID_TANIS (Tanith),
  SID_WLUPTOS (Occult's own skill slot) -> sages and bishops.

The lists live between the skill records and ``DivineData``, each skill's
scroll entry followed by its restriction labels.

- `params[0]` (0x19): the skill's icon, CONFIRMED (engine): the skill-list
  rows (``skill_list_draw_row_a``/``_b``) draw it, icon n being cell n - 1
  of ``window/icon.tpl``'s second image (see icons.py). The nonzero values
  are exactly 1-46, one per icon; 0 means no icon, and the learnable-skill
  lists skip those skills.
- `params[1]` (0x1A): the capacity cost, CONFIRMED (engine): the same rows
  print it and grey the skill out when it is more than the unit's class
  capacity (class record 0x40) minus the capacity already used.
- `params[2]` (0x1B): 1 on exactly the 42 skills that have a scroll
  (0x20 non-null), 0 elsewhere - including Handi, EquipKnife, EquipLight,
  Steal and Goddess Bless, which have an icon but no scroll. No load in
  main.dol reads it (the skill-capacity screens decide what can be removed
  from the icon, the cost and the class skills), so changing it does
  nothing.

**read_skill_descriptions()** resolves a skill's help_key/help2_key to its
actual text. That text does NOT live in FE8Data.bin - confirmed end to end
against a real disc: files/system.cmp (LZ10-compressed, see lz10.py) is a
`pack` archive (pak.py) whose entries mirror several other top-level files
(oddly including another copy of FE8Data.bin itself - unexplained, flagged
for future investigation) plus `mess/common.m`, a message file in the exact
format message.py already parses for chapter dialogue (its header's
`filesize` field matches the extracted entry's length exactly, and
message.read_messages() parses it as 2530 clean messages). Looking up
"Mess_Help_skill_Counter" and "Mess_Help_skill_Gamble" in the parsed result
gives back the real, correct in-game skill descriptions ("In certain
instances, causes enemy to receive half of the damage it deals to this
unit." / "Halves this unit's chance to hit, but doubles its chance to land
a critical hit.") - about as strong a confirmation as this codebase's
reverse-engineering ever gets, short of an actual emulator screenshot.

**Chant stat choice** (chased down in a third follow-up pass). CHANTHP
through CHANTMDEF (table indices 25-32) have neither a restriction list nor
params, unlike every other "special mechanic" skill - so where's the
"which stat does this chant" data stored? Everywhere it plausibly could be
was checked and came up empty: no character record's 3 SID slots reference
any of the 8 variants (only the plain SID_CHANT - Rieusion/Reyson and two
other heron-related records carry it, nothing else), and no class record's
5 skill-pointer slots reference any variant either (JID_HERON/JID_BIRD_HE
and their promotions carry only laguz-transformation flags: Animalize,
Lycanthrope, Fly, Higher - never Chant at all). So the stat is never
*assigned* to anyone - only the ability to chant is (via plain SID_CHANT);
the specific stat must be chosen some other way, at runtime.

The resolution: the 8 variants' own table positions ARE the data. They sit
in one unbroken run (indices 25-32) immediately after the generic CHANT
(24), and their SID suffixes - HP, STR, MPOW, TECH, QUICK, LUCK, DEF, MDEF
- match STAT_NAMES (HP, Str, Mag, Skl, Spd, Lck, Def, Res) exactly, in
exact order, one variant per stat, no gaps. Each has an MSID_ (short menu
label) but, unlike the 57 genuinely player-facing skills, no help_key/
help2_key text - consistent with these being options inside an in-battle
"choose a stat to boost" quick-menu (built by the engine iterating
skill-table indices 25 through 32) rather than standalone learnable
skills that would show up, and need describing, in a skill list. Given
every other storage location was ruled out, `chant_stat_name()` computes
the stat from table position relative to SID_CHANTHP rather than reading
a field, since there is no field - this is the strongest inference the
data supports, not something verifiable against the game's executable or
an emulator, so it's kept as a separate best-effort helper rather than
folded into SkillEntry itself.

**Skill table leftovers**: params[2] and the `reserved` bytes at
0x1D-0x1F (zero except 0x1F = 5 on SID_TELEGNOSIS and SID_BIGEAR) are
never read by the game. Why system.cmp embeds a second copy of FE8Data.bin (and
several other top-level files) is also unexplained - if the two ever turn
out to diverge, or if a future editor's writes need to patch both, that's
the loose end to chase.

**Support data was NOT found in this pass.** The same "reverse-engineering
roadmap" plan that scoped this table also asked for the numeric
support-bonus tables (Hit/Avoid/etc. bonuses per support level). No
PID_-pair-keyed table turned up searching FE8Data.bin's own string-pool
region, and cp_data.bin (a plausible-sounding lead, given "CP") turned out to be the
computer player's AI data (research/CP_DATA_NOTES.md), not support data. Given
real Tellius support bonuses scale by *affinity pair* (a compact ~10x10
matrix), not by *character* pair, a useful next search would look for a
small fixed-size table keyed by affinity index rather than by PID_ label -
consistent with the original plan's own warning that support data would
need its own discovery pass "likely without a label-prefix shortcut to
lean on."
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Optional

HEADER_SIZE = 0x20

CHARACTER_TABLE_OFFSET = 0x30
CHARACTER_RECORD_SIZE = 0x54
CHARACTER_COUNT = 340

CLASS_TABLE_OFFSET = 0x6FC4
CLASS_RECORD_SIZE = 0x64
CLASS_COUNT = 115
CLASS_RANKS_OFFSET = 0x14  # pointer to the 9-character weapon rank string
CLASS_AID_OFFSET = 0x38  # base animation ID; get_unit_animation_id falls back to it (runtime +0x18)
CLASS_MOVE_OFFSET = 0x3E
CLASS_CAPS_OFFSET = 0x4C  # 8 bytes, STAT_NAMES order - see module docstring for confidence level
CLASS_MOVE_TYPE_OFFSET = 0x42  # movement type: the terrain cost column (stats block byte 8 + type)
CLASS_BASE_STAT_OFFSET = 0x44  # 8 bytes, STAT_NAMES order (the HP getter adds class +0x44)
CLASS_GROWTH_OFFSET = 0x54  # 8 bytes, STAT_NAMES order, class growth rates (build_job_data_table)

#: The 15 movement types (class byte 0x42), named after the classes using them;
#: several share identical cost columns (0/1/2/14 and 5/6/10/13 in vanilla).
MOVEMENT_TYPE_NAMES = (
    "Lord (Ranger, Hero)", "Infantry", "Promoted infantry", "Armor", "Promoted armor",
    "Mage, priest", "Sage, bishop", "Cavalier", "Paladin", "Flier", "Thief",
    "Bandit (crosses water)", "Beast laguz", "Dragon laguz", "Untransformed laguz, citizen",
)

ITEM_TABLE_OFFSET = 0x9CB4
ITEM_RECORD_SIZE = 0x60

#: Weapon-type tokens (item 0x0C / 0x10) in the engine's enum order, with a display name.
ITEM_WEAPON_TYPES = (
    ("sword", "Sword"), ("lance", "Lance"), ("axe", "Axe"), ("bow", "Bow"), ("flame", "Fire"),
    ("thunder", "Thunder"), ("wind", "Wind"), ("rod", "Light / staff"), ("knife", "Knife"),
    ("fang", "Laguz strike"), ("item", "Item"), ("acc", "Accessory"),
)
#: Item categories for listing items by kind: the weapon types, with "rod" split
#: the way derive_item_default_capability_flags does (might > 0: a Light tome, else a staff).
ITEM_CATEGORIES = ["Sword", "Lance", "Axe", "Bow", "Knife", "Fire", "Thunder", "Wind", "Light", "Staff",
                   "Laguz strike", "Item", "Accessory"]


def item_category(item: "ItemEntry") -> str:
    """The :data:`ITEM_CATEGORIES` name of an item, from its weapon type."""
    if item.weapon_type == "rod":
        return "Light" if item.might else "Staff"
    return dict(ITEM_WEAPON_TYPES).get(item.weapon_type or "", "Other")


CLASS_CATEGORIES = ["Unpromoted", "Promoted", "Laguz"]
#: Class category tokens only laguz classes carry.
LAGUZ_CLASS_TOKENS = frozenset({"alize", "beast", "dragon", "bird"})


def class_category(cls: "ClassEntry", classes: list) -> str:
    """The :data:`CLASS_CATEGORIES` name of a class. Laguz classes carry a
    laguz category token (or an innate weapon, on it or its linked class).
    A human class is promoted when it outranks its linked ``promotes_to``
    class (HP cap, then movement; see the module docstring), or, with no
    link, when its HP cap is above the unpromoted 40."""
    linked = next((c for c in classes if cls.promotes_to and c.jid == cls.promotes_to and c is not cls), None)
    pair = [cls] + ([linked] if linked is not None else [])
    if any(LAGUZ_CLASS_TOKENS.intersection(c.categories or ()) or c.innate_weapon for c in pair):
        return "Laguz"
    hp_cap = cls.stat_caps[0] if cls.stat_caps else 0
    if linked is not None:
        linked_cap = linked.stat_caps[0] if linked.stat_caps else 0
        if hp_cap != linked_cap:
            return "Promoted" if hp_cap > linked_cap else "Unpromoted"
        if cls.movement != linked.movement:
            return "Promoted" if cls.movement > linked.movement else "Unpromoted"
    return "Promoted" if hp_cap > 40 else "Unpromoted"


#: Rank tokens (item 0x14) and the minimum weapon EXP each one becomes; "N" means none, like null.
ITEM_RANKS = (("E", 1), ("D", 31), ("C", 71), ("B", 121), ("A", 181), ("S", 251), ("N", 0))
ITEM_PROPERTY_SLOTS = 6  # 0x18-0x2C
ITEM_CATEGORY_SLOTS = 2  # 0x30/0x34
#: Property tokens the engine recognises (apply_item_property_flag_token), with
#: what they do - "vanilla:" where only the vanilla items carrying it are known.
ITEM_PROPERTY_TOKENS = {
    "infinity": "Unbreakable - never loses uses",
    "valuable": "Vanilla: the unique and legendary weapons, Knight Ring",
    "twice": "Brave - strikes twice",
    "crit0": "Cannot land critical hits",
    "sealcrit": "Vanilla: Alondite, Ragnell, Gurgurant, laguz claws and kings' beaks",
    "poison": "Poisons the target",
    "resire": "Drains HP (Runesword, Resire)",
    "magsw": "Magic sword - attacks with magic, not strength (Runesword, Sonic Sword)",
    "stormsw": "Vanilla: Alondite, Ragnell, Gurgurant",
    "longfar": "Siege weapon (siege tomes, ballistae)",
    "sh": "Vanilla: the ballistae and the Onager",
    "revatr": "Not used in vanilla",
    "breath": "Vanilla: the dragon breaths",
    "fang": "Laguz natural weapon",
    "flutter": "Vanilla: Vortex",
    "weakA": "Vanilla: Ragnell, laguz claws, breaths, kings' beaks",
    "sfxseal": "Holder takes no effective damage (Full Guard)",
    "skysfxseal": "Holder ignores anti-flier effectiveness (not used in vanilla)",
    "lycsfxseal": "Holder ignores anti-laguz effectiveness (Beorcguard)",
    "lycdamhalf": "Halves damage from laguz (Laguzguard)",
    "movtw": "Canto - move again after acting (Knight Ring)",
    "beastsamul": "Keeps a laguz transformed (Demi Band, Laguz Band)",
    "JH": "Vanilla: Demi Band",
    "noneart": "Vanilla: Boots",
    "heroonly": "Only Ike can use it (Regal Sword, Ragnell)",
    "blackonly": "Only the Black Knight can use it (Alondite)",
    "finalonly": "Only Ashnard can use it (Gurgurant)",
    "humanonly": "Only beorc can use it",
    "beastonly": "Only laguz can use it",
    "knightonly": "Only knights can use it (not used in vanilla)",
    "shootonly": "Vanilla: Double Bow, Longbow",
    "eqA": "User lock A (Rolf's Bow: Rolf only)",
    "eqB": "User lock B (Amiti: Elincia only)",
    "eqC": "User lock C (Laguz Band)",
    "eqD": "User lock D (Knight Ward: soldiers, knights, paladins)",
    "eqrevA": "Everyone except lock A (Demi Band)",
}
#: Tokens vanilla items carry that the engine never matches (no effect).
ITEM_IGNORED_PROPERTY_TOKENS = ("areaattack", "absolutehit")
#: Category tokens (item 0x30/0x34, the same set classes use) - what the weapon is effective against.
ITEM_CATEGORY_TOKENS = {
    "mage": "Mages", "fly": "Fliers", "knight": "Cavalry", "armor": "Armor", "alize": "Laguz",
    "human": "Beorc", "beast": "Beast laguz", "dragon": "Dragon laguz", "bird": "Bird laguz",
    "final": "Final boss", "hero": "Hero", "boss": "Boss", "doorbreak": "Can break doors",
}
#: Held-item stat bonus order (0x4B-0x54): STAT_NAMES, then movement and build (Con).
ITEM_STAT_BONUS_NAMES = ["HP", "Str", "Mag", "Skl", "Spd", "Lck", "Def", "Res", "Mov", "Con"]
#: Attack trail colours (0x5D): the engine's RGBA table at 0x80368D38.
ITEM_TRAIL_COLORS = (
    ("Grey", 0x808080FF), ("Black (transparent)", 0x00000080), ("Red", 0xFF2020FF), ("Green", 0x20FF20FF),
    ("Blue", 0x2020FFFF), ("Olive", 0x808020FF), ("Purple", 0x802080FF), ("Brown", 0x804020FF),
    ("Teal", 0x208080FF),
)

SKILL_TABLE_OFFSET = 0xE398  # first record (SID_HERO); the count word sits just before it
SKILL_RECORD_SIZE = 0x28
CHAPTER_RECORD_SIZE = 0x60

# HP, Str, Mag, Skl, Spd, Lck, Def, Res - standard Fire Emblem stat order,
# not independently confirmed field-by-field but consistent with every
# mainline entry in the series.
STAT_NAMES = ["HP", "Str", "Mag", "Skl", "Spd", "Lck", "Def", "Res"]

# Position order of a class's 9-character weapon-rank string (see
# ClassEntry.weapon_ranks / module docstring). Positions 0-6 confirmed by
# real single-weapon-type classes (Fighter -> only position 2 set, Archer
# -> only position 3, Mage_F/Mage_T/Mage_W -> only position 4/5/6
# respectively, ...). Position 7 (here "Staff") is the weaker of the two
# magic-adjacent guesses: Priest/Bishop/Valkyrie all carry a rank there,
# consistent with Tellius's staff-healer archetype, but no class was found
# with a *letter* rank at position 8 to independently confirm "Light" - it
# was only ever seen as the '*' wildcard marker (ClassEntry.weapon_ranks'
# own docstring), so position 8 is the single lowest-confidence entry here.
WEAPON_TYPE_NAMES = ["Sword", "Lance", "Axe", "Bow", "Fire", "Thunder", "Wind", "Staff", "Light"]
#: The characters of a weapon rank string: '-' unusable, '*' usable without a
#: fixed rank, else the rank letter.
WEAPON_RANK_CHARS = "-*EDCBAS"


def _resolve(data: bytes, ptr: int) -> Optional[str]:
    """A record field pointer is 0-based after HEADER_SIZE, same convention
    as every other format in this package (see common.py). Returns None for
    a null pointer, or the resolved NUL-terminated label if the bytes at
    that address look like a real ASCII string."""
    if ptr == 0:
        return None
    addr = ptr + HEADER_SIZE
    if not (0 <= addr < len(data)):
        return None
    end = data.find(b"\x00", addr)
    if end == -1 or end - addr >= 64:
        return None
    raw = data[addr:end]
    if raw and all(32 <= b < 127 for b in raw):
        return raw.decode("ascii")
    return None


def _resolve_sjis(data: bytes, ptr: int) -> Optional[str]:
    """Like _resolve(), but for the skill table's internal Japanese-name
    pointer (offset 0x08): decodes shift_jis and allows non-ASCII bytes,
    which _resolve()'s ASCII-only check would reject outright."""
    if ptr == 0:
        return None
    addr = ptr + HEADER_SIZE
    if not (0 <= addr < len(data)):
        return None
    end = data.find(b"\x00", addr)
    if end == -1 or end - addr >= 64:
        return None
    raw = data[addr:end]
    if not raw:
        return None
    try:
        return raw.decode("shift_jis")
    except UnicodeDecodeError:
        return None


def _encode_label(label: str) -> bytes:
    """A label as the file stores it: ASCII, or Shift-JIS for the Japanese
    names and keys (terrain names, ``MG_`` army keys...)."""
    try:
        return label.encode("ascii")
    except UnicodeEncodeError:
        return label.encode("shift_jis")


def _string_at(data: bytes, ptr: int) -> Optional[bytes]:
    addr = ptr + HEADER_SIZE
    if not ptr or not 0 <= addr < len(data):
        return None
    end = data.find(b"\x00", addr)
    return None if end == -1 else data[addr:end]


def _pool_window(data: bytes, targets) -> tuple[int, int]:
    """Where a bare string search is trusted: from the first pointer target
    that is a string (short tokens like "E" also occur as plain bytes in the
    record tables before it) up to the first section placed after it (a
    table moved to the end of the data section) or the end of the data."""
    if not _complete_container(data):
        return 0, len(data)
    data_end = HEADER_SIZE + struct.unpack_from(">I", data, 4)[0]
    strings = [t for t in targets if _resolve(data, t) is not None]
    start = min(strings) + HEADER_SIZE - 1 if strings else HEADER_SIZE
    later = [HEADER_SIZE + o for o in symbol_offsets(data).values() if HEADER_SIZE + o > start]
    return start, min(later + [data_end])


def _label_offset(data: bytes, label: str, *, pool_only: bool = False) -> Optional[int]:
    """Inverse of _resolve(): the pointer value naming ``label`` - one an
    existing pointer field already uses, else the string in the pool, else
    (unless ``pool_only``) a copy anywhere outside the record tables - or
    None when the file has no such string."""
    encoded = _encode_label(label)
    targets = sorted({struct.unpack_from(">I", data, f)[0] for f in listed_pointer_fields(data)})
    for ptr in targets:
        if _string_at(data, ptr) == encoded:
            return ptr
    needle = b"\x00" + encoded + b"\x00"
    lo, hi = _pool_window(data, targets)
    idx = data.find(needle, max(lo, 0), hi)
    if idx != -1:
        return idx + 1 - HEADER_SIZE
    if pool_only:
        return None
    # not in the pool proper (a file whose pointer list misses fields): any
    # match outside the record tables
    areas = []
    for kind in TABLES:
        try:
            start = table_start(data, kind)
            areas.append((start - 4, start + table_count(data, kind) * TABLES[kind][1]))
        except (ValueError, struct.error):
            continue
    idx = data.find(needle)
    while idx != -1:
        if not any(a <= idx + 1 < b for a, b in areas):
            return idx + 1 - HEADER_SIZE
        idx = data.find(needle, idx + 1)
    return None


def add_label(data: bytes, label: str) -> bytes:
    """Return ``data`` with ``label`` in its string pool, appending it to the
    end of the data section when it is not already there."""
    if _label_offset(data, label) is not None:
        return data
    return _append_label(data, label)[0]


def _append_label(data: bytes, label: str) -> tuple[bytes, int]:
    """``data`` with a new copy of ``label`` at the end of the data section,
    and the pointer value naming it. The pointer list and symbol table after
    the data section hold data-relative offsets, so they move unchanged."""
    file_size, data_size = struct.unpack(">II", data[:8])
    end = HEADER_SIZE + data_size
    added = _encode_label(label) + b"\x00"
    added += bytes(-(data_size + len(added)) % 4)
    out = bytearray(data[:end] + added + data[end:])
    struct.pack_into(">II", out, 0, file_size + len(added), data_size + len(added))
    return bytes(out), data_size


def _patch_label_field(data: bytes, offset: int, label: Optional[str], *, append: bool) -> bytes:
    """Point the pointer field at absolute ``offset`` to ``label`` (None:
    null). With ``append`` a label missing from the file is added to the
    string pool, else it is refused."""
    if label is None:
        out = bytearray(data)
        _pack_pointer(out, offset, 0)
        return bytes(out)
    data, ptr = _label_pointer(data, label, append=append)
    out = bytearray(data)
    _pack_pointer(out, offset, ptr)
    return bytes(out)


@dataclass
class CharacterEntry:
    index: int
    offset: int  # absolute file offset of this record's start
    pid: Optional[str]  # person ID - the character's internal identity
    fid: Optional[str]  # portrait ID
    jid: Optional[str]  # class ID
    sids: list  # 0x1C/0x20/0x24, the 3 personal skills (build_person_data_table's set_skill_flag_by_name calls)
    aid_unpromoted: Optional[str]  # unpromoted model/animation ID
    aid_promoted: Optional[str]  # promoted model/animation ID
    level: int
    build: int
    weight: int
    stat_bonus: list  # 8 ints, STAT_NAMES order - personal bonus added atop class base + growths, not a displayed total
    growth: list  # 8 ints, STAT_NAMES order, growth rate percentage points
    fixed_growth_start: list  # 0x49-0x50, starting accumulators of the fixed ("Fraction") level-up mode, STAT_NAMES order
    mpid: Optional[str] = None  # +0x04, the name key ("MPID_IKE") looked up in Mess/common.m
    weapon_ranks: Optional[str] = None  # +0x18, personal 9-character rank string ("D--------"), WEAPON_TYPE_NAMES order
    roster_order: int = 0  # +0x30 u16 (runtime +0x5A), recruitment order: the unit lists' default sort key
    biorhythm_pattern: int = 0  # +0x32 u16; 0 = a random pattern 0-365 at load
    start_transform_gauge: int = 0  # +0x34 (runtime +0x56), laguz transform gauge at deployment (0-20)
    biorhythm_phase: int = 30  # +0x35; 0 = 30 at load (30 in every vanilla record)


@dataclass
class ClassEntry:
    index: int
    offset: int
    jid: Optional[str]
    mjid: Optional[str]  # menu/display JID variant - relationship to jid not fully understood
    hybrid_id: Optional[str]  # +0x08, the class description key ("MH_J_..."; the loader stores it as the description)
    promotes_to: Optional[str]  # actually bidirectional - the linked class points back at this one too, see docstring
    aid: Optional[str]  # +0x38, the class's base animation ID: a unit whose character has none uses it
    movement: int  # confirmed: +1 on every human-class promotion pair, checked aggregate not just by eye
    stat_caps: list  # 8 ints, STAT_NAMES order; only cap[0] (HP, 40->60 on promotion) was aggregate-checked, rest by thematic fit
    base_stats: list  # 8 ints at 0x44, STAT_NAMES order, class base stats (Luck unused by the loader)
    growths: list  # 8 ints at 0x54, STAT_NAMES order, class growth rates
    movement_type: int  # 0x42, index into MOVEMENT_TYPE_NAMES
    weapon_ranks: Optional[str]  # 9-char string, WEAPON_TYPE_NAMES order, '-'=unusable, a letter=that rank, '*'=usable without a fixed rank; see module docstring
    skills: list  # up to 5 SID_ pointers (class-innate skills) at 0x18-0x2C; None for an empty slot
    raw: bytes  # the rest of the record (offset 0x10 onward) - includes the decoded fields above again in raw form, same convention as ItemEntry.raw; genuinely-undecoded ranges are documented in the module docstring
    innate_weapon: Optional[str] = None  # 0x10, IID_ equipped by equip_innate_laguz_weapon (falls back to the promotion's)
    build: int = 0  # 0x3C, added to the character's build (get_unit_build)
    weight: int = 0  # 0x3D, added to the character's weight (get_unit_weight)
    skill_capacity: int = 0  # 0x40, skill capacity (the skill-capacity gauge and learnable-skill checks)
    vision: int = 0  # 0x41, fog-of-war vision range; the Torch bonus in unit +0x1A6 bits 2-4 adds to it
    growth_modifiers: list = dataclass_field(default_factory=list)  # 0x5C-0x63, signed, STAT_NAMES order (process_exp_and_growth)
    categories: list = dataclass_field(default_factory=list)  # 0x2C-0x34, 3 category tokens (None = empty slot)


@dataclass
class ItemEntry:
    """Every field of a 0x60-byte item record - see the module docstring's
    "Item record" section for how each was confirmed."""
    index: int
    offset: int
    iid: Optional[str]  # 0x00
    miid: Optional[str]  # 0x04, name key
    help_key: Optional[str]  # 0x08, description key (MH_I_...)
    weapon_type: Optional[str]  # 0x0C token, see ITEM_WEAPON_TYPES
    attack_type: Optional[str]  # 0x10 token: decides physical vs. magic
    rank: Optional[str]  # 0x14 token, see ITEM_RANKS; None = no rank needed
    properties: list  # 0x18-0x2C, 6 property tokens (None = empty slot)
    categories: list  # 0x30/0x34, 2 category tokens: what the weapon is effective against
    effect: Optional[str]  # 0x38, EID_ use/spell effect
    weapon_effect: Optional[str]  # 0x3C, EID_ weapon effect
    cost: int  # 0x40, u16 price per use
    uses: int  # 0x42
    might: int  # 0x43
    hit: int  # 0x44
    weight: int  # 0x45
    crit: int  # 0x46
    min_range: int  # 0x47
    max_range: int  # 0x48, 255 = Mag/2
    icon: int  # 0x49
    weapon_exp: int  # 0x4A, weapon EXP per use
    stat_bonus: list  # 0x4B-0x54, 10 signed, ITEM_STAT_BONUS_NAMES order
    growth_bonus: list  # 0x55-0x5C, 8 signed, STAT_NAMES order
    trail_color: int  # 0x5D, index into ITEM_TRAIL_COLORS
    padding: bytes  # 0x5E-0x5F, skipped by the loader


@dataclass
class SkillEntry:
    index: int
    offset: int
    sid: Optional[str]  # skill's internal ID, e.g. "SID_COUNTER"
    msid: Optional[str]  # 0x08, the skill's name key (the skill lists resolve it)
    japanese_name: Optional[str]  # untranslated internal dev name, shift_jis
    help_key: Optional[str]  # "Mess_Help_skill_<Name>" - a lookup KEY, not the text itself; None for skills with no player-facing description (see module docstring)
    help2_key: Optional[str]  # "Mess_Help2_skill_<Name>", same caveat
    restricted_to: list  # 0x24 -> list of 0x1C labels (PID_/JID_) the skill is exclusive to; [] if anyone
    params: tuple  # 0x19-0x1B: icon (0 = none), capacity cost, has-a-scroll flag (never read) - see module docstring
    skill_items: list = dataclass_field(default_factory=list)  # 0x20 -> the IID_ of the scroll that teaches it
    self_index: int = 0  # 0x18, the record's own table index
    reserved: bytes = b""  # 0x1D-0x1F: 0, except byte 0x1F = 5 on SID_TELEGNOSIS/SID_BIGEAR - never read
    effect: Optional[str] = None  # 0x14 -> EID_ played when the skill triggers


@dataclass
class Fe8Data:
    characters: list
    classes: list
    items: list
    skills: list


def _read_character(data: bytes, index: int, base: Optional[int] = None) -> CharacterEntry:
    off = (table_start(data, "character") if base is None else base) + index * CHARACTER_RECORD_SIZE
    rec = data[off : off + CHARACTER_RECORD_SIZE]
    (pid_ptr,) = struct.unpack(">I", rec[0x00:0x04])
    (mpid_ptr,) = struct.unpack(">I", rec[0x04:0x08])
    (fid_ptr,) = struct.unpack(">I", rec[0x0C:0x10])
    (jid_ptr,) = struct.unpack(">I", rec[0x10:0x14])
    (ranks_ptr,) = struct.unpack(">I", rec[0x18:0x1C])
    sid_ptrs = struct.unpack(">III", rec[0x1C:0x28])
    (aid_un,) = struct.unpack(">I", rec[0x28:0x2C])
    (aid_pr,) = struct.unpack(">I", rec[0x2C:0x30])
    return CharacterEntry(
        index=index,
        offset=off,
        pid=_resolve(data, pid_ptr),
        fid=_resolve(data, fid_ptr),
        jid=_resolve(data, jid_ptr),
        sids=[_resolve(data, p) for p in sid_ptrs],
        aid_unpromoted=_resolve(data, aid_un),
        aid_promoted=_resolve(data, aid_pr),
        level=rec[0x36],
        build=rec[0x37],
        weight=rec[0x38],
        stat_bonus=_signed(rec[0x39:0x41]),  # signed: retail PID_KILROY has Def -1 (0xFF)
        growth=list(rec[0x41:0x49]),
        fixed_growth_start=list(rec[0x49:0x51]),
        mpid=_resolve(data, mpid_ptr),
        weapon_ranks=_resolve(data, ranks_ptr),
        roster_order=struct.unpack(">H", rec[0x30:0x32])[0],
        biorhythm_pattern=struct.unpack(">H", rec[0x32:0x34])[0],
        start_transform_gauge=rec[0x34],
        biorhythm_phase=rec[0x35],
    )


def _read_class(data: bytes, index: int, base: Optional[int] = None) -> ClassEntry:
    off = (table_start(data, "class") if base is None else base) + index * CLASS_RECORD_SIZE
    rec = data[off : off + CLASS_RECORD_SIZE]
    jid_ptr, mjid_ptr, hybrid_ptr, promotes_ptr = struct.unpack(">IIII", rec[0x00:0x10])
    (rank_ptr,) = struct.unpack(">I", rec[0x14:0x18])
    skill_ptrs = struct.unpack(">IIIII", rec[0x18:0x2C])
    (aid_ptr,) = struct.unpack(">I", rec[CLASS_AID_OFFSET : CLASS_AID_OFFSET + 4])
    return ClassEntry(
        index=index,
        offset=off,
        jid=_resolve(data, jid_ptr),
        mjid=_resolve(data, mjid_ptr),
        hybrid_id=_resolve(data, hybrid_ptr),
        promotes_to=_resolve(data, promotes_ptr),
        aid=_resolve(data, aid_ptr),
        movement=rec[CLASS_MOVE_OFFSET],
        stat_caps=list(rec[CLASS_CAPS_OFFSET : CLASS_CAPS_OFFSET + 8]),
        base_stats=list(rec[CLASS_BASE_STAT_OFFSET : CLASS_BASE_STAT_OFFSET + 8]),
        growths=list(rec[CLASS_GROWTH_OFFSET : CLASS_GROWTH_OFFSET + 8]),
        movement_type=rec[CLASS_MOVE_TYPE_OFFSET],
        weapon_ranks=_resolve(data, rank_ptr),
        skills=[_resolve(data, p) for p in skill_ptrs],
        raw=rec[0x10:],
        innate_weapon=_resolve(data, struct.unpack(">I", rec[0x10:0x14])[0]),
        build=rec[0x3C],
        weight=rec[0x3D],
        skill_capacity=rec[0x40],
        vision=rec[0x41],
        growth_modifiers=_signed(rec[0x5C:0x64]),
        categories=[_resolve(data, p) for p in struct.unpack(">III", rec[0x2C:0x38])],
    )


def class_weapon_rank_map(class_entry: ClassEntry) -> dict:
    """ClassEntry.weapon_ranks (a 9-char string) as a {weapon type: rank}
    dict in WEAPON_TYPE_NAMES order, skipping '-' (unusable) entries. A
    '*' rank means "usable without a fixed letter requirement" - see the
    module docstring."""
    if not class_entry.weapon_ranks:
        return {}
    return {
        WEAPON_TYPE_NAMES[i]: ch
        for i, ch in enumerate(class_entry.weapon_ranks)
        if i < len(WEAPON_TYPE_NAMES) and ch != "-"
    }


def _signed(values: bytes) -> list:
    return [v - 256 if v > 127 else v for v in values]


def _read_item(data: bytes, index: int, base: Optional[int] = None) -> ItemEntry:
    off = (table_start(data, "item") if base is None else base) + index * ITEM_RECORD_SIZE
    rec = data[off : off + ITEM_RECORD_SIZE]
    labels = [_resolve(data, p) for p in struct.unpack(">16I", rec[:0x40])]
    return ItemEntry(
        index=index,
        offset=off,
        iid=labels[0],
        miid=labels[1],
        help_key=labels[2],
        weapon_type=labels[3],
        attack_type=labels[4],
        rank=labels[5],
        properties=labels[6:12],
        categories=labels[12:14],
        effect=labels[14],
        weapon_effect=labels[15],
        cost=struct.unpack(">H", rec[0x40:0x42])[0],
        uses=rec[0x42],
        might=rec[0x43],
        hit=rec[0x44],
        weight=rec[0x45],
        crit=rec[0x46],
        min_range=rec[0x47],
        max_range=rec[0x48],
        icon=rec[0x49],
        weapon_exp=rec[0x4A],
        stat_bonus=_signed(rec[0x4B:0x55]),
        growth_bonus=_signed(rec[0x55:0x5D]),
        trail_color=rec[0x5D],
        padding=rec[0x5E:0x60],
    )


def _table_count(data: bytes, table_offset: int, record_size: int, fallback: int) -> int:
    """A table's record count: the u32 just before its first record (the
    word the table's symbol points at). ``fallback`` when that word is
    missing or doesn't fit the file."""
    if table_offset < 4:
        return fallback
    (count,) = struct.unpack_from(">I", data, table_offset - 4)
    if 0 < count and table_offset + count * record_size <= len(data):
        return count
    return fallback


def _count_valid_records(
    data: bytes, table_offset: int, record_size: int, id_prefix: bytes, max_count: int, ptr_offset: int = 0
) -> int:
    """Scan forward from table_offset until a record's ID pointer field
    fails to resolve to a label with the expected prefix - used to find a
    table's length empirically since the file header's own count fields
    aren't confirmed for class/item/skill tables (see module docstring).
    `ptr_offset` is where that pointer sits within a record."""
    count = 0
    while count < max_count:
        off = table_offset + count * record_size + ptr_offset
        if off + 4 > len(data):
            break
        (ptr,) = struct.unpack(">I", data[off : off + 4])
        label = _resolve(data, ptr)
        if label is None or not label.encode("ascii").startswith(id_prefix):
            break
        count += 1
    return count


def _read_label_list(data: bytes, ptr: int, count: int) -> list:
    """``count`` label pointers stored at header-relative ``ptr``."""
    addr = ptr + HEADER_SIZE
    if not ptr or count <= 0 or addr + 4 * count > len(data):
        return []
    return [_resolve(data, w) for w in struct.unpack_from(f">{count}I", data, addr)]


def _read_skill(data: bytes, index: int, base: Optional[int] = None) -> SkillEntry:
    off = (table_start(data, "skill") if base is None else base) + index * SKILL_RECORD_SIZE
    rec = data[off : off + SKILL_RECORD_SIZE]
    sid_ptr, jpname_ptr, msid_ptr, help_ptr, help2_ptr = struct.unpack(">IIIII", rec[0x00:0x14])
    items_ptr, restriction_ptr = struct.unpack(">II", rec[0x20:0x28])
    return SkillEntry(
        index=index,
        offset=off,
        sid=_resolve(data, sid_ptr),
        msid=_resolve(data, msid_ptr),
        japanese_name=_resolve_sjis(data, jpname_ptr),
        help_key=_resolve(data, help_ptr),
        help2_key=_resolve(data, help2_ptr),
        restricted_to=[label for label in _read_label_list(data, restriction_ptr, rec[0x1C]) if label],
        params=(rec[0x19], rec[0x1A], rec[0x1B]),
        skill_items=[label for label in _read_label_list(data, items_ptr, 1) if label],
        self_index=rec[0x18],
        reserved=rec[0x1D:0x20],
        effect=_resolve(data, struct.unpack(">I", rec[0x14:0x18])[0]),
    )


def read_fe8data(data: bytes) -> Fe8Data:
    def count(table: int, size: int, prefix: bytes, limit: int) -> int:
        return _table_count(data, table, size, _count_valid_records(data, table, size, prefix, max_count=limit))

    bases = {kind: table_start(data, kind) for kind in ("character", "class", "item", "skill")}
    character_count = _table_count(data, bases["character"], CHARACTER_RECORD_SIZE, CHARACTER_COUNT)
    characters = [_read_character(data, i, bases["character"]) for i in range(character_count)]
    class_count = count(bases["class"], CLASS_RECORD_SIZE, b"JID_", CLASS_COUNT + 10)
    classes = [_read_class(data, i, bases["class"]) for i in range(class_count)]
    item_count = count(bases["item"], ITEM_RECORD_SIZE, b"IID_", 600)
    items = [_read_item(data, i, bases["item"]) for i in range(item_count)]
    skill_count = count(bases["skill"], SKILL_RECORD_SIZE, b"SID_", 300)
    skills = [_read_skill(data, i, bases["skill"]) for i in range(skill_count)]

    return Fe8Data(characters=characters, classes=classes, items=items, skills=skills)


def read_fe8data_path(path: Path | str) -> Fe8Data:
    return read_fe8data(Path(path).read_bytes())


def read_skill_descriptions(system_cmp_path: Path | str) -> dict:
    """Resolve every skill's help_key/help2_key (see SkillEntry) to its
    actual localized text. That text does not live in FE8Data.bin itself -
    see the module docstring's "read_skill_descriptions()" section for how
    this LZ10 -> pack -> message.py pipeline was confirmed against real
    skill descriptions. Returns a dict from message key (e.g.
    "Mess_Help_skill_Counter") to its text, covering both the short and
    long description pools in one lookup."""
    import io

    from . import lz10, message, pak

    decompressed = lz10.decompress(Path(system_cmp_path).read_bytes())
    entries = pak.read_pak_entries(decompressed)
    common_entry = next(e for e in entries if e.name == "mess/common.m")
    common_data = pak.read_pak_file_content(decompressed, common_entry)
    messages = message.read_messages(io.BytesIO(common_data))
    return {m.speaker: m.text for m in messages if m.speaker.startswith("Mess_Help")}


#: Terrain types in ``TerrainData`` (the engine walks a fixed 77 entries).
TERRAIN_TYPE_COUNT = 77


@dataclass(frozen=True)
class TerrainType:
    """One ``TerrainData`` record (12 bytes): the Japanese name a map tile's
    panel points to (``平地``), the message key of its displayed name
    (``MT_平地`` -> "Plain"), and a pointer to a 24-byte stats block shared
    by several types:

    - bytes 0-2: avoid, defence, resistance (``apply_terrain_defense_bonus``
      copies them; confirmed in the terrain window);
    - bytes 3-5: the same three for units with flag 4 (plausibly fliers);
    - byte 6: HP healed at the start of a turn, in % of max HP (10 on Heal,
      Healhedge, Throne, Castle, Fort; ``initialize_damage_event_process``);
    - byte 7: object tile (roofs, trees, fences, small objects, buildings,
      holes, sandbags, the impassable type): copied into a per-tile grid at
      map setup, and the nearest-free-tile search never picks such a tile;
    - bytes 8-22: movement cost per movement type (``MOVEMENT_TYPE_NAMES``,
      the class byte 0x42), 255 = impassable.

    ``block`` is the stats block's data-relative offset; several types share
    one block (13 blocks for 77 types in vanilla), so
    :func:`patch_terrain_stats` either edits the shared block or gives the
    type its own.
    """

    index: int
    name: str
    name_key: str
    block: int
    avoid: int = 0
    defense: int = 0
    resistance: int = 0
    alt_bonus: tuple[int, int, int] = (0, 0, 0)  # avoid, defence, resistance with flag 4
    heal: int = 0
    flag7: int = 0
    move_costs: tuple[int, ...] = ()

    @property
    def impassable(self) -> bool:
        return bool(self.move_costs) and all(c == 255 for c in self.move_costs)


def symbol_offsets(data: bytes) -> dict[str, int]:
    """Data-relative offsets of the container's named symbols
    (``PersonData``, ``TerrainData``...)."""
    _size, data_size, pointer_count, symbol_count = struct.unpack(">IIII", data[:16])
    table = HEADER_SIZE + data_size + 4 * pointer_count
    names = table + 8 * symbol_count
    result = {}
    for i in range(symbol_count):
        offset, name_offset = struct.unpack(">II", data[table + 8 * i : table + 8 * i + 8])
        end = data.index(b"\x00", names + name_offset)
        result[data[names + name_offset : end].decode("ascii", errors="replace")] = offset
    return result


def read_terrain_types(data: bytes) -> list[TerrainType]:
    """The 77 terrain types, in the engine's index order (index 9 and 33 are
    looked up as 28, the door)."""
    start = HEADER_SIZE + symbol_offsets(data)["TerrainData"] + 4
    result = []
    for i in range(TERRAIN_TYPE_COUNT):
        name_ptr, key_ptr, block = struct.unpack(">III", data[start + 12 * i : start + 12 * i + 12])
        b = data[HEADER_SIZE + block : HEADER_SIZE + block + 24] if block else bytes(24)
        signed = [v - 256 if v > 127 else v for v in b[:6]]
        result.append(
            TerrainType(
                i, _resolve_sjis(data, name_ptr) or "", _resolve_sjis(data, key_ptr) or "", block,
                avoid=signed[0], defense=signed[1], resistance=signed[2], alt_bonus=tuple(signed[3:6]),
                heal=b[6], flag7=b[7], move_costs=tuple(b[8:23]),
            )
        )
    return result


def terrain_block_users(data: bytes, index: int) -> list[int]:
    """Indices of every terrain type sharing type ``index``'s stats block."""
    types = read_terrain_types(data)
    return [t.index for t in types if t.block == types[index].block]


def patch_terrain_stats(data: bytes, index: int, block: bytes, own_block: bool = False) -> bytes:
    """Write a 24-byte stats block for terrain type ``index`` (layout in
    :class:`TerrainType`). By default the type's current block is
    overwritten, changing every type sharing it (:func:`terrain_block_users`);
    with ``own_block`` a new block is appended to the data section and only
    this type points at it."""
    if len(block) != 24:
        raise ValueError("A terrain stats block is 24 bytes.")
    record = HEADER_SIZE + symbol_offsets(data)["TerrainData"] + 4 + 12 * index
    current = struct.unpack(">I", data[record + 8 : record + 12])[0]
    if not own_block and current:
        out = bytearray(data)
        out[HEADER_SIZE + current : HEADER_SIZE + current + 24] = block
        return bytes(out)
    file_size, data_size = struct.unpack(">II", data[:8])
    end = HEADER_SIZE + data_size
    added = bytes(block) + bytes(-(data_size + 24) % 4)
    out = bytearray(data[:end] + added + data[end:])
    struct.pack_into(">II", out, 0, file_size + len(added), data_size + len(added))
    _pack_pointer(out, record + 8, data_size)
    return bytes(out)


def terrain_stats_block(t: "TerrainType") -> bytes:
    """A :class:`TerrainType`'s stats as the 24 bytes the file stores."""
    signed = [t.avoid, t.defense, t.resistance, *t.alt_bonus]
    return bytes(v & 0xFF for v in signed) + bytes((t.heal, t.flag7, *t.move_costs)) + bytes(1)


def read_message_texts(system_cmp_path: Path | str) -> dict:
    """Every ``mess/common.m`` message of ``system.cmp`` by key. Keys are
    Shift-JIS (``MT_平地``); the message reader decodes them as cp437, so
    they are re-decoded here."""
    import io

    from . import lz10, message, pak

    decompressed = lz10.decompress(Path(system_cmp_path).read_bytes())
    entries = pak.read_pak_entries(decompressed)
    common_entry = next(e for e in entries if e.name == "mess/common.m")
    messages = message.read_messages(io.BytesIO(pak.read_pak_file_content(decompressed, common_entry)))
    texts = {}
    for m in messages:
        try:
            key = m.speaker.encode(message.ENCODING).decode("shift_jis")
        except (UnicodeEncodeError, UnicodeDecodeError):
            key = m.speaker
        texts[key] = m.text
    return texts


#: English names of the ``GroupData`` army keys (the game's own texts are
#: just "Army", "Bandits"...).
GROUP_KEY_NAMES = {
    "MG_クリミア軍": "Crimean Army", "MG_デイン軍": "Daein Army", "MG_ガリア軍": "Gallia Army",
    "MG_山賊": "Bandits", "MG_海賊": "Pirates", "MG_エリンシア増援": "Elincia's reinforcements",
    "MG_タニス増援": "Tanith's reinforcements", "MG_カリワ山賊": "Kariwa bandits",
    "MG_グレイル傭兵団": "Greil Mercenaries", "MG_ベグニオン軍": "Begnion Army",
    "MG_はぐれ天馬騎士": "Stray pegasus knights", "MG_行商団": "Merchant caravan",
    "MG_ラグズ解放軍": "Laguz Liberation Army", "MG_タナス公爵軍": "Duke Tanas's army", "MG_盗賊": "Thieves",
    "MG_キルヴァス軍": "Kilvas Army", "MG_フェニキス軍": "Phoenicis Army", "MG_本当に無所属": "Truly unaffiliated",
    "MG_パルメニー僧": "Palmeny monks", "MG_捕虜": "Prisoners", "MG_ベグニオン増援": "Begnion reinforcements",
    "MG_自警団": "Militia", "MG_謎の軍": "Mysterious army", "MG_デイン残党": "Daein remnants",
    "MG_謎の勢力": "Mysterious force", "MG_闘士": "Fighters", "MG_サギの民": "Heron clan",
    "MG_はぐれ傭兵": "Stray mercenaries",
}


def read_group_keys(data: bytes) -> list[Optional[str]]:
    """The ``GroupData`` table: the army-name message key (``MG_...``) of
    every group id a dispos section header can name. Id 0 is no group."""
    start = HEADER_SIZE + symbol_offsets(data)["GroupData"]
    count = struct.unpack_from(">I", data, start)[0]
    return [_resolve_sjis(data, struct.unpack_from(">I", data, start + 4 + 4 * i)[0]) for i in range(count)]


def group_label(index: int, keys: list[Optional[str]]) -> str:
    """``"1 Crimean Army"`` for group ``index``; ``"0 (none)"`` for 0."""
    if index == 0:
        return "0 (none)"
    key = keys[index] if 0 <= index < len(keys) else None
    return f"{index} {GROUP_KEY_NAMES.get(key, key) if key else '(not in GroupData)'}"


def chant_stat_name(skills: list, skill: SkillEntry) -> Optional[str]:
    """For one of the 8 SID_CHANT<STAT> variants, return which of
    STAT_NAMES it boosts. This is inferred from the variant's position in
    the skill table relative to SID_CHANTHP, NOT read from a stored field -
    no field exists (see the module docstring's "Chant stat choice"
    section for what was ruled out and why this is the resolution).
    Returns None for anything that isn't one of the 8 variants (including
    plain SID_CHANT itself, which has no single stat)."""
    if skill.sid is None or not skill.sid.startswith("SID_CHANT") or skill.sid == "SID_CHANT":
        return None
    chanthp = next((s for s in skills if s.sid == "SID_CHANTHP"), None)
    if chanthp is None:
        return None
    stat_index = skill.index - chanthp.index
    if 0 <= stat_index < len(STAT_NAMES):
        return STAT_NAMES[stat_index]
    return None


def label_index_by_prefix(fe8: Fe8Data, data: bytes) -> dict:
    """Every label this file's records actually reference, grouped by prefix
    (PID/JID/IID/FID/SID/AID/MJID/MIID/MH_J/MH_I/EID) - mirrors dispo.py's
    label_index_by_prefix(), for offering "pick an existing label" dropdowns
    in an editor. Built from the label pool directly (every NUL-terminated
    ASCII run following a recognized prefix), not just labels seen on
    already-read records, so it also covers labels that only appear on
    not-yet-decoded fields."""
    grouped: dict = {}
    prefixes = [b"PID_", b"JID_", b"IID_", b"FID_", b"SID_", b"MSID_", b"AID_", b"MJID_", b"MIID_", b"MH_J_",
                b"MH_I_", b"EID_"]
    for prefix in prefixes:
        start = 0
        names = []
        while True:
            idx = data.find(prefix, start)
            if idx == -1:
                break
            end = data.find(b"\x00", idx)
            if end != -1 and 0 < end - idx < 64:
                raw = data[idx:end]
                if raw.isascii() and all(32 <= b < 127 for b in raw):
                    names.append((raw.decode("ascii"), idx - HEADER_SIZE))
            start = idx + 1
        if names:
            grouped[prefix.decode("ascii").rstrip("_")] = dict(names)
    return grouped


def _pack_pointer(data: bytearray, offset: int, value: int) -> None:
    """Write a pointer field (absolute file ``offset``) and keep the
    container's pointer list in step: the loader adds the file base to every
    listed field, so a null field must be off the list (a listed 0 becomes a
    pointer to the data start, read as an empty name) and a set field on it.
    The list is sorted; the symbol table after it is position-independent."""
    struct.pack_into(">I", data, offset, value)
    size, data_size, count = struct.unpack(">III", data[:12])
    start = HEADER_SIZE + data_size
    if size != len(data) or start + 4 * count > len(data):
        return  # not a complete container (a bare table in tests): no list to keep
    listed = list(struct.unpack_from(f">{count}I", data, start))
    field = offset - HEADER_SIZE
    if (field in listed) == bool(value):
        return
    if value:
        listed.append(field)
        listed.sort()
    else:
        listed.remove(field)
    data[start : start + 4 * count] = struct.pack(f">{len(listed)}I", *listed)
    struct.pack_into(">I", data, 0, len(data))
    struct.pack_into(">I", data, 8, len(listed))


#: Character pointer fields naming a string the game resolves elsewhere
#: (message key, portrait, model): a new label is added to the pool.
CHARACTER_KEY_FIELDS = {"mpid": 0x04, "fid": 0x0C, "aid_unpromoted": 0x28, "aid_promoted": 0x2C}
#: Character pointer fields naming another record: the label must exist.
CHARACTER_LINK_FIELDS = {"jid": 0x10, "sid0": 0x1C, "sid1": 0x20, "sid2": 0x24}
CHARACTER_BYTE_FIELDS = {"start_transform_gauge": 0x34, "biorhythm_phase": 0x35, "level": 0x36, "build": 0x37,
                         "weight": 0x38}


def _weapon_rank_string(value) -> str:
    ranks = str(value or "").upper()
    if len(ranks) != len(WEAPON_TYPE_NAMES) or any(ch not in WEAPON_RANK_CHARS for ch in ranks):
        raise ValueError(f"Weapon ranks are {len(WEAPON_TYPE_NAMES)} characters, each one of "
                         f"{WEAPON_RANK_CHARS} (- unusable, * no fixed rank).")
    return ranks


def _byte(value, low: int = 0, high: int = 255) -> int:
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f"must be {low} to {high}")
    return value & 0xFF


def patch_character_field(data: bytes, index: int, field: str, value) -> bytes:
    """Return a copy of data with one field of one character record
    overwritten. ``field`` is one of:

    - ``pid``: the character's ID, unique among characters (a new one is
      added to the string pool);
    - ``mpid``, ``fid``, ``aid_unpromoted``, ``aid_promoted``: a label (added
      to the pool when new) or None;
    - ``jid``, ``sid0``..``sid2``: an existing label or None;
    - ``weapon_ranks``: a 9-character rank string (see
      :data:`WEAPON_RANK_CHARS`) or None for the class's ranks;
    - ``level``, ``build``, ``weight``, ``start_transform_gauge``,
      ``biorhythm_phase`` (0-255), ``roster_order``, ``biorhythm_pattern``
      (0-65535);
    - ``stat_bonus0..7`` (-128..127), ``growth0..7``, ``fixed_growth_start0..7`` (0-255)."""
    off = table_start(data, "character") + index * CHARACTER_RECORD_SIZE
    if field == "pid":
        return _patch_id(data, "character", index, value)
    if field in CHARACTER_KEY_FIELDS:
        return _patch_label_field(data, off + CHARACTER_KEY_FIELDS[field], (value or "").strip() or None,
                                  append=True)
    if field in CHARACTER_LINK_FIELDS:
        return _patch_label_field(data, off + CHARACTER_LINK_FIELDS[field], (value or "").strip() or None,
                                  append=False)
    if field == "weapon_ranks":
        ranks = None if value is None or not str(value).strip() else _weapon_rank_string(value)
        return _patch_label_field(data, off + 0x18, ranks, append=True)
    out = bytearray(data)
    if field in CHARACTER_BYTE_FIELDS:
        out[off + CHARACTER_BYTE_FIELDS[field]] = _byte(value)
    elif field in ("roster_order", "biorhythm_pattern"):
        if not 0 <= int(value) <= 0xFFFF:
            raise ValueError("must be 0 to 65535")
        struct.pack_into(">H", out, off + (0x30 if field == "roster_order" else 0x32), int(value))
    elif re.fullmatch(r"(stat_bonus|growth|fixed_growth_start)[0-7]", field):
        name, i = field[:-1], int(field[-1])
        if name == "stat_bonus":  # signed
            if not -128 <= int(value) <= 127:
                raise ValueError("must be -128 to 127")
            byte = int(value) & 0xFF
        else:
            byte = _byte(value)
        out[off + {"stat_bonus": 0x39, "growth": 0x41, "fixed_growth_start": 0x49}[name] + i] = byte
    else:
        raise ValueError(f"Unknown character field {field!r}")
    return bytes(out)


#: Class pointer fields naming a string resolved elsewhere (name and
#: description keys, model): a new label is added to the pool.
CLASS_KEY_FIELDS = {"mjid": 0x04, "hybrid_id": 0x08, "aid": CLASS_AID_OFFSET}
#: Class pointer fields naming another record: the label must exist.
CLASS_LINK_FIELDS = {"promotes_to": 0x0C, "innate_weapon": 0x10, **{f"skill{i}": 0x18 + 4 * i for i in range(5)}}
CLASS_CATEGORY_SLOTS = 3  # 0x2C/0x30/0x34
CLASS_BYTE_FIELDS = {"movement": CLASS_MOVE_OFFSET, "build": 0x3C, "weight": 0x3D, "skill_capacity": 0x40,
                     "vision": 0x41}


def patch_class_field(data: bytes, index: int, field: str, value) -> bytes:
    """Return a copy of data with one field of one class record overwritten.
    ``field`` is one of:

    - ``jid``: the class ID, unique among classes (a new one is added to the
      string pool);
    - ``mjid``, ``hybrid_id`` (description key), ``aid``: a label (added when
      new) or None;
    - ``promotes_to``, ``innate_weapon``, ``skill0..4``: an existing label or
      None;
    - ``weapon_ranks``: a 9-character string (see :data:`WEAPON_RANK_CHARS`;
      added to the string pool when no class uses it yet, so classes sharing
      the old string keep it);
    - ``categories``: up to 3 category tokens (:data:`ITEM_CATEGORY_TOKENS`,
      the set ``apply_unit_category_flag_token`` knows), written in order;
    - ``movement``, ``build``, ``weight``, ``skill_capacity``, ``vision``
      (0-255), ``movement_type`` (0-14);
    - ``cap0..7``, ``base_stat0..7``, ``growth0..7`` (0-255) and
      ``growth_modifier0..7`` (-128..127), STAT_NAMES order."""
    off = table_start(data, "class") + index * CLASS_RECORD_SIZE
    if field == "jid":
        return _patch_id(data, "class", index, value)
    if field in CLASS_KEY_FIELDS:
        return _patch_label_field(data, off + CLASS_KEY_FIELDS[field], (value or "").strip() or None, append=True)
    if field in CLASS_LINK_FIELDS:
        return _patch_label_field(data, off + CLASS_LINK_FIELDS[field], (value or "").strip() or None,
                                  append=False)
    if field == "weapon_ranks":
        if value is None:
            raise ValueError("A class needs a weapon rank string.")
        return _patch_label_field(data, off + CLASS_RANKS_OFFSET, _weapon_rank_string(value), append=True)
    if field == "categories":
        tokens = [_item_token(t, ITEM_CATEGORY_TOKENS, "category") for t in value or []]
        tokens = list(dict.fromkeys(t for t in tokens if t))
        if len(tokens) > CLASS_CATEGORY_SLOTS:
            raise ValueError(f"a class has room for {CLASS_CATEGORY_SLOTS} categories, not {len(tokens)}")
        tokens += [None] * (CLASS_CATEGORY_SLOTS - len(tokens))
        for slot, token in enumerate(tokens):
            data = _patch_label_field(data, off + 0x2C + 4 * slot, token, append=True)
        return data
    out = bytearray(data)
    if field in CLASS_BYTE_FIELDS:
        out[off + CLASS_BYTE_FIELDS[field]] = _byte(value)
    elif field == "movement_type":
        if not 0 <= int(value) < len(MOVEMENT_TYPE_NAMES):
            raise ValueError(f"Movement type {value} is not 0-{len(MOVEMENT_TYPE_NAMES) - 1}.")
        out[off + CLASS_MOVE_TYPE_OFFSET] = int(value)
    elif re.fullmatch(r"(cap|base_stat|growth|growth_modifier)[0-7]", field):
        name, i = field[:-1], int(field[-1])
        if name == "growth_modifier":
            out[off + 0x5C + i] = _byte(value, -128, 127)
        else:
            base = {"cap": CLASS_CAPS_OFFSET, "base_stat": CLASS_BASE_STAT_OFFSET, "growth": CLASS_GROWTH_OFFSET}[name]
            out[off + base + i] = _byte(value)
    else:
        raise ValueError(f"Unknown class field {field!r}")
    return bytes(out)


def _label_pointer(data: bytes, label: str, *, append: bool) -> tuple[bytes, int]:
    """The pointer value for ``label`` (see :func:`_label_offset`), else
    (``append``) a new copy added to the pool."""
    ptr = _label_offset(data, label, pool_only=append)
    if ptr is not None:
        return data, ptr
    if not append:
        raise ValueError(f"Label {label!r} not found anywhere in this file.")
    return _append_label(data, label)


def _item_token(value: Optional[str], allowed, what: str, *, required: bool = False) -> Optional[str]:
    value = (value or "").strip() or None
    if value is None:
        if required:
            raise ValueError(f"An item needs a {what}.")
        return None
    if value not in allowed:
        raise ValueError(f"{value!r} is not a {what} the game knows.")
    return value


#: Byte fields of an item record: offset, lowest and highest value.
ITEM_BYTE_FIELDS = {
    "uses": (0x42, 0, 255), "might": (0x43, 0, 255), "hit": (0x44, 0, 255), "weight": (0x45, 0, 255),
    "crit": (0x46, 0, 255), "min_range": (0x47, 0, 255), "max_range": (0x48, 0, 255), "icon": (0x49, 0, 255),
    "weapon_exp": (0x4A, 0, 255), "trail_color": (0x5D, 0, len(ITEM_TRAIL_COLORS) - 1),
}
ITEM_BYTE_FIELDS.update({f"stat_bonus{i}": (0x4B + i, -128, 127) for i in range(len(ITEM_STAT_BONUS_NAMES))})
ITEM_BYTE_FIELDS.update({f"growth_bonus{i}": (0x55 + i, -128, 127) for i in range(len(STAT_NAMES))})


def patch_item_field(data: bytes, index: int, field: str, value) -> bytes:
    """Return a copy of data with one field of one item record overwritten.

    - ``iid``: the item's ID; a new one is added to the string pool, one
      another item already has is refused;
    - ``miid``, ``help_key``, ``effect``, ``weapon_effect``: an existing
      label, or None;
    - ``weapon_type``, ``attack_type``: a token of :data:`ITEM_WEAPON_TYPES`;
      ``rank``: a token of :data:`ITEM_RANKS` or None;
    - ``properties`` (up to 6 tokens of :data:`ITEM_PROPERTY_TOKENS` /
      :data:`ITEM_IGNORED_PROPERTY_TOKENS`) and ``categories`` (up to 2 of
      :data:`ITEM_CATEGORY_TOKENS`): a list, written to the slots in order;
    - ``cost`` (0-65535) and the :data:`ITEM_BYTE_FIELDS` (ints; the stat
      and growth bonuses are signed).

    Tokens missing from the file's string pool are added to it."""
    off = table_start(data, "item") + index * ITEM_RECORD_SIZE
    if field in ITEM_BYTE_FIELDS:
        position, low, high = ITEM_BYTE_FIELDS[field]
        if not low <= int(value) <= high:
            raise ValueError(f"must be {low} to {high}")
        out = bytearray(data)
        out[off + position] = int(value) & 0xFF
        return bytes(out)
    if field == "cost":
        if not 0 <= int(value) <= 0xFFFF:
            raise ValueError("must be 0 to 65535")
        out = bytearray(data)
        struct.pack_into(">H", out, off + 0x40, int(value))
        return bytes(out)

    weapon_types = [token for token, _ in ITEM_WEAPON_TYPES]
    if field in ("properties", "categories"):
        if field == "properties":
            first, slots, allowed = 0x18, ITEM_PROPERTY_SLOTS, set(ITEM_PROPERTY_TOKENS) | set(ITEM_IGNORED_PROPERTY_TOKENS)
        else:
            first, slots, allowed = 0x30, ITEM_CATEGORY_SLOTS, set(ITEM_CATEGORY_TOKENS)
        tokens = [_item_token(t, allowed, "property" if field == "properties" else "category") for t in value or []]
        tokens = list(dict.fromkeys(t for t in tokens if t))
        if len(tokens) > slots:
            raise ValueError(f"an item has room for {slots} {field}, not {len(tokens)}")
        # tokens the item keeps stay in their slot; new ones take the free slots
        current = getattr(_read_item(data, index), field)
        wanted = [t if t in tokens else None for t in current]
        for token in tokens:
            if token not in wanted:
                wanted[wanted.index(None)] = token
        for slot, (old, new) in enumerate(zip(current, wanted)):
            if old != new:
                data = _patch_item_pointer(data, off + first + 4 * slot, new, append=True)
        return data
    if field in ("weapon_type", "attack_type"):
        return _patch_item_pointer(data, off + (0x0C if field == "weapon_type" else 0x10),
                                   _item_token(value, weapon_types, "weapon type", required=True), append=True)
    if field == "rank":
        return _patch_item_pointer(data, off + 0x14, _item_token(value, [r for r, _ in ITEM_RANKS], "rank"),
                                   append=True)
    if field == "iid":
        iid = (value or "").strip()
        if not iid:
            raise ValueError("An item needs an ID.")
        if not iid.isascii() or not iid.isprintable() or " " in iid:
            raise ValueError("An item ID is plain ASCII with no spaces.")
        others = [it for it in read_fe8data(data).items if it.iid == iid and it.index != index]
        if others:
            raise ValueError(f"item {others[0].index} already has the ID {iid}.")
        return _patch_item_pointer(data, off, iid, append=True)
    pointer_offsets = {"miid": 0x04, "help_key": 0x08, "effect": 0x38, "weapon_effect": 0x3C}
    if field not in pointer_offsets:
        raise ValueError(f"Unknown item field {field!r}")
    return _patch_item_pointer(data, off + pointer_offsets[field], (value or "").strip() or None, append=False)


def _patch_item_pointer(data: bytes, offset: int, label: Optional[str], *, append: bool) -> bytes:
    return _patch_label_field(data, offset, label, append=append)


#: Skill pointer fields naming a string resolved elsewhere (added when new).
SKILL_KEY_FIELDS = {"japanese_name": 0x04, "msid": 0x08, "help_key": 0x0C, "help2_key": 0x10, "effect": 0x14}
SKILL_BYTE_FIELDS = {"param0": 0x19, "param1": 0x1A, "param2": 0x1B}


def patch_skill_field(data: bytes, index: int, field: str, value) -> bytes:
    """Return a copy of data with one field of one skill record overwritten.
    ``field`` is one of:

    - ``sid``: the skill's ID, unique among skills; the record's own ``SID_``
      symbol is renamed with it (the engine matches skills by this name);
    - ``japanese_name``, ``msid``, ``help_key``, ``help2_key``, ``effect``: a
      label (added to the string pool when new) or None;
    - ``param0`` (icon), ``param1`` (capacity cost), ``param2`` (has a
      scroll, never read): 0-255;
    - ``restricted_to``: the PID_/JID_ labels the skill is exclusive to
      (each must exist; [] = anyone), kept with its count byte (0x1C);
    - ``skill_items``: [] or [the IID_ of the scroll that teaches it]; the
      unread "has a scroll" byte follows it.

    The record's own index (0x18) is not editable: the engine refers to
    skills by position."""
    off = table_start(data, "skill") + index * SKILL_RECORD_SIZE
    if field == "sid":
        new = (value or "").strip()
        if not new.startswith("SID_") or len(new) == 4:
            raise ValueError("A skill ID starts with SID_.")
        old = _read_skill(data, index).sid
        skills = read_fe8data(data).skills
        if any(sk.sid == new and sk.index != index for sk in skills):
            raise ValueError(f"Another skill already has the ID {new}.")
        if not new.isascii() or not new.isprintable() or " " in new:
            raise ValueError("An ID is plain ASCII with no spaces.")
        data = _patch_label_field(data, off, new, append=True)
        if old and old != new and old in symbol_offsets(data):
            data = rename_symbol(data, old, new)
        return data
    if field in SKILL_KEY_FIELDS:
        return _patch_label_field(data, off + SKILL_KEY_FIELDS[field], (value or "").strip() or None, append=True)
    if field in SKILL_BYTE_FIELDS:
        out = bytearray(data)
        out[off + SKILL_BYTE_FIELDS[field]] = _byte(value)
        return bytes(out)
    if field == "restricted_to":
        labels = [str(v).strip() for v in value or [] if str(v).strip()]
        if len(labels) > 255:
            raise ValueError("A restriction list holds at most 255 labels.")
        data = _write_label_list(data, off + 0x24, data[off + 0x1C], labels)
        out = bytearray(data)
        out[off + 0x1C] = len(labels)
        return bytes(out)
    if field == "skill_items":
        labels = [str(v).strip() for v in value or [] if str(v).strip()]
        if len(labels) > 1:
            raise ValueError("A skill is taught by at most one scroll.")
        old_count = 1 if struct.unpack_from(">I", data, off + 0x20)[0] else 0
        data = _write_label_list(data, off + 0x20, old_count, labels)
        out = bytearray(data)
        out[off + 0x1B] = 1 if labels else 0
        return bytes(out)
    raise ValueError(f"Unknown skill field {field!r}")


def _write_label_list(data: bytes, field: int, old_count: int, labels: list[str]) -> bytes:
    """Point the list field at absolute ``field`` to a list of ``labels``
    (each an existing label). The old list is rewritten in place when it is
    long enough and no other field points at it; otherwise a new list is
    appended to the data section."""
    pointers = []
    for label in labels:
        data, ptr = _label_pointer(data, label, append=False)
        pointers.append(ptr)
    old = struct.unpack_from(">I", data, field)[0]
    listed = listed_pointer_fields(data)
    shared = old and any(f != field and struct.unpack_from(">I", data, f)[0] == old for f in listed)
    if not pointers:
        out = bytearray(data)
        _pack_pointer(out, field, 0)
        return bytes(out)
    if old and not shared and len(pointers) <= old_count:
        out = bytearray(data)
        base = HEADER_SIZE + old
        for i in range(old_count):
            _pack_pointer(out, base + 4 * i, pointers[i] if i < len(pointers) else 0)
        return bytes(out)
    data, ptr = append_block(data, struct.pack(f">{len(pointers)}I", *pointers), range(0, 4 * len(pointers), 4))
    out = bytearray(data)
    _pack_pointer(out, field, ptr)
    return bytes(out)


def _patch_pointer_field(data: bytes, offset: int, label: Optional[str]) -> bytes:
    return _patch_label_field(data, offset, label, append=False)


#: Record tables: kind -> (symbol, record size, vanilla first-record offset
#: or None). The symbol names the count word; the records follow it.
TABLES = {
    "character": ("PersonData", CHARACTER_RECORD_SIZE, CHARACTER_TABLE_OFFSET),
    "class": ("JobData", CLASS_RECORD_SIZE, CLASS_TABLE_OFFSET),
    "item": ("ItemData", ITEM_RECORD_SIZE, ITEM_TABLE_OFFSET),
    "skill": ("SkillData", SKILL_RECORD_SIZE, SKILL_TABLE_OFFSET),
    "chapter": ("ChapterData", CHAPTER_RECORD_SIZE, None),
}
#: Pointer fields of each record kind (record-relative), including ones that
#: are null in some records and so absent from the pointer list.
RECORD_POINTER_FIELDS = {
    "character": tuple(range(0x00, 0x30, 4)),
    "class": (0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38),
    "item": tuple(range(0x00, 0x40, 4)),
    "skill": (0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x20, 0x24),  # 0x20/0x24: scroll and restriction lists
    "chapter": tuple(range(0x00, 0x3C, 4)) + (0x44, 0x48, 0x4C, 0x50),
}
#: kind -> (vanilla first-record offset, record size); kept for callers that
#: only need the size.
RECORD_TABLES = {kind: (default, size) for kind, (_symbol, size, default) in TABLES.items()}
#: Tables the engine binds to a fixed number of records (FE8DATA_NOTES.md
#: §4.7): SkillData is looped to a literal 98 and indexed by literal skill
#: ids, so its records can be edited but not added, removed or moved.
FIXED_TABLES = ("skill",)
#: The 1-based record numbers of these tables are what a save stores
#: (``deserialize_unit_slot_from_stream``): removing or moving a record
#: renumbers the ones after it, so saves made before the change load other
#: records. Appending is safe.
SAVED_BY_NUMBER = ("character", "class", "item")


def table_start(data: bytes, kind: str) -> int:
    """Absolute offset of a table's first record, 4 bytes past its symbol
    (the count word). A bare table without a symbol table (the tests'
    synthetic files) uses the vanilla offset."""
    symbol, _size, default = TABLES[kind]
    try:
        offset = symbol_offsets(data).get(symbol)
    except (struct.error, ValueError, IndexError):
        offset = None
    if offset is None:
        if default is None:
            raise ValueError(f"FE8Data.bin has no {symbol} symbol.")
        return default
    return HEADER_SIZE + offset + 4


def table_count(data: bytes, kind: str) -> int:
    """The count word of a table."""
    return struct.unpack_from(">I", data, table_start(data, kind) - 4)[0]


def _complete_container(data) -> bool:
    size, data_size, count = struct.unpack_from(">III", data, 0)
    return size == len(data) and HEADER_SIZE + data_size + 4 * count <= len(data)


def listed_pointer_fields(data: bytes) -> set[int]:
    """Absolute offsets of every field on the container's pointer list."""
    if not _complete_container(data):
        return set()
    return {HEADER_SIZE + f for f in pointer_list(data)[1]}


def pointer_list(data) -> tuple[int, list[int]]:
    """Absolute start of the pointer list, and its data-relative entries."""
    _size, data_size, count = struct.unpack_from(">III", data, 0)
    start = HEADER_SIZE + data_size
    return start, list(struct.unpack_from(f">{count}I", data, start))


def write_pointer_list(data, listed: list[int]) -> bytearray:
    """Replace the pointer list (it may change length; the symbol table after
    it holds data-relative offsets and moves with it)."""
    start, old = pointer_list(data)
    listed = sorted(set(listed))
    out = bytearray(data[:start]) + struct.pack(f">{len(listed)}I", *listed) + data[start + 4 * len(old):]
    struct.pack_into(">I", out, 0, len(out))
    struct.pack_into(">I", out, 8, len(listed))
    return out


def _symbol_entries(data) -> list[tuple[int, int, str]]:
    """(absolute table position, data-relative offset, name) of every symbol."""
    _size, data_size, pointer_count, symbol_count = struct.unpack_from(">IIII", data, 0)
    table = HEADER_SIZE + data_size + 4 * pointer_count
    names = table + 8 * symbol_count
    result = []
    for i in range(symbol_count):
        offset, name_offset = struct.unpack_from(">II", data, table + 8 * i)
        end = data.index(b"\x00", names + name_offset)
        result.append((table + 8 * i, offset, bytes(data[names + name_offset:end]).decode("ascii", errors="replace")))
    return result


def set_symbol(data: bytearray, name: str, data_offset: int) -> None:
    """Point symbol ``name`` at ``data_offset`` (data-relative), in place."""
    for position, _offset, symbol in _symbol_entries(data):
        if symbol == name:
            struct.pack_into(">I", data, position, data_offset)
            return
    raise ValueError(f"FE8Data.bin has no {name} symbol.")


def rename_symbol(data: bytes, old: str, new: str) -> bytes:
    """Rename a symbol, rebuilding the symbol-name area (the last thing in
    the file)."""
    symbols = [(offset, new if name == old else name) for _position, offset, name in _symbol_entries(data)]
    if all(name != new for _offset, name in symbols):
        raise ValueError(f"FE8Data.bin has no {old} symbol.")
    _size, data_size, pointer_count, _count = struct.unpack_from(">IIII", data, 0)
    table = HEADER_SIZE + data_size + 4 * pointer_count
    entries, names = bytearray(), bytearray()
    for offset, name in symbols:
        entries += struct.pack(">II", offset, len(names))
        names += name.encode("ascii") + b"\x00"
    out = bytearray(data[:table]) + entries + names
    struct.pack_into(">I", out, 0, len(out))
    return bytes(out)


def section_start(data: bytes, name: str) -> int:
    """Absolute offset of a named section; ValueError when it is missing."""
    offsets = symbol_offsets(data)
    if name not in offsets:
        raise ValueError(f"FE8Data.bin has no {name} symbol.")
    return HEADER_SIZE + offsets[name]


def _free_space_after(data: bytes, start: int, end: int) -> int:
    """How far the section ``start``..``end`` may grow in place: over the
    zero bytes after it that no pointer targets or lists, up to the next
    section and the end of the data section (a moved table leaves such room
    behind it, see :func:`replace_section`)."""
    if not _complete_container(data):
        return end
    listed = pointer_list(data)[1]
    bounds = [HEADER_SIZE + struct.unpack_from(">I", data, 4)[0]]
    bounds += [HEADER_SIZE + o for o in symbol_offsets(data).values() if HEADER_SIZE + o > start]
    bounds += [HEADER_SIZE + f for f in listed if HEADER_SIZE + f >= end]
    bounds += [HEADER_SIZE + t for t in (struct.unpack_from(">I", data, HEADER_SIZE + f)[0] for f in listed)
               if HEADER_SIZE + t >= end]
    limit = min(bounds)
    pos = end
    while pos < limit and data[pos] == 0:
        pos += 1
    return pos & ~3 if pos < limit else pos


def replace_section(data: bytes, name: str, old_end: int, block: bytes, pointer_fields: list[int],
                    slack: int = 0) -> bytes:
    """Write a rebuilt section. ``block`` is the new section; ``pointer_fields``
    are offsets inside it that hold pointers. It is written in place when it
    fits in the old section and the free zero bytes after it (the rest is
    zeroed), else appended to the data section, followed by ``slack`` zero
    bytes of room to grow, and the symbol repointed (the engine finds every
    section by its symbol). The old section's pointer-list entries are
    dropped either way, so no stale relocation survives."""
    start = section_start(data, name)
    old_lo, old_hi = start - HEADER_SIZE, old_end - HEADER_SIZE
    room = _free_space_after(data, start, old_end)
    out = bytearray(data)
    _, listed = pointer_list(out)
    listed = [p for p in listed if not (old_lo <= p < old_hi)]
    out[start:old_end] = bytes(old_end - start)
    if len(block) <= room - start:
        base = start
        out[start:start + len(block)] = block
    else:
        out, base = _append_data(out, bytes(block) + bytes(slack))
        set_symbol(out, name, base - HEADER_SIZE)
    listed += [base - HEADER_SIZE + f for f in pointer_fields]
    return bytes(write_pointer_list(out, listed))


def _append_data(data, block: bytes) -> tuple[bytearray, int]:
    """``data`` with ``block`` appended to the data section (word-aligned),
    and the block's absolute offset. The pointer list and symbol table after
    the data section hold data-relative offsets, so they move unchanged."""
    file_size, data_size = struct.unpack_from(">II", data, 0)
    pad = -data_size % 4
    base = HEADER_SIZE + data_size + pad
    added = bytes(pad) + bytes(block) + bytes(-len(block) % 4)
    end = HEADER_SIZE + data_size
    out = bytearray(data[:end]) + added + data[end:]
    struct.pack_into(">II", out, 0, file_size + len(added), data_size + len(added))
    return out, base


def append_block(data: bytes, block: bytes, pointer_fields=()) -> tuple[bytes, int]:
    """Append a data block (a label list...) whose ``pointer_fields`` hold
    pointers; returns the new file and the block's pointer value."""
    out, base = _append_data(bytearray(data), block)
    if pointer_fields:
        _, listed = pointer_list(out)
        out = write_pointer_list(out, listed + [base - HEADER_SIZE + f for f in pointer_fields])
    return bytes(out), base - HEADER_SIZE


def record_bytes(data: bytes, kind: str, index: int) -> bytes:
    size = TABLES[kind][1]
    off = table_start(data, kind) + index * size
    return data[off : off + size]


def protected_record_words(data: bytes, kind: str, index: int) -> set[int]:
    """Record-relative offsets of the 4-byte words raw editing must leave
    alone: the known pointer fields, and any word on the pointer list (the
    loader relocates those, so a hand-typed value there would be wrong)."""
    size = TABLES[kind][1]
    off = table_start(data, kind) + index * size
    listed = {f - off for f in listed_pointer_fields(data) if off <= f < off + size}
    return set(RECORD_POINTER_FIELDS[kind]) | listed


def patch_record_bytes(data: bytes, kind: str, index: int, new: bytes) -> bytes:
    """Overwrite one whole record with ``new`` (same size). Raises ValueError
    when a protected word (see :func:`protected_record_words`) would change:
    pointers are edited through their own fields."""
    size = TABLES[kind][1]
    if len(new) != size:
        raise ValueError(f"A {kind} record is {size} bytes, not {len(new)}.")
    off = table_start(data, kind) + index * size
    old = data[off : off + size]
    for word in sorted(protected_record_words(data, kind, index)):
        if old[word : word + 4] != new[word : word + 4]:
            raise ValueError(f"Bytes 0x{word:02X}-0x{word + 3:02X} are a pointer field; "
                             "change it with its own field instead.")
    return data[:off] + bytes(new) + data[off + size :]


# -- adding, removing and moving records -------------------------------------------------

@dataclass
class RawRecord:
    """One table record as bytes, plus which of its words are on the pointer
    list (record-relative): the loader relocates exactly those."""
    raw: bytes
    pointers: frozenset


def read_table(data: bytes, kind: str) -> list[RawRecord]:
    size = TABLES[kind][1]
    start = table_start(data, kind)
    listed = listed_pointer_fields(data)
    rows = []
    for i in range(table_count(data, kind)):
        off = start + i * size
        rows.append(RawRecord(data[off:off + size], frozenset(f - off for f in listed if off <= f < off + size)))
    return rows


def write_table(data: bytes, kind: str, rows: list[RawRecord]) -> bytes:
    """Rebuild a table from ``rows`` (count word + records). The table stays
    in place when it fits, else moves to the end of the data section."""
    count = table_count(data, kind)
    if kind in FIXED_TABLES and len(rows) != count:
        raise ValueError(f"The game is bound to the {count} {kind} records: "
                         "they can be edited but not added or removed.")
    symbol, size, _default = TABLES[kind]
    start = table_start(data, kind) - 4
    block = bytearray(struct.pack(">I", len(rows)))
    pointers = []
    for row in rows:
        if len(row.raw) != size:
            raise ValueError(f"A {kind} record is {size} bytes, not {len(row.raw)}.")
        pointers += [len(block) + p for p in sorted(row.pointers)]
        block += row.raw
    return replace_section(data, symbol, start + 4 + count * size, bytes(block), pointers, slack=8 * size)


#: The ID field (record-relative pointer, prefix) of each kind that has one.
RECORD_ID_FIELDS = {"character": (0x00, "PID_"), "class": (0x00, "JID_"), "item": (0x00, "IID_")}


def add_record(data: bytes, kind: str, new_id: Optional[str] = None,
               copy_from: Optional[int] = None) -> tuple[bytes, int]:
    """Append a record: a copy of record ``copy_from``, or an empty one.
    Kinds with an ID field need ``new_id`` (a label no record of that kind
    has yet; added to the string pool). A new chapter gets the lowest
    free story chapter id (33-89, see below). Returns the file and the new record's index."""
    rows = read_table(data, kind)
    size = TABLES[kind][1]
    if kind in RECORD_ID_FIELDS:
        prefix = RECORD_ID_FIELDS[kind][1]
        new_id = (new_id or "").strip()
        if not new_id.startswith(prefix) or len(new_id) == len(prefix):
            raise ValueError(f"A new {kind} needs an ID starting with {prefix}.")
    if copy_from is not None:
        row = rows[copy_from]
    else:
        row = RawRecord(bytes(size), frozenset())
    if kind == "chapter":
        # 32 is "game cleared" (the ending plays) and 90+ are trial maps, so story ids come
        # from 33-89 first (chapters.NEW_CHAPTER_IDS)
        used = {r.raw[0x3C] for r in rows}
        free = next((i for i in (*range(33, 90), *range(1, 32), *range(90, 256)) if i not in used), None)
        if free is None:
            raise ValueError("Every chapter id 1-255 is taken.")
        raw = bytearray(row.raw)
        raw[0x3C] = free
        row = RawRecord(bytes(raw), row.pointers)
    index = len(rows)
    data = write_table(data, kind, rows + [row])
    if kind in RECORD_ID_FIELDS:
        data = _patch_id(data, kind, index, new_id)
    return data, index


def remove_record(data: bytes, kind: str, index: int) -> bytes:
    """Drop record ``index``; the records after it move up one number."""
    rows = read_table(data, kind)
    if not 0 <= index < len(rows):
        raise ValueError(f"No {kind} record {index}.")
    if kind in FIXED_TABLES:
        raise ValueError(f"The game is bound to the {len(rows)} {kind} records: they cannot be removed.")
    return write_table(data, kind, rows[:index] + rows[index + 1:])


def move_record(data: bytes, kind: str, index: int, new_index: int) -> bytes:
    """Move record ``index`` to position ``new_index``."""
    if kind in FIXED_TABLES:
        raise ValueError(f"The {kind} records cannot be reordered: the game refers to them by position.")
    rows = read_table(data, kind)
    row = rows.pop(index)
    rows.insert(max(0, min(new_index, len(rows))), row)
    return write_table(data, kind, rows)


def _patch_id(data: bytes, kind: str, index: int, new_id: str) -> bytes:
    """Give record ``index`` the ID ``new_id``, refusing one another record
    of the same kind already has."""
    offset, _prefix = RECORD_ID_FIELDS[kind]
    new_id = (new_id or "").strip()
    if not new_id:
        raise ValueError(f"A {kind} needs an ID.")
    if not new_id.isascii() or not new_id.isprintable() or " " in new_id:
        raise ValueError("An ID is plain ASCII with no spaces.")
    start, size = table_start(data, kind), TABLES[kind][1]
    for i in range(table_count(data, kind)):
        if i != index:
            ptr = struct.unpack_from(">I", data, start + i * size + offset)[0]
            if _resolve(data, ptr) == new_id:
                raise ValueError(f"{kind} record {i} already has the ID {new_id}.")
    return _patch_label_field(data, start + index * size + offset, new_id, append=True)


# -- the smaller sections ---------------------------------------------------------------
# Layouts from load_master_game_database (0x8001B134) and each section's
# readers; see FE8DATA_NOTES.md §4.7-4.11.

def _section_start(data: bytes, name: str) -> Optional[int]:
    offset = symbol_offsets(data).get(name)
    return None if offset is None else HEADER_SIZE + offset


def _listed_label(data: bytes, field: int, listed: set) -> Optional[str]:
    """The label a pointer field points at, or None when the field is off
    the pointer list (a null pointer)."""
    if field not in listed:
        return None
    (ptr,) = struct.unpack_from(">I", data, field)
    return _resolve(data, ptr) or _resolve_sjis(data, ptr)


def read_database_head(data: bytes) -> tuple[Optional[str], Optional[str]]:
    """``DatabaseHead``: the build time and author the loader prints to the
    debug console (``"2005/06/29 10:11:21"``, ``"金子"``). Word 0 is unread."""
    start = _section_start(data, "DatabaseHead")
    if start is None:
        return None, None
    listed = listed_pointer_fields(data)
    return _listed_label(data, start + 4, listed), _listed_label(data, start + 8, listed)


#: GameData rows (one byte per difficulty, Normal/Hard/Maniac/Easy) and their readers.
GAME_DATA_ROWS = (
    ("battle_exp_mode_bonus", "get_battle_exp_mode_bonus"),
    ("battle_exp_level_constant", "get_battle_exp_level_constant"),
    ("promotion_exp_bonus_base", "get_promotion_exp_bonus_base"),
    ("boss_exp_bonus", "get_boss_exp_bonus"),
    ("thief_exp_bonus", "get_thief_exp_bonus"),
    ("laguz_growth_bonus", "get_laguz_growth_bonus"),
    ("class_critical_bonus", "get_class_critical_bonus"),
)
DIFFICULTY_NAMES = ("Normal", "Hard", "Maniac", "Easy")  # current_difficulty_id 0-3


def read_game_data(data: bytes) -> dict[str, tuple[int, int, int, int]]:
    """``GameData``: seven rows of four difficulty bytes, no count word."""
    start = _section_start(data, "GameData")
    if start is None:
        return {}
    return {name: tuple(data[start + 4 * i : start + 4 * i + 4]) for i, (name, _) in enumerate(GAME_DATA_ROWS)}


def read_group_names(data: bytes) -> list[Optional[str]]:
    """``GroupData``: a count word, then one ``MG_`` message key per army
    group (``resolve_group_name_by_index``); group 0 has none."""
    start = _section_start(data, "GroupData")
    if start is None:
        return []
    (count,) = struct.unpack_from(">I", data, start)
    listed = listed_pointer_fields(data)
    return [_listed_label(data, start + 4 + 4 * i, listed) for i in range(count)]


def read_battle_skies(data: bytes) -> list[Optional[str]]:
    """``BattleSkyData``: a count byte (padded to a word), then one sky
    name per map weather id (``get_battle_sky_name``)."""
    start = _section_start(data, "BattleSkyData")
    if start is None:
        return []
    listed = listed_pointer_fields(data)
    return [_listed_label(data, start + 4 + 4 * i, listed) for i in range(data[start])]


@dataclass
class BattleTerrainRow:
    map_name: Optional[str]  # the map this row applies to ("bmap01"); row 0 is the default
    scenes: list  # one battle-scene map name per terrain type (77), None = use row 0's


def read_battle_terrain(data: bytes) -> list[BattleTerrainRow]:
    """``BattleTerrData``: u16 column count (the 77 terrain types), u16 row
    count, then per row a map name and one battle-scene name per terrain
    type. ``get_battle_terrain_scene_name`` finds the row by the current map's
    name and falls back to row 0's entry for a null one."""
    start = _section_start(data, "BattleTerrData")
    if start is None:
        return []
    columns, rows = struct.unpack_from(">HH", data, start)
    listed = listed_pointer_fields(data)
    result = []
    for r in range(rows):
        base = start + 4 + r * (columns + 1) * 4
        result.append(BattleTerrainRow(
            _listed_label(data, base, listed),
            [_listed_label(data, base + 4 + 4 * c, listed) for c in range(columns)],
        ))
    return result


@dataclass
class ChapterRecord:
    index: int
    offset: int
    title_key: Optional[str]  # 0x00, "MCT01" - chapter title key (resolve_ui_string_or_default)
    map_name: Optional[str]  # 0x04, "bmap01" - zmap/<name>, also the BattleTerrData row key
    script: Optional[str]  # 0x08, "C01" - Scripts/<name>.cmb
    message: Optional[str]  # 0x0C, "C01" - mess/<name>.m; None = no chapter message file
    bgm: Optional[str]  # 0x10, map music
    objectives: list  # 0x14-0x20, four text slots: goal, (unused), loss ("ML_共通"), second goal line
    hard_objectives: list  # 0x24-0x2C, Hard overrides of slots 0, 1 and 3 (None = keep Normal)
    maniac_objectives: list  # 0x30-0x38, Maniac overrides of slots 0, 1 and 3
    chapter_id: int  # 0x3C, the id find_chapter_record_by_id matches (>= 90: trial maps)
    enemy_bonus_levels: tuple  # 0x3D-0x40, levels added to auto-levelled enemies, by current_difficulty_id (0-3); 0x41-0x43 pad
    base_background: Optional[str]  # 0x44, preparation/base screen background (RID_)
    scene_map: Optional[str]  # 0x48, map of the class-change scene
    scene_sky: Optional[str]  # 0x4C, sky of the class-change scene (a BattleSkyData name)
    talk_background: Optional[str]  # 0x50, default conversation background (RID_)
    trial_turn_grades: tuple  # 0x54-0x57, trial maps: most turns for grade A, B, C, D
    trial_loss_grades: tuple  # 0x58-0x5B, trial maps: most units lost for grade A, B, C, D
    trial_score_grades: tuple  # 0x5C-0x5F, trial maps: fewest player kills on the map (unit +0x22C) for A, B, C, D


def read_chapter_data(data: bytes) -> list[ChapterRecord]:
    """``ChapterData``: a count word, then 0x60-byte chapter records."""
    start = _section_start(data, "ChapterData")
    if start is None:
        return []
    (count,) = struct.unpack_from(">I", data, start)
    listed = listed_pointer_fields(data)
    result = []
    for i in range(count):
        off = start + 4 + i * CHAPTER_RECORD_SIZE
        label = lambda o: _listed_label(data, off + o, listed)  # noqa: E731
        rec = data[off : off + CHAPTER_RECORD_SIZE]
        result.append(ChapterRecord(
            index=i, offset=off, title_key=label(0x00), map_name=label(0x04), script=label(0x08),
            message=label(0x0C), bgm=label(0x10),
            objectives=[label(0x14 + 4 * k) for k in range(4)],
            hard_objectives=[label(o) for o in (0x24, 0x28, 0x2C)],
            maniac_objectives=[label(o) for o in (0x30, 0x34, 0x38)],
            chapter_id=rec[0x3C], enemy_bonus_levels=tuple(rec[0x3D:0x41]),
            base_background=label(0x44), scene_map=label(0x48), scene_sky=label(0x4C),
            talk_background=label(0x50),
            trial_turn_grades=tuple(rec[0x54:0x58]), trial_loss_grades=tuple(rec[0x58:0x5C]),
            trial_score_grades=tuple(rec[0x5C:0x60]),
        ))
    return result


# -- writers for the smaller sections ----------------------------------------------------

def patch_database_head(data: bytes, build_time: Optional[str], author: Optional[str]) -> bytes:
    """``DatabaseHead`` words 1-2: the build time and author strings the
    loader prints to the debug console (no effect in game)."""
    start = section_start(data, "DatabaseHead")
    data = _patch_label_field(data, start + 4, (build_time or "").strip() or None, append=True)
    return _patch_label_field(data, start + 8, (author or "").strip() or None, append=True)


def patch_game_data(data: bytes, row: str, difficulty: int, value: int) -> bytes:
    """Set one ``GameData`` byte: row ``row`` (a :data:`GAME_DATA_ROWS`
    name) for ``difficulty`` (0-3, :data:`DIFFICULTY_NAMES` order)."""
    names = [name for name, _reader in GAME_DATA_ROWS]
    if row not in names:
        raise ValueError(f"Unknown GameData row {row!r}")
    if not 0 <= difficulty < len(DIFFICULTY_NAMES):
        raise ValueError(f"Difficulty {difficulty} is not 0-3.")
    out = bytearray(data)
    out[section_start(data, "GameData") + 4 * names.index(row) + difficulty] = _byte(value)
    return bytes(out)


def _write_label_table(data: bytes, section: str, header: bytes, old_end: int,
                       labels: list[Optional[str]]) -> bytes:
    """Rebuild a section made of ``header`` then one label pointer per entry
    (None = null); new labels are added to the string pool."""
    block = bytearray(header)
    pointers = []
    for label in labels:
        label = (label or "").strip() or None
        if label is None:
            block += bytes(4)
            continue
        data, ptr = _label_pointer(data, label, append=True)
        pointers.append(len(block))
        block += struct.pack(">I", ptr)
    return replace_section(data, section, old_end, bytes(block), pointers)


def write_group_names(data: bytes, keys: list[Optional[str]]) -> bytes:
    """Rebuild ``GroupData`` from one ``MG_`` army key per group id (id 0
    has none). Dispos name groups by id, so ids must keep their meaning."""
    start = section_start(data, "GroupData")
    old_end = start + 4 + 4 * struct.unpack_from(">I", data, start)[0]
    return _write_label_table(data, "GroupData", struct.pack(">I", len(keys)), old_end, list(keys))


def write_battle_skies(data: bytes, names: list[Optional[str]]) -> bytes:
    """Rebuild ``BattleSkyData`` from one sky name per map weather id."""
    if len(names) > 255:
        raise ValueError("BattleSkyData holds at most 255 skies (a count byte).")
    start = section_start(data, "BattleSkyData")
    old_end = start + 4 + 4 * data[start]
    return _write_label_table(data, "BattleSkyData", bytes([len(names), 0, 0, 0]), old_end, list(names))


def write_battle_terrain(data: bytes, rows: list[BattleTerrainRow]) -> bytes:
    """Rebuild ``BattleTerrData``. Row 0 is the default the others fall back
    to; the rest are found by map name, so any row can be added or removed."""
    start = section_start(data, "BattleTerrData")
    columns, old_rows = struct.unpack_from(">HH", data, start)
    old_end = start + 4 + old_rows * (columns + 1) * 4
    labels = []
    for row in rows:
        if len(row.scenes) != columns:
            raise ValueError(f"A battle-terrain row has {columns} terrain columns, not {len(row.scenes)}.")
        labels += [row.map_name] + list(row.scenes)
    return _write_label_table(data, "BattleTerrData", struct.pack(">HH", columns, len(rows)), old_end, labels)


#: Chapter record fields: pointer fields (a label or None) and byte fields.
CHAPTER_POINTER_FIELDS = {
    "title_key": 0x00, "map_name": 0x04, "script": 0x08, "message": 0x0C, "bgm": 0x10,
    **{f"objective{i}": 0x14 + 4 * i for i in range(4)},
    **{f"hard_objective{i}": 0x24 + 4 * i for i in range(3)},
    **{f"maniac_objective{i}": 0x30 + 4 * i for i in range(3)},
    "base_background": 0x44, "scene_map": 0x48, "scene_sky": 0x4C, "talk_background": 0x50,
}
CHAPTER_BYTE_FIELDS = {
    **{f"enemy_bonus_level{i}": 0x3D + i for i in range(4)},
    **{f"trial_turn_grade{i}": 0x54 + i for i in range(4)},
    **{f"trial_loss_grade{i}": 0x58 + i for i in range(4)},
    **{f"trial_score_grade{i}": 0x5C + i for i in range(4)},
}


def patch_chapter_field(data: bytes, index: int, field: str, value) -> bytes:
    """Return a copy of data with one field of one ``ChapterData`` record
    overwritten: a :data:`CHAPTER_POINTER_FIELDS` name (a label, added to
    the string pool when new, or None), a :data:`CHAPTER_BYTE_FIELDS` name
    (0-255), or ``chapter_id`` (0-255, unique: ``find_chapter_record_by_id``
    matches it)."""
    off = table_start(data, "chapter") + index * CHAPTER_RECORD_SIZE
    if field in CHAPTER_POINTER_FIELDS:
        return _patch_label_field(data, off + CHAPTER_POINTER_FIELDS[field], (value or "").strip() or None,
                                  append=True)
    out = bytearray(data)
    if field in CHAPTER_BYTE_FIELDS:
        out[off + CHAPTER_BYTE_FIELDS[field]] = _byte(value)
    elif field == "chapter_id":
        value = _byte(value)
        others = [c.index for c in read_chapter_data(data) if c.chapter_id == value and c.index != index]
        if others:
            raise ValueError(f"Chapter record {others[0]} already has the id {value}.")
        out[off + 0x3C] = value
    else:
        raise ValueError(f"Unknown chapter field {field!r}")
    return bytes(out)


def patch_terrain_names(data: bytes, index: int, name: Optional[str] = None,
                        name_key: Optional[str] = None) -> bytes:
    """Set terrain type ``index``'s Japanese name (map tiles name their
    terrain by this string) and/or its display-name key (``MT_...``). A None
    argument leaves that field alone; new strings are added to the pool."""
    record = section_start(data, "TerrainData") + 4 + 12 * index
    if name is not None:
        if not name.strip():
            raise ValueError("A terrain type needs a name.")
        data = _patch_label_field(data, record, name.strip(), append=True)
    if name_key is not None:
        data = _patch_label_field(data, record + 4, name_key.strip() or None, append=True)
    return data
