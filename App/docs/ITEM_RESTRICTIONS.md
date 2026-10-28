# FE9 custom item use restrictions

Open **Game Data → Items**, select an item, and use **Custom use restriction**. Enter or browse for character (`PID_`), class (`JID_`), and skill (`SID_`) IDs. The rule belongs to the item's `IID_`, so reordering the item table does not change its owner. Copying an item copies its rule; renaming or removing an item updates its rule.

**Any** permits use when at least one listed ID matches. **All** requires one match from every populated group. Multiple IDs within the same group are alternatives. An empty rule adds no restriction. Existing game checks, such as weapon rank, Equip Light, and other exclusive weapon flags, still apply in addition to the custom rule. These rules govern use and equip, so units may still carry, buy, and trade restricted items.

Save writes the rules to a versioned `ItemRestrictionData` export inside `FE8Data.bin` and installs a separate text section in `main.dol` to enforce them. A missing PID, JID, SID, or IID is rejected. Removing all nonempty rules removes the executable hook. Keep both modified files together when building a disc. The hook recognizes US, European, and Japanese FE9 builds and checks the expected retail instructions before installation; an incompatible or conflicting executable is rejected.

The playthrough simulator applies the same custom rule to weapons, staves, and its item Use action. It does not simulate every original FE9 item effect.
