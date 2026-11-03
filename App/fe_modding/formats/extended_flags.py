"""Versioned extended event-flag layout and save payload (FE9 only).

This is the host-side format contract. It does not enable an executable patch.
IDs are append-only, including deleted entries, and local IDs belong to a chapter.
The UUID identifies a compatible layout lineage, not a hash of its current names.
"""
from __future__ import annotations

import json
import struct
from dataclasses import asdict, dataclass, field, replace
from uuid import UUID, uuid4

from .event_flags import check_flag_name

MANIFEST_NAME = "extended_flags.json"
FORMAT_VERSION = 1
TAG = b"XFLG"
CAMPAIGN_SLOTS = 1024
CHAPTER_SLOTS = 256
HUB_BYTES = 4
PAYLOAD_SIZE = HUB_BYTES + CAMPAIGN_SLOTS // 8 + CHAPTER_SLOTS // 8
HEADER = struct.Struct(">4sHH16s")
RECORD_SIZE = HEADER.size + PAYLOAD_SIZE
# Separate versions retain regional magic; SYSF stays in its retail format.
SAVE_VERSIONS = {b"FE8J": 0x54460101, b"FE8X": 0x54460102}
HUB_ALIASES = {"HUB_ACTIVE": (0, 0), "HUB_STARTED": (0, 1),
               **{f"HUB_DEST_{i}": (1, i) for i in range(8)},
               **{f"HUB_PENDING_{i}": (2, i) for i in range(8)}}


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value < high:
        raise ValueError(f"{label} must be an integer from {low} to {high - 1}")


@dataclass(frozen=True)
class FlagEntry:
    name: str
    scope: str
    slot: int
    chapter: int | None = None
    deleted: bool = False

    def __post_init__(self):
        if self.scope not in ("campaign", "chapter"):
            raise ValueError("flag scope must be campaign or chapter")
        if not isinstance(self.name, str):
            raise ValueError("flag name must be text")
        problem = check_flag_name(self.name, ())
        if problem or any(ord(c) < 32 for c in self.name):
            raise ValueError(problem or "control characters are not allowed in flag names")
        if self.name.startswith("HUB_") or self.name.startswith("gf_"):
            raise ValueError("HUB_ and gf_ names are reserved")
        _integer(self.slot, 0, CAMPAIGN_SLOTS if self.scope == "campaign" else CHAPTER_SLOTS, "slot")
        if self.scope == "campaign":
            if self.chapter is not None:
                raise ValueError("campaign flags do not have a chapter")
        else:
            _integer(self.chapter, 0, 256, "chapter")
        if type(self.deleted) is not bool:
            raise ValueError("deleted must be a boolean")


