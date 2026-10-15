"""Data-side records required by the opt-in three-tier promotion patch.

This module only transforms FE8Data.bin bytes.  The caller must install the
matching main.dol hooks before writing its result to a playable project.
"""

from __future__ import annotations

import io
import struct

from ..formats import fe8data, message

TIER3_SID = "SID_TIER3"
CROWN_IID = "IID_MASTERCROWN"
RETAIL_SKILL_COUNTS = {"GFEE01": 98, "GFEP01": 98, "GFEJ01": 97}


def provision(data: bytes, version: str = "GFEE01") -> bytes:
    """Append the tier flag and Crown without moving existing record numbers.

    Repeating the operation is safe.  A non-retail skill layout or an item
    identity collision is rejected instead of guessing where to insert data.
    """
    if version not in RETAIL_SKILL_COUNTS:
        raise ValueError(f"Unsupported game version {version}.")
    retail_count = RETAIL_SKILL_COUNTS[version]
    parsed = fe8data.read_fe8data(data)
    skills = parsed.skills
    if len(skills) == retail_count:
        if any(skill.sid == TIER3_SID for skill in skills):
            raise ValueError(f"{TIER3_SID} already occupies a retail skill slot.")
        rows = fe8data.read_table(data, "skill")
        row = bytearray(fe8data.SKILL_RECORD_SIZE)
        row[0x18] = retail_count
        rows.append(fe8data.RawRecord(bytes(row), frozenset()))
        start = fe8data.table_start(data, "skill") - 4
        block = bytearray(struct.pack(">I", len(rows)))
        pointers: list[int] = []
        for record in rows:
            pointers.extend(len(block) + position for position in sorted(record.pointers))
            block.extend(record.raw)
        data = fe8data.replace_section(
            data, "SkillData", start + 4 + retail_count * fe8data.SKILL_RECORD_SIZE,
            bytes(block), pointers, slack=fe8data.SKILL_RECORD_SIZE,
        )
        # SkillData is unusual: every retail record also has its own symbol.
        # Moving the table must carry those symbols along with its parent.
        skill_start = fe8data.table_start(data, "skill")
        moved = bytearray(data)
        for index, skill in enumerate(skills):
            fe8data.set_symbol(moved, skill.sid, skill_start + index * fe8data.SKILL_RECORD_SIZE
                               - fe8data.HEADER_SIZE)
        data = bytes(moved)
        data = fe8data.patch_skill_field(data, retail_count, "sid", TIER3_SID)
        data = _add_skill_symbol(data, TIER3_SID, retail_count)
    elif len(skills) != retail_count + 1 or skills[-1].sid != TIER3_SID:
        raise ValueError(f"The skill table must contain the {retail_count} retail entries, "
                         "optionally followed by SID_TIER3.")

    parsed = fe8data.read_fe8data(data)
    crowns = [item for item in parsed.items if item.iid == CROWN_IID]
    if len(crowns) > 1:
        raise ValueError(f"Multiple {CROWN_IID} records exist.")
    if not crowns:
        seals = [item for item in parsed.items if item.iid == "IID_MASTERPROOF"]
        if len(seals) != 1:
            raise ValueError("Expected exactly one retail Master Seal item.")
        data, index = fe8data.add_record(data, "item", CROWN_IID, copy_from=seals[0].index)
        data = fe8data.add_label(data, "MIID_MASTERCROWN")
        data = fe8data.add_label(data, "MH_I_MASTERCROWN")
        data = fe8data.patch_item_field(data, index, "miid", "MIID_MASTERCROWN")
        data = fe8data.patch_item_field(data, index, "help_key", "MH_I_MASTERCROWN")
    return data


def _add_skill_symbol(data: bytes, sid: str, index: int) -> bytes:
    if sid in fe8data.symbol_offsets(data):
        raise ValueError(f"Symbol {sid} already exists.")
    entries = [(offset, name) for _position, offset, name in fe8data._symbol_entries(data)]
    entries.append((fe8data.table_start(data, "skill") + index * fe8data.SKILL_RECORD_SIZE
                    - fe8data.HEADER_SIZE, sid))
    _size, data_size, pointer_count, _symbol_count = struct.unpack_from(">IIII", data)
    table = fe8data.HEADER_SIZE + data_size + 4 * pointer_count
    rows = bytearray()
    names = bytearray()
    for offset, name in entries:
        rows.extend(struct.pack(">II", offset, len(names)))
        names.extend(name.encode("ascii") + b"\x00")
    out = bytearray(data[:table]) + rows + names
    struct.pack_into(">I", out, 0, len(out))
    struct.pack_into(">I", out, 12, len(entries))
    return bytes(out)


def provision_messages(data: bytes, version: str, language: str = "en") -> bytes:
    """Add the Crown's visible name/help to a FE9 common.m message file."""
    if version not in RETAIL_SKILL_COUNTS:
        raise ValueError(f"Unsupported game version {version}.")
    stream = io.BytesIO(data)
    messages = message.read_messages(stream)
    stream.seek(0)
    order = message.read_text_order(stream)
    names = {entry.speaker for entry in messages}
    def encoded(text: str) -> str:
        return text.encode("shift_jis").decode(message.ENCODING)
    texts = ({
        "MIID_MASTERCROWN": encoded("マスタークラウン"),
        "MH_I_MASTERCROWN": encoded("上級職を最上級職にクラスチェンジさせる道具。"),
    } if version == "GFEJ01" else {
        "MIID_MASTERCROWN": {
            "en": "Master Crown", "de": "Meisterkrone", "fr": "Couronne mag.",
            "it": "Corona suprema", "es": "Corona maestra",
        }[language],
        "MH_I_MASTERCROWN": {
            "en": "Promotes an eligible second-tier unit to its third-tier class.",
            "de": "Ermoeglicht einer Einheit der zweiten Stufe den Wechsel in die dritte Stufe.",
            "fr": "Permet a une unite de deuxieme rang de passer au troisieme rang.",
            "it": "Permette a un'unita di secondo livello di passare al terzo livello.",
            "es": "Permite a una unidad de segundo nivel ascender al tercer nivel.",
        }[language],
    })
    if all(key in names for key in texts):
        return data
    messages.extend(message.Message(key, value) for key, value in texts.items() if key not in names)
    messages.sort(key=lambda entry: entry.speaker.encode(message.ENCODING))
    return message.write_messages(messages, order)


def validate_chain(data: bytes, first: str, second: str, third: str) -> None:
    """Check a configured forward chain and the two runtime tier markers."""
    classes = {cls.jid: cls for cls in fe8data.read_fe8data(data).classes}
    if len({first, second, third}) != 3 or any(jid not in classes for jid in (first, second, third)):
        raise ValueError("A three-tier chain needs three distinct existing classes.")
    a, b, c = (classes[jid] for jid in (first, second, third))
    if a.promotes_to != second or b.promotes_to != third or c.promotes_to in (first, second, third):
        raise ValueError("Expected first→second→third without a link back into the chain.")
    if "SID_HIGHER" in a.skills or TIER3_SID in a.skills:
        raise ValueError("The first class must not have a promoted-tier flag.")
    if "SID_HIGHER" not in b.skills or TIER3_SID in b.skills:
        raise ValueError("The second class needs SID_HIGHER and no SID_TIER3.")
    if "SID_HIGHER" not in c.skills or TIER3_SID not in c.skills:
        raise ValueError("The third class needs both SID_HIGHER and SID_TIER3.")
