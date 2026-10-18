---
id: "modding-items-and-weapons"
title: "Create, balance, and present an item or weapon"
description: "A field-by-field guide to item identity, weapon rules, combat values, restrictions, effects, bonuses, icons, and battle models"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Items", "Weapons"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/17-items-and-weapons.md"
tutorial_kind: "task"
tutorial_track: "characters-and-game-data"
tutorial_stage: "draft"
prerequisites: ["modding-saving-and-restoring", "modding-classes"]
verification: ["source-reviewed", "unknown"]
---
# Create, balance, and present an item or weapon

**Route:** Game Data → Items

## What you will make

You will copy an ordinary weapon into `IID_TUTORIAL_SPEAR`, give it independent text, increase one combat value, verify who can equip it, place it on a test unit, and make its battle presentation resolve. You will then test an effectiveness category and a custom use restriction as separate changes.

The exercise separates five systems that are easy to conflate: the item record, class/unit weapon access, inventory placement, effects, and the `xwp` battle-weapon model table.

## Before you begin

- Complete [Create, understand, and test a class](16-classes.md) and use a disposable character whose class can wield the template weapon.
- Choose a simple weapon with the intended family, attack type, range, and a visible battle model. Avoid staves, light magic, siege range, bows, laguz natural weapons, and plot-locked weapons for the first copy.
- Search for `IID_TUTORIAL_SPEAR` and choose another unique IID if it exists.
- Record the template's complete item form, icon users, resolved `xwp` model, inventory owner, and Battle Simulator forecast.
- Save a project checkpoint before adding the record.

## How the editor fits together

The Items tab edits records and custom-use rules in `FE8Data.bin`. Leaving a field applies it to the shared Game Data session; **Save FE8Data.bin** persists every unsaved change in that session. A build later copies the file into `system.cmp`.

The item record owns mechanics and references: identity, weapon/attack type, rank, combat values, uses, price, properties, effectiveness, restrictions, effects, bonuses, icon number, and trail color. It does not put itself into an inventory or guarantee a visible battle weapon.

- Characters/classes determine weapon permission and proficiency.
- Deployment, shops, scripts, or saves place item instances into inventories.
- `window/icon.tpl` owns the shared icon cell.
- `zdbx.cmp` uses `xwp/<IID without IID_>.dbx` to locate the normal battle model; forged presentation has its own lookup.
- Effect IDs refer to effect resources or handlers. A renamed IID does not create new effect code.

## Guided walkthrough

### 1. Copy the nearest mechanical template

Select the template and click **New…**, then copy the selected item. Set **Item ID (IID)** to `IID_TUTORIAL_SPEAR`. An empty record is inappropriate here because item properties, type/rank tokens, effect pointers, and model expectations must all agree.

**Checkpoint:** the copy and template are distinct list entries, while every other value still matches.

### 2. Give the copy independent text

Set **Name key (MIID)** and **Description key (MH_I)** to unused message keys and confirm their previews. These fields store references, not display text. Reusing a template key deliberately shares its message; later editing that message changes all users.

Do not infer mechanics from the description. The rank, types, properties, restrictions, and executable effect determine behavior even when the text claims something else.

### 3. Preserve type, attack type, and rank for the baseline

For the first test, retain the copied values:

- **Weapon type** decides which proficiency family it trains and which class permission is required.
- **Attack type** determines the damage-stat/resistance pairing. Fire, Thunder, Wind, and Light/staff-style attack tokens use Magic against Resistance; ordinary physical types use Strength against Defense.
- **Rank needed** is the item's proficiency threshold. `(none)` does not waive every other restriction.
- **Weapon EXP per use** is the proficiency gain awarded by a qualifying use.

A rod with Might acts as a Light spell; a rod with zero Might is a staff. Light-spell access also depends on the appropriate permission skill. Properties can impose fixed-skill or class locks in addition to rank.

### 4. Change one combat value

