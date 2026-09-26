# check_steal_action_targeted

**Address:** 0x8018D4CC  
**Size:** 728 bytes  
**Domain:** battle  
**Confirmed:** Twenty-seventh finding  

## Overview

`check_steal_action_targeted` is the "already have a target in mind" entry point for the Steal action in Fire Emblem: Path of Radiance. It is a near-identical twin of `check_steal_action_scan`, sharing the same skill gate (`SID_STEAL`), the same item eligibility check (`TBL_STEALITEMS`), and the same action ID (`0x11` = Steal), but differs in how it acquires its target: instead of scanning the nearby area for stealable items, it operates on a pre-selected unit/context provided via its parameters.

This function determines whether a unit can perform a steal action against a specific, already-identified target, making it the targeted counterpart to the scanning variant.

## Parameters

- `actingUnit`: The unit attempting the steal action (passed as `param_1`)
- `predicateFn`: A function pointer used for additional targeting validation (passed as `param_2`)

Returns a boolean-like value (`uVar8`) indicating whether the steal action was successfully registered.

## Detailed Implementation

### 1. Skill Validation

The function first checks if the acting unit possesses the Steal skill:

The unit's skill flags are stored at offset `0x1bc` in the unit structure, and `0x3c` (60 in decimal) corresponds to `SID_STEAL` in the game's skill table.

### 2. Early Exit Conditions

If the unit has the Steal skill, the function proceeds to check two possible early-exit conditions:

#### Condition A: AI Decision Flag Check

This checks:
- Whether bit 1 of `DAT_8032b3c1` is clear (related to AI decision-making)
- Whether bits 24-25 of `unit + 0x254` are clear (likely related to unit state or action restrictions)

If both conditions are true, it calls `FUN_800fe2a0` with parameters `(actingUnit, 5, 0xffffffff)`, which appears to be a specialized AI handling routine.

#### Condition B: Map State Preparation
If Condition A fails, the function prepares the map state for item scanning:

This sequence:
1. Clears map state buffers for a specific layer (parameter `5`)
2. Initializes a descriptor at that layer
3. Resets a value in the map's height data at the unit's current position (calculated from `param_1 + 0x19e` and `param_1 + 0x19f`)

### 3. Target Scanning Loop

The core of the function is a scanning loop that evaluates nearby units for steal eligibility:

### 4. Action Registration

After scanning all nearby units, if a valid steal target was found:

This block:
1. Checks if a valid target was found (`iVar11` was updated from initial value)
2. Extracts coordinates from the best target unit (`unaff_r27 + 0x19e` and `+0x19f`)
3. Calls `FUN_8010f3f4` (likely pathfinding or movement validation)
4. Increments a counter at `param_1 + 600` (possibly tracking steal attempts)
5. Calls `register_available_action` with:
   - Action ID: `0x11` (Steal)
   - Target tile coordinates: `(char)local_50`, `(char)local_4e`
   - Target unit: `unaff_r27`
   - Item parameters: `(int)cVar7`, `(int)cVar1` (likely item slot and item data)
   - Best item slot: `unaff_r24`
   - Three zero parameters (likely reserved for other action types)
6. Returns the action found flag

## Relationship to check_steal_action_scan

As noted in the research documentation, `check_steal_action_targeted` is a near-identical twin of `check_steal_action_scan` (at address `0x8018D294`). The key differences are:

| Aspect | check_steal_action_scan | check_steal_action_targeted |
|--------|-------------------------|-----------------------------|
| **Target Acquisition** | Scans nearby area for targets | Uses pre-selected target via parameters |
| **Input Parameters** | None (scans from unit's position) | `actingUnit`, `predicateFn` |
| **Scanning Logic** | Initiates fresh scan of surroundings | Uses provided context/state |
| **Use Case** | "Find me a target" | "Already have a target in mind" |

Both functions:
- Check for `SID_STEAL` skill via `actor_has_flag_or_skill(unit+0x1bc, 0x3c)`
- Consult `TBL_STEALITEMS` to determine steal-eligible items
- Attempt to register action `0x11` (Steal) when valid target found
- Share the same core scanning and evaluation logic

## Gameplay Context

This function is part of the Fire Emblem: Path of Radiance action menu system. When a player selects the Steal command for a unit:

1. The game first checks if there's a pre-existing steal target in mind (possibly from AI targeting or previous selection)
2. If so, it calls `check_steal_action_targeted` to validate that specific target
3. If not, or if the targeted validation fails, it falls back to `check_steal_action_scan` to search for any valid target in the vicinity
4. If either function successfully registers the action, the Steal command becomes available in the unit's action menu

The Steal action allows a unit with the Steal skill to take an item from an adjacent enemy unit's inventory, subject to:
- The thief having sufficient capacity to carry the item (checked via `can_actor_carry_item` equivalent logic)
- The item being listed in the `TBL_STEALITEMS` table (which excludes key items, equipped weapons, etc.)
- The target being within range (determined by the scanning logic)

## Data Structures Referenced

- **Unit Structure**: Accessed via `param_1`, with skill flags at offset `0x1bc`, position data at `0x19e`/`0x19f`, and state flags at `0x254`
- **Item Structure**: Retrieved via `FUN_80037bd0(unit, slot_index)` for inventory examination
- **String Tables**: `TBL_STEALITEMS` referenced via `s_TBL_STEALITEMS_802798ed` for item name lookups
- **Global State**: 
  - `DAT_8032b3c1`: AI/decision-making flags
  - `DAT_802ef4e0`: Count of units in scan radius
  - `action_found_flag`: Indicates if an action was successfully registered
- **Helper Functions**: 
  - `actor_has_flag_or_skill`: Skill checking
  - `clear_map_state_buffers`/`FUN_80022fd8`: Map scanning initialization
  - `FUN_8002f728`/`FUN_8002f658`/`FUN_8002f740`: Unit iteration
  - `FUN_80037bd0`: Item retrieval from unit
  - `hash_lookup_by_name_b`: String table lookup
  - `FUN_8003dac4`: Item carrying capacity check (equivalent to `can_actor_carry_item`)
  - `FUN_8003dc80`: Speed comparison (likely for range validation)
  - `module_name_strcmp`: String comparison for item matching
  - `FUN_8010f3f4`: Pathfinding/movement validation
  - `register_available_action`: Action menu registration

## Notes

- This function was identified as the "real menu-driver" for Steal, resolving a prior dead end where `can_steal_nearby_item` (which shares similar logic but different purpose) was mistaken for the action registration function
- The function implements the "targeted" variant of the Steal action, complementing the "scan" variant
- Despite extensive searching, the exact mechanism by which this function gets its target parameters remains partially unknown, as it appears to be called through a mechanism not traced by the project's static analysis tools (possibly indirect jump tables or hash-based dispatch)