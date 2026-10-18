---
id: "modding-deployment-by-difficulty"
title: "Place and tune units by difficulty"
description: "A controlled workflow for common and difficulty files, counterpart matching, shared fields, levels, stat bonuses, and testing"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Deployment", "Difficulty", "Units"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/30-deployment-by-difficulty.md"
tutorial_kind: "task"
tutorial_track: "units-and-events"
tutorial_stage: "draft"
prerequisites: ["modding-deployment-sections", "modding-difficulty-and-armies"]
verification: ["source-reviewed", "unknown"]
---
# Place and tune units by difficulty

**Routes:** Chapter → Build → Place unit; Chapter → Deployment

## What you will make

You will add one enemy to matching Normal, Hard, and Maniac sections, keep its identity/equipment/position shared, and give each difficulty a different level and one controlled stat bonus. You will then remove the unit from one difficulty without deleting its counterparts.

The exercise clarifies which controls propagate and which remain per file. The current Build unit form treats character, class, faction, flags, position, inventory, skills, AI, and gauge as shared counterpart fields; **Level** and the eight deployment stat bonuses are intentionally edited per difficulty.

## Before you begin

Complete [Design and connect deployment sections](29-deployment-sections.md). Choose a chapter with `_n`, `_h`, and `_m` counterparts for one enemy section. Record the baseline unit counts and section names in all three files.

Pick one empty, walkable spawn cell and one test character/class combination. Record chapter **Enemy levels +** values so you can distinguish deployment level from chapter autolevel additions.

Avoid the common file for this exercise. A common record exists on every difficulty by definition and does not expose separate difficulty rows.

## How the editor fits together

The Build top selector chooses the deployment file currently displayed. The **Place unit → Add to** controls independently choose where a new record is created:

- **Common file (every difficulty)** creates one common record.
- **Difficulty files** creates a copy in each checked Normal/Hard/Maniac document.

After creation, Build finds counterpart units by related section name and record identity/order. The inspector's **Difficulties** table then controls presence, level, and HP/Str/Mag/Skl/Spd/Lck/Def/Res bonuses in each file.

Changing other fields through **Apply** updates all matched counterparts. **All fields...** is the escape hatch for editing one raw record in the currently selected file only.

## Guided walkthrough

### 1. Create matched destination sections

Open Normal in Build and filter to the intended `_n` section. Verify corresponding `_h` and `_m` sections exist. Counterpart creation cannot work when the destination section is absent.

Use the Units list to compare their army headers and current counts. For this test, make the headers equivalent and note any deliberate differences.

### 2. Place the record in all difficulty files

Activate **Place unit**. Select the section and choose **Difficulty files**. Tick Normal, Hard, and Maniac. Click the empty test cell.

New units copy AI, faction, and flags from the destination section's first unit. That is a convenience, not a safe default. Immediately select the new unit and inspect every copied field.

If no suitable template unit exists in the section, create/copy a known working unit and then replace its identity deliberately.

### 3. Configure shared fields

Set **Character**, optional **Class**, **Faction**, **Flags**, and the four tile fields. Use the same spawn and destination tile for a stationary first test.

Give it one usable weapon in slots 1–4, no item flags, and known AI appropriate to its faction. Leave optional skills and Laguz gauge empty/zero unless the design needs them.

Choose **Apply**. Reopen Hard and Maniac and confirm these shared fields followed into the matched record.

### 4. Configure difficulty-specific values

In the **Difficulties** table, leave all three presence boxes ticked. Use a clear progression such as:

| Difficulty | Level | HP bonus | Other bonuses |
| --- | ---: | ---: | ---: |
| Normal | 5 | 0 | 0 |
| Hard | 7 | 1 | 0 |
| Maniac | 9 | 2 | 0 |

Choose **Apply** and revisit each variant. The form header changes with the selected file, but the bottom table should preserve three distinct rows.

Deployment bonuses are signed bytes added to the generated stats. They are not growth rates and do not change class caps.

### 5. Remove one counterpart safely

Untick the Maniac presence box and apply. The matched record is removed from Maniac while Normal and Hard remain. Recheck unit counts and section order in all variants.

Ticking it again copies the current unit as a new counterpart and applies the Maniac row's level/bonuses. Verify its index/order because removing and re-adding structural records may affect list order.

### 6. Test actual output

Save Chapter and reopen the phase. Launch Normal, Hard, and Maniac from fresh chapter starts. Record unit presence, tile, faction, displayed level, generated stats, inventory, and AI behavior.

If displayed/generated values exceed the deployment row, account for chapter **Enemy levels +**, autolevel, character base level, class growths, stat caps, and unit flags before treating the file write as wrong.

## Understand every control

### Viewing variant

The Build **Normal/Hard/Maniac/Common** selector changes the document drawn on the map. It does not choose insertion destinations. The Deployment editor's **Difficulty variant** does the same for its tree/table.

