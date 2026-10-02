import os
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import numpy as np

    from fe_modding.gui import battle_stage
    from fe_modding.gui.model_viewer import _skin_triangles, _Triangle, _VertexSkin
except ImportError as exc:  # tkinter or numpy missing
    battle_stage = None
    REASON = str(exc)

from fe_modding.battle_sim import FixedOutcomes, simulate
from fe_modding.battle_sim import scene_assets as sa
from fe_modding.battle_sim.units import Combatant, Weapon


def _matrix(rng):
    return [[rng.uniform(-1, 1) for _ in range(4)] for _ in range(3)]


@unittest.skipIf(battle_stage is None, "needs tkinter and numpy")
class SkinnedMeshTests(unittest.TestCase):
    def test_matches_model_viewer_skinning(self):
        rng = random.Random(3)
        bones = 6
        tris = []
        for i in range(40):
            def skin():
                count = rng.randint(1, 3)
                idx = tuple(rng.randint(-1, bones) for _ in range(count))  # some out of range
                return _VertexSkin(idx, tuple(rng.uniform(0.1, 1) for _ in range(count)), rng.random() < 0.5)

            point = lambda: tuple(rng.uniform(-5, 5) for _ in range(3))
            tris.append(_Triangle(point(), point(), point(), (0.0, 1.0, 0.0), (200, 100, 50),
                                  None if i % 7 == 0 else (skin(), skin(), skin())))
        world = [_matrix(rng) for _ in range(bones)]
        palette = [_matrix(rng) for _ in range(bones)]
        expected = _skin_triangles(tris, world, palette)
        positions, normals = battle_stage.SkinnedMesh(tris).pose(world, palette)
        for e, p, n in zip(expected, positions, normals):
            np.testing.assert_allclose(p, [e.a, e.b, e.c], atol=1e-9)
            np.testing.assert_allclose(n, e.normal, atol=1e-9)

    def test_stage_frame(self):
        tri = _Triangle((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 1.0), (1, 2, 3),
                        (_VertexSkin((0,), (1.0,)),) * 3)

        class Loaded:
            bones = []
            triangles = [tri]

        units = []
        for _ in (0, 1):
            u = battle_stage.StageUnit(sa.UnitAssets(code="fig1"))
            u.loaded, u.mesh, u.height = Loaded(), battle_stage.SkinnedMesh([tri]), 2.0
            units.append(u)
        stage = battle_stage.BattleStage(units)
        self.assertAlmostEqual(stage.spacing, 2.4)
        sword = Weapon("IID_IRONSWORD", "sword", "sword", might=5, hit=100)
        log = simulate(Combatant("A", weapon=sword), Combatant("B", weapon=sword), outcomes=FixedOutcomes())
        stage.set_log(log)
        frame = stage.frame(0.0)
        self.assertEqual(len(frame), 2)
        self.assertAlmostEqual(frame[0].a[2], -1.2)
        self.assertAlmostEqual(frame[1].a[2], 1.2)
        self.assertAlmostEqual(frame[1].b[0], -1.0)  # turned to face the attacker
        self.assertEqual(len(stage.timeline.changes), 2)


