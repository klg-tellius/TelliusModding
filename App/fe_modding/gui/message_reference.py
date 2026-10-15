"""Shared support for message IDs selected by game-data dropdowns."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ..formats import fe10_message, message
from ..game_profile import profile_of

CREATE_MESSAGE = "＋ Create new message…"


def common_path(project) -> Path:
    folder = project.extracted_dir / "files" / "Mess"
    english = folder / "e_common.m"
    return english if profile_of(project).message_dialect == "fe10" and english.is_file() else folder / "common.m"


def display_id(raw: str) -> str:
    try:
        return raw.encode(message.ENCODING).decode("shift_jis")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def raw_id(shown: str) -> str:
    return shown.encode("shift_jis").decode(message.ENCODING)


def message_texts(project) -> dict[str, str]:
    path = common_path(project)
    if not path.is_file():
        return {}
    try:
        return {display_id(m.speaker): m.text for m in message.read_messages_path(path)}
    except (OSError, ValueError, IndexError):
        return {}


def preview(text: str, fe10: bool = False) -> str:
    if fe10:
        text = fe10_message.plain_text(text)
    return " ".join(text.split())[:80]


def suggested_id(prefix: str, field: str, used: set[str]) -> str:
    stem = "".join(c if c.isalnum() and c.isascii() else "_" for c in field.upper()).strip("_")
    base = f"{prefix}{stem or 'NEW'}"
    candidate, suffix = base, 2
    while candidate in used:
        candidate, suffix = f"{base}_{suffix}", suffix + 1
    return candidate


def create_message(project, name: str, text: str) -> None:
    """Write a common message, preserving the extracted original and text order."""
    path = common_path(project)
    if not path.is_file():
        raise ValueError(f"{path.name} is missing. Extract the message files first.")
    name = name.strip()
    if not name or "|" in name or "\x00" in name:
        raise ValueError("The message ID cannot be empty or contain '|' or NUL.")
    if not text.strip() or "\x00" in text:
        raise ValueError("Enter message text without NUL characters.")
    try:
        encoded_name = raw_id(name)
        fe10 = profile_of(project).message_dialect == "fe10"
        encoded_text = fe10_message.to_raw(text) if fe10 else text
        encoded_text.encode(message.ENCODING)
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"The ID or text cannot be encoded for this game: {exc}") from exc
    messages = message.read_messages_path(path)
    buckets = profile_of(project).name_hash_buckets
    new_hash = message.engine_name_hash(encoded_name, buckets)
    for existing in messages:
        if display_id(existing.speaker) == name:
            raise ValueError(f"{name} already exists in {path.name}.")
        if message.engine_name_hash(existing.speaker, buckets) == new_hash:
            raise ValueError(f"{name} conflicts with {display_id(existing.speaker)} in the game's ID lookup.")
    order = message.read_text_order_path(path)
    messages.append(message.Message(encoded_name, encoded_text))
    messages.sort(key=lambda m: m.speaker.encode(message.ENCODING))
    project.write_keeping_original(path, message.write_messages(messages, order))


class NewMessageDialog(tk.Toplevel):
    """Collect the ID and visible text; cancellation changes nothing."""

    def __init__(self, parent, initial_id: str):
        super().__init__(parent)
        self.title("Create message")
        self.transient(parent.winfo_toplevel())
        self.result: tuple[str, str] | None = None
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Message ID").grid(row=0, column=0, sticky="w")
        self._name = tk.StringVar(value=initial_id)
        entry = ttk.Entry(body, textvariable=self._name, width=52)
        entry.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        ttk.Label(body, text="Message text").grid(row=2, column=0, sticky="w")
        self._text = tk.Text(body, width=58, height=7, wrap="word")
        self._text.grid(row=3, column=0, sticky="nsew", pady=(2, 10))
        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, sticky="e")
        ttk.Button(buttons, text="Create and assign", command=self._accept).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        entry.focus_set()
        entry.select_range(0, "end")
        self.grab_set()
        self.wait_window()

    def _accept(self) -> None:
        self.result = (self._name.get().strip(), self._text.get("1.0", "end-1c"))
        self.destroy()
