import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import mesh_reduce
from fe_modding.formats import gltf_import

FILES = os.environ.get("FE9_EXTRACTED_FILES")


def _tube(rings=24, sides=16, seam=True):
    """A capped-free tube along y; with ``seam`` the texture wraps with a
    column of duplicated vertices, as exported models do."""
    cols = sides + 1 if seam else sides
    P, UV = [], []
    for r in range(rings + 1):
        for c in range(cols):
            a = 2 * np.pi * (c % sides) / sides
            P.append((np.cos(a), r * 0.25, np.sin(a)))
            UV.append((c / sides, r / rings))
    T = []
    for r in range(rings):
        for c in range(sides):
            c1 = c + 1 if seam else (c + 1) % sides
            a, b, d, e = r * cols + c, r * cols + c1, (r + 1) * cols + c, (r + 1) * cols + c1
            T += [(a, d, b), (b, d, e)]
    return np.array(P, np.float32), np.array(UV, np.float32), np.array(T, np.uint32)


def _glb(P, UV, T) -> bytes:
    blobs = [P.tobytes(), UV.tobytes(), T.tobytes()]
    offsets = np.cumsum([0] + [len(b) for b in blobs])
    doc = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2}]}],
        "buffers": [{"byteLength": int(offsets[-1])}],
        "bufferViews": [{"buffer": 0, "byteOffset": int(offsets[i]), "byteLength": len(b)} for i, b in enumerate(blobs)],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3",
             "min": P.min(0).tolist(), "max": P.max(0).tolist()},
            {"bufferView": 1, "componentType": 5126, "count": len(UV), "type": "VEC2"},
            {"bufferView": 2, "componentType": 5125, "count": T.size, "type": "SCALAR"},
        ],
    }
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    binary = b"".join(blobs)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(js) + len(binary)) + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


class SimplifyTests(unittest.TestCase):
    def test_reaches_the_target_without_degenerate_or_flipped_triangles(self):
        P, _uv, T = _tube(seam=False)
        kept, moved = mesh_reduce.simplify(P, T, 200)
        self.assertLessEqual(len(kept), 200)
        self.assertGreater(len(kept), 150)

        def facing(points, tri):
            a, b, c = (points[i] for i in tri)
            centre = (a + b + c) / 3
            return float(np.cross(b - a, c - a) @ np.array([centre[0], 0, centre[2]]))

        side = np.sign(facing(P.astype(float), T[0]))
        for tri in kept:
            self.assertEqual(len(set(tri)), 3)
            self.assertEqual(np.sign(facing(moved, tri)), side)
        # the tube keeps its length and radius
        used = moved[np.unique(kept)]
        self.assertAlmostEqual(float(used[:, 1].max() - used[:, 1].min()), 6.0, places=4)
        self.assertGreater(float(np.linalg.norm(used[:, [0, 2]], axis=1).min()), 0.9)

    def test_locked_vertices_stay(self):
        P, _uv, T = _tube(seam=False)
        locked = P[:, 1] > 5
        kept, moved = mesh_reduce.simplify(P, T, 150, locked=locked)
        idx = np.flatnonzero(locked)
        self.assertTrue(set(idx) <= set(np.unique(kept).tolist()))
        np.testing.assert_allclose(moved[idx], P[idx])


class GlbTests(unittest.TestCase):
    def test_reduced_glb_keeps_attributes_and_the_uv_seam(self):
        P, UV, T = _tube()
        data = _glb(P, UV, T)
        self.assertEqual(mesh_reduce.glb_triangle_count(data), len(T))
        result = mesh_reduce.reduce_glb(data, 250)
        self.assertLessEqual(result.triangles_after, 250)
        self.assertEqual(mesh_reduce.glb_triangle_count(result.glb), result.triangles_after)
        scene = gltf_import.read_gltf(result.glb)
        tris = [t for ts in scene.triangles.values() for t in ts]
        self.assertEqual(len(tris), result.triangles_after)
        # both copies of the seam are still used: u = 0 and u = 1 at x = 1, z = 0
        doc, buffers = mesh_reduce._glb_parts(result.glb, None)
        prim = doc["meshes"][0]["primitives"][0]
        uv = mesh_reduce._values(doc, buffers, prim["attributes"]["TEXCOORD_0"])
        pos = mesh_reduce._values(doc, buffers, prim["attributes"]["POSITION"])
        on_seam = np.abs(pos[:, 2]) < 1e-6
        on_seam &= pos[:, 0] > 0
        self.assertTrue((uv[on_seam, 0] < 1e-6).any() and (uv[on_seam, 0] > 1 - 1e-6).any())

    def test_small_model_is_left_alone(self):
        P, UV, T = _tube(rings=2, sides=6)
        data = _glb(P, UV, T)
        result = mesh_reduce.reduce_glb(data, 500)
        self.assertEqual(result.glb, data)


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to the extracted disc's files folder")
class DiscMapReduceTests(unittest.TestCase):
    def test_fighter_kit_reduced_imports_with_its_weapon_whole(self):
        from fe_modding.gui import model_viewer as mv

        container = Path(FILES) / "ymu/fighter/pack.cmp"
        self.assertEqual(mv.map_locked_joints(container), {"Ax", "Ax1"})
        glb, _bones, _named = mv.rig_kit_glb(container)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "fighter.glb"
            source.write_bytes(glb)
            reduced, result = mv.reduce_map_glb(container, source, 300)
            self.assertEqual(reduced.name, "fighter_300tris.glb")
            self.assertLessEqual(result.triangles_after, 300)

            def weapon_triangles(data):
                scene = gltf_import.read_gltf(data)
                return sum(
                    1 for ts in scene.triangles.values() for t in ts
                    if all(max(inf, key=lambda jw: jw[1])[0] in ("Ax", "Ax1") for inf in t.influences)
                    and np.linalg.norm(np.cross(np.subtract(t.positions[1], t.positions[0]),
                                                np.subtract(t.positions[2], t.positions[0]))) > 1e-9
                )

            self.assertEqual(weapon_triangles(reduced.read_bytes()), weapon_triangles(glb))
            imported = mv.replace_rig_with_glb(container, reduced)
        self.assertIn(container, imported.outputs)


if __name__ == "__main__":
    unittest.main()
