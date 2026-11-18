"""Builders for small synthetic game files, so format tests run without a disc.

Nothing here is copied from a retail file: every builder writes the documented layout from scratch
with made-up names and numbers. The CI machine has no game data (the ``FE9_*`` / ``FE10_*``
variables are unset there), so these let the readers and writers be checked on every push.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe10_battle  # noqa: E402
from fe_modding.formats.common import HEADER_SIZE  # noqa: E402


def data_container(body: bytes, pointer_fields: list[int], symbols: list[tuple[str, int]],
                   header_tail: bytes = bytes(16)) -> bytes:
    """A Tellius data container: the 0x20-byte header, ``body`` as the data section, its pointer
    list (data-relative field offsets) and the symbol table (name, data-relative offset)."""
    names = b"".join(name.encode("ascii") + b"\0" for name, _ in symbols)
    table, name_at = b"", 0
    for name, offset in symbols:
        table += struct.pack(">II", offset, name_at)
        name_at += len(name.encode("ascii")) + 1
    tail = struct.pack(f">{len(pointer_fields)}I", *pointer_fields) + table + names
    header = struct.pack(">IIII", HEADER_SIZE + len(body) + len(tail), len(body), len(pointer_fields),
                         len(symbols)) + header_tail
    return header + body + tail


def _record(size: int, strings: dict[int, str] | None = None, **bytes_at: int) -> fe10_battle.BattleRecord:
    raw = bytearray(size)
    for key, value in bytes_at.items():
        raw[int(key[1:], 16)] = value
    return fe10_battle.BattleRecord(0, bytes(raw), tuple(sorted((strings or {}).items())))


def _with(record: fe10_battle.BattleRecord, at: int, fmt: str, *values) -> fe10_battle.BattleRecord:
    raw = bytearray(record.raw)
    struct.pack_into(fmt, raw, at, *values)
    return fe10_battle.BattleRecord(0, bytes(raw), record.strings)


def fe10_battle_file() -> bytes:
    """A small ``FE10Battle.cms`` (decompressed) with every table and array the reader needs.

    - FE10BAnimData: 2 selectors (one by PID+JID, one by JID) pointing at unit ``UNIT_A``.
    - FE10BWeapon: 2 rows; FE10BWeaponType: the 16 rows camera dispatch needs.
    - FE10BMapModel: 3 rows; FE10BMapData: 2 backgrounds (``MAP_A`` uses models 0 and 1).
    - FE10BCamFile: 3 clips; FE10BCamGroup: 2 groups choosing 2 and 1 clips.
    - FE10BMotion: 2 rows; FE10BCamList: 1 row, so FE10BCamGroupIndex is 1 x 16 x 2 bytes.
    - FE10BUnit: 2 rows owning 2 and 1 FE10BTex rows.
    """
    sizes = fe10_battle.TABLE_SIZES
    tables: dict[str, list[fe10_battle.BattleRecord]] = {name: [] for name in sizes}
    tables["FE10BAnimData"] = [
        _record(20, {4: "PID_ALPHA", 8: "JID_SWORD", 12: "UNIT_A"}),
        _record(20, {8: "JID_LANCE", 12: "UNIT_B"}),
    ]
    tables["FE10BFootEffect"] = [_record(24, {0: "なし"}), _record(24, {0: "砂煙"}), _record(24, {0: "custom"})]
    tables["FE10BSetup"] = [_record(8)]
    tables["FE10BWeapon"] = [
        _record(36, {0: "鉄の剣", 4: "IRONSWORD", 8: "ironsword", 12: "EID_HIT"}, x20=1),
        _record(36, {0: "手斧", 4: "HANDAXE"}, x20=3, x21=2),
    ]
    tables["FE10BWeaponType"] = [_record(8, {0: f"型{i}", 4: f"t{i:02d}"}) for i in range(16)]
    models = [_record(24, {0: f"bg{i:02d}", 4: "SND_GROUP_TEST"}, x08=0x12 if i == 1 else 0) for i in range(3)]
    models[0] = _with(models[0], 0x0E, ">3hhh", 10, -20, 30, 90, 0x300)
    tables["FE10BMapModel"] = models
    tables["FE10BMapData"] = [
        _with(_record(16, {0: "MAP_A"}), 4, ">5h", 0, -1, 1, -1, -1),
        _with(_record(16, {0: "MAP_B"}), 4, ">5h", -1, -1, -1, -1, -1),
    ]
    tables["FE10BSky"] = [_record(8)]
    tables["FE10BMotion"] = [_record(12), _record(12)]
    tables["FE10BFlags"] = [_record(4, {0: "大型"}), _record(4, {0: "飛行系"}), _record(4, {0: "新しい"})]
    tables["FE10BParam"] = [_record(4, {0: "補間比率"}), _record(4, {0: "間合い"})]
    tables["FE10BSFXList"] = [_record(20, {0: "なし"}), _record(20, {0: "鎧系"})]
    tables["FE10BCamFile"] = [_record(12, {0: f"clip {i}", 4: f"cam{i:02d}"}) for i in range(3)]
    tables["FE10BCamGroup"] = [_record(20, x0b=2), _record(20, x0b=1)]
    tables["FE10BCamList"] = [_record(72)]
    units = [_record(340, {0: "UNIT_A", 4: "modelA"}), _record(340, {0: "UNIT_B", 4: "modelB"})]
    units[0] = _with(units[0], 0x10, ">I", 0b10)
    units[0] = _with(units[0], 0x18, ">2h", 128, -512)
    units[0] = _with(units[0], 0x14C, ">BB", 1, 2)
    units[1] = _with(units[1], 0x14D, ">B", 1)
    tables["FE10BUnit"] = units
    tables["FE10BTex"] = [_record(8, {0: "ARMY_A", 4: "zu/modelA/a.tpl"}),
                          _record(8, {0: "PID_ALPHA", 4: "zu/modelA/alpha.tpl"}),
                          _record(8, {0: "ARMY_A", 4: "zu/modelB/b.tpl"})]
    matrix = bytearray([0xFF]) * (1 * 16 * 2)
    matrix[0], matrix[1] = 0, 1
    arrays = {"FE10BCamFileIndex": bytes([0, 2, 1]), "FE10BCamFileRate": bytes([60, 40, 100]),
              "FE10BCamGroupIndex": bytes(matrix)}
    document = fe10_battle.Fe10Battle(
        tuple(fe10_battle.BattleTable(name, size, tuple(tables[name])) for name, size in sizes.items()),
        tuple(arrays.items()), b"", (), (), (), (), (), (), ())
    return fe10_battle.build_fe10_battle(document)


def brstm_template(channels: int = 2, sample_rate: int = 32000, block_size: int = 0x100) -> bytes:
    """A one-block BRSTM of 14 silent samples per channel: the shape :func:`brstm.write_brstm` takes
    as its template (HEAD with stream info, channel table and one ADPCM info per channel, ADPC, DATA)."""
    base = 8  # HEAD references are relative to HEAD + 8
    stream_at, table_at, info_at, adpcm_at = 0x20, 0x60, 0x80, 0xA0
    head = bytearray(base + adpcm_at + 0x30 * channels)
    head += bytes(-len(head) % 0x20)
    head[:4] = b"HEAD"
    struct.pack_into(">I", head, 4, len(head))
    for slot, target in ((0, stream_at), (8, 0x58), (16, table_at)):
        struct.pack_into(">II", head, base + slot, 0x01000000, target)
    head[base + table_at] = channels
    for channel in range(channels):
        struct.pack_into(">II", head, base + table_at + 4 + 8 * channel, 0x01000000, info_at + 8 * channel)
        struct.pack_into(">II", head, base + info_at + 8 * channel, 0x01000000, adpcm_at + 0x30 * channel)
    header_size = 0x40
    head_offset = header_size
    adpc = bytearray(-(-(8 + 4 * channels) // 0x20) * 0x20)
    adpc[:4] = b"ADPC"
    struct.pack_into(">I", adpc, 4, len(adpc))
    adpc_offset = head_offset + len(head)
    data_offset = adpc_offset + len(adpc)
    data = bytearray(0x20 + 0x20 * channels)
    data[:4] = b"DATA"
    struct.pack_into(">I", data, 4, len(data))
    # codec 2 (DSP-ADPCM), no loop; then loop start, samples, audio offset, blocks, block size,
    # samples per block, last block used / samples / padded, ADPC samples, ADPC entry size
    struct.pack_into(">4BH", head, base + stream_at, 2, 0, channels, 0, sample_rate)
    struct.pack_into(">11I", head, base + stream_at + 8, 0, 14, data_offset + 0x20, 1, block_size,
                     block_size // 8 * 14, 8, 14, 0x20, block_size // 8 * 14, 4)
    out = bytearray(header_size)
    out[:4] = b"RSTM"
    struct.pack_into(">HHIHH", out, 4, 0xFEFF, 0x0100, 0, header_size, 3)
    struct.pack_into(">6I", out, 0x10, head_offset, len(head), adpc_offset, len(adpc), data_offset, len(data))
    out += head + adpc + data
    struct.pack_into(">I", out, 8, len(out))
    return bytes(out)


def sound_data_file(cues: list[tuple[str, str, int]]) -> bytes:
    """A decompressed ``sound_data.cms``: one 36-byte record per (cue, resource, first raw word),
    exported under the cue's name, plus an aggregate ``SND_TABLE`` export the reader skips."""
    records = bytearray()
    strings = bytearray()
    pointer_fields = []
    string_at: dict[str, int] = {}
    record_size = 0x24
    strings_base = record_size * len(cues) + 8
    for name in [n for cue in cues for n in cue[:2]]:
        if name not in string_at:
            string_at[name] = strings_base + len(strings)
            strings += name.encode("ascii") + b"\0"
    symbols = []
    for index, (name, resource, word) in enumerate(cues):
        at = index * record_size
        records += struct.pack(">9I", string_at[name], string_at[resource], word, *range(1, 7))
        pointer_fields += [at, at + 4]
        symbols.append((name, at))
    aggregate_at = len(records)
    records += struct.pack(">II", len(cues), 0)
    symbols.append(("SND_TABLE", aggregate_at))
    body = bytes(records) + bytes(strings)
    body += bytes(-len(body) % 4)
    return data_container(body, pointer_fields, sorted(symbols, key=lambda item: item[0].encode()))


