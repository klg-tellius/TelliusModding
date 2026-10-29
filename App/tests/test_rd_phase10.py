import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import battle_sim
from fe_modding.battle_sim.units import Combatant, Weapon
from fe_modding.game_profile import BATTLE_SIM, PLAY, PLAYTHROUGH, PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE
from fe_modding.playthrough.ai_vm import unsupported_fe10_opcodes
from fe_modding.playthrough.dialect import dialect_for
from fe_modding.playthrough.state import GameState, SimUnit
from fe_modding.playthrough import fog, natives, triggers


class Phase10ProfileTests(unittest.TestCase):
    def test_capabilities_are_distinct_and_enabled(self):
        for profile in (PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE):
            self.assertTrue(profile.supports(PLAY))
            self.assertTrue(profile.supports(PLAYTHROUGH))
            self.assertTrue(profile.supports(BATTLE_SIM))

    def test_rd_dialect_contract(self):
        dialect = dialect_for(RADIANT_DAWN_PROFILE)
        self.assertEqual(dialect.cp.entry_words, 10)
        self.assertEqual(dialect.flag_slots, 128)
        self.assertEqual(dialect.army.phase_order, (0, 1, 2))
        self.assertIn(19, dialect.trigger_catalogue)
        self.assertEqual(unsupported_fe10_opcodes(), [])

    def test_native_registry_has_explicit_rd_ownership(self):
        world = type("World", (), {"dialect": dialect_for(RADIANT_DAWN_PROFILE)})()
        self.assertEqual(natives.classification(world, "SetSight"), "stateful")
        self.assertEqual(natives.classification(world, "EventCameraMove"), "presentation")
        self.assertEqual(natives.classification(world, "UntracedMutation"), "unclassified")


class Fe10BattleTests(unittest.TestCase):
    def unit(self, name, weapon, **kw):
        return Combatant(name=name, stats=[30, 15, 5, 12, 14, 8, 10, 6], weapon=weapon, **kw)

    def test_forecast_uses_rd_effectiveness_and_strength_weight(self):
        rules = battle_sim.Fe10Rules()
        sword = Weapon(weapon_type="sword", attack_type="sword", might=5, hit=80, weight=20,
                       min_range=1, max_range=1, effective=frozenset({"armor"}), durability=20)
        axe = Weapon(weapon_type="axe", attack_type="axe", might=4, hit=70, weight=4,
                     min_range=1, max_range=1, durability=20)
        a = self.unit("A", sword)
        d = self.unit("D", axe, categories=frozenset({"armor"}))
        side = rules.side(a, d)
        self.assertTrue(side.effective)
        self.assertEqual(side.attack_speed, 9)  # 14 - (20 - 15)
        self.assertEqual(side.atk, 15 + 5 * 3 + 1)

    def test_simulate_delegates_and_consumes_rd_durability(self):
        rules = battle_sim.Fe10Rules()
        weapon = Weapon(weapon_type="sword", attack_type="sword", might=5, hit=100, weight=0,
                        min_range=1, max_range=1, durability=10)
        log = battle_sim.simulate(self.unit("A", weapon), Combatant(name="D", stats=[30] + [5] * 7),
                                  rules=rules, outcomes=battle_sim.FixedOutcomes())
        self.assertTrue(log.strikes)
        self.assertLess(log.attacker.weapon.durability, 10)

    def test_exp_uses_rd_game_data_and_skill_adjustments(self):
        rules = battle_sim.Fe10Rules()
        winner = self.unit("A", None, effective_level=20, exp=10, skills=["SID_PARAGON"])
        other = self.unit("D", None, effective_level=25, boss=True)
        constants = {"action_exp_base": 10, "action_exp_multiplier": 100,
                     "kill_exp_base": 15, "kill_exp_multiplier": 100, "boss_kill_bonus": 20}
        self.assertEqual(rules.battle_exp(winner, other, dealt=True, killed=True, constants=constants), 90)

    def test_biorhythm_affects_hit_avoid_and_skill_activation_but_not_critical(self):
        rules = battle_sim.Fe10Rules()
        weapon = Weapon(weapon_type="sword", attack_type="sword", might=5, hit=70, crit=8, weight=0,
                        min_range=1, max_range=1, durability=20)
        attacker = self.unit("A", weapon, biorhythm=10)
        defender = self.unit("D", weapon, biorhythm=10)
        side = rules.side(attacker, defender)
        neutral = rules.side(self.unit("A", weapon), self.unit("D", weapon))
        self.assertEqual(side.raw_hit, neutral.raw_hit + 10)
        self.assertEqual(side.avoid, neutral.avoid + 10)
        self.assertEqual(side.raw_crit, neutral.raw_crit)
        self.assertEqual(rules.proc_chance("adept", attacker), rules.proc_chance("adept", self.unit("A", weapon)) + 10)


class SightTests(unittest.TestCase):
    def test_show_all_does_not_mutate_game_sight(self):
        world = type("World", (), {"width": 8, "height": 8, "classes": {}})()
        state = GameState(sight=2)
        state.add_unit(SimUnit(0, "PID", "JID", 0, 3, 3, vision=2))
        self.assertLess(len(fog.visible_tiles(world, state)), 64)
        self.assertEqual(len(fog.visible_tiles(world, state, show_all=True)), 64)
        self.assertEqual(state.sight, 2)


if __name__ == "__main__":
    unittest.main()
