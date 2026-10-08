import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.battle_sim import (
    Combatant, Fe9Rng, Fe9Rules, FixedOutcomes, RngOutcomes, from_character, from_class, simulate,
)
from fe_modding.battle_sim import camera, scene_assets as sa, timeline
from fe_modding.battle_sim.timeline import Clip
from fe_modding.battle_sim import units
from fe_modding.battle_sim.units import Weapon, weapon_from_item
from fe_modding.formats import fe8data

SWORD = Weapon("IID_IRONSWORD", "sword", "sword", might=5, hit=100, crit=0, weight=5)
LANCE = Weapon("IID_IRONLANCE", "lance", "lance", might=7, hit=80, crit=0, weight=8)
AXE = Weapon("IID_IRONAXE", "axe", "axe", might=8, hit=75, crit=0, weight=10)
BOW = Weapon("IID_IRONBOW", "bow", "bow", might=6, hit=85, weight=5, min_range=2, max_range=2,
             effective=frozenset({"fly"}))
FIRE = Weapon("IID_FIRE", "flame", "flame", might=5, hit=90, weight=4, min_range=1, max_range=2)


def unit(name="A", stats=(30, 10, 5, 10, 10, 5, 5, 3), weapon=SWORD, build=8, **kw):
    return Combatant(name=name, stats=list(stats), build=build, weapon=weapon, **kw)


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.rules = Fe9Rules()

    def test_basic_numbers(self):
        a, d = unit("A"), unit("D", weapon=SWORD)
        f = self.rules.forecast(a, d).attacker
        self.assertEqual(f.atk, 15)
        self.assertEqual(f.defense, 5)
        self.assertEqual(f.damage, 10)
        self.assertEqual(f.raw_hit, 100 + 20 + 2)
        self.assertEqual(f.avoid, 10 * 2 + 5)
        self.assertEqual(f.hit, 97)
        self.assertEqual(f.crit, 5 - 5)

    def test_weight_lowers_attack_speed(self):
        light = unit(build=3, weapon=AXE)
        self.assertEqual(self.rules.attack_speed(light), 10 - (10 - 3))
        self.assertEqual(self.rules.attack_speed(unit(build=12, weapon=AXE)), 10)

    def test_double_threshold(self):
        fast = unit("F", stats=(30, 10, 0, 10, 14, 5, 5, 3))
        slow = unit("S")
        self.assertTrue(self.rules.side(fast, slow).doubles)
        fast.stats[4] = 13
        self.assertFalse(self.rules.side(fast, slow).doubles)

    def test_triangle(self):
        s = self.rules.forecast(unit(weapon=SWORD), unit(weapon=AXE))
        self.assertEqual((s.attacker.triangle, s.defender.triangle), (1, -1))
        plain = self.rules.side(unit(weapon=SWORD), unit(weapon=SWORD))
        self.assertEqual(s.attacker.atk, plain.atk + 1)
        self.assertEqual(s.attacker.raw_hit, plain.raw_hit + 10)

    def test_effective_doubles_might(self):
        flier = unit("P", categories=frozenset({"fly"}))
        f = self.rules.side(unit(weapon=BOW), flier, distance=2)
        self.assertTrue(f.effective)
        self.assertEqual(f.atk, 10 + 12)
        guard = Weapon("IID_FULLGUARD", properties=frozenset({"sfxseal"}))
        flier.weapon = guard
        self.assertFalse(self.rules.side(unit(weapon=BOW), flier, distance=2).effective)

    def test_magic_uses_mag_and_res(self):
        mage = unit("M", stats=(20, 0, 9, 8, 8, 4, 2, 6), weapon=FIRE)
        f = self.rules.side(mage, unit())
        self.assertTrue(f.magic)
        self.assertEqual((f.atk, f.defense), (14, 3))

    def test_range(self):
        archer = unit(weapon=BOW)
        self.assertFalse(self.rules.can_attack(archer, 1))
        self.assertTrue(self.rules.can_attack(archer, 2))
        log = simulate(unit(weapon=BOW), unit(), distance=2)
        self.assertTrue(all(s.side == 0 for s in log.strikes))

    def test_crit_flags_and_wrath(self):
        killer = Weapon("IID_KILLER", "sword", "sword", might=9, hit=75, crit=30, weight=7)
        a, d = unit(weapon=killer), unit()
        self.assertEqual(self.rules.side(a, d).crit, 30 + 5 - 5)
        a.weapon = Weapon(**{**killer.__dict__, "properties": frozenset({"crit0"})})
        self.assertEqual(self.rules.side(a, d).crit, 0)
        a.weapon = killer
        d.weapon = Weapon("IID_RAGNELL", "sword", "sword", might=18, properties=frozenset({"sealcrit"}))
        self.assertEqual(self.rules.side(a, d).crit, 0)
        d.weapon = SWORD
        rules = Fe9Rules()
        rules._keys["SID_WRATH_TEST"] = "wrath"
        a.skills, a.hp = ["SID_WRATH_TEST"], 15
        self.assertEqual(rules.side(a, d).crit, 30 + 5 + 50 - 5)

    def test_blessed_armor(self):
        f = self.rules.side(unit(), unit(blessed_armor=True))
        self.assertEqual(f.atk, 0)
        weak = Weapon(**{**SWORD.__dict__, "properties": frozenset({"weakA"})})
        self.assertEqual(self.rules.side(unit(weapon=weak), unit(blessed_armor=True)).atk, 15)

    def test_skill_table_matching(self):
        table = [fe8data.SkillEntry(0x2F, 0, "SID_X", None, None, None, None, [], ()),
                 fe8data.SkillEntry(3, 0, "SID_Y", None, None, "Mess_Help_skill_Wrath", None, [], ())]
        rules = Fe9Rules(table)
        self.assertEqual(rules.skill_key("SID_X"), "sol")
        self.assertEqual(rules.skill_key("SID_Y"), "wrath")
        self.assertEqual(rules.skill_key("SID_COUNTER"), "counter")


