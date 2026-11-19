"""Sharing a mod (1.0 checklist section 6 ⭐): Create patch, then Tellius Patcher on a retail disc image.

The edited tree (G1's edit: Ike's Str bonus +2, no chapter jump) is turned into a ``.tpatch`` with
``patch.create_patch`` and applied to the retail US disc image with ``patch.apply_patch_to_disc``, the code
Tellius Patcher runs. Dolphin boots the image it built; the driver starts a New Game (Difficult) and plays
to the Prologue's first player phase, where Ike's person record in RAM must carry the edit. Retail: G1's
retail run (the same record from a chapter jump into the Prologue).
"""
from __future__ import annotations

import json
from pathlib import Path

from .checks_gamedata import por_edit
from .core import BASES, ROOT, Check, Title
from .oracles import map_start, record_edit

RETAIL_IMAGE = Path("G:/ROM/Fire Emblem - Path of Radiance (USA).ciso")


def package(run: Path, variant: str) -> None:
    from fe_modding import patch
    from fe_modding.games import Game
    from tools.session_playtest.harness import assemble_run_tree
    disc = run / "disc_tree"         # the edited disc alone (the run folder also holds patch/, card/...)
    assemble_run_tree(BASES["GFEE01"], run / "patch", disc)
    tpatch = run / "mod.tpatch"
    patch.create_patch(BASES["GFEE01"], disc, tpatch, game=Game.PATH_OF_RADIANCE, name="In-game check X1")
    patch.apply_patch_to_disc(tpatch, RETAIL_IMAGE, run / "image.iso")


def judge(mod, retail, facts):
    path = ROOT / "out" / "G1_retail" / "observations.json"
    if not path.is_file():
        return False, "run G1 first (its retail run is the reference)"
    retail = json.loads(path.read_text(encoding="utf-8"))
    passed, text = record_edit("PID_IKE", "person")(mod, retail, facts)
    return passed, f"image built by the patcher from the .tpatch: {text}"


CHECKS = [Check("X1", "por", "Create patch + Tellius Patcher: the patched image carries the edit",
                ["1.0 §6 Create patch ⭐", "1.0 §6 TelliusPatcher ⭐"], play=map_start(["PID_IKE"], minutes=12), judge=judge,
                fixture=por_edit("character", "PID_IKE", "stat_bonus1", 2), start=Title(), package=package,
                retail=False, minutes=12)]


# -- NP1 / NP1r: New project from the retail image, Check, Build disc, play the built image -----------------------
#
# As the app does it: ModProject.create (overlay layout, the New project dialog), set_source + extract, the
# Check report (validator.validate_project), then Build disc (ModProject.build). Dolphin boots the image the
# build wrote; the driver starts a New Game and plays to the first player phase.

IMAGES = {"GFEE01": RETAIL_IMAGE, "RFEE01": Path("G:/ROM/Fire Emblem - Radiant Dawn (USA) (Rev 1).wbfs")}


def new_project_package(region: str):
    def package(run: Path, variant: str) -> None:
        import shutil
        from fe_modding.games import Game
        from fe_modding.project import LAYOUT_OVERLAY, ModProject
        from fe_modding.validator import validate_project
        folder = run / "new_project"
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        game = Game.RADIANT_DAWN if region.startswith("R") else Game.PATH_OF_RADIANCE
        project = ModProject.create(folder, "Check project", game, layout=LAYOUT_OVERLAY)
        project.set_source(IMAGES[region])
        project.extract()
        report = validate_project(project)
        built = project.build()
        shutil.move(str(built), str(run / "image.iso"))
        (run / "check_report.json").write_text(json.dumps({
            "errors": [str(i) for i in report.errors], "warnings": [str(i) for i in report.warnings]},
            indent=2) + "\n", encoding="utf-8")
        shutil.rmtree(folder, ignore_errors=True)
    return package


def judge_new_project(mod, retail, facts, run_id: str):
    report = json.loads((ROOT / "run" / f"{run_id}_mod" / "check_report.json").read_text(encoding="utf-8"))
    on_map = bool(mod.get("units"))
    ok = not report["errors"] and on_map
    return ok, (f"new project from the retail image: Check {len(report['errors'])} error(s), "
                f"{len(report['warnings'])} warning(s); the built image boots, New Game reaches the first map "
                f"({len(mod.get('units', []))} units)")


