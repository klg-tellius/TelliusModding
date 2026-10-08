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
from .games import Game, get_game_info

PROJECT_FILENAME = "project.json"

# Subfolders created inside every new project directory.
SOURCE_DIR = "source"       # the original disc image(s) the project was built from
EXTRACTED_DIR = "extracted"  # unpacked game files, ready to edit
BUILD_DIR = "build"          # repacked output (ISO/WBFS ready to run)
ORIGINALS_DIR = "originals"  # first copies of extracted files an import overwrote
PROJECT_SUBDIRS = (SOURCE_DIR, EXTRACTED_DIR, BUILD_DIR)

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
    if game == Game.PATH_OF_RADIANCE:
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
    source_iso: Optional[str] = None
    author: str = ""
    version: str = ""
    credits: str = ""  # free text: who made or allowed what; goes into patches
    last_build_warning: Optional[str] = field(default=None, repr=False, compare=False)

    @property
    def project_file(self) -> Path:
        return self.directory / PROJECT_FILENAME

    @property
    def game_info(self):
        return get_game_info(self.game)

    @property
    def source_path(self) -> Optional[Path]:
        """Absolute path to the source disc image, if one has been set."""
        if not self.source_iso:
            return None
        return self.directory / SOURCE_DIR / self.source_iso

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

    def _original_of(self, path: Path) -> Optional[Path]:
        try:
            relative = Path(path).resolve().relative_to(self.extracted_dir.resolve())
        except ValueError:
            return None
        return self.originals_dir / relative

    def write_keeping_original(self, path: Path | str, data: bytes) -> None:
        """Write ``data`` to ``path`` (a file under ``extracted/``), first
        copying the current file to :attr:`originals_dir` unless a copy is
        already there - so the copy stays the file as extracted however
        many times it is replaced."""
        path = Path(path)
        original = self._original_of(path)
        if original is not None and path.is_file() and not original.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, original)
        path.write_bytes(data)

    def originals_in(self, folder: Path | str) -> list[Path]:
        """The extracted files directly in ``folder`` that have a kept
        original (their paths under ``extracted/``)."""
        original_folder = self._original_of(Path(folder))
        if original_folder is None or not original_folder.is_dir():
            return []
        return [Path(folder) / p.name for p in sorted(original_folder.iterdir()) if p.is_file()]

    def restore_original(self, path: Path | str) -> None:
        """Put the kept original of ``path`` back and drop the copy."""
        path = Path(path)
        original = self._original_of(path)
        if original is None or not original.is_file():
            raise ProjectError(f"No kept original for {path}.")
        shutil.copy2(original, path)
        original.unlink()

    @property
    def has_extracted_files(self) -> bool:
        return self.extracted_dir.exists() and any(self.extracted_dir.iterdir())

    def set_source(self, disc_image: Path | str) -> Path:
        """Copy a disc image into the project's source/ folder and record it.

        Returns the new path inside the project. Raises ProjectError if the
        extension isn't one the bundled tool can read for this game.
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

        source_dir = self.directory / SOURCE_DIR
        source_dir.mkdir(parents=True, exist_ok=True)
        dest = source_dir / disc_image.name
        if dest.resolve() != disc_image.resolve():
            shutil.copy2(disc_image, dest)

        self.source_iso = dest.name
        self.save()
        return dest

    def extract(self, *, overwrite: bool = True) -> Path:
        """Extract the source disc image into the project's extracted/ folder."""
        if self.source_path is None:
            raise ProjectError("No source disc image set for this project yet.")
        tools.extract_disc(self.source_path, self.extracted_dir, overwrite=overwrite)
        return self.extracted_dir

    def build(self, *, overwrite: bool = True) -> Path:
        """Rebuild a disc image from the project's extracted/ folder."""
        if not self.has_extracted_files:
            raise ProjectError("Nothing extracted yet - extract the source disc image first.")
        dest = self.build_dir / f"{sanitize_folder_name(self.name)}{self.game_info.build_extension}"
        self.last_build_warning = None
        if self.game == Game.PATH_OF_RADIANCE:
            if dest.exists() and not overwrite:
                raise ProjectError(f"{dest} already exists.")
            from .chapters import ensure_name_images
            ensure_name_images(self)       # before the sync: nothing it writes is in system.cmp
            self.sync_system_archive()
        self.last_build_warning = build_image(self.game, self.extracted_dir, dest, overwrite=overwrite)
        return dest

    def sync_system_archive(self) -> list[str]:
        """Copy edited loose files into ``system.cmp`` and return their names.

        ``system.cmp`` bundles copies of ``FE8Data.bin``, ``FE8Anim.bin``,
        ``mess/common.m`` and other loose files. The game loads it at boot and
        its file lookup searches loaded archives before the disc, so the copies
        are the ones it reads; the loose files stay the ones editors change."""
        path = self.extracted_dir / "files" / "system.cmp"
        if not path.is_file():
            return []
        unpacked = lz10.decompress(path.read_bytes())
        entries = pak.read_pak_entries(unpacked)
        files, changed = [], []
        for entry in entries:
            content = pak.read_pak_file_content(unpacked, entry)
            loose = self.extracted_dir / "files" / entry.name
            if loose.is_file() and loose.read_bytes() != content:
                content = loose.read_bytes()
                changed.append(entry.name)
            files.append((entry.name, content))
        if changed:
            packed = pak.pack_pak(files, [entry.reserved for entry in entries])
            self.write_keeping_original(path, lz10.compress(packed))
        return changed

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "game": self.game.value,
            "description": self.description,
            "created_at": self.created_at,
            "source_iso": self.source_iso,
            "author": self.author,
            "version": self.version,
            "credits": self.credits,
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
    ) -> "ModProject":
        """Create a new project as a subfolder of ``parent_directory``.

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
        for sub in PROJECT_SUBDIRS:
            (directory / sub).mkdir(parents=True, exist_ok=True)

        project = cls(name=name, game=game, directory=directory, description=description)
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

        return cls(
            name=data.get("name", directory.name),
            game=game,
            directory=directory,
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            source_iso=data.get("source_iso"),
            author=data.get("author", ""),
            version=data.get("version", ""),
            credits=data.get("credits", ""),
        )
