"""Update existing experimental fixtures without changing their UUIDs or cards."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime

from prepare_extended_flag_playtest import (
    ModProject, FlagLayout, MANIFEST_NAME, hub, gcdisc,
    apply_test_quality_of_life, sync_boot_archive, verify_packaged_executable,
    inspect_project, RuntimeState,
    write_script, script_sources,
)
from fe_modding import chapter_images, chapters, hub_creation
from fe_modding.formats import lz10, map_file, pak, dispo
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.extended_flag_candidate import build_candidate
from fe_modding.game_code.extended_flag_installation import RECEIPT_NAME, _restore, receipt_for


def repair_hub_opening(project, setup, layout):
    paths = chapters.chapter_paths(project, f"{setup.chapter:02d}")
    source = script_sources.peek(project, paths.script)
    old_group = f"bmap{setup.chapter:02d}_mikata_c"
    new_group = old_group.replace("mikata", "avatar")
    old = ("@export\ndef Opening0():\n"
           f'    MapLoad("bmap{setup.chapter:02d}")\n'
           f'    InstantDisposFirst("{old_group}")\n')
    new = hub_creation.opening_source(setup.chapter, new_group, setup.avatar_pid)
    focused = new.replace(f'    InstantUnitFocusByPID("{setup.avatar_pid}")',
                         f'    HubPositionAvatar()\n    InstantUnitFocusByPID("{setup.avatar_pid}")')
    if new in source or focused in source:
        return
    if old not in source:
        raise ValueError("Unexpected hub opening; refusing to overwrite other script changes")
    packed = lz10.decompress(paths.deployment.read_bytes())
    changes = {}
    for entry in pak.read_pak_entries(packed):
        if entry.name == "dispos_c.bin":
            document = dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
            if document.section(old_group) is None:
                raise ValueError("Expected avatar deployment group missing")
            dispo.rename_section_prefix(document, old_group, new_group)
            changes[entry.name] = dispo.build_dispo(document)
    if not changes:
        raise ValueError("Common deployment file missing")
    write_script(project, paths.script, source.replace(old, new, 1), layout)
    project.write_keeping_original(paths.deployment, hub_creation._pack_entries(packed, changes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    records = json.loads((root / "builds.json").read_text(encoding="utf-8"))
    revision = max(record.get("fixture_revision", 1) for record in records) + 1
    evidence = root / "evidence" / datetime.now().strftime(f"before-r{revision}-%Y%m%d-%H%M%S")
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copy2(root / "builds.json", evidence / "builds.json")
    previous_verification = root / "verification.json"
    if previous_verification.exists():
        shutil.copy2(previous_verification, evidence / "verification.json")
    for record in records:
        region = record["region"]
        if region not in ("GFEE01", "GFEP01", "GFEJ01"):
            raise ValueError("Unexpected test region")
        project = ModProject.load(root / region)
        layout = FlagLayout.from_json((project.directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        configuration = hub.saved_setup(project)
        setup = hub.setup_from(configuration) if configuration else None
        status = inspect_project(project)
        if status.state != RuntimeState.MATCHING:
            # A new generator revision cannot validate the previous experimental
            # section byte-for-byte. Restore its guarded retail inputs from the
            # old receipt, then atomically replace it with the current candidate.
            executable = project.extracted_dir / "sys/main.dol"
            receipt_path = project.directory / RECEIPT_NAME
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            original = _restore(Dol.open(executable), receipt)
            candidate = build_candidate(original, region, layout,
                                        hub_chapter=setup.chapter if setup else None)
            executable.write_bytes(candidate.executable)
            receipt_path.write_text(receipt_for(candidate, layout), encoding="utf-8")
            status = inspect_project(project)
            if status.state != RuntimeState.MATCHING:
                raise ValueError(f"{region}: refreshed runtime failed verification: {status}")
        saved = evidence / region
        saved.mkdir()
        shutil.copy2(project.directory / "test-build.json", saved / "test-build.json")
        shutil.copy2(project.extracted_dir / "sys/main.dol", saved / "main.dol")
        shutil.copy2(project.directory / RECEIPT_NAME, saved / RECEIPT_NAME)
        for path in (project.directory / "DolphinUser").rglob("*.gci"):
            target = saved / path.relative_to(project.directory)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if not setup:
            print(f"{region}: no hub; existing runtime-only image retained", flush=True)
            continue
        paths = chapters.chapter_paths(project, f"{setup.chapter:02d}")
        shutil.copy2(paths.script, saved / "hub-script-before.cmb")
        shutil.copy2(paths.deployment, saved / "hub-dispos-before.cmp")
        if setup and record.get("fixture_revision", 1) < 3:
            map_path = chapters.chapter_paths(project, f"{setup.chapter:02d}").map
            original = map_path.read_bytes()
            shutil.copy2(map_path, saved / "hub-map-before.cmp")
            packed = lz10.decompress(original)
            entry = next(e for e in pak.read_pak_entries(packed) if e.name == "map.bin")
            capacity = map_file.read_map_bytes(pak.read_pak_file_content(packed, entry)).capacity
            project.write_keeping_original(map_path, hub_creation.blank_map(
                original, capacity.x_size, capacity.y_size))
        repair_hub_opening(project, setup, layout)
        write_script(project, paths.script,
                     hub.hub_script(script_sources.peek(project, paths.script), setup), layout)
        project.write_keeping_original(paths.deployment, hub_creation.repair_avatar_deployment(
            paths.deployment.read_bytes(), setup.avatar_pid,
            hub_creation.avatar_class(project.read_logical("game_data"), setup.avatar_pid)))
        shutil.copy2(paths.map, saved / "hub-map-before-markers.cmp")
        project.write_keeping_original(paths.map, hub.entrance_markers(project, paths.map, setup))
        print(f"{region}: applying test conveniences and syncing boot archive", flush=True)
        apply_test_quality_of_life(project, setup, layout)
        # Redraw the hub's file-menu and title-card pictures: before revision 9 the Japanese ones were
        # drawn with bigkana.gcf, which has no ASCII, so they showed a row of dashes.
        title = chapters.chapter_display_title(f"{setup.chapter:02d}", chapters.chapter_titles(project))
        for path, data in chapter_images.chapter_name_images(project.files_dir, setup.chapter, title, 1).items():
            project.write_keeping_original(path, data)
        changed = sync_boot_archive(project)
        if inspect_project(project).state != RuntimeState.MATCHING:
            raise ValueError("Runtime integrity check failed after test edits")
        image = project.directory / f"{region}-extended-flags-EXPERIMENTAL.ciso"
        print(f"{region}: rebuilding image", flush=True)
        gcdisc.build_gamecube_ciso(project.extracted_dir, image)
        verify_packaged_executable(image, (project.extracted_dir / "sys/main.dol").read_bytes(), region)
        with image.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        record.update(sha256=digest, fixture_revision=revision, animation_speed=2.0,
                      return_position_before_fade=True,
                      avatar_ai_fix=True,
                      avatar_class_fix=True,
                      entrance_markers=[[d.x, d.y] for d in setup.destinations],
                      hub_opening_fix=True,
                      hub_ground_texture_fix=bool(setup),
                      automatic_victory_chapters=[d.chapter for d in setup.destinations] if setup else [],
                      boot_archive_synced=changed, in_game_verified=False)
        (project.directory / "test-build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        (root / "builds.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(f"{region}: revision {revision} ready; memory card unchanged", flush=True)
    print(f"Original test evidence copied to {evidence}")
    (root / "verification.json").write_text(json.dumps({
        "fixture_revision": revision, "in_game_tested": False,
        "images": [{"region": r["region"], "fixture_revision": r["fixture_revision"], "packaged_executable_matches": True,
                    "boot_archive_synced": r["boot_archive_synced"], "sha256": r["sha256"]}
                   for r in records],
        "full_dolphin_image_verification": f"Not repeated for revision {revision}",
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
