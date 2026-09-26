"""Tkinter live preview for chapter dialogue conversations."""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from ..formats import conversation, face_data, lz10, portrait_anim, rect, tpl
from ..project import ModProject

SCENE_SIZE = (640, 480)
TEXT_BOXES = (
    (0, 296, 640, 480),
    (0, 72, 640, 256),
    (0, 296, 640, 480),
    (0, 72, 640, 256),
)
TEXT_INSET = (44, 48)
NAME_PLATE = (36, -24, 214, 14)
PORTRAIT_POSITIONS = (
    (112, 326),
    (528, 326),
    (224, 326),
    (416, 326),
    (320, 326),
    (64, 326),
    (576, 326),
    (168, 326),
    (472, 326),
)


class ConversationPreview(ttk.Frame):
    def __init__(self, parent: tk.Misc, project: ModProject):
        super().__init__(parent)
        self._asset_loader = _ConversationAssetLoader(project.extracted_dir)
        self._timeline = conversation.build_timeline("")
        self._elapsed_ms = 0
        self._playing = False
        self._waiting_for_input = False
        self._auto_advance_page_breaks = tk.BooleanVar(value=True)
        self._after_id: str | None = None
        self._canvas_images: list[ImageTk.PhotoImage] = []
        self._timeline_var = tk.DoubleVar(value=0.0)
        self._updating_timeline = False

        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 4))
        ttk.Label(controls, text="Playback").pack(side="left", padx=(0, 8))
        self._play_button = ttk.Button(controls, text="Play", command=self._toggle_play)
        self._play_button.pack(side="left")
        self._restart_button = ttk.Button(controls, text="Restart", command=self._restart)
        self._restart_button.pack(side="left", padx=(6, 0))
        self._step_button = ttk.Button(controls, text="Step", command=self._step)
        self._step_button.pack(side="left", padx=(6, 0))
        self._auto_advance_check = ttk.Checkbutton(
            controls,
            text="Auto-advance pages",
            variable=self._auto_advance_page_breaks,
        )
        self._auto_advance_check.pack(side="left", padx=(8, 0))
        self._position_label = ttk.Label(controls, text="", style="Muted.TLabel")
        self._position_label.pack(side="left", padx=(8, 0))
        self._warning_label = ttk.Label(controls, text=self._asset_loader.warning, foreground="#a66")
        self._warning_label.pack(side="left", padx=(8, 0))

        timeline_row = ttk.Frame(self)
        timeline_row.pack(fill="x", pady=(0, 4))
        ttk.Label(timeline_row, text="Playback Timeline").pack(anchor="w")
        self._timeline_scale = ttk.Scale(
            timeline_row,
            from_=0,
            to=1,
            orient="horizontal",
            variable=self._timeline_var,
            command=self._on_timeline_dragged,
        )
        self._timeline_scale.pack(fill="x", expand=True)
        self._timeline_events = tk.Canvas(timeline_row, height=18, highlightthickness=0, background="#f4f4f4")
        self._timeline_events.pack(fill="x", pady=(2, 0))
        self._timeline_events.bind("<Button-1>", self._on_timeline_event_click)
        self._timeline_events.bind("<Configure>", lambda _event: self._draw_timeline_events())

        self._canvas = tk.Canvas(self, width=SCENE_SIZE[0], height=SCENE_SIZE[1], highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", lambda _event: self._render())

        self.update_message("", "")

    def update_message(self, speaker: str, text: str, *, message_id=None) -> None:
        self._stop_timer()
        self._timeline = conversation.build_timeline(text, fallback_speaker=speaker)
        self._elapsed_ms = 0
        self._playing = False
        self._waiting_for_input = False
        self._configure_timeline_scale()
        self._render()

    def cleanup(self) -> None:
        self._stop_timer()

    def _toggle_play(self) -> None:
        if self._playing:
            self._playing = False
            self._stop_timer()
        else:
            if self._elapsed_ms >= self._timeline.duration_ms:
                self._elapsed_ms = 0
            self._waiting_for_input = False
            self._playing = True
            self._tick()
        self._render()

    def _restart(self) -> None:
        self._stop_timer()
        self._elapsed_ms = 0
        self._playing = False
        self._waiting_for_input = False
        self._render()

    def _step(self) -> None:
        self._stop_timer()
        self._playing = False
        if self._waiting_for_input:
            self._waiting_for_input = False
            self._elapsed_ms = self._timeline.next_frame_after(self._elapsed_ms).time_ms
        else:
            self._elapsed_ms = self._timeline.next_interesting_after(self._elapsed_ms).time_ms
            frame = self._timeline.frame_at(self._elapsed_ms)
            self._waiting_for_input = frame.wait_for_input
        self._render()

    def _on_timeline_dragged(self, value: str) -> None:
        if self._updating_timeline:
            return
        self._stop_timer()
        self._playing = False
        self._waiting_for_input = False
        try:
            self._elapsed_ms = int(float(value))
        except ValueError:
            self._elapsed_ms = 0
        self._elapsed_ms = max(0, min(self._elapsed_ms, self._timeline.duration_ms))
        self._render()

    def _on_timeline_event_click(self, event: tk.Event) -> None:
        width = max(1, self._timeline_events.winfo_width())
        duration = max(1, self._timeline.duration_ms)
        self._stop_timer()
        self._playing = False
        self._waiting_for_input = False
        self._elapsed_ms = max(0, min(self._timeline.duration_ms, int(event.x / width * duration)))
        self._render()

    def _tick(self) -> None:
        if not self._playing:
            return
        next_wait = self._timeline.next_wait_after(self._elapsed_ms)
        next_elapsed = min(self._elapsed_ms + 50, self._timeline.duration_ms)
        if (
            not self._auto_advance_page_breaks.get()
            and next_wait is not None
            and self._elapsed_ms < next_wait.time_ms <= next_elapsed
        ):
            self._elapsed_ms = next_wait.time_ms
            self._playing = False
            self._waiting_for_input = True
            self._render()
            return
        self._elapsed_ms = next_elapsed
        if self._elapsed_ms >= self._timeline.duration_ms:
            self._playing = False
            self._stop_timer()
            self._render()
            return
        self._render()
        self._after_id = self.after(50, self._tick)

    def _stop_timer(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

    def _render(self) -> None:
        self._canvas.delete("all")
        self._canvas_images.clear()
        if not self._timeline.frames:
            return
        self._sync_timeline_controls()

        width = max(1, self._canvas.winfo_width())
        height = max(1, self._canvas.winfo_height())
        scale = min(width / SCENE_SIZE[0], height / SCENE_SIZE[1])
        offset_x = (width - SCENE_SIZE[0] * scale) / 2
        offset_y = (height - SCENE_SIZE[1] * scale) / 2

        def sx(value: float) -> float:
            return offset_x + value * scale

        def sy(value: float) -> float:
            return offset_y + value * scale

        def box(values: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
            return sx(values[0]), sy(values[1]), sx(values[2]), sy(values[3])

        frame = self._timeline.frame_at(self._elapsed_ms)
        state = frame.state

        background = self._asset_loader.background(state.background)
        if background is not None:
            self._draw_image_cover(background, sx(0), sy(0), SCENE_SIZE[0] * scale, SCENE_SIZE[1] * scale)
        else:
            self._draw_placeholder_background(sx, sy, scale, state.background)

        for slot, portrait in enumerate(state.portraits):
            if not portrait.visible or not portrait.name:
                continue
            asset = self._asset_loader.portrait(portrait.name)
            x, y = PORTRAIT_POSITIONS[slot]
            if asset is None:
                self._draw_portrait_placeholder(sx(x), sy(y), scale, portrait.name, portrait.expression)
            else:
                image = asset.render(portrait.expression, self._elapsed_ms)
                self._draw_portrait(image, sx(x), sy(y), scale, portrait.expression)

        active_box = TEXT_BOXES[min(state.selected_box, len(TEXT_BOXES) - 1)]
        self._draw_text_window(active_box, frame.speaker, frame.text, sx, sy, scale)
        box_left, box_top, box_right, box_bottom = active_box
        self._canvas.create_text(
            sx(box_right - 52),
            sy(box_bottom - 32),
            text="▼",
            fill="#f5e8b8",
            font=("Segoe UI", max(9, int(15 * scale)), "bold"),
        )

        self._play_button.config(text="Pause" if self._playing else ("Continue" if self._waiting_for_input else "Play"))
        status = "waiting" if self._waiting_for_input else frame.kind
        page = self._timeline.page_number_at(self._elapsed_ms)
        self._position_label.config(
            text=f"Page {page}/{self._timeline.page_count} - {self._elapsed_ms} / {self._timeline.duration_ms} ms ({status})"
        )
        self._draw_timeline_events()

    def _configure_timeline_scale(self) -> None:
        self._timeline_scale.configure(to=max(1, self._timeline.duration_ms))
        self._sync_timeline_controls()
        self._draw_timeline_events()

    def _sync_timeline_controls(self) -> None:
        self._updating_timeline = True
        try:
            self._timeline_var.set(float(self._elapsed_ms))
        finally:
            self._updating_timeline = False

    def _draw_timeline_events(self) -> None:
        if not hasattr(self, "_timeline_events"):
            return
        self._timeline_events.delete("all")
        width = max(1, self._timeline_events.winfo_width())
        height = max(1, self._timeline_events.winfo_height())
        duration = max(1, self._timeline.duration_ms)
        self._timeline_events.create_rectangle(0, height // 2 - 2, width, height // 2 + 2, fill="#d7dce2", outline="")
        current_x = int(width * self._elapsed_ms / duration)
        self._timeline_events.create_rectangle(0, height // 2 - 3, current_x, height // 2 + 3, fill="#3b82f6", outline="")
        for frame in self._timeline.frames:
            if frame.kind not in {"pause", "page_break", "end"} and not frame.wait_for_input:
                continue
            x = int(width * frame.time_ms / duration)
            color = "#d97706" if frame.kind == "pause" else "#dc2626" if frame.wait_for_input else "#475569"
            self._timeline_events.create_line(x, 2, x, height - 2, fill=color, width=2)
        self._timeline_events.create_oval(current_x - 4, height // 2 - 4, current_x + 4, height // 2 + 4, fill="#1d4ed8", outline="")

    def _draw_image_cover(self, image: Image.Image, x: float, y: float, width: float, height: float) -> None:
        if width <= 1 or height <= 1:
            return
        resized = _cover_resize(image.convert("RGBA"), (max(1, int(width)), max(1, int(height))))
        photo = ImageTk.PhotoImage(resized)
        self._canvas_images.append(photo)
        self._canvas.create_image(x, y, image=photo, anchor="nw")

    def _draw_portrait(self, image: Image.Image, x: float, y: float, scale: float, expression: str | None) -> None:
        max_size = (max(1, int(192 * scale)), max(1, int(144 * scale)))
        portrait = image.convert("RGBA").copy()
        portrait.thumbnail(max_size, _pixel_resample())
        photo = ImageTk.PhotoImage(portrait)
        self._canvas_images.append(photo)
        self._canvas.create_image(x, y, image=photo, anchor="s")

    def _draw_text_window(self, rect_values, speaker: str, text: str, sx, sy, scale: float) -> None:
        left, top, right, bottom = rect_values
        shadow = (sx(left + 7), sy(top + 8), sx(right - 7), sy(bottom - 4))
        outer = (sx(left + 16), sy(top + 12), sx(right - 16), sy(bottom - 14))
        inner = (sx(left + 24), sy(top + 20), sx(right - 24), sy(bottom - 22))
        self._canvas.create_rectangle(*shadow, fill="#050608", outline="")
        self._canvas.create_rectangle(*outer, fill="#1b130d", outline="#f6d992", width=max(1, int(3 * scale)))
        self._canvas.create_rectangle(
            sx(left + 21),
            sy(top + 17),
            sx(right - 21),
            sy(bottom - 19),
            fill="#5a3922",
            outline="#9d6b34",
            width=max(1, int(2 * scale)),
        )
        self._canvas.create_rectangle(*inner, fill="#111820", outline="#0a0d12")
        self._canvas.create_line(sx(left + 30), sy(top + 27), sx(right - 30), sy(top + 27), fill="#34495c")
        if speaker:
            plate = (
                left + NAME_PLATE[0],
                top + NAME_PLATE[1],
                left + NAME_PLATE[2],
                top + NAME_PLATE[3],
            )
            self._canvas.create_rectangle(
                sx(plate[0] + 4),
                sy(plate[1] + 4),
                sx(plate[2] + 4),
                sy(plate[3] + 4),
                fill="#050608",
                outline="",
            )
            self._canvas.create_rectangle(
                sx(plate[0]),
                sy(plate[1]),
                sx(plate[2]),
                sy(plate[3]),
                fill="#23170e",
                outline="#f6d992",
                width=max(1, int(2 * scale)),
            )
            self._canvas.create_text(
                sx(plate[0] + 16),
                sy(plate[1] + 19),
                text=speaker,
                fill="#fff6d6",
                anchor="w",
                font=("Segoe UI", max(8, int(14 * scale)), "bold"),
            )
        self._canvas.create_text(
            sx(left + TEXT_INSET[0]),
            sy(top + TEXT_INSET[1]),
            text=text,
            fill="#f8f3dc",
            anchor="nw",
            width=max(20, int((right - left - TEXT_INSET[0] * 2) * scale)),
            font=("Segoe UI", max(10, int(18 * scale))),
        )

    def _draw_placeholder_background(self, sx, sy, scale: float, name: str | None) -> None:
        self._canvas.create_rectangle(sx(0), sy(0), sx(640), sy(480), fill="#2d3642", outline="")
        self._canvas.create_rectangle(sx(0), sy(260), sx(640), sy(480), fill="#222a32", outline="")
        self._canvas.create_text(
            sx(320),
            sy(170),
            text=name or "No background",
            fill="#d6dee8",
            font=("Segoe UI", max(10, int(16 * scale)), "bold"),
        )

    def _draw_portrait_placeholder(self, x: float, y: float, scale: float, name: str, expression: str | None) -> None:
        w, h = 128 * scale, 156 * scale
        self._canvas.create_rectangle(x - w / 2, y - h, x + w / 2, y, fill="#384657", outline="#e6edf3")
        self._canvas.create_oval(x - 30 * scale, y - 132 * scale, x + 30 * scale, y - 72 * scale, fill="#56677c")
        self._canvas.create_text(
            x,
            y - 22 * scale,
            text=f"{name}{' ' + expression if expression else ''}",
            fill="#f8fafc",
            font=("Segoe UI", max(7, int(10 * scale)), "bold"),
            width=max(40, int(w - 10)),
        )


class _ConversationAssetLoader:
    def __init__(self, extracted_dir: Path):
        self._files_dir = _resolve_files_dir(extracted_dir)
        self._background_by_key = self._index_backgrounds()
        self._portrait_files = self._index_portraits()
        self._face_records = self._load_face_records()
        self._background_cache: dict[str, Image.Image | None] = {}
        self._portrait_cache: dict[str, portrait_anim.PortraitAsset | None] = {}
        self.warning = "" if self._face_records else "No face/facedata.bin data; using alpha-hole face placement."

    def background(self, key: str | None) -> Image.Image | None:
        if not key:
            return None
        if key not in self._background_cache:
            path = self._background_by_key.get(key) or self._background_by_key.get(_normalize_key(key))
            self._background_cache[key] = self._read_tpl_first_image(path) if path is not None else None
        return self._background_cache[key]

    def portrait(self, name: str) -> portrait_anim.PortraitAsset | None:
        if name not in self._portrait_cache:
            path = self._resolve_portrait_path(name)
            fid = self._portrait_name_to_fid(name)
            self._portrait_cache[name] = self._read_portrait_asset(path, fid) if path is not None else None
        return self._portrait_cache[name]

    def _index_backgrounds(self) -> dict[str, Path]:
        out: dict[str, Path] = {}
        background_dir = self._files_dir / "s"
        rect_path = background_dir / "rect.bin"
        if rect_path.exists():
            try:
                for entry in rect.read_rects_path(rect_path):
                    keys = {
                        entry.name.decode("shift-jis", errors="replace"),
                        entry.resource_id.decode("shift-jis", errors="replace"),
                    }
                    for image in entry.images:
                        file_name = image.file_name.decode("ascii", errors="replace").replace("\\", "/")
                        path = self._files_dir.joinpath(*file_name.split("/"))
                        if not path.exists():
                            path = background_dir / Path(file_name).name
                        if path.exists():
                            for key in keys | {path.name, path.stem}:
                                out.setdefault(key, path)
                                out.setdefault(_normalize_key(key), path)
            except Exception:  # noqa: BLE001 - preview falls back to placeholders
                pass
        if background_dir.exists():
            for path in background_dir.iterdir():
                if path.is_file() and path.name != "rect.bin":
                    out.setdefault(path.name, path)
                    out.setdefault(path.stem, path)
                    out.setdefault(_normalize_key(path.stem), path)
        return out

    def _index_portraits(self) -> dict[str, Path]:
        face_dirs = [self._files_dir / "Face"]
        face_dirs.extend(path for path in self._files_dir.rglob("Face") if path.is_dir())
        out: dict[str, Path] = {}
        for face_dir in face_dirs:
            if not face_dir.exists():
                continue
            for path in face_dir.glob("*.cms"):
                if not path.is_file():
                    continue
                key = _normalize_key(path.stem)
                out.setdefault(key, path)
                out.setdefault(f"FID_{key}", path)
                if key.startswith("FID_"):
                    out.setdefault(key[4:], path)
                if key.startswith("L_"):
                    out.setdefault(key[2:], path)
        if not out:
            return {}
        return out

    def _load_face_records(self) -> dict[str, face_data.FaceDataRecord]:
        system_path = self._files_dir / "system.cmp"
        if not system_path.exists():
            return {}
        try:
            return face_data.read_face_data_from_system_cmp(system_path)
        except Exception:  # noqa: BLE001
            return {}

    def _resolve_portrait_path(self, name: str) -> Path | None:
        cleaned = _normalize_key(name)
        candidates = [cleaned, f"FID_{cleaned}"]
        if cleaned.startswith("FID_"):
            candidates.append(cleaned[4:])
        if cleaned.startswith("PID_") or cleaned.startswith("MPID_"):
            candidates.append(cleaned.split("_", 1)[1])
            candidates.append(f"FID_{cleaned.split('_', 1)[1]}")
        if cleaned.startswith("L_"):
            candidates.append(cleaned[2:])
        candidates.append(f"L_{cleaned}")
        candidates.append(f"FID_L_{cleaned}")
        for candidate in candidates:
            path = self._portrait_files.get(candidate)
            if path is not None:
                return path
        return None

    def _portrait_name_to_fid(self, name: str) -> str:
        cleaned = _normalize_key(name)
        if cleaned.startswith("FID_"):
            return cleaned
        return f"FID_{cleaned}"

    def _read_portrait_asset(self, path: Path, fid: str) -> portrait_anim.PortraitAsset | None:
        images: list[Image.Image]
        try:
            images = tpl.read_tpl_images(io.BytesIO(lz10.decompress(path.read_bytes())))
        except Exception:  # noqa: BLE001
            try:
                images = tpl.read_tpl_images_path(path)
            except Exception:  # noqa: BLE001
                return None
        if not images:
            return None
        base = images[0].convert("RGBA")
        parts = tuple(image.convert("RGBA") for image in images[1:] if image.width <= 64 and image.height <= 64)
        return portrait_anim.PortraitAsset(base=base, parts=parts, face_data=self._face_records.get(fid))

    def _read_tpl_first_image(self, path: Path) -> Image.Image | None:
        try:
            images = tpl.read_tpl_images_path(path)
        except Exception:  # noqa: BLE001
            return None
        return images[0].convert("RGBA") if images else None


def _normalize_key(value: str) -> str:
    return value.strip().upper()


def _resolve_files_dir(extracted_dir: Path) -> Path:
    direct = extracted_dir / "files"
    if direct.exists():
        return direct
    matches = [path for path in extracted_dir.rglob("files") if path.is_dir()]
    return matches[0] if matches else direct


def _cover_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, _resample())
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _resample():
    return getattr(Image, "Resampling", Image).LANCZOS


def _pixel_resample():
    return getattr(Image, "Resampling", Image).NEAREST
