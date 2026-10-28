"""Optional FE9 hub routing layered onto the existing chapter-flow tail call.

The state lives in registered global flag bits, so it is part of normal saves.  The
hub script owns the active and destination flags; this hook owns the pending story
chapter.  It runs after the ordinary successor table has selected ``r4``.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Patch, State, in_cave
from .chapter_flow import CONTINUED_PART, FLOW_HOOK, FLOW_PATCH, _SITES

HUB_HOOK = CAVE_ADDRESS + 0x700
HUB_CONFIG = CAVE_ADDRESS + 0x9F0
CONFIG_SIZE = 5
FLAG_BITS_OFFSET = 0x3B4  # party_data + 0xB4 + 0x300
HISTORY_OFFSET = 0x3C4
HISTORY_SLOTS = 40


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _router(set_chapter: int, *, hub_state_address: int | None = None) -> bytes:
    """r3=party, r4=normal successor; tail-call set_current_chapter.

    The optional address is the separately reserved four-byte extended hub state.
    Only code generation is supported for that variant until the full runtime's
    release gate passes; the retail installer below continues to use legacy flags.
    """
    prefix = [
        ppc.lis(8, 0x8000), ppc.addi(8, 8, HUB_CONFIG & 0xFFFF),
        ppc.lbz(9, 0, 8),       # hub chapter
        ppc.lbz(10, 1, 8),      # control-byte index
        ppc.lbz(11, 2, 8),      # active bit mask
        ppc.lbz(0, 3, 8),       # destination-byte index
        ppc.lbz(6, 4, 8),       # pending-byte index
        ppc.addi(7, 3, FLAG_BITS_OFFSET),
        ppc.lbzx(5, 7, 10), ppc.and_(5, 5, 11),
        ppc.lbzx(10, 7, 0), ppc.lbzx(11, 7, 6),
    ]
    if hub_state_address is not None:
        if type(hub_state_address) is not int or not 0x80000000 <= hub_state_address <= 0x817FFFFC:
            raise ValueError("Extended hub state must be inside reserved GameCube main RAM.")
        prefix = [
            ppc.lis(8, 0x8000), ppc.addi(8, 8, HUB_CONFIG & 0xFFFF),
            ppc.lbz(9, 0, 8),
            ppc.lis(7, ((hub_state_address + 0x8000) >> 16) & 0xFFFF),
            ppc.addi(7, 7, hub_state_address & 0xFFFF),
            ppc.li(0, 1), ppc.li(6, 2), ppc.li(11, 1),
            ppc.lbz(5, 0, 7), ppc.and_(5, 5, 11),
            ppc.lbz(10, 1, 7), ppc.lbz(11, 2, 7),
        ]
    program = prefix + [
        ppc.lbz(12, 0x10, 3),
        ppc.cmpwi(12, CONTINUED_PART), ("eq", "done"),
        ppc.cmplw(12, 9), ("eq", "hub"),
        ppc.cmpwi(11, 0), ("eq", "no_pending"),
        ppc.cmplw(12, 11), ("eq", "advance_pending"),
        # Chapter 28 always flows into 29; count the second half as the
        # completion of a pending chapter 28.
        ppc.cmpwi(12, 29), ("ne", "normal_decide"),
        ppc.cmpwi(11, 28), ("ne", "normal_decide"),
        "advance_pending",
        ppc.stbx(4, 7, 6), ppc.mr(11, 4),  # completed pending story chapter
        "normal_decide",
        ppc.cmpwi(5, 0), ("ne", "return_hub"),
        ppc.mr(4, 11), ("b", "clear_pending"),
        "no_pending",
        ppc.cmpwi(5, 0), ("eq", "done"),
        ppc.stbx(4, 7, 6), ("b", "return_hub"),
        "hub",
        # The normal clear routine just appended a history row for this hub
        # visit.  Remove only that final row; otherwise repeated visits exhaust
        # the retail table's forty entries and pollute the war record.
        ppc.addi(8, 3, HISTORY_OFFSET), ppc.li(12, HISTORY_SLOTS),
        "history_scan",
        ppc.lbz(4, 0, 8), ppc.cmpwi(4, 0), ("eq", "history_end"),
        ppc.addi(8, 8, 8), ppc.addi(12, 12, -1),
        ppc.cmpwi(12, 0), ("ne", "history_scan"),
        "history_end",
        ppc.cmpwi(12, HISTORY_SLOTS), ("eq", "hub_decide"),
        ppc.addi(8, 8, -8), ppc.lbz(4, 0, 8),
        ppc.cmplw(4, 9), ("ne", "hub_decide"),
        ppc.li(4, 0), ppc.stw(4, 0, 8), ppc.stw(4, 4, 8),
        "hub_decide",
        ppc.cmpwi(5, 0), ("eq", "hub_exit"),
        ppc.cmpwi(10, 0), ("eq", "hub_exit"),
        ppc.mr(4, 10), ("b", "done"),
        "hub_exit",
        ppc.cmpwi(11, 0), ("eq", "return_hub"),
        ppc.mr(4, 11),
        "clear_pending",
        ppc.li(8, 0), ppc.stbx(8, 7, 6), ppc.stbx(8, 7, 0),
        ("b", "done"),
        "return_hub",
        ppc.mr(4, 9),
        "done",
        ("b", set_chapter),
    ]
    code = b"".join(_word(w) for w in ppc.assemble(HUB_HOOK, program))
    assert in_cave(HUB_HOOK, len(code)) and HUB_HOOK + len(code) <= HUB_CONFIG
    return code


def _edits(version: str) -> tuple[Edit, ...]:
    set_chapter = _SITES[version][0]
    tail = FLOW_HOOK + 7 * 4
    code = _router(set_chapter)
    return (
        # The retail DOL has no flow hook at this address.  This edit is
        # managed only while FLOW_PATCH is on, so its branch is not a status
        # discriminator for the independent hub patch.
        Edit(tail, _word(ppc.b(tail, set_chapter)), _word(ppc.b(tail, HUB_HOOK)), wild=((0, 4),)),
        Edit(HUB_HOOK, bytes(len(code)), code),
        Edit(HUB_CONFIG, bytes(CONFIG_SIZE), bytes(CONFIG_SIZE), wild=((0, CONFIG_SIZE),)),
    )


HUB_PATCH = CATALOG.add(Patch(
    "chapters.hub.routing", "Chapters", "Hub chapter routing",
    "Routes victories through a saved hub destination and pending story chapter.",
    versions={v: _edits(v) for v in _SITES}, internal=True))


def validate_slots(hub_chapter: int, active_slot: int, destination_slot: int, pending_slot: int) -> bytes:
    """Return the five-byte router configuration for fixed global flag slots."""
    if not 33 <= hub_chapter < 90:
        raise ValueError("The hub must be an added chapter from 33-89.")
    if not 0 <= active_slot < 96:
        raise ValueError("The hub-active flag is outside the 96-slot flag table.")
    if destination_slot % 8 or pending_slot != destination_slot + 8 or pending_slot + 7 >= 96:
        raise ValueError("Destination and pending flags must occupy two consecutive whole bytes.")
    if destination_slot <= active_slot < pending_slot + 8:
        raise ValueError("The hub-active flag overlaps a chapter-number byte.")
    return bytes((hub_chapter, active_slot // 8, 1 << (active_slot % 8),
                  destination_slot // 8, pending_slot // 8))


class HubFlow:
    def __init__(self, editor):
        self.editor = editor

    @property
    def installed(self) -> bool:
        if self.editor.status(HUB_PATCH).state == State.APPLIED:
            return True
        from .extended_flag_runtime import BASE
        if not self.editor.dol.has_section_at(BASE):
            return False
        from .extended_flag_installation import inspect_runtime, RuntimeState, RECEIPT_NAME
        from ..formats.extended_flags import FlagLayout, MANIFEST_NAME
        root = self.editor.project_dir
        try:
            layout = FlagLayout.from_json((root / MANIFEST_NAME).read_text(encoding="utf-8"))
            receipt = (root / RECEIPT_NAME).read_text(encoding="utf-8")
            status = inspect_runtime(self.editor.dol, self.editor.version.code, layout, receipt)
            import json
            return status.state == RuntimeState.MATCHING and json.loads(receipt)["hub_chapter"] is not None
        except (OSError, ValueError, KeyError, AttributeError):
            return False

    def config(self) -> bytes | None:
        return self.editor.dol.read(HUB_CONFIG, CONFIG_SIZE) if self.installed else None

    def install(self, hub_chapter: int, active_slot: int, destination_slot: int, pending_slot: int) -> None:
        config = validate_slots(hub_chapter, active_slot, destination_slot, pending_slot)
        if self.editor.status(FLOW_PATCH).state != State.APPLIED:
            raise ValueError("Install the story-flow table before hub routing.")
        version = self.editor.version.code
        tail = HUB_PATCH.versions[version][0]
        expected = tail.patched if self.installed else tail.original
        if self.editor.dol.read(tail.address, 4) != expected:
            raise ValueError("The chapter-flow tail branch conflicts with another patch.")
        status = self.editor.status(HUB_PATCH)
        if status.state not in (State.ORIGINAL, State.APPLIED):
            raise ValueError(f"Hub routing cannot be patched: {status.detail}")
        self.editor.session.set_patch(HUB_PATCH, True)
        self.editor.session._write(HUB_CONFIG, config)
        self.editor.save()

    def remove(self) -> None:
        from .extended_flag_runtime import BASE
        if self.editor.dol.has_section_at(BASE):
            raise ValueError("Removing hub routing from an extended runtime is not supported.")
        if self.installed:
            self.editor.session.set_patch(HUB_PATCH, False)
            self.editor.save()
