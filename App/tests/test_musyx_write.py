import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import gcfesnd, musyx, musyx_write

NUL = bytes([0])


def _group(group_id, macros, samples, fx, next_offset_holder):
    """One FX group laid out like the game's: header, id lists, FX table."""
    header_size = 0x28
    lists = b"".join(struct.pack(f">{len(ids) + 1}H", *ids, 0xFFFF) for ids in (macros, samples, [], [], []))
    macro_off = next_offset_holder + header_size
    offsets = []
    position = macro_off
    for ids in (macros, samples, [], [], []):
        offsets.append(position)
        position += 2 * (len(ids) + 1)
    position += -position % 4
    lists += bytes(position - (macro_off + len(lists)))
    table = struct.pack(">HH", len(fx), 0) + b"".join(struct.pack(">HH6B", *entry) for entry in fx)
    table += bytes(-len(table) % 4)
    end = position + len(table)
    header = struct.pack(">IHH8I", end, group_id, 1, *offsets, position, 0, 0)
    return header + lists + table


def _proj():
    first = _group(1, [5], [3], [(7, 5, 1, 10, 127, 64, 60, 0)], 0)
    second = _group(2, [6], [4], [(9, 6, 1, 10, 100, 64, 60, 0)], len(first))
    return first + second + struct.pack(">I", 0xFFFFFFFF)


def _macro(macro_id, sample_id):
    commands = [(0x38, 0), (0x10 | (sample_id << 8), 0), (0, 0)]
    body = b"".join(struct.pack(">II", a, b) for a, b in commands)
    return struct.pack(">IHH", 8 + len(body), macro_id, 0) + body


def _sdir(samples):
    records = b""
    infos = b""
    base = 32 * len(samples) + 4
    for i, (sample_id, offset) in enumerate(samples):
        info = struct.pack(">HHHH", 8, 0, 0, 0) + struct.pack(">16h", *([0x800, 0] + [0] * 14))
        records += struct.pack(">HHIIIIIII", sample_id, 0, offset, 0, (60 << 24) | 32000, 14, 0, 0, base + 0x28 * i)
        infos += info
    return records + struct.pack(">HH", 0xFFFF, 0) + infos


def _write_bank(directory: Path) -> None:
    macros = _macro(5, 3) + _macro(6, 4) + struct.pack(">I", 0xFFFFFFFF)
    pool = struct.pack(">4I", 0x10, 0x10 + len(macros), 0, 0x10 + len(macros)) + macros
    frame = bytes([0x01]) + bytes([0x11] * 7)
    (directory / "gcfesnd.pool").write_bytes(pool)
    (directory / "gcfesnd.proj").write_bytes(_proj())
    (directory / "gcfesnd.sdir").write_bytes(_sdir([(3, 0), (4, 0x20)]))
    (directory / "gcfesnd.samp").write_bytes(frame + bytes(0x20 - len(frame)) + frame + bytes(0x20 - len(frame)))


def _container(names, sound_ids=None):
    """Minimal gcfesnd.bin: SFX records, terminator, label pool, relocations, one section."""
    pool = bytearray()
    offsets = {}
    count = len(names)
    records_size = SFX = 20 * count + 8
    for name in names:
        offsets[name] = records_size + len(pool)
        pool += name.encode("ascii") + NUL
    pool += bytes(-len(pool) % 4)
    records = bytearray()
    for i, name in enumerate(names):
        records += struct.pack(">IBBBBI4sI", offsets[name], 20, 0, 127, 64, (sound_ids or list(range(count)))[i], bytes([30, 0, 0, 0]), 200)
    records += bytes(8)
    body = bytes(records) + bytes(pool)
    relocs = [20 * i for i in range(count)]
    sections = struct.pack(">II", 0, 0) + b"Table" + NUL
    header = struct.pack(">5I", 0x20 + len(body) + 4 * len(relocs) + len(sections), len(body), len(relocs), 1, 0) + bytes(12)
    return header + body + struct.pack(f">{len(relocs)}I", *relocs) + sections


