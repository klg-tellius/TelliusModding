---
id: "modding-classes"
title: "Create, understand, and test a class"
description: "A field-by-field guide to classes, promotion, weapons, skills, movement, stats, categories, and models"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Classes"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/16-classes.md"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-saving-and-restoring", "modding-create-character"]
verification: ["source-reviewed", "unknown"]
---
# Create, understand, and test a class

**Route:** Game Data → Classes

## What you will make

You will copy a working unpromoted class into `JID_TUTORIAL_GUARD`, give it a distinct movement and stat identity, link it to a copied promoted class named `JID_TUTORIAL_GUARD_P`, and test the same character before and after promotion. The exercise deliberately keeps the original model and weapon family at first. That isolates class mechanics from the separate work of adding a model or weapon presentation.

By the end, you will know which class controls affect statistics, weapon access, skills, movement, fog vision, effectiveness, promotion, map appearance, and transforming units.

## Before you begin

- Complete [Create a character](10-create-character.md) and use a disposable test character rather than a story-critical unit.
- In **Game Data → Classes**, identify one unpromoted human class and its promoted partner. Choose classes whose weapon type and movement style are close to your design.
- Search the class list for `JID_TUTORIAL_GUARD` and `JID_TUTORIAL_GUARD_P`. Use different IDs if either already exists.
- Record the template classes' JIDs, displayed names, weapon ranks, movement types, skills, and promotes-to links.
- Save a project checkpoint before adding records. A new class can be removed safely during the exercise only while nothing important refers to it.

Do not begin with a laguz class, a story-promoted class, or a new battle model. Those cases add transformation, event, or presentation rules that can hide a basic class error.

## How the editor fits together

The Classes tab edits class records inside `FE8Data.bin`. Leaving a field applies it to the shared in-memory FE8Data session. **Save FE8Data.bin** writes that session; building later copies it into `system.cmp`. **Discard unsaved edits** returns the entire shared FE8Data session to its saved state, including unsaved changes made through other Game Data or character views.

A class is a shared definition. Character records and deployments refer to it by JID. The class supplies bases, caps, movement, class skills, categories, and default model identity. A named character adds personal stats, growths, skills, and optional model overrides. Changing one class therefore affects every unit that uses it.

Map and battle appearance are separate lookups:

- **Class model (AID)** is the default map-model identity when the character has no applicable personal AID.
- Battle presentation also uses `jobList.dbx` class and character/class mappings. A correct AID does not prove that a battle model exists.
- **Innate weapon** is the transformed natural weapon used by laguz-style classes; it is not an ordinary inventory grant.

## Guided walkthrough

### 1. Copy both sides of a working promotion pair

Select the unpromoted template and click **New…**. Choose the option to copy the selected record rather than create an empty record. An empty record requires every pointer and byte to be reconstructed and is inappropriate for a first class.

Set **Class ID (JID)** to `JID_TUTORIAL_GUARD`. Repeat from the promoted template and create `JID_TUTORIAL_GUARD_P`. Do not assign either class to a character yet.

**Checkpoint:** both new JIDs appear as separate records, and their original template records are unchanged.

### 2. Give the records their own text keys

Set **Name key (MJID)** and **Description key** to unused message keys created for this exercise. The fields store keys, not the displayed English text. Use the adjacent message preview to confirm that each key resolves to the intended text.

Reusing the template's key means both classes display the same shared message. Editing that shared message later renames every user of it; changing only the JID does not create a new visible name.

### 3. Link promotion in the intended direction

On `JID_TUTORIAL_GUARD`, set **Promotes to / linked class** to `JID_TUTORIAL_GUARD_P`. Use **Open ›** to inspect the target. Preserve the copied pair's link pattern on the promoted record; do not invent a self-link.

Promotion does not store a separate “+2 Strength” table. The unit is recomputed under the linked class. The difference between the old and new class bases, caps, movement, build, ranks, skills, and other properties determines the transition, while personal permanent gains remain with the unit. Generic promotion resets level to 1 and EXP to 0, halves fixed-growth accumulators, swaps class-granted skill state, raises weapon proficiencies to the new class minimums, and clamps HP to the new maximum.

### 4. Keep weapon access simple, then change one column

The nine **Weapon ranks** columns are Sword, Lance, Axe, Bow, Fire, Thunder, Wind, Staff, and Knife. Keep the template string for the first save. After the baseline test, enable one additional family in the promoted class only.

- `-` forbids the family.
- `E`, `D`, `C`, `B`, `A`, or `S` supplies the class's starting/minimum rank.
- `*` permits the family without assigning a fixed rank letter. It is not “S rank.”

For example, to make the promoted class gain bows, change only its **Bow** column from `-` to the rank appropriate for the exercise. The editor writes a new nine-character rank string when necessary, so other classes that shared the template's old string are not edited.

