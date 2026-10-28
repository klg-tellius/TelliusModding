"""Build opt-in, isolated experimental images. Never enables production approval.

Run with --source-root pointing at extracted GFEE01/GFEP01/GFEJ01 trees and
--output pointing at a NEW directory. Only that new output tree is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fe_modding import chapters, hub, hub_creation, script_sources
from fe_modding.extended_hub import prepare_fresh_project_update
from fe_modding.formats import event_flags as ef, fe8data, gcdisc, message, fe9_message_scene
from fe_modding.formats.cmb import compile_source, read_cmb, write_cmb
from fe_modding.formats.cmb.parser import parse
from fe_modding.formats.extended_flags import FlagLayout, FlagCompileContext, MANIFEST_NAME
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.extended_flag_candidate import build_candidate
from fe_modding.game_code.extended_flag_installation import RECEIPT_NAME, receipt_for, inspect_project, RuntimeState
from fe_modding.game_code.extended_flag_container import container_name
from fe_modding.games import Game
from fe_modding.project import ModProject
from tools.build_hub_infinite_action_test import patched_executable

CAMPAIGN = [f"XFT_CAMPAIGN_{i:03d}" for i in range(100)]
LOCALS = [f"XFT_LOCAL_{i:03d}" for i in range(80)]
AVATAR = "PID_XFT_AVATAR"


VICTORY_MARKER = "# XFT automatic test victory"
_VICTORY_BLOCK = re.compile(r"\n?# XFT automatic test victory\n@on_phase\([^\n]*\)\ndef XftFinishAfterPlayerTurnOne\(\):\n"
                            r"(?:    [^\n]*\n?)+")


def part_goals(source, chapter):
    """[(section flag, goal flag)] of a multipart chapter, last part first; [] for one part.

    Part k (k >= 2) starts in ``Opening<chapter>_<k>``, whose first top-level ``set`` marks it
    (C18: セクション２..４). Part k ends when the flag of the ``@on_complete`` handler that calls
    ``Complete<chapter>(k)`` is set; the last part ends on ``gf_complete``, whose handler is the
    whole chapter's ending (it assumes the earlier parts were played)."""
    goals = {}
    for flag, body in re.findall(r'@on_complete\(flag="([^"]+)"\)\ndef \w+\(\):\n((?:(?:    [^\n]*)?\n)+)', source):
        if flag != "gf_complete":
            for part in re.findall(rf"\bComplete{chapter}\((\d+)\)", body):
                goals[int(part)] = flag
    if not goals:
        return []
    sections = {}
    for part, body in re.findall(rf"def Opening{chapter}_(\d+)\(\):\n((?:(?:    [^\n]*)?\n)+)", source):
        first = re.search(r'^    set\("([^"]+)"\)', body, re.M)
        if first:
            sections[int(part)] = first.group(1)
    last = max(goals) + 1
    if any(part not in sections for part in range(2, last + 1)):
        raise ValueError(f"C{chapter:02d}: a part opening has no section flag; cannot route the test victory")
    return [(sections.get(part), goals.get(part, "gf_complete")) for part in range(last, 0, -1)]


def victory_source(source, chapter):
    """The automatic turn-one victory: ``gf_complete``, or the current part's goal flag."""
    body = ""
    goals = part_goals(source, chapter)
    if not goals:
        body = '    set("gf_complete")\n'
    for i, (section, goal) in enumerate(goals):
        if section is None:
            body += f'    else:\n        set("{goal}")\n'
        else:
            body += f'    {"if" if i == 0 else "elif"} get("{section}"):\n        set("{goal}")\n'
    return ('\n' + VICTORY_MARKER + '\n@on_phase(turn_from=1, turn_to=1, phase="enemy")\n'
            'def XftFinishAfterPlayerTurnOne():\n' + body)


def apply_test_quality_of_life(project, setup, layout):
    """Keep probe coordinates; shorten only the connected test battles."""
    if setup is not None:
        for destination in setup.destinations:
            path = script_sources.chapter_script(project, f"{destination.chapter:02d}")
            source = script_sources.peek(project, path)
            # Earlier builds always set gf_complete, which in a multipart chapter runs the final
            # ending from part 1: replace that handler rather than keeping it.
            base = _VICTORY_BLOCK.sub("", source)
            updated = base + victory_source(base, destination.chapter)
            if updated != source:
                write_script(project, path, updated, layout)
    from fe_modding.game_code.editor import CodeEditor
    from fe_modding.game_code.catalog import CATALOG
    CodeEditor(project.extracted_dir).set_value(CATALOG.entries["anim.speed"], 2.0)