class FightTests(unittest.TestCase):
    def test_default_fixed_round(self):
        log = simulate(unit("A"), unit("D"))
        self.assertEqual([s.side for s in log.strikes], [0, 1])
        self.assertEqual(log.hp_end, (20, 20))

    def test_follow_up_and_brave(self):
        brave = Weapon(**{**SWORD.__dict__, "properties": frozenset({"twice"})})
        fast = unit("A", stats=(30, 10, 0, 10, 15, 5, 5, 3), weapon=brave)
        log = simulate(fast, unit("D", stats=(80, 1, 0, 1, 1, 0, 5, 0)))
        self.assertEqual([s.side for s in log.strikes], [0, 0, 1, 0, 0])
        self.assertEqual([s.label for s in log.strikes], ["", "brave", "", "follow-up", "brave"])

    def test_fixed_miss_and_crit(self):
        log = simulate(unit("A"), unit("D"), outcomes=FixedOutcomes({(1, "hit"): False, (2, "crit"): True}))
        self.assertFalse(log.strikes[0].hit)
        self.assertTrue(log.strikes[1].crit)
        self.assertEqual(log.hp_end, (0, 30))
        self.assertTrue(log.strikes[1].kill)
        self.assertEqual(log.dead, 0)

    def test_kill_stops_the_fight(self):
        log = simulate(unit("A"), unit("D", hp=5))
        self.assertEqual(len(log.strikes), 1)
        self.assertEqual(log.hp_end[1], 0)

    def test_sol_luna(self):
        a = unit("A", skills=["SID_SUNTRICK", "SID_MOONTRICK"], hp=10)
        d = unit("D", stats=(40, 1, 0, 1, 1, 0, 10, 0))
        log = simulate(a, d, outcomes=FixedOutcomes({(1, "proc:luna"): True, (1, "proc:sol"): True}))
        s = log.strikes[0]
        self.assertEqual(set(s.procs), {"luna", "sol"})
        self.assertEqual(s.damage, 15 - 5)
        self.assertEqual(s.heal, 10)

    def test_pray_and_wing_guard(self):
        d = unit("D", hp=5, skills=["SID_PRAY", "SID_WINGSHIELD"])
        log = simulate(unit(), d, outcomes=FixedOutcomes({(1, "proc:pray"): True}))
        self.assertEqual(log.strikes[0].hp_after[1], 1)
        log = simulate(unit(), d, outcomes=FixedOutcomes({(1, "proc:wing_guard"): True}))
        self.assertEqual(log.strikes[0].damage, 0)

    def test_cancel_and_vantage(self):
        log = simulate(unit(skills=["SID_DEFENCE"]), unit("D"), outcomes=FixedOutcomes({(2, "proc:cancel"): True}))
        self.assertEqual([s.side for s in log.strikes], [0])
        log = simulate(unit(), unit("D", skills=["SID_AMBUSH"]))
        self.assertEqual([s.side for s in log.strikes], [1, 0])

    def test_counter_and_astra(self):
        log = simulate(unit(), unit("D", skills=["SID_COUNTER"]), outcomes=FixedOutcomes({(1, "proc:counter"): True}))
        self.assertEqual([(s.side, s.label) for s in log.strikes], [(0, ""), (1, "Counter"), (1, "")])
        a = unit(skills=["SID_STARTRICK"])
        log = simulate(a, unit("D", stats=(99, 1, 0, 1, 1, 0, 5, 0)),
                       outcomes=FixedOutcomes({(1, "proc:astra"): True}))
        astra = [s for s in log.strikes if s.label == "Astra"]
        self.assertEqual(len(astra), 5)
        self.assertEqual(astra[0].damage, 5)

    def test_rng_is_seeded(self):
        a, d = unit(), unit("D", skills=["SID_COUNTER"])
        one = simulate(a, d, outcomes=RngOutcomes(1234))
        two = simulate(a, d, outcomes=RngOutcomes(1234))
        self.assertEqual(one.text(), two.text())
        self.assertEqual([x.roll for x in one.decisions], [x.roll for x in two.decisions])
        self.assertEqual(a.hp, 30)  # inputs untouched

    def test_rng_distribution(self):
        rng = Fe9Rng(7)
        rolls = [rng.rn() for _ in range(20000)]
        self.assertTrue(all(0 <= r < 100 for r in rolls))
        self.assertAlmostEqual(sum(rolls) / len(rolls), 49.5, delta=1.5)
        hits = sum(rng.roll_true_hit(80)[0] for _ in range(20000)) / 20000
        self.assertGreater(hits, 0.85)  # true hit makes 80 displayed land more often


