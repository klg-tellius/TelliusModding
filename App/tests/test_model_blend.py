"""How the model renderer picks a .gs shape's blend mode for both games."""

import unittest

from fe_modding.formats import model
from fe_modding.gui.model_viewer import _chunk_blend_mode


def _chunk(flags: int) -> model.TriChunk:
    return model.TriChunk(mesh_index=0, material_index=0, bone=0, format=flags, format2=0, bone_subset=[], strips=[])


def _material(flag0: int) -> model.Material:
    return model.Material(index=0, name="fire_lambert2", color0=(204, 204, 204, 153), color1=(0, 0, 0, 255),
                          color2=(0, 0, 0, 0), textures=[], flag0=flag0)


class BlendModeTests(unittest.TestCase):
    def test_path_of_radiance_shape_bit_is_additive(self):
        self.assertEqual(_chunk_blend_mode(_chunk(0x7A42), _material(0)), "additive")

    def test_radiant_dawn_material_bit_is_additive(self):
        # bmap0203's torch flame (torh02): shape flags 0x7800, material bytes +4/+5 = 0x30, 0x28
        self.assertEqual(_chunk_blend_mode(_chunk(0x7800), _material(0x30)), "additive")

    def test_blended_and_plain_materials_stay_normal(self):
        self.assertEqual(_chunk_blend_mode(_chunk(0x7800), _material(0x10)), "normal")  # smoke, panels
        self.assertEqual(_chunk_blend_mode(_chunk(0x3002), _material(0)), "normal")
        self.assertEqual(_chunk_blend_mode(_chunk(0x3002)), "normal")


if __name__ == "__main__":
    unittest.main()
