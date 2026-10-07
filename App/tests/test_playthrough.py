import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import cp_ai_lang, cp_data, dispo, fe8data  # noqa: E402
from fe_modding.formats.cmb.compiler import compile_source  # noqa: E402
from fe_modding.playthrough import actions, ai_vm, combat, fog, movement, setup  # noqa: E402
from fe_modding.playthrough.simulation import LINE, MESSAGE, Simulation  # noqa: E402
from fe_modding.playthrough.state import ENEMY, PLAYER, GameState, SimUnit  # noqa: E402
from fe_modding.playthrough.world import World  # noqa: E402

PLAIN, FOREST, WALL = "平地", "林", "壁"


def _class(jid, movement=5, movement_type=1, ranks="D--------", skills=(), categories=(), bases=(20, 5, 0, 5, 5, 0, 3, 0),
           growths=(50,) * 8):
    return fe8data.ClassEntry(
        index=0, offset=0, jid=jid, mjid=None, hybrid_id=None, promotes_to=None, aid=None, movement=movement,
        stat_caps=[60] + [30] * 7, base_stats=list(bases), growths=list(growths), movement_type=movement_type,
        weapon_ranks=ranks, skills=list(skills), raw=b"", build=5, categories=list(categories),
    )


def _char(pid, jid, level=1, bonus=(0,) * 8, sids=()):
    return fe8data.CharacterEntry(
        index=0, offset=0, pid=pid, fid=None, jid=jid, sids=list(sids), aid_unpromoted=None, aid_promoted=None,
        level=level, build=0, weight=0, stat_bonus=list(bonus), growth=[50] * 8, fixed_growth_start=[0] * 8,
    )


def _item(iid, weapon_type="sword", might=5, hit=100, crit=0, weight=0, rng=(1, 1), uses=40, attack_type="sword"):
    return fe8data.ItemEntry(
        index=0, offset=0, iid=iid, miid=None, help_key=None, weapon_type=weapon_type, attack_type=attack_type,
        rank=None, properties=[], categories=[], effect=None, weapon_effect=None, cost=0, uses=uses, might=might,
        hit=hit, weight=weight, crit=crit, min_range=rng[0], max_range=rng[1], icon=0, weapon_exp=1,
        stat_bonus=[0] * 10, growth_bonus=[0] * 8, trail_color=0, padding=b"",
    )


def _terrain(index, name, costs, avoid=0, defense=0, heal=0):
    return fe8data.TerrainType(index, name, f"MT_{name}", 0, avoid=avoid, defense=defense, heal=heal,
                               move_costs=tuple(costs))


TERRAIN = [
    _terrain(0, PLAIN, [1] * 15),
    _terrain(1, FOREST, [2] * 15, avoid=20, defense=1),
    _terrain(2, WALL, [255] * 15),
]


def _fe8():
    return fe8data.Fe8Data(
        characters=[_char("PID_A", "JID_SWORD"), _char("PID_B", "JID_SWORD"), _char("PID_C", "JID_SWORD"),
                    _char("PID_RIDER", "JID_RIDER", sids=["SID_TWICE"]), _char("PID_HEALER", "JID_CLERIC")],
        classes=[_class("JID_SWORD"), _class("JID_RIDER", movement=7, movement_type=7),
                 _class("JID_CLERIC", ranks="-------D-", bases=(18, 0, 5, 3, 4, 0, 1, 5))],
        items=[_item("IID_SWORD"), _item("IID_KILLER", might=30), _item("IID_HEAL", weapon_type="rod", might=0,
                                                                         attack_type="rod", rng=(1, 1))],
        skills=[],
    )


def _world(width=8, height=8, terrain=None, scripts=(), cp=None, messages=None):
    grid = [[PLAIN] * height for _ in range(width)]
    for (x, y), name in (terrain or {}).items():
        grid[x][y] = name
    return World(width=width, height=height, terrain=grid, terrain_types=TERRAIN, fe8=_fe8(),
                 scripts=list(scripts), cp=cp, messages=dict(messages or {}))


