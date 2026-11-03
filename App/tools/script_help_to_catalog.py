"""Copy the event-script function descriptions into the app's catalog.

The descriptions are written in ``docs/app/script_reference_details.py``
(one entry per native and startup.cmb helper: what it does, its arguments,
its result). The app reads ``fe_modding/formats/cmb/externs_fe9.json``, so
this script copies a short form of them there: each argument's name and
help, the description (``note``) and the result (``returns``).

    python tools/script_help_to_catalog.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
DOCS = APP.parent / "docs" / "app"
CATALOG = APP / "fe_modding" / "formats" / "cmb" / "externs_fe9.json"


def first_sentence(text: str) -> str:
    text = " ".join((text or "").split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    return match.group(1) if match else text


def main() -> int:
    sys.path.insert(0, str(DOCS))
    import script_reference_details as reference  # noqa: E402 - from the docs folder

    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    changed = 0
    for name, entry in data["externs"].items():
        detail = reference.DETAILS.get(name)
        if detail is None:
            continue
        args = entry.get("args") or []
        for i, (arg_name, arg_help) in enumerate(detail.get("args", [])[:entry["argc"]]):
            while len(args) <= i:
                args.append({"name": "", "kind": "int"})
            args[i]["name"] = arg_name
            args[i]["help"] = first_sentence(arg_help)
        entry["args"] = args
        entry["note"] = first_sentence(detail.get("behavior", ""))
        returns = detail.get("returns") or ""
        entry["returns"] = "" if returns.startswith("Not specified") else first_sentence(returns)
        changed += 1
    with open(CATALOG, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print(f"{changed} of {len(data['externs'])} functions described")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
