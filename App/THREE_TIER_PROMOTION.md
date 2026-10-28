# Three-tier promotions (Path of Radiance)

Enable **Game Code → Promotion → Three-tier promotions** in an extracted US,
European, or Japanese Path of Radiance project. This adds `SID_TIER3` to
`FE8Data.bin`, creates a separate `IID_MASTERCROWN` item, installs the DOL
hooks, and adds Crown name/help messages. The European project receives text
in all five language files. Save the Game Data session before building.

For each desired chain, configure three distinct classes in Game Data:

| Class | Promotion link | Class skills |
| --- | --- | --- |
| Tier 1 (A) | B | No `SID_HIGHER` or `SID_TIER3` |
| Tier 2 (B) | C | `SID_HIGHER`, without `SID_TIER3` |
| Tier 3 (C) | Empty | `SID_HIGHER` and `SID_TIER3` |

Other class skills may remain. Class links and flags are opt-in; existing
two-tier chains keep their retail behavior. The Master Seal works only on
tier 1. The Master Crown works only on tier 2, from level 10 by default.
Tier 2 can also promote automatically at level 20 by default. Set **Third
tier: Crown only** to 1 to disable that automatic promotion, or change
**Master Crown minimum level** in Game Code. Tier 3 has a normal level-20 cap.
Builds before 2026-10-27 crashed with an emulator error at `0x80002DD8` when a
tier-2 unit used the Crown: the level-gate stub loaded the minimum level with a
load based on r0, which PowerPC reads as address 0 plus the offset. Re-enable the
patch (or rebuild) to pick up the fixed stub.
The displayed effective level is offset by 20 for tier 2 and 40 for tier 3.

The Crown is a distinct item record and effect, initially cloned from the
Master Seal, including its icon, price, and uses. Place `IID_MASTERCROWN` in
shops, events, or inventories as desired. For a distinct tier-3 battle model,
set the tier-3 class AID and clear the character's promoted AID; the engine
then uses each class's AID. Characters with a promoted AID set continue to
use that AID in both promoted tiers.

The patch changes no character class, inventory, or recruitment data on its
own. Run `three_tier_data.validate_chain(fe8_bytes, A, B, C)` to validate a
configured chain. Removing the DOL patch leaves the extra records in game
data; the Crown then has no usable class-change effect.