### Add to

**Common file** is one record consumed on every difficulty. **Difficulty files** exposes one checkbox per available mode and creates separate records. With no checked file, the implementation falls back to the current variant, so always verify the result rather than relying on an empty selection.

### Section

The chosen section controls record grouping, named-army header, and script lookup. Difficulty-file placement requires matching counterpart sections. A unit in the wrong section can exist in the file but load at the wrong time—or never load.

### Apply

**Apply** writes shared form fields to matched counterparts and writes each difficulty row's level/bonuses to its own record. The tooltip explicitly states this boundary. It also applies presence checkbox additions/removals.

### Difficulties table

The checkbox controls whether the counterpart record exists. **Lv** is deployment field 36. The eight stat columns are signed bonuses added to HP, Strength, Magic, Skill, Speed, Luck, Defence, and Resistance.

Common-file units show only their common document because they are not separate per-difficulty records.

### All fields

This exposes all 48 raw record fields for the selected file only, including unread/reserved slots. Use it when intentional divergence cannot be represented by the shared form. It bypasses cross-difficulty synchronization and therefore requires a comparison afterward.

### Standalone Deployment save

The Deployment page edits the same deployment archive through its own session and offers **Save**, Excel export/import, add unit, and delete unit. Do not keep incompatible unsaved Build and Deployment sessions open and assume the last save will merge them.

## Interactions and precedence

The final unit is determined by:

1. Current difficulty and selected deployment file.
2. Script call selecting the section.
3. Whether the counterpart record exists.
4. Character/class bases and deployment level.
5. Autolevel flag, class growths, and chapter **Enemy levels +**.
6. Signed deployment bonuses and class caps.
7. Shared inventory, skills, faction, position, flags, and AI.

Easy in later regional builds often follows Normal deployment/shop resources while retaining its own internal difficulty value and formula/chapter-bonus column. Test resource selection and rule columns separately.

## Test matrix

| Case | Expected result |
| --- | --- |
| Normal | Unit present at Normal level/bonus row |
| Hard | Same identity/equipment/position, Hard level/bonus row |
| Maniac removed | Unit absent while other counterparts remain |
| Common control | A common unit appears on every mode without per-mode rows |
| Shared edit | Weapon or position change follows all matched counterparts |
| Raw-file edit | Change through All fields affects only selected variant |
| Fresh reload | Counts and values survive Save Chapter |
| Runtime stats | Differences match deployment plus documented autolevel/chapter rules |

## Troubleshooting

**The unit was created only on Normal.** The view selector is not **Add to**. Check the destination boxes and whether counterpart sections exist.

**Changing Hard moved Normal too.** Position is a shared field in the main form. Use a deliberate one-file raw edit only if the design truly requires positional divergence, then document it.

**Hard level keeps matching Normal.** Edit the Hard row in the bottom table, not only the currently visible main fields.

**The generated level/stat is higher than entered.** Inspect autolevel, character base level, chapter enemy bonus, and caps. Deployment level is one input.

**A counterpart checkbox is disabled.** That file has no matching section, or the unit is common. Create/fix the section structure first.

**The wrong record was matched after reordering.** Compare PID, section, and record order. Remove/re-add carefully or repair the variant directly through Deployment/All fields.

**Edits vanished after another editor saved.** Competing unsaved sessions wrote different snapshots. Save and reload before switching between Build and standalone Deployment.

## Save, build, and revert

Use **Save Chapter** for Build deployment edits or **Save** in the standalone Deployment page. Reopen all variants and compare counts before launching.

To revert, restore each counterpart's presence and per-mode values plus all shared fields. For structural mismatches or broad Excel imports, restore the original `dispos.cmp` rather than guessing record pairing.

## Limits and confidence

The four deployment files, placement destinations, counterpart behavior, shared/per-variant split, record fields, ranges, and save semantics are source-reviewed. Final generated stats and regional difficulty selection combine additional runtime systems and remain **unknown** until tested from a fresh chapter start.

## Things to try next

- Add one extra enemy only on Hard and Maniac.
- Keep unit count fixed but change per-mode level/bonuses.
- Move one unit in a single raw file and document why it should not synchronize.
- Compare a common player record with three enemy counterparts.
- Export all variants to Excel and audit them side by side.

## Related tutorials and references

- [Design and connect deployment sections](29-deployment-sections.md)
- [Set unit inventory, drops, skills, AI, and flags](31-unit-inventory-and-flags.md)
- [Difficulty modes and regional builds](../systems/difficulty-and-regions.md)
- [Deployment format](../formats/dispo-format.md)

---

[← Previous: Design and connect deployment sections](29-deployment-sections.md) · [All tutorials](index.md) · [Next: Set inventory, drops, rings, and flags →](31-unit-inventory-and-flags.md)