Increase **Might** by one and leave Hit, Crit, Weight, Uses, and Range unchanged. Save later and compare the copied weapon with its template using identical units, terrain, skills, distance, and roll mode.

The combat row contains unsigned byte values:

- **Might** contributes to attack power.
- **Hit %** contributes to hit rate.
- **Crit %** contributes to critical rate before seals and immunity.
- **Weight** interacts with effective Build and speed penalties.
- **Uses** is the maximum durability of an ordinary instance.
- **Min range / Max range** gate legal distances. Max range `255` means Magic ÷ 2 for long-range staff behavior, not 255 tiles.

Keep Min ≤ Max and test every intended distance. A forecast at range 1 does not prove a range-2 animation or targeting path.

### 5. Check price and durability together

**Cost per use** is multiplied by **Uses** to produce the ordinary shop price. If the copied weapon has 30 uses and a cost of 40, its price is 1,200. Decide whether durability or total price is the design target, calculate the other value, and confirm the editor's displayed current price.

### 6. Inspect properties and effectiveness before changing them

The **Properties** area has six storage slots. Each checkbox is an engine token such as brave/twice behavior, critical handling, special equipment locks, magic-sword behavior, or sound/effect suppression. Some preserved tokens are explicitly ignored by the game. Do not select a token from its short name alone; inspect the Items & Weapons reference and test the original item that uses it.

The **Effective against** area has two category slots. Its tokens match class categories such as armor, fly, beast, or dragon. Add one category to the copied weapon only after confirming the test defender actually carries it. Compare against the same defender with the template weapon.

Properties and effectiveness are independent. An armor-effective weapon does not automatically gain a special model, sound, or description.

### 7. Add a custom restriction as a separate experiment

Under **Custom use restriction**, choose how the listed groups combine:

- **Any** permits a unit when any listed PID, current JID, or SID matches.
- **All** requires a match from every populated group. Empty groups impose no additional requirement.

Use **Browse…** to select the tutorial character PID and leave Classes and Skills empty. Existing weapon ranks, native locks, and other item rules still apply. Save and confirm the named character can use the item while a same-class control character cannot.

Then use **Clear custom restriction** and verify both eligible characters return to the normal rank/type rules. This button removes the custom rule; it does not clear built-in restrictions encoded by properties or game code.

### 8. Preserve effects and trail color first

Keep **Use / spell effect**, **Weapon effect**, and **Attack trail colour** copied for the baseline.

- Use/spell effect drives staff, tome, or consumable presentation/behavior associated with the EID.
- Weapon effect is the weapon-side EID, commonly in an `_WP` family.
- Attack trail color selects a known palette entry; forged weapons use their forge color instead.

Only swap an EID with another effect proven to accept the same use context. A visually similar effect can have different resource, timing, target, or script assumptions.

### 9. Understand equipped and permanent bonuses

The ten **Stats** cells are HP, Strength, Magic, Skill, Speed, Luck, Defense, Resistance, Movement, and Build. Signed values from -128 to 127 apply while the item is equipped. A stat-booster item instead commits its bonuses permanently when consumed, so test the template's use path before repurposing it.

The eight **Growth %** cells are signed modifiers applied while the weapon is equipped. Test them with a deterministic fixed-growth level where the difference crosses a threshold. Raising an equipped growth modifier does not raise the class cap.

Keep all bonuses at the copied baseline during the initial Might test. Combining a stat bonus with Might would make the forecast difference ambiguous.

### 10. Choose and audit the icon

**Icon** is a byte index into the item portion of `window/icon.tpl`. Click **Choose…** to browse known cells. The preview warns when other items share the same cell. Selecting an existing number reuses its art; editing that cell under Assets changes every item sharing it.

Use a copied icon for this mechanical exercise. A distinct item identity does not require duplicating art until you want a visually different icon.

### 11. Save, place, simulate, and render

Click **Save FE8Data.bin**, reopen the item, and confirm every changed value. Add `IID_TUTORIAL_SPEAR` to the disposable unit through Deployment and save the chapter.

