"""XLSX round trips for script flag registrations."""
from __future__ import annotations

from . import excel_io


def export_flags(path, campaign, chapters, *, layout=None):
    """Write registrations; save-file bit values are not project data."""
    if layout is not None:
        excel_io.write_workbook(path, _banked_sheets(campaign, chapters, layout))
        return
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


def _banked_sheets(campaign, chapters, layout):
    from .formats.extended_flags import HUB_ALIASES

    def rows(names, chapter=None):
        vanilla_slot = 0 if chapter is None else 95
        result = []
        for order, name in enumerate(names):
            entry = layout.find(name, chapter)
            if name in HUB_ALIASES:
                storage, slot = "hub", ".".join(map(str, HUB_ALIASES[name]))
            elif entry is not None:
                storage, slot = "extended", entry.slot
            else:
                storage, slot = "vanilla", vanilla_slot
                vanilla_slot += 1 if chapter is None else -1
            result.append([order, name, storage, slot])
        return result
    return {
        "Flag Layout": [["format", "layout_uuid"], [2, layout.identity]],
        "Campaign Flags": [["order", "name", "storage", "slot"], *rows(campaign)],
        "Chapter Flags": [["chapter", "order", "name", "storage", "slot"],
                          *[[chapter, *row] for chapter, names in chapters.items() for row in rows(names, int(chapter))]],
    }


def plan_banked_import(path, campaign, chapters, layout):
    """Return a compatible layout and append-only registrations, or raise.

    Old workbooks keep existing bank assignments; new rows without bank metadata
    are explicitly treated as vanilla, never automatically spilled.
    """
    from .formats import event_flags as ef
    sheets = excel_io.read_workbook(path)
    if "Flag Layout" not in sheets:
        additions, errors = plan_flag_import(path, campaign, chapters, 1 << 30, ef.check_flag_name)
        if errors:
            raise ValueError("\n".join(errors))
        updated = layout
    else:
        metadata = sheets["Flag Layout"]
        if metadata != [["format", "layout_uuid"], [2, layout.identity]]:
            raise ValueError("Workbook layout identity or format does not match this project")
        expected = _banked_sheets(campaign, chapters, layout)
        groups = {"campaign": [], **{chapter: [] for chapter in chapters}}
        for sheet, key in (("Campaign Flags", "campaign"), ("Chapter Flags", None)):
            table = sheets.get(sheet, [])
            if not table or table[0] != expected[sheet][0]:
                raise ValueError(f"{sheet}: unexpected banked workbook columns")
            for row in table[1:]:
                if not any(value not in (None, "") for value in row):
                    continue
                if len(row) > len(table[0]):
                    raise ValueError(f"{sheet}: too many row values")
                row = list(row) + [None] * (len(table[0]) - len(row))
                group = key if key else str(row.pop(0))
                if group not in groups:
                    raise ValueError(f"Unknown chapter {group}")
                if excel_io._num(row[0], "order") != len(groups[group]):
                    raise ValueError(f"{sheet}: registration order changed")
                groups[group].append(row)
        additions, updated = {}, layout
        for group, rows in groups.items():
            current = campaign if group == "campaign" else chapters[group]
            old = expected["Campaign Flags"][1:] if group == "campaign" else [row[1:] for row in expected["Chapter Flags"][1:] if row[0] == group]
            if rows[:len(current)] != old:
                raise ValueError(f"{group}: existing names, banks and slots must stay unchanged")
            additions[group] = []
            for _, name, storage, slot in rows[len(current):]:
                if not isinstance(name, str) or storage not in ("vanilla", "extended"):
                    raise ValueError(f"{group}: new flags need a name and explicit vanilla/extended storage")
                name = name.strip()
                problem = ef.check_flag_name(name, set(current) | set(additions[group]) | set(campaign))
                if problem or name.startswith(("HUB_", "gf_")):
                    raise ValueError(problem or "Hub and engine flag names are reserved")
                if storage == "extended":
                    updated = updated.add(name, "campaign" if group == "campaign" else "chapter",
                                          None if group == "campaign" else int(group))
                    expected_slot = updated.entries[-1].slot
                else:
                    existing = current + additions[group]
                    count = len(updated.vanilla_names(existing, "campaign" if group == "campaign" else "chapter",
                                                       None if group == "campaign" else int(group)))
                    expected_slot = count if group == "campaign" else 95 - count
                if slot not in (None, "") and excel_io._num(slot, "slot") != expected_slot:
                    raise ValueError(f"{group}: new flag must use slot {expected_slot}")
                additions[group].append(name)
    globals_ = campaign + additions["campaign"]
    if any(name.startswith(("HUB_", "gf_")) for names in additions.values() for name in names):
        raise ValueError("Hub and engine flag names are reserved")
    locals_ = {int(chapter): names + additions[chapter] for chapter, names in chapters.items()}
    updated.validate_registrations(globals_, locals_)
    problem = ef.capacity_problem(len(updated.vanilla_names(globals_, "campaign")), 0)
    if problem:
        raise ValueError(problem)
    for chapter, names in locals_.items():
        vanilla_globals = updated.vanilla_names(globals_, "campaign")
        vanilla_locals = updated.vanilla_names(names, "chapter", chapter)
        problem = ef.capacity_problem(len(vanilla_globals), len(vanilla_locals))
        if problem:
            raise ValueError(f"Chapter {chapter}: {problem}")
        added_locals = next(additions[key] for key in chapters if int(key) == chapter)
        if set(additions["campaign"]) & set(names) or set(added_locals) & set(globals_):
            raise ValueError(f"Chapter {chapter}: campaign/chapter name collision")
    return updated, additions
