import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import rig_fit, rig_tools
from fe_modding.formats import animation, engine_pose, gltf_import, gs_file, skeleton

FILES = os.environ.get("FE9_EXTRACTED_FILES")


def _bare_rig(names, parents, positions, verts=None, vjoint=None):
    from types import SimpleNamespace
    rest = np.tile(np.eye(4), (len(names), 1, 1))
    rest[:, :3, 3] = positions
    verts = verts if verts is not None else positions
    vjoint = vjoint if vjoint is not None else list(range(len(names)))
    V = np.array(verts, float)
    J = np.zeros((len(V), 4), int)
    J[:, 0] = vjoint
    W = np.zeros((len(V), 4))
    W[:, 0] = 1
    rig = rig_fit.Rig(doc=SimpleNamespace(doc={"animations": []}), nodes=[], node_parent={},
                      joints=list(range(len(names))), names=list(names), parent=list(parents), rest=rest,
                      V=V, N=np.tile([0.0, 0.0, 1.0], (len(V), 1)), UV=np.zeros((len(V), 2)), J=J, W=W,
                      idx=np.arange(len(V) - len(V) % 3), image=None)
    rig.joint_index = {n: k for k, n in enumerate(names)}
    return rig


class MirrorTests(unittest.TestCase):
    def test_side_tokens_are_swapped(self):
        self.assertIn("RightFoot", rig_tools.mirrored_names("LeftFoot"))
        self.assertIn("mixamorig:RightArm", rig_tools.mirrored_names("mixamorig:LeftArm"))
        self.assertIn("R_arm1", rig_tools.mirrored_names("L_arm1"))
        self.assertIn("hand.R", rig_tools.mirrored_names("hand.L"))
        self.assertIn("Bip001 R Thigh", rig_tools.mirrored_names("Bip001 L Thigh"))
        self.assertIn("migi_ude3", rig_tools.mirrored_names("hidari_ude3"))
        self.assertIn("_r_hand_", rig_tools.mirrored_names("_l_hand_"))
        # letters inside a word are not sides
        self.assertEqual(rig_tools.mirrored_names("Lower"), [])
        self.assertEqual(rig_tools.mirrored_names("Hips"), [])

    def test_mapping_copied_to_the_other_side_by_name_and_by_position(self):
        # the model names its sides; the game rig only by position (Japanese names)
        model = _bare_rig(["Hips", "LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"], [-1, 0, 1, 0, 3],
                          [(0, 10, 0), (1, 9, 0), (1, 5, 0), (-1, 9, 0), (-1, 5, 0)])
        game = _bare_rig(["koshi", "momo_a", "ashi_a", "momo_b", "ashi_b"], [-1, 0, 1, 0, 3],
                         [(0, 10, 0), (1.1, 9, 0), (1.1, 5, 0), (-1.1, 9, 0), (-1.1, 5, 0)])
        mapping = {"Hips": "koshi", "LeftUpLeg": "momo_a", "LeftLeg": "ashi_a", "RightUpLeg": "", "RightLeg": ""}
        result = rig_tools.mirror_mapping(model, game, mapping, "left")
        self.assertEqual(result.mapping["RightUpLeg"], "momo_b")
        self.assertEqual(result.mapping["RightLeg"], "ashi_b")
        self.assertEqual(result.mapping["Hips"], "koshi")
        self.assertEqual(sorted(result.changed), ["RightLeg", "RightUpLeg"])
        back = rig_tools.mirror_mapping(model, game, dict(result.mapping, RightLeg=""), "right")
        self.assertEqual(back.mapping["LeftLeg"], "")

    def test_a_one_sided_joint_is_not_taken_for_the_other_leg(self):
        # the Fighter's pouch hangs on the left hip, near where the right thigh mirrors to
        names = ["Hip", "L_leg1", "R_leg1", "Fukuro"]
        pos = np.array([(0, 10, 0), (1.3, 8.8, 0.4), (-1.3, 8.8, 0.4), (1.9, 8.5, 0.1)], float)
        self.assertEqual(rig_tools.mirror_joint(names, pos, 1, 0.7), 2)
        self.assertIsNone(rig_tools.mirror_joint(names, pos, 3, 0.7))
        rig = _bare_rig(names, [-1, 0, 0, 0], pos)
        result = rig_tools.mirror_mapping(rig, rig, {"Hip": "Hip", "L_leg1": "L_leg1", "R_leg1": "", "Fukuro": ""})
        self.assertEqual(result.mapping["R_leg1"], "R_leg1")
        self.assertEqual(result.unmatched, ["Fukuro"])

    def test_unmapped_joints_carrying_the_mesh_are_listed(self):
        model = _bare_rig(["Root", "Hips", "Cape"], [-1, 0, 0], [(0, 0, 0), (0, 10, 0), (0, 12, -1)],
                          verts=[(0, 10, 0)] * 6 + [(0, 12, -1)] * 6, vjoint=[1] * 6 + [2] * 6)
        self.assertEqual(rig_tools.unmapped_deforming(model, {"Hips": "hip1"}), ["Cape"])
        self.assertEqual(rig_tools.unmapped_deforming(model, {"Hips": "hip1", "Root": "hip1"}), [])

    def test_outline_fits_the_unit_square_facing_the_viewer(self):
        out = rig_tools.skeleton_outline(["a", "b"], [-1, 0], np.array([[1.0, 0, 0], [-1.0, 10, 0]]))
        (ax, ay), (bx, by) = out.points
        self.assertGreater(ax, bx)  # the character's left (+x) is on the viewer's right
        self.assertGreater(ay, by)  # y down
        for x, y in out.points:
            self.assertTrue(0 <= x <= 1 and 0 <= y <= 1)


