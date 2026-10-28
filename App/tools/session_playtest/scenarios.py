"""Every test of the session: what it builds, where it boots, what to do and what to look for.

Chapter numbers are ChapterData ids (the file numbers): id 1 is the Prologue, id 2 is the game's
"Chapter 1", id 4 is "Chapter 3", and so on. The instructions always use the in-game names.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from fe_modding.formats import save_file as sf

from .harness import Scenario
from fe_modding.game_profile import files_root_of

US = "GFEE01"

# The base save used for every "real army" test: chapter12.gci, File 3, the base before the
# game's Chapter 12 (ChapterData id 13), 19 units with Ike, Titania, Boyd, Lethe, Sothe, Volke,
# Soren. It is a cheat save (all units promoted, 99,999,999 gold), which makes edits easy to see.
ARMY_GCI, ARMY_BLOCK = "chapter12.gci", 5

JUMP_NOTE = ("Dolphin starts the game; press A on the warning screen. The game then goes straight "
             "into the chapter on Hard (no title screen, no file menu, no tutorials). Press Start to skip cutscenes that are "
             "not part of the test. Tab (Dolphin's default hotkey) turns the speed limit off and on.")
TITLE_NOTE = ("Dolphin starts the game normally; press A on the warning screen, then Start through the intro "
              "and the title screen; 'Restart Chapter' in the file menu lists the saves. The memory card in slot A is a folder holding only this test's save.")


def in_game(chapter: int) -> str:
    return "the Prologue" if chapter == 1 else f"Chapter {chapter - 1}"


# -- helpers ---------------------------------------------------------------------------------------

def _first_enemies(ctx, folder: str, variant: str):
    docs = ctx.dispos(folder)
    doc = docs[f"dispos_{variant}.bin"]
    section = next(s for s in doc.sections if s.name == f"{folder}_first_{variant}")
    return section.units


def _boss(units):
    return next(u for u in units if u[38] & 0x04)


def _army_save(ctx):
    save = ctx.load_save(ARMY_GCI)
    return save, save.blocks[ARMY_BLOCK]


def _newest_block(card: Path, slot: int, newer_than: int = 0, checkpoints: bool = False):
    """The newest valid file save of ``slot`` (0-based) on the test card written after sequence
    ``newer_than`` (the block the test started from), or None; ``checkpoints`` also takes the
    suspended maps of that slot."""
    best = None
    for path in card.glob("*.gci"):
        save = sf.SaveFile.from_bytes(path.read_bytes())
        for block in save.blocks:
            if block is None or not block.decoded or not block.crc_ok or block.header.sequence <= newer_than:
                continue
            if (not block.is_checkpoint and block.header.save_kind == 2 and block.header.file_slot == slot
                    or checkpoints and block.is_checkpoint and block.header.owner_slot == slot):
                if best is None or block.header.sequence > best.header.sequence:
                    best = block
    return best


# -- A: harness and launch paths ----------------------------------------------------------------------

def build_a1(ctx):
    normal, hard = _first_enemies(ctx, "bmap02", "n"), _first_enemies(ctx, "bmap02", "h")
    boss_n, boss_h = _boss(normal), _boss(hard)
    record = ctx.chapter_record(2)
    ctx.facts.update(boss_class=ctx.job(boss_h[1]).jid.removeprefix("JID_").title(),
                     boss_n=boss_n[36] + (record.enemy_bonus_levels[0] if boss_n[38] & 1 else 0),
                     boss_h=boss_h[36] + (record.enemy_bonus_levels[1] if boss_h[38] & 1 else 0),
                     enemies_n=sum(1 for u in normal if u[37] == 1), enemies_h=sum(1 for u in hard if u[37] == 1))


def card_a2(ctx):
    save, block = _army_save(ctx)
    block.party.gold = 123456
    ike = ctx.unit(block, "PID_IKE")
    ike.level, ike.exp = 7, 42
    ctx.set_items(ctx.unit(block, "PID_TIAMAT"), ["IID_HANDAXE", "IID_STEELAXE", "IID_VULNERARY"])
    return {"session_A2.gci": ctx.save_copy(save, ARMY_BLOCK)}


def card_a3(ctx):
    save, block = _army_save(ctx)
    block.party.gold = 7777
    return {"session_A3.gci": ctx.save_copy(save, ARMY_BLOCK, chapter=2)}


# -- B: chapter flow -----------------------------------------------------------------------------------

B_TITLE = "Session Test Chapter"


def build_b1(ctx):
    from fe_modding import chapters
    from fe_modding.game_code import chapter_flow

    flow = chapter_flow.ChapterFlow(ctx.code)
    plan = chapters.add_story_chapter(ctx.project, ctx.fe8, "02", 33, B_TITLE, after=1, flow=flow)
    ctx.fe8 = plan.fe8data
    ctx.drop_editor()
    ctx.facts["warnings"] = "; ".join(plan.warnings) or "none"


def card_b2(ctx):
    """The army save moved to the start of the added chapter 33. The cheat save's clear history is
    full (40 of 40), and a full history records no clear, so no continued-part flag either (B3):
    the last 10 entries are emptied."""
    save, block = _army_save(ctx)
    history = block.party.clear_history
    for i in range(len(history) - 10, len(history)):
        history[i] = sf.ClearRecord(0, 0, 0, 0)
    return {"session_B.gci": ctx.save_copy(save, ARMY_BLOCK, chapter=33)}


def build_b2(ctx):
    from fe_modding.game_code.chapter_parts import ChapterParts

    build_b1(ctx)
    ChapterParts(ctx.code).set_continued(33, True)


# -- C: Game Code rules ------------------------------------------------------------------------------------

def build_c1(ctx):
    """Chapter 3 (C04): forecast rules, Charisma/Horror, rings, villages. Every check reads the
    ENEMY's Hit in the forecast, which stays below the 100 cap, or a same-enemy difference."""
    ctx.patch("combat.no_terrain_bonus", "combat.player_charisma",
              "economy.rings_first_playthrough", "map.no_village_destruction")
    ctx.tunes({"combat.triangle_hit_advantage": 40, "combat.triangle_atk_advantage": 6,
               "combat.triangle_hit_disadvantage": -40, "combat.triangle_atk_disadvantage": -6,
               "combat.charisma_bonus": 30, "combat.charisma_range": 3,
               "combat.horror_penalty": -30, "combat.horror_range": 3})
    ctx.add_character_skill("PID_IKE", "SID_CHARISMA")
    docs = ctx.dispos("bmap04")
    for variant, doc in docs.items():
        ike = None
        for section in doc.sections:
            for unit in section.units:
                if unit[0] == "PID_IKE":
                    unit[38] |= 0x04                     # group commander: his Charisma helps his army
                    ike = unit
                if unit[0] == "PID_TIAMAT":              # lance C / axe A: same-enemy triangle comparison
                    unit[3:11] = ["IID_IRONLANCE", "IID_IRONAXE", "IID_VULNERARY", 0, 0, 0, 0, 0]
                    unit[40:48] = [0] * 8
        first = next((s_ for s_ in doc.sections if s_.name == f"bmap04_first_{variant[7]}"), None)
        if first is None:
            continue
        bandit = next(u for u in first.units if u[1] == "JID_BANDIT" and u[0] == "PID_BANDIT_SEA" and u[36] == 2)
        bandit[32], bandit[33], bandit[34], bandit[35] = 21, 20, 21, 20      # beside the village door (20, 20)
        _check_tiles(ctx, "bmap04", [(21, 20)])
        if ike is not None:
            # Horror on the enemy closest to Ike's start (a dispos skill slot, field 11).
            near = min((u for u in first.units if u is not bandit and u[38] & 0x04 == 0),
                       key=lambda u: abs(u[32] - ike[32]) + abs(u[33] - ike[33]))
            near[11] = "SID_HORROR"
            if variant == "dispos_h.bin":
                ctx.facts["horror"] = ctx.job(near[1]).jid.removeprefix("JID_").title()
                ctx.facts["horror_far"] = abs(near[32] - ike[32]) + abs(near[33] - ike[33])
    ctx.write_dispos("bmap04", docs)


