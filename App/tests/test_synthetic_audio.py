"""Radiant Dawn audio formats on synthetic files (no disc needed, runs in CI): BRSTM streams and
the ``sound_data.cms`` cue registry."""

import math
import tempfile
import unittest
from pathlib import Path

from synthetic_data import brstm_template, rwsd_file, sound_data_file

from fe_modding.formats import brstm, dsp_adpcm, fe10_sound, rwsd


def _tone(count: int, amplitude: int, period: float) -> list[int]:
    return [int(amplitude * math.sin(i / period)) for i in range(count)]


class BrstmSyntheticTests(unittest.TestCase):
    def test_template_reads(self):
        for channels in (1, 2):
            info = brstm.read_info(brstm_template(channels))
            self.assertEqual((info.channel_count, info.sample_count, info.block_count), (channels, 14, 1))
            audio = brstm.read_brstm(brstm_template(channels))
            self.assertEqual(audio.channels, [[0] * 14] * channels)
            self.assertIsNone(audio.loop_start)

    def test_unchanged_audio_returns_the_template(self):
        template = brstm_template()
        self.assertEqual(brstm.write_brstm(brstm.read_brstm(template), template), template)

    def test_multi_block_encode_decodes_close_to_the_source(self):
        template = brstm_template(2, block_size=0x100)
        pcm = [_tone(1500, 8000, 10.0), _tone(1500, 5000, 7.0)]
        out = brstm.write_brstm(brstm.BrstmAudio(22050, pcm, loop_start=100), template)
        info = brstm.read_info(out)
        self.assertEqual((info.sample_rate, info.sample_count, info.loop_start), (22050, 1500, 100))
        self.assertEqual(info.block_count, math.ceil(1500 / info.samples_per_block))
        self.assertEqual(len(out) % 0x20, 0)
        decoded = brstm.read_brstm(out)
        for source, back in zip(pcm, decoded.channels):
            self.assertEqual(len(back), 1500)
            error = math.sqrt(sum((a - b) ** 2 for a, b in zip(source, back)) / len(source))
            self.assertLess(error, 400)  # lossy 4-bit ADPCM, but the same waveform

    def test_adpc_history_matches_the_decoded_samples(self):
        template = brstm_template(1, block_size=0x40)  # 112 samples per block
        pcm = [_tone(500, 6000, 5.0)]
        out = brstm.write_brstm(brstm.BrstmAudio(32000, pcm), template)
        info = brstm.read_info(out)
        decoded = brstm.read_brstm(out).channels[0]
        import struct
        for block in range(1, info.block_count):
            hist1, hist2 = struct.unpack_from(">hh", out, info.adpc_offset + 8 + 4 * block)
            start = block * info.samples_per_block
            self.assertEqual((hist1, hist2), (decoded[start - 1], decoded[start - 2]), f"block {block}")

    def test_writer_refuses_bad_audio(self):
        template = brstm_template(2)
        for audio in (brstm.BrstmAudio(32000, [[1, 2, 3]]),                 # channel count differs
                      brstm.BrstmAudio(32000, [[1, 2], [1]]),               # uneven channels
                      brstm.BrstmAudio(70000, [[1, 2], [1, 2]]),            # rate above 16 bits
                      brstm.BrstmAudio(32000, [[1, 2], [1, 2]], loop_start=2)):
            with self.assertRaises(brstm.BrstmError):
                brstm.write_brstm(audio, template)

    def test_reader_refuses_damaged_headers(self):
        template = bytearray(brstm_template())
        cases = {"version": (6, b"\x02\x00"), "codec": (brstm.read_info(template).stream_info_offset, b"\x01"),
                 "DATA": (brstm.read_info(template).data_offset, b"XXXX")}
        for name, (at, value) in cases.items():
            damaged = bytearray(template)
            damaged[at:at + len(value)] = value
            with self.assertRaises(brstm.BrstmError, msg=name):
                brstm.read_info(damaged)

    def test_wav_round_trip(self):
        audio = brstm.BrstmAudio(16000, [_tone(64, 1000, 3.0), _tone(64, 2000, 4.0)], loop_start=8)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.wav"
            brstm.brstm_to_wav_path(audio, path)
            self.assertEqual(brstm.wav_path_to_brstm_audio(path, loop_start=8), audio)


