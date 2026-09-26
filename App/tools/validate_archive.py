"""Static checks for the self-contained Tellius Archive HTML artifact."""

from __future__ import annotations

import re
import sys
import json
from pathlib import Path


ARCHIVE = Path(__file__).resolve().parents[1] / "docs" / "tellius_archive.html"
MANIFEST = ARCHIVE.with_name("review_manifest.json")


def main() -> int:
    text = ARCHIVE.read_text(encoding="utf-8")
    errors: list[str] = []

    titles_match = re.search(r"const TITLES = \{(.*?)\n\};", text, re.S)
    articles_match = re.search(r"const ARTICLES = \{(.*?)\n\n\};\n\n/\* meta counts", text, re.S)
    if not titles_match or not articles_match:
        print("ERROR: could not locate TITLES or ARTICLES")
        return 1

    titles = set(re.findall(r'(?:^|[,\n])\s*(?:"([^"]+)"|([A-Za-z0-9_-]+))\s*:', titles_match.group(1)))
    title_ids = {quoted or bare for quoted, bare in titles}
    article_ids = {
        quoted or bare
        for quoted, bare in re.findall(
            r'^(?:"([^"]+)"|([A-Za-z0-9_-]+))\s*:\s*\{',
            articles_match.group(1),
            re.M,
        )
    }
    links = set(re.findall(r'wl\("([^"]+)"', articles_match.group(1)))
    article_source = articles_match.group(1)
    entry_matches = list(re.finditer(
        r'^(?:"([^"]+)"|([A-Za-z0-9_-]+))\s*:\s*\{', article_source, re.M
    ))
    article_bodies: dict[str, str] = {}
    for index, entry in enumerate(entry_matches):
        article_id = entry.group(1) or entry.group(2)
        end = entry_matches[index + 1].start() if index + 1 < len(entry_matches) else len(article_source)
        entry_source = article_source[entry.start():end]
        body_match = re.search(r'\bbody\s*:\s*`(.*?)`\s*\r?\n\s*\},?', entry_source, re.S)
        article_bodies[article_id] = body_match.group(1) if body_match else ""

    missing_titles = article_ids - title_ids
    missing_articles = title_ids - article_ids
    broken_links = links - article_ids
    if missing_titles:
        errors.append(f"articles absent from TITLES: {sorted(missing_titles)}")
    if missing_articles:
        errors.append(f"TITLES entries absent from ARTICLES: {sorted(missing_articles)}")
    if broken_links:
        errors.append(f"broken wl() links: {sorted(broken_links)}")
    if "undefined" in articles_match.group(1) or "NaN" in articles_match.group(1):
        errors.append("literal undefined or NaN in article data")

    banned = {
        "process-history wording": r"\b(?:we|our)\s+(?:found|tried|tested|built|decoded|investigated)|"
        r"\b(?:mistake|wrong turn|bug caught|while porting|this project's tooling|"
        r"found by tracing|opened for the first time|previously mis-guessed|"
        r"originally examined|from-scratch scan|dead end worth recording)\b",
    }
    for label, pattern in banned.items():
        matches = list(re.finditer(pattern, articles_match.group(1), re.I))
        if matches:
            lines = [text.count("\n", 0, articles_match.start(1) + m.start()) + 1 for m in matches]
            errors.append(f"{label} at lines {lines}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    reviewed_ids = {
        article_id for article_id, review in manifest["articles"].items()
        if review.get("status") == "reviewed"
    }
    if reviewed_ids != article_ids:
        errors.append(
            f"review coverage mismatch: missing={sorted(article_ids - reviewed_ids)}, "
            f"extra={sorted(reviewed_ids - article_ids)}"
        )
    minimum = manifest["minimum_score"]
    for article_id, review in manifest["articles"].items():
        if article_id not in article_ids:
            errors.append(f"review manifest references missing article: {article_id}")
            continue
        if review.get("status") != "reviewed":
            continue
        if review.get("score", 0) < minimum:
            errors.append(f"reviewed article below rubric threshold: {article_id}")
        body = article_bodies.get(article_id, "")
        opening = re.search(r"<p>(.*?)</p>", body, re.S)
        opening_text = re.sub(r"<[^>]+>", " ", opening.group(1) if opening else "")
        first_sentence = opening_text.split(".", 1)[0]
        if re.search(r"\b(?:offset|0x[0-9a-f]+|\d+\s*bytes?)\b", first_sentence, re.I) or re.match(
            r"\s*(?:a|an|each|every|this)\s+.*\brecord\b", first_sentence, re.I
        ):
            errors.append(f"reviewed article opens with implementation detail: {article_id}")
        if not re.search(r"<h2\b", body, re.I):
            errors.append(f"reviewed article has no teaching sections: {article_id}")
        if not re.search(r"<h2\b[^>]*>[^<]*(?:Example|How|What|Mental|life|layers)", body, re.I):
            errors.append(f"reviewed article lacks a mental-model/example heading: {article_id}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    namespaces = {
        ns: len(re.findall(rf'ns:"{ns}"', articles_match.group(1)))
        for ns in ("format", "system", "meta")
    }
    reviewed_count = sum(
        1 for review in manifest.get("articles", {}).values()
        if review.get("status") == "reviewed"
    )
    print(
        f"OK: {len(article_ids)} articles; {namespaces}; "
        f"{len(links)} linked targets; {reviewed_count} pedagogically reviewed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
