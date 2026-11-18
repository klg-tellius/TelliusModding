"""Smaller formats on synthetic files (no disc needed, runs in CI): the Radiant Dawn staff roll,
LZ10 pack textures and the Wii disc banner."""

import hashlib
import struct
import unittest

from synthetic_data import data_container, wii_banner_file

from fe_modding.formats import fe10_staffroll, lz10, message, packed_texture, pak, wii_banner


def _ending(lines: list[tuple[str, str, str]], *, title: str | None = "スタッフ", copyright_lines: bool = True,
            count_text: str | None = None, encoding: str = "cp932") -> bytes:
    def stored(text: str) -> str:
        return text.encode(encoding).decode("cp437")

    messages = []
    if copyright_lines:
        messages += [message.Message(key, stored(f"(C) line {n}"))
                     for n, key in enumerate(fe10_staffroll.COPYRIGHT, 1)]
    for n, (role, heading, name) in enumerate(lines):
        messages += [message.Message(fe10_staffroll.LINE_KEY.format(n, "C"), stored(heading)),
                     message.Message(fe10_staffroll.LINE_KEY.format(n, "L"), stored(role)),
                     message.Message(fe10_staffroll.LINE_KEY.format(n, "R"), stored(name))]
    messages.append(message.Message(fe10_staffroll.LINES, count_text or f" {len(lines)} "))
    if title is not None:
        messages.append(message.Message(fe10_staffroll.TITLE, stored(title)))
    messages.append(message.Message("MED_OTHER", "kept"))
    return message.write_messages(messages)


def _timings() -> bytes:
    body = bytearray()
    symbols = []
    for label, (fmt, _meaning) in fe10_staffroll.TIMINGS.items():
        symbols.append((label, len(body)))
        body += struct.pack(fmt, 1.5 if fmt == ">f" else 1000 + len(body))
    return data_container(bytes(body), [], symbols)


class StaffRollTests(unittest.TestCase):
    LINES = [("Director", "", "Someone"), ("", "Programming", ""), ("", "", ""), ("音楽", "", "名前")]

    def test_read_and_rebuild_unchanged(self):
        data = _ending(self.LINES)
        roll = fe10_staffroll.read_rd_staffroll(data)
        self.assertEqual(roll.lines, self.LINES)
        self.assertEqual(roll.title, "スタッフ")
        self.assertEqual(roll.copyright[4], "(C) line 5")
        self.assertEqual([m.speaker for m in roll.others], ["MED_OTHER"])
        self.assertEqual(fe10_staffroll.build_rd_staffroll(roll), data)

    def test_edited_lines_rewrite_the_count(self):
        data = _ending(self.LINES, count_text="4")
        roll = fe10_staffroll.read_rd_staffroll(data)
        self.assertEqual(fe10_staffroll.build_rd_staffroll(roll), data)  # unchanged count text kept
        roll.lines.append(("Tester", "", "Name"))
        again = fe10_staffroll.read_rd_staffroll(fe10_staffroll.build_rd_staffroll(roll))
        self.assertEqual(again.count_text, " 5 ")
        self.assertEqual(again.lines[-1], ("Tester", "", "Name"))

    def test_file_without_title_or_copyright(self):
        data = _ending(self.LINES[:1], title=None, copyright_lines=False)
        roll = fe10_staffroll.read_rd_staffroll(data)
        self.assertFalse(roll.has_title or roll.has_copyright)
        self.assertEqual(fe10_staffroll.build_rd_staffroll(roll), data)

    def test_european_encoding(self):
        data = _ending([("Régie", "", "Zoë")], title="Générique", encoding="cp1252")
        roll = fe10_staffroll.read_rd_staffroll(data, "cp1252")
        self.assertEqual((roll.title, roll.lines), ("Générique", [("Régie", "", "Zoë")]))
        self.assertEqual(fe10_staffroll.build_rd_staffroll(roll, "cp1252"), data)

    def test_refusals(self):
        with self.assertRaises(fe10_staffroll.Fe10StaffRollError):
            fe10_staffroll.read_rd_staffroll(message.write_messages([message.Message("A", "b")]))
        with self.assertRaises(fe10_staffroll.Fe10StaffRollError):
            fe10_staffroll.read_rd_staffroll(_ending([], count_text="many"))
        roll = fe10_staffroll.read_rd_staffroll(_ending(self.LINES))
        roll.lines[0] = ("Ω€", "", "")
        with self.assertRaises(fe10_staffroll.Fe10StaffRollError):
            fe10_staffroll.build_rd_staffroll(roll, "cp1252")
        roll.copyright = roll.copyright[:4]
        with self.assertRaises(fe10_staffroll.Fe10StaffRollError):
            fe10_staffroll.build_rd_staffroll(roll)

    def test_timings(self):
        data = _timings()
        values = fe10_staffroll.read_timings(data)
        self.assertEqual(values["LBL_STAFFROLL_SCROLLSPEED"], 1.5)
        self.assertEqual(len(values), len(fe10_staffroll.TIMINGS))
        out = fe10_staffroll.set_timing(data, "LBL_STAFFROLL_SCROLLSPEED", 2.25)
        out = fe10_staffroll.set_timing(out, "LBL_STAFFROLL_LYRIC", 42)
        self.assertEqual(len(out), len(data))
        values = fe10_staffroll.read_timings(out)
        self.assertEqual((values["LBL_STAFFROLL_SCROLLSPEED"], values["LBL_STAFFROLL_LYRIC"]), (2.25, 42))
        for label, value in (("LBL_NOPE", 1), ("LBL_STAFFROLL_LYRIC", -1), ("LBL_STAFFROLL_LYRIC", 1.5)):
            with self.assertRaises(fe10_staffroll.Fe10StaffRollError):
                fe10_staffroll.set_timing(data, label, value)
        with self.assertRaises(fe10_staffroll.Fe10StaffRollError):
            fe10_staffroll.read_timings(data_container(b"\0" * 4, [], [("LBL_STAFFROLL_SCROLLSPEED", 0)]))


