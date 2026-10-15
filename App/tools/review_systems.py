"""Validate and report coverage of the FE9 system inventory.

Articles claim responsibility with ``system_entries``.  A review (by a person or
an AI agent) is a separate assertion in ``system_reviewed``; unresolved but well-disclosed work
also appears in ``system_reviewed_with_gaps`` and must document both the gap
and the investigation already attempted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"
INVENTORY = WIKI / "meta" / "game-systems-inventory.md"
REVIEW_PAGE = WIKI / "meta" / "system-review.md"
START_MARKER = "<!-- SYSTEM_REVIEW_REPORT_START -->"
END_MARKER = "<!-- SYSTEM_REVIEW_REPORT_END -->"
SYSTEM_ID = re.compile(r"FE9-SYS-\d{3}")
ENTRY = re.compile(
    r'^\d+\.\s+<span id="(fe9-sys-\d{3})"></span>\s+\*\*(FE9-SYS-\d{3}) — ([^*]+)\*\*',
    re.M,
)
REQUIRED_REVIEW_SECTIONS = {
    "mental model or example": re.compile(r"^##\s+.*(?:mental model|example|in practice|walkthrough)", re.I | re.M),
    "rules or lifecycle": re.compile(r"^##\s+.*(?:how|rules|calculation|resolution|lifecycle|flow|process)", re.I | re.M),
    "limits or interactions": re.compile(r"^##\s+.*(?:limits|edge cases|interactions|known gaps|what remains|compatibility)", re.I | re.M),
}


def parse_scalar(value: str):
    value = value.strip()
    if value.startswith(("[", "{", '"')):
        return json.loads(value)
    if value in {"true", "false"}:
        return value == "true"
    return value


def read_page(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\s*\n(.*?)\n---\s*\n(.*)", text, re.S)
    if not match:
        raise ValueError("missing YAML front matter")
    metadata: dict[str, object] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or line.startswith((" ", "\t")):
            raise ValueError(f"unsupported front-matter line: {line!r}")
        metadata[key.strip()] = parse_scalar(value)
    return metadata, match.group(2)


def inventory_entries() -> dict[str, str]:
    text = INVENTORY.read_text(encoding="utf-8")
    entries: dict[str, str] = {}
    for anchor, system_id, title in ENTRY.findall(text):
        if anchor != system_id.lower():
            raise ValueError(f"{system_id}: anchor is {anchor!r}")
        if system_id in entries:
            raise ValueError(f"duplicate inventory id {system_id}")
        entries[system_id] = title.strip()
    return entries


def list_field(meta: dict, field: str, path: Path, errors: list[str]) -> list[str]:
    value = meta.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{path.relative_to(WIKI).as_posix()}: {field} must be a JSON-style string list")
        return []
    return value


def gap_map(values: list[str], field: str, path: Path, errors: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        system_id, separator, explanation = value.partition(":")
        system_id = system_id.strip()
        explanation = explanation.strip()
        if not separator or not SYSTEM_ID.fullmatch(system_id) or len(explanation.split()) < 6:
            errors.append(
                f"{path.relative_to(WIKI).as_posix()}: {field} entries need "
                "'FE9-SYS-NNN: a meaningful explanation of at least six words'"
            )
            continue
        result[system_id] = explanation
    return result


def review_repository() -> tuple[list[str], dict[str, dict]]:
    errors: list[str] = []
    try:
        entries = inventory_entries()
    except ValueError as exc:
        return [f"meta/game-systems-inventory.md: {exc}"], {}
    if len(entries) != 384:
        errors.append(f"meta/game-systems-inventory.md: expected 384 stable system IDs, found {len(entries)}")

    coverage: dict[str, list[tuple[str, str]]] = defaultdict(list)
    reviewed: dict[str, list[str]] = defaultdict(list)
    with_gaps: set[str] = set()
    proposals: list[tuple[Path, dict, str]] = []

    for path in sorted(WIKI.rglob("*.md")):
        try:
            meta, body = read_page(path)
        except (ValueError, json.JSONDecodeError):
            continue  # The main wiki validator reports general metadata errors.
        if meta.get("article_type") == "system-proposal":
            proposals.append((path, meta, body))
        claimed = list_field(meta, "system_entries", path, errors)
        passed = list_field(meta, "system_reviewed", path, errors)
        gap_ids = list_field(meta, "system_reviewed_with_gaps", path, errors)
        gaps = gap_map(list_field(meta, "system_known_gaps", path, errors), "system_known_gaps", path, errors)
        attempts = gap_map(list_field(meta, "system_gap_work", path, errors), "system_gap_work", path, errors)

        for field, values in (("system_entries", claimed), ("system_reviewed", passed),
                              ("system_reviewed_with_gaps", gap_ids)):
            duplicates = sorted({value for value in values if values.count(value) > 1})
            if duplicates:
                errors.append(f"{path.relative_to(WIKI).as_posix()}: duplicate IDs in {field}: {duplicates}")
            unknown = sorted(set(values) - set(entries))
            if unknown:
                errors.append(f"{path.relative_to(WIKI).as_posix()}: unknown IDs in {field}: {unknown}")
        if not set(passed).issubset(claimed):
            errors.append(f"{path.relative_to(WIKI).as_posix()}: system_reviewed must be a subset of system_entries")
        if not set(gap_ids).issubset(passed):
            errors.append(
                f"{path.relative_to(WIKI).as_posix()}: system_reviewed_with_gaps must be a subset of system_reviewed"
            )

        for system_id in claimed:
            coverage[system_id].append((str(meta.get("id", path.stem)), path.relative_to(WIKI).as_posix()))
        for system_id in passed:
            reviewed[system_id].append(meta.get("id", path.stem))
            if not re.search(rf'(?:id=["\']{system_id.lower()}["\']|\b{system_id}\b)', body):
                errors.append(
                    f"{path.relative_to(WIKI).as_posix()}: reviewed {system_id} needs an in-article "
                    f"{system_id} label or id=\"{system_id.lower()}\" anchor"
                )
        if passed:
            if meta.get("status") != "published":
                errors.append(f"{path.relative_to(WIKI).as_posix()}: reviewed systems require status published")
            reviewer = str(meta.get("system_reviewed_by", "")).strip()
            reviewed_on = str(meta.get("system_reviewed_on", "")).strip()
            if not reviewer:
                errors.append(f"{path.relative_to(WIKI).as_posix()}: reviewed systems require system_reviewed_by")
            try:
                when = date.fromisoformat(reviewed_on)
                if when > date.today():
                    errors.append(f"{path.relative_to(WIKI).as_posix()}: system_reviewed_on cannot be in the future")
            except ValueError:
                errors.append(f"{path.relative_to(WIKI).as_posix()}: reviewed systems require YYYY-MM-DD system_reviewed_on")
            words = re.findall(r"\b[\w'-]+\b", re.sub(r"`[^`]*`", "", body))
            if len(words) < 700:
                errors.append(f"{path.relative_to(WIKI).as_posix()}: reviewed article needs at least 700 words")
            for label, pattern in REQUIRED_REVIEW_SECTIONS.items():
                if not pattern.search(body):
                    errors.append(f"{path.relative_to(WIKI).as_posix()}: reviewed article needs a {label} section")
        for system_id in gap_ids:
            with_gaps.add(system_id)
            if system_id not in gaps:
                errors.append(f"{path.relative_to(WIKI).as_posix()}: {system_id} needs a system_known_gaps entry")
            if system_id not in attempts:
                errors.append(f"{path.relative_to(WIKI).as_posix()}: {system_id} needs a system_gap_work entry")
        if gap_ids and not re.search(r"^##\s+(?:Known gaps|What remains unknown|Known limits)", body, re.I | re.M):
            errors.append(f"{path.relative_to(WIKI).as_posix()}: reviewed-with-gaps article needs a Known gaps section")

    for system_id, owners in reviewed.items():
        if len(owners) > 1:
            errors.append(f"{system_id}: reviewed by multiple primary articles {owners}")

    proposal_ids: set[str] = set()
    declared_sources = set(
        re.findall(r"^`([a-z0-9][a-z0-9-]*)`\s*$", (WIKI / "meta" / "sources.md").read_text(encoding="utf-8"), re.M)
    )
    for path, meta, body in proposals:
        relative = path.relative_to(WIKI).as_posix()
        proposal_id = str(meta.get("id", ""))
        if proposal_id in proposal_ids:
            errors.append(f"{relative}: duplicate proposal id {proposal_id!r}")
        proposal_ids.add(proposal_id)
        for field in ("proposed_system_name", "proposed_system_scope", "proposed_system_reason"):
            if len(str(meta.get(field, "")).split()) < 4:
                errors.append(f"{relative}: {field} needs a meaningful description")
        evidence = list_field(meta, "proposed_system_evidence", path, errors)
        if not evidence:
            errors.append(f"{relative}: proposed_system_evidence must cite at least one source key")
        unknown_evidence = sorted(set(evidence) - declared_sources)
        if unknown_evidence:
            errors.append(
                f"{relative}: proposed_system_evidence uses undeclared source keys {unknown_evidence}; "
                "document them in meta/sources.md first"
            )
        state = meta.get("proposal_status")
        if state not in {"proposed", "accepted", "rejected", "merged"}:
            errors.append(f"{relative}: invalid proposal_status {state!r}")
        for heading in ("Why this is a distinct system", "Supporting documentation", "Inputs, rules, and outputs",
                        "Relationship to the existing inventory", "Known gaps"):
            if not re.search(rf"^##\s+{re.escape(heading)}\s*$", body, re.I | re.M):
                errors.append(f"{relative}: proposal needs section {heading!r}")
        accepted_id = str(meta.get("accepted_system_id", "")).strip()
        if state in {"accepted", "merged"} and accepted_id not in entries:
            errors.append(f"{relative}: accepted/merged proposal needs a valid accepted_system_id")
        if state == "merged" and accepted_id not in coverage:
            errors.append(f"{relative}: merged proposal {accepted_id} needs a covering article")

    state: dict[str, dict] = {}
    for system_id, title in entries.items():
        if system_id in reviewed:
            status = "reviewed with gaps" if system_id in with_gaps else "reviewed"
        elif system_id in coverage:
            status = "covered, review pending"
        else:
            status = "uncovered"
        state[system_id] = {"title": title, "status": status, "articles": coverage.get(system_id, [])}
    return errors, state


def report_block(state: dict[str, dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in state.values():
        counts[item["status"]] += 1
    lines = [
        START_MARKER,
        "",
        "_Generated by `python App/tools/review_systems.py --write-report`; do not edit this block by hand._",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for label in ("reviewed", "reviewed with gaps", "covered, review pending", "uncovered"):
        lines.append(f"| {label.capitalize()} | {counts[label]} |")
    lines.extend(["", "| Inventory ID | System | Review state | Covering article(s) |", "|---|---|---|---|"])
    for system_id, item in state.items():
        inventory_link = f"[${system_id}](game-systems-inventory.md#{system_id.lower()})".replace("$", "")
        articles = ", ".join(f"[{article}](../{path})" for article, path in item["articles"]) or "—"
        lines.append(f"| {inventory_link} | {item['title']} | {item['status']} | {articles} |")
    lines.extend(["", END_MARKER])
    return "\n".join(lines)


def update_or_check_report(state: dict[str, dict], write: bool) -> str | None:
    text = REVIEW_PAGE.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.S)
    replacement = report_block(state)
    if not pattern.search(text):
        return "meta/system-review.md: generated report markers are missing"
    updated = pattern.sub(replacement, text)
    if updated == text:
        return None
    if write:
        REVIEW_PAGE.write_bytes(updated.encode("utf-8"))
        return None
    return "meta/system-review.md: coverage report is stale; run python App/tools/review_systems.py --write-report"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate metadata and require a current report")
    parser.add_argument("--write-report", action="store_true", help="refresh the generated report in the review page")
    args = parser.parse_args()
    errors, state = review_repository()
    if state and (args.check or args.write_report):
        report_error = update_or_check_report(state, args.write_report)
        if report_error:
            errors.append(report_error)
    counts: dict[str, int] = defaultdict(int)
    for item in state.values():
        counts[item["status"]] += 1
    print(
        f"Systems: {len(state)}; reviewed {counts['reviewed']}; reviewed with gaps "
        f"{counts['reviewed with gaps']}; pending {counts['covered, review pending']}; "
        f"uncovered {counts['uncovered']}"
    )
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
