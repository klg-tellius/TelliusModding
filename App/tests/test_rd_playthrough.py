"""The in-app playthrough on Radiant Dawn (RFEE01) scripts: FE10 natives, opcodes and stopping cleanly.

The corpus tests need ``FE10_EXTRACTED_FILES`` (an extracted RD ``files/`` directory)."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_playthrough as T  # noqa: E402
from fe_modding.formats import dispo, lz10, map_file, pak  # noqa: E402
from fe_modding.formats.cmb import compile_source  # noqa: E402
from fe_modding.formats.cmb.binary import read_cmb_path  # noqa: E402
from fe_modding.formats.cmb.model import FE10  # noqa: E402
from fe_modding.game_profile import RADIANT_DAWN_PROFILE  # noqa: E402
from fe_modding.playthrough import actions, engine, loader, natives, setup  # noqa: E402
from fe_modding.playthrough.dialect import dialect_for  # noqa: E402
from fe_modding.playthrough.simulation import INPUT, Simulation  # noqa: E402
from fe_modding.playthrough.state import PLAYER, GameState, SimUnit  # noqa: E402
from fe_modding.playthrough.world import World  # noqa: E402

FILES = Path(os.environ.get("FE10_EXTRACTED_FILES", ""))


def _world(source: str) -> World:
    grid = [[T.PLAIN] * 8 for _ in range(8)]
    return World(width=8, height=8, terrain=grid, terrain_types=T.TERRAIN, fe8=T._fe8(),
                 scripts=[compile_source(source, dialect=FE10).script], dialect=dialect_for("fe10"))


def _vm(state=None, world=None):
    world = world or SimpleNamespace(dialect=dialect_for("fe10"), groups={}, difficulty="n", names={},
                                     name=lambda pid: pid)
    return SimpleNamespace(state=state or GameState(), world=world, ctx={}, inserted=[],
                           insert=lambda *tasks: None)


def _call(vm, name, *args):
    return natives.handler(vm.world, name)(vm, list(args))


class Fe10ScriptRuntimeTests(unittest.TestCase):
    def test_assign_inc_dec_and_the_frame_clock(self):
        world = _world('''
@export
def Startup():
    var v0
    v0 = 0
    while v0 < 30:
        v0++
        yield
    v0--
    regist("counted")
    regist("timed")
    if v0 == 29:
        set("counted")
    if GetTime() == 500:
        set("timed")
''')
        sim = Simulation(world, setup.initial_state(world))
        sim.run(INPUT)
        self.assertTrue(sim.state.get_flag("counted"))
        self.assertTrue(sim.state.get_flag("timed"))  # 30 frames = 500 ms
        self.assertEqual(sim.state.frame, 30)

    def test_a_runtime_error_stops_the_run_with_its_reason(self):
        world = _world("@export\ndef Startup():\n    g0 = 1\n")
        sim = Simulation(world, setup.initial_state(world))
        original = engine.step

        def failing(world, state):
            raise RuntimeError("Unsupported state-changing RFEE01 native: Mystery()")

        engine.step = failing
        try:
            steps = sim.run(INPUT)
        finally:
            engine.step = original
        self.assertEqual(steps[-1].kind, "over")
        self.assertEqual(sim.state.over, "stopped")
        self.assertTrue(any("Mystery()" in o.text for o in sim.entry.outputs))
        self.assertEqual(sim.run(INPUT), [])  # nothing more to play


class Fe10NativeTests(unittest.TestCase):
    def test_build_switches_and_unknown_names(self):
        vm = _vm()
        self.assertEqual(_call(vm, "IsFinalVersion"), 1)
        self.assertEqual(_call(vm, "IsJPVersion"), 0)
        self.assertEqual(natives.classification(vm.world, "RegistLocationTT"), "presentation")
        with self.assertRaises(RuntimeError):
            natives.unmodelled(vm, "UntracedMutation", [])

    def test_rank_group_picks_the_difficulty_entry(self):
        world = SimpleNamespace(dialect=dialect_for("fe10"), groups={"bmap0101_teki_n": object()}, difficulty="n")
        vm = _vm(world=world)
        self.assertEqual(_call(vm, "DisposGetRankGroup", "bmap0101_teki"), "bmap0101_teki_n")
        self.assertEqual(_call(vm, "DisposGetRankGroup", "bmap0101_mikata"), "")

    def test_units_push_and_pop_restore_the_chapter_units(self):
        state = GameState()
        hero = state.add_unit(SimUnit(0, "PID_IKE", "JID_HERO", PLAYER, 1, 1))
        vm = _vm(state)
        _call(vm, "UnitsPush_Uninitialize")
        state.units[hero.uid].x = 5
        state.add_unit(SimUnit(0, "PID_EXTRA", "JID_SOLDIER", 1, 2, 2))
        _call(vm, "UnitsPop")
        self.assertEqual([(u.pid, u.x) for u in state.units.values()], [("PID_IKE", 1)])

    def test_all_push_clears_chapter_flags_and_all_pop_restores_them(self):
        state = GameState(flags=[[f"f{i}", i in (3, 40)] for i in range(128)])
        state.add_unit(SimUnit(0, "PID_IKE", "JID_HERO", PLAYER, 1, 1))
        vm = _vm(state)
        _call(vm, "AllPush")
        self.assertEqual(state.units, {})
        self.assertTrue(state.flags[3][1])  # a global flag stays
        self.assertFalse(state.flags[40][1])  # a chapter flag is reset
        _call(vm, "AllPop")
        self.assertTrue(state.flags[40][1])
        self.assertEqual(len(state.units), 1)

    def test_rescue_and_drop_off(self):
        state = GameState()
        carrier = state.add_unit(SimUnit(0, "PID_A", "JID", PLAYER, 3, 3))
        carried = state.add_unit(SimUnit(0, "PID_B", "JID", PLAYER, 4, 3))
        world = SimpleNamespace(dialect=dialect_for("fe10"), width=8, height=8, names={}, name=lambda p: p,
                                inside=lambda x, y: 0 <= x < 8 and 0 <= y < 8, move_cost=lambda x, y, m: 1)
        vm = _vm(state, world)
        self.assertEqual(_call(vm, "UnitRescue", carrier.uid, carried.uid), 1)
        self.assertEqual(_call(vm, "UnitGetParent", carried.uid), carrier.uid)
        self.assertEqual(_call(vm, "UnitTstStatus", carrier.uid, 0x2), 0x2)
        _call(vm, "UnitDropOff", carrier.uid, 8)
        self.assertEqual((carried.on_map, carried.tile), (True, (3, 2)))
        self.assertIsNone(carrier.rescue_partner)


def _chapter_world(chapter: str) -> World:
    folder = FILES / "zmap" / ("bmap" + chapter[1:])
    raw = lz10.decompress((folder / "map.cmp").read_bytes())
    contents = {e.name: pak.read_pak_file_content(raw, e) for e in pak.read_pak_entries(raw)}
    documents = [dispo.parse_dispo(p.read_bytes()) for p in sorted(folder.glob("dispos_*.bin"))]
    return loader.load_world(FILES, map_data=map_file.read_map_bytes(contents["map.bin"]),
                             terrain_grid=map_file.terrain_grid(contents["map.bin"]), terrain_types=[],
                             documents=documents, profile=RADIANT_DAWN_PROFILE,
                             script=read_cmb_path(FILES / "Scripts" / f"{chapter}.cmb"), chapter_stem=chapter)


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"), "set FE10_EXTRACTED_FILES to an extracted RD files/ directory")
class Fe10CorpusPlaythroughTests(unittest.TestCase):
    def test_no_chapter_script_calls_an_unclassified_native(self):
        startup = read_cmb_path(FILES / "Scripts" / "startup.cmb")
        chapters = sorted((FILES / "Scripts").glob("C*.cmb"))
        self.assertEqual(len(chapters), 44)
        found = {}
        for path in chapters:
            world = SimpleNamespace(scripts=[read_cmb_path(path), startup], dialect=dialect_for("fe10"))
            for name in natives.audit_scripts(world)["unclassified"]:
                found.setdefault(name, []).append(path.stem)
        self.assertEqual(found, {})

    def test_chapter_openings_reach_the_first_player_phase(self):
        for chapter in ("C0101", "C0204"):
            with self.subTest(chapter=chapter):
                world = _chapter_world(chapter)
                sim = Simulation(world, setup.initial_state(world))
                sim.run(INPUT)
                state = sim.state
                self.assertEqual(state.over, "")
                self.assertTrue(sim.needs_input)
                self.assertEqual((state.turn, state.phase), (1, PLAYER))
                self.assertTrue(state.living(PLAYER))
                self.assertTrue(state.living(1))
                sim.command(actions.EndPhase())  # the enemy and partner phases play, then turn 2
                sim.run(INPUT)
                self.assertEqual(sim.state.over, "")
                self.assertEqual((sim.state.turn, sim.state.phase), (2, PLAYER))
                self.assertTrue(sim.needs_input)


if __name__ == "__main__":
    unittest.main()
