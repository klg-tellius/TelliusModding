"""TPL mip levels: layout, replace, region replace, copy and append keep
every image's chain consistent."""

import io
import os
import struct
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import tpl


def _gradient(width: int, height: int) -> Image.Image:
    x = np.linspace(0, 255, width, dtype=np.uint8)[None, :].repeat(height, 0)
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, None].repeat(width, 1)
    return Image.fromarray(np.dstack([x, y, 255 - x, np.full_like(x, 255)]), "RGBA")


def _mean_error(a: Image.Image, b: Image.Image) -> float:
    return float(np.abs(np.asarray(a.convert("RGB"), float) - np.asarray(b.convert("RGB"), float)).mean())


class MipLayoutTests(unittest.TestCase):
    def test_level_sizes_halve_down_to_one(self):
        self.assertEqual(tpl.mip_level_sizes(8, 2, 3), [(8, 2), (4, 1), (2, 1), (1, 1)])

    def test_build_writes_header_and_chain(self):
        data = tpl.build_tpl([(_gradient(32, 64), tpl.FORMAT_CMPR)], mip_count=2)
        (info,) = tpl.read_tpl_image_info(io.BytesIO(data))
        self.assertEqual((info.min_lod, info.max_lod, info.mip_count), (0, 2, 2))
        self.assertEqual((info.min_filter, info.mag_filter), (tpl.FILTER_LIN_MIP_LIN, tpl.FILTER_LINEAR))
        self.assertEqual(info.mip_data_length, tpl.cmpr_data_length(32, 64) + tpl.cmpr_data_length(16, 32) + tpl.cmpr_data_length(8, 16))
        self.assertEqual(len(data), info.data_addr + info.mip_data_length)
        levels = tpl.read_mip_levels(data, 0)
        self.assertEqual([level.size for level in levels], [(32, 64), (16, 32), (8, 16)])
        self.assertLess(_mean_error(levels[1], _gradient(32, 64).resize((16, 32), Image.BOX)), 8)

    def test_no_mips_by_default(self):
        (info,) = tpl.read_tpl_image_info(io.BytesIO(tpl.build_tpl([(_gradient(8, 8), tpl.FORMAT_RGBA8)])))
        self.assertEqual((info.mip_count, info.min_filter), (0, tpl.FILTER_LINEAR))


class MipWriteTests(unittest.TestCase):
    def _two_images(self, fmt=tpl.FORMAT_RGB565) -> bytes:
        return tpl.build_tpl([(_gradient(16, 16), fmt), (Image.new("RGBA", (8, 8), (1, 2, 3, 255)), fmt)], mip_count=1)

    def test_replace_regenerates_every_level_and_spares_the_next_image(self):
        for fmt in (tpl.FORMAT_CMPR, tpl.FORMAT_RGB565, tpl.FORMAT_RGBA8, tpl.FORMAT_I4):
            with self.subTest(fmt=tpl.format_name(fmt)):
                data = self._two_images(fmt)
                infos = tpl.read_tpl_image_info(io.BytesIO(data))
                red = Image.new("RGBA", (40, 40), (255, 0, 0, 255))
                patched = tpl.replace_image(data, 0, red)
                self.assertEqual(len(patched), len(data))
                expected = tpl.mip_chain(red.resize((16, 16)), 1)
                if fmt == tpl.FORMAT_I4:
                    expected = [lvl.convert("L") for lvl in expected]
                levels = tpl.read_mip_levels(patched, 0)
                self.assertEqual([lvl.size for lvl in levels], [(16, 16), (8, 8)])
                for got, want in zip(levels, expected):
                    self.assertLess(_mean_error(got, want), 9)
                start = infos[1].data_addr
                self.assertEqual(patched[start:], data[start:])

    def test_replace_region_refreshes_mips(self):
        data = tpl.build_tpl([(Image.new("RGBA", (16, 16), (0, 0, 0, 255)), tpl.FORMAT_RGBA8)], mip_count=1)
        patched = tpl.replace_region(data, 0, (0, 0, 8, 8), Image.new("RGBA", (8, 8), (255, 255, 255, 255)))
        mip = np.asarray(tpl.read_mip_levels(patched, 0)[1].convert("RGB"))
        self.assertTrue((mip[:4, :4] == 255).all())
        self.assertTrue((mip[4:, 4:] == 0).all())

    def test_copy_and_select_keep_the_chain(self):
        data = self._two_images()
        source = tpl.build_tpl([(_gradient(32, 32), tpl.FORMAT_CMPR)], mip_count=1)
        merged, first = tpl.copy_images(data, source, [0])
        self.assertEqual(first, 2)
        for got, want in zip(tpl.read_mip_levels(merged, 2), tpl.read_mip_levels(source, 0)):
            self.assertEqual(got.tobytes(), want.tobytes())
        selected = tpl.select_images(merged, [2, 0])
        self.assertEqual(tpl.image_keys(selected), [tpl.image_keys(merged)[2], tpl.image_keys(merged)[0]])
        for got, want in zip(tpl.read_mip_levels(selected, 1), tpl.read_mip_levels(data, 0)):
            self.assertEqual(got.tobytes(), want.tobytes())

    def test_append_matches_the_file(self):
        data = self._two_images()
        self.assertEqual(tpl.typical_mip_count(data), 1)
        out, first = tpl.append_images(
            data, [(_gradient(16, 8), tpl.FORMAT_CMPR, tpl.WRAP_REPEAT)], tpl.typical_mip_count(data)
        )
        infos = tpl.read_tpl_image_info(io.BytesIO(out))
        self.assertEqual(infos[first].mip_count, 1)
        self.assertEqual([lvl.size for lvl in tpl.read_mip_levels(out, first)], [(16, 8), (8, 4)])
        for i in range(2):
            self.assertEqual(
                [lvl.tobytes() for lvl in tpl.read_mip_levels(out, i)], [lvl.tobytes() for lvl in tpl.read_mip_levels(data, i)]
            )

    def test_chain_past_end_of_file_is_refused(self):
        data = tpl.build_tpl([(_gradient(8, 8), tpl.FORMAT_RGBA8)])
        broken = bytearray(data)
        header_at = struct.unpack_from(">I", broken, 12)[0]
        broken[header_at + 0x22] = 1  # claims a mip level the file does not hold
        with self.assertRaises(tpl.TplError):
            tpl.replace_image(bytes(broken), 0, _gradient(8, 8))


