"""Exercise particle editor round trips against an extracted FE9 files folder.

Usage: python App/tools/validate_particle_editor.py <extracted-files-folder>
The script reads effects into memory; it does not change the extracted files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fe_modding.formats import animation, effects, particle_editor  # noqa: E402


def validate(files: Path) -> tuple[int, int, list[str]]:
    total = 0
    particle_packs = 0
    failures = []
    for path in sorted((files / "yme").glob("EID_*.cmp")):
        total += 1
        try:
            parts = effects.read_effect_pack(path.read_bytes())
            ga = next((blob for name, blob in parts.items() if name.endswith(".ga")), None)
            if ga is None:
                continue
            layout = animation.read_particle_table_layout(ga)
            if layout is None:
                continue
            particle_packs += 1
            if not layout.emitters:
                changed = particle_editor.add_emitter(ga)
                assert len(animation.read_particle_table_layout(changed).emitters) == 1
                continue
            first = layout.emitters[0]
            assert particle_editor.edit_emitter(ga, 0, material=first.material_index) == ga
            if first.stage_count:
                stage = animation.read_particle_stage(ga, first, 0)
                assert particle_editor.edit_stage(ga, 0, 0, start=stage.start_frame) == ga
            duplicate = particle_editor.duplicate_emitter(ga, 0)
            copied = animation.read_particle_table_layout(duplicate)
            assert len(copied.emitters) == len(layout.emitters) + 1
            assert copied.emitters[-1].stages_offset != copied.emitters[0].stages_offset
            removed = particle_editor.remove_emitter(duplicate, len(copied.emitters) - 1)
            assert len(animation.read_particle_table_layout(removed).emitters) == len(layout.emitters)
            empty_added = particle_editor.add_emitter(ga)
            assert len(animation.read_particle_table_layout(empty_added).emitters) == len(layout.emitters) + 1
            empty_removed = particle_editor.remove_emitter(empty_added, len(layout.emitters))
            assert len(animation.read_particle_table_layout(empty_removed).emitters) == len(layout.emitters)
            if first.stage_count:
                doubled = particle_editor.duplicate_stage(ga, 0, 0)
                assert animation.read_particle_table_layout(doubled).emitters[0].stage_count == first.stage_count + 1
                restored = particle_editor.remove_stage(doubled, 0, 1)
                assert animation.read_particle_table_layout(restored).emitters[0].stage_count == first.stage_count
            anim = animation.read_animation_bytes(ga)
            events = list(anim.events)
            events.append(animation.EventKey(max((event.frame for event in events), default=0), (0,)))
            changed = particle_editor.replace_events(ga, events)
            assert animation.read_particle_table_layout(changed).emitters[0].name_path == first.name_path
        except Exception as exc:  # noqa: BLE001 - report all problematic source packs
            failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
    return total, particle_packs, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, help="Extracted files folder containing yme")
    args = parser.parse_args()
    total, particle_packs, failures = validate(args.files)
    print(f"Scanned {total} effect packs; checked {particle_packs} particle tables; failures: {len(failures)}")
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
