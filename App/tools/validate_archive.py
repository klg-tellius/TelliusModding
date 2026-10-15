"""Backward-compatible entry point for validating the Tellius Archive wiki."""

from __future__ import annotations

from validate_wiki import main


if __name__ == "__main__":
    raise SystemExit(main())
