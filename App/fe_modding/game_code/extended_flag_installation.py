"""Verify generated runtime bytes, rather than trusting project settings alone."""
from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from .dol import Dol, DolError
from .extended_flag_metadata import REVISION, read_metadata
from .extended_flag_runtime import BASE, RECORD_OFFSET
from ..formats.extended_flags import FlagLayout, HEADER, MANIFEST_NAME
from ..game_profile import sys_root_of

RECEIPT_NAME = "extended_flags_installation.json"


class RuntimeState(Enum):
    ABSENT = "not installed"
    MATCHING = "installed and matching"
    MANIFEST_MISMATCH = "manifest mismatch"
    CONFLICT = "code conflict"
    UNSUPPORTED = "unsupported revision"
    RECOVERY = "recovery required"


@dataclass(frozen=True)
class RuntimeStatus:
    state: RuntimeState
    detail: str = ""
    layout: FlagLayout | None = None


def receipt_for(candidate, layout):
    return json.dumps({
        "version": 1, "revision": REVISION, "region": candidate.region,
        "base": candidate.image.base, "layout": layout.to_json(),
        "hub_chapter": candidate.hub_chapter,
        "section_sha256": hashlib.sha256(candidate.image.data).hexdigest(),
        "edits": [{"address": e.address, "before": e.original.hex(), "after": e.patched.hex()}
                  for e in candidate.image.edits],
    }, indent=2, sort_keys=True) + "\n"


def _restore(dol, receipt):
    scratch = Dol(bytes(dol.data))
    seen = set()
    for edit in receipt["edits"]:
        address = edit["address"]
        before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
        if type(address) is not int or not before or len(before) != len(after):
            raise ValueError("Invalid installed edit")
        addresses = set(range(address, address + len(before)))
        if seen & addresses or scratch.read(address, len(after)) != after:
            raise ValueError("Installed hook differs from its receipt")
        seen.update(addresses)
        scratch.write(address, before)
    scratch.remove_section_at(BASE)
    chapter = receipt["hub_chapter"]
    if chapter is not None:
        from . import hub_flow as hub, chapter_flow as flow
        from .catalog import Session, State
        from .versions import VERSIONS
        version = receipt["region"]
        if type(chapter) is not int or not 33 <= chapter < 90:
            raise ValueError("Invalid installed hub chapter")
        code = hub._router(flow._SITES[version][0], hub_state_address=BASE + RECORD_OFFSET + HEADER.size)
        expected = code.ljust(hub.HUB_CONFIG - hub.HUB_HOOK, b"\0")
        if (dol.read(hub.HUB_HOOK, len(expected)) != expected or
                dol.read(hub.HUB_CONFIG, 5) != bytes((chapter, 0, 1, 1, 2)) or
                dol.read(flow.FLOW_TABLE + chapter, 1) != bytes([chapter])):
            raise ValueError("Installed hub routing differs from its manifest")
        tail = hub.HUB_PATCH.versions[version][0]
        if dol.read(tail.address, 4) != tail.patched:
            raise ValueError("Installed hub tail branch differs")
        if Session(scratch, VERSIONS[version]).patch_status(flow.FLOW_PATCH).state != State.APPLIED:
            raise ValueError("Required chapter-flow patch differs")
        legacy = hub._router(flow._SITES[version][0])
        scratch.write(hub.HUB_HOOK, legacy.ljust(hub.HUB_CONFIG - hub.HUB_HOOK, b"\0"))
    return scratch


