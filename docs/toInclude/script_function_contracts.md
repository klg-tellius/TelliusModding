# Script function reference: argument and behavior contracts

## Documentation structure

The [function reference](../app/script-call-reference.md) includes all 497 catalogued names with positional signatures, individual argument explanations, behavior and return descriptions, and practical restrictions. Registration addresses, evidence badges, raw call-site dumps and research methodology are excluded from author-facing entries.

Native contracts were investigated in the canonical US executable. See [SCRIPT_NATIVE_CONTRACTS.md](https://klg-tellius.github.io/TelliusModding/#/events-scripting) for the contract index, focused decompilation, applied Ghidra annotations and remaining resource-specific limits. The 44-script observation snapshot is retained privately under research/main_dol/notes/script_reference_observations.json for maintenance checks.

## Shared-script facts to preserve

The game-side facts are filed under [Shared helper argument and return contracts](https://klg-tellius.github.io/TelliusModding/#/events-scripting): different live/deployed tests; unit-handle versus boolean returns; first-target/second-mover argument order; success paths returning zero; coordinate and weapon-away error sentinels; force-0-only breakup; and the nontrivial inventory valuation branch.

Other established helper sequences include the full/half/no-delay BGM variants, fixed 60/1000 tutorial delay conversion, the two-stage map release with an intervening yield, and reward/tutorial-dialog wrapper calls. `_gi` and `td` have caller-established roles, while their native body contracts remain unresolved. The unknown-byte and remaining-question references reflect that distinction.

Existing force-list, named-flag, support-rank and US-language/difficulty findings are incorporated from their topical research notes. Native handler and consumer findings are applied as function comments, signatures, variable names, global labels and runtime-record types in the canonical Ghidra project.

## Maintenance

Reviewed explanations live in `docs/app/script_reference_details.py` and `script_native_contracts.py`, separate from the compiler catalog. `generate-script-reference.py` checks names, argument counts, native registration agreement, helper definition counts and unique anchors before rendering. It can refresh the bounded example snapshot with `--scripts PATH_TO_SCRIPTS` and otherwise regenerates offline. Changes to the generated Markdown must be made in those sources to survive regeneration.
