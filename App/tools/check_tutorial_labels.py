"""List, for each GUI module, the visible control labels its modding tutorials never name.

    python App/tools/check_tutorial_labels.py [MODULE ...]

Labels are the ``text=``/``label=``/``title=`` literals of up to seven words in
``App/fe_modding/gui``; ``OWN`` maps each module to the lessons that teach it. The
output is a review aid, not a gate: it still lists noise such as "Cancel" and
empty-state messages. See research/WIKI_TUTORIAL_REVIEW_PLAN.md.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUI = ROOT / "App" / "fe_modding" / "gui"
WIKI = ROOT / "wiki" / "modding"

#: module (relative to gui/, no .py) -> the lessons that own it (numbers, or a page name)
OWN = {
    "new_project_dialog": [1], "tool_setup": [1, 4, 80], "shell": [2, 80], "app": [2, 80], "changelog": [2, 3],
    "pages/home": [2], "pages/disc": [1, 4, 61], "settings_dialog": [4, 51, 80], "pages/check": [5],
    "pages/chapters": [6, 7, 8, 65, 21, 27, 28], "campaign_dialog": [7, 8], "chapter_settings": [27],
    "pages/characters": [10, 11, 12, 13, 67], "character_form": [10], "record_actions": [10, 15],
    "portrait_viewer": [11], "support_editor": [13], "stats_editor": [10, 16, 17, 18, 19, 20],
    "pages/data": [16, 20], "icon_picker": [17, 18], "map_builder": [21, 22, 23, 24, 25, 66],
    "map_windows": [23, 24, 27], "prop_browser": [24], "map_editor": [21, 24], "map_scene": [21],
    "deployment_editor": [29, 30, 31], "dispo_window": [29, 30, 31, 32], "dispo_widgets": [31],
    "script_editor": [33, 35, 36], "code_editor": [33, 43], "pages/flags": [34, 59],
    "dialogue_editor": [37], "scene_editor": [37], "conversation_preview": [37], "layout_examples": [37],
    "background_viewer": [38], "rect_images": [38, 72], "rect_detail": [38, 72], "message_reference": [37, 40],
    "pages/text_assets": [37, 40, 79], "font_viewer": [39, 42], "cp_data_editor": [43, 44, 45],
    "shop_editor": [46], "music_editor": [47], "sfx_viewer": [48], "sfx_import_dialog": [48],
    "video_viewer": [49], "graphics_viewers": [50], "icon_viewer": [50], "soundroom_editor": [73],
    "soundroom_tracks_editor": [47, 73], "staffroll_editor": [73], "tutorials_editor": [73],
    "model_viewer": [12, 25, 26, 51, 52, 53, 54], "battle_weapons_viewer": [17, 55],
    "battle_scenery_viewer": [28, 55], "battle_camera_viewer": [70], "battle_params_viewer": [55],
    "battle_table_viewer": [55], "dbx_files_viewer": [71], "dbx_form": [71], "battle_scene_editor": [55],
    "effects_viewer": [69], "effect_add_dialog": [69], "particle_editor": [69],
    "battle_simulator": [56], "battle_window": [56], "battle_stage": [56], "pages/code": [57, 60],
    "playthrough_window": [58, 45], "playthrough_battle": [58], "pages/saves": [59],
    "mod_details_dialog": [61], "patch_dialog": [61], "hub_dialog": ["hub-chapters"],
    "hub_tool": ["hub-chapters"], "pages/tools": [56, 5, 59, 57], "extended_recovery": [34],
}

LABEL_RE = re.compile(r'''\b(?:text|label|title)\s*=\s*(["'])((?:(?!\1).){2,80})\1''')


def norm(text: str) -> str:
    return text.replace("…", "").replace("...", "").replace("&", "").strip().strip(":").strip().lower()


def article(lesson) -> str:
    if isinstance(lesson, str):
        return (WIKI / f"{lesson}.md").read_text(encoding="utf-8")
    pages = sorted(WIKI.glob(f"{lesson:02d}-*.md"))
    return pages[0].read_text(encoding="utf-8") if pages else ""


def labels_of(path: Path) -> list[str]:
    found = []
    for match in LABEL_RE.finditer(path.read_text(encoding="utf-8")):
        text = match.group(2)
        if "{" in text or not re.search(r"[A-Za-z]{3}", text) or text.endswith(".TLabel") or len(text.split()) > 7:
            continue
        if text not in found:
            found.append(text)
    return found


def missing_labels() -> dict[str, tuple[list, list[str]]]:
    """module -> (owning lessons, labels none of them names)."""
    report = {}
    for module, owners in OWN.items():
        path = GUI / f"{module}.py"
        if not path.exists():
            continue
        owned = "\n".join(article(o) for o in owners).lower()
        report[module] = (owners, [label for label in labels_of(path) if norm(label) and norm(label) not in owned])
    return report


def main(argv=None) -> int:
    wanted = (argv if argv is not None else sys.argv[1:])
    report = missing_labels()
    for module, (owners, missing) in sorted(report.items(), key=lambda kv: -len(kv[1][1])):
        if (wanted and module not in wanted) or not missing:
            continue
        lessons = ", ".join(map(str, owners)) or "none"
        print(f"{module} (lessons {lessons}, {len(missing)}): " + " ; ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