class DataTests(unittest.TestCase):
    def test_builders(self):
        cls = fe8data.ClassEntry(0, 0, "JID_X", None, None, None, "AID_X", 6, [40] * 8, [18, 5, 1, 6, 7, 9, 5, 1],
                                 [0] * 8, 0, "C--------", ["SID_CRITRISE", None], b"", build=9,
                                 categories=["armor", None])
        char = fe8data.CharacterEntry(0, 0, "PID_Y", None, "JID_X", ["SID_COUNTER", None, None], None, None, 3, 2,
                                      0, [1, 2, 0, 0, 0, 4, 0, 0], [0] * 8, [0] * 8)
        data = fe8data.Fe8Data([char], [cls], [], [])
        u = from_character(data, "PID_Y")
        self.assertEqual(u.stats, [19, 7, 1, 6, 7, 4, 5, 1])
        self.assertEqual(u.build, 11)
        self.assertEqual(u.skills, ["SID_COUNTER", "SID_CRITRISE"])
        self.assertEqual(u.categories, frozenset({"armor"}))
        self.assertEqual(u.aid, "AID_X")
        g = from_class(data, "JID_X")
        self.assertEqual(g.stats[5], 0)
        char.stat_bonus[1] = -3  # personal bonuses are signed: Str 5 - 3
        self.assertEqual(from_character(data, "PID_Y").stats[1], 2)

    def test_levels_and_promotion(self):
        def job(jid, link, base, caps, hp_cap):
            return fe8data.ClassEntry(0, 0, jid, None, None, link, "AID_" + jid, 6, [hp_cap] + caps, base,
                                      [0] * 8, 0, "C--------", [None], b"", build=5, categories=[None],
                                      growth_modifiers=[0, 10, 0, 0, 0, 0, 0, 0])
        low = job("JID_LOW", "JID_HIGH", [10, 2, 0, 2, 2, 0, 2, 0], [8] * 7, 40)
        high = job("JID_HIGH", "JID_LOW", [15, 5, 0, 4, 4, 0, 4, 0], [30] * 7, 60)
        char = fe8data.CharacterEntry(0, 0, "PID_Y", None, "JID_LOW", [None] * 3, None, None, 1, 2, 0,
                                      [0] * 8, [50, 40, 0, 100, 0, 30, 0, 0], [50, 0, 0, 0, 0, 0, 0, 0])
        data = fe8data.Fe8Data([char], [low, high], [], [])
        self.assertIs(units.promotion_of(data, low), high)
        self.assertIsNone(units.promotion_of(data, high))
        self.assertEqual(from_character(data, "PID_Y").stats, [10, 2, 0, 2, 2, 0, 2, 0])
        u = from_character(data, "PID_Y", level=5)  # 4 fixed-growth level-ups
        # HP counter 50 + 4 x 50 pays 2; Str 50% (40 + class 10) pays 2; Skl 100% pays 4, capped at 8
        self.assertEqual(u.level, 5)
        self.assertEqual(u.stats[:6], [12, 4, 0, 6, 2, 1])
        u = from_character(data, "PID_Y", level=20)
        self.assertEqual(u.stats[3], 8)  # class cap
        p = from_character(data, "PID_Y", jid="JID_HIGH", level=1, promoted_at=20)
        # promotion keeps the gains and swaps the class bases and caps: Skl gains 6 + base 4
        self.assertEqual(p.jid, "JID_HIGH")
        self.assertEqual(p.stats[3], 10)
        self.assertGreater(from_character(data, "PID_Y", jid="JID_HIGH", level=10, promoted_at=20).stats[3], 10)
        self.assertEqual(from_class(data, "JID_HIGH", level=1, promoted_from="JID_LOW").stats[0], 15)
        item = fe8data.ItemEntry(0, 0, "IID_Z", None, None, "sword", "rod", "E", ["magsw", None], ["fly", None],
                                 None, None, 0, 30, 7, 80, 9, 0, 1, 2, 0, 1, [0] * 10, [0] * 8, 0, b"")
        w = weapon_from_item(item)
        self.assertTrue(w.magic)
        self.assertEqual(w.effective, frozenset({"fly"}))


