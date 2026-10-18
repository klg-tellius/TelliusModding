"""Read test memory cards and write a diagnostic report; never edits saves."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fe_modding.formats.extended_flags import FlagLayout, MANIFEST_NAME
from fe_modding.formats.save_file import SaveFile, block_label


def inspect(root):
    report = {}
    for region in ("GFEE01", "GFEP01", "GFEJ01"):
        folder = root / region
        manifest = folder / MANIFEST_NAME
        if not manifest.exists():
            continue
        layout = FlagLayout.from_json(manifest.read_text(encoding="utf-8"))
        records = []
        for path in (folder / "DolphinUser").rglob("*.gci"):
            record = {"file": str(path.relative_to(root)), "blocks": []}
            try:
                save = SaveFile.from_bytes(path.read_bytes())
                for block in save.blocks:
                    result = {"label": block_label(block), "crc_ok": block.crc_ok,
                              "decoded": block.decoded, "error": block.error}
                    state = block.extended_flags
                    if state is not None:
                        state.require_layout(layout)
                        result.update(layout_matches=True, hub_bytes=list(state.hub),
                                      campaign_probe_set=sum(state.get("campaign", i) for i in range(100)),
                                      local_first_80_set=sum(state.get("chapter", i) for i in range(80)))
                    else:
                        result["extended_record"] = False
                    record["blocks"].append(result)
            except (OSError, ValueError) as exc:
                record["error"] = str(exc)
            records.append(record)
        report[region] = records
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    report = inspect(args.root)
    destination = args.root / "save-diagnostics.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for region, saves in report.items():
        print(f"{region}: {len(saves)} GCI file(s)")
        for save in saves:
            print(" ", save["file"])
            if "error" in save:
                print("  ERROR:", save["error"])
            for block in save["blocks"]:
                print("  ", block)
    print(f"Report: {destination}")


if __name__ == "__main__":
    main()