Weapon access still depends on the item, unit state, and engine restrictions. The class rank does not place a weapon in inventory, create its battle model, or remove named native restrictions.

### 5. Set movement and carrying identity

For the first intentional mechanical change, increase **Movement** by one on the promoted class and leave the unpromoted value unchanged. Keep **Movement type** copied from the template until the baseline passes.

Then inspect **Game Data → Terrain**. Movement type selects one terrain-cost column; Movement is the number of movement points available. A unit with Movement 7 can still be stopped by a tile whose selected-column cost is impassable. Changing from infantry to flying movement is therefore not just a label change—it changes which terrain costs the unit reads across every map.

Keep **Build (Con)** and **Weight** at their copied values for the baseline. Build is added to the character's personal build and participates in carrying and weapon-weight calculations. Weight is separate class weight data; do not use it as a substitute for Build.

Set **Vision** only after testing fog. Most ordinary classes use a small radius, while thief-like classes use a larger one. The value is a tile radius and a Torch adds its own bonus. Outside fog, changing Vision can appear to do nothing.

### 6. Design bases, caps, and growth behavior separately

The stat columns are HP, Strength, Magic, Skill, Speed, Luck, Defense, and Resistance.

1. Copy the template values into your notes.
2. Change one **Base stats** value on the unpromoted class, such as Defense +1.
3. Change the corresponding promoted base enough to make the promotion difference obvious.
4. Keep **Caps** above the expected test-unit values so a cap does not hide the change.
5. Leave **Growth %** and **Growth modifiers** unchanged until the base/promotion test passes.

Class bases combine with a character's personal stat bonuses. Luck is exceptional: the loader ignores the class Luck base and class Luck cap, and the effective Luck cap is 40. Do not use those two cells to design a class-specific Luck curve.

The two growth rows have different consumers:

- **Growth %** is the class's own eight-rate row. The app uses it when constructing and levelling a generic class combatant.
- **Growth modifiers** are signed percentage points added to a named character's personal growths while that character is in the class. A personal 45% growth with a `+5` modifier becomes 50%; a `-10` modifier becomes 35%.

Use modifiers, not the class Growth % row, when the design goal is “characters retain their personal growth identity but this class nudges it.” Values are signed from -128 to 127, while bases, caps, and class Growth % are bytes from 0 to 255. High growth does not raise a cap; it only reaches the cap sooner.

### 7. Add class abilities without confusing their ownership

The five **Innate skills** slots grant those skills to every unit in the class. Use **Open ›** to inspect a candidate skill's capacity, restrictions, and special behavior before assigning it. Some SID records represent engine properties rather than menu-visible abilities, so copying an unfamiliar hidden skill can change promotion, transformation, equipment, or movement rules.

**Occult scroll → Mastery skill** is not a sixth innate skill. The selector edits the chosen mastery skill's restriction list so an Occult scroll can teach it to this JID. Selecting Aether here does not automatically grant Aether and does not waive the scroll or capacity rules.

For the baseline, retain the template's innate skills and choose no new Occult mapping. Add one known, visible skill only after the class works without it.

### 8. Set skill capacity and effectiveness categories

**Skill capacity** is the total capacity available to learned/equipped skills. It accepts 0–255, but ordinary class values are much smaller. Raising capacity does not teach a skill; lowering it can leave an existing unit with a skill arrangement that no longer fits the intended limit.

The three **Categories** slots describe what the class is, such as armored, flying, knight, beast, dragon, or bird. Weapons use matching category tokens for effectiveness, and some skills/items inspect them. Categories do not directly change terrain movement or models. Add a category only when you intend every matching effectiveness rule to apply.

Test a category by comparing an ordinary weapon with a weapon known to be effective against that category. Keep attacker, defender, distance, and terrain identical.

### 9. Assign the class and save

Open the disposable character and set its class JID to `JID_TUTORIAL_GUARD`. Return to Classes and re-open both new records to flush any focused field. Click **Save FE8Data.bin** once for the shared session.

Close and reopen the project or navigate away and back. Confirm that the new JIDs, text keys, link, ranks, movement, and stat values reload. A value visible only before reload is not a saved result.

### 10. Compare before and after promotion

Open **Tools → Battle Simulator** and load the test character in the unpromoted class. Record level, effective stats, Build, skills, categories, weapon access, and resolved model. Use the simulator's promotion/class controls to load the promoted state and record the same fields.

Change only one variable per comparison:

1. Old class versus new class at the baseline level.
2. Unpromoted versus promoted state.
3. Original weapon family versus the newly enabled family.
4. Ordinary weapon versus effective-category weapon.
5. Default map/battle identity versus any later model override.

The simulator models documented class mechanics but cannot prove every engine-only promotion menu, story promotion, per-unit weapon-choice, transformation, or presentation behavior. Build and test those claims in Dolphin before calling the class game-verified.