class TimelineTests(unittest.TestCase):
    CLIPS = {
        sa.IDLE: Clip("idle", 40), sa.ATTACK1: Clip("at1", 50, impact=30, swing=20),
        sa.CRIT1: Clip("cr1", 70, impact=45), sa.DAMAGE: Clip("dam", 20), sa.DODGE: Clip("dog", 16),
        sa.DEATH: Clip("ded", 60, swing=5), sa.RUN: Clip("run", 34),
    }

    def lookup(self, side, role):
        return self.CLIPS.get(role)

    def test_strike_sequence(self):
        log = simulate(unit("A"), unit("D"))
        tl = timeline.build(log, self.lookup)
        # opening: WaitInit 120 + the state machine's ticks, then a 34-tick run
        self.assertEqual(tl.moves[0].start, 125)
        self.assertEqual(tl.moves[0].end, 159)
        self.assertAlmostEqual(tl.x(0, 200), -20 + 0.6 * 34)  # the default 移動速度
        self.assertEqual(tl.pose(0, 140)[0], "run")
        first = tl.changes[0]
        self.assertEqual(first.frame, 163 + 30)  # WaitAtk0, then the clip's event 0
        self.assertEqual(tl.pose(0, first.frame - 1), ("at1", 29))
        self.assertEqual(tl.pose(1, first.frame - 1)[0], "idle")
        self.assertEqual(tl.pose(1, first.frame + 2), ("dam", 2))
        self.assertEqual(tl.hp(first.frame - 1), (30, 30))
        self.assertEqual(tl.hp(first.frame), (30, 20))
        self.assertEqual(len(tl.changes), 2)
        # the counter waits WaitAtk2 and runs only to its range from the target
        self.assertAlmostEqual(tl.moves[1].x1, 20 - (20 - tl.x(0, 200) - 10))
        self.assertEqual([(c.script, c.slot, c.mirror) for c in tl.camera],
                         [("standby", 0, False), ("atk_l", 0, False), ("atk_l", 1, True)])
        self.assertEqual(tl.camera[1].frame, 163)
        self.assertEqual(tl.camera[0].dest, (0.0, timeline.OPENING_HEIGHT, 0.0))
        self.assertEqual([q.strength for q in tl.quakes], [0.5, 0.5])
        self.assertEqual(tl.pose(0, tl.length - 1)[0], "idle")
        self.assertEqual(tl.pose(0, tl.length)[0], "idle")  # the last frame keeps the clip, never the bind pose
        self.assertEqual(tl.pose(1, tl.length + 30)[0], tl.pose(1, tl.length - 1)[0])

    def test_crit_miss_and_death(self):
        log = simulate(unit("A"), unit("D"), outcomes=FixedOutcomes({(1, "hit"): False, (2, "crit"): True}))
        tl = timeline.build(log, self.lookup)
        self.assertEqual(tl.changes[0].text, "Miss")
        self.assertEqual(tl.changes[0].frame, tl.camera[1].frame + 20)  # dodged on event 1
        self.assertEqual(tl.pose(1, tl.changes[0].frame + 1)[0], "dog")
        self.assertEqual(tl.changes[1].text, "Crit 30")
        self.assertEqual(tl.pose(0, tl.length - 1), ("ded", 60))  # held
        self.assertEqual(tl.popup(tl.changes[1].frame + 3).text, "Crit 30")
        scripts = [c.script for c in tl.camera]
        self.assertEqual(scripts[-2:], ["crit2_l", "ded_l"])  # a killing crit, then the death shot
        self.assertEqual(tl.quakes[-1].strength, 1.8)

    def test_variant_and_fallback_roles(self):
        clips = dict(self.CLIPS)
        clips["必殺1_攻撃1"] = Clip("cr1_at1", 66, impact=40)
        log = simulate(unit("A", stats=(30, 10, 5, 10, 16, 5, 5, 3)),
                       unit("D", stats=(60, 10, 5, 10, 10, 5, 5, 3), weapon=None),
                       outcomes=FixedOutcomes({(2, "crit"): True}))
        from fe_modding.battle_sim.staging import UnitParams
        # fast enough to reach its range in one run, so the follow-up needs no second run
        tl = timeline.build(log, lambda side, role: clips.get(role), units=[UnitParams(move_speed=1.0), UnitParams()])
        crit = next(seg for seg in tl.segments if seg.role == sa.CRIT1)
        self.assertEqual(crit.clip.stem, "cr1_at1")  # the attacker's previous role was 攻撃1

    def test_jump_attack_skips_the_run(self):
        from fe_modding.battle_sim.staging import UnitParams
        log = simulate(unit("A"), unit("D", weapon=None))
        tl = timeline.build(log, self.lookup, units=[UnitParams(jump_attack=True), UnitParams()])
        self.assertEqual(tl.moves, [])

    def test_missing_clips(self):
        tl = timeline.build(simulate(unit("A"), unit("D")), lambda side, role: None)
        self.assertEqual(tl.pose(0, 30), (None, 0.0))
        self.assertEqual(len(tl.changes), 2)

    def test_attack_role(self):
        roles = {sa.ATTACK1: 1, sa.ATTACK2: 1, sa.CRIT1: 1, sa.SHOT: 1, sa.SPELL: 1}
        self.assertEqual(sa.attack_role(roles, crit=True, second=False, weapon_type="sword", magic=False,
                                        ranged=False), sa.CRIT1)
        self.assertEqual(sa.attack_role(roles, crit=False, second=True, weapon_type="sword", magic=False,
                                        ranged=False), sa.ATTACK2)