def wii_banner_file(titles: list[tuple[str, str]]) -> bytes:
    """An ``opening.bnr``: IMET header with ``titles`` (ten languages) and its MD5, then the outer U8
    archive whose ``meta/icon.bin`` and ``meta/banner.bin`` are IMD5+LZ77 U8 archives holding one
    ``arc/timg/*.tpl`` each, and an uncompressed ``meta/sound.bin``."""
    import hashlib

    from fe_modding.formats import wii_banner as wb

    def part(picture: str, content: bytes) -> bytes:
        inner = wb.build_u8([wb.U8Entry("arc", None), wb.U8Entry("arc/blyt", None),
                             wb.U8Entry("arc/blyt/x.brlyt", b"RLYT" + bytes(12)),
                             wb.U8Entry("arc/timg", None), wb.U8Entry(f"arc/timg/{picture}", content)])
        return inner

    icon, banner = part("icon.tpl", b"\x00\x20\xaf\x30" + bytes(60)), part("bg.tpl", bytes(range(64)))
    outer = wb.build_u8([wb.U8Entry("meta", None),
                         wb.U8Entry("meta/icon.bin", wb.wrap(icon, compress=True)),
                         wb.U8Entry("meta/banner.bin", wb.wrap(banner, compress=True)),
                         wb.U8Entry("meta/sound.bin", wb.wrap(b"BNS " + bytes(28), compress=False))])
    header = bytearray(wb.HEADER_END)
    struct.pack_into(">4sIIIIII", header, wb.IMET_OFFSET, b"IMET", 0x600, 3, len(icon), len(banner), 32, 0)
    for index, (line1, line2) in enumerate(titles):
        at = wb.TITLES_OFFSET + wb.TITLE_SIZE * index
        header[at:at + len(line1) * 2] = line1.encode("utf-16-be")
        at += 2 * wb.TITLE_CHARS
        header[at:at + len(line2) * 2] = line2.encode("utf-16-be")
    header[wb.HASH_OFFSET:] = hashlib.md5(bytes(header)).digest()
    return bytes(header) + outer