def _fit_glb(**options):
    game = _bare_rig(["hip1", "body1", "face1", "l_leg", "l_foot"], [-1, 0, 1, 0, 3],
                     [(0, 10, 0), (0, 12, 0), (0, 15, 0), (1, 6, 0), (1, 1, 0)],
                     verts=[(0, 10, 0), (0, 12, 0), (0, 16, 0), (1, 6, 0), (1, 0, 0), (1, 1, 0)],
                     vjoint=[0, 1, 2, 3, 4, 4])
    # the model stops at the ankle: its lowest vertex is its foot joint
    model = _bare_rig(["Hips", "Spine", "Head", "LeftLeg", "LeftFoot"], [-1, 0, 1, 0, 3],
                      [(0, 5, 0), (0, 6, 0), (0, 8, 0), (0.5, 3, 0), (0.5, 0, 0)],
                      verts=[(0, 5, 0), (0, 6, 0), (0, 9, 0), (0.5, 3, 0), (0.5, 0, 0), (0.5, 0.2, 0)],
                      vjoint=[0, 1, 2, 3, 4, 4])
    mapping = {"Hips": "hip1", "Spine": "body1", "Head": "face1", "LeftLeg": "l_leg", "LeftFoot": "l_foot"}
    return rig_fit.fit_rig(model, game, mapping, battle=False, **options)


class FitOptionTests(unittest.TestCase):
    def test_feet_option_puts_the_ankle_at_the_game_ankle_height(self):
        mesh = rig_fit.read_rig(_fit_glb().glb)
        self.assertAlmostEqual(float(mesh.V[:, 1].min()), 0.0, places=3)
        feet = _fit_glb(floor=rig_fit.FLOOR_FEET)
        rig = rig_fit.read_rig(feet.glb)
        self.assertAlmostEqual(float(rig.pos[rig.joint_index["LeftFoot"]][1]), 1.0, places=3)
        self.assertAlmostEqual(float(rig.V[:, 1].max()), 16.0, places=3)
        self.assertTrue(any(w.startswith("Feet:") for w in feet.warnings))

    def test_double_sided_reaches_the_shape_flags(self):
        scene_one = gltf_import._Document(_fit_glb().glb, None).doc
        scene_two = gltf_import._Document(_fit_glb(double_sided=True).glb, None).doc
        self.assertNotIn("doubleSided", scene_one["materials"][0])
        self.assertTrue(scene_two["materials"][0]["doubleSided"])

    def test_unknown_floor_is_refused(self):
        with self.assertRaises(rig_fit.RigFitError):
            _fit_glb(floor="ceiling")


