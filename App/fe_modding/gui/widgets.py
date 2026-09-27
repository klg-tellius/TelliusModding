"""Building blocks of the workspace pages: scrollable frames, clickable cards
and a reflowing card grid, chips, links, a portrait thumbnail cache and the
tile browser the Game Data tabs pick their records with.

Cards are classic ``tk`` frames rather than ttk so they can change colour on
hover; they repaint themselves through :func:`theme.on_change`.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from . import theme


# -- scrolling ------------------------------------------------------------------

class ScrollFrame(ttk.Frame):
    """A vertically scrolling area; put content in ``self.body``."""

    def __init__(self, parent: tk.Misc, *, padding=(24, 16)):
        super().__init__(parent, style="Page.TFrame")
        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=theme.color("bg"))
        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self._canvas, style="Page.TFrame", padding=padding)
        self._window = self._canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(self._window, width=e.width))
        self._canvas._scroll_frame = self
        theme.on_change(self, lambda: self._canvas.configure(background=theme.color("bg")))
        _install_wheel(self)

    def scroll_by_wheel(self, delta: int) -> None:
        if self._canvas.yview() != (0.0, 1.0):
            self._canvas.yview_scroll(int(-delta / 120), "units")

    def scroll_top(self) -> None:
        self._canvas.yview_moveto(0)


def _install_wheel(widget: tk.Misc) -> None:
    """One wheel handler for the whole window: it scrolls the ScrollFrame
    under the pointer (no per-frame enter/leave rebinding)."""
    root = widget.winfo_toplevel()
    if getattr(root, "_scroll_wheel_installed", False):
        return
    root._scroll_wheel_installed = True

    def on_wheel(event):
        target = event.widget
        if isinstance(target, str) or isinstance(target, (tk.Listbox, tk.Text, ttk.Treeview)):
            return  # widgets that scroll themselves keep the wheel
        while target is not None:
            frame = getattr(target, "_scroll_frame", None)
            if frame is not None:
                frame.scroll_by_wheel(event.delta)
                return
            if isinstance(target, tk.Canvas):
                return  # a drawing canvas (map, model preview) handles its own wheel
            target = target.master

    root.bind_all("<MouseWheel>", on_wheel, add="+")


def pointer_inside(widget: tk.Misc) -> bool:
    """Whether the mouse pointer is over ``widget`` or one of its children."""
    try:
        x, y = widget.winfo_pointerxy()
        under = widget.winfo_containing(x, y)
    except (tk.TclError, KeyError):
        return False
    path = str(widget)
    return under is not None and (str(under) == path or str(under).startswith(path + "."))


def track_hover(widget: tk.Misc, on_change: Callable[[bool], None]) -> None:
    """Call ``on_change(True/False)`` when the pointer enters or leaves
    ``widget`` (children included). Moving between children never flickers:
    an Enter starts a short poll that reports the leave once the pointer is
    really outside, and nothing repaints while the state stays the same."""
    state = {"hover": False, "job": None}

    def check():
        state["job"] = None
        try:
            inside = pointer_inside(widget)
            if inside != state["hover"]:
                state["hover"] = inside
                on_change(inside)
            if inside:
                state["job"] = widget.after(80, check)
        except tk.TclError:
            pass

    def on_enter(_event):
        if state["job"] is None:
            check()

    def bind(w):
        w.bind("<Enter>", on_enter, add="+")
        for child in w.winfo_children():
            bind(child)

    bind(widget)


# -- small pieces -----------------------------------------------------------------

def section_header(parent: tk.Misc, text: str, detail: str = "") -> ttk.Frame:
    row = ttk.Frame(parent, style="Page.TFrame")
    ttk.Label(row, text=text, style="Subtitle.TLabel").pack(side="left")
    if detail:
        ttk.Label(row, text=detail, style="Muted.TLabel").pack(side="left", padx=(10, 0), pady=(4, 0))
    return row


class Chip(tk.Label):
    """A small rounded-looking tag in a token colour."""

    def __init__(self, parent: tk.Misc, text: str, token: str = "chip_generic", fg_token: str = "fg"):
        super().__init__(parent, text=text, font=theme.font("caption"), padx=7, pady=1)
        self._token, self._fg_token = token, fg_token
        self._paint()
        theme.on_change(self, self._paint)

    def _paint(self) -> None:
        self.configure(background=theme.color(self._token), foreground=theme.color(self._fg_token))


class Link(tk.Label):
    """Clickable text in the accent colour."""

    def __init__(self, parent: tk.Misc, text: str, command: Callable[[], None], *, bg_token: str = "bg",
                 font_role: str = "body"):
        super().__init__(parent, text=text, cursor="hand2", font=theme.font(font_role), padx=0, pady=0)
        self._bg_token = bg_token
        self.bind("<Button-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self.configure(font=theme.font(font_role) + ("underline",)))
        self.bind("<Leave>", lambda e: self.configure(font=theme.font(font_role)))
        self._paint()
        theme.on_change(self, self._paint)

    def _paint(self) -> None:
        self.configure(background=theme.color(self._bg_token), foreground=theme.color("accent"))


# -- cards --------------------------------------------------------------------------

class Card(tk.Frame):
    """A clickable tile: optional image on the left, a title, a subtitle, a
    caption and a row of chips. ``on_click`` runs on a left click."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        subtitle: str = "",
        caption: str = "",
        chips: tuple = (),
        on_click: Optional[Callable[[], None]] = None,
        width: int = 240,
        image_box: Optional[tuple[int, int]] = None,
        icon: str = "",
    ):
        # no width/height options: a tk.Frame re-requests them on every
        # configure (each hover repaint), which briefly resizes the card
        super().__init__(parent, highlightthickness=1, borderwidth=0, cursor="hand2" if on_click else "")
        self._on_click = on_click
        self._hover = False
        self._painted: list[tuple[tk.Widget, str]] = []  # (widget, fg token); chips paint themselves
        inner = tk.Frame(self, borderwidth=0)
        inner.pack(fill="both", expand=True, padx=12, pady=10)
        self._painted.append((inner, ""))
        self._image_label = None
        if image_box is not None:
            self._image_label = tk.Label(inner, width=image_box[0], height=image_box[1], borderwidth=0)
            self._image_label.pack(side="left", padx=(0, 12))
            self._painted.append((self._image_label, ""))
        elif icon:
            icon_label = tk.Label(inner, text=icon, font=(theme.font("title")[0], 18), width=2)
            icon_label.pack(side="left", padx=(0, 10))
            self._painted.append((icon_label, "accent"))
        text = tk.Frame(inner, borderwidth=0)
        text.pack(side="left", fill="both", expand=True)
        self._painted.append((text, ""))
        # The labels ask for no width of their own (width=1): the grid column
        # decides how wide the card is and they wrap to it. If their wrapped
        # text set the width instead, rewrapping would resize the card and
        # the two would chase each other forever.
        self._labels: list[tk.Label] = []
        wrap = max(60, width - 40 - (60 if image_box else 0) - (44 if icon else 0))
        for value, role, token in ((title, "strong", "fg"), (subtitle, "body", "muted"), (caption, "caption", "faint")):
            if value:
                label = tk.Label(text, text=value, font=theme.font(role), anchor="w", justify="left",
                                 width=1, wraplength=wrap)
                label.pack(fill="x")
                self._painted.append((label, token))
                self._labels.append(label)
        self._wrap = 0
        text.bind("<Configure>", self._on_text_resized)
        if chips:
            row = tk.Frame(text, borderwidth=0)
            row.pack(fill="x", pady=(6, 0))
            self._painted.append((row, ""))
            for chip in chips:
                label, token = chip if isinstance(chip, tuple) else (chip, "chip_generic")
                Chip(row, label, token).pack(side="left", padx=(0, 4))
        self._paint()
        theme.on_change(self, self._paint)
        if on_click is not None:
            self._bind_click(self)
            track_hover(self, self._set_hover)

    def _bind_click(self, widget: tk.Misc) -> None:
        widget.bind("<Button-1>", lambda e: self._on_click(), add="+")
        for child in widget.winfo_children():
            self._bind_click(child)

    def _on_text_resized(self, event) -> None:
        wrap = max(60, event.width - 2)
        if wrap != self._wrap:
            self._wrap = wrap
            for label in self._labels:
                label.configure(wraplength=wrap)

    def _set_hover(self, hover: bool) -> None:
        if hover != self._hover:
            self._hover = hover
            self._paint()

    def _paint(self) -> None:
        bg = theme.color("surface_hover" if self._hover and self._on_click else "surface")
        border = theme.color("accent" if self._hover and self._on_click else "border")
        self.configure(background=bg, highlightbackground=border, highlightcolor=border)
        for widget, token in self._painted:
            widget.configure(background=bg)
            if token:
                widget.configure(foreground=theme.color(token))

    def set_image(self, photo) -> None:
        if self._image_label is not None:
            self._image_label.configure(image=photo, width=0, height=0)
            self._image_label.image = photo