def _reorder_army(ctx, block, first_pids):
    """Relink the player army list (unit +0x180/+0x184, 1-based slots) with ``first_pids`` first."""
    slot_of = {unit.character: i + 1 for i, unit in enumerate(block.units) if unit is not None and unit.army == 0}
    head = next(s for s in slot_of.values() if block.units[s - 1].prev_slot == 0)
    order, seen, slot = [], set(), head
    while slot and slot not in seen:
        order.append(slot)
        seen.add(slot)
        slot = block.units[slot - 1].next_slot
    wanted = [slot_of[ctx.character(pid).index + 1] for pid in first_pids]
    if wanted[0] != head:
        raise ValueError("the army list must keep its head first")
    order = wanted + [s for s in order if s not in wanted]
    for i, slot in enumerate(order):
        unit = block.units[slot - 1]
        unit.prev_slot = order[i - 1] if i else 0
        unit.next_slot = order[i + 1] if i + 1 < len(order) else 0


def card_c3(ctx):
    """The army save, edited for promotions, steal, laguz gauge and level-ups, moved to the base."""
    save, block = _army_save(ctx)
    # The shared army save has a late-game Ike whose high stats can hide the support-bonus change.
    # Rebuild him at his character-record defaults while preserving his support data with Titania.
    ike = ctx.unit(block, "PID_IKE")
    person = ctx.character("PID_IKE")
    ike.stats = bytes(8)
    ike.growth_points = bytes(8)
    ike.build_bonus = ike.move_bonus = 0
    ctx.set_unit_job(ike, person.jid, person.level, 0)
    ike.weapon_exp = bytes((31, 0, 0, 0, 0, 0, 0, 0))
    ctx.set_items(ike, ["IID_IRONSWORD"])
    sothe = ctx.unit(block, "PID_SOTHE")
    ctx.set_unit_job(sothe, "JID_THIEF", 10, 90)
    ctx.set_items(sothe, ["IID_KNIFE", "IID_MASTERPROOF", "IID_VULNERARY"])
    soren = ctx.unit(block, "PID_SENERIO")
    ctx.set_unit_job(soren, "JID_MAGE_W", 15, 0)
    ctx.set_items(soren, ["IID_WIND", "IID_MASTERPROOF"])
    boyd = ctx.unit(block, "PID_BOLE")
    ctx.set_unit_job(boyd, "JID_WARRIOR", 12, 0)
    ctx.set_items(boyd, ["IID_STEELAXE", "IID_MASTERCROWN"])
    # A default Lethe instead of the saved one, which is in the transformed Cat class at Lv 20 with a
    # fixed full gauge: her own human-form class, Lv 3, no gains, start gauge 16, Cat Nail.
    lethe = ctx.unit(block, "PID_LETHE")
    person = ctx.character("PID_LETHE")
    lethe.stats = bytes(8)
    ctx.set_unit_job(lethe, person.jid, person.level, 0)
    lethe.transform_gauge = 0              # the gain is added at every player phase start, turn 1 included
    ctx.set_items(lethe, ["IID_CATNAIL"])
    # A chapter without preparations gives its slots to the army in list order (prev/next links), not
    # by character: put the seven test units first, Ike staying the head.
    _reorder_army(ctx, block, ("PID_IKE", "PID_TIAMAT", "PID_OSCAR", "PID_BOLE",
                               "PID_SOTHE", "PID_SENERIO", "PID_LETHE"))
    # Boyd and Titania list each other (Boyd slot 0, Titania slot 2, C at 7). A unit with 5 support
    # stars gains no points, and the cheat save has both at 6: Boyd's points are all cleared, Titania
    # keeps only her A with Ike (slot 0, 3 stars, for the range check). The pair then gains 3 points.
    ctx.unit(block, "PID_BOLE").supports = bytes(10)
    titania = ctx.unit(block, "PID_TIAMAT")
    titania.supports = titania.supports[:1] + bytes(9)
    ctx.facts["crown"] = "IID_MASTERCROWN"
    # Chapter 1's bandits, not the Chapter 12 map (Sothe at Lv 10 did not survive there).
    return {"session_C3.gci": ctx.save_copy(save, ARMY_BLOCK, chapter=C3_CHAPTER)}


C3_CHAPTER = 2
#: Chapter 1 deploys only Ike, Titania, Oscar and Boyd: three more player slots beside them. Like
#: the vanilla ones they carry flag 0x08, which ties a slot to its own character (without it the
#: slot goes to any reserve unit).
#: Tiles inside the playable grid (x 2-13, y 2-17 on bmap02), clear of where the opening walks the
#: vanilla four: Oscar (13,16), Titania (11,16), Ike (12,17), Boyd (10,17).
C3_SLOTS = (("PID_SOTHE", 12, 15), ("PID_SENERIO", 13, 17), ("PID_LETHE", 11, 15))
C3_TAKEN = {(13, 16), (11, 16), (12, 17), (10, 17)}