@unittest.skipIf(battle_stage is None, "needs tkinter and numpy")
class StageExtrasTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.battle_sim import timeline as tlm
        self.tlm = tlm
        tri = _Triangle((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 1.0), (1, 2, 3))

        class Loaded:
            bones = []
            triangles = [tri]
            animations = []

        self.loaded = Loaded()
        units = []
        for _ in (0, 1):
            u = battle_stage.StageUnit(sa.UnitAssets(code="fig1"))
            u.loaded, u.mesh, u.height = Loaded(), battle_stage.SkinnedMesh([tri]), 2.0
            units.append(u)
        effect = battle_stage.EffectAsset(Loaded(), battle_stage.SkinnedMesh([tri]), None, 10.0)
        self.stage = battle_stage.BattleStage(units, effects=lambda kind, key: effect if key == "sol" else None)

    def test_effects_and_projectiles(self):
        tl = self.tlm.Timeline(hp_start=(10, 10), length=100)
        tl.cues = [self.tlm.Cue(20, 1, "skill", "sol"), self.tlm.Cue(20, 0, "skill", "luna")]
        tl.flights = [self.tlm.Flight(40, 60, 0)]
        self.stage.timeline = tl
        self.assertEqual(len(self.stage.frame(10)), 2)
        with_effect = self.stage.frame(25)
        self.assertEqual(len(with_effect), 3)  # luna has no pack: skipped
        self.assertAlmostEqual(with_effect[2].a[2], 1.2)  # on the defender's spot
        self.assertEqual(len(self.stage.frame(31)), 2)  # past the effect's 10 frames
        flying = self.stage.frame(50)
        self.assertEqual(len(flying), 2 + 8)  # the stand-in arrow: two planes, both windings
        zs = [p[2] for t in flying[2:] for p in (t.a, t.b, t.c)]
        self.assertTrue(-1.2 < min(zs) and max(zs) < 1.2)

    def test_game_camera_view(self):
        from fe_modding.battle_sim import camera
        from fe_modding.formats import battle_camera as bc
        script = bc.read_script(bc.new_script("atk_l", "cam1", keyframes=[
            bc.Keyframe((0.0, 1.0, 0.0), (10.0, 90.0, 0.0), 40.0, 0)]))
        tl = self.tlm.Timeline(hp_start=(10, 10), length=100)
        tl.shots = [(0.0, 0, False)]
        self.stage.timeline = tl
        self.stage.frame(0)
        center, yaw, pitch, dist = self.stage.camera(camera.GameCamera({"atk_l": script}, {}), 5)
        self.assertEqual(center, (0.0, 1.0, 0.0))  # between the units, plus pos
        self.assertAlmostEqual(yaw, 1.5707963, places=5)
        self.assertEqual(dist, 40.0)
        self.assertIsNone(self.stage.camera(camera.GameCamera({}, {}), 5))


@unittest.skipIf(battle_stage is None, "needs tkinter and numpy")
class PerspectiveTests(unittest.TestCase):
    def test_far_geometry_shrinks(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        try:
            from fe_modding.gui.model_viewer import _ModelCanvas
            canvas = _ModelCanvas(root)
            near = _Triangle((-1.0, -1.0, -5.0), (1.0, -1.0, -5.0), (0.0, 1.0, -5.0), (0.0, 0.0, -1.0), (255, 0, 0))
            far = _Triangle((-1.0, -1.0, 5.0), (1.0, -1.0, 5.0), (0.0, 1.0, 5.0), (0.0, 0.0, -1.0), (0, 255, 0))
            canvas._center, canvas._extent, canvas._yaw, canvas._pitch = (0.0, 0.0, 0.0), 5.0, 0.0, 0.0

            def area(perspective, tri):
                canvas._perspective = perspective
                image = canvas._rasterize([tri], 200, 200)
                return int((image != 43).any(axis=-1).sum())

            self.assertEqual(area(0.0, near), area(0.0, far))
            self.assertGreater(area(0.1, near), area(0.1, far))
            canvas._perspective = 0.1
            behind = _Triangle((-1.0, -1.0, -20.0), (1.0, -1.0, -20.0), (0.0, 1.0, -20.0), (0.0, 0.0, -1.0),
                               (0, 0, 255))
            self.assertEqual(area(0.1, behind), 0)  # behind the eye
        finally:
            root.destroy()


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES") and battle_stage is not None,
                     "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscStageTests(unittest.TestCase):
    def test_fighter_vs_fighter_in_a_scenery(self):
        files = Path(os.environ["FE9_EXTRACTED_FILES"])
        assets = sa.BattleAssets.from_files(files)
        axe = Weapon("IID_IRONAXE", "axe", "axe", might=8, hit=75, weight=10)
        units = [Combatant("A", jid="JID_FIGHTER", weapon=axe), Combatant("B", jid="JID_FIGHTER", weapon=axe)]
        found = [assets.unit(u) for u in units]
        self.assertTrue(found[0].roles, found[0].notes)
        cache = battle_stage.SetCache()
        stage_units = [battle_stage.load_unit(cache, a) for a in found]
        scenery = next(iter(assets.sceneries().values()))
        stage = battle_stage.BattleStage(stage_units, battle_stage.load_scenery(scenery))
        log = simulate(units[0], units[1], outcomes=FixedOutcomes({(1, "crit"): True}))
        stage.set_log(log)
        self.assertIsNotNone(stage.timeline.pose(0, stage.timeline.changes[0].frame - 1)[0])
        for t in (0.0, stage.timeline.changes[0].frame, stage.timeline.length):
            self.assertGreater(len(stage.frame(t)), len(stage.scenery))


if __name__ == "__main__":
    unittest.main()
