import os
import struct
import unittest
from pathlib import Path

from fe_modding.formats import brsar, brstm, fe10_sound, lz10, rbnk, rseq, rwsd, soundroom, thp


class BrstmValidationTests(unittest.TestCase):
    def test_rejects_non_rstm(self):
        with self.assertRaises(brstm.BrstmError):
            brstm.read_info(bytes(0x40))

    def test_rejects_mismatched_file_size(self):
        data = bytearray(0x40)
        data[:4] = b"RSTM"
        data[4:8] = b"\xfe\xff\x01\x00"
        with self.assertRaises(brstm.BrstmError):
            brstm.read_info(bytes(data))


class BrsarValidationTests(unittest.TestCase):
    def test_rejects_non_rsar(self):
        with self.assertRaises(brsar.BrsarError):
            brsar.read_brsar(bytes(0x40))


class RwsdValidationTests(unittest.TestCase):
    @staticmethod
    def _pcm16_fixture() -> tuple[bytes, bytes]:
        data_offset = 0x20
        data_size = 0x88
        wave_offset = data_offset + data_size
        wave_size = 0x4C
        out = bytearray(wave_offset + wave_size)
        out[:4] = b"RWSD"
        struct.pack_into(">HHIHH", out, 4, 0xFEFF, 0x0102, len(out), 0x20, 2)
        struct.pack_into(">4I", out, 0x10, data_offset, data_size, wave_offset, wave_size)
        out[data_offset:data_offset + 4] = b"DATA"
        struct.pack_into(">I", out, data_offset + 4, data_size)
        base = data_offset + 8
        struct.pack_into(">I2I", out, base, 1, 1, 0x0C)
        entry = base + 0x0C
        struct.pack_into(">2I", out, entry, 1, 0x24)
        struct.pack_into(">2I", out, entry + 8, 0, 0)
        struct.pack_into(">2I", out, entry + 16, 1, 0x44)
        struct.pack_into(">f4B", out, base + 0x24, 1.0, 64, 0, 0, 0)
        note_table = base + 0x44
        struct.pack_into(">I2I", out, note_table, 1, 1, 0x50)
        note = base + 0x50
        struct.pack_into(">I", out, note, 0)
        out[note + 9] = 127
        struct.pack_into(">f", out, note + 0x10, 1.0)
        out[wave_offset:wave_offset + 4] = b"WAVE"
        struct.pack_into(">II", out, wave_offset + 4, wave_size, 1)
        struct.pack_into(">I", out, wave_offset + 12, 0x10)
        wave = wave_offset + 0x10
        struct.pack_into(">4BH", out, wave, 1, 0, 1, 0, 22050)
        struct.pack_into(">4I", out, wave + 8, 0, 3, 0x1C, 0)
        struct.pack_into(">I", out, wave + 0x1C, 0x20)
        struct.pack_into(">2I", out, wave + 0x20, 0, 0)
        return bytes(out), struct.pack(">3h", -32768, 0, 32767)

    def test_pcm16_entry_decode_and_render(self):
        header, samples = self._pcm16_fixture()
        document = rwsd.read_rwsd(header, samples)
        self.assertEqual((len(document.entries), len(document.waves)), (1, 1))
        audio = rwsd.render_entry(document, 0)
        self.assertEqual(audio.sample_rate, 22050)
        self.assertEqual(audio.channels, ((-32768, 0, 32767),))

    def test_rejects_missing_wave_payload(self):
        header, _samples = self._pcm16_fixture()
        with self.assertRaises(rwsd.RwsdError):
            rwsd.read_rwsd(header, b"")


class SoundRoomBuilderTests(unittest.TestCase):
    def test_variable_radiant_dawn_tables_and_string_pool(self):
        entries = [soundroom.SoundRoomEntry("RID_ONE", 1, -2, 0x640000)]
        tracks = [soundroom.SoundRoomTrack("BGM_ROOM_ONE", 7)]
        original = soundroom.build_fe10_soundroom(entries, tracks)
        self.assertEqual(soundroom.build_fe10_soundroom(entries, tracks, original), original)

        changed_entries = entries + [soundroom.SoundRoomEntry("RID_TWO", -3, 4, 0x3F0000)]
        changed_tracks = tracks + [soundroom.SoundRoomTrack("BGM_ROOM_TWO", 9)]
        rebuilt = soundroom.build_fe10_soundroom(changed_entries, changed_tracks, original)
        self.assertEqual(soundroom.read_soundroom(rebuilt), changed_entries)
        self.assertEqual(soundroom.read_soundroom_tracks(rebuilt), changed_tracks)
        _size, data_size, pointer_count, symbol_count = struct.unpack_from(">4I", rebuilt)
        self.assertEqual((pointer_count, symbol_count), (4, 0))
        relocation = struct.unpack_from(">4I", rebuilt, 0x20 + data_size)
        self.assertEqual(relocation, (4, 16, 32, 40))


