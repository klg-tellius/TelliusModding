import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import cp_ai_lang, cp_data, dispo, fe8data  # noqa: E402
from fe_modding.formats.cmb.compiler import compile_source  # noqa: E402
from fe_modding.playthrough import actions, ai_vm, movement, setup  # noqa: E402
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

    def test_unreachable_destination_rejected(self):
        a = _unit(self.state, "PID_A", 0, 0)
        with self.assertRaises(actions.CommandError):
            actions.apply(self.world, self.state, actions.Act(a.uid, (7, 7)))


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


class SetupTests(unittest.TestCase):
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