def sync_boot_archive(project):
    """Boot archive entries override loose files, so verify both copies agree."""
    from fe_modding.formats import lz10, pak
    changed = project.sync_system_archive()
    packed = lz10.decompress(project.logical_path("system_archive").read_bytes())
    for entry in pak.read_pak_entries(packed):
        path = project.files_dir / entry.name
        if path.is_file() and path.read_bytes() != pak.read_pak_file_content(packed, entry):
            raise ValueError(f"Boot archive still contains a stale copy: {entry.name}")
    return changed


def verify_packaged_executable(image, expected, region):
    """Read the boot header and DOL back through the CISO block map."""
    with image.open("rb") as stream:
        header = stream.read(0x8000)
        if len(header) != 0x8000 or header[:4] != b"CISO":
            raise ValueError("Invalid CISO header")
        block_size = struct.unpack_from("<I", header, 4)[0]
        if not 0 < block_size <= 0x1000000 or any(value not in (0, 1) for value in header[8:]):
            raise ValueError("Invalid CISO block map")
        offsets, packed = [], 0
        for present in header[8:]:
            offsets.append(0x8000 + packed * block_size if present else None)
            packed += present

        def read(offset, size):
            result = bytearray()
            while size:
                block, within = divmod(offset, block_size)
                take = min(size, block_size - within)
                if block >= len(offsets):
                    raise ValueError("CISO read beyond block map")
                if offsets[block] is None:
                    result += bytes(take)
                else:
                    stream.seek(offsets[block] + within)
                    data = stream.read(take)
                    if len(data) != take:
                        raise ValueError("Truncated CISO data")
                    result += data
                offset += take
                size -= take
            return bytes(result)

        boot = read(0, 0x440)
        if boot[:6] != region.encode("ascii"):
            raise ValueError("Packaged disc region differs")
        dol_at = struct.unpack_from(">I", boot, 0x420)[0]
        if read(dol_at, len(expected)) != expected:
            raise ValueError("Packaged executable differs from verified candidate")