class PackedTextureTests(unittest.TestCase):
    def test_replace_keeps_other_members_and_reserved_words(self):
        archive = lz10.compress(pak.pack_pak([("a.bin", b"first"), ("sky.tpl", b"\x00\x20\xaf\x30old"),
                                              ("b.bin", b"last")], [7, 8, 9]))
        self.assertEqual(packed_texture.read_packed_tpl(archive), b"\x00\x20\xaf\x30old")
        out = packed_texture.replace_packed_tpl(archive, b"\x00\x20\xaf\x30new texture")
        self.assertEqual(packed_texture.read_packed_tpl(out), b"\x00\x20\xaf\x30new texture")
        unpacked = lz10.decompress(out)
        entries = pak.read_pak_entries(unpacked)
        self.assertEqual([(e.name, e.reserved) for e in entries], [("a.bin", 7), ("sky.tpl", 8), ("b.bin", 9)])
        self.assertEqual(pak.read_pak_file_content(unpacked, entries[2]), b"last")

    def test_needs_exactly_one_texture(self):
        for files in ([("a.bin", b"x")], [("a.tpl", b"x"), ("b.TPL", b"y")]):
            archive = lz10.compress(pak.pack_pak(files))
            with self.assertRaises(ValueError):
                packed_texture.read_packed_tpl(archive)
            with self.assertRaises(ValueError):
                packed_texture.replace_packed_tpl(archive, b"")


class WiiBannerTests(unittest.TestCase):
    TITLES = [("ファイアーエムブレム", "暁の女神")] + [("Fire Emblem", "Radiant Dawn")] * 9

    def setUp(self):
        self.data = wii_banner_file(self.TITLES)

    def test_reads_titles_and_parts(self):
        banner = wii_banner.read_banner(self.data)
        self.assertEqual(banner.titles, self.TITLES)
        self.assertEqual([e.path for e in banner.archive],
                         ["meta", "meta/icon.bin", "meta/banner.bin", "meta/sound.bin"])
        self.assertEqual([e.path for e in banner.pictures("banner.bin")], ["arc/timg/bg.tpl"])
        self.assertEqual(banner.pictures("banner.bin")[0].data, bytes(range(64)))

    def test_unchanged_banner_rebuilds_byte_identically(self):
        self.assertEqual(wii_banner.build_banner(wii_banner.read_banner(self.data)), self.data)

    def test_title_edit_refreshes_the_hash(self):
        banner = wii_banner.read_banner(self.data)
        banner.titles[1] = ("Fire Emblem", "Mod")
        out = wii_banner.build_banner(banner)
        self.assertEqual(wii_banner.read_banner(out).titles[1], ("Fire Emblem", "Mod"))
        self.assertEqual(out[wii_banner.HEADER_END:], self.data[wii_banner.HEADER_END:])
        header = bytearray(out[:wii_banner.HEADER_END])
        stored = bytes(header[wii_banner.HASH_OFFSET:])
        header[wii_banner.HASH_OFFSET:] = bytes(16)
        self.assertEqual(hashlib.md5(bytes(header)).digest(), stored)
        banner.titles[2] = ("x" * 22, "")
        with self.assertRaises(wii_banner.BannerError):
            wii_banner.build_banner(banner)

    def test_picture_replacement_rewraps_its_part(self):
        banner = wii_banner.read_banner(self.data)
        banner.replace_file("icon.bin", "arc/timg/icon.tpl", b"new picture")
        out = wii_banner.build_banner(banner)
        again = wii_banner.read_banner(out)
        self.assertEqual(again.pictures("icon.bin")[0].data, b"new picture")
        self.assertEqual(again.pictures("banner.bin")[0].data, bytes(range(64)))
        icon_entry = next(e for e in again.archive if e.path == "meta/icon.bin")
        payload, compressed = wii_banner.unwrap(icon_entry.data)
        self.assertTrue(compressed)
        self.assertEqual(struct.unpack_from(">I", out, wii_banner.IMET_OFFSET + 12)[0], len(payload))
        self.assertEqual(icon_entry.data[16:32], hashlib.md5(icon_entry.data[32:]).digest())
        with self.assertRaises(wii_banner.BannerError):
            banner.replace_file("icon.bin", "arc/timg/none.tpl", b"")

    def test_refusals(self):
        with self.assertRaises(wii_banner.BannerError):
            wii_banner.read_banner(bytes(0x600))
        with self.assertRaises(wii_banner.BannerError):
            wii_banner.read_u8(b"nope")
        with self.assertRaises(wii_banner.BannerError):
            wii_banner.unwrap(b"LZ77")
        with self.assertRaises(wii_banner.BannerError):
            wii_banner.build_u8([wii_banner.U8Entry("dir/file", b"x")])


if __name__ == "__main__":
    unittest.main()