class CardGrid(ttk.Frame):
    """Cards laid out in as many columns as fit; :meth:`filter` shows a subset
    without rebuilding them."""

    def __init__(self, parent: tk.Misc, *, card_width: int = 240, gap: int = 12):
        super().__init__(parent, style="Page.TFrame")
        self._card_width, self._gap = card_width, gap
        self._cards: list[tuple[object, tk.Widget]] = []
        self._visible: list[tk.Widget] = []
        self._columns = 0
        self.bind("<Configure>", lambda e: self._reflow())

    @property
    def card_width(self) -> int:
        return self._card_width

    def clear(self) -> None:
        for _key, card in self._cards:
            card.destroy()
        self._cards, self._visible, self._columns = [], [], 0

    def add(self, key, card: tk.Widget) -> None:
        self._cards.append((key, card))
        self._visible.append(card)

    def filter(self, predicate: Callable[[object], bool]) -> int:
        for card in self._visible:
            card.grid_forget()
        self._visible = [card for key, card in self._cards if predicate(key)]
        self._columns = 0
        self._reflow()
        return len(self._visible)

    def done(self) -> None:
        self._columns = 0
        self._reflow()

    def _reflow(self) -> None:
        width = max(self.winfo_width(), self._card_width)
        columns = max(1, (width + self._gap) // (self._card_width + self._gap))
        if columns == self._columns:
            return
        self._columns = columns
        for i, card in enumerate(self._visible):
            card.grid(row=i // columns, column=i % columns, sticky="nsew",
                      padx=(0, self._gap), pady=(0, self._gap))
        for c in range(max(columns, self.grid_size()[0])):
            self.grid_columnconfigure(c, weight=1 if c < columns else 0, uniform="card" if c < columns else "",
                                      minsize=self._card_width if c < columns else 0)


# -- portraits ------------------------------------------------------------------------

class PortraitCache:
    """Face thumbnails (composed like the game draws them) loaded in a
    background thread; ``request(fid, size, callback)`` calls back on the UI
    thread with a PhotoImage, or never when the face can't be drawn."""

    def __init__(self, root: tk.Misc, extracted_dir: Path):
        self._root = root
        self._extracted = extracted_dir
        self._assets = None
        self._assets_failed = False
        self._photos: dict[tuple[str, int], ImageTk.PhotoImage] = {}
        self._pending: dict[tuple[str, int], list] = {}
        self._jobs: "queue.Queue[tuple[str, int]]" = queue.Queue()
        self._results: "queue.Queue[tuple[tuple[str, int], Optional[Image.Image]]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def request(self, fid: Optional[str], size: int, callback: Callable) -> None:
        if not fid:
            return
        key = (fid, size)
        if key in self._photos:
            callback(self._photos[key])
            return
        if key in self._pending:
            self._pending[key].append(callback)
            return
        self._pending[key] = [callback]
        self._jobs.put(key)
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._work, daemon=True)
            self._thread.start()
            self._root.after(60, self._poll)

    def _work(self) -> None:
        while not self._closed:
            try:
                key = self._jobs.get(timeout=0.5)
            except queue.Empty:
                return
            self._results.put((key, self._render(*key)))

    def _render(self, fid: str, size: int) -> Optional[Image.Image]:
        if self._assets is None and not self._assets_failed:
            try:
                from ..formats.fe9_conversation_assets import ConversationAssets
                self._assets = ConversationAssets(self._extracted)
            except Exception:  # noqa: BLE001 - no portraits, no thumbnails
                self._assets_failed = True
        if self._assets is None:
            return None
        try:
            face = self._assets.face(fid)
            image = face.compose()
        except Exception:  # noqa: BLE001
            return None
        return face_thumbnail(image, face.record, size)

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            while True:
                key, image = self._results.get_nowait()
                callbacks = self._pending.pop(key, [])
                if image is None:
                    continue
                photo = ImageTk.PhotoImage(image)
                self._photos[key] = photo
                for callback in callbacks:
                    try:
                        callback(photo)
                    except tk.TclError:
                        pass
        except queue.Empty:
            pass
        if self._pending or (self._thread is not None and self._thread.is_alive()):
            self._root.after(60, self._poll)


