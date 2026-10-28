"""Release gate for the extended event-flag runtime.

The host format is implemented in formats.extended_flags. No retail executable
is approved yet: mapped function starts do not prove safe writer hooks, early
memory reservation, or resume ordering. Never ship a patch with partial hooks.
"""
from __future__ import annotations

from .catalog import Patch
from ..exceptions import ProjectError
from ..formats.extended_flags import FlagLayout, MANIFEST_NAME

UNAVAILABLE_REASON = (
    "Extended event flags are not available in the game yet. "
    "The normal-card runtime candidates still need final editor checks, "
    "save-error validation, and Dolphin validation for US, EU and JP. "
    "The manifest and save editor do not install those hooks."
)

# Deliberately absent from CATALOG: it only contains fully mapped retail patches.
EXTENDED_FLAGS_PATCH = Patch(
    "events.extended_flags", "Events", "Extended event flags",
    "Separate saved hub state, 1,024 campaign flags and 256 chapter flags. " + UNAVAILABLE_REASON,
    versions={},
)


def require_project_runtime(project) -> None:
    """Require both release approval and verified installation before writes."""
    from ..project_transaction import JOURNAL
    if (project.directory / JOURNAL).exists():
        raise ProjectError("An interrupted extended-flag installation needs recovery before building or editing scripts.")
    path = project.directory / MANIFEST_NAME
    from .extended_flag_installation import RECEIPT_NAME, inspect_project, RuntimeState
    from .extended_flag_runtime import BASE
    from .dol import Dol
    from .versions import read_boot_code
    from ..game_files import files_of
    extracted = files_of(project).at("")
    executable = extracted / "sys" / "main.dol"
    opted_in = path.exists() or (project.directory / RECEIPT_NAME).exists()
    if not opted_in and executable.exists():
        opted_in = Dol.open(executable).has_section_at(BASE)
    if not opted_in:
        return
    if read_boot_code(extracted) not in EXTENDED_FLAGS_PATCH.versions:
        raise ProjectError(UNAVAILABLE_REASON)
    status = inspect_project(project)
    if status.state != RuntimeState.MATCHING:
        raise ProjectError(f"Extended flags: {status.state.value}: {status.detail}")
