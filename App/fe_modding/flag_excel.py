"""XLSX round trips for script flag registrations."""
from __future__ import annotations

from . import excel_io


def export_flags(path, campaign, chapters):
    """Write registrations; save-file bit values are not project data."""
    sheets = {
        "Campaign Flags": [["slot", "name"]] + [[slot, name] for slot, name in enumerate(campaign)],
        "Chapter Flags": [["chapter", "order", "name"]] +
            [[chapter, order, name] for chapter, names in chapters.items()
             for order, name in enumerate(names)],
    }
    excel_io.write_workbook(path, sheets)


def plan_flag_import(path, campaign, chapters, slot_count, check_name):
    """Validate append-only changes before any script is written."""
    sheets = excel_io.read_workbook(path)
    if not {"Campaign Flags", "Chapter Flags"}.issubset(sheets):
        return {}, ["Expected Campaign Flags and Chapter Flags worksheets."]
    errors = []

    def read_rows(sheet, headers):
        rows = sheets[sheet]
        if not rows:
            errors.append(f"{sheet}: missing header row")
            return []
        cols = {str(value).strip().casefold(): i for i, value in enumerate(rows[0]) if value is not None}
        if not set(headers).issubset(cols):
            errors.append(f"{sheet}: expected columns {', '.join(headers)}")
            return []
        result = []
        for rn, row in enumerate(rows[1:], 2):
            if not any(value not in (None, "") for value in row):
                continue
            result.append((rn, [row[cols[field]] if cols[field] < len(row) else None for field in headers]))
        return result

    imported_campaign = []
    for rn, (slot, name) in read_rows("Campaign Flags", ("slot", "name")):
        try:
            number = excel_io._num(slot, "slot")
            if number != len(imported_campaign):
                raise ValueError(f"expected slot {len(imported_campaign)}")
            if name in (None, ""):
                raise ValueError("name is empty")
            imported_campaign.append(str(name).strip())
        except ValueError as exc:
            errors.append(f"Campaign Flags row {rn}: {exc}")
    if imported_campaign[:len(campaign)] != campaign or len(imported_campaign) < len(campaign):
        errors.append("Campaign Flags: existing slots must remain in their original order.")
    additions = {"campaign": imported_campaign[len(campaign):]}

    imported_chapters = {chapter: [] for chapter in chapters}
    for rn, (chapter, order, name) in read_rows("Chapter Flags", ("chapter", "order", "name")):
        chapter = str(chapter).strip() if chapter is not None else ""
        if chapter not in chapters:
            errors.append(f"Chapter Flags row {rn}: unknown chapter {chapter!r}")
            continue
        try:
            number = excel_io._num(order, "order")
            if number != len(imported_chapters[chapter]):
                raise ValueError(f"expected order {len(imported_chapters[chapter])} for {chapter}")
            if name in (None, ""):
                raise ValueError("name is empty")
            imported_chapters[chapter].append(str(name).strip())
        except ValueError as exc:
            errors.append(f"Chapter Flags row {rn}: {exc}")
    for chapter, current in chapters.items():
        names = imported_chapters[chapter]
        if names[:len(current)] != current or len(names) < len(current):
            errors.append(f"Chapter Flags: existing registrations for {chapter} must remain in their original order.")
        additions[chapter] = names[len(current):]

    taken = set(campaign)
    for name in additions["campaign"]:
        problem = check_name(name, taken)
        if problem:
            errors.append(f"Campaign Flags: {name!r}: {problem}")
        taken.add(name)
    if len(imported_campaign) >= slot_count:
        errors.append(f"Campaign Flags: the {slot_count}-slot flag table is full.")
    for chapter, names in imported_chapters.items():
        local_taken = set(taken) | set(chapters[chapter])
        for name in additions[chapter]:
            problem = check_name(name, local_taken)
            if problem:
                errors.append(f"Chapter Flags {chapter}: {name!r}: {problem}")
            local_taken.add(name)
        if len(imported_campaign) + len(names) >= slot_count:
            errors.append(f"Chapter Flags {chapter}: registrations exceed the {slot_count}-slot table.")
    return additions, errors
