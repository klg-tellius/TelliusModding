Detailed Explanation of check_steal_action_scan Function (0x8018D294)

Function Signature:
undefined check_steal_action_scan(int param_1, undefined4 param_2)

Overview:
This function is the confirmed driver for the Steal map-action in Fire Emblem: Radiant Dawn. It resolves the previous dead-end around can_steal_nearby_item by implementing the actual Steal action logic. The function is gated by the SID_STEAL skill flag and scans nearby enemy units' inventories to find stealable items, then registers the Steal action if a valid target is found.

Inner Working Breakdown:

1. Skill Gate Check (Lines 110-114):
   - First checks if the acting unit (param_1) has the SID_STEAL skill (0x3c) via actor_has_flag_or_skill(param_1 + 0x1bc, 0x3c)
   - If the unit does NOT have the Steal skill, immediately returns 0 (action_not_found_flag)
   - This ensures only units with the Steal skill can perform this action

2. Initialization (Lines 115-120):
   - Sets up local variables pointing to TBL_STEALITEMS (0x80296078) - the reference table of stealable/eligible items
   - Stores param_1 (acting unit) in local_48 and param_2 in local_44
   - Clears the target unit list (DAT_802ef4e0) via FUN_8002f728
   - Calls FUN_8002c47c(&local_4c, 0) which performs a full-map scan calling vtable+0xc on self for each row>=threshold
     (This appears to populate DAT_802ef4e0 with potential target units)

3. Main Search Loop (Lines 121-163):
   - Initializes iVar10 (target index counter) to 0
   - While loop continues until iVar10 >= DAT_802ef4e0 (number of potential targets found)
   - For each target unit:
     * Gets unit data via FUN_8002f658(&DAT_802ef4e0, iVar10)
     * Resolves unit slot ID via FUN_8002f740() (returns unit slot ID)
     * Checks if unit can carry items via FUN_8003dc80(param_1, iVar2) - this is the can_actor_carry_item check
     * If the unit can carry items (cVar7 != '\0'):
       - Scans up to 8 inventory slots (iVar12 from 0 to 7)
       - For each inventory slot:
         + Gets item pointer via FUN_80037bd0(iVar2, iVar12) (returns item struct pointer)
         + If item exists (*piVar3 != 0):
           * Looks up TBL_STEALITEMS via hash_lookup_by_name_b(s_TBL_STEALITEMS_802798ed)
           * Checks if actor can carry/can use the item via FUN_8003dac4(param_1, piVar3) (get_str_stat vs get_item_weight check)
           * If item is usable by actor (cVar7 == '\0'):
             - Sets iVar9 = -1 (indicates no match in steal table)
           * Else (item not usable by actor):
             - Iterates through TBL_STEALITEMS string table
             * For each string in table:
               - If item pointer is NULL, uVar5 = 0
               - Else, uVar5 = *item pointer (item name/ID)
               - Compares uVar5 against current steal table entry via module_name_strcmp
               - If match found (iVar6 == 0): goto LAB_8018d3e8 (found stealable item)
               - Else increment iVar9 (check next table entry)
             * If loop completes without match: iVar9 = -1 (item not in steal table)
         + If iVar9 != -1 (item found in steal table or usable by actor): break inner loop
       - If a valid item was found (iVar6 == 0 from strcmp):
         * Stores unit index in unaff_r24
         * Stores item index in iVar11 (best item score so far)
         * Stores inventory slot in unaff_r27 (best slot so far)
   - Increments iVar10 to check next target unit

4. Action Registration (Lines 164-174):
   - Sets uVar8 = action_found_flag (0 or 1 indicating if action was found)
   - If a valid target was found (iVar11 != 0x7fffffff):
     * Extracts unit data: cVar7 = unit->y_pos, cVar1 = unit->x_pos
     * Calls FUN_8010f3f4 to calculate action positioning
     * Increments unit's action count (*(short *)(param_1 + 600)++)
     * Calls register_available_action with:
       - Action ID: 0x11 (17) = Steal
       - X coordinate: (int)(char)local_4e
       - Y coordinate: (int)(char)local_50
       - Target unit: unaff_r24 (unit with stealable item)
       - Target unit's y_pos: (int)cVar7
       - Target unit's x_pos: (int)cVar1
       - Item index: unaff_r27 (inventory slot of stealable item)
       - Unknown: 0, 0
     * Sets uVar8 = action_found_flag again (should now be 1)

5. Return Value:
   - Returns uVar8 (0 if no action found, 1 if Steal action was registered)

Key Characteristics:
- This is the "scan" variant that searches the whole neighborhood for the best target from scratch
- It has a near-identical twin: check_steal_action_targeted (0x8018D4CC) which uses pre-selected context instead of scanning fresh
- The function prioritizes items based on some scoring mechanism (lower iVar9 values are better)
- It checks both if the actor can use the item AND if the item is in the stealable items table
- Only registers one action per call (the best target found)

Relationship to Other Functions:
- Called by: dispatch_chant_steal_rescue_a/b/c (when Chant action fails and unit has SID_STEAL)
- Calls: actor_has_flag_or_skill, FUN_8002f728, FUN_8002c47c, FUN_8002f658, FUN_8002f740, FUN_8003dc80, FUN_80037bd0, hash_lookup_by_name_b, FUN_8003dac4, module_name_strcmp, FUN_8010f3f4, register_available_action
- The function populates and reads from DAT_802ef4e0 (target unit list)
- Uses TBL_STEALITEMS (0x80296078) as the reference for stealable items

This explanation focuses purely on the function's internal mechanics without discussing callers, callees, or meta-values as requested.