EXTRACTED = os.environ.get("FE9_EXTRACTED_FILES")


@unittest.skipUnless(EXTRACTED, "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class VanillaMipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fe_modding import map_props

        _, files = map_props.read_map_container(Path(EXTRACTED) / "zmap" / "bmap01" / "map.cmp")
        cls.texpack = files[map_props.texpack_name(files)]

    def test_bmap01_image0_layout(self):
        infos = tpl.read_tpl_image_info(io.BytesIO(self.texpack))
        first = infos[0]
        self.assertEqual((first.width, first.height, first.format), (512, 1024, tpl.FORMAT_CMPR))
        self.assertEqual((first.min_lod, first.max_lod, first.min_filter), (0, 1, tpl.FILTER_LIN_MIP_LIN))
        self.assertEqual(first.mip_data_length - first.data_length, 0x10000)
        self.assertEqual(infos[1].data_addr, first.data_addr + first.mip_data_length)
        self.assertEqual(tpl.typical_mip_count(self.texpack), tpl.MAP_MIP_COUNT)

    def test_vanilla_mip_is_a_box_reduction(self):
        base, mip = tpl.read_mip_levels(self.texpack, 1)
        self.assertLess(_mean_error(mip, base.resize(mip.size, Image.BOX)), 2)

    def test_round_trip_replace_and_select(self):
        info = tpl.read_tpl_image_info(io.BytesIO(self.texpack))[1]
        base = tpl.read_tpl_images(io.BytesIO(self.texpack))[1]
        patched = tpl.replace_image(self.texpack, 1, base)
        self.assertEqual(len(patched), len(self.texpack))
        end = info.data_addr + info.mip_data_length
        self.assertEqual(patched[:info.data_addr], self.texpack[:info.data_addr])
        self.assertEqual(patched[end:], self.texpack[end:])
        old_levels = tpl.read_mip_levels(self.texpack, 1)
        for got, want in zip(tpl.read_mip_levels(patched, 1), old_levels):
            self.assertLess(_mean_error(got, want), 2)
        count = len(tpl.read_tpl_image_info(io.BytesIO(self.texpack)))
        rebuilt = tpl.select_images(self.texpack, range(count))
        self.assertEqual(tpl.image_keys(rebuilt), tpl.image_keys(self.texpack))
        for i in range(count):
            self.assertEqual(
                [lvl.tobytes() for lvl in tpl.read_mip_levels(rebuilt, i)],
                [lvl.tobytes() for lvl in tpl.read_mip_levels(self.texpack, i)],
            )


if __name__ == "__main__":
    unittest.main()
