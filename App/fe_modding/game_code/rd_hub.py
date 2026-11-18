"""Radiant Dawn hub routing, layered onto the story runtime's advance hook (RFEE01).

The counterpart of :mod:`hub_flow` (Path of Radiance). The state lives in registered global flag
bits, which a save keeps: the hub script owns the active and destination bytes, this router owns
the pending story chapter. Radiant Dawn keeps its 128 flag bits at ``0x803CB07C`` (party +0x544,
:mod:`formats.event_flags`), slot ``i`` in byte ``i >> 3``, bit ``i & 7``.

``rd_story``'s hook (cave +0x100) runs when a chapter ends: it calls the retail advance (or, for
chapters 56-79, skips it) and then applies its successor table. Its last step is ``done``, which
restores the saved link register. This patch turns the first instruction of ``done`` into a call
to the router below, which runs while the hook's frame (the finished chapter at ``sp+8``) is still
live. The router reads the chapter the advance chose (party +0x10) and, when the hub changes it,
calls ``_SET_CHAPTER`` again and sets the resume point as the hook does. It then performs the
instruction it replaced, so the hook carries on as before.

Routing, for a finished chapter ``C`` and the chapter ``N`` the story chose:

- ``C`` is the hub: go to the destination when the hub is active and one is set; otherwise to the
  pending story chapter (clearing it and the destination); otherwise stay at the hub.
- no pending chapter: when the hub is active, remember ``N`` as pending and go to the hub.
- ``C`` is the pending chapter: the pending chapter becomes ``N``. Then go to the hub when it is
  active, else to the pending chapter (clearing it and the destination).
- ``C`` is the ending (55): nothing changes.

Not done here, unlike Path of Radiance: removing the hub visit from the clear history.
"""

from __future__ import annotations

from . import ppc, rd_regions, rd_story
from .catalog import CAVE_ADDRESS, Edit, Patch, State, in_cave

RFEE01 = rd_story.RFEE01

HUB_HOOK = CAVE_ADDRESS + 0x1100
HUB_CONFIG = CAVE_ADDRESS + 0x1280
CONFIG_SIZE = 5
FLAG_BITS = 0x803CB07C
SLOT_COUNT = 128

_LWZ_R0 = ppc.lwz(0, 0x24, 1)
_HOOK_WORDS = [int.from_bytes(rd_story._hook()[i:i + 4], "big") for i in range(0, len(rd_story._hook()), 4)]
# The hook's ``done``: the first ``lwz r0, 0x24(r1)``.
DONE = rd_story.HOOK + 4 * _HOOK_WORDS.index(_LWZ_R0)


def _hi(address: int) -> int:
    return ((address + 0x8000) >> 16) & 0xFFFF


def _lo(address: int) -> int:
    low = address & 0xFFFF
    return low - 0x10000 if low >= 0x8000 else low


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _router() -> bytes:
    base = 0x803D0000
    program = [
        ppc.stwu(1, -0x20, 1),
        ppc.MFLR_R0,
        ppc.stw(0, 0x24, 1),
        ppc.stw(3, 0x8, 1),
        ppc.lwz(12, 0x28, 1),                  # C: the hook's sp+8
        ppc.lis(8, _hi(HUB_CONFIG)), ppc.addi(8, 8, _lo(HUB_CONFIG)),
        ppc.lbz(9, 0, 8),                      # hub chapter (0: not configured)
        ppc.lbz(10, 1, 8),                     # active byte index
        ppc.lbz(11, 2, 8),                     # active bit mask
        ppc.lbz(0, 3, 8),                      # destination byte index
        ppc.lbz(6, 4, 8),                      # pending byte index
        ppc.lis(7, _hi(FLAG_BITS)), ppc.addi(7, 7, _lo(FLAG_BITS)),
        ppc.lbzx(5, 7, 10), ppc.and_(5, 5, 11),  # active
        ppc.lbzx(10, 7, 0),                    # destination
        ppc.lbzx(11, 7, 6),                    # pending
        ppc.lis(3, base >> 16),
        ppc.lbz(4, rd_story._CURRENT_CHAPTER - base, 3),  # N
        ppc.mr(8, 4),
        ppc.cmplwi(9, 0), ("eq", "done"),
        ppc.cmplwi(12, rd_story.ENDING), ("eq", "done"),
        ppc.cmplw(12, 9), ("eq", "hub"),
        ppc.cmplwi(11, 0), ("eq", "no_pending"),
        ppc.cmplw(12, 11), ("ne", "normal_decide"),
        ppc.stbx(4, 7, 6), ppc.mr(11, 4),      # the pending chapter is done: N is pending now
        "normal_decide",
        ppc.cmplwi(5, 0), ("ne", "return_hub"),
        ppc.mr(4, 11), ("b", "clear_pending"),
        "no_pending",
        ppc.cmplwi(5, 0), ("eq", "done"),
        ppc.stbx(4, 7, 6), ("b", "return_hub"),
        "hub",
        ppc.cmplwi(5, 0), ("eq", "hub_exit"),
        ppc.cmplwi(10, 0), ("eq", "hub_exit"),
        ppc.mr(4, 10), ("b", "set"),
        "hub_exit",
        ppc.cmplwi(11, 0), ("eq", "return_hub"),
        ppc.mr(4, 11),
        "clear_pending",
        ppc.li(12, 0), ppc.stbx(12, 7, 6), ppc.stbx(12, 7, 0),
        ("b", "set"),
        "return_hub",
        ppc.mr(4, 9),
        "set",
        ppc.cmplw(4, 8), ("eq", "done"),
        ppc.lis(3, base >> 16), ppc.addi(3, 3, rd_story._PARTY - base),
        ("bl", rd_story._SET_CHAPTER),
        ppc.lis(6, base >> 16), ppc.li(5, 4),
        ppc.stb(5, rd_story._RESUME_POINT - base, 6),
        "done",
        ppc.lwz(3, 0x8, 1),
        ppc.lwz(0, 0x24, 1),
        ppc.MTLR_R0,
        ppc.addi(1, 1, 0x20),
        _LWZ_R0,                               # the hook instruction this patch replaced
        ppc.BLR,
    ]
    code = b"".join(_word(w) for w in ppc.assemble(HUB_HOOK, program))
    assert in_cave(HUB_HOOK, len(code)) and HUB_HOOK + len(code) <= HUB_CONFIG
    return code