def _check_tiles(ctx, folder: str, tiles, taken=frozenset()):
    """Refuse a fixture that puts a unit off the playable grid, on blocked terrain or on a taken tile."""
    from fe_modding import map_props
    from fe_modding.formats import map_file

    _entries, files = map_props.read_map_container(files_root_of(ctx.project) / "zmap" / folder / "map.cmp")
    raw = next(v for k, v in files.items() if k.lower().endswith("map.bin"))
    data, grid = map_file.read_map_bytes(raw), map_file.terrain_grid(raw)
    buffer, cap = data.extra.grid_buffer, data.capacity
    for x, y in tiles:
        if not (buffer <= x < cap.x_size - buffer and buffer <= y < cap.y_size - buffer):
            raise ValueError(f"{folder}: ({x},{y}) is outside the playable grid")
        if grid[x][y] in ("崖", "移動不可", "建物", "廃墟", "柵", "海"):
            raise ValueError(f"{folder}: ({x},{y}) is {grid[x][y]}, not a tile a unit can stand on")
        if (x, y) in taken:
            raise ValueError(f"{folder}: ({x},{y}) is taken")


def _c3_deployment(ctx):
    from fe_modding.formats import dispo

    _check_tiles(ctx, "bmap02", [(x, y) for _pid, x, y in C3_SLOTS], C3_TAKEN)

    docs = ctx.dispos("bmap02")
    for variant, doc in docs.items():
        letter = variant[7]
        mikata = doc.section(f"bmap02_mikata_{letter}")
        if mikata is not None:
            for pid, x, y in C3_SLOTS:
                values = dispo.new_unit_values()
                values[0], values[32], values[33], values[34], values[35] = pid, x, y, x, y
                values[38] |= dispo.FLAG_SPAWN_WHEN_ABSENT
                dispo.add_unit(doc, mikata.name, values)
        first = doc.section(f"bmap02_first_{letter}")
        if first is not None:
            # Steal target: the axe fighter closest to the start, faster than Sothe and carrying a Vulnerary.
            target = min((u for u in first.units if u[1] == "JID_FIGHTER"),
                         key=lambda u: abs(u[32] - 14) + abs(u[33] - 17))
            target[23] = 15                      # bonus_spd
            target[4], target[41] = "IID_VULNERARY", 0
    ctx.write_dispos("bmap02", docs)


def build_c3(ctx):
    from fe_modding.game_code import three_tier_data

    _c3_deployment(ctx)

    # Three tiers: Fighter -> Warrior -> Berserker; the Crown is a new item record.
    data = three_tier_data.provision(ctx.fe8, US)
    common = files_root_of(ctx.project) / "Mess" / "common.m"
    ctx.project.write_keeping_original(common, three_tier_data.provision_messages(common.read_bytes(), US, "en"))
    ctx.fe8 = data
    ctx.set_class("JID_WARRIOR", promotes_to="JID_BERSERKER")
    berserker = ctx.job("JID_BERSERKER")
    free = [i for i, s in enumerate(berserker.skills) if s is None]
    if "SID_HIGHER" not in berserker.skills:
        ctx.set_class("JID_BERSERKER", **{f"skill{free.pop(0)}": "SID_HIGHER"})
    ctx.set_class("JID_BERSERKER", **{f"skill{free.pop(0)}": three_tier_data.TIER3_SID})
    # Boyd has one character-specific promoted animation ID, which cannot distinguish Warrior
    # from a new third tier.  Let the current class provide its model so Warrior remains a
    # Warrior and the second promotion switches to the Berserker model.
    ctx.set_character("PID_BOLE", aid_promoted=None)
    three_tier_data.validate_chain(ctx.fe8, "JID_FIGHTER", "JID_WARRIOR", "JID_BERSERKER")
    # Anima choice: Wind Sage offers Fire and Thunder in the promotion weapon picker. The Wind classes,
    # not Soren's own JID_MAGE (which already starts Fire and Thunder at E), so the grant is visible.
    ctx.set_class("JID_SAGE_W", weapon_ranks="----**C--")
    ctx.patch("promotion.three_tiers", "promotion.event_classes", "promotion.anima_weapon_choice",
              "combat.steal_ignores_speed", "support.full_bonus", "growth.force_random", "random.fixed_seed")
    ctx.tunes({"support.range": 6, "support.points_per_chapter": 3, "laguz.turn_gain": 4,
               "random.seed": 1234, "promotion.crown_min_level": 10,
               **{f"growth.random.{i}": 3 for i in range(8)}})


def after_c3(card: Path, ctx) -> list[str]:
    before = _army_save(ctx)[1]
    block = _newest_block(card, 2, before.header.sequence, checkpoints=True)
    if block is None or not block.is_checkpoint:
        return ["No suspend on the next map: support points are added when that map starts, so suspend on "
                "its first turn to let this check run."]
    lines = []
    for pid, slot in (("PID_BOLE", 0), ("PID_TIAMAT", 2)):
        number = ctx.character(pid).index + 1          # any army: Chapter 2's story sets Titania aside
        points = next(u for u in block.units if u is not None and u.character == number).supports[slot]
        lines.append(f"{pid} points with {'Titania' if pid == 'PID_BOLE' else 'Boyd'}: 0 -> {points} "
                     f"({'PASS' if points == 3 else 'expected 3 if both were deployed'})")
    return lines


def card_c4(ctx):
    save, block = _army_save(ctx)
    block.party.gold = 60000
    return {"session_C4.gci": ctx.save_copy(save, ARMY_BLOCK)}


def build_c4(ctx):
    ctx.patch("economy.unlimited_forging")
    ctx.tunes({"economy.gold_cap": 50000, "economy.forge_hit_step": 7, "economy.forge_crit_step": 4})


def after_c4(card: Path, ctx) -> list[str]:
    before = _army_save(ctx)[1]
    block = _newest_block(card, 2, before.header.sequence)
    if block is None:
        return ["No new File 3 save on the card: save at the base after forging."]
    forged = [f for f in block.forges if f.allocated]
    old = sum(1 for f in before.forges if f.allocated)
    lines = [f"Gold in the new save: {block.party.gold:,} (expected 50,000 or less)",
             f"Forge records in use: {old} -> {len(forged)} (expected at least 2 more)"]
    items = ctx.data.items
    holders = [("convoy", slot) for slot in block.convoy] + [
        (ctx.data.characters[u.character - 1].pid.removeprefix("PID_"), slot)
        for u in block.units if u is not None and u.army in (0, 5) for slot in u.items]
    for owner, slot in holders:
        if slot.item and slot.forge:
            record = block.forges[slot.forge - 1]
            lines.append(f"  {owner}: {items[slot.item - 1].iid} -> forge {slot.forge} {record.name_text!r} "
                         f"(Mt {record.might:+d}, Hit {record.hit:+d}, Crit {record.crit:+d}, Wt {record.weight:+d})")
    if not any(slot.item and slot.forge for _owner, slot in holders):
        lines.append("  No item in the convoy or an inventory points to a forge record.")
    return lines


