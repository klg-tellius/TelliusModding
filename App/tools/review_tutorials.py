"""Validate the staged migration from short tutorials to the deep curriculum."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODDING = ROOT / "wiki" / "modding"
LEDGER = ROOT / "wiki" / "meta" / "tutorial-coverage.md"

STAGES = {"legacy", "inventory", "draft", "verified", "published"}
TRACKS = {
    "start-safely", "campaign-foundations", "characters-and-game-data", "maps",
    "units-and-events", "dialogue-and-text", "ai-economy-and-media",
    "models-and-battle-presentation", "test-and-release",
}
VERIFICATION = {
    "source-reviewed", "app-tested", "simulator-tested", "dolphin-tested", "inferred", "unknown",
}
DEEP_STAGES = {"draft", "verified", "published"}
KINDS = {"task", "reference"}
REQUIRED_TASK_HEADINGS = {
    "What you will make",
    "Before you begin",
    "How the editor fits together",
    "Guided walkthrough",
    "Interactions and precedence",
    "Test matrix",
    "Troubleshooting",
    "Save, build, and revert",
    "Limits and confidence",
    "Related tutorials and references",
}
REQUIRED_REFERENCE_HEADINGS = {
    "How this surface fits together",
    "Control reference",
    "Interactions and precedence",
    "Failure modes",
    "Limits and confidence",
    "Related tutorials and references",
}
VAGUE = re.compile(r"\b(?:adjust as needed|set appropriately|configure as needed|test it)\b", re.I)


def _parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\s*\n(.*?)\n---\s*\n(.*)", text, re.S)
    if not match:
        return {}, text
    metadata: dict[str, object] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or line.startswith((" ", "\t")):
            continue
        value = value.strip()
        if value.startswith(("[", "{", '"')):
            try:
                metadata[key.strip()] = json.loads(value)
            except json.JSONDecodeError:
                metadata[key.strip()] = value
        else:
            metadata[key.strip()] = value
    return metadata, match.group(2)


def review_tutorials() -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    pages: dict[str, tuple[Path, dict, str]] = {}
    counts = {stage: 0 for stage in STAGES}

    for path in sorted(MODDING.glob("*.md")):
        if path.name == "index.md":
            continue
        meta, body = _parse(path)
        article_id = str(meta.get("id", ""))
        pages[article_id] = (path, meta, body)
        numbered = re.match(r"^\d{2}-", path.name) is not None
        stage = str(meta.get("tutorial_stage", "legacy"))
        if stage not in STAGES:
            errors.append(f"{path.relative_to(ROOT)}: invalid tutorial_stage {stage!r}")
            continue
        if numbered:
            counts[stage] += 1

        if "tutorial_stage" not in meta:
            continue  # Existing pages remain usable while their batch is migrated.
        kind = str(meta.get("tutorial_kind", "task" if numbered else ""))
        if kind not in KINDS:
            errors.append(f"{path.relative_to(ROOT)}: invalid or missing tutorial_kind {kind!r}")
        if numbered and kind != "task":
            errors.append(f"{path.relative_to(ROOT)}: numbered curriculum pages must use tutorial_kind 'task'")
        track = str(meta.get("tutorial_track", ""))
        if track not in TRACKS:
            errors.append(f"{path.relative_to(ROOT)}: invalid or missing tutorial_track {track!r}")
        prerequisites = meta.get("prerequisites")
        if not isinstance(prerequisites, list):
            errors.append(f"{path.relative_to(ROOT)}: prerequisites must be a JSON-style list")
        verification = meta.get("verification")
        if not isinstance(verification, list) or not verification:
            errors.append(f"{path.relative_to(ROOT)}: verification must be a non-empty JSON-style list")
        elif unknown := set(verification) - VERIFICATION:
            errors.append(f"{path.relative_to(ROOT)}: unknown verification levels {sorted(unknown)}")

        if stage in DEEP_STAGES:
            headings = set(re.findall(r"^##\s+(.+?)\s*$", body, re.M))
            required = REQUIRED_TASK_HEADINGS if kind == "task" else REQUIRED_REFERENCE_HEADINGS
            missing = required - headings
            if missing:
                errors.append(f"{path.relative_to(ROOT)}: deep tutorial missing headings {sorted(missing)}")
            if kind == "task" and not ({"Understand every control", "Understand every choice"} & headings):
                errors.append(f"{path.relative_to(ROOT)}: deep tutorial needs a control or choice reference")
            if VAGUE.search(body):
                errors.append(f"{path.relative_to(ROOT)}: contains an unbounded vague instruction")
            if stage in {"verified", "published"} and len(verification or []) < 2:
                errors.append(f"{path.relative_to(ROOT)}: verified tutorial needs at least two verification levels")

    for article_id, (path, meta, _body) in pages.items():
        for dependency in meta.get("prerequisites", []) if isinstance(meta.get("prerequisites"), list) else []:
            if dependency not in pages:
                errors.append(f"{path.relative_to(ROOT)}: unknown prerequisite id {dependency!r}")

    if not LEDGER.exists():
        errors.append("wiki/meta/tutorial-coverage.md: coverage ledger is missing")
    else:
        ledger = LEDGER.read_text(encoding="utf-8")
        numbered_rows = re.findall(r"^\|\s*(\d{2})\s*\|", ledger, re.M)
        expected = {path.name[:2] for path in MODDING.glob("[0-9][0-9]-*.md")}
        found = set(numbered_rows)
        if found != expected:
            errors.append(
                "wiki/meta/tutorial-coverage.md: lesson ledger differs from the numbered lessons "
                f"(missing {sorted(expected - found)}, extra {sorted(found - expected)})"
            )

    return errors, counts


def main() -> int:
    errors, counts = review_tutorials()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    summary = ", ".join(f"{stage}={counts[stage]}" for stage in sorted(STAGES))
    print(f"OK: tutorial curriculum ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
