"""Crawl the generated Tellius Archive artifact for broken local URLs."""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
PROJECT_PREFIX = "/TelliusModding/"


class References(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.canonical = False
        self.article_record = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("class") and "article-record" in values["class"].split():
            self.article_record = True
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical = True
        for name in ("href", "src"):
            if values.get(name):
                self.references.append(values[name] or "")


def resolve(source: Path, reference: str) -> Path | None:
    parts = urlsplit(reference)
    if parts.scheme or parts.netloc or reference.startswith(("mailto:", "data:", "javascript:", "#")):
        return None
    location = unquote(parts.path)
    if not location:
        return None
    if location.startswith(PROJECT_PREFIX):
        destination = SITE / location.removeprefix(PROJECT_PREFIX)
    elif location.startswith("/"):
        return None  # Another origin-root path (for example a future custom domain asset).
    else:
        destination = source.parent / location
    if location.endswith("/"):
        destination /= "index.html"
    return destination.resolve()


def main() -> int:
    if not SITE.exists():
        print("ERROR: site/ does not exist; run mkdocs build first")
        return 1
    errors: list[str] = []
    article_pages = 0
    for page in sorted(SITE.rglob("*.html")):
        relative = page.relative_to(SITE).as_posix()
        parser = References()
        parser.feed(page.read_text(encoding="utf-8"))
        if relative not in {"404.html", "tellius_archive.html", "admin/index.html"}:
            article_pages += 1
            if not parser.canonical:
                errors.append(f"{relative}: missing canonical URL")
            if not parser.article_record:
                errors.append(f"{relative}: missing article contribution record")
        for reference in parser.references:
            destination = resolve(page, reference)
            if destination is None:
                continue
            try:
                destination.relative_to(SITE.resolve())
            except ValueError:
                errors.append(f"{relative}: URL escapes generated site: {reference}")
                continue
            if not destination.exists():
                errors.append(f"{relative}: broken generated URL: {reference}")
    if article_pages != 91:
        errors.append(f"generated {article_pages} article pages, expected 91")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: crawled {article_pages} article pages with canonical URLs and contribution records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