def build_c5(ctx):
    ctx.tunes({"phases.enemy": 1})      # 1 = Player (choices: No phase, Player, Computer)


def build_c6(ctx):
    # Chapter 1's player records deliberately carry SEQ_NOATTACK / SEQ_NOMOVE.  A computer-
    # controlled player phase faithfully obeys those orders, so give the four player slots the
    # ordinary mobile-enemy orders this fixture is meant to exercise.
    docs = ctx.dispos("bmap02")
    mobile = next(
        unit
        for doc in docs.values()
        for section in doc.sections
        for unit in section.units
        if unit[37] == 1 and not unit[38] & 0x02
    )
    for variant, doc in docs.items():
        letter = variant[7]
        player = doc.section(f"bmap02_mikata_{letter}")
        if player is None:
            continue
        for unit in player.units:
            unit[28:32] = mobile[28:32]
    ctx.write_dispos("bmap02", docs)
    # Forced fog hides the nearest bandit at distance 4 from all four starting units (their
    # classes have vision 3).  Player-side AI respects that visibility and otherwise finds no
    # hostile target, so retain visible fog at the map edges but expose the nearby bandits.
    for pid in ("PID_IKE", "PID_TIAMAT", "PID_OSCAR", "PID_BOLE"):
        ctx.set_class(ctx.character(pid).jid, vision=5)
    ctx.tunes({"phases.player": 2, "phases.enemy": 0})
    ctx.patch("map.fog_on", "camera.free", "camera.smooth")


def build_c7(ctx):
    ctx.patch("battle.show_stats")
    ctx.patch("anim.ally_npc_battles")


def build_c8(ctx):
    ctx.patch("battle.info_window")


def build_c9(ctx):
    """Battle visuals on Chapter 3: Titania gets a Hand Axe; anim speed left at 1x."""
    docs = ctx.dispos("bmap04")
    for doc in docs.values():
        for section in doc.sections:
            for unit in section.units:
                if unit[0] == "PID_TIAMAT":
                    unit[3], unit[4], unit[5] = "IID_HANDAXE", "IID_STEELAXE", "IID_VULNERARY"
    ctx.write_dispos("bmap04", docs)


# -- D: content made with the editors ------------------------------------------------------------------------

def _recoloured_boyd(ctx):
    from PIL import Image
    from fe_modding import portraits
    from fe_modding.formats import tpl

    images = tpl.read_tpl_images(io.BytesIO(portraits.read_texture_set(portraits.face_dir(ctx.project) / "BOLE.cms")))
    body = images[0].convert("RGBA")
    r, g, b, a = body.split()
    return Image.merge("RGBA", (b, g, r, a))          # red and blue swapped: a blue-haired Boyd


def build_d1_text(ctx):
    from fe_modding.formats import message

    path = files_root_of(ctx.project) / "Mess" / "c01.m"
    order = message.read_text_order_path(path)
    entries = message.read_messages_path(path)
    for i, entry in enumerate(entries):
        if entry.speaker == "MS_01_OP_01":
            text = entry.text.replace("Are you all right?", "SESSION TEST: are you all right?", 1)
            if text == entry.text:
                raise ValueError("MS_01_OP_01 text changed; update the fixture")
            entries[i] = message.Message(entry.speaker, text)
    ctx.project.write_keeping_original(path, message.write_messages(entries, order))


def build_d1_portrait(ctx):
    from fe_modding import portraits

    small, _large = portraits.add_portrait(ctx.project, "SESSIONBOYD", "MPID_BOLE", _recoloured_boyd(ctx))
    for pid in ("PID_BOLE", "PID_BOLE_MAP1"):
        ctx.set_character(pid, fid=small)


def build_d1_music(ctx):
    from fe_modding.formats import gcfesnd, stm

    sound = files_root_of(ctx.project) / "Sound"
    audio = stm.read_stm_path(sound / "gcfe_bgm_btl_dknight_32k.stm")
    keep = audio.sample_rate * 30
    audio.channels = [channel[:keep] for channel in audio.channels]
    audio.loop_start = 0
    target = sound / "session_test_32k.stm"
    target.write_bytes(stm.write_stm(audio))
    catalog = sound / "gcfesnd.bin"
    ctx.project.write_keeping_original(catalog, gcfesnd.add_bgm_cue(catalog.read_bytes(), "BGM_SESSION_TEST",
                                                                   "sound/session_test_32k"))
    ctx.replace_script(1, 'BGMPlay(2, "BGM_EVT_IKE1")', 'BGMPlay(2, "BGM_SESSION_TEST")', count=1)


def build_d1_map(ctx):
    from fe_modding import map_props
    from fe_modding.formats import map_file

    path = files_root_of(ctx.project) / "zmap" / "bmap01" / "map.cmp"
    entries, files = map_props.read_map_container(path)
    data = map_file.read_map_bytes(next(v for k, v in files.items() if k.lower().endswith("map.bin")))
    names = [n for n in map_props.prop_names(files, data)]
    if not names:
        raise ValueError("bmap01 has no props to copy")
    ike = next(u for doc in ctx.dispos("bmap01").values() for s in doc.sections for u in s.units
               if u[0] == "PID_IKE")
    for dx in (-1, 0, 1):
        map_props.place_prop(files, names[0], ike[32] + dx, ike[33] + 2)
    map_props.write_map_container(ctx.project, path, entries, files)
    ctx.facts["prop"] = names[0]


def build_d1(ctx):
    build_d1_text(ctx)
    build_d1_portrait(ctx)
    build_d1_music(ctx)
    build_d1_map(ctx)


def build_d2(ctx):
    """Titania's battle model through the glTF exporter and back through the importer."""
    import tempfile
    from fe_modding.gui import model_viewer

    pack = files_root_of(ctx.project) / "zu" / "timt" / "timt_ax.pak"
    if not pack.is_file():
        pack = next((files_root_of(ctx.project) / "zu" / "timt").glob("*.pak"))
    glb = model_viewer.export_set_glb(pack)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "timt.glb"
        path.write_bytes(glb)
        result = model_viewer.replace_battle_body_with_glb(pack, path)
    for out_path, data in result.outputs.items():
        ctx.project.write_keeping_original(out_path, data)
    ctx.facts["model_warnings"] = "; ".join(result.warnings) or "none"