def _unit(state, pid, x, y, faction=PLAYER, items=("IID_SWORD",), jid=None, move=None, **kw):
    world_fe8 = _fe8()
    char = next(c for c in world_fe8.characters if c.pid == pid)
    cls = next(c for c in world_fe8.classes if c.jid == (jid or char.jid))
    unit = SimUnit(uid=0, pid=pid, jid=cls.jid, faction=faction, x=x, y=y, stats=list(cls.base_stats),
                   hp=cls.base_stats[0], build=cls.build, move=move if move is not None else cls.movement,
                   movement_type=cls.movement_type, skills=list(char.sids),
                   items=[[i, 40, False] for i in items], **kw)
    return state.add_unit(unit)


def _script(source):
    return compile_source(source).script


class MovementTests(unittest.TestCase):
    def test_terrain_costs_and_walls(self):
        world = _world(terrain={(1, 0): FOREST, (0, 1): WALL})
        state = GameState()
        unit = _unit(state, "PID_A", 0, 0, move=2)
        reach = movement.destinations(world, state, unit)
        self.assertIn((1, 0), reach)
        self.assertEqual(reach[(1, 0)][0], 2)
        self.assertNotIn((2, 0), reach)  # forest ate the movement
        self.assertNotIn((0, 1), reach)  # wall
        self.assertEqual(movement.path(reach, (1, 0)), [(0, 0), (1, 0)])

    def test_hostile_units_block_allies_pass(self):
        world = _world()
        state = GameState()
        unit = _unit(state, "PID_A", 0, 0, move=2)
        _unit(state, "PID_B", 1, 0)
        reach = movement.destinations(world, state, unit)
        self.assertIn((2, 0), reach)  # through the ally
        self.assertNotIn((1, 0), reach)  # but not onto it
        state.units[2].faction = ENEMY
        reach = movement.destinations(world, state, unit)
        self.assertNotIn((2, 0), reach)

    def test_link_grid_closes_an_edge(self):
        world = _world(width=2, height=1)
        from fe_modding.formats import map_file

        world.link = [[map_file.LINK_PASS_WEST], [map_file.LINK_PASS_WEST]]
        state = GameState()
        unit = _unit(state, "PID_A", 0, 0)
        self.assertNotIn((1, 0), movement.destinations(world, state, unit))


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.world = _world()
        self.state = GameState()

    def test_attack_with_forced_outcomes_kills_and_uses_weapon(self):
        a = _unit(self.state, "PID_A", 0, 0, items=("IID_KILLER",))
        b = _unit(self.state, "PID_B", 2, 0, faction=ENEMY)
        self.state.forced = {}
        sim = Simulation(self.world, self.state)
        sim.command(actions.Act(a.uid, (1, 0), "attack", b.uid, 0))
        sim.run()
        state = sim.state
        self.assertTrue(state.units[b.uid].dead)
        self.assertEqual(state.units[a.uid].items[0][1], 39)
        self.assertTrue(state.units[a.uid].done)
        self.assertTrue(any(o.kind == "battle" for e in sim.history for o in e.outputs))

    def test_shove(self):
        a = _unit(self.state, "PID_A", 0, 0)
        b = _unit(self.state, "PID_B", 2, 0)
        actions.apply(self.world, self.state, actions.Act(a.uid, (1, 0), "shove", b.uid))
        self.assertEqual(self.state.units[b.uid].tile, (3, 0))

    def test_shove_blocked_by_wall(self):
        world = _world(terrain={(3, 0): WALL})
        a = _unit(self.state, "PID_A", 0, 0)
        _unit(self.state, "PID_B", 2, 0)
        self.assertFalse(any(c.action == "shove" for c in actions.choices(world, self.state, a, (1, 0))))

    def test_canto_after_acting(self):
        rider = _unit(self.state, "PID_RIDER", 0, 0, jid="JID_RIDER", items=("IID_KILLER",))
        foe = _unit(self.state, "PID_B", 3, 0, faction=ENEMY)
        self.state.forced = {}
        sim = Simulation(self.world, self.state)
        sim.command(actions.Act(rider.uid, (2, 0), "attack", foe.uid, 0))
        sim.run()
        self.assertEqual(sim.state.canto, (rider.uid, 5))
        sim.command(actions.CantoMove(rider.uid, (2, 4)))
        self.assertEqual(sim.state.units[rider.uid].tile, (2, 4))
        self.assertIsNone(sim.state.canto)

    def test_staff_heals(self):
        healer = _unit(self.state, "PID_HEALER", 0, 0, jid="JID_CLERIC", items=("IID_HEAL",))
        hurt = _unit(self.state, "PID_A", 2, 0)
        hurt.hp = 5
        choice = next(c for c in actions.choices(self.world, self.state, healer, (1, 0)) if c.action == "staff")
        actions.apply(self.world, self.state, actions.Act(healer.uid, (1, 0), "staff", choice.target, choice.item))
        self.assertEqual(self.state.units[hurt.uid].hp, 5 + 5 + 10)

    def test_move_through_an_ally(self):
        # a corridor: the ally's tile is on the path but is not a destination
        world = _world(width=4, height=1)
        state = GameState()
        a = _unit(state, "PID_A", 0, 0)
        _unit(state, "PID_B", 1, 0)
        actions.apply(world, state, actions.Act(a.uid, (2, 0)))
        self.assertEqual(state.units[a.uid].tile, (2, 0))

    def test_link_sections_list_exceptions(self):
        # retail maps list only the tiles with closed directions; the others are open
        from fe_modding.formats import map_file
        from fe_modding.playthrough import loader

        data = map_file.MapData(capacity=map_file.MapCapacity(3, 1, 0, 0, 2000.0),
                                link=[[-1], [map_file.LINK_PASS_WEST], [-1]], link_at=None, link_abs=None)
        world = _world(width=3, height=1)
        world.link = loader.link_grid(data)
        state = GameState()
        a = _unit(state, "PID_A", 0, 0)
        self.assertEqual(set(movement.destinations(world, state, a)), {(0, 0), (1, 0)})  # (1,0) opens west only

    def test_unreachable_destination_rejected(self):
        a = _unit(self.state, "PID_A", 0, 0)
        with self.assertRaises(actions.CommandError):
            actions.apply(self.world, self.state, actions.Act(a.uid, (7, 7)))


    def test_failed_action_leaves_the_unit_in_place(self):
        a = _unit(self.state, "PID_HEALER", 0, 0, jid="JID_CLERIC", items=("IID_HEAL",))
        b = _unit(self.state, "PID_B", 2, 0, faction=ENEMY)
        with self.assertRaises(actions.CommandError):  # no weapon
            actions.apply(self.world, self.state, actions.Act(a.uid, (1, 0), "attack", b.uid))
        self.assertEqual(a.tile, (0, 0))
        self.assertFalse(a.done)
        self.assertEqual(self.state.out, [])

    def test_rejected_command_keeps_the_forward_history(self):
        a = _unit(self.state, "PID_A", 0, 0)
        sim = Simulation(self.world, self.state)
        sim.command(actions.Act(a.uid, (1, 0)))
        sim.back()
        entries = len(sim.history)
        with self.assertRaises(actions.CommandError):
            sim.command(actions.Act(a.uid, (7, 7)))
        self.assertEqual(len(sim.history), entries)

    def test_battle_exp_follows_calculate_battle_exp(self):
        def unit(level, *skills):
            return SimUnit(uid=0, pid="PID_X", jid="JID_X", faction=PLAYER, x=0, y=0, level=level, skills=list(skills))

        exp = combat.battle_exp
        # Normal constants: level 20, mode 20, promotion 0, boss 30, thief 20
        self.assertEqual(exp(unit(5), unit(5), True, False), 10)  # (20 + 5 - 5 + 1) / 2
        self.assertEqual(exp(unit(5), unit(5), True, True), 30)  # + 20 + 5 - 5
        # a promoted unit counts 20 levels higher: Titania (Paladin 4) killing a level-3 soldier
        self.assertEqual(exp(unit(4, "SID_HIGHER"), unit(3), True, True), 1)
        self.assertEqual(exp(unit(5), unit(5, "SID_BOSS"), True, True), 60)
        self.assertEqual(exp(unit(5), unit(5, "SID_STEAL"), True, True), 50)
        self.assertEqual(exp(unit(5), unit(5), False, True), 1)  # no damage dealt
        self.assertEqual(exp(unit(5, "SID_ELITE"), unit(5), True, False), 20)
        self.assertEqual(exp(unit(5), unit(5, "SID_FINAL"), True, True), 0)
        self.assertEqual(exp(unit(1), unit(20, "SID_HIGHER", "SID_BOSS"), True, True), 100)  # capped
        hard = {"battle_exp_mode_bonus": 15, "battle_exp_level_constant": 20, "promotion_exp_bonus_base": 0,
                "boss_exp_bonus": 25, "thief_exp_bonus": 20}
        self.assertEqual(exp(unit(5), unit(5), True, True, hard), 25)

    def test_fallen_unit_gains_no_exp(self):
        a = _unit(self.state, "PID_A", 1, 0)
        b = _unit(self.state, "PID_B", 0, 0, faction=ENEMY, items=("IID_KILLER",))
        a.exp = 99
        self.state.forced = {}
        combat.fight(self.world, self.state, b, a, 0, 1)
        self.assertEqual(a.hp, 0)
        self.assertEqual((a.exp, a.level), (99, 1))

    def test_destroyed_village_is_spent(self):
        b = _unit(self.state, "PID_B", 0, 0, faction=ENEMY)
        actions.apply(self.world, self.state, actions.Act(b.uid, (1, 1), "destroy"), by_ai=True)
        self.assertIn((1, 1), self.state.visited)


