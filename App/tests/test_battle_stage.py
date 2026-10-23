import os
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_returning_hand_axe_spins_parallel_to_ground(self):
        # A rest-model triangle in local X/Y is the axe's blade plane.  Retail keeps that
        # plane horizontal during the throw; the previous transform mapped local Y to world
        # up and made the weapon cartwheel vertically.
        self.stage._rest = np.asarray([((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                                        (0.0, 2.0, 0.0))])
        self.stage._rest_normals = np.asarray([(0.0, 0.0, 1.0)])
        part = SimpleNamespace(side=0, start=0, count=1)
        flight = self.tlm.Flight(10.0, 30.0, 0, speed=4.5)

        positions, _normals = self.stage._returning_axe(part, flight, 15.0)

        np.testing.assert_allclose(positions[0, :, 1], positions[0, 0, 1], atol=1e-9)

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
        # The object-based/CPU rendering route keeps the same animated alpha sentinel as the
        # array/GPU route; otherwise large spells render fully opaque on machines without wgpu.
        self.assertAlmostEqual(self.stage.frame(25)[3].alpha,
                               float(battle_stage.effect_alpha(127 / 255)), places=5)

    def test_magic_fade_darkens_units_but_not_spell(self):
        self.stage.units[0].assets.weapon_effect = "sol"
        tl = self.tlm.Timeline(hp_start=(10, 10), length=100)
        tl.cues = [self.tlm.Cue(20, 0, "effect", "sol", aim=1)]
        self.stage.timeline = tl
        self.stage._layout()

        self.stage.arrays(25)
        expected = 1.0 + (60.0 / 255.0 - 1.0) * 0.25
        self.assertEqual(float(self.stage.shades[0]), 1.0)  # scenery stays bright
        self.assertAlmostEqual(float(self.stage.shades[1]), expected, places=5)
        self.assertAlmostEqual(float(self.stage.shades[2]), expected, places=5)
        self.assertEqual(float(self.stage.shades[3]), 1.0)  # spell geometry stays bright
        self.assertAlmostEqual(self.stage.frame(25)[1].shade, expected, places=5)
        self.assertEqual(self.stage.frame(25)[3].shade, 1.0)

        # This fixture's spell is only 10 ticks long, so restoration starts from
        # the partially faded value without a brightness discontinuity.
        self.stage.arrays(30)
        at_end = 1.0 + (60.0 / 255.0 - 1.0) * 0.5
        self.assertAlmostEqual(float(self.stage.shades[1]), at_end, places=5)
        self.stage.arrays(40)
        self.assertAlmostEqual(float(self.stage.shades[1]), (at_end + 1.0) / 2.0, places=5)

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

    def test_2d_effect_layer_fills_the_camera_viewport(self):
        # FE8Effect category-6 packs use an 8 x 6 authoring plane.  It must be
        # attached to the camera; placing it at the caster leaves Rexbolt's
        # sky and lightning overlay flat on the battlefield floor.
        tri = _Triangle((-4.0, 0.0, -3.0), (4.0, 0.0, -3.0),
                        (4.0, 0.0, 3.0), (0.0, 1.0, 0.0), (1, 2, 3))

        class Loaded:
            bones = []
            triangles = [tri]
            animations = []

        overlay = battle_stage.EffectAsset(
            Loaded(), battle_stage.SkinnedMesh([tri]), None, 10.0, screen_space=True)
        self.stage.effects = lambda _kind, _key: overlay
        tl = self.tlm.Timeline(hp_start=(10, 10), length=10)
        tl.cues = [self.tlm.Cue(0, 0, "effect", "EID_K_THUNDER4")]
        self.stage.timeline = tl
        self.stage.shots = [camera.Shot(None, (0.0, 9.0, 0.0), (0.0, 0.0, 0.0),
                                          0.0, 180.0, 60.0)] * 11
        self.stage._layout()

        frame = self.stage.frame(1)
        overlay_tri = frame[-1]
        half_height = (battle_stage.SCREEN_EFFECT_DEPTH
                       * np.tan(np.radians(camera.FOVY) / 2.0)
                       * battle_stage.SCREEN_EFFECT_OVERSCAN
                       * battle_stage.SCREEN_EFFECT_LAYER_OVERSCAN)
        self.assertAlmostEqual(overlay_tri.a[0], -half_height * camera.ASPECT, places=6)
        self.assertAlmostEqual(overlay_tri.b[0], half_height * camera.ASPECT, places=6)
        self.assertAlmostEqual(overlay_tri.a[1], 9.0 + half_height, places=6)
        self.assertAlmostEqual(overlay_tri.c[1], 9.0 - half_height, places=6)

        backdrop = battle_stage.EffectAsset(
            Loaded(), battle_stage.SkinnedMesh([tri]), None, 10.0, screen_space=True)
        cue = tl.cues[0]
        matrix = self.stage._effect_matrix(backdrop, cue, 1.0)
        # Local Y=-0.20 is Rexbolt's black sky plane; Y=0 is its lightning.
        # Along this camera's -Z view axis, the sky must be farther away.
        sky = matrix @ np.array((0.0, -0.20, 0.0, 1.0))
        bolt = matrix @ np.array((0.0, 0.0, 0.0, 1.0))
        self.assertLess(sky[2], bolt[2])
        bolt_top = matrix @ np.array((0.0, 0.0, -6.0, 1.0))
        bolt_later = matrix @ np.array((0.0, 0.0, -4.0, 1.0))
        self.assertGreater(bolt_top[1], bolt_later[1])  # authored motion is downward on screen
        self.assertGreater(bolt[2], 50.0)  # screen pass is in front of ordinary battle geometry

    def test_screen_backdrop_overscan_does_not_enlarge_lightning(self):
        backdrop = _Triangle((-3.2, 0.0, -3.0), (4.8, 0.0, -3.0),
                             (4.8, 0.0, 3.0), (0.0, 1.0, 0.0), (1, 2, 3), material=9)
        bolt = _Triangle((-1.5, 0.0, -7.0), (1.5, 0.0, -7.0),
                         (1.5, 0.0, -1.0), (0.0, 1.0, 0.0), (1, 2, 3), material=10)

        class Loaded:
            label = "EID_K_THUNDER4_2D"
            bones = []
            animations = []
            triangles = [backdrop, bolt]

        effect = battle_stage.EffectAsset(
            Loaded(), battle_stage.SkinnedMesh(Loaded.triangles), None, 10.0, screen_space=True)
        positions = effect.mesh.positions.copy()
        covered = self.stage._cover_screen_effect_layers(effect, positions)

        self.assertAlmostEqual(float(covered[0, :, 0].min()), -4.2)
        self.assertAlmostEqual(float(covered[0, :, 0].max()), 5.8)
        np.testing.assert_allclose(covered[1], positions[1])

        self.stage.effects = lambda _kind, _key: effect
        tl = self.tlm.Timeline(hp_start=(10, 10), length=10)
        tl.cues = [self.tlm.Cue(0, 0, "effect", "EID_K_THUNDER4")]
        self.stage.timeline = tl
        self.stage._layout()
        self.stage.arrays(1)
        self.assertAlmostEqual(float(self.stage.shades[-2]), battle_stage.REXBOLT_STRIKE_SHADE)
        self.assertEqual(float(self.stage.shades[-1]), 1.0)  # bolt intensity is unchanged


@unittest.skipIf(battle_stage is None, "needs tkinter and numpy")
class PerspectiveTests(unittest.TestCase):
    def test_screen_overlay_ignores_world_depth(self):
        canvas = SimpleNamespace(
            _center=(0.0, 0.0, 0.0), _perspective=0.0,
            _screen_x_sign=1.0, _screen_y_sign=1.0,
            _rotation_matrix=lambda: np.eye(3), _scale=lambda _width, _height: 20.0,
        )
        foreground = _Triangle(
            (-1.0, -1.0, -1.0), (1.0, -1.0, -1.0), (0.0, 1.0, -1.0),
            (0.0, 0.0, -1.0), (255, 0, 0), cull="none")
        overlay = _Triangle(
            (-1.0, -1.0, 1.0), (1.0, -1.0, 1.0), (0.0, 1.0, 1.0),
            (0.0, 0.0, -1.0), (0, 0, 255), cull="none", overlay=True)

        image = battle_stage._ModelCanvas._rasterize(canvas, [overlay, foreground], 80, 80)

        self.assertEqual(tuple(image[40, 40]), (0, 0, 255))

    def test_transparent_effect_cards_are_culled_before_texture_sampling(self):
        canvas = SimpleNamespace(
            _center=(0.0, 0.0, 0.0), _perspective=0.0,
            _screen_x_sign=1.0, _screen_y_sign=1.0,
            _rotation_matrix=lambda: np.eye(3), _scale=lambda _width, _height: 20.0,
        )
        texture = np.full((2, 2, 4), 255, dtype=np.uint8)
        hidden = _Triangle(
            (-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0),
            (255, 255, 255), uv=((0, 0), (1, 0), (0.5, 1)), texture=texture,
            alpha=battle_stage.effect_alpha(0.0), blend_mode="additive", cull="none",
        )

        with patch("fe_modding.gui.model_viewer._sample_texture_batch",
                   side_effect=AssertionError("transparent texture should not be sampled")):
            image = battle_stage._ModelCanvas._rasterize(canvas, [hidden] * 1496, 80, 60)

        self.assertFalse((image != 43).any())

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

    def test_overlapping_additive_effects_accumulate(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        try:
            from fe_modding.gui.model_viewer import _ModelCanvas
            canvas = _ModelCanvas(root)
            canvas._center, canvas._extent = (0.0, 0.0, 0.0), 2.0
            canvas._yaw = canvas._pitch = 0.0
            # The nearer card is intentionally first.  If additive cards write depth, it hides
            # the second one and the center remains roughly one card's intensity.
            cards = [
                _Triangle((-1, -1, z), (1, -1, z), (0, 1, z), (0, 0, -1), (40, 0, 0),
                          alpha=1.0, blend_mode="additive", cull="none")
                for z in (-0.1, 0.1)
            ]
            image = canvas._rasterize(cards, 100, 100)
            self.assertGreater(int(image[50, 50, 0]), 100)  # background 43 + 40 + 40
        finally:
            root.destroy()


@unittest.skipIf(battle_stage is None, "needs tkinter and numpy")
class StageViewPlaybackTests(unittest.TestCase):
    def test_slow_effect_draw_advances_exactly_one_tick(self):
        shown = []
        scheduled = []
        view = SimpleNamespace(
            _after="previous", _playing=True, _t=1.0,
            stage=SimpleNamespace(timeline=SimpleNamespace(length=400.0)),
            _scale=SimpleNamespace(set=lambda _value: None),
            _show=lambda frame, now=False: shown.append((frame, now)),
            update_idletasks=lambda: None,
            after=lambda delay, callback: scheduled.append((delay, callback)) or "next",
            on_finished=None,
        )
        view._tick = lambda: None

        # Simulate a two-second Breathred draw. Playback must slow down for it rather than
        # deriving the next animation frame from elapsed wall time and jumping near the end.
        with patch("fe_modding.gui.battle_stage.time.perf_counter", side_effect=(10.0, 12.0)):
            battle_stage.StageView._tick(view)

        self.assertEqual(view._t, 2.0)
        self.assertEqual(shown, [(2.0, True)])
        self.assertEqual(scheduled[0][0], 1)
        self.assertEqual(view._after, "next")


class ModelPreviewPlaybackTests(unittest.TestCase):
    def test_programmatic_slider_change_renders_one_frame(self):
        from fe_modding.gui import model_viewer

        rendered = []
        preview = SimpleNamespace(_setting_frame=False)
        preview._on_frame_scrub = lambda value: model_viewer._ModelPreview._on_frame_scrub(preview, value)
        preview._update_pose_display = lambda frame: rendered.append(frame)

        class Scale:
            def set(self, value):
                preview._on_frame_scrub(str(value))

        preview._frame_scale = Scale()
        model_viewer._ModelPreview._set_frame(preview, 12.0)
        self.assertEqual(rendered, [12.0])


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


@unittest.skipIf(battle_stage is None, "needs tkinter and numpy")
class ParticleTests(unittest.TestCase):
    def test_anchor_is_the_deepest_bone_in_the_path(self):
        from fe_modding.formats import particle_preview
        bones = {"group": 0, "h2_particle1": 1}
        self.assertEqual(particle_preview.anchor_bone("|group|h2_particle1|_h2_particleShape1_xl_", bones), 1)
        self.assertEqual(particle_preview.anchor_bone("|group|other|", bones), 0)
        self.assertIsNone(particle_preview.anchor_bone("|nothing|", bones))

    def test_battle_cards_keep_material_tint(self):
        from types import SimpleNamespace
        from fe_modding.formats import animation, particle_preview
        emitter = animation.ParticleEmitterLayout(
            0, "|root|", 0, 0, 0, 0, 0, (1.0, 1.0), 0.0, 1, 0, 0, 0, 0, 1)
        layout = animation.ParticleStageLayout(0, 0, 0, 10, (0.0, 0.0, 0.0), 0, 0)
        texture = np.full((2, 2, 4), 255, dtype=np.uint8)
        loaded = SimpleNamespace(particle_materials={0: (texture, (128, 64, 32), 1.0)})
        effect = SimpleNamespace(loaded=loaded, particles=(particle_preview.Stage(emitter, layout, ()),))
        cards = battle_stage.particle_cards(effect)
        self.assertEqual(cards[0].texture_layers[0].color_scale, (128 / 255, 64 / 255, 32 / 255))

    def test_battle_cards_apply_particle_colour_curve(self):
        from fe_modding.formats import animation, particle_preview
        emitter = animation.ParticleEmitterLayout(
            0, "|root|", 0, 0, 0, 0, 0, (1.0, 1.0), 0.0, 1, 0, 0, 0, 0, 1)
        layout = animation.ParticleStageLayout(0, 0, 0, 10, (0.0, 0.0, 0.0), 0, 3)
        curves = ((5, ((0, 1.0),)), (6, ((0, 0.5),)), (7, ((0, 0.25),)))
        texture = np.full((2, 2, 4), 255, dtype=np.uint8)
        loaded = SimpleNamespace(particle_materials={0: (texture, (128, 128, 128), 1.0)})
        effect = SimpleNamespace(loaded=loaded, particles=(particle_preview.Stage(emitter, layout, curves),))

        cards = battle_stage.particle_cards(effect)

        self.assertEqual(cards[0].texture_layers[0].color_scale,
                         (128 / 255, 64 / 255, 32 / 255))

    def test_battle_line_card_follows_velocity(self):
        from types import SimpleNamespace
        from fe_modding.formats import animation, particle_preview
        emitter = animation.ParticleEmitterLayout(
            0, "|root|", 0, 0, 0, 2, 0, (1.0, 1.0), 0.0, 1, 0, 0, 0, 0, 1)
        layout = animation.ParticleStageLayout(0, 0, 0, 10, (0.0, 0.0, 0.0), 0, 1)
        particle = particle_preview.Stage(emitter, layout, ((1, ((0, 1.0),)), (2, ((0, 1.0),))))
        loaded = SimpleNamespace(bones=[], particle_materials={0: (None, (255, 255, 255), 1.0)})
        effect = battle_stage.EffectAsset(loaded, battle_stage.SkinnedMesh([]), None, 10.0, (particle,))
        stage = battle_stage.BattleStage([])
        cue = SimpleNamespace(frame=0.0, side=0, aim=None, height=0.0)
        cards = battle_stage.particle_cards(effect)
        stage._add("particles", cards, side=0, item=(cue, effect))
        stage.alphas = np.zeros(len(cards), dtype=np.float32)
        positions = np.zeros((len(cards), 3, 3))
        normals = np.zeros((len(cards), 3))
        stage._particles(positions, normals, stage._parts[0], effect, cue, 1.0, 1.0)
        long_edge = positions[0, 2] - positions[0, 1]
        # side 0 turns local +Z into world +X; with +Y too, the streak is diagonal,
        # rather than locked to the camera's vertical axis.
        self.assertGreater(abs(long_edge[0]), 0.1)
        self.assertGreater(abs(long_edge[1]), 0.1)

    @unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES")
    def test_fire_cards_are_placed_and_hidden(self):
        from types import SimpleNamespace
        effect = battle_stage.load_effect(Path(os.environ["FE9_EXTRACTED_FILES"]) / "yme" / "EID_FIRE.cmp")
        cards = battle_stage.particle_cards(effect)
        self.assertEqual(len(cards), 2 * len(effect.particles))
        stage = battle_stage.BattleStage([])
        cue = SimpleNamespace(frame=0.0, side=0, aim=None, height=0.0)
        stage._add("particles", cards, side=0, item=(cue, effect))
        stage.alphas = np.zeros(len(cards), dtype=np.float32)
        positions, normals = np.zeros((len(cards), 3, 3)), np.zeros((len(cards), 3))
        stage._particles(positions, normals, stage._parts[0], effect, cue, 15.0, 15.0)
        shown = positions.any(axis=(1, 2))
        self.assertTrue(shown.any())
        self.assertTrue((stage.alphas[shown] < -1.0).all())      # unlit, two-sided effect alpha
        self.assertFalse(positions[~shown].any())                  # inactive stages stay hidden
