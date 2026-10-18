"""Compose the normal-card runtime into an in-memory validation candidate.

This is not the production installer. It writes no project files and does not
open the release gate. Virtual-card mode remains outside the supported scope.
"""
from dataclasses import dataclass
import hashlib

from .dol import Dol, DolError
from .extended_flag_runtime import NativeImage, build_core
from .extended_flag_checkpoint import build_checkpoint_fragment
from .extended_flag_file_save import build_file_save_fragment
from .extended_flag_jp_file_save import build_jp_file_save_fragment
from .extended_flag_new_game import build_new_game_fragment
from .extended_flag_snapshot import build_snapshot_fragment
from .extended_flag_load import build_card_open_fragment, build_card_read_fragment
from .extended_flag_container import build_container_fragment
from .extended_flag_versions import build_version_fragment


@dataclass(frozen=True)
class RuntimeCandidate:
    region: str
    layout_identity: str
    source_sha256: str
    executable: bytes
    image: NativeImage
    hub_chapter: int | None = None


def build_candidate(dol, version, layout, *, hub_chapter=None):
    """Validate every fragment before editing a private executable copy."""
    original = bytes(dol.data)
    image = build_core(dol, version, layout)
    file_builder = build_jp_file_save_fragment if version == "GFEJ01" else build_file_save_fragment
    for builder in (file_builder, build_checkpoint_fragment, build_new_game_fragment,
                    build_snapshot_fragment, build_card_open_fragment, build_card_read_fragment,
                    build_container_fragment, build_version_fragment):
        image = builder(dol, version, image)
    end = -1
    for edit in sorted(image.edits, key=lambda e: e.address):
        if edit.address < end:
            raise DolError("Extended runtime edits overlap")
        if not edit.original or dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Extended runtime input changed during composition")
        end = edit.address + len(edit.original)
    if bytes(dol.data) != original:
        raise DolError("Extended runtime input changed during composition")
    candidate = Dol(original)
    candidate.add_text_section(image.base, image.data)
    for edit in image.edits:
        candidate.write(edit.address, edit.patched)
    if hub_chapter is not None:
        candidate = _with_hub(candidate, version, image, hub_chapter)
    return RuntimeCandidate(version, layout.identity, hashlib.sha256(original).hexdigest(),
                            bytes(candidate.data), image, hub_chapter)


def _with_hub(dol, version, image, chapter):
    """Prepare routing in the candidate only, preserving other story successors."""
    from .catalog import Session, State
    from .versions import VERSIONS
    from .chapter_flow import FLOW_PATCH, FLOW_TABLE
    from .hub_flow import HUB_PATCH, HUB_HOOK, HUB_CONFIG, _router, _SITES

    if type(chapter) is not int or not 33 <= chapter < 90:
        raise ValueError("The hub must be an added chapter from 33-89")
    session = Session(dol, VERSIONS[version])
    flow_status = session.patch_status(FLOW_PATCH)
    if flow_status.state not in (State.ORIGINAL, State.APPLIED):
        raise DolError("Story-flow patch conflicts with the extended hub candidate")
    if flow_status.state == State.ORIGINAL:
        session.set_patch(FLOW_PATCH, True)
    hub_status = session.patch_status(HUB_PATCH)
    if hub_status.state not in (State.ORIGINAL, State.APPLIED):
        raise DolError("Hub routing conflicts with the extended hub candidate")
    tail = HUB_PATCH.versions[version][0]
    expected = tail.patched if hub_status.state == State.APPLIED else tail.original
    if dol.read(tail.address, 4) != expected:
        raise DolError("Story-flow tail conflicts with the extended hub candidate")
    if hub_status.state == State.APPLIED and dol.read(HUB_CONFIG, 1) != bytes([chapter]):
        raise ValueError("Keep the existing hub chapter when migrating its storage")
    old_end = HUB_HOOK + len(HUB_PATCH.versions[version][1].patched)
    if any(dol.read(old_end, HUB_CONFIG - old_end)):
        raise DolError("Extended hub router padding conflicts with another patch")
    session.set_patch(HUB_PATCH, True)
    code = _router(_SITES[version][0], hub_state_address=image.hub_address)
    # Clear the whole old router's reserved span, including any trailing words.
    session._write(HUB_HOOK, code.ljust(HUB_CONFIG - HUB_HOOK, b"\0"))
    session._write(HUB_CONFIG, bytes((chapter, 0, 1, 1, 2)))
    session._write(FLOW_TABLE + chapter, bytes([chapter]))
    return dol