def face_thumbnail(image: Image.Image, record, size: int) -> Image.Image:
    """A square crop around the face: centred on the mouth when the portrait
    has one, else on the top of the drawn area."""
    image = image.convert("RGBA")
    bbox = image.getbbox() or (0, 0, image.width, image.height)
    side = min(96, image.height, image.width)
    if record.flags & 2 and record.mouth[0] >= 0:
        cx = record.mouth[0] + 12
        top = record.mouth[1] - int(side * 0.66)
    else:
        cx = (bbox[0] + bbox[2]) // 2
        top = bbox[1]
    left = min(max(0, cx - side // 2), image.width - side)
    top = min(max(0, top), image.height - side)
    crop = image.crop((left, top, left + side, top + side))
    return crop.resize((size, size), Image.LANCZOS)


# -- record browser ------------------------------------------------------------------

class TileBrowser(ttk.Frame):
    """Chooses one record of a long table from a grid of tiles, like the
    Characters page: a search box that keeps the tiles matching every typed
    word, category toggles when the entries have categories, and a picture
    on each tile when the host has one. Clicking a tile opens the record:
    the tiles make way for :attr:`detail`, where the host puts the record's
    form, under a bar with **‹ All …**, previous/next and the position.

    The host puts its always-available buttons in :attr:`actions` and those
    that act on the open record in :attr:`record_actions`.
    ``on_pick(index)`` runs when a record is opened; :meth:`select` does it
    from code (``notify=False`` only moves the current record)."""

    ALL = "All"

    def __init__(self, parent: tk.Misc, noun: str, on_pick: Callable[[int], None], *, tile_width: int = 230,
                 image_box: tuple[int, int] = (4, 2), style: str = "Page.TFrame"):
        super().__init__(parent, style=style)
        self._noun = noun
        self._on_pick = on_pick
        self._tile_width = tile_width
        self._image_box = image_box
        self._style = style
        self._labels: list[str] = []
        self._subtitles: list[str] = []
        self._haystacks: list[str] = []
        self._categories: list[str] = []
        self._category_names: list[str] = []
        self._image: Optional[Callable[[int, Callable], None]] = None
        self._signature = None
        self._stale = True
        self._requested: set[int] = set()
        self._cards: dict[int, Card] = {}
        self._shown: list[int] = []
        self.current: Optional[int] = None
        self._mode = "grid"

        self.toolbar = ttk.Frame(self, style=style, padding=(12, 10, 12, 4))
        self.toolbar.pack(fill="x")
        self._nav = ttk.Frame(self.toolbar, style=style)
        ttk.Button(self._nav, text=f"‹ All {noun}", command=self.show_grid).pack(side="left", padx=(0, 10))
        ttk.Button(self._nav, text="◀", width=3, command=lambda: self.step(-1)).pack(side="left")
        ttk.Button(self._nav, text="▶", width=3, command=lambda: self.step(1)).pack(side="left", padx=(4, 0))
        self._title = ttk.Label(self._nav, text="", style="Strong.TLabel")
        self._title.pack(side="left", padx=(12, 0))
        self._position = ttk.Label(self._nav, text="", style="Muted.TLabel")
        self._position.pack(side="left", padx=(10, 0))
        self.actions = ttk.Frame(self.toolbar, style=style)
        self.actions.pack(side="left")
        self.record_actions = ttk.Frame(self.toolbar, style=style)
        self._search = ttk.Frame(self.toolbar, style=style)
        self._search.pack(side="right")
        self._count = ttk.Label(self._search, text="", style="Muted.TLabel")
        self._count.pack(side="right", padx=(10, 0))
        self._query = tk.StringVar()
        entry = ttk.Entry(self._search, textvariable=self._query, width=30)
        entry.pack(side="right")
        entry.bind("<Return>", lambda e: self._shown and self.select(self._shown[0]))
        entry.bind("<Escape>", lambda e: self._query.set(""))
        self._entry = entry
        ttk.Label(self._search, text="Search name or ID", style="Muted.TLabel").pack(side="right", padx=(0, 8))
        self._query.trace_add("write", lambda *_: self._filter_changed())

        self._chips = ttk.Frame(self, style=style, padding=(12, 0, 12, 6))
        self._category = tk.StringVar(value=self.ALL)
        self._scroll = ScrollFrame(self, padding=(12, 4, 12, 16))
        self._grid = CardGrid(self._scroll.body, card_width=tile_width, gap=10)
        self._grid.pack(fill="x")
        self.detail = ttk.Frame(self, style=style)
        self._layout()

    # -- entries ---------------------------------------------------------------------
    def set_entries(self, labels: list[str], haystacks: Optional[list[str]] = None,
                    categories: Optional[list[str]] = None, category_order: Optional[list[str]] = None, *,
                    image: Optional[Callable[[int, Callable], None]] = None,
                    image_keys: Optional[list] = None) -> None:
        """The entries, in table order. A label ``"Name  ·  ID"`` is shown
        as the tile's title and subtitle; ``haystacks`` is extra searchable
        text per entry, ``categories`` one category name per entry (listed
        in ``category_order``, then in order of appearance).
        ``image(index, callback)`` calls ``callback(photo)`` with the
        entry's picture (at once or later); ``image_keys`` names each
        picture, so the tiles are only redrawn when one changes."""
        self._labels = list(labels)
        self._subtitles = [label.split("  ·  ", 1)[1].replace("  ·  ", " · ") if "  ·  " in label else ""
                           for label in self._labels]
        self._categories = list(categories) if categories else []
        self._haystacks = [f"{label} {extra} {category}".casefold()
                           for label, extra, category in zip(labels, haystacks or [""] * len(labels),
                                                             self._categories or [""] * len(labels))]
        self._image = image
        present = list(dict.fromkeys(self._categories))
        names = [c for c in (category_order or []) if c in present]
        names += [c for c in present if c not in names]
        if names != self._category_names:
            self._category_names = names
            self._build_chips()
        if self.current is not None and self.current >= len(labels):
            self.current = None
        signature = (tuple(self._labels), tuple(self._categories), image is not None,
                     tuple(image_keys) if image_keys is not None else None)
        if signature != self._signature:
            self._signature = signature
            self._stale = True
        if self._stale and self._mode == "grid":
            self._rebuild()
        else:
            self._filter()
        self._show_current()

    @property
    def labels(self) -> list[str]:
        return list(self._labels)

    def refresh_images(self) -> None:
        """Ask for every picture again (the host can draw more of them now)."""
        self._requested.clear()
        self._request_images()

    # -- modes -----------------------------------------------------------------------------
    def show_grid(self) -> None:
        if self._mode != "grid":
            self._mode = "grid"
            self._layout()
            if self._stale:
                self._rebuild()
            else:
                self._filter()
            self._entry.focus_set()

    def _show_detail(self) -> None:
        if self._mode != "detail":
            self._mode = "detail"
            self._layout()

    def _layout(self) -> None:
        for widget in (self._nav, self.record_actions, self._search, self._chips, self._scroll, self.detail):
            widget.pack_forget()
        if self._mode == "detail":
            self._nav.pack(side="left", before=self.actions)
            self.record_actions.pack(side="left", after=self.actions)
            self.detail.pack(fill="both", expand=True)
        else:
            self._search.pack(side="right")
            if self._category_names:
                self._chips.pack(fill="x")
            self._scroll.pack(fill="both", expand=True)

    def _build_chips(self) -> None:
        for child in self._chips.winfo_children():
            child.destroy()
        if self._category.get() not in self._category_names:
            self._category.set(self.ALL)
        for value in [self.ALL] + self._category_names:
            ttk.Radiobutton(self._chips, text=value, value=value, variable=self._category,
                            style="Toggle.TButton", command=self._filter_changed).pack(side="left", padx=(0, 6))
        self._layout()

    # -- tiles ------------------------------------------------------------------------------
    def _rebuild(self) -> None:
        self._stale = False
        self._grid.clear()
        self._cards = {}
        self._requested.clear()
        for i, label in enumerate(self._labels):
            title = label.split("  ·  ", 1)[0]
            card = Card(self._grid, title=title or label, subtitle=self._subtitles[i],
                        caption=self._categories[i] if self._categories else "", width=self._tile_width,
                        image_box=self._image_box if self._image is not None else None,
                        on_click=lambda i=i: self.select(i))
            self._grid.add(i, card)
            self._cards[i] = card
        self._grid.done()
        self._filter()

    def _filter_changed(self) -> None:
        self._filter()
        self._scroll.scroll_top()

    def _filter(self) -> None:
        words = self._query.get().casefold().split()
        category = self._category.get()
        self._shown = [i for i in range(len(self._labels))
                       if (words or category == self.ALL or not self._categories or self._categories[i] == category)
                       and all(w in self._haystacks[i] for w in words)]
        shown = set(self._shown)
        if not self._stale and self._mode == "grid":
            self._grid.filter(lambda i: i in shown)
            self._request_images()
        where = f" in {category}" if self._categories and category != self.ALL and not words else ""
        self._count.configure(text=f"{len(self._shown)} of {len(self._labels)} {self._noun}{where}"
                              + ("  ·  Enter opens the first" if words and self._shown else ""))

    def _request_images(self) -> None:
        if self._image is None or self._stale or self._mode != "grid":
            return
        for i in self._shown:
            if i in self._requested or i not in self._cards:
                continue
            self._requested.add(i)
            card = self._cards[i]
            try:
                self._image(i, lambda photo, card=card: card.winfo_exists() and card.set_image(photo))
            except Exception:  # noqa: BLE001 - pictures are a convenience
                pass

    # -- the current record ----------------------------------------------------------------------
    def select(self, index: Optional[int], notify: bool = True) -> None:
        if index is None or not 0 <= index < len(self._labels):
            return
        self.current = index
        self._show_current()
        if notify:
            self._show_detail()
            self._on_pick(index)

    def step(self, delta: int) -> None:
        order = self._shown if self.current in self._shown else list(range(len(self._labels)))
        if not order:
            return
        if self.current in order:
            position = order.index(self.current) + delta
        else:
            position = 0 if delta > 0 else -1
        self.select(order[position % len(order)])

    def focus_search(self) -> None:
        self.show_grid()
        self._entry.focus_set()
        self._entry.select_range(0, "end")

    def _show_current(self) -> None:
        if self.current is None:
            self._title.configure(text="")
            self._position.configure(text="")
            return
        self._title.configure(text=self._labels[self.current])
        if self.current in self._shown and len(self._shown) != len(self._labels):
            text = f"{self._shown.index(self.current) + 1} of {len(self._shown)} shown"
        else:
            text = f"{self.current + 1} of {len(self._labels)}"
        self._position.configure(text=text)