VISIT_SCRIPT = '''
@export
def Startup():
    regist("visited_flag")

@on_location(x=1, y=1, action="visit", name=None)
def village():
    set("visited_flag")
    TalkEvent("MS_VISIT")
'''


class EventTests(unittest.TestCase):
    def test_visit_runs_its_event_once(self):
        world = _world(scripts=[_script(VISIT_SCRIPT)], messages={"MS_VISIT": "Hello$K"})
        state = setup.initial_state(world)
        a = _unit(state, "PID_A", 0, 0)
        sim = Simulation(world, state)
        sim.run()
        self.assertTrue(sim.state.awaiting_input)
        self.assertIn("visit", [c.action for c in actions.choices(world, sim.state, sim.state.units[a.uid], (1, 1))])
        sim.command(actions.Act(a.uid, (1, 1), "visit"))
        steps = sim.run(MESSAGE)
        self.assertEqual(steps[-1].kind, "message")
        sim.run()
        self.assertTrue(sim.state.get_flag("visited_flag"))
        self.assertNotIn("visit", [c.action for c in actions.choices(world, sim.state, sim.state.units[a.uid], (1, 1))])

    def test_turn_event_deploys_and_vm_arithmetic(self):
        source = '''
@export
def Startup():
    regist("f")

@on_phase(turn_from=2, turn_to=2, phase="player")
def reinforce():
    var n = 0
    while n < 3:
        n += 1
    if n == 3 and Normal():
        set("f")
'''
        world = _world(scripts=[_script(source)])
        state = setup.initial_state(world)
        _unit(state, "PID_A", 0, 0)
        sim = Simulation(world, state)
        sim.run()
        self.assertFalse(sim.state.get_flag("f"))
        sim.command(actions.EndPhase())
        sim.run()
        self.assertEqual(sim.state.turn, 2)
        self.assertTrue(sim.state.get_flag("f"))

    def test_line_stepping_and_rewind(self):
        world = _world(scripts=[_script(VISIT_SCRIPT)], messages={"MS_VISIT": "Hi$K"})
        state = setup.initial_state(world, seed=3)
        _unit(state, "PID_A", 0, 0)
        sim = Simulation(world, state)
        first = sim.run(LINE)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].kind, "script")
        sim.run()
        end = sim.cursor
        sim.back(end)
        self.assertEqual(sim.cursor, 0)
        sim.forward(end)
        self.assertTrue(sim.state.awaiting_input)

    def test_deterministic_replay(self):
        def play(seed):
            world = _world()
            state = GameState(rng=__import__("fe_modding.battle_sim", fromlist=["Fe9Rng"]).Fe9Rng(seed))
            a = _unit(state, "PID_A", 0, 0)
            b = _unit(state, "PID_B", 2, 0, faction=ENEMY)
            sim = Simulation(world, state)
            sim.command(actions.Act(a.uid, (1, 0), "attack", b.uid, 0))
            sim.run()
            return [u.hp for u in sim.state.units.values()], sim

        first, sim = play(7)
        again, _ = play(7)
        self.assertEqual(first, again)
        # a new command from an earlier entry drops the later ones
        sim.goto(0)
        sim.command(actions.Act(1, (0, 1)))
        self.assertTrue(sim.at_end)
        self.assertEqual(sim.state.units[1].tile, (0, 1))