def _edits() -> tuple[Edit, ...]:
    code = _router()
    return (
        # Managed only while the story runtime is on (its hook is all zeros otherwise), so this
        # branch is not what tells the patch's state.
        Edit(DONE, _word(_LWZ_R0), _word(ppc.bl(DONE, HUB_HOOK)), wild=((0, 4),)),
        Edit(HUB_HOOK, bytes(len(code)), code),
        Edit(HUB_CONFIG, bytes(CONFIG_SIZE), bytes(CONFIG_SIZE), wild=((0, CONFIG_SIZE),)),
    )


PATCH = Patch(
    "rd.hub.routing", "Chapters", "Hub chapter routing",
    "Routes victories through a saved hub destination and pending story chapter.",
    {RFEE01: _edits()}, internal=True)
rd_regions.install_entry(PATCH)


def validate_slots(hub_chapter: int, active_slot: int, destination_slot: int, pending_slot: int) -> bytes:
    """The five-byte router configuration for fixed global flag slots."""
    if not rd_story.CUSTOM_FIRST <= hub_chapter <= rd_story.CUSTOM_LAST:
        raise ValueError(f"The hub must be an added chapter ({rd_story.CUSTOM_FIRST}-{rd_story.CUSTOM_LAST}).")
    if not 0 <= active_slot < SLOT_COUNT:
        raise ValueError(f"The hub-active flag is outside the {SLOT_COUNT}-slot flag table.")
    if destination_slot % 8 or pending_slot != destination_slot + 8 or pending_slot + 7 >= SLOT_COUNT:
        raise ValueError("Destination and pending flags must occupy two consecutive whole bytes.")
    if destination_slot <= active_slot < pending_slot + 8:
        raise ValueError("The hub-active flag overlaps a chapter-number byte.")
    return bytes((hub_chapter, active_slot // 8, 1 << (active_slot % 8),
                  destination_slot // 8, pending_slot // 8))


class RdHubFlow:
    def __init__(self, editor):
        self.editor = editor

    @property
    def installed(self) -> bool:
        return self.editor.status(PATCH).state == State.APPLIED

    def config(self) -> bytes | None:
        return self.editor.dol.read(HUB_CONFIG, CONFIG_SIZE) if self.installed else None

    def apply(self, session, config: bytes) -> None:
        """Write the router and its configuration into ``session`` (the story runtime first)."""
        if session.patch_status(rd_story.PATCH).state == State.ORIGINAL:
            session.set_patch(rd_story.PATCH, True)
        if session.patch_status(rd_story.PATCH).state != State.APPLIED:
            raise ValueError("The Radiant Dawn story runtime conflicts with another patch.")
        status = session.patch_status(PATCH)
        if status.state not in (State.ORIGINAL, State.APPLIED):
            raise ValueError(f"Hub routing cannot be patched: {status.detail}")
        code = session.version.code if session.version is not None else RFEE01
        sites = PATCH.versions.get(code, PATCH.versions[RFEE01])
        expected = sites[0].patched if status.state == State.APPLIED else _word(_LWZ_R0)
        if session.dol.read(DONE, 4) != expected:
            raise ValueError("The story hook's last step conflicts with another patch.")
        session.set_patch(PATCH, True)
        session._write(HUB_CONFIG, config)

    def install(self, config: bytes) -> None:
        self.apply(self.editor.session, config)
        self.editor.save()

    def remove(self) -> None:
        if self.installed:
            self.editor.session.set_patch(PATCH, False)
            self.editor.save()