In Battle Simulator, compare the template and copy with identical combatants. Confirm the +1 Might result, usability, durability/range assumptions, and effectiveness case. Then use **Render fight**.

If the copied IID has no `xwp/TUTORIAL_SPEAR.dbx`, mechanics can work while the battle weapon is invisible. In **Assets → Battle Weapons / 3D Models**, copy or create the mapping from the template, inspect the normal and forged variants, and render again. Do not “fix” an invisible weapon by changing the character's body model.

## Understand every control

| Control | Input and meaning | Selection and verification |
| --- | --- | --- |
| **New… / Remove** | Add by copy/empty or delete after reference checks. | Copy the nearest kind; remove only after inventory/shop/script/save references are addressed. |
| **Item ID (IID)** | Unique item identity used by deployments, shops, scripts, saves, and `xwp` lookup. | Search before creating; verify every consumer uses the exact IID. |
| **Name key / Description key** | Shared MIID/MH_I message references. | Confirm previews and decide whether sharing is intentional. |
| **Weapon type** | Proficiency family trained and required. | Match the intended class rank column and test a user/non-user. |
| **Attack type** | Physical or magical damage channel. | Compare attack stat and target defense/resistance in the forecast. |
| **Rank needed** | Item proficiency threshold or none. | Test just below and at the threshold; other locks remain active. |
| **Weapon EXP per use** | 0–255 proficiency gain. | Record rank progress after a qualifying use. |
| **Icon / Choose…** | 0–255 shared item-icon cell. | Check the preview and sharing warning before editing art. |
| **Might, Hit, Crit, Weight** | Unsigned combat inputs. | Change one and hold units, terrain, skills, and distance constant. |
| **Uses** | Unsigned durability count. | Test decrement/break behavior appropriate to the item kind. |
| **Min / Max range** | Legal target-distance bounds; max 255 has special staff meaning. | Exercise every boundary distance, not only the forecast default. |
| **Cost per use** | 0–65,535 multiplied by Uses for shop price. | Calculate and verify the displayed total and shop transaction. |
| **Properties** | Up to six recognized or preserved tokens. | Trace a known original user and test activation plus a non-activation case. |
| **Effective against** | Up to two matching class-category tokens. | Compare ordinary/effective weapons against the same categorized defender. |
| **Match / Characters / Classes / Skills** | Custom Any/All PID/JID/SID rule. | Test matching, nonmatching, and normal rank-lock cases. |
| **Clear custom restriction** | Deletes the item's custom rule. | Reopen and confirm normal access behavior returns. |
| **Use / spell effect** | EID for use, spell, staff, or consumable context. | Verify target, timing, result, and visible effect. |
| **Weapon effect** | Weapon-side EID. | Compare the original animation/effect that uses it. |
| **Attack trail colour** | Known palette index; forge overrides it. | Render normal and forged versions separately. |
| **Stats** | Ten signed equipped/permanent-use bonus bytes. | Determine whether the template is held equipment or a consumed booster. |
| **Growth %** | Eight signed equipped growth modifiers. | Use fixed growth and a known threshold-crossing level. |
| **Save FE8Data.bin** | Writes the shared data session. | Reload the project before placing/testing the item. |

## Things to try next

1. **Anti-armor sidegrade:** trade one ordinary stat for armor effectiveness and compare both armored and unarmored defenders.
2. **Character-bound heirloom:** use a PID restriction while keeping ordinary class/rank checks, then test a second character of the same class.
3. **Longer but heavier weapon:** raise range and Weight separately to expose targeting versus doubling/speed consequences.
4. **Growth weapon:** add one growth modifier and demonstrate the exact fixed-growth level where it changes the gain.
5. **Forged presentation study:** compare normal/forged trail color, icon, and model resolution without changing mechanics.

## Interactions and precedence

