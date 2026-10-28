"""Mod project creation, loading, and persistence.

A project is just a directory on disk containing a ``project.json`` metadata
file plus a few standard subfolders. Everything else (asset extraction,
repacking, editors, ...) is layered on top of this in later milestones.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import tools
from .formats import gcdisc, lz10, pak
from .exceptions import ProjectError
from .game_profile import GameProfile, game_for_disc_id
from .games import Game, get_game_info, profile as game_profile, read_disc_id, read_image_disc_id
from .game_files import OVERLAY_FILE, GameFiles, GamePath, LegacyFiles, OverlayFiles

PROJECT_FILENAME = "project.json"

# Subfolders created inside every new project directory.
SOURCE_DIR = "source"       # disc images copied in by older versions (new projects record the path)
EXTRACTED_DIR = "extracted"  # layout 1: unpacked game files, edited in place
ORIGINALS_DIR = "originals"  # layout 1: first copies of extracted files an import overwrote
OUTPUT_DIR = "output"        # layout 2: only the files the mod replaced or added
BUILD_DIR = "build"          # repacked output (ISO/WBFS ready to run), staged disc trees
PROJECT_SUBDIRS = (EXTRACTED_DIR, BUILD_DIR)

#: Layout 1 keeps a whole extracted disc in the project and edits it in place. Layout 2 reads the
#: vanilla files from a shared, read-only store (``vanilla_store``) and keeps only the mod's own
#: files in ``output/`` (the Paragon-style input/output layout).
LAYOUT_EXTRACTED = 1
LAYOUT_OVERLAY = 2
STAGE_DIR = "stage"          # under build/: the merged disc tree that building and Dolphin read

_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_folder_name(name: str) -> str:
    """Turn a project name into a filesystem-safe folder name."""
    cleaned = _INVALID_FOLDER_CHARS.sub("", name).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise ProjectError("Project name must contain at least one valid character.")
    return cleaned


def build_image(game: Game, extracted_dir: Path, dest: Path, *, overwrite: bool = True) -> Optional[str]:
    """Pack an extracted disc tree into ``dest`` in the game's build format
    and return a warning to show the user, if any."""
    if not game_profile(game).wii:
        # WIT composes every extracted tree as a Wii disc - see gcdisc.py.
        result = gcdisc.build_gamecube_ciso(extracted_dir, dest)
        if result.oversized:
            over_mib = (result.disc_size - gcdisc.GAMECUBE_DISC_SIZE) / (1 << 20)
            return (
                f"The game data is {over_mib:.1f} MiB larger than a GameCube disc can hold. "
                "The image runs in Dolphin, but not on real hardware or in loaders that "
                "enforce the disc size. Shrink large replaced files (e.g. videos) to fit."
            )
        return None
    tools.build_disc(extracted_dir, dest, overwrite=overwrite)
    return None


@dataclass
class ModProject:
    name: str
    game: Game
    directory: Path
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_iso: Optional[str] = None     # file name of the source disc image, shown in the app
    source_image: Optional[str] = None   # its absolute path; None for projects with a copy in source/
    author: str = ""
    version: str = ""
    credits: str = ""  # free text: who made or allowed what; goes into patches
    layout: int = LAYOUT_EXTRACTED
    input_key: Optional[str] = None      # layout 2: the vanilla store the project reads
    last_build_warning: Optional[str] = field(default=None, repr=False, compare=False)
    _files: Optional[GameFiles] = field(default=None, init=False, repr=False, compare=False)

    @property
    def project_file(self) -> Path:
        return self.directory / PROJECT_FILENAME

    @property
    def game_info(self):
        return get_game_info(self.game)

    @property
    def profile(self) -> GameProfile:
        """Where this game keeps its files and which features the app has for it."""
        return game_profile(self.game)

    @property
    def files(self) -> GameFiles:
        """The project's game files: every read and write of a disc file goes through this."""
        if self._files is None:
            if self.layout == LAYOUT_OVERLAY:
                root = self.input_root
                self._files = OverlayFiles(root if root is not None else self.directory / ".no-input",
                                           self.output_dir, self.directory / OVERLAY_FILE)
            else:
                self._files = LegacyFiles(self.extracted_dir, self.originals_dir)
        return self._files

    @property
    def is_overlay(self) -> bool:
        return self.layout == LAYOUT_OVERLAY

    @property
    def input_store(self):
        """Layout 2: the vanilla store the project reads, or None when it is not set or gone."""
        if not self.input_key:
            return None
        from . import vanilla_store
        return vanilla_store.get_store(self.input_key)

    @property
    def input_root(self) -> Optional[Path]:
        store = self.input_store
        return store.root if store is not None else None

    @property
    def output_dir(self) -> Path:
        """Layout 2: the mod's own files, at their disc paths (``output/files/...``)."""
        return self.directory / OUTPUT_DIR

    def disc_tree(self) -> Path:
        """A real folder holding the whole disc as it is now, for the disc builders and Dolphin:
        ``extracted/`` itself, or the merged tree staged in ``build/stage`` (layout 2)."""
        return self.files.disc_tree(self.build_dir / STAGE_DIR)

    @property
    def files_root(self) -> GamePath:
        """The disc's file tree (``files/``), where the profile's paths are relative to, as a
        :class:`~fe_modding.game_files.GamePath`: joins, reads and writes go through :attr:`files`."""
        return self.files.at("files")

    @property
    def sys_root(self) -> GamePath:
        """The disc's ``sys/`` folder (``main.dol``, ``boot.bin``...), through :attr:`files`."""
        return self.files.at("sys")

    @property
    def files_dir(self) -> Path:
        """``extracted/files`` of the older layout. Use :attr:`files_root`."""
        return self.extracted_dir / "files"

    def logical_rel(self, name: str) -> str:
        """Disc-relative path of a logical game file (``files/FE8Data.bin``), for :attr:`files`."""
        return f"files/{self.profile.logical(name).path}"

    def logical_path(self, name: str) -> GamePath:
        """A logical game file (``game_data``, ``battle_data``...) of this project."""
        return self.files.at(self.logical_rel(name))

    def read_logical(self, name: str) -> bytes:
        """The bytes of a logical game file, LZ10-decompressed when the game stores it compressed
        (Radiant Dawn's ``.cms`` files). Raises ProjectError when the file is missing."""
        data = self.files.read_or_none(self.logical_rel(name))
        if data is None:
            raise ProjectError(f"{self.profile.file_label(name)} was not found. Extract the project first.")
        path = self.logical_path(name)
        if self.profile.logical(name).compressed:
            try:
                return lz10.decompress(data)
            except lz10.LZ10Error as exc:
                raise ProjectError(f"{path.name} could not be decompressed: {exc}") from exc
        return data

    def write_logical(self, name: str, data: bytes) -> None:
        """Write a logical game file through :attr:`files`, LZ10-compressing it where the game
        stores it compressed."""
        if self.profile.logical(name).compressed:
            data = lz10.compress(data)
        self.files.write(self.logical_rel(name), data)

    @property
    def source_path(self) -> Optional[Path]:
        """Absolute path to the source disc image, if one has been set: the recorded path, or for
        projects made by older versions the copy in ``source/``. The image may have moved since."""
        if self.source_image:
            return Path(self.source_image)
        if not self.source_iso:
            return None
        return self.directory / SOURCE_DIR / self.source_iso

    @property
    def source_missing(self) -> bool:
        """Whether a source disc image is set but no longer where it was recorded."""
        return self.source_path is not None and not self.source_path.is_file()

    @property
    def extracted_dir(self) -> Path:
        return self.directory / EXTRACTED_DIR

    @property
    def build_dir(self) -> Path:
        return self.directory / BUILD_DIR

    @property
    def originals_dir(self) -> Path:
        """Copies of extracted files as they were before an import first
        overwrote them, at the same relative paths (created on demand)."""
        return self.directory / ORIGINALS_DIR

    def _extracted_path(self, relative: str) -> Path:
        return self.extracted_dir / relative

    def write_keeping_original(self, path: Path | str, data: bytes) -> None:
        """Write ``data`` to ``path`` (a file under ``extracted/``) through :attr:`files`, which
        keeps the file as extracted however many times it is replaced."""
        self.files.write(Path(path), data)

    def extracted_bytes(self, path: Path | str) -> Optional[bytes]:
        """``path`` (under ``extracted/``) as extracted; None when the disc had no such file."""
        files = self.files
        return files.vanilla(Path(path))

    def is_added_file(self, path: Path | str) -> Optional[bool]:
        """Whether ``path`` (a file under ``files/``) is one the mod added, absent from the source
        disc; None when that cannot be told."""
        return self.files.is_added(Path(path))

    def originals_in(self, folder: Path | str) -> list[Path]:
        """The extracted files directly in ``folder`` that the mod replaced (their paths under
        ``extracted/``)."""
        files = self.files
        return [self._extracted_path(rel) for rel in files.modified_in(Path(folder))]

    def restore_original(self, path: Path | str) -> None:
        """Put the file as extracted back."""
        if not self.files.revert(Path(path)):
            raise ProjectError(f"No kept original for {path}.")

    @property
    def has_extracted_files(self) -> bool:
        """Whether the game's files are there to edit (extracted, or the vanilla store found)."""
        if self.is_overlay:
            return self.files.has_files
        return self.extracted_dir.exists() and any(self.extracted_dir.iterdir())

    def _set_input(self, store) -> None:
        self.input_key = store.key
        self._files = None
        self.save()
        from .formats import game_text
        game_text.use_for_extraction(self.files.at(""))

    def use_input_folder(self, folder: Path | str):
        """Layout 2: read the vanilla files from a folder the user already extracted (Dolphin's
        "Extract Entire Disc", WIT...), registered in place as a store. Returns the store."""
        from . import vanilla_store
        store = vanilla_store.adopt_folder(folder, wii=self.profile.wii)
        warning = self._mismatch_message(store.disc_id)
        if warning and game_for_disc_id(store.disc_id) is not None:
            raise ProjectError(warning)
        self._set_input(store)
        return store

    def input_problems(self) -> list[str]:
        """Layout 2: what is wrong with the vanilla files, empty when nothing: the store is gone or
        changed, or files the mod replaced were made from other vanilla files than these."""
        if not self.is_overlay:
            return []
        store = self.input_store
        if store is None:
            return ["The vanilla files this project reads are not available. Extract the disc again "
                    "or choose the extracted folder."]
        problems = store.verify()
        hashes = store.file_hashes()
        for rel, sha1 in self.files.base_hashes().items():
            if rel in hashes and hashes[rel] != sha1:
                problems.append(f"{rel}: the mod's file was made from another version of it")
        return problems

    def set_source(self, disc_image: Path | str) -> Path:
        """Record a disc image as the project's source, by its absolute path (it is not copied).

        Returns that path. Raises ProjectError if the extension isn't one the
        bundled tool can read for this game.
        """
        disc_image = Path(disc_image)
        if not disc_image.is_file():
            raise ProjectError(f"Source disc image not found: {disc_image}")

        allowed = self.game_info.disc_formats
        if disc_image.suffix.lower() not in allowed:
            raise ProjectError(
                f"'{disc_image.suffix}' is not a format the bundled tool can read for "
                f"{self.game_info.display_name}. Supported: {', '.join(allowed)}."
            )

        disc_image = disc_image.resolve()
        self.source_iso = disc_image.name
        self.source_image = str(disc_image)
        self.save()
        return disc_image

    def extract(self, *, overwrite: bool = True) -> Path:
        """Extract the source disc image: into the project's extracted/ folder (layout 1), or into
        the shared vanilla store unless that disc is already there (layout 2). Returns the tree."""
        if self.source_path is None:
            raise ProjectError("No source disc image set for this project yet.")
        if self.source_missing:
            raise ProjectError(f"The source disc image is no longer at {self.source_path}. Choose it again.")
        if self.is_overlay:
            from . import vanilla_store
            store = vanilla_store.ensure_store(self.source_path, wii=self.profile.wii)
            self._set_input(store)
            return store.root
        tools.extract_disc(self.source_path, self.extracted_dir, overwrite=overwrite, wii=self.profile.wii)
        return self.extracted_dir

    def _mismatch_message(self, disc_id: str) -> Optional[str]:
        detected = game_for_disc_id(disc_id)
        if detected == self.game:
            return None
        if detected is None:
            return (f"The disc ID {disc_id} is not a Path of Radiance or Radiant Dawn disc, so this "
                    f"{self.game_info.display_name} project may not work with it.")
        return (f"This is a {get_game_info(detected).display_name} disc ({disc_id}), but the project is "
                f"set to {self.game_info.display_name}. Create the project again with the right game.")

    def disc_mismatch_warning(self) -> Optional[str]:
        """A warning when the extracted disc is not the project's game (e.g. a Radiant Dawn disc in
        a Path of Radiance project), from the disc ID in ``sys/boot.bin``; None when it matches or
        there is no ID to read."""
        disc_id = read_disc_id(self.files.at(""))
        return self._mismatch_message(disc_id) if disc_id else None

    def source_mismatch_warning(self) -> Optional[str]:
        """The same check on the source image's header, before extracting (plain ISO/WBFS/CISO only;
        None for formats whose ID needs a tool to read)."""
        if self.source_path is None:
            return None
        disc_id = read_image_disc_id(self.source_path)
        return self._mismatch_message(disc_id) if disc_id else None

    def build(self, *, overwrite: bool = True) -> Path:
        """Build a disc image of the project's files as they are now (:meth:`disc_tree`)."""
        from .game_code.extended_flags import require_project_runtime
        require_project_runtime(self)
        if not self.has_extracted_files:
            raise ProjectError("Nothing extracted yet - extract the source disc image first.")
        dest = self.build_dir / f"{sanitize_folder_name(self.name)}{self.game_info.build_extension}"
        self.last_build_warning = None
        if self.profile.has_file("system_archive"):
            if dest.exists() and not overwrite:
                raise ProjectError(f"{dest} already exists.")
            from .chapters import ensure_name_images
            ensure_name_images(self)       # before the sync: nothing it writes is in system.cmp
            self.sync_system_archive()
        self.last_build_warning = build_image(self.game, self.disc_tree(), dest, overwrite=overwrite)
        return dest

    def sync_system_archive(self) -> list[str]:
        """Copy edited loose files into ``system.cmp`` and return their names.

        ``system.cmp`` bundles copies of ``FE8Data.bin``, ``FE8Anim.bin``,
        ``mess/common.m`` and other loose files. The game loads it at boot and
        its file lookup searches loaded archives before the disc, so the copies
        are the ones it reads; the loose files stay the ones editors change."""
        if not self.profile.has_file("system_archive"):
            return []
        path = self.logical_path("system_archive")
        if not path.is_file():
            return []
        unpacked = lz10.decompress(path.read_bytes())
        entries = pak.read_pak_entries(unpacked)
        files, changed = [], []
        for entry in entries:
            content = pak.read_pak_file_content(unpacked, entry)
            loose = self.files_root / entry.name
            if loose.is_file() and loose.read_bytes() != content:
                content = loose.read_bytes()
                changed.append(entry.name)
            files.append((entry.name, content))
        if changed:
            packed = pak.pack_pak(files, [entry.reserved for entry in entries])
            path.write_bytes(lz10.compress(packed))
        return changed

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "game": self.game.value,
            "description": self.description,
            "created_at": self.created_at,
            "source_iso": self.source_iso,
            "source_image": self.source_image,
            "author": self.author,
            "version": self.version,
            "credits": self.credits,
            **({"layout": self.layout, "input": self.input_key} if self.is_overlay else {}),
        }

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.project_file.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def create(
        cls,
        parent_directory: Path | str,
        name: str,
        game: Game,
        description: str = "",
        layout: int = LAYOUT_EXTRACTED,
    ) -> "ModProject":
        """Create a new project as a subfolder of ``parent_directory``, in ``layout`` (the app
        makes new projects in :data:`LAYOUT_OVERLAY`).

        Raises ProjectError if the target folder already exists and is not empty.
        """
        name = name.strip()
        if not name:
            raise ProjectError("Project name cannot be empty.")

        parent_directory = Path(parent_directory)
        if not parent_directory.exists():
            raise ProjectError(f"Location does not exist: {parent_directory}")
        if not parent_directory.is_dir():
            raise ProjectError(f"Location is not a folder: {parent_directory}")

        directory = parent_directory / sanitize_folder_name(name)
        if directory.exists() and any(directory.iterdir()):
            raise ProjectError(f"'{directory}' already exists and is not empty.")

        directory.mkdir(parents=True, exist_ok=True)
        for sub in (PROJECT_SUBDIRS if layout == LAYOUT_EXTRACTED else (OUTPUT_DIR, BUILD_DIR)):
            (directory / sub).mkdir(parents=True, exist_ok=True)

        project = cls(name=name, game=game, directory=directory, description=description, layout=layout)
        project.save()
        return project

    @classmethod
    def load(cls, directory: Path | str) -> "ModProject":
        directory = Path(directory)
        project_file = directory / PROJECT_FILENAME
        if not project_file.exists():
            raise ProjectError(f"No project found in '{directory}' (missing {PROJECT_FILENAME}).")

        try:
            with project_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise ProjectError(f"Could not read project file '{project_file}': {exc}") from exc

        try:
            game = Game(data["game"])
        except (KeyError, ValueError) as exc:
            raise ProjectError(f"Project file '{project_file}' has an invalid or missing game id.") from exc

        from .formats import game_text
        project = cls(
            name=data.get("name", directory.name),
            game=game,
            directory=directory,
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            source_iso=data.get("source_iso"),
            source_image=data.get("source_image"),
            author=data.get("author", ""),
            version=data.get("version", ""),
            credits=data.get("credits", ""),
            layout=int(data.get("layout", LAYOUT_EXTRACTED)),
            input_key=data.get("input"),
        )
        if project.layout not in (LAYOUT_EXTRACTED, LAYOUT_OVERLAY):
            raise ProjectError(f"Project file '{project_file}' uses a layout this version cannot open.")
        game_text.use_for_extraction(project.files.at(""))
        return project
