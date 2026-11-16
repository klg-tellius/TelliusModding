"""Movie subtitles (Radiant Dawn): ``Movie/caption_data.bin``, one tab per subtitled movie
(see :mod:`fe_modding.formats.fe10_captions`). The pictures themselves are on the Subtitle
Pictures page (``Movie/Caption/``)."""

from __future__ import annotations

import io
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from ..formats import fe10_captions as fc
from ..formats import lz10, tpl
from ..game_profile import files_root_of, message_prefix
from .record_tables_editor import Column, RecordTablesEditor, TableSpec

PREVIEW_WIDTH = 480


class SubtitlesEditor(RecordTablesEditor):
    display_name = "Movie Subtitles"
    subject = "Subtitles"
    help_text = ("The subtitles of the seven story movies are pictures: each caption shows one picture of "
                 "Movie/Caption/<lang><movie>.cms (an LZ10 TPL; replace them on the Subtitle Pictures page) "
                 "centred at the bottom of the screen. Times are milliseconds: the wait counts from the end "
                 "of the previous caption, then the fade-in, the time it stays and the fade-out.")

    def load_tables(self) -> list[TableSpec]:
        files = Path(files_root_of(self._project))
        self._files = files
        self._path = files / "Movie" / "caption_data.bin"
        self._data = fc.read_captions(self._path.read_bytes())
        self._prefix = message_prefix(self._project)
        self._images: dict[str, list] = {}
        self._labels: dict[str, ttk.Label] = {}
        self._photo = None
        columns = [
            Column("picture", "Picture", "int", width=60),
            Column("wait", "Wait (ms)", "int", width=80),
            Column("fade_in", "Fade in", "int", width=70),
            Column("hold", "Shown for", "int", width=80),
            Column("fade_out", "Fade out", "int", width=70),
        ]
        return [TableSpec(movie.movie, movie.movie, movie.captions, columns,
                          new_row=lambda m=movie: fc.Caption(len(m.captions)),
                          note=f"Pictures: {movie.picture_path(self._prefix)}") for movie in self._data.movies]

    def describe(self) -> str:
        return f"{len(self._data.movies)} movies, {sum(len(m.captions) for m in self._data.movies)} captions"

    def build_extra(self, spec: TableSpec, parent) -> None:
        self._labels[spec.key] = ttk.Label(parent, text="", style="Muted.TLabel", compound="top")
        self._labels[spec.key].pack(anchor="w")

    def _pictures(self, movie: fc.MovieCaptions) -> list:
        if movie.movie not in self._images:
            images = []
            path = self._files / movie.picture_path(self._prefix)
            try:
                raw = path.read_bytes()
                images = tpl.read_tpl_images(io.BytesIO(lz10.decompress(raw) if raw[:1] == b"\x10" else raw))
            except (OSError, ValueError):
                images = []
            self._images[movie.movie] = images
        return self._images[movie.movie]

    def row_selected(self, spec: TableSpec, index) -> None:
        label = self._labels.get(spec.key)
        if label is None:
            return
        movie = next(m for m in self._data.movies if m.movie == spec.key)
        if index is None:
            label.config(text="", image="")
            return
        caption = movie.captions[index]
        start, end, _ = movie.timeline()[index]
        images = self._pictures(movie)
        when = f"From {start / 1000:.2f} s to {end / 1000:.2f} s of the movie"
        if not 0 <= caption.picture < len(images):
            label.config(text=f"{when}\n(no picture {caption.picture} in the .cms)", image="")
            return
        image: Image.Image = images[caption.picture].convert("RGBA")
        backdrop = Image.new("RGBA", image.size, (24, 24, 32, 255))
        backdrop.alpha_composite(image)
        if backdrop.width > PREVIEW_WIDTH:
            backdrop = backdrop.resize((PREVIEW_WIDTH, round(backdrop.height * PREVIEW_WIDTH / backdrop.width)))
        self._photo = ImageTk.PhotoImage(backdrop)
        label.config(text=f"{when}\nPicture {caption.picture}, {image.width} x {image.height}", image=self._photo)

    def problems(self) -> list[str]:
        out = []
        for movie in self._data.movies:
            count = len(self._pictures(movie))
            for i, caption in enumerate(movie.captions):
                if count and caption.picture >= count:
                    out.append(f"{movie.movie} caption {i}: picture {caption.picture}, the file has {count}.")
                if min(caption.wait, caption.fade_in, caption.hold, caption.fade_out) < 0:
                    out.append(f"{movie.movie} caption {i}: a time is negative.")
        return out

    def build_files(self) -> dict[Path, bytes]:
        return {self._path: fc.build_captions(self._data)}
