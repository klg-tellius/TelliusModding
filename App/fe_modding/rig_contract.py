"""What a unit's rig must provide, and the checks and rig kit built on it.

See ``research/GRAPHICS_NOTES.md``, "Rig contract":

- **Anchor bones** (flag ``0x80000000``) are the only bones the engine finds
  by name (``find_anchor_bone_by_token``): ``_r_hand_``/``_l_hand_`` hold the
  weapon, ``_root_`` carries the actor's position across animation switches,
  ``_cam_`` is a camera target, ``_s1_``/``_s2_`` place a map model's feet
  and shadow, pairs such as ``_ax1_``/``_ax2_`` are weapon-trail ends.
- **Combat events**: the battle script advances on the attacker's event
  codes ``0`` (the blow lands) and ``1`` (the swing, on a miss); ``2``
  releases a thrown or fired item. An animation that replaces one carrying
  them must carry them too.
- **Battle roles** come from ``zu/<code>.dbx``: ``<weapon>_<role>`` (or
  ``<weapon>_<role>_<next role>``) names the file to play.
- **Map weapons** are body meshes on their own bones, shown or hidden by
  each animation's scale (``Ax`` for the axe, ``Ax1`` for the hand axe).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .formats import animation, engine_pose, skeleton, zdbx

#: Codes the battle script waits for (``process_combat_round_controller_tick``,
#: ``spawn_attack_message_popup_and_advance_round``).
COMBAT_CODES = {
    0: "the blow lands (damage, HP gauge)",
    1: "the swing (moves the round on after a miss)",
    2: "releases the thrown or fired item",
}

#: Other event codes, for the rig kit sheet.
EVENT_NAMES = {
    3: "loop start",
    4: "loop end",
    8: "projectile hit",
    0x14: "sword trail start",
    0x15: "spear trail start",
    0x16: "axe trail start",
    0x17: "bow trail start",
    0x18: "ex trail start",
    0x19: "trail end",
    0x1A: "javelin trail start",
    0x1B: "hand-axe trail start",
    0x28: "crit camera/light effect",
    0x29: "crit camera/light effect",
    47: "footstep",
    48: "footstep",
    50: "footstep / dust",
}

#: Anchor bones and what the engine does with them. Imports refuse a rig
#: that lacks one the replaced rig had (``gltf_import.check_rig_against``).
ANCHORS = {
    "_r_hand_": "holds the weapon (every weapon but bows)",
    "_l_hand_": "holds the bow",
    "_root_": "follows the hips; carries the unit's position from one battle animation to the next",
    "_cam_": "battle camera target",
    "_lfoot_": "foot contact (optional)",
    "_rfoot_": "foot contact (optional)",
    "_pl_": "origin of crit camera and light effects (optional)",
    "_s1_": "map foot and shadow point",
    "_s2_": "map foot and shadow point",
}
TRAIL_RE = re.compile(r"^_(sw|sp|ax|bw|ex|ja|ha|ar)[12]_$")

#: Map actions (``format_map_animation_path``'s table at ``0x80285880``).
MAP_ACTIONS = {
    "wait": "idle",
    "move": "walk",
    "move2": "walk (second style)",
    "atk1": "attack",
    "atk2": "second attack",
    "crit": "critical hit",
    "crit2": "second critical hit",
    "rod": "staff",
    "tackle": "unarmed attack; also plays for any action the model does not enable",
    "escape": "dodge",
    "ready": "stance before acting",
    "damage": "hit reaction",
    "trans": "transformation",
    "dead": "death",
    "magic1": "spell",
    "magic2": "second spell",
    "event": "cutscene pose",
}

#: Battle roles of ``zu/<code>.dbx`` (Japanese keys) and file-name suffixes.
BATTLE_ROLES = {
    "待機": "idle",
    "構え": "ready stance",
    "攻撃1": "attack 1",
    "攻撃2": "attack 2",
    "必殺1": "critical 1",
    "必殺2": "critical 2",
    "回避": "dodge",
    "ダメージ": "damage",
    "死亡": "death",
    "走り": "run",
    "摺足": "sidestep",
    "投げ": "throw",
    "必殺投げ": "critical throw",
    "射撃": "shot",
    "必殺射撃": "critical shot",
    "魔法": "spell",
}
BATTLE_SUFFIXES = {
    "poi": "idle / ready stance",
    "at1": "attack 1",
    "at2": "attack 2",
    "cr1": "critical 1",
    "cr2": "critical 2",
    "dog": "dodge",
    "dam": "damage",
    "ded": "death",
    "mov": "run",
    "sds": "sidestep",
    "lda": "throw",
    "ldc": "critical throw",
    "lar": "ranged",
    "arc": "ranged",
}

#: A bone whose world scale is under this is hidden.
HIDDEN_SCALE = 0.01


def combat_codes(events: list[animation.EventKey]) -> set[int]:
    return {c for key in events for c in key.codes if c in COMBAT_CODES}


def event_errors(name: str, new_ga: bytes, vanilla_ga: bytes) -> list[str]:
    """The combat codes ``vanilla_ga`` carries that ``new_ga`` lacks."""
    wanted = combat_codes(animation.read_animation_bytes(vanilla_ga).events)
    have = combat_codes(animation.read_animation_bytes(new_ga).events)
    missing = sorted(wanted - have)
    if not missing:
        return []
    listed = ", ".join(f"{c} ({COMBAT_CODES[c]})" for c in missing)
    return [f"{name} lacks event code {listed}: the fight would wait for it forever."]


def replace_events(ga: bytes, events: list[animation.EventKey]) -> bytes:
    """``ga`` with its event track (footer slot 0) replaced."""
    anim = animation.read_animation_bytes(ga)
    events = sorted(events, key=lambda k: k.frame)
    footer = anim.footer
    if events:
        if footer is None:
            footer = animation.GaFooter()
        footer.blocks[0] = animation.write_event_block(events)
        if 0 not in footer.order:
            footer.order = [0] + footer.order
            footer.trailing = b""
    elif footer is not None and footer.blocks[0] is not None:
        footer.blocks[0] = None
        footer.order = [s for s in footer.order if s != 0]
    anim.events = events
    anim.footer = footer
    return animation.write_animation(anim)


def hidden_bones(bones: list[skeleton.Bone], ga: bytes, frame: float = 0.0) -> set[str]:
    """Bones scaled to (near) zero at ``frame``."""
    anim = animation.read_animation_bytes(ga)
    world, _palette = engine_pose.pose(bones, anim, frame)
    hidden = set()
    for bone, m in zip(bones, world):
        scale = max(sum(m[r][c] ** 2 for r in range(3)) ** 0.5 for c in range(3))
        if scale < HIDDEN_SCALE:
            hidden.add(bone.name)
    return hidden


def weapon_bones(bones: list[skeleton.Bone], animations: dict[str, bytes]) -> dict[str, set[str]]:
    """Per animation, the switchable bones it hides: bones hidden by some
    animations and shown by others (a map model's weapons)."""
    per = {name: hidden_bones(bones, data) for name, data in animations.items()}
    everywhere = set.intersection(*per.values()) if per else set()
    switchable = set().union(*per.values()) - everywhere if per else set()
    return {name: hidden & switchable for name, hidden in per.items()}


def visibility_warnings(
    old_bones: list[skeleton.Bone],
    old_animations: dict[str, bytes],
    new_bones: list[skeleton.Bone],
    new_animations: dict[str, bytes],
) -> list[str]:
    """Map weapons: the new rig must show and hide the same weapon bones as
    the old one in each animation."""
    old = weapon_bones(old_bones, old_animations)
    switchable = set().union(*old.values()) if old else set()
    if not switchable:
        return []
    new_names = {b.name for b in new_bones}
    warnings = []
    missing = sorted(switchable - new_names)
    if missing:
        warnings.append(
            "The new skeleton lacks the weapon bones " + ", ".join(missing) + ": the map model shows its weapons "
            "by scaling those bones (1 shown, 0 hidden), so the weapons will not switch."
        )
    kept = switchable & new_names
    wrong = []
    for name, data in new_animations.items():
        if name not in old:
            continue
        hidden_now = hidden_bones(new_bones, data) & kept
        if hidden_now != old[name] & kept:
            wrong.append(name)
    if wrong:
        warnings.append(
            "These animations show or hide weapon bones differently from the originals ("
            + ", ".join(sorted(kept))
            + "): "
            + ", ".join(sorted(wrong))
        )
    return warnings


# ---------------------------------------------------------------- battle roles


def read_battle_roles(zdbx_data: bytes, code: str) -> list[tuple[str, str]]:
    """``(role key, file stem)`` lines of ``zu/<code>.dbx``."""
    for entry in zdbx.read_zdbx_archive(zdbx_data):
        if entry.name == f"zu/{code}.dbx":
            lines = []
            for line in entry.text.splitlines():
                fields = line.split("#", 1)[0].split()
                if len(fields) == 2 and "_" in fields[0] and fields[0].split("_", 1)[0].isascii():
                    weapon = fields[0].split("_", 1)[0]
                    if weapon.isalpha() and weapon.islower() and len(weapon) <= 3:
                        lines.append((fields[0], fields[1]))
            return lines
    return []


def describe_role(key: str) -> str:
    """``ax_必殺1_攻撃1`` -> ``axe: critical 1, then attack 1``."""
    weapon, *roles = key.split("_")
    return f"{weapon}: " + ", then ".join(BATTLE_ROLES.get(r, r) for r in roles)


def describe_battle_file(stem: str) -> str:
    parts = stem.split("_")
    if len(parts) < 3:
        return ""
    text = BATTLE_SUFFIXES.get(parts[1], parts[1])
    if len(parts) > 3:
        text += ", followed by " + BATTLE_SUFFIXES.get(parts[3], parts[3])
    return text


def describe_map_file(stem: str) -> str:
    action = stem.split("_")[0].lower()
    return MAP_ACTIONS.get(action, "")


# ---------------------------------------------------------------- rig kit


@dataclass
class KitAnimation:
    file: str
    pack: str
    frames: int
    loops: bool
    events: list[animation.EventKey]
    role: str
    hidden_weapons: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)