class JointTests(unittest.TestCase):
    def test_added_joints_sit_where_asked_and_keep_the_mesh(self):
        glb = _fit_glb().glb
        names, parents, pos, _rot = rig_tools.glb_joints(glb)
        specs = rig_tools.anchor_joint_specs(glb, [("_ex1_", "Head", (0.0, 1.0, 0.0)),
                                                   ("_ex2_", "Head", (0.0, 0.0, 0.0))], battle=True)
        self.assertEqual([s.name for s in specs], ["carrier_ex1_", "_ex1_", "_ex2_"])
        out = rig_tools.add_joints_to_glb(glb, specs)
        n2, p2, pos2, _r2 = rig_tools.glb_joints(out)
        self.assertEqual(n2[:len(names)], names)
        head = names.index("Head")
        np.testing.assert_allclose(pos2[n2.index("_ex1_")], pos[head] + [0, 1, 0], atol=1e-5)
        self.assertEqual(n2[p2[n2.index("_ex1_")]], "carrier_ex1_")
        self.assertEqual(n2[p2[n2.index("_ex2_")]], "Head")
        before, after = rig_fit.read_rig(glb), rig_fit.read_rig(out)
        np.testing.assert_allclose(before.V, after.V, atol=1e-4)
        with self.assertRaises(ValueError):
            rig_tools.add_joints_to_glb(out, [rig_tools.JointSpec("_ex1_", "Head", (0, 0, 0))])
        with self.assertRaises(ValueError):
            rig_tools.anchor_joint_specs(glb, [("ex1", "Head", (0, 0, 0))], battle=False)

    def test_anchor_offsets_follow_the_same_named_bone_and_scale(self):
        source = rig_tools.add_joints_to_glb(_fit_glb().glb, [rig_tools.JointSpec("_ex1_", "Head", (0.0, 18.0, 0.0))])
        target = _fit_glb().glb
        copies = rig_tools.anchor_offsets(source, target)
        self.assertEqual([(c.name, c.parent) for c in copies], [("_ex1_", "Head")])
        _n, _p, pos, _r = rig_tools.glb_joints(target)
        head = _n.index("Head")
        self.assertAlmostEqual(copies[0].offset[1], 18.0 - pos[head][1], places=4)
        self.assertEqual(rig_tools.anchor_offsets(source, source), [])


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to the extracted disc's files folder")
class DiscAnchorTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.gui import model_viewer as mv
        self.mv = mv
        self.files = Path(FILES)

    def _poses(self, container, pending, clip, frame):
        files, anims = self.mv._set_contents(container, pending)
        g = next(d for n, d in files.items() if n.lower().endswith(".g"))
        clips = dict(anims)
        clips.update({n: d for n, d in files.items() if n.lower().endswith(".ga")})
        bones = skeleton.read_skeleton_file(g).bones
        anim = animation.read_animation_bytes(clips[clip])
        world = engine_pose.world_matrices(bones, engine_pose.local_matrices(bones, anim, frame))
        return {b.name: np.array(engine_pose.apply(world[i], engine_pose.rest_pivot(b))) for i, b in enumerate(bones)}

    def test_spell_anchors_copied_from_the_sage_onto_the_fighter(self):
        sage, fighter = self.files / "ymu/sene/pack.cmp", self.files / "ymu/fighter/pack.cmp"
        copies = self.mv.anchor_copies(sage, fighter)
        self.assertEqual([(c.name, c.parent) for c in copies], [("_ex1_", "R_arm2"), ("_ex2_", "R_arm2")])
        result = self.mv.add_anchor_bones(fighter, [(c.name, c.parent, c.offset) for c in copies])
        for frame in (0, 8):
            old = self._poses(fighter, None, "atk1_AX.ga", frame)
            new = self._poses(fighter, result.outputs, "atk1_AX.ga", frame)
            for name, at in old.items():
                np.testing.assert_allclose(new[name], at, atol=0.01)
            self.assertIn("_ex1_", new)
        moved = self._poses(fighter, result.outputs, "atk1_AX.ga", 8)["_ex1_"] - \
            self._poses(fighter, result.outputs, "atk1_AX.ga", 0)["_ex1_"]
        self.assertGreater(float(np.linalg.norm(moved)), 0.1)  # it follows the arm

    def test_battle_anchor_added_with_a_carrier(self):
        pak = self.files / "zu/fig1/fig1_ax.pak"
        result = self.mv.add_anchor_bones(pak, [("_ex1_", "LeftHand", (0.0, 2.0, 0.0))])
        new = self._poses(pak, result.outputs, "fig1_at1_ax.ga", 0)
        old = self._poses(pak, None, "fig1_at1_ax.ga", 0)
        self.assertIn("carrier_ex1_", new)
        for name, at in old.items():
            np.testing.assert_allclose(new[name], at, atol=0.01)

    def test_rig_check_reports_trail_anchors_a_clip_needs(self):
        fighter = self.files / "ymu/fighter/pack.cmp"
        self.assertFalse([f for f in self.mv.check_rig(fighter, fighter) if f.level == "error"])
        files, _anims = self.mv._set_contents(fighter)
        bones = skeleton.read_skeleton_file(next(d for n, d in files.items() if n.endswith(".g"))).bones
        spell = (self.files / "ymu/sene/magic1_N.ga").read_bytes()
        findings = rig_tools.rig_check(bones, [("magic1_N.ga", spell)], battle=False)
        errors = [f.text for f in findings if f.level == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("_ex1_", errors[0])
        battle = self.mv.check_rig(self.files / "zu/fig1/fig1_ax.pak")
        self.assertFalse([f for f in battle if f.level == "error"])

    def test_fit_double_sided_writes_untouched_cull_flags(self):
        import json
        import struct
        container = self.files / "ymu/fighter/pack.cmp"
        glb, _bones, _named = self.mv.rig_kit_glb(container)
        n = struct.unpack_from("<I", glb, 12)[0]
        doc = json.loads(glb[20:20 + n])
        for node in doc["nodes"]:
            if rig_fit.is_anchor(node.get("name", "")):
                node["name"] = "x" + node["name"]
        js = json.dumps(doc).encode()
        js += b" " * (-len(js) % 4)
        rest = glb[20 + n:]
        model_glb = struct.pack("<III", 0x46546C67, 2, 20 + len(js) + len(rest)) + \
            struct.pack("<II", len(js), 0x4E4F534A) + js + rest
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "model.glb"
            model_path.write_bytes(model_glb)
            setup = self.mv.prepare_rig_fit(container, model_path)
            mapping = dict(setup.mapping, R_arm1="R_arm1", R_arm2="R_arm2", R_hand="R_hand")
            result = self.mv.fit_new_rig(container, setup, mapping, double_sided=True, floor=rig_fit.FLOOR_FEET)
        files, _anims = self.mv._set_contents(container, result.outputs)
        gs = gs_file.read_gs(next(d for n, d in files.items() if n.endswith(".gs")))
        flags = {c.flags & 0x1800 for c in gs.chunks}
        self.assertEqual(flags, {0x1800})


if __name__ == "__main__":
    unittest.main()