def rwsd_file(waves: list[tuple[int, list[int], int]]) -> tuple[bytes, bytes]:
    """``(header, wave_data)`` of an RWSD with one mono entry per wave; ``waves`` lists
    (encoding, samples, sample rate) with encoding 1 (PCM16) or 2 (DSP-ADPCM, encoded here)."""
    from fe_modding.formats import dsp_adpcm

    count = len(waves)
    # DATA: entry list, then per entry: entry (0x18), WSD info (0x20), note table (0xC), note (0x30)
    per_entry = 0x18 + 0x20 + 0x0C + 0x30
    list_size = 4 + 8 * count
    data = bytearray(8 + list_size + per_entry * count)
    data[:4] = b"DATA"
    struct.pack_into(">II", data, 4, len(data), count)
    for index in range(count):
        entry = list_size + per_entry * index  # relative to DATA + 8
        wsd, table, note = entry + 0x18, entry + 0x38, entry + 0x44
        struct.pack_into(">II", data, 8 + 4 + 8 * index, 0x01000000, entry)
        struct.pack_into(">II", data, 8 + entry, 0x01000000, wsd)
        struct.pack_into(">II", data, 8 + entry + 0x10, 0x01000000, table)
        struct.pack_into(">fB", data, 8 + wsd, 1.0, 64)
        struct.pack_into(">III", data, 8 + table, 1, 0x01000000, note)
        struct.pack_into(">I", data, 8 + note, index)
        data[8 + note + 9] = 100
        struct.pack_into(">f", data, 8 + note + 0x10, 1.0)

    payload = bytearray()
    infos = []
    for encoding, samples, rate in waves:
        payload += bytes(-len(payload) % 0x20)
        start = len(payload)
        info = dsp_adpcm.AdpcmInfo()
        if encoding == 2:
            payload += dsp_adpcm.encode(list(samples), info)
            stored = dsp_adpcm.get_nibble_address(len(samples))
        else:
            payload += struct.pack(f">{len(samples)}h", *samples)
            stored = len(samples)
        infos.append((encoding, rate, stored, start, info))
    wave_size = 12 + 4 * count + 0x6C * count
    wave = bytearray(wave_size)
    wave[:4] = b"WAVE"
    struct.pack_into(">II", wave, 4, wave_size, count)
    for index, (encoding, rate, stored, start, info) in enumerate(infos):
        at = 12 + 4 * count + 0x6C * index
        struct.pack_into(">I", wave, 12 + 4 * index, at)
        struct.pack_into(">4BH", wave, at, encoding, 0, 1, rate >> 16, rate & 0xFFFF)
        struct.pack_into(">4I", wave, at + 8, 0, stored, 0x1C, start)
        struct.pack_into(">I", wave, at + 0x1C, 0x20)
        struct.pack_into(">2I", wave, at + 0x20, 0, 0x3C)
        struct.pack_into(">16h2H2hH2h", wave, at + 0x3C, *info.coef, info.gain, info.pred_scale,
                         info.yn1, info.yn2, info.loop_pred_scale, info.loop_yn1, info.loop_yn2)
    header = bytearray(0x20)
    header[:4] = b"RWSD"
    data_offset = 0x20
    wave_offset = data_offset + len(data)
    struct.pack_into(">HHIHH", header, 4, 0xFEFF, 0x0102, 0x20 + len(data) + len(wave), 0x20, 2)
    struct.pack_into(">4I", header, 0x10, data_offset, len(data), wave_offset, len(wave))
    return bytes(header + data + wave), bytes(payload)
