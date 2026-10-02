import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk  # noqa: E402

import test_playthrough as T  # noqa: E402
from fe_modding.formats import cp_data, dispo, map_file, message  # noqa: E402
from fe_modding.formats.cmb.binary import write_cmb  # noqa: E402
from fe_modding.playthrough import actions  # noqa: E402

SOURCE = '''
@export
def Startup():
    regist("visited")
    InstantDispos("bmap01_enemy")
    InstantDispos("bmap01_mikata_c")

@on_location(x=4, y=4, action="visit", name=None)
def village():
    set("visited")
    TalkEvent("MS_01_VISIT")
'''


def _record(pid, x, y, faction, ai=False):
    F = dispo.FIELD
    r = [0] * 48
    r[F["pid"]], r[F["item0"]], r[F["level"]], r[F["faction"]] = pid, "IID_SWORD", 1, faction
    r[F["pos_x"]] = r[F["pos2_x"]] = x
    r[F["pos_y"]] = r[F["pos2_y"]] = y
    if ai:
        r[F["seq_attack"]], r[F["seq_move"]] = "SEQ_ATK", "SEQ_MOV"
    return r


class PlaythroughWindowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.root.withdraw()
        tmp = Path(tempfile.mkdtemp())
        files = tmp / "files"
        (files / "Scripts").mkdir(parents=True)
        (files / "Mess").mkdir()
        (files / "Scripts" / "C01.cmb").write_bytes(write_cmb(T._script(SOURCE)))
        cp = T._cp({"SEQ_ATK": "attack(chance=100)\nif found: goto L99\nL99:\nend()\n",
                    "SEQ_MOV": "move_nearest()\nend()\n"})
        (files / "cp_data.bin").write_bytes(cp_data.build_cp_data(cp))
        (files / "Mess" / "c01.m").write_bytes(message.write_messages([message.Message("MS_01_VISIT", "Hi.$K")]))
        data = map_file.MapData(capacity=map_file.MapCapacity(x_size=12, y_size=10, build_desc_count=0,
                                                              build_inst_count=0, scale_unit=1))
        grid = [[T.PLAIN] * 10 for _ in range(12)]
        doc = dispo.DispoDocument(
            sections=[dispo.DocSection("bmap01_mikata_c", 0, [_record("PID_RIDER", 2, 1, 0)]),
                      dispo.DocSection("bmap01_enemy", 0, [_record("PID_B", 5, 4, 1, ai=True)])],
            table_order=[], name_offsets=[], names_blob=b"", labels=[], header_tail=b"")
        builder = tk.Frame(self.root)
        builder.map_editor = types.SimpleNamespace(map_data=data, terrain_grid=grid, terrain_types=T.TERRAIN,
                                                   map_name="bmap01", add_listener=lambda f: None,
                                                   remove_listener=lambda f: None)
        builder._deploy = types.SimpleNamespace(variants=lambda: ["dispos_c.bin"], document=lambda v: doc)
        builder._script = types.SimpleNamespace(chapter_path=files / "Scripts" / "C01.cmb",
                                                chapter_source=lambda: None, dirty=False)
        builder._project = types.SimpleNamespace(extracted_dir=tmp)
        builder._session_provider = lambda: types.SimpleNamespace(fe8=T._fe8())
        builder._index_provider = lambda: None
        builder._backdrop = None
        builder.undo = builder.redo = lambda: None
        from fe_modding.gui.playthrough_window import PlaythroughWindow

        self.window = PlaythroughWindow(builder)
        self.window.withdraw()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def _settle(self):
        import time

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            self.root.update()
            if self.window.sim is not None and self.window._running is None and self.window.sim.needs_input:
                return
            time.sleep(0.01)

    def test_opening_runs_to_the_player_phase_and_a_command_plays_on(self):
        w = self.window
        self._settle()  # the window starts the chapter itself
        state = w.sim.state
        self.assertEqual([u.pid for u in state.living()], ["PID_B", "PID_RIDER"])
        rider = next(u for u in state.living() if u.pid == "PID_RIDER")
        w._command(actions.Act(rider.uid, (4, 4), "visit"))  # stops on the message page
        self.root.update()
        self.assertTrue(w.sim.state.get_flag("visited"))
        self.assertIn("Hi.", w._message_label.cget("text"))
        w.run()  # past the message
        self._settle()
        w.end_phase()
        self._settle()
        self.assertEqual(w.sim.state.turn, 2)
        self.assertLess(w.sim.state.units[rider.uid].hp, 20)  # the enemy attacked
        w.back_command()
        self.assertFalse(w.sim.at_end)


if __name__ == "__main__":
    unittest.main()
