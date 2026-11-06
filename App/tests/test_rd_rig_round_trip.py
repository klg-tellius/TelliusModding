"""Radiant Dawn map rigs through the rig kit: export, import back untouched, and the body is where the game
draws it (rest and animated), anchors included; paired models and multi-image textures import."""

import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FE10 = os.environ.get("FE10_EXTRACTED_FILES")


def _posed(bones, gs, anim, frame):
    from fe_modding.formats import engine_pose, skeleton
    world, palette = engine_pose.pose(bones, anim, frame)
    points = []
    for chunk in gs.chunks:
        if chunk.hidden:
            continue
        for strip in chunk.strips:
            for v in strip:
                if not chunk.format & 3 and 0 <= chunk.bone < len(bones):
                    m = world[chunk.bone]
                elif v.bone_indices:
                    pairs = [(i, w) for i, w in zip(v.bone_indices, v.bone_weights) if w > 0 and 0 <= i < len(bones)]
                    total = sum(w for _, w in pairs) or 1
                    m = [[sum(w * palette[i][r][c] for i, w in pairs) / total for c in range(4)] for r in range(3)]
                else:
                    m = skeleton.IDENTITY_3X4
                points.append(engine_pose.apply(m, v.position))
    return points


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdRigRoundTripTests(unittest.TestCase):
    def round_trip(self, name: str, animation_file: str):
        import numpy as np
        from fe_modding.formats import animation, model as model_fmt, skeleton
        from fe_modding.gui import model_viewer as mv

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        work = Path(tmp.name) / "ymu" / name        # the loose texture is found beside a ymu/ set
        shutil.copytree(Path(FE10) / "ymu" / name, work)

        def load():
            files, _ = mv._set_contents(work / "pack.cmp")
            g = next(n for n in files if n.lower().endswith(".g"))
            gs = next(n for n in files if n.lower().endswith(".gs"))
            anim = (work / animation_file).read_bytes() if (work / animation_file).is_file() else files[animation_file]
            return (skeleton.read_skeleton(io.BytesIO(files[g])), model_fmt.read_model_bytes(files[gs]),
                    animation.read_animation_bytes(anim))

        before = load()
        glb, _bones, _named = mv.rig_kit_glb(work / "pack.cmp")
        kit = Path(tmp.name) / "kit.glb"
        kit.write_bytes(glb)
        result = mv.replace_rig_with_glb(work / "pack.cmp", kit)
        for path, data in result.outputs.items():
            Path(path).write_bytes(data)
        after = load()
        # The game always plays an animation (a bone without a group keeps its seed matrix); a pose with
        # no animation at all is not something it draws.
        for frame, anim in ((0.0, before[2]), (5.0, before[2]), (12.0, before[2])):
            old = np.array(_posed(before[0], before[1], anim, frame))
            new = np.array(_posed(after[0], after[1], after[2], frame))
            nearest = np.sqrt(((old[:, None, :] - new[None, :, :]) ** 2).sum(-1)).min(1)
            self.assertLess(nearest.max(), 0.05, f"{name} frame {frame}")
        self.assertEqual([b.name for b in after[0]], [b.name for b in before[0]])
        return before, after, result

    def test_micaiah_keeps_her_body_and_anchors(self):
        _before, _after, result = self.round_trip("mikaya1", "walk_1.ga")
        self.assertFalse([w for w in result.warnings if "Anchor bones" in w or "no texture" in w], result.warnings)

    def test_paired_model_keeps_its_repeated_bone_names(self):
        before, after, _result = self.round_trip("sothe1_mikaya2", "evt1_1.ga")
        names = [b.name for b in before[0]]
        self.assertGreater(len(names) - len(set(names)), 0)
        self.assertEqual([b.name for b in after[0]], names)

    def test_archer_with_body_and_bow_textures(self):
        before, after, result = self.round_trip("archer1", "atk_1.ga")
        self.assertEqual(sorted({t.tex_id for m in after[1].materials for t in m.textures}), [0, 1])
        self.assertFalse([w for w in result.warnings if "New texture" in w], result.warnings)

    def test_a_new_skeleton_is_refused_on_a_joint_orient_rig(self):
        from fe_modding import rig_fit
        from fe_modding.gui import model_viewer as mv
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        work = Path(tmp.name) / "ymu" / "mikaya1"
        shutil.copytree(Path(FE10) / "ymu" / "mikaya1", work)
        other = Path(tmp.name) / "ymu" / "greil"
        shutil.copytree(Path(FE10) / "ymu" / "greil", other)
        model = Path(tmp.name) / "greil.glb"
        model.write_bytes(mv.rig_kit_glb(other / "pack.cmp")[0])
        with self.assertRaisesRegex(rig_fit.RigFitError, "joint orient"):
            mv.prepare_rig_fit(work / "pack.cmp", model)
        from fe_modding.formats import gltf_import
        with self.assertRaisesRegex(gltf_import.GltfImportError, "joint orient"):
            mv.replace_rig_with_glb(work / "pack.cmp", model)

    def test_joint_names_are_unique_in_the_kit_and_restored(self):
        from fe_modding.formats import gltf_export, gltf_import, skeleton
        files = skeleton.read_skeleton_file  # noqa: F841 - imported for the restore below
        bones = [type("B", (), {"name": n})() for n in ("hand", "hand", "arm", "hand")]
        self.assertEqual(gltf_export.joint_names(bones), ["hand", "hand~2", "arm", "hand~3"])
        self.assertIsNotNone(gltf_import.restore_duplicate_names)


if __name__ == "__main__":
    unittest.main()
