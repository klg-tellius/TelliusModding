"""The AI script opcodes of ``cp_data.bin`` - what every one of the 52
handlers does and what its entry fields mean.

An AI script entry is 7 words ``op a b c d e f`` (see :mod:`cp_data`). The
engine (``cp_run_attack_script_step`` / ``cp_run_move_script_step``) reads
the entry at the unit's program counter, then:

* if ``b`` is non-zero, copies it into ``cp_move_threat_limit``
  (``0x8032B3C4``) - so ``b`` is a setting of *every* entry, not only of the
  ones that use it. The movement checks only stop on tiles whose enemy-threat
  value (the map ``build_enemy_threat_map`` fills) is at most this limit.
  ``0xFFFF`` = no limit. The limit is reset to ``0xFFFF`` before each step of
  the unit's turn (attack script, move script...). COMPARE uses ``b`` as its
  comparison code and COUNT_UNITS as its range factor, so those two set the
  limit as a side effect;
* binary-searches ``op`` in the table at ``0x80273000`` (US; ``0x8027C2C0`` PAL,
  ``0x8026CAF0`` JP - the same 52 opcodes) and calls the handler.

A handler normally moves the counter on by one. Jumps set it to the first
``op 0`` (label) entry whose ``c`` is the wanted label; label ``0`` means
"back to the first entry". A jump to a label the script doesn't have runs past
the end of the script (the search never stops), so it must not happen.

The attack script runs first. The engine calls entries until one sets the
"done" flag (END / STOP, a SET_SCRIPTS that replaces the running script,
CALL); after 256 entries without it, it runs a built-in
``attack(chance=100); end()`` (move: ``move_nearest(); end()``) instead. If no
action was found, the move script runs the same way. The counters are kept on
the unit (``+0x250`` attack, ``+0x251`` move) and saved, so a script resumes
where its last END / STOP jumped to on the next turn.

Action entries register a candidate action (``register_available_action``)
and set the *found* flag; a later action entry overwrites the candidate, so
scripts follow each one with ``if found: goto ...``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# -- field kinds -----------------------------------------------------------------------
# int      signed number
# percent  0..100; the handler acts when roll_random_int(100) <= value, so 0 still
#          acts 1% of the time and 100 always
# bool     0 / non-zero
# label    jump target: a label id, 0 = back to the first entry
# reg      register index (0..3) of the shared register file 0x8032B3C8
# cmp      comparison code of COMPARE
# fixed    16.16 fixed-point factor
# pid jid iid sid seq name
#          a label naming a character / class / item / skill / AI script / native
# pid_table  TBL_PID_* section pointer (character list)
# route      TBL_MAP*_ROUTE* section pointer (waypoints)
# tiles      tile list section pointer (same (x << 16) | y format as a route)
# any        whatever the word holds
NAME_KINDS = ("pid", "jid", "iid", "sid", "seq", "name")
TABLE_KINDS = ("pid_table", "route", "tiles")

NO_LIMIT = 0xFFFF


@dataclass(frozen=True)
class Field:
    slot: str  # entry word: "a".."f"
    name: str  # keyword in the readable language
    kind: str
    default: object  # value left out of readable code; None = always written
    help: str


@dataclass(frozen=True)
class OpSpec:
    op: int
    key: str  # short upper-case name
    name: str  # function / statement name in the readable language
    form: str  # call, assign (writes reg[a]), label, goto, if_found, compare, header
    summary: str
    fields: tuple[Field, ...] = ()
    b_default: int = NO_LIMIT  # value of the threat limit word when the op doesn't use b
    confidence: str = "confirmed"  # confirmed / strong / tentative
    action: Optional[int] = None  # action id it registers
    result: str = ""  # what it writes to the registers

    @property
    def uses_b(self) -> bool:
        return any(f.slot == "b" for f in self.fields)

    def field(self, slot: str) -> Optional[Field]:
        for f in self.fields:
            if f.slot == slot:
                return f
        return None


def _chance() -> Field:
    return Field("a", "chance", "percent", None, "percent chance to try (roll 0-99 <= chance)")


def _targets(table_help: str = "only units in this character list") -> tuple[Field, Field]:
    return (Field("e", "targets", "pid_table", 0, f"TBL_PID_* list; none = every hostile unit; set: {table_help}"),
            Field("d", "exclude", "bool", False,
                  "with targets: hostile units NOT in the list (False: any unit in the list, whatever its side)"))


_HOLD = " without moving (the 'hold position' flag: only the unit's own tile is considered)"

_LIST: list[OpSpec] = [
    OpSpec(-2, "HEADER", "header", "header", "first entry of every script; e = the script's own name",
           (Field("e", "name", "seq", None, "the script's own name"),), b_default=0),
    OpSpec(-1, "ID", "script_id", "header", "second entry; a = the script's id (position in its id list)",
           (Field("a", "id", "int", None, "id saved in save files"),), b_default=0),
    OpSpec(0, "LABEL", "label", "label", "jump target; does nothing",
           (Field("c", "label", "int", None, "label id"),)),
    OpSpec(1, "COMPARE", "compare", "compare",
           "if reg[a] <comparison> c, jump to label d; otherwise go on. b is the comparison "
           "(0 >, 1 >=, 2 ==, 3 <=, 4 <, 5 !=, other: never) and also sets the threat limit",
           (Field("a", "reg", "reg", 0, "register"), Field("b", "cmp", "cmp", None, "comparison"),
            Field("c", "value", "int", 0, "value"), Field("d", "target", "label", None, "label to jump to"))),
    OpSpec(2, "CALL", "call_native", "call",
           "call the function registered under the name e with argument f; its return value is the 'done' "
           "flag (not used by the vanilla scripts)",
           (Field("e", "function", "name", None, "registered name"), Field("f", "arg", "any", 0, "argument")),
           confidence="strong"),
    OpSpec(3, "SET_SCRIPTS", "set_scripts", "call",
           "give the unit attack script e and/or move script f (none = keep) from their first entry. "
           "Ends the unit's 'escape' mode. Replacing the running script ends this run and restarts the turn's "
           "steps with the new script; setting both resets the try counter and the route waypoint",
           (Field("e", "attack", "seq", 0, "new attack script"), Field("f", "move", "seq", 0, "new move script"))),
    OpSpec(4, "GOTO", "goto", "goto", "jump to label d (0 = first entry)",
           (Field("d", "target", "label", None, "label"),)),
    OpSpec(5, "EVENT_ACTION", "event_action", "assign",
           "turn the pending action into action c when the tile the unit moves to (d: a tile next to it) has "
           "an unseen event of kind c; otherwise reg[a] = 9 (not used by the vanilla scripts)",
           (Field("a", "reg", "reg", 0, "register for the result"), Field("c", "kind", "int", 0, "event kind / action id"),
            Field("d", "adjacent", "bool", False, "look on the 4 neighbouring tiles")),
           confidence="strong", result="reg[a] = 9 when no such event"),
    OpSpec(6, "JUMP_IF_FOUND", "if_found", "if_found",
           "a != 0: jump to label d when an action has been found; a = 0: when none has",
           (Field("a", "found", "bool", None, "jump when found (True) or when not found (False)"),
            Field("d", "target", "label", None, "label"))),
    OpSpec(7, "CLEAR_FOUND", "clear_found", "call", "forget the action found so far (clears the found flag)"),
    OpSpec(100, "ATTACK_CHARACTER", "attack_character", "call",
           "attack the character named e with a weapon (action 15). exclude: attack any hostile unit except "
           "that character",
           (_chance(), Field("e", "pid", "pid", None, "character"),
            Field("d", "exclude", "bool", False, "attack every hostile unit except this one")),
           action=15, result="reg[0] = 1 when the character isn't on the map, 4 when it is in state 0x04"),
    OpSpec(101, "ATTACK", "attack", "call", "attack a unit with one of the unit's usable weapons (action 15), "
           "best-scoring target and tile", (_chance(),) + _targets(), action=15),
    OpSpec(102, "NOP_102", "nop102", "call", "does nothing (SEQ_NOATTACK)"),
    OpSpec(103, "ATTACK_IN_PLACE", "attack_in_place", "call", "attack (action 15)" + _HOLD,
           (_chance(),) + _targets(), action=15),
    OpSpec(104, "ATTACK_CLASS", "attack_class", "call",
           "attack a unit of class e (action 15). exclude: any hostile unit not of that class "
           "(not used by the vanilla scripts)",
           (_chance(), Field("e", "jid", "jid", None, "class"),
            Field("d", "exclude", "bool", False, "attack every hostile unit not of this class")), action=15),
    OpSpec(105, "USE_STAFF", "use_staff", "call",
           "use one of the unit's staves: heal (Live, Relive, Recover, Physic, Fortify), Restore, Silence, "
           "Sleep, Berserk, Warp, Rescue or Ward (table 0x8028F5F8; Torch, Hammerne and Unlock are never used). "
           "Healing staves first, highest rank first", (_chance(),) + _targets("units in this list")),
    OpSpec(106, "USE_STAFF_IN_PLACE", "use_staff_in_place", "call", "use a staff" + _HOLD,
           (_chance(),) + _targets("units in this list")),
    OpSpec(107, "STEAL", "steal", "call",
           "steal from a unit (action 17): needs SID_STEAL; the item must be in TBL_STEALITEMS, earlier "
           "entries preferred; increments the try counter", (_chance(),) + _targets(), action=17),
    OpSpec(108, "STEAL_IN_PLACE", "steal_in_place", "call", "steal (action 17)" + _HOLD,
           (_chance(),) + _targets(), action=17),
    OpSpec(109, "NOP_109", "nop109", "call", "does nothing"),
    OpSpec(110, "USE_SKILL", "use_skill", "call",
           "use skill f when the unit has it. Only these skills have an AI routine (table 0x80297278): "
           "SID_GAMBLE (attack, action 21), SID_FAIRNESS, SID_FLUTTER, SID_TACKLE, SID_TACKLE2, SID_SNARL, "
           "SID_EARTHBLESSING, SID_SKYBLESSING",
           (_chance(), Field("f", "sid", "sid", None, "skill")) + _targets()),
    OpSpec(111, "USE_SKILL_IN_PLACE", "use_skill_in_place", "call", "use skill f" + _HOLD,
           (_chance(), Field("f", "sid", "sid", None, "skill")) + _targets()),
    OpSpec(112, "SHOOT", "shoot", "call",
           "fire a ballista the unit can reach (needs SID_SHOOT): action 49, else 42",
           (_chance(),) + _targets(), action=49),
    OpSpec(113, "ROCK_ATTACK", "rock_attack", "call",
           "use the nearest map object of kind 10 (the rocks of SEQ_*_ROCK100), scored by the units "
           "around it (action 46)", (_chance(),) + _targets("units in this list"),
           confidence="strong", action=46, result="reg[0] = 9 when there is none, else 0"),
    OpSpec(114, "ROCK_ATTACK_FORCE", "rock_attack_force", "call",
           "use a map object of kind 10 (action 46), no roll: the first one of the tile list e that the unit "
           "can reach, or with no list the nearest reachable one",
           (Field("e", "tiles", "tiles", 0, "tile list ((x << 16) | y words ended by 0xFFFF0000)"),),
           confidence="strong", action=46, result="reg[0] = 9 when there is none, else 0"),
    OpSpec(115, "TACKLE", "tackle", "call",
           "action 19 on the lowest-level unit next to a tile the unit can reach (SEQ_ALLUNITATTACK100_TACKLE100)",
           (_chance(),) + _targets(), confidence="tentative", action=19),
    OpSpec(116, "ATTACK_DIRECT", "attack_direct", "call",
           "attack (action 15) with the simpler tile choice of ai_check_attack_action_variant_b, then _a "
           "(SEQ_ALLATK100_DIRECT)", (_chance(),) + _targets(), confidence="strong", action=15),
    OpSpec(200, "MOVE_TO", "move_to", "call",
           "move towards tile (x, y); reg[0] = 8 when the tile reached is within 'near' tiles of it",
           (Field("c", "x", "int", None, "tile x"), Field("d", "y", "int", None, "tile y"),
            Field("a", "near", "int", 0, "distance that counts as arrived")), action=1, result="reg[0] = 8 when arrived"),
    OpSpec(201, "MOVE_TO_TALK", "move_to_talk", "call",
           "walk towards the character e; once next to it the move is dropped and reg[0] = 2",
           (Field("e", "pid", "pid", None, "character"),), action=1,
           result="reg[0]: 2 next to it, 9 not found, 1 not on the map, 4/5/6/7 its state flag 0x04/0x20/0x40/0x80"),
    OpSpec(202, "NOP_202", "nop202", "call", "does nothing (SEQ_NOMOVE)"),
    OpSpec(203, "MOVE_TO_CLASS", "move_to_class", "call",
           "move to the nearest unit of class e (not used by the vanilla scripts)",
           (Field("e", "jid", "jid", None, "class"),), confidence="strong", action=1),
    OpSpec(204, "DESTROY_VILLAGE", "destroy_village", "call",
           "open a door or chest first when possible; else, with SID_VILLAGEDESTROY, go to the nearest "
           "village event (kind 37) and destroy it (action 37). Counts tries; reg[0] = 10 when 'tries' is reached",
           (Field("c", "tries", "int", 0, "try limit (0 = none)"),), action=37,
           result="reg[0] = 9 when there is nothing to destroy, 10 at the try limit"),
    OpSpec(205, "MOVE_SAFEST", "move_safest", "call",
           "move to the reachable tile with the lowest threat value", confidence="strong", action=1),
    OpSpec(206, "MOVE_NEAREST", "move_nearest", "call",
           "move towards the target unit with the lowest path cost",
           _targets() + (Field("c", "fallback", "bool", False,
                               "when no tile under the threat limit gets closer, still move "
                               "(to the closest such tile, else the least threatened)"),), action=1),
    OpSpec(207, "MOVE_NEAREST_STRAIGHT", "move_nearest_straight", "call",
           "like move_nearest, the target picked ignoring the unit's class terrain costs "
           "(not used by the vanilla scripts)",
           _targets() + (Field("c", "fallback", "bool", False, "see move_nearest"),), confidence="strong", action=1),
    OpSpec(208, "NOP_208", "nop208", "call", "does nothing"),
    OpSpec(209, "MOVE_TO_EVENT", "move_to_event", "assign",
           "move to the nearest tile with an unseen event of kind c (adjacent: next to it); reg[a] = 8 when "
           "it is in reach, 9 when there is none; when it isn't reached this turn, try Chant, Steal, then an "
           "attack from the tile it stops on (not used by the vanilla scripts)",
           (Field("a", "reg", "reg", 0, "register for the result"), Field("c", "kind", "int", 0, "event kind"),
            Field("d", "adjacent", "bool", False, "stop next to the event tile")),
           confidence="strong", action=1, result="reg[a] = 8 in reach, 9 none"),
    OpSpec(210, "MOVE_RANDOM", "move_random", "call", "move to a random free tile within the unit's Mov "
           "(not used by the vanilla scripts)", action=1),
    OpSpec(211, "ESCAPE", "escape", "call",
           "go to the nearest escape point (event kind 44) and leave the map there; sets the unit's 'escape' "
           "mode (+0x254 bit 3), which set_scripts clears (SEQ_ESCAPEMOVE)", confidence="strong", action=44),
    OpSpec(212, "BREAK_OBJECT", "break_object", "call",
           "go to the nearest intact map object of kind 4 and act on it (action 39) (SEQ_BREAKMOVE)",
           confidence="tentative", action=39, result="reg[0] = 9 when there is none"),
    OpSpec(213, "NOP_213", "nop213", "call", "does nothing"),
    OpSpec(214, "NOP_214", "nop214", "call", "does nothing"),
    OpSpec(215, "TALK_MOVE", "talk_move", "call",
           "move next to the character e and talk to it (action 7); needs an unseen talk event between the two",
           (Field("e", "pid", "pid", None, "character"),), action=7,
           result="reg[0]: 3 talk queued, 9 no talk event / not found, 0 when the unit's +0x1A5 bits 4-6 "
                  "are set (nothing done), 1/4/5/6/7 as move_to_talk"),
    OpSpec(216, "FOLLOW_ROUTE", "follow_route", "call",
           "walk along the waypoint table e (loops back to the first point after the last). A waypoint "
           "counts as reached within 'reach' tiles; 'budget' is the movement spent per turn (negative: the "
           "unit's Mov)",
           (Field("e", "route", "route", None, "TBL_MAP*_ROUTE* table"),
            Field("c", "budget", "int", None, "movement per turn"),
            Field("a", "reach", "int", 0, "distance that counts as reached")), action=1),
    OpSpec(217, "MOVE_NEAREST_RANGED", "move_nearest_ranged", "call",
           "like move_nearest; with unit flag +0x254 bit 0x2000 the unit only closes in to its weapons' "
           "minimum range (SEQ_NEARESTUNITMOVEINDIRECT)",
           _targets() + (Field("c", "fallback", "bool", False, "see move_nearest"),), confidence="strong", action=1),
    OpSpec(218, "TALK", "talk", "call",
           "talk to the character e from where the unit stands (action 7); needs an unseen talk event",
           (Field("e", "pid", "pid", None, "character"),), action=7, result="reg[0] as talk_move"),
    OpSpec(500, "COUNT_UNITS", "count_units", "assign",
           "reg[a] = number of target units the unit could reach within Mov x range "
           "(+ its usable weapons' range with weapon_range)",
           (Field("a", "reg", "reg", 0, "register for the result"),
            Field("b", "range", "fixed", None, "factor of the unit's Mov (1.5 = one and a half)"),
            Field("c", "weapon_range", "bool", False, "add the unit's weapon range")) + _targets(),
           b_default=0, result="reg[a] = the count"),
    OpSpec(501, "HAS_SKILL_9", "has_skill_9", "assign",
           "reg[a] = 11 when the unit has skill #9 (SID_LYCANTHROPE in the vanilla FE8Data), else 0",
           (Field("a", "reg", "reg", 0, "register for the result"),), b_default=0, result="reg[a] = 0 or 11"),
    OpSpec(502, "USE_ITEM", "use_item", "call",
           "use the item e when the unit holds it and can use it (action 4); after a move action, the move "
           "becomes 'move, then use'; otherwise clears the found flag",
           (Field("e", "iid", "iid", None, "item"),), b_default=0, action=4),
    OpSpec(600, "MOVE_STAT", "move_stat", "assign",
           "add d to the unit's Mov bonus (+0x1AA, kept), then reg[a] = its Mov",
           (Field("a", "reg", "reg", 0, "register for the result"), Field("d", "add", "int", 0, "Mov bonus change")),
           b_default=0, result="reg[a] = Mov"),
    OpSpec(1000, "STOP", "stop", "call",
           "end this run; the next run starts at label 'resume' (0 = first entry). Same code as end",
           (Field("d", "resume", "label", 0, "where the next run starts"),), b_default=0),
    OpSpec(1001, "END", "end", "call",
           "end this run; the next run starts at label 'resume' (0 = first entry)",
           (Field("d", "resume", "label", 0, "where the next run starts"),), b_default=0),
]

OPS: dict[int, OpSpec] = {spec.op: spec for spec in _LIST}
BY_NAME: dict[str, OpSpec] = {spec.name: spec for spec in _LIST if spec.form != "header"}
NOP_OPS = (102, 109, 202, 208, 213, 214)
HANDLED_OPS = frozenset(OPS)

#: COMPARE's b -> operator
COMPARISONS = {0: ">", 1: ">=", 2: "==", 3: "<=", 4: "<", 5: "!="}
COMPARISON_CODES = {v: k for k, v in COMPARISONS.items()}

#: codes the action and move entries leave in reg[0]
RESULT_CODES = {
    1: ("NOT_ON_MAP", "the character isn't on the map (reserve or inactive)"),
    2: ("NEXT_TO_TARGET", "move_to_talk: next to the character"),
    3: ("TALK_QUEUED", "talk / talk_move: the talk action was queued"),
    4: ("TARGET_STATE_04", "the character has state flag 0x04 (+0x1A0)"),
    5: ("TARGET_STATE_20", "the character has state flag 0x20"),
    6: ("TARGET_STATE_40", "the character has state flag 0x40"),
    7: ("TARGET_STATE_80", "the character has state flag 0x80"),
    8: ("ARRIVED", "move_to / move_to_event: destination in reach"),
    9: ("NONE_FOUND", "no target / event / object"),
    10: ("TRY_LIMIT", "destroy_village: the try limit is reached"),
    11: ("HAS_SKILL", "has_skill_9: the unit has the skill"),
}
RESULT_NAMES = {name: code for code, (name, _) in RESULT_CODES.items()}

#: map action ids the opcodes register (register_available_action)
ACTIONS = {
    1: "move / wait on a tile", 4: "use item", 7: "talk", 15: "weapon attack", 16: "use staff",
    17: "steal", 19: "tackle (tentative)", 21: "gamble attack", 37: "destroy village",
    39: "act on a map object (tentative)", 42: "shoot (ballista, second kind)", 44: "escape",
    46: "rock / map object of kind 10", 49: "shoot (ballista)",
}

#: register file size (memset 0x10 at the start of each unit's turn)
REGISTER_COUNT = 4


def describe(op: int) -> str:
    """One-paragraph help for an opcode."""
    spec = OPS.get(op)
    if spec is None:
        return f"Opcode {op} has no handler: the game would misbehave."
    lines = [f"{spec.op} {spec.key} - {spec.summary}."]
    for f in spec.fields:
        lines.append(f"  {f.slot} = {f.name}: {f.help}")
    if not spec.uses_b and spec.form != "header":
        lines.append(f"  b = threat_limit (default {spec.b_default:#x}): when non-zero, sets the threat limit "
                     "the move checks use")
    if spec.result:
        lines.append(f"  Result: {spec.result}.")
    if spec.confidence != "confirmed":
        lines.append(f"  Confidence: {spec.confidence}.")
    return "\n".join(lines)