def rig_kit_sheet(
    label: str,
    bones: list[skeleton.Bone],
    animations: list[KitAnimation],
    battle: bool,
) -> str:
    """The rig kit's checklist (Markdown)."""
    world = engine_pose.world_matrices(bones, engine_pose.local_matrices(bones, None, 0))
    out = [f"# Rig kit: {label}", ""]
    out.append(
        "Everything a replacement rig must provide. The `.glb` next to this sheet holds the original skeleton, "
        "body and every animation, each named like its file: import it in Blender as the reference."
    )
    out += ["", "## Anchor bones", "", "Names must match exactly; every other bone name is free.", ""]
    out += ["| Bone | Position | Purpose |", "|---|---|---|"]
    for i, bone in enumerate(bones):
        if not (bone.name.startswith("_") and bone.name.endswith("_") and len(bone.name) > 2):
            continue
        at = engine_pose.apply(world[i], engine_pose.rest_pivot(bone))
        purpose = ANCHORS.get(bone.name) or ("weapon-trail end" if TRAIL_RE.match(bone.name) else "")
        out.append(f"| `{bone.name}` | {at[0]:.2f}, {at[1]:.2f}, {at[2]:.2f} | {purpose} |")
    switchable = sorted({b for a in animations for b in a.hidden_weapons})
    if switchable:
        out += ["", "## Map weapons", ""]
        out.append(
            "Weapons are part of the body mesh, each on its own bone. Each animation scales the weapon in use to 1 "
            "and the others to 0:"
        )
        out.append("")
        for a in animations:
            shown = [b for b in switchable if b not in a.hidden_weapons]
            out.append(f"- `{a.file}`: shows {', '.join(shown) or 'none'}; hides {', '.join(a.hidden_weapons) or 'none'}")
    out += ["", "## Animations", ""]
    if battle:
        out.append(
            "A glTF animation named like a file fills it in every pack that holds that file; `name@pack` (for "
            "example `fig1_dam_ax@ha`) fills one pack only. A follow-up clip (`fig1_cr1_ax_at1`) left out reuses "
            "its base clip (`fig1_cr1_ax`), and a clip left out for one weapon reuses the same role of another."
        )
        out.append("")
    out.append(
        "Events: an animation without events in its glTF `extras` keeps the original's, retimed to its length. "
        "Codes 0 and 1 (melee attacks) and 2 (throws) are required where the original has them."
    )
    out += ["", "| File | Pack | Frames | Loops | Role | Events (frame: codes) |", "|---|---|---|---|---|---|"]
    for a in animations:
        events = "; ".join(
            f"{e.frame}: " + ", ".join(
                f"**{c}**" if c in COMBAT_CODES else (f"{c} ({EVENT_NAMES[c]})" if c in EVENT_NAMES else str(c))
                for c in e.codes
            )
            for e in a.events
        )
        role = a.role + (" — " + "; ".join(a.roles) if a.roles else "")
        out.append(f"| `{a.file}` | {a.pack} | {a.frames} | {'yes' if a.loops else 'no'} | {role} | {events} |")
    out += ["", "Bold codes are the ones combat waits for.", ""]
    return "\n".join(out)


def kit_animation(file: str, pack: str, data: bytes, role: str, bones=None, hidden=None, roles=None) -> KitAnimation:
    anim = animation.read_animation_bytes(data)
    return KitAnimation(
        file=file,
        pack=pack,
        frames=anim.header.end_frame,
        loops=anim.header.loops,
        events=list(anim.events),
        role=role,
        hidden_weapons=sorted(hidden or ()),
        roles=list(roles or ()),
    )


def kit_json(animations: list[KitAnimation]) -> str:
    """The animation list as JSON, for scripts (Blender add-ons...)."""
    return json.dumps(
        [
            {
                "file": a.file,
                "pack": a.pack,
                "frames": a.frames,
                "loops": a.loops,
                "role": a.role,
                "roles": a.roles,
                "events": [[e.frame, list(e.codes)] for e in a.events],
                "hidden_weapons": a.hidden_weapons,
            }
            for a in animations
        ],
        ensure_ascii=False,
        indent=1,
    )
