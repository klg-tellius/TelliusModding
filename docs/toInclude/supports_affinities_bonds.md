# Supports, affinities and bonds

Suggested Archive pages: a **Supports** system page (with Affinities as a section or sub-page) and a **Bonds** section. Source reference: `research/SUPPORT_NOTES.md`.

## What a support is

Two characters who fight together build a relationship. Each relationship has up to three ranks, **C**, **B** and **A**. Every rank is unlocked by a conversation viewed in the base, and every rank makes both characters stronger when they stand near each other in battle.

All the numbers live in `FE8Data.bin`; the rules that use them are in the executable.

## Affinity

Every playable character has one of eight **affinities**, named by a pointer in the character record (`+0x14`):

| Affinity | Name in the data | Bonus per rank (stored ×2) |
|---|---|---|
| Fire | `fire` | Attack 1, Hit 5 |
| Thunder | `thunder` | Defence 1, Avoid 5 |
| Wind | `wind` | Hit 5, Avoid 5 |
| Water | `water` | Attack 1, Defence 1 |
| Dark | `dark` | Attack 1, Avoid 5 |
| Light | `light` | Defence 1, Hit 5 |
| Heaven | `heaven` | Hit 10 |
| Earth | `telius` | Avoid 10 |

The bonuses come from the **`DivineData`** table: nine 12-byte rows (a "none" row first), each a name and six signed bytes — Attack, Defence, Hit, Avoid, Critical, Critical avoid — plus two unused bytes. No vanilla affinity gives Critical or Critical avoid, but the game supports it. The order of the affinities is fixed by the executable.

## The support lists — `RelianceData`

Every character with supports has a block: its PID, a slot count, then one 8-byte slot per partner — the partner's PID and three **thresholds** (C, B, A) plus a zero byte. Path of Radiance has 41 such characters and 68 pairs. Each pair appears twice, once in each character's list, with the same thresholds.

Some slots are empty (no partner): they keep the positions of the other slots fixed. A character can have at most 10 slots.

## Earning a support

Every unit keeps a **support point** counter for each slot, saved with the unit.

1. **At the end of each chapter**, a unit that finished the chapter on the map gains **1 point** with every partner who also did. Units left in reserve or dead do not.
2. Points stop at the next threshold: when they reach the C threshold, the **C conversation** becomes available in the base's Support menu, and no more points come in until it is viewed.
3. Viewing the conversation adds the last point to both characters and grants the rank. The same happens for B and A.

Example: Ike and Titania have thresholds 8 / 12 / 28. After 8 chapters together their C conversation opens; viewing it brings them to 9 points and rank C, and the B conversation opens 3 chapters later, at 12.

Limits:

- A character can hold at most **5 support stars** (C = 1, B = 2, A = 3) — for instance one A and one B. At 5 stars they gain no more points with anyone.
- Parts 1 to 3 of the four-part Chapter 17 and Chapter 28 give no points.
- When a character dies, the points between them and all their partners drop to zero.

## Conversations

A support conversation is the message **`MYELL_<X>_<Y>_<R>`** in `Mess/yell.m`: `X` and `Y` are the two characters' internal names (the PID without `PID_`) in alphabetical order, and `R` is `C`, `B` or `A` — for example `MYELL_BOLE_MIST_B` for Boyd and Mist's B conversation.

A chapter script can take over: a script function with the *support* trigger (event type 13: character 1, character 2, rank 1 = C / 2 = B / 3 = A) runs instead of the plain message. The game uses this five times to pick between versions of a conversation depending on the chapter or on whether someone is alive — for example Makalov and Astrid's C and A conversations change if Marcia is dead.

Scripts can also read and set a rank directly with `PersonGetYellLevel` and `PersonSetYellLevel` ("yell" is the game's internal word for supports).

## The bonus in battle

When a battle starts, each fighter looks at every support partner:

- the partner must be on the same side and **within 3 tiles**;
- the rank counts as 0 (none), 1 (C), 2 (B) or 3 (A);
- the fighter adds **rank × its own affinity row** and **rank × the partner's affinity row**.

The totals from all partners are then **halved** (rounded down) and added to Attack, Defence, Hit, Avoid, Critical and Critical avoid.

Example: Ike (Earth) with Titania (Light) at rank A gives Ike Defence +1, Hit +7 and Avoid +15 — ⌊3 × 1 ÷ 2⌋, ⌊3 × 5 ÷ 2⌋ and ⌊3 × 10 ÷ 2⌋. Titania gets exactly the same, since the same two rows are added for her.

Because the halving happens once, after summing, two partners can give a little more than the two separate results added together.

The skill `SID_FAIRNESS` cancels support bonuses for both sides when the attacker has it.

## Bonds — `KiznaData`

Separately from supports, 36 **bonds** tie two characters together (12-byte records: two PIDs, a kind and a value). A bond only works while the two stand **next to each other** on the same side.

- **Kind 1 — Critical bonus.** Both characters gain *value* Critical (10 or 5). Examples: Ike and Mist (+10), Oscar and Boyd (+10), Marcia and Makalov (+5), Tibarn and Reyson (+10).
- **Kind 2 — protection.** While the second character stands next to the first, enemies cannot land a critical hit on the second. Examples: Soren next to Ike, Titania next to Greil, Ike, Geoffrey, Bastian, Lucia and Kieran next to Elincia, Petrine next to Ashnard.

Bonds need no support and no conversation; they are active from the start.

## Summary for modders

| To change | Where |
|---|---|
| Who supports whom, and how fast | `RelianceData` thresholds (both characters' lists) |
| Conversation text | `Mess/yell.m`, `MYELL_<X>_<Y>_<R>` |
| Situational conversations | a type-13 script function |
| A character's affinity | character record `+0x14` |
| What an affinity gives | `DivineData` row |
| Adjacency bonuses | `KiznaData` |
| 5-star cap, 3-tile range, halving, per-chapter gain | executable only |
