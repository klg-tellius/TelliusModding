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
from fe_modding.battle_sim import camera, scene_assets as sa
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
        for e, n in zip(expected, normals):  # by default the model viewer's normals
            np.testing.assert_allclose(n, e.normal, atol=1e-9)
        positions, normals = battle_stage.SkinnedMesh(tris, exact_faces=True).pose(world, palette)
        for i, (e, p, n) in enumerate(zip(expected, positions, normals)):
            np.testing.assert_allclose(p, [e.a, e.b, e.c], atol=1e-9)
            # normals are the posed face's own (unit, on the face's plane)...
            self.assertAlmostEqual(float(np.linalg.norm(n)), 1.0, places=9)
            self.assertAlmostEqual(float(np.dot(n, p[1] - p[0])), 0.0, places=6)
            self.assertAlmostEqual(float(np.dot(n, p[2] - p[0])), 0.0, places=6)
            if tris[i].skin is None:  # ...turned the way the stored normal faced at rest
                self.assertGreater(float(np.dot(n, tris[i].normal)), 0.0)

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
        sword = Weapon("IID_IRONSWORD", "sword", "sword", might=5, hit=100)
        log = simulate(Combatant("A", weapon=sword), Combatant("B", weapon=sword), outcomes=FixedOutcomes())
        stage.set_log(log)
        frame = stage.frame(0.0)
        self.assertEqual(len(frame), 2)
        # the game's spots: x -20 turned +90 degrees (model +X goes to -Z), x +20 turned -90
        self.assertEqual(tuple(round(v, 6) for v in frame[0].b), (-20.0, 0.0, -1.0))
        self.assertEqual(tuple(round(v, 6) for v in frame[1].b), (20.0, 0.0, 1.0))
        self.assertEqual(len(stage.timeline.changes), 2)
        self.assertTrue(stage.changed.all())  # no scenery: every triangle can move
        positions, _normals = stage.arrays(stage.timeline.length)
        self.assertGreater(positions[0, 0, 0], -20.0)  # the attacker ran in


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

        units = []
        for _ in (0, 1):
            u = battle_stage.StageUnit(sa.UnitAssets(code="fig1"))
            u.loaded, u.mesh, u.height = Loaded(), battle_stage.SkinnedMesh([tri]), 2.0
            units.append(u)
        effect = battle_stage.EffectAsset(Loaded(), battle_stage.SkinnedMesh([tri]), None, 10.0)
        scenery = Loaded()
        self.stage = battle_stage.BattleStage(units, scenery, effects=lambda kind, key: effect if key == "sol" else None)

    def test_effects_and_projectiles(self):
        tl = self.tlm.Timeline(hp_start=(10, 10), length=100)
        tl.cues = [self.tlm.Cue(20, 1, "skill", "sol"), self.tlm.Cue(20, 0, "skill", "luna")]
        tl.flights = [self.tlm.Flight(40, 60, 0)]
        self.stage.timeline = tl
        self.stage._layout()
        self.assertEqual(list(self.stage.changed), [False, True, True] + [True] * 8 + [True])
        self.assertEqual(len(self.stage.frame(10)), 3)  # scenery and the two units
        with_effect = self.stage.frame(25)
        self.assertEqual(len(with_effect), 4)  # luna has no pack: skipped
        self.assertEqual(tuple(round(v, 6) for v in with_effect[3].a), (20.0, 0.0, 0.0))  # on the defender's spot
        self.assertEqual(len(self.stage.frame(31)), 3)  # past the effect's 10 frames
        flying = self.stage.frame(50)
        self.assertEqual(len(flying), 3 + 8)  # the stand-in arrow: two planes, both windings
        xs = [p[0] for t in flying[3:] for p in (t.a, t.b, t.c)]
        self.assertTrue(-20 < min(xs) and max(xs) < 20)

    def test_spell_travel_and_fade(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from fe_modding.formats.animation import EventKey, MaterialTrack
        tri = replace(self.stage.units[0].loaded.triangles[0], material=0)

        class Loaded:
            bones = []
            triangles = [tri]
            animations = []

        anim = SimpleNamespace(events=[EventKey(10, (0x12,)), EventKey(14, (0x13,))],
                               material_alphas=lambda: {0: MaterialTrack(0, ((0, 0), (10, 255)))})
        spell = battle_stage.EffectAsset(Loaded(), battle_stage.SkinnedMesh([tri]), anim, 30.0)
        self.assertEqual([spell.travel(f) for f in (5, 12, 14, 20)], [0.0, 0.5, 1.0, 1.0])
        self.stage.effects = lambda kind, key: spell
        tl = self.tlm.Timeline(hp_start=(10, 10), length=100)
        tl.cues = [self.tlm.Cue(20, 0, "effect", "EID_K_WIND", aim=1)]
        self.stage.timeline = tl
        self.stage._layout()
        x = lambda t: round(self.stage.frame(t)[3].a[0], 6)
        self.assertEqual((x(25), x(32), x(40)), (-20.0, 0.0, 20.0))  # from the caster to the target
        self.stage.arrays(25)
        # unlit, two-sided effect alpha: half of the track's 0 -> 255 by frame 5
        self.assertAlmostEqual(float(self.stage.alphas[3]), float(battle_stage.effect_alpha(127 / 255)), places=5)

    def test_game_camera_view(self):
        from fe_modding.battle_sim import camera
        tl = self.tlm.Timeline(hp_start=(10, 10), length=10)
        self.stage.timeline = tl
        self.stage.shots = [camera.Shot(None, (0.0, 9.0, 0.0), (0.0, 0.0, 0.0), 0.0, 180.0, 60.0)] * 11
        self.stage.arrays(5)
        eye, center = self.stage.view(5)
        self.assertEqual(center, (0.0, 9.0, 0.0))
        self.assertAlmostEqual(eye[2], 60.0)
        self.stage.shots = [camera.Shot(1, (0.0, 0.0, 0.0), (0.0, 7.0, 0.0), 0.0, 180.0, 60.0)] * 11
        self.assertEqual(self.stage.view(5)[1], (20.0, 7.0, 0.0))  # the defender's spot: no cam bone here
        self.stage.shots = None
        self.assertIsNone(self.stage.view(5))


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
            # a low camera looking up still sees the ground it stands above: faces are culled
            # against the ray from the eye, not the view axis
            ground = _Triangle((-50.0, 0.0, -60.0), (50.0, 0.0, -60.0), (0.0, 0.0, 10.0), (0.0, 1.0, 0.0),
                               (200, 200, 200))
            canvas.set_camera((0.0, 2.0, 20.0), (0.0, 4.0, 0.0), 30.0)
            self.assertGreater(int((canvas._rasterize([ground], 200, 150) != 43).any(axis=-1).sum()), 0)
            canvas.clear_camera()
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
        stage = battle_stage.BattleStage(stage_units, battle_stage.load_scenery(scenery), params=assets.battle_params())
        log = simulate(units[0], units[1], outcomes=FixedOutcomes({(1, "crit"): True}))
        stage.set_log(log, 1, camera.GameCamera.from_zdbx(assets.zdbx_data))
        self.assertIsNotNone(stage.timeline.pose(0, stage.timeline.changes[0].frame - 1)[0])
        self.assertEqual(len(stage.shots), int(stage.timeline.length) + 1)
        for t in (0.0, stage.timeline.changes[0].frame, stage.timeline.length):
            self.assertGreater(len(stage.frame(t)), len(stage.scenery))


if __name__ == "__main__":
    unittest.main()