# -- E-H: optional blocks -----------------------------------------------------------------------------------

def build_e1(ctx):
    from fe_modding.formats import soundroom

    path = files_root_of(ctx.project) / "soundroom.bin"
    entries = soundroom.read_soundroom_path(path)
    ctx.facts["pictures"] = len(entries)
    ctx.facts["first_picture"] = entries[-1].name if hasattr(entries[-1], "name") else str(entries[-1])
    ctx.project.write_keeping_original(path, soundroom.build_soundroom(list(reversed(entries))))


def card_g2(ctx):
    save, block = _army_save(ctx)
    ctx.unit(block, "PID_LETHE").transform_gauge = 0
    return {"session_G2.gci": ctx.save_copy(save, ARMY_BLOCK)}


def build_pal_prologue(ctx):
    pass                                      # the automatic victory and the jump are added by the builder


# -- the list ------------------------------------------------------------------------------------------------

SCENARIOS: list[Scenario] = [
    Scenario(
        "A1", "A. Harness and launch paths", "Chapter jump on Hard",
        "dev.jump_chapter boot + the difficulty byte (Play in Dolphin from a chapter page)",
        build=build_a1, boot="chapter", chapter=2, difficulty="Hard", minutes=3,
        steps=[JUMP_NOTE,
               "Skip the opening of Chapter 1 with Start until your first player phase.",
               "Count the enemies on the map, then put the cursor on the boss ({boss_class}) and read his level."],
        checks=["The game went from the warning screen straight into Chapter 1 (no title, no file menu).",
                "The boss is level {boss_h} (Normal would show {boss_n}).",
                "There are {enemies_h} enemies at the start (Normal has {enemies_n}).",
                "Map units walk visibly faster than normal (animation speed 2x)."]),
    Scenario(
        "A2", "A. Harness and launch paths", "Edited save loads as saved",
        "Saves page edits (gold, level, EXP, inventory) re-signed by the app; GCI-folder card override",
        boot="title", card=card_a2, anim_speed=None, minutes=3,
        steps=[TITLE_NOTE,
               "Restart Chapter > the third slot (Ch.12: A Strange Land, Base).",
               "At the base, read the gold, then open Ike's and Titania's status / items."],
        checks=["The file menu shows the save and it loads with no error message.",
                "Gold is 123,456.",
                "Ike is level 7 with 42 EXP.",
                "Titania holds Hand Axe, Steel Axe, Vulnerary (Hand Axe equipped)."]),
    Scenario(
        "A3", "A. Harness and launch paths", "Save moved to another chapter's start",
        "save_file.retarget_to_chapter_start (Saves page, Play in Dolphin, 'start a chapter')",
        boot="title", card=card_a3, anim_speed=None, minutes=3,
        steps=[TITLE_NOTE, "Restart Chapter > the third slot, which now reads \"Ch. 1: The Battle Begins\"."],
        checks=["Loading File 3 starts Chapter 1 (its opening plays), not the Chapter 12 base.",
                "Your units on the map are the saved army (promoted classes, e.g. Ike as a Lord at Lv 20).",
                "Gold (pause menu / Data) is 7,777."]),
    Scenario(
        "A4", "A. Harness and launch paths", "App buttons start Dolphin",
        "The app's own launch code: chapter page and Saves page 'Play in Dolphin…'",
        boot="none", minutes=4,
        app_steps=["In the app (any Path of Radiance US project): Chapters > open Chapter 1 > ▶ Play in Dolphin… > "
                   "Normal > Play. Close Dolphin once the chapter starts.",
                   "Saves > open G:\\ROM\\SaveFile\\chapter12.gci > select the 'File 3 - chapter 13 - base' block (seq 1179) > "
                   "Play in Dolphin… > play it as saved. Close Dolphin once File 3 shows in the file menu."],
        steps=[],
        checks=["The chapter page button boots straight into Chapter 1.",
                "The Saves page button boots with a card that shows the chosen save (and no other file of that slot)."]),

    Scenario(
        "B1", "B. Chapter flow", "Added chapter after the Prologue (story flow)",
        "chapters.add_story_chapter + story-flow patch + the new chapter's title card",
        build=build_b1, boot="chapter", chapter=1, auto_win={1: 1, 33: 1}, minutes=6,
        notes=["A chapter-jump boot has no game file on the card, so the game offers no save between "
               "chapters here; B2 covers saving.", "Build warnings: {warnings}"],
        steps=[JUMP_NOTE,
               "Prologue: on your first player phase press A on an empty tile > End (the map is won once "
               "that enemy phase has played). Start skips the ending scene.",
               "Watch the next chapter's title card, then its first player phase.",
               "End turn 1 there too, skip its ending, and watch which chapter starts. Close Dolphin."],
        checks=["Ending turn 1 wins the Prologue once its enemy phase has played.",
                "The next chapter's title card reads \"" + B_TITLE + "\" (also the title on the Start / Data screen).",
                "That chapter is a copy of Chapter 1 (same map, 10 bandits on Hard) and reaches the player phase.",
                "After it, the game goes on to the real Chapter 1 (\"The Battle Begins\")."]),
    Scenario(
        "B2", "B. Chapter flow", "Added chapter: file menu, save and continue",
        "save check hook for ids > 31, chapter_name_texture_table copy (file-menu slot picture), flow table",
        build=build_b1, boot="title", card=card_b2, auto_win={33: 1}, anim_speed=2.0, minutes=6,
        steps=[TITLE_NOTE,
               "Restart Chapter: look at the third slot (your army save, moved to the new chapter), then load it.",
               "On the first player phase: A on an empty tile > End. Skip the ending scene with Start.",
               "On the Save Data screen pick the third slot and answer Yes (the default is No).",
               "Watch which chapter starts next, then close Dolphin."],
        checks=["The third slot shows the chapter picture \"" + B_TITLE + "\" (not an empty box).",
                "Loading it starts \"" + B_TITLE + "\" with your army.",
                "Ending turn 1 wins it after the enemy phase, the Save Data screen appears and the save works.",
                "The game continues with the real Chapter 1 (\"The Battle Begins\")."]),
    Scenario(
        "B3", "B. Chapter flow", "Added chapter carries on into the next (two-part chapter)",
        "chapters.flow.parts: a playable part list beyond chapter 28",
        build=build_b2, boot="title", card=card_b2, auto_win={33: 1}, anim_speed=2.0, minutes=5,
        steps=[TITLE_NOTE,
               "Restart Chapter > the third slot (\"" + B_TITLE + "\").",
               "On the first player phase: A on an empty tile > End. Skip the ending scene with Start."],
        checks=["There is NO Save Data screen after \"" + B_TITLE + "\" (B2 showed one): Chapter 1 starts right away.",
                "Chapter 1 starts at turn 1 with the same army (nobody re-joined)."],
        notes=["The card's clear history has 10 free entries: with all 40 used the game records no clear, "
               "so a chapter cannot carry on (a known limit; the project check warns about it)."]),
    Scenario(
        "B4", "B. Chapter flow", "Hub and extended flags (separate package)",
        "Hub routing, extended flag banks: already packaged in workspace/extended-flags-playtest",
        boot="none", optional=True, minutes=20,
        app_steps=["Run workspace\\extended-flags-playtest\\Play-GFEE01.cmd and follow its START-HERE.md "
                   "(revision 8 return-tile fix is the open item). Fill its RESULTS.md."],
        steps=[], checks=["START-HERE.md's hub round trip passes (see that package's RESULTS.md)."]),

    Scenario(
        "C1", "C. Game Code rules", "Forecast rules, rings and villages (Chapter 3)",
        "no terrain bonus, triangle values, Charisma/Horror amount+range, class rings on first playthrough, "
        "no village destruction",
        build=build_c1, boot="chapter", chapter=4, minutes=8,
        notes=["Read the ENEMY's Hit in each forecast: your own Hit is often capped at 100 here."],
        steps=[JUMP_NOTE,
               "Skip the opening. Put the cursor on the boss (Bandit leader on the ship, north) and open his items.",
               "Triangle: move Titania next to a SWORD enemy. Open the attack forecast with the Iron Lance, note the "
               "enemy's Hit and Titania's damage; switch to the Iron Axe (same target) and note them again.",
               "Charisma: same enemy, same weapon, once with Ike within 3 tiles of Titania and once 4+ tiles away.",
               "Terrain: same enemy, Titania once on a tree/bush tile and once on plain ground.",
               "Horror: the {horror} closest to your start has Horror. Open Ike's attack forecast while within "
               "3 tiles of that {horror}, then again from 4+ tiles away.",
               "End the turn and watch the bandit placed right next to the south-east village."],
        checks=["The boss carries a Hand Axe AND a Thief's Ring (first playthrough; vanilla: no ring).",
                "With the axe instead of the lance, the enemy's Hit is about 84 higher (vanilla about 24) and "
                "Titania's damage 11 lower (vanilla 1).",
                "With Ike within 3 tiles, the enemy's Hit on Titania is 30 lower (Charisma 30, vanilla 5).",
                "The tree/bush tile does not lower the enemy's Hit (no terrain Avoid bonus).",
                "Within 3 tiles of the {horror}, Ike's Hit is 30 lower (Horror -30, vanilla -5).",
                "The bandit next to the village does not destroy it (the village can still be visited)."]),
    Scenario(
        "C2", "C. Game Code rules", "Base: forging and gold cap",
        "economy.unlimited_forging, forge Hit/Crit per step, gold cap; FWEP reader on a save made after forging",
        build=build_c4, boot="title", card=card_c4, after=after_c4, anim_speed=None, minutes=6,
        steps=[TITLE_NOTE,
               "Restart Chapter > the third slot (Ch.12: A Strange Land, Base). Gold shows 60,000.",
               "Forge: forge one weapon, buying Hit and Crit steps; note the per-step increases on the forge screen.",
               "Forge a second weapon in the same base visit.",
               "Shop: sell any item. Read the gold.",
               "Save at the base to File 3, then close Dolphin (the runner reads the saved forges)."],
        checks=["Each Hit step adds 7 and each Crit step adds 4 (vanilla 5 / 3).",
                "The second forge is allowed in the same chapter.",
                "After selling, gold is 50,000 at most (the cap), not 60,000 + price.",
                "The save works; the runner's summary lists the forged weapons."]),
    Scenario(
        "C3", "C. Game Code rules", "Promotions, steal, supports, laguz, level-ups, fixed seed (Chapter 1)",
        "event_classes, anima choice, three tiers + Master Crown, steal from faster, support range/double/"
        "points per chapter, laguz gain, forced random growth x3, fixed RNG seed",
        build=build_c3, boot="title", card=card_c3, after=after_c3, auto_win={C3_CHAPTER: 2}, boots=2, minutes=14,
        notes=["The army save is moved to Chapter 1 (weak bandits); Sothe, Soren and Lethe get extra "
               "starting slots next to the usual four. Ike and Lethe are reset to their default class, level and stats; "
               "Lethe starts in human form with an empty gauge."],
        steps=[TITLE_NOTE,
               "Restart Chapter > the third slot (now \"Ch. 1: The Battle Begins\"). Skip the opening.",
               "Turn 1, before anything else: Sothe attacks the nearest bandit he can reach. Note the exact result "
               "(hit/miss, damage) and the level-up gains (he is at 90 EXP).",
               "Sothe: Steal the Vulnerary from the fast Fighter closest to your start (check its Speed is higher).",
               "Sothe: use the Master Seal (Items).",
               "Soren: use the Master Seal; in the weapon choice choose Fire.",
               "Boyd (Warrior Lv 12): use the Master Crown.",
               "Open Ike's forecast with Titania 4-6 tiles away (support range 6).",
               "Look at Lethe's gauge, then end the turn (A on an empty tile > End). On turn 2 look at it again. "
               "End turn 2: the map is won after that enemy phase; save to the third slot (Yes). Let Chapter 2 "
               "start, then on its first turn: map menu > Suspend > Yes, and close Dolphin.",
               "Second boot (the runner starts it again): load the same slot (it is back at the chapter start) "
               "and repeat step 2 exactly; compare."],
        checks=["Sothe's level-up gains are all 0 or 3 (forced random growth, 3 per success).",
                "Steal is offered against the faster Fighter (vanilla: only slower units).",
                "The Master Seal promotes Sothe to Assassin (vanilla refuses: Thief has SID_EVENTCC).",
                "Soren promotes to Wind Sage (generic Sage model: the Wind classes have no Soren model), the picker "
                "offers Fire/Thunder, and afterwards Fire shows rank E, Thunder none and Wind C (the Sage default).",
                "The Master Crown turns Boyd into a Berserker (third tier), with no emulator error.",
                "Ike gets a support bonus with Titania up to 6 tiles away, twice the usual amount.",
                "Lethe's gauge number (next to her HP when the cursor is on her) goes up by 4 from turn 1 to turn 2 "
                "(gain 4 per turn, vanilla 2; she starts the map at 0).",
                "The automatic victory at turn 2 works and the save succeeds (the save prompt defaults to No: choose Yes).",
                "The runner's automatic check (the suspend on Chapter 2) shows Boyd and Titania at 3 support points with "
                "each other (vanilla 1).",
                "Second boot: Sothe's first attack and level-up are identical (fixed seed 1234)."]),
    Scenario(
        "C4", "C. Game Code rules", "Enemy phase played by you",
        "phases.enemy = Player (army phase controller)",
        build=build_c5, boot="chapter", chapter=2, minutes=4,
        steps=[JUMP_NOTE, "Skip the opening, End your first turn.",
               "In the enemy phase: select an enemy, move it, attack one of your units, then End."],
        checks=["Enemy units can be selected and ordered during the enemy phase; the AI does not move them.",
                "End turn works and your next player phase starts normally."]),
    Scenario(
        "C5", "C. Game Code rules", "Player phase run by the computer, enemy phase skipped",
        "phases.player = Computer, phases.enemy = No phase; fog on every map; free + smooth camera",
        build=build_c6, boot="chapter", chapter=2, minutes=3,
        notes=["The four starting classes have vision 5 for this fixture, so the player-side AI can see nearby "
               "bandits while fog remains visible around the rest of the map."],
        steps=[JUMP_NOTE, "Skip the opening and watch two turns; only use the C-stick.",
               "Hold the C-stick left or right while the units move."],
        checks=["Your units move and act on their own (note what they do).",
                "There is no enemy phase between turns.",
                "Fog of war is on (vanilla Chapter 1 has none).",
                "The camera turns 1 degree at a time while the C-stick is held, all the way round."]),
    Scenario(
        "C6", "C. Game Code rules", "Battle-screen numbers (retest)",
        "battle.show_stats (the trailing '#C' fix) and anim.ally_npc_battles",
        build=build_c7, boot="chapter", chapter=4, anim_speed=None, minutes=5,
        steps=[JUMP_NOTE, "Fight four or five battles with different units (include a counter-less archer hit).",
               "End the turn and watch at least one enemy attacking you (an enemy-phase battle)."],
        checks=["Each fighter's Dmg / Hit / Crit prints under its own HP window, on both sides, and matches the map forecast.",
                "In the enemy-phase battle the numbers are still under the right fighters.",
                "Nothing garbled after 'Crit'; no freeze over five battles.",
                "A fighter that cannot counter shows dashes."]),
    Scenario(
        "C7", "C. Game Code rules", "FE7Dragon battle info window",
        "battle.info_window (Gecko port in MetroTRK space + battle.dbx / number.tpl / 3sukumi.tpl edits)",
        build=build_c8, boot="chapter", chapter=4, anim_speed=None, minutes=5,
        steps=[JUMP_NOTE, "Fight with battle animations on, then turn animations off (Options) and fight again."],
        checks=["A parchment box at the bottom middle shows both fighters' Hit, Dmg and Crit in animated battles.",
                "The same box shows in map (no-animation) battles.",
                "Digits and the triangle icons are drawn correctly (no garbage textures)."]),

    Scenario(
        "D1", "D. Content made with the editors", "Prologue content pack",
        "dialogue text edit, New portrait (FID_SESSIONBOYD), new music track + BGM cue, map props copy",
        build=build_d1, boot="chapter", chapter=1, auto_win={1: 1}, minutes=5,
        steps=[JUMP_NOTE, "Watch the Prologue opening (do not skip it).",
               "On the map, look below Ike's starting tile.", "End turn 1 (the map is won once the enemy phase has played)."],
        checks=["Mist's first line reads \"SESSION TEST: are you all right?\".",
                "Boyd's portrait is the recoloured (blue-haired) one, in dialogue and on his map status "
                "(a still picture: the fixture gives it no eye or mouth parts).",
                "The music of the opening conversation is the Black Knight battle theme (30 s, loops cleanly).",
                "Three extra copies of the prop '{prop}' stand in a row near Ike's start.",
                "Nothing crashes when the chapter ends."],
        notes=["If D1 crashes, run D1a-D1d (one change each) to find the culprit."]),
    Scenario("D1a", "D. Content made with the editors", "D1 part: dialogue text only", "message.write_messages",
             build=build_d1_text, boot="chapter", chapter=1, optional=True, minutes=2,
             steps=[JUMP_NOTE], checks=["Mist's first line reads \"SESSION TEST: are you all right?\"."]),
    Scenario("D1b", "D. Content made with the editors", "D1 part: portrait only", "portraits.add_portrait",
             build=build_d1_portrait, boot="chapter", chapter=1, optional=True, minutes=2,
             steps=[JUMP_NOTE], checks=["Boyd shows the recoloured portrait."]),
    Scenario("D1c", "D. Content made with the editors", "D1 part: music only", "stm.write_stm + add_bgm_cue",
             build=build_d1_music, boot="chapter", chapter=1, optional=True, minutes=2,
             steps=[JUMP_NOTE], checks=["The opening plays the new cue."]),
    Scenario("D1d", "D. Content made with the editors", "D1 part: map props only", "map_props.place_prop",
             build=build_d1_map, boot="chapter", chapter=1, optional=True, minutes=2,
             steps=[JUMP_NOTE], checks=["The extra props show near Ike's start."]),
    Scenario(
        "D2", "D. Content made with the editors", "Battle model round trip (Titania)",
        "export_set_glb -> replace_battle_body_with_glb with the multi-matrix-first importer",
        build=build_d2, boot="chapter", chapter=4, anim_speed=None, minutes=4,
        steps=[JUMP_NOTE, "Fight with Titania twice (attack and get attacked), animations on."],
        checks=["Titania's battle model looks like vanilla: no part floating, stretched or misplaced.",
                "Her axe stays in her hand through the whole attack."],
        notes=["Import warnings: {model_warnings}"]),
    Scenario(
        "D3", "D. Content made with the editors", "Battle window vs Dolphin (Titania, hand axe)",
        "battle simulator render: hit particles, hand-axe arc/spin, knock-back, dodge step",
        build=build_c9, boot="chapter", chapter=4, anim_speed=None, minutes=8,
        steps=[JUMP_NOTE,
               "Titania throws her Hand Axe at an enemy 2 tiles away, then attacks an adjacent enemy with the "
               "Steel Axe. Watch: hit sparks, the hand axe's height arc and spin, the target's knock-back and any "
               "dodge step. Repeat until you have seen a hit and a miss.",
               "In the app: Assets > Battle Simulator, Titania (Steel Axe / Hand Axe) vs a Bandit, Render fight."],
        checks=["Hit particles in the app look like the game (colour, size, where they appear).",
                "The hand axe's arc height and spin match.",
                "Knock-back and dodge distances match."]),
    Scenario(
        "E1", "E. Other editors", "Sound Room picture list",
        "soundroom.bin writer (Assets > Sound Room): pictures reversed",
        build=build_e1, boot="title", card=card_a2, anim_speed=None, optional=True, minutes=3,
        steps=[TITLE_NOTE, "Title screen > Extras > Sound Room. Play two tracks (A) and watch the pictures."],
        checks=["The first picture is the one that is normally last ({first_picture}), then they go backwards.",
                "Playing tracks and paging pictures works without a freeze."]),
    Scenario(
        "E2", "E. Other editors", "PAL: make a save (part 1)",
        "PAL extraction on GFEP01 + New Game; produces the PAL .gci for part 2",
        build=build_pal_prologue, boot="title", region="GFEP01", auto_win={1: 1},
        optional=True, minutes=5,
        notes=["A normal boot: a chapter jump has no game file, so the game would never offer a save."],
        steps=["Dolphin starts the European game normally; press A on the warning screen, choose English "
               "if asked, Start through the intro and the title screen.",
               "New Game on Hard (no tutorials); let it create the game file in File 1.",
               "Prologue: skip the opening with Start, then End on turn 1 (won once the enemy phase has played).",
               "Save to File 1 when asked. Close Dolphin."],
        checks=["The European build starts a new game and the Prologue is won automatically.",
                "The save to File 1 works."]),
    Scenario(
        "E3", "E. Other editors", "PAL: edited save in the app and in game (part 2)",
        "Saves page on a real PAL .gci (FE8X blocks, accented text), edit, reload in the PAL game",
        boot="title", region="GFEP01", card_from="E2", anim_speed=None, optional=True, minutes=5,
        app_steps=["In the app: Saves > open the .gci in G:\\ROM\\tellius_test\\session_run\\E2\\card_a. "
                   "Check that the blocks list and the chapter/title texts read correctly.",
                   "Set File 1's gold to 4,321 and save the file in the app (it stays in that folder; this "
                   "test starts from a copy of it)."],
        steps=[TITLE_NOTE, "Restart Chapter > the first slot."],
        checks=["The Saves page opens the PAL card and shows sensible block labels (no garbled text).",
                "The edited File 1 loads in the PAL game with 4,321 gold."]),
    Scenario(
        "G1", "G. Live watchpoints (Dolphin debugger)", "Unread FE8Data fields",
        "LIVE_DEBUG_CHECKLIST 'Unread data fields': class +0x04/+0x3F/+0x43, person +0x08, skill +0x1B/+0x1D",
        boot="title", card=card_a2, anim_speed=None, gdb=True, watch="fields", optional=True, minutes=10,
        notes=["Emulation is about 5x slower while the debugger is attached."],
        steps=[TITLE_NOTE + " A second console runs research/live_watch.py fields.",
               "Restart Chapter > third slot (Ch.12, Base). When at the base, press Enter in the live_watch console.",
               "Open: a unit's status screen, the unit list, the skill screen, then start the battle and open "
               "a battle forecast. Type q in the live_watch console when done."],
        checks=["live_watch logged hits (or clearly none) for each watched field: send the summary file."]),
    Scenario(
        "G2", "G. Live watchpoints (Dolphin debugger)", "Laguz gauge at turn change",
        "LIVE_DEBUG_CHECKLIST: turn-change laguz step with an ordinary laguz (Lethe, gauge 0)",
        boot="title", card=card_g2, anim_speed=None, gdb=True, watch="turns", optional=True, minutes=10,
        notes=["Emulation is about 5x slower while the debugger is attached."],
        steps=[TITLE_NOTE + " A second console runs research/live_watch.py turns.",
               "Restart Chapter > third slot (Ch.12, Base), deploy Lethe, start the battle; press Enter in the live_watch console.",
               "End two turns. Type q in the live_watch console."],
        checks=["live_watch logged the gauge writes at each turn change: send the summary file."]),
    Scenario(
        "H1", "H. Radiant Dawn", "Rebuilt Radiant Dawn disc boots",
        "RD phase 0: wit rebuild of an unmodified extraction (the one-file edit image passed on 2026-10-08)",
        boot="image", image=r"G:\ROM\rd_work\rebuild\RFEE01.wbfs", anim_speed=None, optional=True, minutes=3,
        steps=["Dolphin boots the rebuilt Radiant Dawn disc. Play until the first map starts, then close Dolphin."],
        checks=["The unmodified rebuild boots and reaches the first map."]),
    Scenario(
        "F1", "F. Release tools", "Create a patch and apply it with the patcher",
        "Disc & Patch > Create patch… and Apply patch… (Tellius Patcher), end to end on a real disc",
        boot="none", optional=True, minutes=10,
        app_steps=["In a project with at least one edit: Disc & Patch > Create patch… and save the patch.",
                   "Disc & Patch > Apply patch… (or TelliusPatcher.exe): choose that patch and your retail USA disc, "
                   "Build patched disc.",
                   "Boot the patched disc in Dolphin and check the edit. Delete the patched image afterwards."],
        steps=[], checks=["The patch is created, applied to the retail disc, and the result boots with the edit."]),
]