CHECKS += [
    Check("NP1", "por", "New project, Check, Build disc: the built image plays", ["1.0 §1 New project / Check / Build ⭐ (POR)"],
          play=map_start(minutes=12), judge=lambda m, r, f: judge_new_project(m, r, f, "NP1"), start=Title(),
          package=new_project_package("GFEE01"), retail=False, minutes=15),
    Check("NP1r", "rd", "New project, Check, Build disc: the built image plays", ["1.0 §1 New project / Check / Build ⭐ (RD)"],
          play=map_start(minutes=15), judge=lambda m, r, f: judge_new_project(m, r, f, "NP1r"), start=Title(),
          package=new_project_package("RFEE01"), retail=False, minutes=18),
]


# -- RV1r: Export for Riivolution, booted by Dolphin through a game-modification descriptor ------------------------
#
# The export needs a project in the shared-vanilla layout, so a fresh one is made from the retail image (as NP1r
# does) and given G1r's edit (Micaiah's Str bonus +2) through FE10Data. ``riivolution.export_project`` writes
# the SD-card folder and XML; ``boot.json`` (Dolphin's "dolphin-game-mod-descriptor") names the retail image and
# the XML with its option enabled, which is what "Start with Riivolution Patches" does from the game list.

def riivolution_package(run: Path, variant: str) -> None:
    import shutil
    from fe_modding import riivolution
    from fe_modding.formats import fe10data
    from fe_modding.games import Game
    from fe_modding.project import LAYOUT_OVERLAY, ModProject
    folder = run / "riivolution_project"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    project = ModProject.create(folder, "Riivolution check", Game.RADIANT_DAWN, layout=LAYOUT_OVERLAY)
    project.set_source(IMAGES["RFEE01"])
    project.extract()
    data = project.read_logical("game_data")
    micaiah = next(r for r in fe10data.read_table(data, "character") if r.id == "PID_MICAIAH")
    old = micaiah.values["bonus_str"]
    project.write_logical("game_data", fe10data.patch_field(data, "character", micaiah.index, "bonus_str", old + 2))
    result = riivolution.export_project(project, run / "riivolution_export")
    descriptor = {
        "type": "dolphin-game-mod-descriptor", "version": 1, "base-file": str(IMAGES["RFEE01"]),
        "display-name": "Tellius Modding check",
        # root: the SD card's top folder (the XML's patch root, /<mod id>, is under it)
        "riivolution": {"patches": [{"xml": str(result.xml), "root": str(result.folder),
                                     "options": [{"section-name": "Tellius Modding", "option-name": project.name,
                                                  "choice": 1}]}]},
    }
    (run / "boot.json").write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
    (run / "riivolution_facts.json").write_text(json.dumps({"old": old, "new": old + 2, "files": result.files,
                                                            "warnings": result.warnings}) + "\n", encoding="utf-8")


#: RD PersonData's Str bonus in RAM (seen in G1r: +0x23 went 2 -> 4 with the same edit)
RD_STR_BONUS = 0x23


def judge_riivolution(mod, retail, facts):
    """The game ran from the retail image with the patch, so the record's pointers differ from a jump boot's;
    the judge reads the edited byte itself (and G1r's retail run for its retail value)."""
    path = ROOT / "out" / "G1r_retail" / "observations.json"
    edit = json.loads((ROOT / "run" / "RV1r_mod" / "riivolution_facts.json").read_text(encoding="utf-8"))
    value = bytes.fromhex(mod["records"]["PID_MICAIAH"]["person"])[RD_STR_BONUS]
    base = (bytes.fromhex(json.loads(path.read_text(encoding="utf-8"))["records"]["PID_MICAIAH"]["person"])[RD_STR_BONUS]
            if path.is_file() else None)
    ok = value == edit["new"] and base in (None, edit["old"])
    return ok, (f"booted with the Riivolution export (retail disc + patch): Micaiah's Str bonus in RAM is {value} "
                f"(edited {edit['old']} -> {edit['new']}; a retail boot reads {base})")


CHECKS.append(Check("RV1r", "rd", "Export for Riivolution: the patched game carries the edit",
                    ["1.0 §6 Export for Riivolution (RD)"], play=map_start(["PID_MICAIAH"], minutes=15),
                    judge=judge_riivolution, start=Title(), package=riivolution_package, retail=False, minutes=18))