class RseqValidationTests(unittest.TestCase):
    def test_reads_and_collects_simple_note(self):
        commands = bytes((0x81, 0, 60, 127, 24, 0xFF))
        data_size = 12 + len(commands)
        label_size = 12
        total = 0x20 + data_size + label_size
        source = bytearray(total)
        source[:4] = b"RSEQ"
        struct.pack_into(">HHIHH", source, 4, 0xFEFF, 0x0100, total, 0x20, 2)
        struct.pack_into(">4I", source, 0x10, 0x20, data_size, 0x20 + data_size, label_size)
        source[0x20:0x24] = b"DATA"
        struct.pack_into(">2I", source, 0x24, data_size, 12)
        source[0x2C:0x2C + len(commands)] = commands
        label = 0x20 + data_size
        source[label:label + 4] = b"LABL"
        struct.pack_into(">2I", source, label + 4, label_size, 0)
        sequence = rseq.read_rseq(bytes(source))
        notes, timebase, tempo = rseq.collect_notes(sequence)
        self.assertEqual((timebase, tempo), (48, 120))
        self.assertEqual(notes, [rseq.SequenceNote(0, 24, 60, 127, 0, 127, 64)])


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"),
                     "set FE10_EXTRACTED_FILES to RFEE01's extracted files directory")
class RadiantDawnAudioCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ["FE10_EXTRACTED_FILES"])

    def test_every_brstm_header_and_representative_audio(self):
        paths = sorted((self.root / "Sound" / "strm").glob("*.brstm"))
        self.assertEqual(len(paths), 1186)
        shapes = set()
        for path in paths:
            info = brstm.read_info(path.read_bytes())
            shapes.add((info.channel_count, info.sample_rate, info.loop_start is not None))
        self.assertIn((1, 22050, False), shapes)
        self.assertIn((1, 44100, False), shapes)
        self.assertIn((2, 32000, True), shapes)
        dummy = self.root / "Sound" / "strm" / "DUMMY.brstm"
        raw = dummy.read_bytes()
        audio = brstm.read_brstm(raw)
        rebuilt = brstm.write_brstm(audio, raw)
        self.assertEqual(rebuilt, raw)
        reread = brstm.read_brstm(rebuilt)
        self.assertEqual(reread, audio)
        changed_channels = [list(channel) for channel in audio.channels]
        changed_channels[0][0] = 1200
        changed = brstm.BrstmAudio(audio.sample_rate, changed_channels, audio.loop_start)
        changed_bytes = brstm.write_brstm(changed, raw)
        changed_info = brstm.read_info(changed_bytes)
        self.assertEqual((changed_info.sample_rate, changed_info.channel_count, changed_info.sample_count),
                         (audio.sample_rate, len(audio.channels), len(audio.channels[0])))
        self.assertNotEqual(brstm.read_brstm(changed_bytes).channels[0][0], 0)

    def test_sound_catalogs_and_archives(self):
        expected = {"sound_data.cms": 3334, "sound_data_en.cms": 3335}
        for name, count in expected.items():
            data = lz10.decompress((self.root / "Sound" / name).read_bytes())
            cues = fe10_sound.read_sound_data(data)
            self.assertEqual(len(cues), count)
            base = next(cue for cue in cues if cue.name == "BGM_BASE1")
            self.assertEqual(fe10_sound.repoint_cue(data, base.name, base.resource), data)
        for name, count in (("sound.brsar", 2307), ("sound_us.brsar", 2310)):
            data = (self.root / "Sound" / name).read_bytes()
            archive = brsar.read_brsar(data)
            self.assertEqual(len(archive.symbols), count)
            self.assertEqual(brsar.build_brsar(archive), data)
            self.assertIn("STRM_BGM_BTL_BOSS4", archive.symbols)
            self.assertGreater(len(archive.files), 1000)
            self.assertGreater(len(archive.sounds), 2000)
        active = brsar.read_brsar((self.root / "Sound" / "sound_us.brsar").read_bytes())
        title = next(sound for sound in active.sounds if sound.name == "STRM_BGM_FE_THEME1")
        self.assertEqual(title.external_path, "strm/fe10_bgm_sys_title1_32k.brstm")

        parsed_files = {}
        for file in active.files:
            if file.magic == "RWSD":
                parsed_files[file.index] = rwsd.read_rwsd(file.header, file.wave_data)
        self.assertEqual(len(parsed_files), 180)
        self.assertEqual(sum(len(item.waves) for item in parsed_files.values()), 963)
        wave_sounds = [sound for sound in active.sounds if sound.sound_type == 3]
        self.assertEqual(len(wave_sounds), 1011)
        for sound in wave_sounds:
            document = parsed_files[sound.file_index]
            preview = rwsd.render_entry(document, sound.info_index, max_seconds=0.01)
            self.assertTrue(preview.channels, sound.name)
            self.assertTrue(preview.channels[0], sound.name)
        first_file_index, first_document = next(iter(parsed_files.items()))
        first_file = active.files[first_file_index]
        self.assertEqual(brsar.replace_embedded_file(active, first_file_index, first_file.header,
                                                      first_file.wave_data), active.source)
        original_audio = rwsd.decode_wave(first_document, 0)
        # 994 is exactly 71 DSP frames: this guards WaveInfo's end-nibble
        # address (which includes the next frame's two header nibbles).
        replacement_count = min(994, len(original_audio.channels[0]))
        replacement = rwsd.RwsdAudio(original_audio.sample_rate,
                                     tuple(tuple(channel[:replacement_count])
                                           for channel in original_audio.channels))
        replacement_header, replacement_wave = rwsd.replace_wave(first_document, 0, replacement)
        changed_archive = brsar.read_brsar(brsar.replace_embedded_file(
            active, first_file_index, replacement_header, replacement_wave))
        changed_document = rwsd.read_rwsd(changed_archive.files[first_file_index].header,
                                          changed_archive.files[first_file_index].wave_data)
        self.assertEqual(len(rwsd.decode_wave(changed_document, 0).channels[0]), replacement_count)

        banks = {}
        sequences = {}
        for file in active.files:
            if file.magic == "RBNK":
                banks[file.index] = rbnk.read_rbnk(file.header, file.wave_data)
            elif file.magic == "RSEQ":
                sequences[file.index] = rseq.read_rseq(file.header)
        self.assertEqual((len(banks), len(sequences)), (82, 111))
        sequence_sounds = [sound for sound in active.sounds if sound.sound_type == 1]
        self.assertEqual(len(sequence_sounds), 376)
        for sound in sequence_sounds:
            notes, _timebase, _tempo = rseq.collect_notes(sequences[sound.file_index], sound.info_index)
            self.assertTrue(notes, sound.name)
        sample = sequence_sounds[0]
        bank_file = active.banks[sample.bank_index].file_index
        rate, pcm = rseq.render_sequence(sequences[sample.file_index], banks[bank_file], sample.info_index,
                                         max_seconds=2)
        self.assertEqual(rate, 32000)
        self.assertTrue(pcm.any())

    def test_radiant_dawn_soundroom_fixed_width_round_trip(self):
        data = (self.root / "soundroom.bin").read_bytes()
        entries = soundroom.read_soundroom(data)
        self.assertEqual(len(entries), 50)
        self.assertTrue(all(entry.extra_word is not None for entry in entries))
        self.assertEqual(soundroom.build_soundroom(entries, data), data)
        reordered = list(entries)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        self.assertEqual(soundroom.read_soundroom(soundroom.build_soundroom(reordered, data)), reordered)
        reused_entries = [soundroom.SoundRoomEntry(entries[0].name, item.x, item.y, item.extra_word)
                          for item in entries]
        reused_data = soundroom.build_soundroom(reused_entries, data)
        self.assertEqual(soundroom.build_soundroom(entries, reused_data), data)

        added_entries = entries + [soundroom.SoundRoomEntry("RID_PHASE7_NEW", 4, -8, entries[0].extra_word)]
        added_data = soundroom.build_soundroom(added_entries, data)
        self.assertEqual(soundroom.read_soundroom(added_data), added_entries)
        self.assertEqual(soundroom.read_soundroom_tracks(added_data), soundroom.read_soundroom_tracks(data))
        self.assertLess(len(soundroom.build_soundroom(entries, added_data)), len(added_data))

        tracks = soundroom.read_soundroom_tracks(data)
        self.assertEqual(len(tracks), 85)
        self.assertEqual(soundroom.build_soundroom_tracks(data, tracks), data)
        reordered_tracks = list(tracks)
        reordered_tracks[0], reordered_tracks[1] = reordered_tracks[1], reordered_tracks[0]
        rebuilt = soundroom.build_soundroom_tracks(data, reordered_tracks)
        self.assertEqual(soundroom.read_soundroom_tracks(rebuilt), reordered_tracks)
        self.assertEqual(rebuilt[:0x20 + 4 + len(entries) * 12], data[:0x20 + 4 + len(entries) * 12])
        reused_tracks = [soundroom.SoundRoomTrack(tracks[0].cue, item.unlock_id) for item in tracks]
        reused_track_data = soundroom.build_soundroom_tracks(data, reused_tracks)
        self.assertEqual(soundroom.build_soundroom_tracks(reused_track_data, tracks), data)

        added_tracks = tracks + [soundroom.SoundRoomTrack("BGM_ROOM_PHASE7_NEW", 0x12345678)]
        added_track_data = soundroom.build_soundroom_tracks(data, added_tracks)
        self.assertEqual(soundroom.read_soundroom_tracks(added_track_data), added_tracks)
        self.assertEqual(soundroom.read_soundroom(added_track_data), entries)

    def test_all_radiant_dawn_movies_use_the_shared_thp_codec(self):
        paths = sorted((self.root / "Movie").glob("*.thp"))
        self.assertEqual(len(paths), 20)
        for path in paths:
            with path.open("rb") as stream:
                info = thp.read_info(stream)
                offsets = thp.iter_frame_offsets(stream, info)
            self.assertEqual(len(offsets), info.num_frames, path.name)
            self.assertIn(info.height, (448, 480))
            self.assertEqual(info.width, 608)


if __name__ == "__main__":
    unittest.main()