class SceneAssetTests(unittest.TestCase):
    def test_unit_assets(self):
        import tempfile

        from fe_modding.formats import zdbx
        with tempfile.TemporaryDirectory() as tmp:
            files = Path(tmp)
            folder = files / "zu" / "fig1"
            folder.mkdir(parents=True)
            for name in ("fig1_ax.pak", "fig1_sw.pak", "fig1.tpl", "fig1_b.tpl"):
                (folder / name).write_bytes(b"x")
            (files / "xwp" / "ironsword").mkdir(parents=True)
            (files / "xwp" / "ironsword" / "ironsword.cmp").write_bytes(b"x")
            enc = lambda text: text.encode("shift_jis")
            archive = zdbx.build_zdbx_archive([
                (zdbx.JOB_LIST, enc("JID_HERO fig1\r\n")),
                ("zu/fig1.dbx", enc("{\r\n\tsw_攻撃1\tfig1_at1_sw\r\n\tsw_必殺1\tfig1_cr1_sw\r\n"
                                    "\tax_攻撃1\tfig1_at1_ax\r\n}\r\n")),
                ("zu/fig1_prm.dbx", enc("{\r\n\tclass\tParam\r\n\tname\tfig1\r\n\ttexnum\t1\r\n\tPID_IKE\tfig1_b\r\n"
                                        "\t間合い\t10.0\r\n}\r\n")),
                ("xwp/IRONSWORD.dbx", enc("{\r\n\tclass\tModel\r\n\tfolder\txwp/ironsword\r\n"
                                          "\tmodel\tironsword\r\n}\r\n{\r\n\tclass\tWeapon\r\n\tkind\t0\r\n}\r\n")),
            ])
            assets = sa.BattleAssets(files, archive)
            u = unit(jid="JID_HERO", pid="PID_IKE")
            found = assets.unit(u)
            self.assertEqual(found.code, "fig1")
            self.assertEqual(found.prefixes, ["ax", "sw"])
            self.assertEqual(found.prefix, "sw")
            self.assertEqual(found.roles, {sa.ATTACK1: "fig1_at1_sw", sa.CRIT1: "fig1_cr1_sw"})
            self.assertEqual(found.pack.name, "fig1_sw.pak")
            self.assertEqual(found.texture.name, "fig1_b.tpl")
            self.assertEqual(found.spacing, 10.0)
            self.assertEqual(found.weapon_model.name, "ironsword.cmp")
            self.assertEqual(assets.unit(u, prefix="ax").roles, {sa.ATTACK1: "fig1_at1_ax"})
            self.assertEqual(assets.model_codes(), ["fig1"])


class StagingTests(unittest.TestCase):
    def test_battle_params(self):
        from fe_modding.battle_sim.staging import BattleParams
        p = BattleParams.from_text("{\r\n\tInitPosL\t\t-25.0, 0.0, 0.0, 0.0\t# left\r\n\tWaitInit\t60\r\n"
                                   "\tQuakeCrit\t2.5\r\n\tPertnerAngle\t40.0f\r\n}\r\n")
        self.assertEqual((p.start_x(0), p.start_x(1), p.wait_init, p.quake_crit, p.wait_atk2),
                         (-25.0, 20.0, 60, 2.5, 20))

    def test_unit_params(self):
        from fe_modding.battle_sim.staging import UnitParams, number
        u = UnitParams.from_values({"移動速度": "0.8", "間合い": "12.0", "ジャンプ必殺": "1"})
        self.assertEqual((u.move_speed, u.range, u.run_count), (0.8, 12.0, 1))
        self.assertTrue(u.jumps("crit"))
        self.assertFalse(u.jumps("attack"))
        self.assertEqual((number("-2.-2"), number("40.0f")), (-2.0, 40.0))