def write_script(project, path, source, layout=None):
    startup = script_sources.startup_path(project)
    globals_ = ef.global_flags(parse(source if path == startup else script_sources.peek(project, startup)))
    helpers = ef.exported_functions(parse(script_sources.peek(project, startup)))
    cid = int(path.stem[1:]) if path.stem.upper().startswith("C") and path.stem[1:].isdigit() else None
    result = compile_source(source, base=read_cmb(path.read_bytes()), global_flags=globals_,
                            known_script_functions={} if path == startup else helpers,
                            flag_context=FlagCompileContext(layout, cid) if layout else None)
    path.write_bytes(write_cmb(result.script))
    sidecar = script_sources.sidecar_path(project, path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(source, encoding="utf-8")


def probe_source():
    lines = ['\n# Experimental manual probes: no automatic state initialization.',
             '@on_location(x=6, y=7, action="visit", name=None)', 'def XftWrite():']
    lines += [f'    set("{name}")' for name in CAMPAIGN + LOCALS]
    lines += ['    TalkEvent("MS_XFT_WRITTEN")', '',
              '@on_location(x=4, y=7, action="visit", name=None)', 'def XftClear():']
    lines += [f'    clr("{name}")' for name in CAMPAIGN + LOCALS]
    lines += ['    TalkEvent("MS_XFT_CLEARED")', '',
              '@on_location(x=5, y=7, action="visit", name=None)', 'def XftRead():']
    for prefix, names in (("CAMPAIGN", CAMPAIGN), ("LOCAL", LOCALS)):
        all_set = " and ".join(f'get("{name}")' for name in names)
        all_clear = " and ".join(f'not get("{name}")' for name in names)
        lines += [f'    if {all_set}:', f'        TalkEvent("MS_XFT_{prefix}_SET")',
                  f'    elif {all_clear}:', f'        TalkEvent("MS_XFT_{prefix}_CLEAR")',
                  '    else:', f'        TalkEvent("MS_XFT_{prefix}_MIXED")']
    return "\n".join(lines) + "\n"


def add_probe(project, cid, layout):
    path = script_sources.chapter_script(project, f"{cid:02d}")
    write_script(project, path, script_sources.peek(project, path) + probe_source(), layout)
    path = chapters.chapter_paths(project, f"{cid:02d}").dialogue
    entries = message.read_messages_path(path)
    texts = {"WRITTEN": "TEST: 100 campaign and 80 local flags set.",
             "CLEARED": "TEST: campaign and local probes cleared."}
    for group, count in (("CAMPAIGN", 100), ("LOCAL", 80)):
        texts[group + "_SET"] = f"{group}: all {count} test flags SET."
        texts[group + "_CLEAR"] = f"{group}: all {count} test flags CLEAR."
        texts[group + "_MIXED"] = f"{group}: MIXED values. Record this result."
    entries += [message.Message("MS_XFT_" + key, fe9_message_scene.to_raw("$RGMAP会話|$O3$G" + text + "$K"))
                for key, text in texts.items()]
    path.write_bytes(message.write_messages(entries, message.read_text_order_path(path)))


def prepare_hub(project):
    data = project.read_logical("game_data")
    donor = next(c for c in fe8data.read_fe8data(data).characters if c.pid == "PID_ACTORMANQUE_P")
    # Rename a fixture-only placeholder; do not alter any normal character's identity.
    fields = {"pid": AVATAR, "jid": "JID_RANGER", "fid": "FID_IKE", "mpid": "MPID_IKE",
              "aid_unpromoted": "AID_LORD", "aid_promoted": "AID_LORD2", "level": 1,
              "sid0": None, "sid1": None, "sid2": None, "weapon_ranks": "D--------"}
    for key, value in fields.items():
        data = fe8data.patch_character_field(data, donor.index, key, value)
    project.write_logical("game_data", data)
    plan = hub_creation.create_chapter(project, data, "05", 33, "Flag Test Hub", 12, 12, AVATAR, (6, 7))
    project.write_logical("game_data", plan.fe8data)
    path = script_sources.chapter_script(project, "33")
    write_script(project, path, script_sources.peek(project, path) + '\n@export\ndef Startup():\n    pass\n')
    return hub.HubSetup(33, 1, AVATAR, (
        hub.Destination(2, 4, 4, 5, 6, "Normal round trip: play Chapter 1, then return here."),
        hub.Destination(3, 6, 4, 5, 6, "Chapter 2 test route. Use after completing Chapter 1."),
        hub.Destination(18, 8, 4, 5, 6, "Advanced Chapter 17 multipart test. Early army may be too weak."),
    ), 6, 7)


def build_region(source, output, region, dolphin, controller_config):
    print(f"{region}: copying clean extracted disc", flush=True)
    project = ModProject.create(output, region, Game.PATH_OF_RADIANCE)
    shutil.copytree(source / region, project.extracted_dir, dirs_exist_ok=True)
    has_hub = True  # All three regions now support editable ChapterData.
    setup = prepare_hub(project) if has_hub else None
    layout = FlagLayout()
    startup = script_sources.startup_path(project)
    source_text = script_sources.peek(project, startup)
    for name in CAMPAIGN:
        layout = layout.add(name, "campaign")
        source_text = ef.append_registration(source_text, "RegistGlobalFlags", "global", name)
    # Compile with explicit banks before installing the experimental native candidate.
    write_script(project, startup, source_text, layout)
    for cid in chapters.list_chapter_ids(project):
        number = int(cid)
        if not (1 <= number <= 31 or has_hub and number == 33):
            continue
        path = script_sources.chapter_script(project, cid)
        if path is None:
            continue
        source_text = script_sources.peek(project, path)
        if not any(fn.name == "Startup" for fn in parse(source_text).functions):
            raise ValueError(f"{region} chapter {cid} has no Startup registration entry")
        names = LOCALS if number in (1, 33) else LOCALS[:2]
        for name in names:
            layout = layout.add(name, "chapter", number)
            source_text = ef.append_registration(source_text, "Startup", "regist", name)
        write_script(project, path, source_text, layout)
    if has_hub:
        update = prepare_fresh_project_update(project, setup, layout)
        update.verify_unchanged()
        # Explicit experimental export only, into this newly created fixture.
        # The production commit gate is intentionally never modified or mocked.
        for change in update.changes:
            change.path.parent.mkdir(parents=True, exist_ok=True)
            change.path.write_bytes(change.after)
    else:
        path = project.extracted_dir / "sys/main.dol"
        candidate = build_candidate(Dol.open(path), region, layout)
        path.write_bytes(candidate.executable)
        (project.directory / MANIFEST_NAME).write_text(layout.to_json(), encoding="utf-8")
        (project.directory / RECEIPT_NAME).write_text(receipt_for(candidate, layout), encoding="utf-8")
    add_probe(project, 1, layout)
    if has_hub:
        add_probe(project, 33, layout)
    apply_test_quality_of_life(project, setup, layout)
    archive_changes = sync_boot_archive(project)
    status = inspect_project(project)
    if status.state != RuntimeState.MATCHING:
        raise ValueError(f"Candidate verification failed: {status}")
    if has_hub:
        # Script refreshes redraw the map, but only the two native action
        # finalizers decide whether the acting unit's turn is consumed.  Keep
        # this fixture-only patch guarded by the installed Hub chapter.
        executable = project.extracted_dir / "sys/main.dol"
        executable.write_bytes(patched_executable(executable.read_bytes(), setup.chapter))
    image = project.directory / f"{region}-extended-flags-EXPERIMENTAL.ciso"
    print(f"{region}: building {image.name}", flush=True)
    result = gcdisc.build_gamecube_ciso(project.extracted_dir, image)
    if result.oversized:
        raise ValueError("Fixture unexpectedly exceeds GameCube disc size")
    verify_packaged_executable(image, (project.extracted_dir / "sys/main.dol").read_bytes(), region)
    user = project.directory / "DolphinUser"
    config = user / "Config"
    config.mkdir(parents=True)
    (config / "Dolphin.ini").write_text(
        "[Analytics]\nEnabled = False\nPermissionAsked = True\n"
        "[Core]\nSlotA = 8\nSlotB = 0\nSIDevice0 = 6\nEnableCheats = False\n"
        "[DSP]\nVolume = 75\n[Interface]\nConfirmStop = True\n", encoding="utf-8")
    for filename in ("GCPadNew.ini", "GCKeyNew.ini"):
        origin = controller_config / filename
        if origin.exists():
            shutil.copy2(origin, config / filename)
    launcher = output / f"Play-{region}.cmd"
    launcher.write_text('@echo off\r\n' + f'"{dolphin}" --user "%~dp0{region}\\DolphinUser" '
                        f'--exec "%~dp0{region}\\{image.name}"\r\n', encoding="utf-8")
    with image.open("rb") as stream:
        image_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    record = {"region": region, "layout_uuid": layout.identity, "hub": has_hub,
              "save_container": container_name(bytes.fromhex(layout.identity.replace("-", ""))),
              "image": str(image), "sha256": image_digest,
              "source_dol_sha256": hashlib.sha256((source / region / "sys/main.dol").read_bytes()).hexdigest(),
              "runtime_verified": True, "in_game_verified": False,
              "fixture_revision": 8, "animation_speed": 2.0,
              "native_infinite_actions": bool(setup),
              "return_position_before_fade": bool(setup),
              "avatar_ai_fix": bool(setup),
              "avatar_class_fix": bool(setup),
              "entrance_markers": [[d.x, d.y] for d in setup.destinations] if setup else [],
              "hub_opening_fix": bool(setup),
              "hub_ground_texture_fix": bool(setup),
              "automatic_victory_chapters": [d.chapter for d in setup.destinations] if setup else [],
              "boot_archive_synced": archive_changes,
              "campaign_probes": CAMPAIGN, "local_probes": LOCALS,
              "chapter_two_flag_coverage": sorted({e.chapter for e in layout.entries if e.scope == "chapter"})}
    (project.directory / "test-build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{region}: ready, {image.stat().st_size // (1024*1024)} MiB", flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--controller-config", type=Path, required=True)
    parser.add_argument("--regions", nargs="+", choices=("GFEE01", "GFEP01", "GFEJ01"),
                        default=("GFEE01", "GFEP01", "GFEJ01"))
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output must be a NEW directory; existing test saves are never overwritten")
    if not args.dolphin.is_file():
        parser.error("Dolphin executable is missing")
    for region in args.regions:
        if not (args.source_root / region / "sys/main.dol").is_file():
            parser.error(f"Missing extracted source for {region}")
    output.mkdir(parents=True)
    for filename in ("START-HERE.md", "RESULTS.md"):
        shutil.copy2(Path(__file__).parent / "playtest_templates" / filename, output / filename)
    inspector = Path(__file__).with_name("inspect_extended_flag_playtest.py").resolve()
    (output / "Inspect-test-saves.cmd").write_text(
        f'@echo off\r\n"{sys.executable}" "{inspector}" "%~dp0."\r\npause\r\n', encoding="utf-8")
    records = [build_region(args.source_root, output, region, args.dolphin, args.controller_config)
               for region in args.regions]
    (output / "builds.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
