"""Run a built disc image in the Dolphin emulator.

Dolphin plays the GameCube image the project builds (CISO). It is found from the
``dolphin_path`` setting, then the usual install folders and the ``PATH``. Nothing here is
Tk code; the Disc & Patch page and the Settings dialog use it.

A chapter can also be played without building: Dolphin boots an extracted disc tree when given
its ``sys/main.dol`` (``DiscIO/DirectoryBlob.cpp``). :func:`prepare_chapter_run` makes such a
tree in ``build/dolphin_run``: copies of ``extracted/sys`` with a ``main.dol`` that boots into the
chosen chapter (``game_code.chapter_jump``), and ``files`` as a directory junction to
``extracted/files``, so the project's own files are read in place and its ``main.dol`` is
never touched.

:func:`prepare_save_run` boots the same tree unpatched with a memory card: Dolphin's slot A
becomes a GCI folder (``build/dolphin_run/card_a``) holding one save, through command-line
config overrides (:func:`save_card_config`) that are not written to Dolphin's own settings.

:func:`prepare_wii_save_run` puts an RFEE01 ``FE10_US.dat`` under a private Dolphin user folder;
the ``--user`` command-line option keeps a Radiant Dawn test run out of the user's normal NAND.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .config import load_setting
from .exceptions import ModdingError
from .game_profile import PLAY
from .games import Game, detect_from_extracted, profile

SETTING_KEY = "dolphin_path"
EXECUTABLE_NAMES = ("Dolphin.exe", "Dolphin", "dolphin-emu")


class EmulatorError(ModdingError):
    """Dolphin is missing or could not be started."""


def candidate_paths(environ=None) -> list[Path]:
    """Where Dolphin is usually installed on Windows (the portable/zip build has no installer)."""
    env = os.environ if environ is None else environ
    roots = [env.get(name) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "USERPROFILE")]
    found = []
    for root in filter(None, roots):
        base = Path(root)
        for folder in ("Dolphin-x64", "Dolphin", "Dolphin Emulator", "Programs/Dolphin Emulator"):
            found.append(base / folder / "Dolphin.exe")
    return found


def find_dolphin(configured: Optional[str] = None, *, environ=None,
                 is_file: Callable[[Path], bool] = Path.is_file,
                 which: Callable[[str], Optional[str]] = shutil.which) -> Optional[Path]:
    """The Dolphin executable: the configured path if it exists, else an install folder, else the PATH."""
    if configured:
        path = Path(configured)
        return path if is_file(path) else None
    for path in candidate_paths(environ):
        if is_file(path):
            return path
    for name in EXECUTABLE_NAMES:
        hit = which(name)
        if hit:
            return Path(hit)
    return None


def configured_dolphin() -> Optional[Path]:
    """:func:`find_dolphin` with the saved setting."""
    return find_dolphin(load_setting(SETTING_KEY) or None)


def command(dolphin: Path | str, image: Path | str, *, batch: bool = True,
            save_state: Optional[Path | str] = None, config: tuple[str, ...] = (),
            user_dir: Optional[Path | str] = None) -> list[str]:
    """The command line: ``--exec`` runs the image; ``--batch`` closes Dolphin with the game
    (no game list window); ``--save_state`` loads a state once the game starts; each
    ``config`` entry (``System.Section.Key=Value``) is a ``--config`` override for this run."""
    args = [str(dolphin), "--exec=" + str(image)]
    if batch:
        args.append("--batch")
    if save_state:
        args.append("--save_state=" + str(save_state))
    if user_dir:
        args.append("--user=" + str(Path(user_dir).resolve()))
    args += ["--config=" + c for c in config]
    return args


def launch(image: Path | str, dolphin: Optional[Path | str] = None, *, batch: bool = True,
           save_state: Optional[Path | str] = None, config: tuple[str, ...] = (),
           user_dir: Optional[Path | str] = None,
           popen=subprocess.Popen) -> subprocess.Popen:
    """Start Dolphin on ``image`` and return at once. ``dolphin`` defaults to the configured/found one."""
    image = Path(image)
    if not image.is_file():
        raise EmulatorError(f"There is no disc image at {image}; build the project first.")
    dolphin = Path(dolphin) if dolphin else configured_dolphin()
    if dolphin is None:
        raise EmulatorError("Dolphin was not found. Set its location in Settings > Preferences.")
    if not Path(dolphin).is_file():
        raise EmulatorError(f"Dolphin was not found at {dolphin}. Set its location in Settings > Preferences.")
    try:
        return popen(command(dolphin, image, batch=batch, save_state=save_state, config=config,
                             user_dir=user_dir))
    except OSError as exc:
        raise EmulatorError(f"Dolphin could not be started: {exc}") from exc


RUN_FOLDER = "dolphin_run"
CARD_FOLDER = "card_a"
WII_USER_FOLDER = "dolphin_user"
RFEE01_DATA_PATH = Path("Wii/title/00010000/52464545/data")
#: Dolphin's ``EXIDeviceType::MemoryCardFolder`` (``Core/HW/EXI/EXI_Device.h``).
GCI_FOLDER_DEVICE = 8


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _link_directory(link: Path, target: Path) -> None:
    """Point ``link`` at the directory ``target``: a junction on Windows (no admin rights
    needed), a symbolic link elsewhere. An existing link is replaced; a real folder is not."""
    if _is_link(link):
        current = os.readlink(link).removeprefix("\\\\?\\")
        if Path(current).resolve() == target.resolve():
            return
        if sys.platform == "win32":
            os.rmdir(link)              # removes the junction only, not what it points to
        else:
            os.unlink(link)
    elif link.exists():
        raise EmulatorError(f"{link} is a real folder, not a link; move it away first.")
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target.resolve()), str(link))
    else:
        os.symlink(target.resolve(), link, target_is_directory=True)


def chapter_position(fe8data: bytes, chapter_id: int) -> int:
    """Position of chapter ``chapter_id``'s record in ``ChapterData`` (what the game's chapter
    select passes, rather than the id)."""
    from .formats import fe8data as fe8

    try:
        records = fe8.read_chapter_data(fe8data)
    except (ValueError, IndexError, struct.error) as exc:
        raise EmulatorError(f"FE8Data.bin could not be read ({exc}).") from exc
    for record in records:
        if record.chapter_id == chapter_id:
            return record.index
    raise EmulatorError(f"Chapter {chapter_id:02d} has no ChapterData record.")


def rd_chapter_number(fe10data: bytes, chapter_id: str) -> int:
    """Internal one-byte chapter number for an RD chapter id such as ``0101`` or ``0407a``."""
    from .game_code.rd_story import chapter_number_map

    wanted = str(chapter_id).lower()
    try:
        numbers = chapter_number_map(fe10data)
    except (ValueError, IndexError, KeyError, struct.error) as exc:
        raise EmulatorError(f"FE10Data.cms could not be read ({exc}).") from exc
    for number, cid in numbers.items():
        if str(cid).lower().removeprefix("c") == wanted.removeprefix("c"):
            return number
    raise EmulatorError(f"Chapter {chapter_id} has no ChapterData record.")


def prepare_chapter_run(extracted_dir: Path | str, run_dir: Path | str,
                        chapter_id: int | str, difficulty: int) -> Path:
    """Make ``run_dir`` a disc tree that boots into chapter ``chapter_id`` (a ``ChapterData`` id)
    on ``difficulty`` (a ``chapter_jump.DIFFICULTIES`` value) with a fresh army; returns its
    ``sys/main.dol`` for Dolphin. ``FE8Data.bin`` is read from disk, as the game will read it
    (copy it into ``system.cmp`` first: ``ModProject.sync_system_archive``)."""
    from .game_code import chapter_jump, chapter_jump_fe10, entries, entries_fe10  # noqa: F401
    from .game_code.catalog import Session
    from .game_code.dol import Dol, DolError
    from .game_code.versions import identify, read_boot_code
    from .formats import lz10

    extracted_dir, run_dir = Path(extracted_dir), Path(run_dir)
    source_sys, files = extracted_dir / "sys", extracted_dir / "files"
    if not (source_sys / "main.dol").is_file() or not files.is_dir():
        raise EmulatorError(f"{extracted_dir} has no sys/main.dol or files folder; extract the disc first.")
    detected = detect_from_extracted(extracted_dir)
    if detected is not None and not profile(detected).supports(PLAY):
        raise EmulatorError(profile(detected).unavailable(PLAY))
    game = detected or Game.PATH_OF_RADIANCE
    game_data_path = profile(game).path(files, "game_data")
    try:
        game_data = game_data_path.read_bytes()
        if profile(game).logical("game_data").compressed:
            game_data = lz10.decompress(game_data)
    except (OSError, ValueError, IndexError, struct.error) as exc:
        raise EmulatorError(f"{game_data_path.name} could not be read ({exc}).") from exc
    dol = Dol.open(source_sys / "main.dol")
    version = identify(dol, read_boot_code(extracted_dir)).version
    if version is None:
        raise EmulatorError("This main.dol is not a supported game build.")
    try:
        session = Session(dol, version)
        if game is Game.RADIANT_DAWN:
            chapter_jump_fe10.install(session, rd_chapter_number(game_data, str(chapter_id)), difficulty)
        else:
            chapter_jump.install(session, chapter_position(game_data, int(chapter_id)), difficulty)
    except (DolError, ValueError) as exc:
        raise EmulatorError(f"Could not patch main.dol for the jump: {exc}") from exc

    return _copy_run_tree(extracted_dir, run_dir, bytes(dol.data))


def save_card_config(card_dir: Path | str) -> tuple[str, ...]:
    """Overrides that make slot A a GCI folder at ``card_dir`` for one run. The override path is
    used as is, with no region subfolder (``CEXIMemoryCard::GetGCIFolderPath``)."""
    return (f"Dolphin.Core.SlotA={GCI_FOLDER_DEVICE}",
            f"Dolphin.Core.GCIFolderAPathOverride={Path(card_dir).resolve()}")


def _copy_run_tree(extracted_dir: Path, run_dir: Path, main_dol: bytes) -> Path:
    sys_dir = run_dir / "sys"
    sys_dir.mkdir(parents=True, exist_ok=True)
    for item in (extracted_dir / "sys").iterdir():
        if item.is_file() and item.name != "main.dol":
            shutil.copyfile(item, sys_dir / item.name)
    (sys_dir / "main.dol").write_bytes(main_dol)
    _link_directory(run_dir / "files", extracted_dir / "files")
    # Wii DirectoryBlob needs the partition metadata beside ``sys`` and ``files``.  Different
    # extractors emit different subsets, so copy every known file that is present.
    for name in ("ticket.bin", "tmd.bin", "cert.bin", "h3.bin"):
        source = extracted_dir / name
        if source.is_file():
            shutil.copyfile(source, run_dir / name)
    disc = extracted_dir / "disc"
    if disc.is_dir():
        shutil.copytree(disc, run_dir / "disc", dirs_exist_ok=True)
    return sys_dir / "main.dol"


def prepare_save_run(extracted_dir: Path | str, run_dir: Path | str, gci_name: str, gci: bytes) -> tuple[Path, Path]:
    """Make ``run_dir`` a disc tree booting the project's own ``main.dol`` plus a GCI folder
    (``run_dir/card_a``) holding only ``gci`` (saved as ``gci_name``). Returns the
    ``sys/main.dol`` for Dolphin and the card folder for :func:`save_card_config`. The folder
    is emptied first; whatever the game saves during the run stays there, never in the
    original save file."""
    extracted_dir, run_dir = Path(extracted_dir), Path(run_dir)
    if not (extracted_dir / "sys" / "main.dol").is_file() or not (extracted_dir / "files").is_dir():
        raise EmulatorError(f"{extracted_dir} has no sys/main.dol or files folder; extract the disc first.")
    detected = detect_from_extracted(extracted_dir)
    if detected is not None and not profile(detected).supports(PLAY):
        raise EmulatorError(profile(detected).unavailable(PLAY))
    name = Path(gci_name).name
    if not name.lower().endswith(".gci"):
        name += ".gci"
    dol = _copy_run_tree(extracted_dir, run_dir, (extracted_dir / "sys" / "main.dol").read_bytes())
    card = run_dir / CARD_FOLDER
    card.mkdir(parents=True, exist_ok=True)
    for old in card.iterdir():
        if old.is_file():
            old.unlink()
    (card / name).write_bytes(gci)
    return dol, card


def prepare_wii_save_run(extracted_dir: Path | str, run_dir: Path | str, save_data: bytes,
                         banner: Optional[bytes] = None) -> tuple[Path, Path]:
    """Prepare a Radiant Dawn run with an isolated Dolphin user folder.

    ``save_data`` is written to RFEE01's normal NAND location as ``FE10_US.dat``.  Dolphin's
    ``--user`` option makes the game read and write only this copy; the user's real emulated
    NAND and the source save remain untouched.  ``banner.bin`` is copied when available.
    Returns the run-tree ``main.dol`` and the isolated user directory.
    """
    from .formats.save_file_fe10 import FILE_NAME, FILE_SIZE

    extracted_dir, run_dir = Path(extracted_dir), Path(run_dir)
    if len(save_data) != FILE_SIZE:
        raise EmulatorError(f"RFEE01 save must be 0x{FILE_SIZE:X} bytes, found 0x{len(save_data):X}.")
    if not (extracted_dir / "sys" / "main.dol").is_file() or not (extracted_dir / "files").is_dir():
        raise EmulatorError(f"{extracted_dir} has no sys/main.dol or files folder; extract the disc first.")
    detected = detect_from_extracted(extracted_dir)
    if detected is not None and detected is not Game.RADIANT_DAWN:
        raise EmulatorError("An RFEE01 NAND save can only be played with a Radiant Dawn project.")
    dol = _copy_run_tree(extracted_dir, run_dir, (extracted_dir / "sys" / "main.dol").read_bytes())
    user_dir = run_dir / WII_USER_FOLDER
    data_dir = user_dir / RFEE01_DATA_PATH
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in (FILE_NAME, "banner.bin"):
        old = data_dir / name
        if old.is_file():
            old.unlink()
    (data_dir / FILE_NAME).write_bytes(save_data)
    if banner is not None:
        (data_dir / "banner.bin").write_bytes(banner)
    return dol, user_dir