class CueAndFlightTests(unittest.TestCase):
    CLIPS = TimelineTests.CLIPS

    def lookup(self, side, role):
        return self.CLIPS.get(role)

    def test_skill_cues(self):
        a = unit("A", skills=["SID_SUNTRICK"])
        d = unit("D", skills=["SID_WINGSHIELD", "SID_COUNTER"], stats=(60, 10, 5, 10, 10, 5, 5, 3))
        log = simulate(a, d, outcomes=FixedOutcomes({(1, "proc:sol"): True, (1, "proc:counter"): True}))
        tl = timeline.build(log, self.lookup)
        cues = [(c.side, c.kind, c.key) for c in tl.cues]
        self.assertIn((0, "skill", "sol"), cues)
        self.assertIn((1, "skill", "counter"), cues)
        sol = next(c for c in tl.cues if c.key == "sol")
        self.assertEqual(sol.frame, tl.changes[0].frame)
        self.assertEqual(tl.quakes[0].strength, 1.8)  # a skill strike shakes with QuakeSkill
        log = simulate(a, d, outcomes=FixedOutcomes({(1, "proc:wing_guard"): True}))
        cues = [(c.side, c.kind, c.key) for c in timeline.build(log, self.lookup).cues]
        self.assertIn((1, "skill", "wing_guard"), cues)  # plays on its owner, the one struck

    def test_spell(self):
        fire = Weapon(**{**FIRE.__dict__, "effect": "EID_FIRE"})
        spell = Clip("EID_K_FIRE", 64, impact=47, swing=44)
        log = simulate(unit(weapon=fire), unit("D", weapon=None))
        tl = timeline.build(log, self.lookup, weapons=(timeline.WeaponEffects(1, "EID_K_FIRE"),),
                            effect_clip=lambda eid: spell if eid == "EID_K_FIRE" else None)
        cast = tl.camera[1].frame + 50  # the cast clip has no event 2: the spell starts as it ends
        # a missile weapon's spell starts at the caster; its own event 0 is the blow
        self.assertIn((0, "effect", "EID_K_FIRE", cast), [(c.side, c.kind, c.key, c.frame) for c in tl.cues])
        self.assertEqual(tl.changes[0].frame, cast + 47)
        self.assertNotIn(timeline.HIT_EFFECT, [c.key for c in tl.cues])  # the spell is the hit
        self.assertEqual(tl.flights, [])
        self.assertFalse([m for m in tl.moves if m.side == 0])  # the caster never runs
        self.assertEqual(tl.camera[1].script, "mag_at_l")
        # <NAME>_at0 as the spell leaves the caster, <NAME>_at1 on the target as it hits
        cams = [(c.frame, c.script, c.slot) for c in tl.camera]
        self.assertIn((cast, "FIRE_at0", 0), cams)
        self.assertIn((cast + 47, "FIRE_at1", 0), cams)
        miss = simulate(unit(weapon=fire), unit("D", weapon=None), outcomes=FixedOutcomes({(1, "hit"): False}))
        tl = timeline.build(miss, self.lookup, weapons=(timeline.WeaponEffects(1, "EID_K_FIRE"),),
                            effect_clip=lambda eid: spell if eid == "EID_K_FIRE" else None)
        self.assertNotIn("FIRE_at1", [c.script for c in tl.camera])  # a miss keeps the cast camera
        # a weapon whose effect is no missile plays it on the target
        tl = timeline.build(log, self.lookup, weapons=(timeline.WeaponEffects(0, "EID_K_FIRE"),))
        self.assertEqual(next(c.side for c in tl.cues if c.key == "EID_K_FIRE"), 1)

    def test_clip_cameras(self):
        log = simulate(unit("A"), unit("D"))
        plain = timeline.build(log, self.lookup)
        self.assertIn("atk_l", [c.script for c in plain.camera])
        tl = timeline.build(log, self.lookup, cameras={"at1", "run"})
        cams = [(c.frame, c.script, c.slot, c.mirror) for c in tl.camera]
        self.assertNotIn("atk_l", [c[1] for c in cams])  # the clip's own camera replaces it
        self.assertIn((125, "run", 0, False), cams)
        strikes = [c for c in tl.camera if c.script == "at1"]
        self.assertEqual([(c.slot, c.mirror) for c in strikes], [(0, False), (1, True)])
        self.assertEqual(strikes[0].frame, tl.changes[0].frame - 30)  # as the clip starts
        # the name is the clip's first 11 characters (a <role>_<previous> variant shares it)
        clips = dict(self.CLIPS, **{sa.ATTACK1: Clip("fig1_at1_ax_at2", 50, impact=30)})
        tl = timeline.build(log, lambda side, role: clips.get(role), cameras={"fig1_at1_ax"})
        self.assertIn("fig1_at1_ax", [c.script for c in tl.camera])

    def test_hit_miss_and_death_effects(self):
        def effects(log, **kw):
            tl = timeline.build(log, self.lookup, **kw)
            return tl, [(c.side, c.key, c.frame, c.height) for c in tl.cues if c.kind == "effect"]

        tl, cues = effects(simulate(unit("A"), unit("D", weapon=None)))
        hit = tl.changes[0].frame
        self.assertIn((1, timeline.HIT_EFFECT, hit + 1, 0.0), cues)  # DamageEffWait after the blow
        log = simulate(unit("A"), unit("D", weapon=None), outcomes=FixedOutcomes({(1, "crit"): True}))
        tl, cues = effects(log)
        self.assertIn((1, timeline.SPECIAL_HIT_EFFECT, tl.changes[0].frame + 1, 0.0), cues)
        tl, cues = effects(simulate(unit("A"), unit("D", weapon=None), outcomes=FixedOutcomes({(1, "hit"): False})))
        self.assertEqual(cues, [(1, timeline.MISS_EFFECT, tl.changes[0].frame, timeline.MARK_HEIGHT)])
        tl, cues = effects(simulate(unit("A"), unit("D", weapon=None, stats=(30, 5, 0, 5, 5, 0, 30, 0))))
        self.assertEqual([c[1] for c in cues], list(timeline.NO_DAMAGE_EFFECTS) * 2)  # two blows, no damage
        # a kill: EID_K_DEATH DeathEffTime before the death clip ends (it has no fade code)
        tl, cues = effects(simulate(unit("A"), unit("D", weapon=None, stats=(5, 5, 0, 5, 5, 0, 0, 0))))
        death = tl.changes[0].frame + 60 - 30
        self.assertIn((1, timeline.DEATH_EFFECT, death, 0.0), cues)
        # a damageEffId replaces the spark for a missile weapon
        tl, cues = effects(simulate(unit("A"), unit("D", weapon=None)),
                           weapons=(timeline.WeaponEffects(1, "EID_K_FIRE2_WP", "EID_K_FIRE2_WP"),))
        self.assertIn("EID_K_FIRE2_WP", [c[1] for c in cues])
        self.assertNotIn(timeline.HIT_EFFECT, [c[1] for c in cues])

    def test_dust(self):
        clips = dict(self.CLIPS)
        clips[sa.ATTACK1] = Clip("at1", 50, impact=30, swing=20, events=((10.0, 0x2B), (12.0, 0x2E), (14.0, 50)))
        log = simulate(unit("A"), unit("D", weapon=None))
        tl = timeline.build(log, lambda s, r: clips.get(r))
        start = tl.camera[1].frame
        self.assertEqual([(c.key, c.frame) for c in tl.cues if "DUST" in c.key],
                         [("EID_CLOUDOFDUST", start + 10), ("EID_CLOUDOFDUST4", start + 12)])
        tl = timeline.build(log, lambda s, r: clips.get(r), foot_effect=3)
        self.assertEqual([c.key for c in tl.cues if "SNOW" in c.key], ["EID_CLOUDOFSNOW", "EID_CLOUDOFSNOW4"])
        tl = timeline.build(log, lambda s, r: clips.get(r), foot_effect=0)
        self.assertFalse([c for c in tl.cues if "DUST" in c.key or "SNOW" in c.key])

    def test_bow_flight(self):
        clips = dict(self.CLIPS)
        clips[sa.ATTACK1] = Clip("shot", 60, impact=40, release=25)
        log = simulate(unit(weapon=BOW), unit("D"), distance=2)
        tl = timeline.build(log, lambda s, r: clips.get(r), distance=2, weapon_kinds=(timeline.BOW, None))
        flight = tl.flights[0]
        start = tl.camera[1].frame
        # ArrowSpeed 6 over the 40 units between the start spots, landing ShootDamageDist away
        self.assertEqual((flight.start, flight.end, flight.side), (start + 25, start + 25 + 7, 0))
        self.assertEqual([c.script for c in tl.camera[:3]], ["standby2", "mag_at_l", "bow_impact_l"])
        self.assertEqual(tl.changes[0].frame, flight.end)
        self.assertEqual(tl.moves, [])

    def test_unarmed_side_only_reacts(self):
        log = simulate(unit("A"), unit("D", weapon=None))
        self.assertEqual([s.side for s in log.strikes], [0])
        tl = timeline.build(log, self.lookup)
        self.assertEqual(tl.pose(1, tl.changes[0].frame + 1)[0], "dam")