- IID identity, text keys, icon cell, item mechanics, inventory instance, effect resources, and battle model table are separate owners.
- Weapon type/rank, custom restriction, property/native locks, and unit permission must all allow use.
- Attack type selects the offensive/defensive stat channel; weapon type selects proficiency. They need not be the same token.
- Equipped stat bonuses affect the current combatant; growth modifiers affect future level gains; caps can trim those gains.
- Effective categories compare item tokens with defender class categories. Similar class names do not matter.
- Shop price is Cost per use × Uses, but scripts or special shops can supply items through different paths.
- A successful forecast does not prove an `xwp` model, effect, projectile, sound, or forged variant resolves.
- Existing saves contain item instances and durability. Test structural changes with a fresh item instance and an existing one when save compatibility matters.

## Test matrix

| Case | Setup | Expected observation |
| --- | --- | --- |
| Baseline | Template weapon, recorded combatants and distance | Record access, forecast, durability, icon, model, trail, and effects. |
| Intended | Copied IID with +1 Might | Damage changes by the predicted amount; unrelated values and presentation remain stable. |
| Boundary | Minimum/maximum range, rank threshold, last use, and capped boosted stat | Each limit behaves according to its owning field. |
| Failure | Missing `xwp` table or nonmatching custom restriction in a disposable copy | Forecast/access and rendering fail independently for the predicted reason. |

## Troubleshooting

| Symptom | Inspect | Correction |
| --- | --- | --- |
| Old name/description appears | MIID/MH_I keys and previews | Create or select distinct messages; IID does not generate text. |
| Unit cannot equip item | Weapon type/rank, custom rule, properties, native locks | Identify and fix the failing gate rather than lowering every restriction. |
| Damage uses the wrong stat | Attack type | Select the intended physical/magical channel and retest. |
| Shop price is surprising | Cost per use and Uses | Recalculate their product. |
| Effectiveness never triggers | Item category and defender class category | Make the tokens match and keep the defender constant. |
| Weapon is invisible | `xwp/<name>.dbx` mapping and model file | Add/copy the battle-weapon table; do not alter the body model. |
| Icon edit changed other items | Shared icon-cell warning | Allocate/edit a distinct cell or accept documented sharing. |
| Growth/stat change seems doubled | Equipped bonus plus Might/growth modifier | Isolate one source and compare a fresh baseline. |
| Changes vanish after reopen | Shared-session status and Save FE8Data.bin | Flush the focused field, save, then rebuild for Dolphin. |

## Save, build, and revert

Leaving a field applies it to the shared FE8Data session. **Save FE8Data.bin** persists the item and custom restriction. Save Deployment, shops, model tables, icons, or other owning resources separately. Build a new image before Dolphin testing.

To remove the exercise, delete all inventories/shops/scripts that reference the IID, remove its model-table entry if newly created, then remove the item and save. Restore the checkpoint if existing saves or unknown references make targeted removal unsafe.

## Limits and confidence

- Field ranges, price calculation, shared icons, custom-rule storage, effect pointers, bonuses, and model lookup are source-reviewed.
- Battle Simulator validates the mechanics it implements; Render fight validates app asset resolution, not retail engine stability.
- Named native restrictions, unusual properties, staff/light behavior, projectiles, and new effect combinations require targeted Dolphin tests.
- A copied item reuses an existing effect. Creating a genuinely new executable item effect is Game Code work.

## Related tutorials and references

- Prerequisites: [Save changes and restore originals](03-saving-and-restoring.md), [Create and test a class](16-classes.md)
- Continue with: [Edit and redistribute skills](18-skills.md), [Set inventory, drops, rings, and flags](31-unit-inventory-and-flags.md), [Edit shops](46-shops.md)
- Presentation and testing: [Edit model budgets](54-model-budgets.md), [Simulate and render a fight](56-battle-simulator.md)
- References: [Items & Weapons](../systems/items-weapons.md), [Weapon families](../systems/weapons-swords.md), [Battle Staging](../systems/battle-staging.md), [FE8Data.bin](../formats/fe8data.md)

---

[All curriculum tracks](index.md)