def inspect_runtime(dol, region, layout, receipt_source):
    """Rebuild from guarded original hooks, then compare all owned bytes."""
    if not dol.has_section_at(BASE):
        return RuntimeStatus(RuntimeState.CONFLICT if receipt_source is not None else RuntimeState.ABSENT,
                             "Runtime section is missing")
    try:
        section = dol.section_at(BASE)
        data = dol.read(BASE, section.size)
        revision, embedded_region, embedded = read_metadata(data)
        if revision != REVISION:
            return RuntimeStatus(RuntimeState.UNSUPPORTED, f"Runtime revision {revision}", embedded)
        if embedded_region != region:
            raise ValueError("Executable region differs from runtime metadata")
        if layout is None or embedded != layout:
            return RuntimeStatus(RuntimeState.MANIFEST_MISMATCH, "Project and embedded manifests differ", embedded)
        if receipt_source is None:
            raise ValueError("Installation receipt is missing")
        receipt = json.loads(receipt_source)
        if receipt["version"] != 1 or receipt["revision"] != REVISION:
            return RuntimeStatus(RuntimeState.UNSUPPORTED, "Installation receipt revision is unsupported", embedded)
        if receipt["region"] != region or receipt["base"] != BASE or receipt["layout"] != embedded.to_json():
            raise ValueError("Installation receipt does not match embedded metadata")
        if hashlib.sha256(data).hexdigest() != receipt["section_sha256"]:
            raise ValueError("Runtime section differs from its installed bytes")
        scratch = _restore(dol, receipt)
        from .extended_flag_candidate import build_candidate
        expected = build_candidate(scratch, region, embedded, hub_chapter=receipt["hub_chapter"])
        if expected.image.data != data:
            raise ValueError("Runtime code differs from the supported generator")
        expected_receipt = json.loads(receipt_for(expected, embedded))
        if receipt != expected_receipt:
            raise ValueError("Installation edits differ from the supported generator")
        for edit in expected.image.edits:
            if dol.read(edit.address, len(edit.patched)) != edit.patched:
                raise ValueError("Installed hook differs from generated runtime")
        return RuntimeStatus(RuntimeState.MATCHING, layout=embedded)
    except (ValueError, TypeError, KeyError, OSError, DolError, AttributeError) as exc:
        return RuntimeStatus(RuntimeState.CONFLICT, str(exc))


def rebuild_installed(dol, region, previous, layout, receipt_source):
    """Prepare a compatible update without changing the source executable."""
    status = inspect_runtime(dol, region, previous, receipt_source)
    if status.state != RuntimeState.MATCHING:
        raise ValueError(f"Cannot update runtime: {status.state.value}: {status.detail}")
    layout.require_compatible(previous)
    receipt = json.loads(receipt_source)
    scratch = _restore(dol, receipt)
    from .extended_flag_candidate import build_candidate
    return build_candidate(scratch, region, layout, hub_chapter=receipt["hub_chapter"])


def inspect_project(project):
    from ..project_transaction import JOURNAL
    from .versions import read_boot_code
    if (project.directory / JOURNAL).exists():
        return RuntimeStatus(RuntimeState.RECOVERY, "An interrupted installation needs recovery")
    try:
        manifest = project.directory / MANIFEST_NAME
        receipt_path = project.directory / RECEIPT_NAME
        layout = FlagLayout.from_json(manifest.read_text(encoding="utf-8")) if manifest.exists() else None
        receipt = receipt_path.read_text(encoding="utf-8") if receipt_path.exists() else None
        executable = sys_root_of(project) / "main.dol"
        if not executable.exists():
            return RuntimeStatus(RuntimeState.ABSENT, "Project executable is missing")
        status = inspect_runtime(Dol.open(executable), read_boot_code(project.extracted_dir), layout, receipt)
        if status.state == RuntimeState.MATCHING:
            from ..hub import config_path
            record = json.loads(receipt)
            if record["hub_chapter"] is not None:
                config = json.loads(config_path(project).read_text(encoding="utf-8"))
                if (config.get("version") != 3 or config.get("storage") != "extended"
                        or config.get("chapter") != record["hub_chapter"]
                        or config.get("layout_identity") != layout.identity):
                    return RuntimeStatus(RuntimeState.MANIFEST_MISMATCH, "Hub configuration differs from installed runtime", layout)
        return status
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return RuntimeStatus(RuntimeState.CONFLICT, str(exc))