#: Pending in-game questions this session leaves out, and why (shown at the end of START-HERE.md).
NOT_COVERED = [
    ("Reinforcement skill limit / unlimited", "needs Tanith's SID_REINFORCEMENTS in a chapter with a reinforcement set; "
     "no save in G:\\ROM\\SaveFile has that set-up"),
    ("Sound Room track list (the 64-entry BGM_ table in main.dol)", "no editor writes it yet; E1 covers the picture list"),
    ("Edited AI scripts (cp_data.bin readable language)", "needs a hand-written AI change with a visible effect; "
     "easy to add as a D-test once one is chosen"),
    ("TrueType font import, tutorial list, staff credits", "credits need a full ending; fonts and tutorials have no "
     "quick visible check yet"),
    ("EXP/growth tunables other than forced random x3 (Elite, Frac90, cap, fixed thresholds), laguz drain/max",
     "same code paths as the tested entries; add them to C3 if a regression shows up"),
    ("'M落石' Push command, support conversations at thresholds, Charisma on Gashilama's own map",
     "need long chapters; the rules themselves are covered by C1/C3"),
    ("Japanese project (names and chapter titles in Japanese)", "app-only check: open a GFEJ01 project and read the "
     "Chapters and Characters pages"),
    ("Simulator vs game for a whole chapter (campaign plan B9)", "D3 compares one fight; a full chapter is a session of "
     "its own"),
]


def by_id() -> dict[str, Scenario]:
    return {s.id: s for s in SCENARIOS}