def _cp(scripts: dict) -> cp_data.CpDocument:
    sections = []
    for i, (name, source) in enumerate(scripts.items()):
        result = cp_ai_lang.compile_source(source, check=False)
        section = cp_data.Section(name)
        cp_data.write_script(section, cp_data.Script(name, i, result.entries))
        sections.append(section)
    return cp_data.CpDocument(sections, [])


class AiTests(unittest.TestCase):
    def test_enemy_attacks_in_order_then_player_phase(self):
        cp = _cp({"SEQ_ATK": "attack(chance=100)\nif found: goto L99\nL99:\nend()\n",
                  "SEQ_MOV": "move_nearest()\nend()\n"})
        world = _world(cp=cp)
        state = GameState()
        _unit(state, "PID_A", 0, 0)
        e1 = _unit(state, "PID_B", 3, 0, faction=ENEMY, seq_attack="SEQ_ATK", seq_move="SEQ_MOV", ai_order=1)
        e2 = _unit(state, "PID_C", 7, 7, faction=ENEMY, seq_attack="SEQ_ATK", seq_move="SEQ_MOV", ai_order=0)
        from fe_modding.playthrough.state import PhaseStart

        state.pending = [PhaseStart(ENEMY)]
        sim = Simulation(world, state)
        steps = sim.run()
        ai_lines = [o.text for s in steps for o in s.outputs if o.kind == "ai"]
        self.assertTrue(any("SEQ_ATK" in t for t in ai_lines))
        acted = [o.data.get("uid") for s in steps for o in s.outputs if o.kind == "ai" and o.text.endswith("'s turn")]
        self.assertEqual(acted[:2], [e2.uid, e1.uid])  # lower ai_order first
        battles = [o for s in steps for o in s.outputs if o.kind == "battle"]
        self.assertTrue(battles)
        self.assertEqual(sim.state.phase, PLAYER)
        self.assertEqual(sim.state.turn, 2)
        self.assertNotEqual(sim.state.units[e2.uid].tile, (7, 7))  # moved towards the player

    def test_attack_choice_comes_with_its_ranking(self):
        cp = _cp({"SEQ_ATK": "attack(chance=100)\nend()\n"})
        world = _world(cp=cp)
        state = GameState()
        strong = _unit(state, "PID_A", 2, 0)
        weak = _unit(state, "PID_C", 0, 2)
        weak.hp = 3  # the attack removes all of its HP: the better target
        e = _unit(state, "PID_B", 0, 0, faction=ENEMY, seq_attack="SEQ_ATK", seq_move="SEQ_ATK")
        from fe_modding.playthrough.state import AiTurn

        state.pending = [AiTurn(e.uid)]
        sim = Simulation(world, state)
        sim.run()
        decision = next(o.data["decision"] for en in sim.history for o in en.outputs
                        if o.kind == "ai" and o.data.get("decision"))
        ranking = decision["ranking"]
        self.assertGreater(len(ranking), 1)
        self.assertEqual([c["score"] for c in ranking], sorted((c["score"] for c in ranking), reverse=True))
        self.assertIn("C", ranking[0]["row"])  # PID_C, the one it can finish
        self.assertEqual(set(ranking[0]["terms"]), set(ai_vm.SCORE_TERMS))
        self.assertIn("kill bonus +50", ranking[0]["row"])
        self.assertLess(sim.state.units[weak.uid].hp, 3)
        self.assertEqual(sim.state.units[strong.uid].hp, sim.state.units[strong.uid].stats[0])

    def test_enemy_threat_map_is_the_hostiles_expected_damage(self):
        from fe_modding.playthrough import combat as cb

        # a corridor: the deciding enemy at 0 (Mov 9), two swordsmen (Mov 5) at 9 and 11
        world = _world(width=12, height=1)
        state = GameState()
        e = _unit(state, "PID_B", 0, 0, faction=ENEMY, move=9)
        q1 = _unit(state, "PID_A", 9, 0)
        q2 = _unit(state, "PID_C", 11, 0)
        threat = ai_vm.enemy_threat_map(world, state, e)

        def value(p):
            f = cb.forecast(world, p, e, world.items["IID_SWORD"], 1).attacker
            return ai_vm.expected_hit_damage(f)

        v1, v2 = value(q1), value(q2)
        self.assertGreater(v1, 0)
        # q1 stands on a free tile it reaches (4-8, 10; not its own 9 nor q2's 11): strikes 3-9 and 11.
        # q2 stands on 6-8, 10: strikes 5-9 and 11. The enemy reaches 0-8 (q1 blocks the corridor).
        expected = {(3, 0): v1, (4, 0): v1, **{(x, 0): v1 + v2 for x in range(5, 9)}}
        self.assertEqual(threat, expected)
        # the attack score reads the map >> 4
        self.assertEqual((threat[(5, 0)] >> 4) & 0xFFF, (v1 + v2) // 16)

    def test_object_tiles_are_left_out_of_the_threat_map(self):
        world = _world(width=8, height=1)
        world.terrain_types = [fe8data.TerrainType(0, PLAIN, "MT_" + PLAIN, 0, avoid=0, defense=0, heal=0,
                                                   move_costs=tuple([1] * 15)),
                               fe8data.TerrainType(1, FOREST, "MT_" + FOREST, 0, avoid=0, defense=0, heal=0,
                                                   move_costs=tuple([1] * 15), flag7=1)]
        world.terrain_by_name = {t.name: t for t in world.terrain_types}
        world.terrain[3][0] = FOREST
        state = GameState()
        e = _unit(state, "PID_B", 0, 0, faction=ENEMY, move=6)
        _unit(state, "PID_A", 6, 0)
        threat = ai_vm.enemy_threat_map(world, state, e)
        # the swordsman stands on 1, 2, 4, 5 or 7 (3 is an object tile, 6 its own): strikes 0-6;
        # the enemy reaches 0-5 but not 3, where nobody can stand
        self.assertEqual(set(threat), {(0, 0), (1, 0), (2, 0), (4, 0), (5, 0)})

    def test_damage_term_and_its_bonuses(self):
        from types import SimpleNamespace as S

        hit = S(damage=10, hit=100, doubles=False)
        miss = S(damage=10, hit=0, doubles=False)
        # weight 64 = x2: 10 expected -> 20; the target has 25 HP: no kill bonus, 20 HP: +50
        self.assertEqual(ai_vm._damage_term(hit, None, 30, 25, 64), (20, False))
        self.assertEqual(ai_vm._damage_term(hit, None, 30, 20, 64), (70, True))
        # double attack, 50% hit: 2 x 10 x (1 - 0.25)^1.75
        self.assertEqual(ai_vm._expected(S(damage=10, hit=50, doubles=True), 1.75), int(20 * 0.75 ** 1.75))
        # no damage: minus the expected counter, capped at 15; +50 first when it reaches the attacker's HP
        self.assertEqual(ai_vm._damage_term(miss, S(damage=8, hit=100, doubles=False), 30, 25, 64), (-8, False))
        self.assertEqual(ai_vm._damage_term(miss, S(damage=8, hit=100, doubles=False), 5, 25, 64), (-15, False))

    def test_provoke_draws_the_attack_and_shade_avoids_it(self):
        cp = _cp({"SEQ_ATK": "attack(chance=100)\nend()\n"})
        for skill, expected in (("SID_PROVOKE", "PID_A"), ("SID_SHADE", "PID_C")):
            world = _world(cp=cp)
            state = GameState()
            a = _unit(state, "PID_A", 2, 0)
            _unit(state, "PID_C", 0, 2)
            a.skills.append(skill)
            e = _unit(state, "PID_B", 0, 0, faction=ENEMY, seq_attack="SEQ_ATK", seq_move="SEQ_ATK")
            from fe_modding.playthrough.state import AiTurn

            state.pending = [AiTurn(e.uid)]
            sim = Simulation(world, state)
            sim.run()
            decision = next(o.data["decision"] for en in sim.history for o in en.outputs
                            if o.kind == "ai" and o.data.get("decision"))
            self.assertIn(expected.removeprefix("PID_"), decision["ranking"][0]["row"], skill)
            self.assertEqual(decision["ranking"][0]["terms"]["skill_bonus"][0],
                             50 if skill == "SID_PROVOKE" and expected == "PID_A" else 0)

    def test_negative_mov_change_slows_the_move(self):
        # retail SEQ_NEARESTUNITMOVE_BLACKNIGHT: move_stat(add=-3), move, move_stat(add=3)
        cp = _cp({"SEQ_ATK": "end()\n", "SEQ_SLOW": "r0 = move_stat(add=-3)\nmove_nearest()\n"
                                                    "r0 = move_stat(add=3)\nend()\n"})
        world = _world(width=12, height=1, cp=cp)
        state = GameState()
        _unit(state, "PID_A", 11, 0)
        e = _unit(state, "PID_B", 0, 0, faction=ENEMY, seq_attack="SEQ_ATK", seq_move="SEQ_SLOW")
        from fe_modding.playthrough.state import AiTurn

        state.pending = [AiTurn(e.uid)]
        sim = Simulation(world, state)
        sim.run()
        self.assertEqual(sim.state.units[e.uid].tile, (2, 0))  # Mov 5 - 3
        self.assertEqual(sim.state.units[e.uid].move, 5)

    def test_label_fallthrough_into_next_section(self):
        cp = _cp({"SEQ_A": "goto L5\n", "SEQ_B": "L5:\nend()\n"})
        world = _world(cp=cp)
        prog = ai_vm.program(world, "SEQ_A")
        self.assertIsNotNone(prog.label(5))
        self.assertGreaterEqual(prog.label(5), prog.body)

    def test_entry_cap_runs_fallback(self):
        cp = _cp({"SEQ_LOOP": "L1:\ngoto L1\n"})
        world = _world(cp=cp)
        state = GameState()
        _unit(state, "PID_A", 0, 0)
        e = _unit(state, "PID_B", 5, 0, faction=ENEMY, seq_attack="SEQ_LOOP", seq_move="SEQ_LOOP")
        from fe_modding.playthrough.state import AiTurn

        state.pending = [AiTurn(e.uid)]
        sim = Simulation(world, state)
        sim.run(limit=5000)
        texts = [o.text for en in sim.history for o in en.outputs if o.kind == "ai"]
        self.assertTrue(any("built-in fallback" in t for t in texts))


class ChoiceTests(unittest.TestCase):
    SOURCE = ("@export\ndef Startup():\n    Dialog2Items(\"M1\", \"M2\")\n    if DialogResult() == 1:\n"
              "        printf(\"second\")\n    else:\n        printf(\"first\")\n")

    def _run(self, plan):
        world = _world(scripts=[_script(self.SOURCE)], messages={"M1": "Yes", "M2": "No"})
        state = setup.initial_state(world)
        state.choice_plan = list(plan)
        sim = Simulation(world, state)
        sim.run()
        return [o.text for e in sim.history for o in e.outputs if o.kind == "script" and "Choice" in o.text], sim

    def test_default_is_the_first_entry(self):
        texts, _ = self._run([])
        self.assertEqual(len(texts), 1)
        self.assertIn("entry 1 of 2", texts[0])
        self.assertIn("default", texts[0])

    def test_plan_picks_and_is_consumed(self):
        texts, sim = self._run([1])
        self.assertIn("entry 2 of 2", texts[0])
        self.assertIn("your choice", texts[0])
        self.assertEqual(sim.state.choice_plan, [])
        self.assertEqual(sim.state.dialog_result, 1)

    def test_out_of_range_is_clamped(self):
        texts, _ = self._run([9])
        self.assertIn("entry 2 of 2", texts[0])


class FogTests(unittest.TestCase):
    def setUp(self):
        self.world = _world(width=10, height=4)
        self.world.classes["JID_SWORD"].vision = 2
        self.state = GameState()
        self.player = _unit(self.state, "PID_A", 0, 0)
        self.enemy_near = _unit(self.state, "PID_B", 2, 0, faction=ENEMY)
        self.enemy_far = _unit(self.state, "PID_C", 6, 0, faction=ENEMY)

    def test_fog_off_shows_everything(self):
        self.assertEqual(len(fog.visible_tiles(self.world, self.state)), 40)
        self.assertTrue(fog.can_see(self.world, self.state, self.enemy_far))

    def test_vision_is_a_manhattan_radius_around_player_units(self):
        self.state.fog = True
        seen = fog.visible_tiles(self.world, self.state)
        self.assertEqual(seen, {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (0, 2)})
        self.assertTrue(fog.can_see(self.world, self.state, self.enemy_near, seen))
        self.assertFalse(fog.can_see(self.world, self.state, self.enemy_far, seen))
        self.assertTrue(fog.can_see(self.world, self.state, self.player, seen))


class PreparationTests(unittest.TestCase):
    def _world_with_player_section(self):
        world = _world()
        F = setup.F
        def record(pid):
            rec = [0] * 80
            rec[F["pid"]], rec[F["jid"]], rec[F["faction"]] = pid, "JID_SWORD", PLAYER
            rec[F["pos_x"]], rec[F["pos_y"]] = 1, 1
            return rec
        section = type("Section", (), {"units": [record("PID_A"), record("PID_B")]})()
        world.groups = {"Dispos_c": section}
        return world

    def test_roster_and_choice_of_deployed_units(self):
        world = self._world_with_player_section()
        self.assertEqual(setup.preparation_roster(world), ["PID_A", "PID_B"])
        state = setup.initial_state(world)
        state.deploy_only = ["PID_B"]
        sim = Simulation(world, state)
        sim.run()
        self.assertEqual([u.pid for u in sim.state.living(PLAYER)], ["PID_B"])


class SetupTests(unittest.TestCase):
    def test_generic_enemies_sharing_a_pid_are_separate_units(self):
        F = dispo.FIELD

        def record(pid, x, faction):
            r = [0] * 48
            r[F["pid"]], r[F["pos_x"]], r[F["pos2_x"]], r[F["level"]], r[F["faction"]] = pid, x, x, 1, faction
            return r

        world = _world()
        world.groups = {"enemies": dispo.DocSection("enemies", 0, [record("PID_B", 1, 1), record("PID_B", 3, 1)]),
                        "party": dispo.DocSection("party", 0, [record("PID_A", 5, 0)])}
        state = GameState()
        setup.deploy(world, state, "enemies")
        self.assertEqual(sorted(u.tile for u in state.living()), [(1, 0), (3, 0)])
        setup.deploy(world, state, "party")
        setup.deploy(world, state, "party")  # a player character is reused, not duplicated
        self.assertEqual(sum(1 for u in state.living() if u.pid == "PID_A"), 1)

    def test_make_unit_applies_bonuses_and_items(self):
        world = _world()
        record = [0] * 48
        F = dispo.FIELD
        record[F["pid"]], record[F["jid"]] = "PID_A", 0
        record[F["item0"]] = "IID_SWORD"
        record[F["bonus_str"]] = 3
        record[F["pos_x"]], record[F["pos_y"]] = 2, 3
        record[F["level"]] = 1
        record[F["faction"]] = 1
        unit = setup.make_unit(world, record, "g")
        self.assertEqual(unit.stats[1], 5 + 3)
        self.assertEqual(unit.items, [["IID_SWORD", 40, False]])
        self.assertEqual((unit.x, unit.y, unit.faction), (2, 3, 1))


if __name__ == "__main__":
    unittest.main()