@dataclass(frozen=True)
class FlagLayout:
    identity: str = field(default_factory=lambda: uuid4().hex)
    entries: tuple[FlagEntry, ...] = ()

    def __post_init__(self):
        try:
            identity = UUID(self.identity)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("layout identity must be a UUID") from exc
        if identity.int == 0:
            raise ValueError("layout identity must not be zero")
        object.__setattr__(self, "identity", identity.hex)
        object.__setattr__(self, "entries", tuple(self.entries))
        slots = set()
        campaign_names = set()
        local_names = set()
        for entry in self.entries:
            key = (entry.scope, entry.chapter, entry.slot)
            if key in slots:
                raise ValueError(f"duplicate extended slot: {key}")
            slots.add(key)
            if entry.deleted:
                continue
            if entry.scope == "campaign":
                if entry.name in campaign_names:
                    raise ValueError(f"duplicate campaign flag: {entry.name}")
                campaign_names.add(entry.name)
            else:
                key = (entry.chapter, entry.name)
                if key in local_names:
                    raise ValueError(f"duplicate chapter flag: {entry.name}")
                local_names.add(key)
        if campaign_names & {name for _, name in local_names}:
            raise ValueError("campaign and chapter flag names must not collide")

    def add(self, name: str, scope: str, chapter: int | None = None) -> FlagLayout:
        used = [e.slot for e in self.entries if (e.scope, e.chapter) == (scope, chapter)]
        entry = FlagEntry(name, scope, max(used, default=-1) + 1, chapter)
        return replace(self, entries=self.entries + (entry,))

    def rename(self, entry: FlagEntry, name: str) -> FlagLayout:
        if entry not in self.entries or entry.deleted:
            raise ValueError("flag is not an active entry in this layout")
        return replace(self, entries=tuple(replace(e, name=name) if e == entry else e for e in self.entries))

    def delete(self, entry: FlagEntry) -> FlagLayout:
        if entry not in self.entries or entry.deleted:
            raise ValueError("flag is not an active entry in this layout")
        return replace(self, entries=tuple(replace(e, deleted=True) if e == entry else e for e in self.entries))

    def find(self, name: str, chapter: int | None = None) -> FlagEntry | None:
        return next((e for e in self.entries if not e.deleted and e.name == name
                     and (e.scope == "campaign" or e.chapter == chapter)), None)

    def remaining(self, scope: str, chapter: int | None = None) -> int:
        if scope not in ("campaign", "chapter"):
            raise ValueError("flag scope must be campaign or chapter")
        limit = CAMPAIGN_SLOTS if scope == "campaign" else CHAPTER_SLOTS
        return limit - max((e.slot + 1 for e in self.entries
                            if (e.scope, e.chapter) == (scope, chapter)), default=0)

    def validate_registrations(self, campaign: list[str], chapters: dict[int, list[str]]) -> None:
        """Reject missing registrations and collisions with vanilla names before building."""
        for entry in self.entries:
            if entry.deleted:
                names = campaign if entry.scope == "campaign" else chapters.get(entry.chapter, [])
                if entry.name in names:
                    raise ValueError(f"{entry.name}: remove the deleted flag's registration")
                continue
            names = campaign if entry.scope == "campaign" else chapters.get(entry.chapter, [])
            if names.count(entry.name) != 1:
                raise ValueError(f"{entry.name}: expected exactly one {entry.scope} registration")
            if entry.scope == "campaign" and any(entry.name in names for names in chapters.values()):
                raise ValueError(f"{entry.name}: campaign/chapter name collision")
            if entry.scope == "chapter" and entry.name in campaign:
                raise ValueError(f"{entry.name}: chapter/campaign name collision")

    def require_compatible(self, previous: FlagLayout) -> None:
        """Check an edited manifest before replacing the project's last installed layout."""
        if self.identity != previous.identity:
            raise ValueError("layout identity changed; a new playthrough is required")
        current = {(e.scope, e.chapter, e.slot): e for e in self.entries}
        old = {(e.scope, e.chapter, e.slot): e for e in previous.entries}
        for key, entry in old.items():
            new = current.get(key)
            if new is None or (entry.deleted and new != entry):
                raise ValueError("existing slots must be retained; deleted slots cannot be reused")
        for key, entry in current.items():
            if key not in old:
                high = max((e.slot for e in previous.entries
                            if (e.scope, e.chapter) == (entry.scope, entry.chapter)), default=-1)
                if entry.slot <= high:
                    raise ValueError("new slots must be appended after the existing high-water mark")
        old_names = {(e.scope, e.chapter, e.name): e.slot for e in previous.entries if not e.deleted}
        for entry in self.entries:
            key = (entry.scope, entry.chapter, entry.name)
            if not entry.deleted and key in old_names and old_names[key] != entry.slot:
                raise ValueError("existing flag names cannot move to different slots")

    def vanilla_names(self, names: list[str], scope: str, chapter: int | None = None) -> list[str]:
        extended = {e.name for e in self.entries if not e.deleted
                    and (e.scope, e.chapter) == (scope, chapter)}
        return [name for name in names if name not in extended and name not in HUB_ALIASES]

    def to_json(self) -> str:
        return json.dumps({"version": FORMAT_VERSION, "identity": self.identity,
                           "entries": [asdict(e) for e in self.entries]}, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, source: str) -> FlagLayout:
        data = json.loads(source)
        if not isinstance(data, dict) or set(data) != {"version", "identity", "entries"}:
            raise ValueError("invalid extended flag manifest fields")
        if type(data["version"]) is not int or data["version"] != FORMAT_VERSION:
            raise ValueError("unsupported extended flag manifest version")
        if not isinstance(data["entries"], list):
            raise ValueError("manifest entries must be a list")
        try:
            return cls(data["identity"], tuple(FlagEntry(**entry) for entry in data["entries"]))
        except TypeError as exc:
            raise ValueError("invalid extended flag entry") from exc


