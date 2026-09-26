"""The app's look: the Sun Valley ttk theme (``sv-ttk``, Windows 11 style)
in dark or light, plus the colour tokens and named styles the workspace uses.

ttk widgets follow the theme on their own. Classic ``tk`` widgets (Listbox,
Text, Canvas, the workspace's custom cards) do not: sv-ttk recolours the ones
still on the default palette when the theme changes, and widgets drawn in a
token colour register a callback with :func:`on_change` to repaint.

Without ``sv-ttk`` installed the app falls back to the stock ``clam`` theme
with the same tokens, so it still runs.
"""

from __future__ import annotations

import tkinter as tk
import weakref
from tkinter import font as tkfont
from tkinter import ttk

from .. import config

try:
    import sv_ttk
except ImportError:  # pragma: no cover - optional dependency
    sv_ttk = None

PALETTES = {
    "dark": {
        "bg": "#1c1c1c",
        "surface": "#2b2b2b",
        "surface_hover": "#353535",
        "surface_alt": "#232323",
        "border": "#3d3d3d",
        "fg": "#fafafa",
        "muted": "#a0a0a0",
        "faint": "#6f6f6f",
        "accent": "#57c8ff",
        "accent_bg": "#1d3a4d",
        "nav_active": "#3a3a3a",
        "field": "#1f1f1f",
        "code_bg": "#1e1e1e",
        "ok": "#6ccb5f",
        "warn": "#fce100",
        "danger": "#ff99a4",
        "chip_playable": "#2e4d2a",
        "chip_named": "#4d3d1f",
        "chip_generic": "#333333",
        "highlight": "#5c4b00",
    },
    "light": {
        "bg": "#fafafa",
        "surface": "#ffffff",
        "surface_hover": "#f0f6fc",
        "surface_alt": "#fafafa",
        "border": "#dcdcdc",
        "fg": "#1c1c1c",
        "muted": "#5f5f5f",
        "faint": "#9a9a9a",
        "accent": "#005fb8",
        "accent_bg": "#dcebf8",
        "nav_active": "#e2e2e2",
        "field": "#ffffff",
        "code_bg": "#fafafa",
        "ok": "#0f7b0f",
        "warn": "#9d5d00",
        "danger": "#c42b1c",
        "chip_playable": "#dff6dd",
        "chip_named": "#fff4ce",
        "chip_generic": "#ebebeb",
        "highlight": "#ffe18a",
    },
}

_mode = "dark"
_listeners: "weakref.WeakKeyDictionary[tk.Misc, list]" = weakref.WeakKeyDictionary()


def mode() -> str:
    return _mode


def color(name: str) -> str:
    return PALETTES[_mode][name]


def font(role: str) -> tuple:
    """Fonts by role: title, subtitle, heading, body, strong, caption, mono."""
    family = "Segoe UI Variable Text" if "Segoe UI Variable Text" in _families() else "Segoe UI"
    display = "Segoe UI Variable Display" if "Segoe UI Variable Display" in _families() else "Segoe UI"
    return {
        "title": (display, 20, "bold"),
        "subtitle": (display, 14, "bold"),
        "heading": (family, 11, "bold"),
        "body": (family, 10),
        "strong": (family, 10, "bold"),
        "caption": (family, 9),
        "brand": (display, 12, "bold"),
    }[role]


_font_families: set | None = None


def _families() -> set:
    global _font_families
    if _font_families is None:
        try:
            _font_families = set(tkfont.families())
        except tk.TclError:
            _font_families = set()
    return _font_families


def setup(root: tk.Tk) -> None:
    """Apply the saved theme (dark by default). Call once, before building widgets."""
    apply(root, config.load_setting("theme", "dark"))


def apply(root: tk.Tk, new_mode: str) -> None:
    global _mode
    _mode = new_mode if new_mode in PALETTES else "dark"
    if sv_ttk is not None:
        sv_ttk.set_theme(_mode, root)
    else:
        ttk.Style(root).theme_use("clam")
        root.tk_setPalette(background=color("bg"), foreground=color("fg"))
    _configure_styles(root)
    root.configure(background=color("bg"))
    root.option_add("*Listbox.background", color("field"))
    root.option_add("*Listbox.foreground", color("fg"))
    root.option_add("*Listbox.relief", "flat")
    root.option_add("*Listbox.highlightThickness", 1)
    root.option_add("*Listbox.highlightBackground", color("border"))
    root.option_add("*Text.background", color("field"))
    root.option_add("*Text.foreground", color("fg"))
    root.option_add("*Text.insertBackground", color("fg"))
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", color("border"))
    # repaint registered widgets once sv-ttk's own palette pass has run
    root.after_idle(_notify)


def set_mode(root: tk.Tk, new_mode: str) -> None:
    """Switch to ``new_mode`` ("dark" or "light") and remember it."""
    if new_mode != _mode:
        apply(root, new_mode)
    config.save_setting("theme", _mode)


def toggle(root: tk.Tk) -> None:
    set_mode(root, "light" if _mode == "dark" else "dark")


def on_change(widget: tk.Misc, callback) -> None:
    """Call ``callback()`` whenever the theme changes, while ``widget`` lives."""
    _listeners.setdefault(widget, []).append(callback)


def _notify() -> None:
    for widget, callbacks in list(_listeners.items()):
        try:
            if not widget.winfo_exists():
                continue
        except tk.TclError:
            continue
        for callback in callbacks:
            try:
                callback()
            except tk.TclError:
                pass


def _configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    bg, fg = color("bg"), color("fg")
    style.configure("Muted.TLabel", foreground=color("muted"))
    style.configure("Faint.TLabel", foreground=color("faint"))
    style.configure("Title.TLabel", font=font("title"))
    style.configure("Subtitle.TLabel", font=font("subtitle"))
    style.configure("Heading.TLabel", font=font("heading"))
    style.configure("Strong.TLabel", font=font("strong"))
    style.configure("Caption.TLabel", font=font("caption"), foreground=color("muted"))
    style.configure("Danger.TLabel", foreground=color("danger"))
    style.configure("Warn.TLabel", foreground=color("warn"))
    style.configure("Ok.TLabel", foreground=color("ok"))
    # surfaces (cards, bars) - plain frames in a token colour
    for name, token in (("Surface", "surface"), ("Bar", "surface_alt")):
        style.configure(f"{name}.TFrame", background=color(token))
        style.configure(f"{name}.TLabel", background=color(token), foreground=fg)
        style.configure(f"{name}Muted.TLabel", background=color(token), foreground=color("muted"))
        style.configure(f"{name}Caption.TLabel", background=color(token), foreground=color("muted"),
                        font=font("caption"))
        style.configure(f"{name}Heading.TLabel", background=color(token), foreground=fg, font=font("heading"))
        style.configure(f"{name}Title.TLabel", background=color(token), foreground=fg, font=font("title"))
        style.configure(f"{name}Subtitle.TLabel", background=color(token), foreground=fg, font=font("subtitle"))
        style.configure(f"{name}Warn.TLabel", background=color(token), foreground=color("warn"))
        style.configure(f"{name}.TCheckbutton", background=color(token))
        style.configure(f"{name}.TRadiobutton", background=color(token))
    style.configure("Page.TFrame", background=bg)
    style.configure("Treeview", rowheight=26)