class EffectTrackTests(unittest.TestCase):
    def test_material_alpha_tracks(self):
        import struct
        from fe_modding.formats.animation import MaterialTrack, read_material_tracks
        track = MaterialTrack(0, ((10, 0), (20, 200), (30, 0)))
        self.assertEqual([track.value(f) for f in (0, 10, 15, 20, 25, 40)], [0, 0, 100, 200, 100, 0])
        self.assertEqual(MaterialTrack(1, ((10, 0), (20, 200))).value(15), 0)  # step: holds the key
        # a two-material table: material 0 has no track (0xFFFF), material 1 two keys
        block = struct.pack(">HHI2H", 2, 0, 0, 0xFFFF, 12) + struct.pack(">HH4h", 2, 0, 0, 0, 45, 179)
        self.assertEqual(read_material_tracks(block), {1: MaterialTrack(0, ((0, 0), (45, 179)))})


class CameraTests(unittest.TestCase):
    def script(self, name="atk_l", rig="camCharaL0"):
        from fe_modding.formats import battle_camera as bc
        frames = [bc.Keyframe((0.0, 7.0, 0.0), (5.0, 180.0, 0.0), 60.0, 0),
                  bc.Keyframe((2.0, 7.0, 0.0), (5.0, 90.0, 0.0), 40.0, 10)]
        return bc.new_script(name, rig, keyframes=frames)

    def camera(self):
        from fe_modding.formats import zdbx
        rigs = ("{\r\n\tclass\tCamera\r\n\tname\tcam1\r\n\tdist\t60.0\r\n\trot\t\t-2.-2, 180.0, 0.0\r\n}\r\n"
                "{\r\n\tclass\tCamera\r\n\tname\tcamCharaL0\r\n\tentityClass\tActor\r\n"
                "\tentityName\tcharaAtk\r\n\tentityName1\tcharaDef\r\n\tdist\t50.0\r\n"
                "\toffs\t0.0, 7.0,0.0\r\n\trot\t\t6.0, 110.0, 0.0\r\n}\r\n")
        archive = zdbx.build_zdbx_archive([
            ("zdbx/camera.dbx", rigs.encode("shift_jis")),
            ("xcam/atk_l.dbx", self.script().encode("shift_jis")),
        ])
        return camera.GameCamera.from_zdbx(archive)

    def test_rigs_and_opening(self):
        gc = self.camera()
        self.assertEqual(gc.rigs["cam1"].rot, (-2.0, 180.0, 0.0))  # read as atof reads "-2.-2"
        shots = gc.track([], [], 5)
        self.assertEqual((shots[0].side, shots[0].pitch, shots[0].yaw, shots[0].dist), (None, -2.0, 180.0, 60.0))

    def test_script_tweens_and_mirror(self):
        gc = self.camera()
        shots = gc.track([camera.Cue(10, "atk_l", 0, False), camera.Cue(40, "atk_l", 1, True)], [], 60)
        self.assertEqual((shots[10].side, shots[10].dist, shots[10].yaw), (0, 60.0, 180.0))  # keyframe 0 cuts
        self.assertTrue(40.0 < shots[15].dist < 60.0)
        self.assertEqual((shots[20].dist, shots[20].yaw, shots[20].offs[0]), (40.0, 90.0, 2.0))
        mirrored = shots[50]
        self.assertEqual((mirrored.side, mirrored.yaw, mirrored.offs[0]), (1, 270.0, -2.0))
        self.assertEqual(shots[15].dist, round(shots[15].dist, 12))
        u = 5 / 10  # Catmull-Rom from 60 to 40 at mid-way, tangents from the previous tween
        self.assertAlmostEqual(camera.hermite(60.0, 60.0, 40.0, 40.0, u), 50.0)

    def test_camera_packs(self):
        from fe_modding.formats import battle_camera as bc, lz10, pak
        listing = "{\r\n\tnum\t1\r\n\tcamanim\tfig1_at1_ax\r\n}\r\n"
        pack = lz10.compress(pak.pack_pak([("fig1_at1_ax.dbx", self.script("fig1_at1_ax").encode("shift_jis")),
                                           ("fig1_ax.dbx", listing.encode("shift_jis"))]))
        self.assertEqual([s.name for s in bc.read_script_pack(pack)], ["fig1_at1_ax"])  # lists skipped
        gc = self.camera().with_packs([pack, b"broken"])
        self.assertEqual(set(gc.scripts), {"atk_l", "fig1_at1_ax"})
        self.assertEqual(gc.track([camera.Cue(0, "fig1_at1_ax")], [], 2)[0].dist, 60.0)

    def test_quake(self):
        gc = self.camera()
        shots = gc.track([camera.Cue(0, "atk_l")], [camera.Quake(5, 1.0)], 80)
        self.assertEqual(shots[4].shake, (0.0, 0.0))
        self.assertNotEqual(shots[6].shake[0], 0.0)
        self.assertAlmostEqual(shots[70].shake[0], shots[71].shake[0])  # died down

    def test_eye_and_look_at(self):
        shot = camera.Shot(0, (0.0, 0.0, 0.0), (0.0, 7.0, 0.0), 0.0, 180.0, 60.0)
        eye, center = shot.eye_center((1.0, 0.0, 0.0))
        self.assertEqual(center, (1.0, 7.0, 0.0))
        self.assertAlmostEqual(eye[2], 60.0)  # yaw 180 films from +Z
        rows = camera.look_at((0.0, 0.0, 60.0), (0.0, 0.0, 0.0))
        self.assertEqual([[round(v, 6) for v in r] for r in rows], [[1, 0, 0], [0, 1, 0], [0, 0, -1]])