@dataclass(frozen=True)
class FlagCompileContext:
    """Explicit bank assignment for one script; None denotes startup.cmb.

    This validates compilation only. Project writers must separately verify the
    installed executable and matching manifest before accepting these scripts.
    """
    layout: FlagLayout
    chapter: int | None = None

    def __post_init__(self):
        if not isinstance(self.layout, FlagLayout):
            raise ValueError("extended compilation requires a flag layout")
        if self.chapter is not None:
            _integer(self.chapter, 0, 256, "chapter")

    def vanilla_counts(self, campaign, local):
        relevant = tuple(e for e in self.layout.entries
                         if e.scope == "campaign" or e.chapter == self.chapter)
        FlagLayout(self.layout.identity, relevant).validate_registrations(
            campaign, {} if self.chapter is None else {self.chapter: local})
        if any(name in HUB_ALIASES for name in local):
            raise ValueError("hub flags must not be registered as chapter-local flags")
        return (len(self.layout.vanilla_names(campaign, "campaign")),
                len(self.layout.vanilla_names(local, "chapter", self.chapter)))


@dataclass
class ExtendedState:
    identity: bytes
    hub: bytes = bytes(HUB_BYTES)
    campaign: bytes = bytes(CAMPAIGN_SLOTS // 8)
    chapter: bytes = bytes(CHAPTER_SLOTS // 8)

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        for name, size in (("identity", 16), ("hub", HUB_BYTES),
                           ("campaign", CAMPAIGN_SLOTS // 8), ("chapter", CHAPTER_SLOTS // 8)):
            value = getattr(self, name)
            if not isinstance(value, bytes) or len(value) != size:
                raise ValueError(f"extended {name} must contain exactly {size} bytes")
        if not any(self.identity):
            raise ValueError("extended layout identity must not be zero")
        if self.hub[0] & ~3 or self.hub[3]:
            raise ValueError("unknown hub control bits or nonzero reserved byte")

    @classmethod
    def for_layout(cls, layout: FlagLayout) -> ExtendedState:
        return cls(bytes.fromhex(layout.identity))

    def require_layout(self, layout: FlagLayout) -> None:
        if self.identity != bytes.fromhex(layout.identity):
            raise ValueError("save belongs to a different extended flag layout; start a new playthrough")

    def build(self) -> bytes:
        self.validate()
        return HEADER.pack(TAG, FORMAT_VERSION, PAYLOAD_SIZE, self.identity) + self.hub + self.campaign + self.chapter

    @classmethod
    def parse(cls, raw: bytes) -> ExtendedState:
        if len(raw) != RECORD_SIZE:
            raise ValueError("missing or truncated extended flag record")
        tag, version, size, identity = HEADER.unpack_from(raw)
        if tag != TAG or version != FORMAT_VERSION or size != PAYLOAD_SIZE:
            raise ValueError("unsupported extended flag record")
        hub_end = HEADER.size + HUB_BYTES
        campaign_end = hub_end + CAMPAIGN_SLOTS // 8
        return cls(identity, raw[HEADER.size:hub_end], raw[hub_end:campaign_end], raw[campaign_end:])

    def get(self, scope: str, slot: int) -> bool:
        raw = self._bank(scope)
        _integer(slot, 0, len(raw) * 8, "slot")
        return bool(raw[slot // 8] & (1 << (slot % 8)))

    def set(self, scope: str, slot: int, value: bool) -> None:
        raw = bytearray(self._bank(scope))
        _integer(slot, 0, len(raw) * 8, "slot")
        if type(value) is not bool:
            raise ValueError("flag value must be a boolean")
        mask = 1 << (slot % 8)
        raw[slot // 8] = (raw[slot // 8] | mask) if value else (raw[slot // 8] & ~mask)
        setattr(self, scope, bytes(raw))

    def _bank(self, scope: str) -> bytes:
        if scope not in ("campaign", "chapter"):
            raise ValueError("flag scope must be campaign or chapter")
        return getattr(self, scope)

    def clear_chapter(self) -> None:
        self.chapter = bytes(CHAPTER_SLOTS // 8)

    def hub_flag(self, name: str, value: bool | None = None) -> bool:
        offset, bit = HUB_ALIASES[name]
        if value is not None:
            if type(value) is not bool:
                raise ValueError("flag value must be a boolean")
            raw = bytearray(self.hub)
            raw[offset] = raw[offset] | (1 << bit) if value else raw[offset] & ~(1 << bit)
            self.hub = bytes(raw)
        return bool(self.hub[offset] & (1 << bit))
