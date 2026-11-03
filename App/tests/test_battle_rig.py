import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import animation, engine_pose, skeleton


def _anim(groups):
    """groups: [(bone, [(channel, [(frame, value), ...]), ...]), ...] with scale shift 4."""
    header = animation.GaHeader(words=(0, 0, 0, 0x11, 0, 1, 10, 0, 0, 0, 0, 0))
    out_groups, curves = [], []
    for bone, channels in groups:
        out_groups.append(animation.BoneGroup(bone, animation_mask(channels), len(curves), len(channels)))
        for channel, keys in channels:
            curves.append(animation.AnimCurve(bone, channel, 4, keys[-1][0],
                                              [animation.Keyframe(f, round(v * 16)) for f, v in keys]))
    return animation.GaAnimation(header, out_groups, curves)


def animation_mask(channels):
    mask = 0
    for channel, _keys in channels:
        mask |= {0: 8, 3: 16, 6: 32}.get(channel // 3 * 3, 0)
    return mask


class RetargetTests(unittest.TestCase):
    def test_bones_matched_by_name_and_positions_follow_the_new_rest_pose(self):
        old_names = ["root", "arm", "tail"]
        new_names = ["arm", "root", "extra"]
        rest = [0.0] * engine_pose.VALUE_COUNT
        old_values = [list(rest) for _ in old_names]
        new_values = [list(rest) for _ in new_names]
        old_values[1][6:9] = [2.0, 0.0, 0.0]  # the old arm sits 2 units out
        new_values[0][6:9] = [3.0, 0.0, 0.0]  # the new one 3
        anim = _anim([
            (0, [(3, [(0, 0.0), (10, 90.0)])]),
            (1, [(6, [(0, 2.0), (10, 2.5)]), (4, [(0, 10.0)])]),
            (2, [(5, [(0, 45.0)])]),
        ])
        moved, dropped = animation.retarget_animation(anim, old_names, old_values, new_names, new_values)
        self.assertEqual(dropped, ["tail"])
        self.assertEqual([g.bone_index for g in moved.groups], [0, 1])  # ascending: arm (0), root (1)
        arm = moved.curves_for_bone(0)
        translate = next(c for c in arm if c.channel == 6)
        self.assertEqual([translate.scaled_value(k) for k in translate.keyframes], [3.0, 3.5])
        rotate = next(c for c in arm if c.channel == 4)
        self.assertEqual(rotate.keyframes, anim.curves[2].keyframes)
        self.assertEqual([c.channel for c in moved.curves_for_bone(1)], [3])
        # the groups describe the curve order, so the file round-trips
        again = animation.read_animation_bytes(animation.write_animation(moved))
        self.assertEqual([(g.bone_index, g.first_curve, g.curve_count) for g in again.groups], [(0, 0, 2), (1, 2, 1)])

    def test_large_shift_lowers_the_key_precision(self):
        rest = [0.0] * engine_pose.VALUE_COUNT
        new_values = [list(rest)]
        new_values[0][6] = 5000.0
        anim = _anim([(0, [(6, [(0, 1.0)])])])
        moved, _ = animation.retarget_animation(anim, ["a"], [list(rest)], ["a"], new_values)
        curve = moved.curves[0]
        self.assertAlmostEqual(curve.scaled_value(curve.keyframes[0]), 5001.0, places=0)
        self.assertLess(curve.scale_shift, 4)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscBattleRigTests(unittest.TestCase):
    def test_fig1_rig_rebuilt_from_its_export_keeps_every_joint(self):
        from fe_modding.formats import gltf_import, pak
        from fe_modding.gui import model_viewer

        pack = sorted((Path(os.environ["FE9_EXTRACTED_FILES"]) / "zu" / "fig1").glob("*.pak"))[0]
        raw = pack.read_bytes()
        files = {e.name: pak.read_pak_file_content(raw, e) for e in pak.read_pak_entries(raw)}
        old = skeleton.read_skeleton_file(next(d for n, d in files.items() if n.endswith(".g"))).bones
        built, _warnings = gltf_import.build_skeleton(model_viewer.export_set_glb(pack), template=old)
        new = skeleton.read_skeleton_file(skeleton.write_skeleton_file(built)).bones

        def joints(bones):
            world = engine_pose.world_matrices(bones, engine_pose.local_matrices(bones, None, 0))
            return {b.name: engine_pose.apply(world[i], engine_pose.rest_pivot(b)) for i, b in enumerate(bones)}

        a, b = joints(old), joints(new)
        worst = max(max(abs(x - y) for x, y in zip(a[n], b[n])) for n in a)
        self.assertLess(worst, 0.01)
        errors, warnings = gltf_import.check_rig_against(new, old)
        self.assertEqual((errors, warnings), ([], []))


if __name__ == "__main__":
    unittest.main()