## Understand every control

| Control | Input and meaning | How to choose and verify |
| --- | --- | --- |
| **New…** | Creates an empty class or copies the selected class. | Copy the nearest mechanical template. Verify the original and copy have distinct JIDs. |
| **Remove** | Deletes the selected record after reference checks. | Use only for an unneeded record; inspect every reported reference and consider existing saves. |
| **Class ID (JID)** | Unique class identifier added to the label pool. | Use a project-specific `JID_` name. Search before saving and reopen all references after renaming. |
| **Name key (MJID)** | Message key for the displayed name. | Create or select the intended message and confirm the preview; do not type display text into the key field. |
| **Description key** | Message key for class help text. | Give the class its own key when its description differs from the template. |
| **Promotes to / linked class** | Existing JID used by class-change logic. | Link an unpromoted class to the intended promoted record and test eligibility plus the resulting transition. |
| **Class model (AID)** | Default map-model identity. | Preserve a working AID initially. Verify map appearance separately from `jobList.dbx` battle resolution. |
| **Innate weapon** | Existing IID used as a transformed natural weapon. | Leave empty for ordinary human classes; inspect the item and transformation pair for laguz-style classes. |
| **Weapon ranks** | Nine choices, each one of `-*EDCBAS`. | Start from a valid template, change one family, then verify both permission and actual inventory/model availability. |
| **Innate skills 1–5** | Existing SID pointers granted by the class. | Inspect each skill first. Verify visible and hidden consequences; blank unused slots rather than duplicating a SID. |
| **Occult skill** | Rewrites mastery-skill JID restrictions. | Choose the scroll result, then test learning with the scroll; do not expect an innate grant. |
| **Movement** | 0–255 movement-point budget. | Compare nearby vanilla classes and test reachable tiles. Extreme values can break map assumptions even when accepted. |
| **Build (Con)** | 0–255 class contribution to effective build. | Compare effective Build on a real character and test weapon/carry interactions. |
| **Weight** | 0–255 class weight value. | Preserve a related class value unless a tested mechanic requires a change; do not assume it equals Build. |
| **Skill capacity** | 0–255 total capacity. | Budget against actual skill costs and test an over-capacity attempt. |
| **Vision** | 0–255 fog sight radius in tiles. | Test in a fog map, with and without a Torch. |
| **Movement type** | One of the indexed terrain-cost columns. | Open Terrain, compare the complete cost column, and test at least infantry plus one different movement type. |
| **Caps** | Eight unsigned class limits; Luck cell is ignored by the game. | Keep intended endgame stats below the cap and test a unit at the boundary. |
| **Base stats** | Eight unsigned class contributions; Luck cell is ignored by the loader. | Compare effective stats before/after class change, not the raw row alone. |
| **Growth %** | Eight unsigned class rates used for generic class levelling. | Test a generic class combatant across known levels; do not substitute these for personal-growth modifiers. |
| **Growth modifiers** | Eight signed additions to named characters' personal growths. | Calculate the effective rate and test deterministic fixed growth at a level where the difference pays out. |
| **Categories 1–3** | Up to three recognized class-category tokens. | Add only categories with an intended consumer and verify with a matching effective weapon or rule. |
| **Save FE8Data.bin** | Writes the shared Game Data session. | Save, reload the project, and re-open both the class and its referring character. |
| **Discard unsaved edits** | Reverts all unsaved changes in the shared FE8Data session. | Use only after reviewing other Game Data/character changes that share the session. |

## Things to try next

1. **Armored caster:** copy a magic class, add the armor category, lower movement appropriately, and test both magic access and armor-effective damage. Categories alone do not create armor-like terrain costs.
2. **Promotion gains a weapon family:** keep the unpromoted family unchanged and enable one promoted column. Verify rank, inventory, and battle model as three separate checks.
3. **Scout class:** raise Vision and test on a fog map. Compare without and with a Torch so the class contribution is visible.
4. **High-capacity specialist:** raise capacity and equip several known skills. Verify costs and restrictions rather than assuming capacity grants or unlocks them.
5. **Transforming class study:** copy an existing laguz pair, preserve its hidden skills and categories, and compare untransformed/transformed records plus the innate weapon. Do this only after the ordinary pair passes.

## Interactions and precedence

