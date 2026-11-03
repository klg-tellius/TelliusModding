import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import gs_file  # noqa: E402
from fe_modding.formats.gltf_import import FLAG_COMPOSITE, FLAG_MULTI_MATRIX, _chunk_lists  # noqa: E402


def _chunk(flags, bone):
    return gs_file.GsChunk(None, flags, 0, bone, -1, 0, b"")


class ChunkOrderTests(unittest.TestCase):
    def test_multi_matrix_chunks_draw_first_in_each_list(self):
        # a composite chunk after a multi-matrix one would draw from a matrix slot the multi-matrix
        # chunk had reloaded (build_and_cache_gs_shape_bone_matrices pre-fills the slots)
        a, b, c, d = (_chunk(0x2000 | FLAG_COMPOSITE, 0), _chunk(0x2000 | FLAG_MULTI_MATRIX, 3),
                      _chunk(0x2000 | FLAG_COMPOSITE, 0), _chunk(0x4000 | FLAG_MULTI_MATRIX, 5))
        first, second, third = _chunk_lists([a, b, c, d])
        self.assertEqual(first, [b, a, c])
        self.assertEqual(second, [d])
        self.assertEqual(third, [])


if __name__ == "__main__":
    unittest.main()
