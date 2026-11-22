"""The Chapters › Roster tab's model (``chapter_roster``) and the Path of Radiance
deployment rules it relies on in the playthrough simulator (``playthrough.setup``).

Synthetic: no game data needed. With ``FE9_EXTRACTED_FILES`` set, the roster of a
vanilla chapter is applied and checked on a copy of its files."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import chapter_roster as cr  # noqa: E402
from fe_modding.formats import dispo, fe8data, lz10, message, pak  # noqa: E402
from fe_modding.formats.cmb import compile_source, read_cmb, write_cmb  # noqa: E402
from fe_modding.playthrough import natives, setup  # noqa: E402
from fe_modding.playthrough.simulation import Simulation  # noqa: E402
from fe_modding.playthrough.state import PLAYER, GameState  # noqa: E402
from fe_modding.playthrough.world import World  # noqa: E402

from dispo_fixture import build_minimal_dispo_bytes  # noqa: E402

F = dispo.FIELD
PIDS = ("PID_IKE", "PID_LUKE", "PID_CHROM", "PID_LISSA", "PID_VADER")


def _fe8():
    cls = fe8data.ClassEntry(
        index=0, offset=0, jid="JID_SWORD", mjid=None, hybrid_id=None, promotes_to=None, aid=None, movement=5,
        stat_caps=[60] + [30] * 7, base_stats=[20, 5, 0, 5, 5, 0, 3, 0], growths=[50] * 8, movement_type=1,
        weapon_ranks="D--------", skills=[], raw=b"", build=5, categories=[])
    characters = [fe8data.CharacterEntry(
        index=0, offset=0, pid=pid, fid=None, jid="JID_SWORD", sids=[], aid_unpromoted=None, aid_promoted=None,
        level=1, build=0, weight=0, stat_bonus=[0] * 8, growth=[50] * 8, fixed_growth_start=[0] * 8)
        for pid in PIDS]
    return fe8data.Fe8Data(characters=characters, classes=[cls], items=[], skills=[])


def _record(pid, x, y, flags=0):
    record = [0] * 48
    record[F["pid"]], record[F["level"]], record[F["flags"]] = pid, 1, flags
    record[F["pos_x"]] = record[F["pos2_x"]] = x
    record[F["pos_y"]] = record[F["pos2_y"]] = y
    return record


def _world(groups, scripts=()):
    world = World(width=10, height=10, terrain=[["平地"] * 10 for _ in range(10)],
                  terrain_types=[fe8data.TerrainType(0, "平地", "MT", 0, avoid=0, defense=0, heal=0,
                                                      move_costs=tuple([1] * 15))],
                  fe8=_fe8(), scripts=list(scripts))
    world.groups = {name: dispo.DocSection(name, 0, records) for name, records in groups.items()}
    return world


def _on_map(state):
    return {u.pid: u.tile for u in state.living(PLAYER)}


class ArmyRuleTests(unittest.TestCase):
    """main.dol 0x8010764c (``_mikata_``) and 0x80107468 (any other name)."""

    def test_new_save_places_the_listed_characters(self):
        world = _world({"bmap34_mikata_c": [_record("PID_LUKE", 1, 1), _record("PID_LISSA", 2, 1)]})
        state = setup.initial_state(world)
        setup.deploy(world, state, "bmap34_mikata_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_LUKE": (1, 1), "PID_LISSA": (2, 1)})

    def test_army_group_takes_the_reserve_in_order_not_the_listed_character(self):
        # The black screen of a duel chapter: Chrom, first of the reserve, takes Luke's tile.
        world = _world({"bmap35_mikata_c": [_record("PID_LUKE", 4, 4)]})
        state = setup.initial_state(world, army=("PID_IKE", "PID_CHROM", "PID_LUKE"))
        setup.deploy(world, state, "bmap35_mikata_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_CHROM": (4, 4)})

    def test_absent_character_is_created_only_with_the_flag_and_still_waits(self):
        world = _world({"g_mikata_c": [_record("PID_VADER", 4, 4)],
                        "f_mikata_c": [_record("PID_VADER", 4, 4, dispo.FLAG_SPAWN_WHEN_ABSENT)]})
        state = setup.initial_state(world, army=("PID_CHROM",))
        setup.deploy(world, state, "g_mikata_c", animate=False)
        self.assertIsNone(state.unit_by_pid("PID_VADER"))
        state = setup.initial_state(world, army=("PID_CHROM",))
        setup.deploy(world, state, "f_mikata_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_CHROM": (4, 4)})
        self.assertEqual(setup.force_of(state.unit_by_pid("PID_VADER")), 5)

    def test_ike_keeps_his_tile_and_is_skipped_by_the_other_slots(self):
        world = _world({"g_mikata_c": [_record("PID_LUKE", 1, 1), _record("PID_IKE", 2, 2)]})
        state = setup.initial_state(world, army=("PID_IKE", "PID_CHROM"))
        setup.deploy(world, state, "g_mikata_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_CHROM": (1, 1), "PID_IKE": (2, 2)})

    def test_empty_reserve_leaves_the_slot_empty(self):
        world = _world({"g_mikata_c": [_record("PID_LUKE", 1, 1), _record("PID_LISSA", 2, 2)]})
        state = setup.initial_state(world, army=("PID_CHROM",))
        setup.deploy(world, state, "g_mikata_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_CHROM": (1, 1)})
        self.assertTrue(any("no reserve unit" in o.text for o in state.out))

    def test_direct_group_places_the_listed_character_from_the_reserve(self):
        world = _world({"bmap35_avatar_c": [_record("PID_LUKE", 4, 4)]})
        state = setup.initial_state(world, army=("PID_IKE", "PID_CHROM", "PID_LUKE"))
        setup.deploy(world, state, "bmap35_avatar_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_LUKE": (4, 4)})
        self.assertEqual(len(state.units), 3)  # reused, not created

    def test_force_seven_is_out_of_the_army_until_named(self):
        world = _world({"g_avatar_c": [_record("PID_CHROM", 3, 3)], "g_mikata_c": [_record("PID_LUKE", 1, 1)]})
        state = setup.initial_state(world, army=("PID_CHROM", "PID_LUKE"))
        chrom = state.unit_by_pid("PID_CHROM")
        natives.handler(world, "UnitTransferToForce")(_Vm(world, state), [chrom.uid, 7])
        self.assertEqual(setup.force_of(chrom), 7)
        self.assertNotIn(chrom, setup.force_members(state, 5))
        setup.deploy(world, state, "g_mikata_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_LUKE": (1, 1)})
        setup.deploy(world, state, "g_avatar_c", animate=False)
        self.assertEqual(_on_map(state), {"PID_LUKE": (1, 1), "PID_CHROM": (3, 3)})

    def test_dead_character_is_not_placed_again(self):
        world = _world({"g_avatar_c": [_record("PID_LUKE", 4, 4)]})
        state = setup.initial_state(world, army=("PID_LUKE",))
        state.unit_by_pid("PID_LUKE").dead = True
        setup.deploy(world, state, "g_avatar_c", animate=False)
        self.assertEqual(_on_map(state), {})

    def test_rule_is_path_of_radiance_only(self):
        world = _world({"g_mikata_c": [_record("PID_LUKE", 1, 1)]})
        world.dialect = type(world.dialect)(**{**world.dialect.__dict__, "name": "fe10"})
        self.assertFalse(setup.is_army_group(world, "g_mikata_c"))

    def test_opening_with_set_aside_block_leaves_only_the_team(self):
        source = ("@export\ndef Opening0():\n"
                  '    InstantDisposFirst("bmap35_avatar_c")\n'
                  + "\n".join(cr.set_aside_block("    ", ["PID_LUKE"])) + "\n"
                  "    pass\n")
        world = _world({"bmap35_avatar_c": [_record("PID_LUKE", 4, 4)],
                        "extra_c": [_record("PID_CHROM", 5, 5)]},
                       scripts=[compile_source(source).script])
        state = setup.initial_state(world, army=("PID_CHROM", "PID_LUKE"), deploy_groups=("extra_c",))
        self.assertIn("PID_CHROM", _on_map(state))
        scenario = cr.play_to_first_turn(world, ["PID_CHROM", "PID_LUKE"])
        self.assertEqual(scenario.error, "")
        self.assertEqual([pid for pid, _x, _y in scenario.on_map], ["PID_LUKE"])

    def test_first_turn_report_of_an_army_group(self):
        source = '@export\ndef Opening0():\n    InstantDisposFirst("bmap35_mikata_c")\n'
        world = _world({"bmap35_mikata_c": [_record("PID_LUKE", 4, 4)]}, scripts=[compile_source(source).script])
        fresh = cr.play_to_first_turn(world, [])
        full = cr.play_to_first_turn(world, ["PID_IKE", "PID_CHROM", "PID_LUKE"], groups={"bmap35_mikata_c"})
        self.assertEqual(fresh.on_map, [("PID_LUKE", 4, 4)])
        self.assertEqual(full.on_map, [("PID_CHROM", 4, 4)])
        self.assertTrue(any("takes the slot" in line for line in full.log))


class _Vm:
    def __init__(self, world, state):
        self.world, self.state = world, state


SCRIPT = '''@export
def Opening0():
    Fade(1, 0)
    MapLoad("bmap35")
    InstantDisposFirst("bmap35_mikata_c")
    Fade(2, 500)

@on_complete(flag="gf_complete")
def func_1():
    WaitM(250)
    set("gf_complete")
'''

STARTUP = '''@export
def UnitTransferToForceByPID(pid, force):
    UnitTransferToForce(UnitGetByPID(pid), force)
'''


def _project(tmp):
    from fe_modding.games import Game
    from fe_modding.project import ModProject

    project = ModProject.create(Path(tmp), "roster test", Game.PATH_OF_RADIANCE)
    files = project.extracted_dir / "files"
    for folder in ("Scripts", "Mess", "zmap/bmap35"):
        (files / folder).mkdir(parents=True, exist_ok=True)
    (files / "Mess" / "c35.m").write_bytes(message.write_messages([]))
    (files / "Scripts" / "startup.cmb").write_bytes(write_cmb(compile_source(STARTUP).script))
    (files / "Scripts" / "C35.cmb").write_bytes(write_cmb(compile_source(SCRIPT).script))
    documents = []
    for letter in "cnhm":
        document = dispo.parse_dispo(build_minimal_dispo_bytes((f"bmap35_mikata_{letter}".encode(),
                                                                f"bmap35_first_{letter}".encode())))
        for section in document.sections:
            for unit in section.units:
                unit[F["pid"]] = "PID_LUKE" if "mikata" in section.name else "PID_ZAKO"
                unit[F["faction"]] = 0 if "mikata" in section.name else 1
                unit[F["pos_x"]] = unit[F["pos2_x"]] = 4
        documents.append((f"dispos_{letter}.bin", dispo.build_dispo(document)))
    (files / "zmap/bmap35/dispos.cmp").write_bytes(lz10.compress(pak.pack_pak(documents)))
    return project


class RosterFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _project(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_the_team_group_the_script_deploys(self):
        roster = cr.read_roster(self.project, "35")
        self.assertEqual((roster.mode, roster.groups, roster.team), (cr.ARMY, ["bmap35_mikata_c"], ["PID_LUKE"]))
        self.assertFalse(roster.set_aside)

    def test_fixed_team_renames_the_group_and_its_calls(self):
        roster = cr.read_roster(self.project, "35")
        roster.mode = cr.FIXED
        roster.members = [cr.Member("PID_LUKE", 4, 4), cr.Member("PID_VADER", 6, 2)]
        roster.set_aside = True
        roster.joins, roster.leaves = ["PID_LISSA"], ["PID_CHROM"]
        plan = cr.apply_roster(self.project, roster)
        self.assertIn('InstantDisposFirst("bmap35_avatar_c")', plan.source)
        self.assertNotIn("bmap35_mikata_c", plan.source)
        again = cr.read_roster(self.project, "35")
        self.assertEqual((again.mode, again.groups), (cr.FIXED, ["bmap35_avatar_c"]))
        self.assertEqual([(m.pid, m.x, m.y) for m in again.members], [("PID_LUKE", 4, 4), ("PID_VADER", 6, 2)])
        self.assertEqual((again.set_aside, again.joins, again.leaves), (True, ["PID_LISSA"], ["PID_CHROM"]))
        sections = cr._sections(cr.read_documents((self.project.extracted_dir / "files/zmap/bmap35/dispos.cmp")
                                                  .read_bytes())[1].values())
        self.assertIn("bmap35_mikata_n", sections)  # the difficulty groups the script doesn't use stay
        self.assertEqual([u[F["pid"]] for u in sections[again.join_group].units], ["PID_LISSA"])
        lines = plan.source.splitlines()
        deploy = lines.index('    InstantDisposFirst("bmap35_avatar_c")')
        self.assertTrue(lines[deploy + 1].strip().startswith(cr.BLOCK_START))
        complete = next(i for i, line in enumerate(lines) if line.startswith("def func_1"))
        self.assertEqual(lines[complete + 2:complete + 4],
                         ['    Join("bmap35_roster_join_c")', '    UnitTransferToForceByPID("PID_CHROM", 7)'])

    def test_applying_twice_changes_nothing_and_army_mode_undoes_it(self):
        roster = cr.read_roster(self.project, "35")
        roster.mode, roster.set_aside, roster.leaves = cr.FIXED, True, ["PID_CHROM"]
        first = cr.apply_roster(self.project, roster).source
        self.assertEqual(cr.apply_roster(self.project, cr.read_roster(self.project, "35")).source, first)
        back = cr.read_roster(self.project, "35")
        back.mode, back.set_aside, back.leaves = cr.ARMY, False, []
        source = cr.apply_roster(self.project, back).source
        self.assertNotIn(cr.BLOCK_START, source)
        self.assertIn('InstantDisposFirst("bmap35_mikata_c")', source)
        self.assertEqual(cr.read_roster(self.project, "35").groups, ["bmap35_mikata_c"])

    def test_refusals(self):
        roster = cr.read_roster(self.project, "35")
        roster.set_aside = True  # army mode
        with self.assertRaisesRegex(cr.RosterError, "fixed team"):
            cr.plan_roster(self.project, roster)
        roster.set_aside, roster.members = False, []
        with self.assertRaisesRegex(cr.RosterError, "empty"):
            cr.plan_roster(self.project, roster)
        roster.members = [cr.Member("PID_LUKE", 1, 1)] * 2
        with self.assertRaisesRegex(cr.RosterError, "twice"):
            cr.plan_roster(self.project, roster)

    def test_check_warns_about_a_call_to_the_old_group_name(self):
        roster = cr.read_roster(self.project, "35")
        roster.mode = cr.FIXED
        cr.apply_roster(self.project, roster)
        path = self.project.extracted_dir / "files/Scripts/C35.cmb"
        source = SCRIPT.replace("def func_1():", 'def func_1():\n    InstantDispos("bmap35_mikata_c")')
        path.write_bytes(write_cmb(compile_source(source, base=read_cmb(path.read_bytes())).script))
        sidecar = self.project.directory / "script_sources" / "C35.fe9s"
        if sidecar.exists():
            sidecar.unlink()
        report = cr.check_roster(self.project, "35", army=[])
        self.assertTrue(any("calls that group bmap35_avatar_c" in w for w in report.warnings), report.warnings)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted POR files/ directory")
class VanillaRosterTests(unittest.TestCase):
    def test_chapter_five_fixed_team_on_both_saves(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        source = Path(os.environ["FE9_EXTRACTED_FILES"])
        with tempfile.TemporaryDirectory() as tmp:
            project = ModProject.create(Path(tmp), "roster", Game.PATH_OF_RADIANCE)
            files = project.extracted_dir / "files"
            for folder in ("Scripts", "Mess"):
                (files / folder).mkdir(parents=True, exist_ok=True)
            for chapter in ("01", "02", "03", "04", "05"):
                shutil.copytree(source / "zmap" / f"bmap{chapter}", files / "zmap" / f"bmap{chapter}")
                shutil.copy(source / "Scripts" / f"C{chapter}.cmb", files / "Scripts")
                shutil.copy(source / "Mess" / f"c{chapter}.m", files / "Mess")
            for name in ("FE8Data.bin", "cp_data.bin"):
                shutil.copy(source / name, files / name)
            shutil.copy(source / "Scripts" / "startup.cmb", files / "Scripts")
            shutil.copy(source / "Mess" / "common.m", files / "Mess")

            roster = cr.read_roster(project, "05")
            self.assertEqual((roster.mode, roster.groups), (cr.ARMY, ["bmap05_mikata_c"]))
            roster.mode, roster.set_aside = cr.FIXED, True
            roster.members = [cr.Member("PID_IKE", 18, 11), cr.Member("PID_MARCIA", 18, 12)]
            cr.apply_roster(project, roster)
            report = cr.check_roster(project, "05")
            self.assertEqual(len(report.scenarios), 2)
            for scenario in report.scenarios:
                self.assertEqual(scenario.error, "")
                self.assertEqual(sorted(pid for pid, _x, _y in scenario.on_map), ["PID_IKE", "PID_MARCIA"])
            self.assertFalse([w for w in report.warnings if "not on the map" in w or "not in the team" in w])


if __name__ == "__main__":
    unittest.main()
