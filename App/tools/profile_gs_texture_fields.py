"""Compare FE9 .gs texture metadata with the referenced .tpl image headers.

Run with the extracted disc's ``files`` directory. This is a correlation
probe, not a decoder: a match does not establish what a .gs field means.
"""

from __future__ import annotations

import argparse
import collections
import io
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from fe_modding.formats import effects, gs_file, tpl  # noqa: E402


def profile(files_dir: Path) -> None:
    rows = collections.Counter()
    examples: dict[tuple[int, int, int, int], str] = {}
    packs = matched = skipped = 0
    for folder in ("yme", "zbg", "zmap", "zu"):
        for path in sorted((files_dir / folder).rglob("*.cmp")):
            try:
                members = effects.read_effect_pack(path.read_bytes())
            except (effects.EffectError, OSError):
                continue
            packs += 1
            tpl_members = {name: data for name, data in members.items() if name.lower().endswith(".tpl")}
            if len(tpl_members) != 1:
                continue  # Texture ID mapping across several TPLs is not confirmed.
            (tpl_name, tpl_bytes), = tpl_members.items()
            try:
                images = tpl.read_tpl_image_info(io.BytesIO(tpl_bytes))
            except (ValueError, IndexError, EOFError, OSError):
                continue
            for gs_name, data in members.items():
                if not gs_name.lower().endswith(".gs"):
                    continue
                try:
                    gs = gs_file.read_gs(data)
                except (gs_file.GsFileError, ValueError, IndexError):
                    continue
                for material in gs.materials:
                    for texture in material.textures:
                        if not 0 <= texture.tex_id < len(images):
                            skipped += 1
                            continue
                        image = images[texture.tex_id]
                        # params[0] is the raw u16 at texture record +6.
                        key = (texture.params[0], texture.flags[0], image.wrap_s, image.wrap_t)
                        rows[key] += 1
                        examples.setdefault(key, f"{path.relative_to(files_dir)}:{gs_name}:{material.name}"
                        )
                        matched += 1
    print(f"packs={packs} matched_textures={matched} unmatched_texture_ids={skipped}")
    print("gs+6  flags0  tpl_wrap_s/t  count  example")
    for (field, flags, wrap_s, wrap_t), count in rows.most_common():
        key = (field, flags, wrap_s, wrap_t)
        print(f"{field:04x}  {flags:04x}    {wrap_s}/{wrap_t}           {count:5d}  {examples[key]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files_dir", type=Path, help="Extracted GFEE01 files directory")
    profile(parser.parse_args().files_dir)
