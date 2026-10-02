import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.battle_sim import (
    Combatant, Fe9Rng, Fe9Rules, FixedOutcomes, RngOutcomes, from_character, from_class, simulate,
)
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
        item = fe8data.ItemEntry(0, 0, "IID_Z", None, None, "sword", "rod", "E", ["magsw", None], ["fly", None],
                                 None, None, 0, 30, 7, 80, 9, 0, 1, 2, 0, 1, [0] * 10, [0] * 8, 0, b"")
        w = weapon_from_item(item)
        self.assertTrue(w.magic)
        self.assertEqual(w.effective, frozenset({"fly"}))


if __name__ == "__main__":
    unittest.main()