- Character-specific map AIDs override the class AID when present; battle models have their own class and character/class lookup.
- Personal stat bonuses combine with class bases. Luck ignores the class base and cap cells.
- Named-character level growth uses personal rates plus class growth modifiers; generic class simulation uses the class Growth % row.
- Caps trim generated gains. Raising growth without raising the cap changes when the unit reaches the ceiling, not the ceiling.
- Promotion replaces class-owned properties and retains personal permanent gains; it does more than change the JID pointer.
- `SID_EVENTCC` and transformation-related class skills alter generic promotion eligibility. Do not copy them without understanding their event path.
- Weapon rank permission, item restrictions, inventory, and battle presentation are independent gates.
- Categories are consumed by effectiveness and other rules; movement type is consumed by terrain costs. Neither substitutes for the other.
- Existing saves store mutable unit state. Test structural class changes on a fresh or disposable save as well as a loaded unit.

## Test matrix

| Case | Setup | Expected observation |
| --- | --- | --- |
| Baseline | Test character in the untouched template class | Record stats, movement, skills, ranks, categories, and models before editing. |
| Intended | Same character in `JID_TUTORIAL_GUARD`, then promote | Only documented differences appear; promoted level/EXP and class-owned properties transition correctly. |
| Boundary | Put one stat at its cap; test fog vision and one impassable terrain cost | Growth/promotion does not exceed the cap, vision has a measurable radius, and terrain remains governed by movement type. |
| Failure | Remove the promoted link or select an unusable weapon family/item combination in a disposable copy | Promotion or weapon use fails for the predicted reason; restoring the field restores behavior. |

Also test a fresh unit and an existing-save unit when the mod is intended to support existing saves. Record any difference rather than repairing the save silently.

## Troubleshooting

| Symptom | Inspect | Likely correction |
| --- | --- | --- |
| New class has the old displayed name | Name key and message preview | Create/select a distinct MJID message; a new JID does not create text. |
| Promotion is unavailable | Source level, promoted link, laguz/event-class skills, already-promoted state | Restore a valid link and use the correct generic or story promotion route. |
| Promotion gains are surprising | Both class base/cap rows and the character's personal values | Compare effective totals and the class differences before editing personal stats. |
| Unit cannot equip the enabled weapon | Rank column, item type/rank/restrictions, unit permission state, inventory | Fix the failing gate; the class column alone is not an item grant. |
| Correct stats but wrong map model | Character AID override and class AID | Clear/fix the applicable personal override or select a valid class AID. |
| Correct map model but wrong/invisible battle model | `jobList.dbx`, character/class override, required model resources | Repair the battle-model mapping and verify the model files separately. |
| Movement value changed but routes did not | Movement type and terrain cost column | Edit or select the intended terrain-cost profile; do not confuse points with costs. |
| Growth change appears ineffective | Class Growth % versus signed growth modifier, current level, caps, growth mode | Modify the row consumed by the test and choose a level where a deterministic difference appears. |
| Effective damage appears unexpectedly | Category tokens on the defender and effective tokens on the weapon | Remove unintended categories or correct the weapon's effectiveness list. |
| Edits disappear after reopening | Shared-session status and **Save FE8Data.bin** | Flush the focused field, save FE8Data.bin, then rebuild if testing the game image. |

## Save, build, and revert

Leaving a field or changing tabs applies the value to the shared FE8Data session. **Save FE8Data.bin** persists all changes in that session. To test in Dolphin, build a new image after saving; an earlier image does not update itself.

For a practice reversal, reassign the test character to its original JID, remove references to both tutorial JIDs, then use **Remove** on the copied classes and save. If other records or saves now depend on them, restore the pre-exercise project checkpoint instead of forcing deletion. **Discard unsaved edits** is safe only when every unsaved FE8Data change may be lost.

## Limits and confidence

- Class field ranges, string-copy behavior, save ownership, simulator construction, promotion-state handling, and model lookup separation are source-reviewed.
- Simulator results establish only the mechanics implemented by the simulator. They do not prove engine menus, scripted promotion scenes, all hidden skills, or battle resource loading.
- Rigged model resolution, story promotion, transforming-class behavior, and existing-save compatibility require recorded Dolphin tests for a finished mod.
- The class Growth % and signed Growth modifiers have different app/runtime consumers. If later executable evidence contradicts the documented split, update this article and the discrepancy ledger together.
- Screenshots remain pending and are not evidence of runtime correctness by themselves.

## Related tutorials and references

- Prerequisites: [Save changes and restore originals](03-saving-and-restoring.md), [Create a character](10-create-character.md)
- Continue with: [Create an item or weapon](17-items-and-weapons.md), [Edit and redistribute skills](18-skills.md), [Edit terrain and movement costs](19-terrain-types.md)
- Test with: [Simulate and render a fight](56-battle-simulator.md), [Play and rewind a chapter](58-play-chapter.md)
- System references: [Classes](../systems/classes.md), [Characters](../systems/characters.md), [Level-Up Growth](../systems/level-up-growth.md), [Skills](../systems/skills.md)
- Format references: [FE8Data.bin](../formats/fe8data.md), [ZDBX & DBX](../formats/zdbx.md)

---

[All curriculum tracks](index.md)
