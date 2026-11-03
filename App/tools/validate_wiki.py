"""Validate Tellius Archive sources before MkDocs publishes them."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from review_systems import review_repository, update_or_check_report
from review_tutorials import review_tutorials


ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"
REQUIRED = {
    "id", "title", "description", "games", "section", "article_type", "tags",
    "aliases", "status", "last_reviewed", "sources", "cms_collection", "source_path",
}
STATUSES = {"published", "draft", "stub", "research-needed"}
GAMES = {"path-of-radiance", "radiant-dawn"}
CONFIDENCE = {"confirmed", "strong", "plausible", "open"}


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


def markdown_targets(body: str):
    for target in re.findall(r"(?<!!)\[[^]]*\]\(([^)]+)\)", body):
        target = target.split("#", 1)[0].split("?", 1)[0]
        if target and not re.match(r"(?:https?:|mailto:|#|/)", target):
            yield target


def main() -> int:
    errors: list[str] = []
    pages: dict[str, Path] = {}
    migrated = 0

    for path in sorted(WIKI.rglob("*.md")):
        relative = path.relative_to(WIKI).as_posix()
        try:
            meta, body = read_page(path)
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: {exc}")
            continue
        missing = REQUIRED - meta.keys()
        if missing:
            errors.append(f"{relative}: missing metadata {sorted(missing)}")
            continue
        article_id = str(meta["id"])
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", article_id):
            errors.append(f"{relative}: invalid stable id {article_id!r}")
        if article_id in pages:
            errors.append(f"{relative}: duplicate id {article_id!r} also used by {pages[article_id]}")
        pages[article_id] = path
        if meta["status"] not in STATUSES:
            errors.append(f"{relative}: invalid status {meta['status']!r}")
        if not isinstance(meta["games"], list) or not set(meta["games"]).issubset(GAMES):
            errors.append(f"{relative}: invalid games {meta['games']!r}")
        if not isinstance(meta["sources"], list) or not meta["sources"]:
            errors.append(f"{relative}: at least one source key is required")
        if meta["source_path"] != relative:
            errors.append(f"{relative}: source_path is {meta['source_path']!r}")
        expected_collection = relative.split("/", 1)[0] if "/" in relative else "pages"
        if expected_collection in {"formats", "systems", "guides", "meta", "pages"} and meta["cms_collection"] != expected_collection:
            errors.append(f"{relative}: cms_collection should be {expected_collection!r}")
        if not re.search(r"^#\s+\S", body, re.M):
            errors.append(f"{relative}: missing article H1")
        if meta["status"] == "published" and meta["article_type"] in {"format-reference", "system-reference"}:
            migrated += 1
            if len(re.findall(r"^##\s+", body, re.M)) < 1:
                errors.append(f"{relative}: published reference needs teaching sections")
            opening = re.sub(r"[*_`]", "", body.split("\n\n", 2)[-1]).split(".", 1)[0]
            if re.search(r"\b(?:offset|0x[0-9a-f]+|\d+\s*bytes?)\b", opening, re.I):
                errors.append(f"{relative}: opens with implementation detail")
        for confidence in re.findall(r'class="confidence confidence--([^"]+)"', body):
            if confidence not in CONFIDENCE:
                errors.append(f"{relative}: unknown confidence label {confidence!r}")
        for target in markdown_targets(body):
            destination = (path.parent / target).resolve()
            try:
                destination.relative_to(WIKI.resolve())
            except ValueError:
                errors.append(f"{relative}: link escapes wiki root: {target}")
                continue
            if not destination.exists():
                errors.append(f"{relative}: broken local link: {target}")

    route_script = WIKI / "assets" / "javascripts" / "legacy-routes.js"
    route_text = route_script.read_text(encoding="utf-8") if route_script.exists() else ""
    route_match = re.search(r"=\s*(\{.*\});", route_text, re.S)
    if not route_match:
        errors.append("legacy route map is missing or invalid")
    else:
        routes = json.loads(route_match.group(1))
        if len(routes) != 79:
            errors.append(f"legacy route map has {len(routes)} entries, expected 79")
        missing_routes = set(routes) - set(pages)
        if missing_routes:
            errors.append(f"legacy routes without pages: {sorted(missing_routes)}")
        legacy_shell = (ROOT / "docs" / "tellius_archive.html").read_text(encoding="utf-8")
        shell_match = re.search(r"const routes = (\{.*?\});", legacy_shell, re.S)
        if not shell_match or set(json.loads(shell_match.group(1))) != set(routes):
            errors.append("docs/tellius_archive.html does not cover every legacy article id")
    if migrated != 98:
        errors.append(f"found {migrated} migrated format/system references, expected 98")

    cms = (WIKI / "admin" / "config.yml").read_text(encoding="utf-8")
    for required in ("open_authoring: true", "publish_mode: editorial_workflow", "auth_endpoint: /auth"):
        if required not in cms:
            errors.append(f"CMS configuration is missing {required!r}")
    if re.search(r"(?:client_secret|oauth_secret|access_token)\s*:", cms, re.I):
        errors.append("CMS configuration appears to contain a secret")

    system_errors, system_state = review_repository()
    errors.extend(system_errors)
    if system_state:
        report_error = update_or_check_report(system_state, write=False)
        if report_error:
            errors.append(report_error)

    tutorial_errors, _tutorial_state = review_tutorials()
    errors.extend(tutorial_errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {len(pages)} wiki pages; 79 legacy routes; {migrated} migrated references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
