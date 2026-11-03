"""Bounded, canonical metadata embedded at the end of the runtime section."""
import json
import struct

from ..formats.extended_flags import FlagLayout

REVISION = 1
FOOTER = struct.Struct(">8sI")
MAGIC = b"XFLGMETA"


def append_metadata(data, region, layout):
    payload = json.dumps({"revision": REVISION, "region": region, "layout": layout.to_json()},
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    padding = bytes(-(len(data) + len(payload) + FOOTER.size) % 32)
    return data + padding + payload + FOOTER.pack(MAGIC, len(payload))


def read_metadata(data):
    if len(data) < FOOTER.size:
        raise ValueError("Runtime metadata is missing")
    magic, size = FOOTER.unpack(data[-FOOTER.size:])
    if magic != MAGIC or not 0 < size <= len(data) - FOOTER.size:
        raise ValueError("Invalid runtime metadata footer")
    value = json.loads(data[-FOOTER.size - size:-FOOTER.size].decode("utf-8"))
    if not isinstance(value, dict) or set(value) != {"revision", "region", "layout"}:
        raise ValueError("Invalid runtime metadata fields")
    if type(value["revision"]) is not int or value["region"] not in ("GFEE01", "GFEP01", "GFEJ01"):
        raise ValueError("Invalid runtime metadata revision or region")
    layout = FlagLayout.from_json(value["layout"])
    if value["layout"] != layout.to_json():
        raise ValueError("Runtime manifest is not canonical")
    return value["revision"], value["region"], layout