class BattleTerrainTests(unittest.TestCase):
    def test_read_and_place(self):
        import math
        import struct

        from fe_modding.formats import battle_terrain as bt
        name = b"ground\0\0"
        data = (struct.pack(">4Hf", 1, 1, 1, 1, 2000.0)  # mapcapacityB at 0
                + struct.pack(">6fII", 0, 0, 0, 100, 10, 50, 0, 0x2c + 12)  # mapbuilddescB at 0x0c
                + struct.pack(">bbBB4xf", -3, -8, 64, 0, 0.0)  # mapbuildinstB at 0x2c
                + name)
        names = b"mapcapacityB\0mapbuilddescB\0mapbuildinstB\0"
        symbols = struct.pack(">6I", 0x00, 0, 0x0c, 13, 0x2c, 27)
        blob = struct.pack(">4I", 0, len(data), 0, 3) + bytes(16) + data + symbols + names
        terrain = bt.read_battle_terrain(blob)
        self.assertEqual(terrain.models[0].name, "ground")
        self.assertEqual(terrain.models[0].bounds, (0, 0, 0, 100, 10, 50))
        inst = terrain.instances[0]
        self.assertEqual((inst.x, inst.y, inst.angle), (-3, -8, 64))
        m = inst.matrix()  # angle 64: 270 degrees, about the tile's centre, scaled by 3, at tile (-3, -8)
        c, s = math.cos(math.radians(270)), math.sin(math.radians(270))
        point = (2.5 + c * (10 - 2.5) + s * (0 - 2.5), 0.0, 2.5 - s * (10 - 2.5) + c * (0 - 2.5))
        expected = (point[0] * 3 - 45, 0.0, point[2] * 3 - 120)
        got = tuple(sum(m[r][k] * v for k, v in enumerate((10.0, 0.0, 0.0))) + m[r][3] for r in range(3))
        for a, b in zip(got, expected):
            self.assertAlmostEqual(a, b)


if __name__ == "__main__":
    unittest.main()