class MusyxWriteTests(unittest.TestCase):
    def test_add_cue_adds_a_playable_cue_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_bank(directory)
            (directory / "gcfesnd.bin").write_bytes(_container(["SFX_ONE", "SFX_TWO"]))
            banks = musyx.SoundBanks(directory)
            before = {fx: banks.resolve(fx) and banks.resolve(fx)[1] for fx in (7, 9)}
            pcm = [int(8000 * math.sin(i / 3)) for i in range(400)]

            sound, files = musyx_write.add_cue(directory, "SFX_NEW_TONE", "gcfesnd", 1, pcm, 22050, volume=90)
            for name, data in files.items():
                (directory / name).write_bytes(data)

            banks = musyx.SoundBanks(directory)
            self.assertEqual({fx: banks.resolve(fx)[1] for fx in (7, 9)}, before)
            cues = gcfesnd.read_sfx_cues_path(directory / "gcfesnd.bin")
            self.assertEqual([c.name for c in cues], ["SFX_ONE", "SFX_TWO", "SFX_NEW_TONE"])
            self.assertEqual((cues[2].sound_id, cues[2].volume), (sound.fx_id, 90))
            rendered = banks.render(sound.fx_id)
            self.assertEqual((rendered.sample_rate, len(rendered.samples)), (22050, 400))
            error = max(abs(a - b) for a, b in zip(rendered.samples, pcm))
            self.assertLess(error, 2500)
            bank = banks.banks[0]
            self.assertEqual(bank.fx[sound.fx_id].group_id, 1)
            self.assertEqual(bank.fx[9].group_id, 2)  # the group after the edited one still resolves

    def test_replace_cue_repoints_only_that_cue(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_bank(directory)
            (directory / "gcfesnd.bin").write_bytes(_container(["SFX_ONE", "SFX_TWO"], [7, 9]))
            sound, files = musyx_write.replace_cue(directory, "SFX_TWO", [1000, -1000] * 50, 32000)
            for name, data in files.items():
                (directory / name).write_bytes(data)
            cues = {c.name: c for c in gcfesnd.read_sfx_cues_path(directory / "gcfesnd.bin")}
            self.assertEqual(cues["SFX_ONE"].sound_id, 7)
            self.assertEqual(cues["SFX_TWO"].sound_id, sound.fx_id)
            bank = musyx.SoundBanks(directory).banks[0]
            self.assertEqual(bank.fx[sound.fx_id].group_id, 2)  # the old sound's group
            self.assertEqual(bank.fx[sound.fx_id].volume, 100)  # and its settings
            self.assertEqual(bank.fx[9].macro, 6)  # the old sound itself is untouched

    def test_replace_needs_a_group_for_unknown_sounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_bank(directory)
            (directory / "gcfesnd.bin").write_bytes(_container(["SFX_ONE", "SFX_TWO"], [7, 0x0606]))
            with self.assertRaises(musyx.MusyxError):
                musyx_write.replace_cue(directory, "SFX_TWO", [1000, -1000] * 50, 32000)
            sound, _files = musyx_write.replace_cue(directory, "SFX_TWO", [1000, -1000] * 50, 32000,
                                                    bank_name="gcfesnd", group_id=1)
            self.assertGreater(sound.fx_id, 9)

    def test_names_and_duplicates_are_rejected(self):
        data = _container(["SFX_ONE"])
        with self.assertRaises(gcfesnd.GcfesndError):
            gcfesnd.add_sfx_cue(data, "SFX_ONE", flags=0, volume=1, pan=1, sound_id=1, extra=bytes(4), range_value=1)
        with self.assertRaises(gcfesnd.GcfesndError):
            gcfesnd.validate_sfx_name("sfx_lower")
        with self.assertRaises(gcfesnd.GcfesndError):
            gcfesnd.validate_sfx_name("BGM_NOPE")

    def test_container_growth_keeps_pointers_valid(self):
        data = _container(["SFX_ONE", "SFX_TWO"])
        out = gcfesnd.add_sfx_cue(data, "SFX_THREE", flags=8, volume=7, pan=9, sound_id=11,
                                  extra=bytes([1, 2, 3, 4]), range_value=5)
        cues = gcfesnd.read_sfx_cues(out)
        self.assertEqual([c.name for c in cues], ["SFX_ONE", "SFX_TWO", "SFX_THREE"])
        self.assertEqual((cues[2].flags, cues[2].volume, cues[2].pan, cues[2].sound_id, cues[2].extra, cues[2].range_value),
                         (8, 7, 9, 11, bytes([1, 2, 3, 4]), 5))
        self.assertEqual(struct.unpack_from(">I", out, 0)[0], len(out))
        relocs = struct.unpack_from(">3I", out, 0x20 + struct.unpack_from(">I", out, 4)[0])
        self.assertEqual(relocs, (0, 20, 40))


if __name__ == "__main__":
    unittest.main()
