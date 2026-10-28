# AI scripts (Game Data › AI (CP))

The enemy and NPC AI of Path of Radiance lives in `cp_data.bin`. A deployment record names four AI entries per unit: an **attack script** (`seq_attack`), a **move script** (`seq_move`), a **heal record** (`seq_heal`) and a **movement type** (`mtype`). Chapter scripts can switch them with `UnitSetCpAttackSeq` / `UnitSetCpMoveSeq` / `UnitSetCpHealSeq` / `UnitSetCpMTypeID`. Game Data › **AI (CP)** edits all of them; **Save AI data** writes the file (the build copies it into `system.cmp`).

The format and every opcode are described in `research/CP_DATA_NOTES.md`; the opcode table the editor uses is `App/fe_modding/formats/cp_ops.py`.

## How a unit's turn runs

1. A unit that has to retreat (its heal record) heals or retreats first.
2. Its **attack script** runs, entry by entry, until an `end()` or `stop()`. Each action entry (`attack`, `use_staff`, `steal`...) looks for something to do and, when it finds it, registers it as the unit's action. A later action entry replaces it, which is why scripts follow each action with `if found: goto L99`.
3. If no action was found, the **move script** runs the same way: it picks the tile to move to.
4. The unit does the registered action.

Each script keeps its position between turns: `end(resume=L1)` makes the next turn start at `L1` (by default it restarts from the top). The position is saved in save files, and so are the ids of the scripts (their place in the list, the number next to the name). New scripts are therefore always added at the end of their list.

## The Attack / Move scripts tab

Pick **Attack** or **Move**, then a script. **Copy as new…** duplicates it under a new `SEQ_` name (the only way to make a new one), **Delete** removes the last script of a list. **Used by → Find** lists the chapter scripts and deployments that name it.

The script has two views of the same data:

- **Readable code**: one line per entry. Type freely; problems are listed under the editor as you type. **Apply** (or switching tab, script or saving) writes the code into the script; code with errors can't be applied. **Insert** adds any statement, grouped as Flow / Actions / Movement / Registers. Ctrl+Space completes names, keywords and values (characters, classes, items, skills, tables, scripts, labels), and the line under the editor shows the signature of the function under the cursor. **Reload from data** throws away the code and shows the script as it is. The code you applied, comments included, is kept in `ai_sources/SEQ_NAME.fe9ai` next to the project and shown again while it still matches the script.
- **Raw entries**: the opcode and its six words `a`–`f` as stored, with the readable line of each entry. Selecting an entry fills the form below; each box is labelled with what that opcode does with the word (`a chance`, `e targets`, `b threat limit`, or `(unused)`), and the text under it explains the opcode. Edits apply when you leave a box; ▲ ▼ move entries, **Insert below** adds a do-nothing entry to edit.

## The readable code

```python
# SEQ_ALLATK100_NOLAGU - attack script, id 15
use_staff(chance=100)
if found: goto L99
steal(chance=100)
if found: goto L99
attack(chance=100, targets=TBL_PID_LAGU, exclude=True)   # anyone hostile but the laguz
L99:
end()
```

| Statement | Meaning |
|---|---|
| `L99:` | a label |
| `goto L99`, `goto start` | jump (`start` = the first entry) |
| `if found: goto L99` / `if not found: goto L99` | jump when an action was found (or wasn't) |
| `if r0 == 3: goto L99` | compare a register (`==`, `!=`, `>`, `>=`, `<`, `<=`) |
| `r0 = count_units(range=1.5)` | the functions that compute a value write a register (`r0`–`r3`) |
| `attack(chance=100)` | every other entry |
| `op(213, a=1, b=0xffff)` | any entry, word by word (used for entries the other forms can't show exactly) |

Arguments are written `name=value`; arguments at their default are left out. `#` starts a comment.

### Arguments most functions share

- `chance=` — percent chance that the entry tries at all (0–100).
- `targets=` / `exclude=` — with no `targets`, the entry looks at every hostile unit. `targets=TBL_PID_X` limits it to the characters of that list (Routes & targets tab), whatever their side; with `exclude=True` it looks at hostile units **not** in the list.
- `threat_limit=` — the movement checks only stop on tiles whose enemy threat is at most this; `none` (the default) means no limit. It stays in effect for the following entries of the script. `move_nearest(fallback=True, threat_limit=5)` is the vanilla "cautious" move.

### Functions

Actions (attack script): `attack`, `attack_in_place`, `attack_character(pid=)`, `attack_class(jid=)`, `attack_direct`, `use_staff`, `use_staff_in_place`, `steal`, `steal_in_place`, `use_skill(sid=)`, `use_skill_in_place`, `shoot` (ballista), `rock_attack`, `rock_attack_force(tiles=)`, `tackle`, `talk(pid=)`, `use_item(iid=)`. `_in_place` versions act without moving.

Movement (move script): `move_nearest`, `move_nearest_straight`, `move_nearest_ranged`, `move_to(x=, y=)`, `move_to_talk(pid=)`, `talk_move(pid=)`, `move_to_class(jid=)`, `move_safest`, `move_random`, `follow_route(route=, budget=)`, `escape`, `destroy_village(tries=)`, `break_object`, `r0 = move_to_event(kind=)`.

Flow and registers: `end(resume=)`, `stop(resume=)`, `set_scripts(attack=, move=)` (switch to other scripts), `clear_found`, `r0 = count_units(range=, weapon_range=)`, `r0 = move_stat(add=)`, `r0 = has_skill_9()`, `r0 = event_action(kind=)`, `call_native(function=)`, `nop102()` … `nop214()`.

Many actions leave a result code in `r0`, usable by name: `NOT_ON_MAP`, `NEXT_TO_TARGET`, `TALK_QUEUED`, `ARRIVED`, `NONE_FOUND`, `TRY_LIMIT`, `HAS_SKILL`, `TARGET_STATE_04/20/40/80`.

### What the checker catches

Errors (the code can't be applied): unknown functions or arguments, wrong value types, jumps to labels the script doesn't have, an attack script given as `move=` (or the reverse), tables that don't exist, more than 254 entries. Warnings: unknown character/class/item/skill names, chances outside 0–100, registers past `r3`, and a script that doesn't end with `end()`, `stop()` or `goto` — the game would go on into the next script in the file (vanilla `SEQ_USECHANGE_ATRANGE` actually does this on purpose).

## The other tabs

- **Heal** — HP % under which the unit retreats to heal, the HP % at which it stops, and whether it uses its own healing items first.
- **Movement types** — the weights the AI uses to score the tiles it could attack from.
- **Steal items** — the items AI thieves take; earlier items are preferred.
- **Routes & targets** — waypoint lists (`follow_route`, typed `x,y`) and the character lists used by `targets=`.
