# build_strike_forecast_log Function

**Address:** 0x801a601c

**Function:** void build_strike_forecast_log(BattleExchangeContext *ctx, CombatActor *attacker, CombatActor *defender, byte logMode) 

## Description

The build_strike_forecast_log function is responsible for calculating and logging combat forecast statistics for both attacker and defender during battle exchanges. It handles terrain bonuses based on equipped items, computes forecast stats (attack, defense, hit, crit, etc.), applies skill effects, and records the forecast data to the combat exchange's record buffer for later display or processing. 

This function is called from `execute_combat_exchange` and `resolve_combat_exchange` to prepare combat forecast data before actual strikes are resolved. 

## Parameters

**ctx**: Pointer to the BattleExchangeContext containing battle state information including combat record buffer, battle result flags, and references to attacker/defender CombatActors.

**attacker**: Pointer to the CombatActor representing the attacking unit in this exchange.

**defender**: Pointer to the CombatActor representing the defending unit in this exchange.

**logMode**: Byte flag controlling whether forecast data should be logged to the combat record buffer. When 0, forecasting data is recorded; when non-zero, only calculations are performed without logging.

## Function Behavior

The function operates in several distinct phases: 

- **Terrain Bonus Calculation:** If the attacker is not already marked as having performed an exchange (ctx->battle_result_flags & 1 == 0), the function calculates terrain-based stat bonuses for both attacker and defender based on their equipped items.
- **Forecast Stats Computation:** Calls `compute_forecast_stats` for the attacker, and if applicable, the defender to calculate all combat statistics (attack, defense, speed, hit, crit, avoid, etc.) including weapon effectiveness, biorhythm effects, and support bonuses.
- **Skill Effect Processing:** Checks for specific skills (like Astra/Aether/Continue) and applies their effects to forecast statistics when conditions are met.
- **Deterministic Mode Override:** If a global flag (DAT_80331b58 & 0x100) is set, forces hit rate to 100% and critical rate to 0% (likely for testing or debugging).
- **Combat Record Logging:** When logMode is 0, records the calculated forecast statistics to the combat record buffer for display in the combat forecast UI.
- **Stat Difference Storage:** Computes and stores the differences between forecast and actual stats for later comparison.

## Terrain Bonus Calculation Details

When calculating terrain bonuses, the function: 

- Initializes terrain bonus variables to zero for both combatants.
- If both combatants have valid secondary resource descriptors (equipped items), it iterates through a terrain bonus lookup table.
- For each terrain entry, it compares the weapon type derived from the equipped item against the terrain entry's weapon type.
- When a match is found, it applies the corresponding terrain bonuses to the appropriate combatant.
- After processing all terrain entries, it checks if the equipped items have a specific flag (bit 0x80 in the flags at offset +4) that indicates the terrain bonuses should be inverted (negated).

## Forecast Stats Recording (logMode == 0)

When logMode is 0, the function records the following forecast statistics to the combat record buffer: 

- Attacker's HP change (if current HP differs from field 0x2b7)
- Attacker's current HP (if field 0x2b8 differs)
- Attacker's forecast attack (field 0x2ba)
- Attacker's forecast defense (field 0x2bc)
- Attacker's forecast hit rate (field 0x2be)
- Attacker's forecast critical rate (field 0x2c0)
- (If defender exists) Defender's HP change (if current HP differs from field 0x2b7)
- (If defender exists) Defender's current HP (if field 0x2b8 differs)
- (If defender exists) Defender's forecast attack (field 0x2ba)
- (If defender exists) Defender's forecast defense (field 0x2bc)
- (If defender exists) Defender's forecast hit rate (field 0x2be)
- (If defender exists) Defender's forecast critical rate (field 0x2c0)

Each value is recorded using `append_id_flag_record_with_sentinel` with specific record IDs (0x59 through 0x65).

### Important Notes

This function does not perform actual combat resolution; it only prepares forecast data that will be used by the actual strike resolution functions (`resolve_combat_exchange` and related functions). The term "forecast" refers to predicted combat outcomes based on current stats, equipment, and temporary effects. 

The function name includes "log" because of its responsibility to log forecast data to the combat record buffer when `logMode` is 0. 

### Known Limitations / Plate Evidence

According to the gameplay function catalog, this function has "plate evidence" meaning the decompilation has been verified against the PAL FE9 decompilation, though there may be some fragmentation in the original decompilation (was 1240 bytes in 2 ranges, PAL says 0x4dc bytes). 

Generated as part of the Tellius Modding Project's gameplay function documentation initiative.
