"""Item and skill icons, and the weapon models items load.

**Icons** live in ``window/icon.tpl`` (two C8 images; ``system.cmp`` bundles
the copy the game reads, and the build copies the loose file into it):

- image 0 (768 x 216) is a grid of 24 x 24 cells, 32 per row. Item-list rows
  draw glyph ``icon + 0x61`` (``FE8Data.bin`` item ``+0x49``), which is cell
  ``icon + 96``: the first item icon is the fourth row's first cell (Iron
  Sword), the last vanilla one (186, the coin) cell 282. Confirmed against
  every vanilla item.
- image 1 (1024 x 96) is a grid of 32 x 32 cells, 32 per row. Skill-list rows
  (``skill_list_draw_row_a``/``_b``) draw the skill record's byte ``0x19``;
  icon ``n`` is cell ``n - 1`` (46 skill icons, then blank frames), and 0
  means none - those skills are also left out of the learnable-skill lists.
  Confirmed against the vanilla skills (Chant's note, Steal's pouch,
  Counter's crossed arrows, Wing Shield's wing).

Assets › Icons (``gui/icon_viewer.py``) replaces them one by one.

**Weapon models**: the battle (``setup_battle_scene`` ->
``gactor_create_weapon_instance``) takes the equipped item's ID without
``IID_`` and opens ``xwp/<NAME>.dbx`` in ``zdbx.cmp``; without that table
no weapon actor is made (the debug log says "no weapon, so bare hands"). Its ``class Model`` block names the model:
``folder xwp/IRONSWORD``, ``model IRONSWORD``, loaded as
``<folder>/<model>.cmp`` (disc paths are case-insensitive:
``xwp/ironsword/ironsword.cmp``). Every vanilla table names its own
weapon; a tome's table has only a ``class Weapon`` block (no model). The
forge preview (``update_forge_result_actor``) builds
``xwp/forge/<name>_b.cmp`` straight from the name.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from . import tpl

ICON_TPL = Path("window") / "icon.tpl"

ITEM_IMAGE, ITEM_CELL, ITEM_FIRST_CELL = 0, 24, 96
SKILL_IMAGE, SKILL_CELL = 1, 32
COLUMNS = 32


def icon_path(files_dir: Path) -> Path:
    return Path(files_dir) / ICON_TPL


def item_cell(icon: int) -> int:
    return ITEM_FIRST_CELL + icon


def skill_cell(icon_id: int) -> Optional[int]:
    return icon_id - 1 if icon_id > 0 else None


def cell_count(images: list, image_index: int, size: int) -> int:
    image = images[image_index]
    return (image.width // size) * (image.height // size)


def _box(cell: int, size: int) -> tuple[int, int, int, int]:
    row, column = divmod(cell, COLUMNS)
    return (column * size, row * size, (column + 1) * size, (row + 1) * size)


def read_icon_images(tpl_bytes: bytes) -> list:
    return tpl.read_tpl_images(io.BytesIO(tpl_bytes))


def cell_image(images: list, image_index: int, cell: Optional[int], size: int) -> Optional[Image.Image]:
    """One icon, or None when ``cell`` is outside the sheet."""
    if cell is None or cell < 0 or image_index >= len(images):
        return None
    if cell >= cell_count(images, image_index, size):
        return None
    return images[image_index].crop(_box(cell, size)).convert("RGBA")


def item_icon(images: list, icon: int) -> Optional[Image.Image]:
    return cell_image(images, ITEM_IMAGE, item_cell(icon), ITEM_CELL)


def skill_icon(images: list, icon_id: int) -> Optional[Image.Image]:
    return cell_image(images, SKILL_IMAGE, skill_cell(icon_id), SKILL_CELL)


def weapon_model_name(iid: Optional[str]) -> Optional[str]:
    """The name the battle looks weapons up by: the item ID without ``IID_``."""
    if not iid or not iid.startswith("IID_") or len(iid) <= 4:
        return None
    return iid[4:]


def weapon_tables(zdbx_entries) -> dict[str, str]:
    """``xwp/<NAME>.dbx`` texts of ``zdbx.cmp`` (:func:`zdbx.read_zdbx_archive`), by upper-case name."""
    tables = {}
    for entry in zdbx_entries:
        folder, _sep, file = entry.name.partition("/")
        if folder.lower() == "xwp" and file.lower().endswith(".dbx"):
            tables[file[:-4].upper()] = entry.text
    return tables


def dbx_blocks(text: str) -> list[dict[str, str]]:
    """The ``{ ... }`` blocks of a ``.dbx`` table as key -> value (``#`` comments dropped)."""
    blocks = []
    for body in re.findall(r"\{(.*?)\}", text, re.S):
        block = {}
        for line in body.splitlines():
            parts = line.split("#", 1)[0].split(None, 1)
            if len(parts) == 2:
                block[parts[0]] = parts[1].strip()
        blocks.append(block)
    return blocks


@dataclass
class WeaponModel:
    name: str  # item ID without IID_
    has_table: bool  # zdbx.cmp has xwp/<NAME>.dbx (else no weapon is drawn in battle)
    folder: Optional[str] = None  # the table's Model block
    model: Optional[str] = None
    path: Optional[Path] = None  # <folder>/<model>.cmp on disc, when it exists

    @property
    def label(self) -> Optional[str]:
        """The model's folder as the 3D Models list shows it (``xwp/ironsword``)."""
        return f"xwp/{self.path.parent.name}" if self.path is not None else None


def _find_case_insensitive(folder: Path, name: str) -> Optional[Path]:
    """``folder``'s entry named ``name`` in any case, spelled as on disk (the
    3D Models list uses the disk names)."""
    if folder.is_dir():
        for child in folder.iterdir():
            if child.name == name:
                return child
        for child in folder.iterdir():
            if child.name.lower() == name.lower():
                return child
    return None


def _resolve(files_dir: Path, relative: str) -> Optional[Path]:
    path = Path(files_dir)
    for part in relative.replace("\\", "/").split("/"):
        if not part:
            continue
        path = _find_case_insensitive(path, part)
        if path is None:
            return None
    return path


def weapon_model(files_dir: Path, iid: Optional[str], tables: dict[str, str]) -> Optional[WeaponModel]:
    """The model an item shows in battle, following its ``xwp/<NAME>.dbx``
    table; None when ``iid`` is not an item ID."""
    name = weapon_model_name(iid)
    if name is None:
        return None
    text = tables.get(name.upper())
    if text is None:
        return WeaponModel(name, has_table=False)
    found = WeaponModel(name, has_table=True)
    block = next((b for b in dbx_blocks(text) if b.get("class") == "Model"), None)
    if block is not None and block.get("folder") and block.get("model"):
        found.folder, found.model = block["folder"], block["model"]
        for suffix in (".cmp", ".pak"):
            path = _resolve(files_dir, f"{found.folder}/{found.model}{suffix}")
            if path is not None and path.is_file():
                found.path = path
                break
    return found


def forged_model_path(files_dir: Path, iid: Optional[str]) -> Optional[Path]:
    """``xwp/forge/<name>_b.cmp``, the model of the item forged, or None."""
    name = weapon_model_name(iid)
    if name is None:
        return None
    path = _resolve(files_dir, f"xwp/forge/{name}_b.cmp")
    return path if path is not None and path.is_file() else None