class DspAdpcmTests(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(dsp_adpcm.bytes_for_adpcm_samples(14), 8)
        self.assertEqual(dsp_adpcm.bytes_for_adpcm_samples(15), 10)

    def test_silence_round_trips_exactly(self):
        info = dsp_adpcm.AdpcmInfo()
        data = dsp_adpcm.encode([0] * 100, info)
        self.assertEqual(dsp_adpcm.decode(data, info, 100), [0] * 100)


class SoundDataTests(unittest.TestCase):
    def setUp(self):
        self.data = sound_data_file([("BGM_TITLE", "STRM_TITLE", 7), ("SFX_HIT", "WSD_HIT", 9),
                                     ("VOICE_IKE_01", "WSD_IKE_01", 11)])

    def test_reads_cues_and_skips_aggregate_tables(self):
        cues = fe10_sound.read_sound_data(self.data)
        self.assertEqual([c.name for c in cues], ["BGM_TITLE", "SFX_HIT", "VOICE_IKE_01"])
        self.assertEqual(cues[1].resource, "WSD_HIT")
        self.assertEqual(cues[1].family, "SFX")
        self.assertEqual(cues[0].raw_words, (7, 1, 2, 3, 4, 5, 6))
        self.assertEqual(fe10_sound.resources(self.data), ("STRM_TITLE", "WSD_HIT", "WSD_IKE_01"))

    def test_repoint_is_fixed_width(self):
        out = fe10_sound.repoint_cue(self.data, "SFX_HIT", "WSD_IKE_01")
        self.assertEqual(len(out), len(self.data))
        self.assertEqual(fe10_sound.cue_map(out)["SFX_HIT"].resource, "WSD_IKE_01")
        with self.assertRaises(fe10_sound.Fe10SoundError):
            fe10_sound.repoint_cue(self.data, "SFX_NONE", "WSD_HIT")
        with self.assertRaises(fe10_sound.Fe10SoundError):
            fe10_sound.repoint_cue(self.data, "SFX_HIT", "WSD_UNKNOWN")

    def test_add_and_remove_cue(self):
        out = fe10_sound.add_cue(self.data, "SFX_NEW_1", "WSD_NEW", "SFX_HIT")
        cue = fe10_sound.cue_map(out)["SFX_NEW_1"]
        self.assertEqual((cue.resource, cue.raw_words), ("WSD_NEW", (9, 1, 2, 3, 4, 5, 6)))
        self.assertEqual(len(fe10_sound.read_sound_data(out)), 4)
        for name, template in (("SFX_HIT", "SFX_HIT"), ("bad name", "SFX_HIT"), ("SFX_X", "SFX_NONE")):
            with self.assertRaises(fe10_sound.Fe10SoundError):
                fe10_sound.add_cue(out, name, "WSD_NEW", template)
        removed = fe10_sound.remove_cue(out, "SFX_NEW_1", self.data)
        self.assertNotIn("SFX_NEW_1", fe10_sound.cue_map(removed))
        with self.assertRaisesRegex(fe10_sound.Fe10SoundError, "game's own"):
            fe10_sound.remove_cue(out, "SFX_HIT", self.data)

    def test_truncated_container_is_refused(self):
        with self.assertRaises(fe10_sound.Fe10SoundError):
            fe10_sound.read_sound_data(self.data[:-4])


class RwsdSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.tone = _tone(300, 6000, 6.0)
        self.header, self.payload = rwsd_file([(2, self.tone, 32000), (1, [1, -2, 3], 22050)])
        self.doc = rwsd.read_rwsd(self.header, self.payload)

    def test_reads_entries_and_waves(self):
        self.assertEqual([e.wave_index for e in self.doc.entries], [0, 1])
        self.assertEqual([(w.encoding, w.sample_count, w.sample_rate) for w in self.doc.waves],
                         [(2, 300, 32000), (1, 3, 22050)])
        self.assertEqual(rwsd.decode_wave(self.doc, 1).channels, ((1, -2, 3),))
        decoded = rwsd.decode_wave(self.doc, 0).channels[0]
        self.assertLess(max(abs(a - b) for a, b in zip(decoded, self.tone)), 600)

    def test_unchanged_audio_keeps_the_bytes(self):
        audio = rwsd.decode_wave(self.doc, 1)
        self.assertEqual(rwsd.replace_wave(self.doc, 1, audio), (self.header, self.payload))

    def test_longer_replacement_moves_the_next_wave(self):
        longer = rwsd.RwsdAudio(16000, (tuple(_tone(800, 3000, 4.0)),), loop_start=100)
        header, payload = rwsd.replace_wave(self.doc, 0, longer)
        doc = rwsd.read_rwsd(header, payload)
        self.assertEqual((doc.waves[0].sample_count, doc.waves[0].loop_start, doc.waves[0].sample_rate),
                         (800, 100, 16000))
        self.assertEqual(rwsd.decode_wave(doc, 1).channels, ((1, -2, 3),))  # neighbour kept
        self.assertEqual(len(header), len(self.header))  # wave infos are fixed size
        looped = rwsd.render_entry(doc, 0, loop_count=1)
        self.assertEqual(len(looped.channels[0]), 800 + 700)

    def test_pcm_wave_replaced_by_adpcm(self):
        header, payload = rwsd.replace_wave(self.doc, 1, rwsd.RwsdAudio(8000, ((5,) * 50,)))
        doc = rwsd.read_rwsd(header, payload)
        self.assertEqual((doc.waves[1].encoding, doc.waves[1].sample_count), (2, 50))
        self.assertEqual(rwsd.decode_wave(doc, 0), rwsd.decode_wave(self.doc, 0))

    def test_refusals(self):
        mono = rwsd.RwsdAudio(8000, ((1, 2),))
        for index, audio in ((5, mono), (0, rwsd.RwsdAudio(8000, ((1,), (1,)))),
                             (0, rwsd.RwsdAudio(0, ((1,),))), (0, rwsd.RwsdAudio(8000, ((1,),), 4))):
            with self.assertRaises(rwsd.RwsdError):
                rwsd.replace_wave(self.doc, index, audio)
        with self.assertRaises(rwsd.RwsdError):
            rwsd.render_entry(self.doc, 0, max_seconds=0)
        with self.assertRaises(rwsd.RwsdError):
            rwsd.decode_wave(self.doc, 2)
        with self.assertRaises(rwsd.RwsdError):
            rwsd.read_rwsd(self.header, self.payload[:100])


if __name__ == "__main__":
    unittest.main()
