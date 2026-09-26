"""A small source-code editor widget for ``.fe9s`` event scripts: line
numbers, syntax highlighting, diagnostic underlines, and name completion.

Kept generic enough (a completion provider and a signature provider are
passed in) that nothing here knows about the game's catalogue."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Optional

from . import theme

KEYWORDS = (
    "def", "if", "elif", "else", "while", "do", "break", "continue", "return", "yield", "pass", "var", "global",
    "goto", "unless", "asm", "and", "or", "not", "True", "False", "None",
)
_TOKEN_PATTERNS = [
    ("comment", r"#[^\n]*"),
    ("string", r'"(?:[^"\\\n]|\\.)*"?'),
    ("decorator", r"^[ \t]*@[\w.]+"),
    ("keyword", r"\b(?:" + "|".join(KEYWORDS) + r")\b"),
    ("number", r"\b(?:0[xX][0-9a-fA-F]+|\d+)\b"),
    ("call", r"\b[A-Za-z_]\w*(?=\s*\()"),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{k}>{p})" for k, p in _TOKEN_PATTERNS), re.MULTILINE)
_WORD_BEFORE = re.compile(r"[A-Za-z_]\w*$")

COLORS = {
    "comment": "#6a737d",
    "string": "#a3551f",
    "decorator": "#6f42c1",
    "keyword": "#0b5cad",
    "number": "#098658",
    "call": "#1f6f43",
    "call_unknown": "#b31d28",
}
DARK_COLORS = {
    "comment": "#8b949e",
    "string": "#e6a26b",
    "decorator": "#c5a3ff",
    "keyword": "#6cb6ff",
    "number": "#7ee2b8",
    "call": "#8ddb8c",
    "call_unknown": "#ff8a8a",
}
# editor surface per theme: text, gutter, gutter numbers, cursor, error, warning, current function
SURFACES = {
    "light": ("#ffffff", "#f3f3f3", "#999999", "#000000", "#ffe3e3", "#fff4d6", "#f5f9ff"),
    "dark": ("#1e1e1e", "#252525", "#6f6f6f", "#fafafa", "#4a2326", "#463a1c", "#232a35"),
}


class CodeEditor(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        completions: Callable[[str], list[str]] = lambda prefix: [],
        signature: Callable[[str], Optional[str]] = lambda name: None,
        is_known_call: Callable[[str], bool] = lambda name: True,
        on_change: Callable[[], None] = lambda: None,
        on_status: Callable[[str], None] = lambda text: None,
    ):
        super().__init__(parent)
        self._completions = completions
        self._signature = signature
        self._is_known_call = is_known_call
        self._on_change = on_change
        self._on_status = on_status
        self._highlight_job = None
        self._popup: Optional[tk.Toplevel] = None
        self._popup_list: Optional[tk.Listbox] = None
        self._suppress_change = False

        mono = tkfont.nametofont("TkFixedFont").copy()
        mono.configure(size=10)
        self._font = mono

        self._lines = tk.Canvas(self, width=44, highlightthickness=0)
        self._lines.pack(side="left", fill="y")
        self.text = tk.Text(
            self, wrap="none", undo=True, font=mono, tabs=(mono.measure("    "),),
            padx=6,
        )
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self._yview)
        xscroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=lambda *a: (yscroll.set(*a), self._redraw_lines()),
                            xscrollcommand=xscroll.set)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.text.pack(side="left", fill="both", expand=True)

        self._apply_theme()
        theme.on_change(self, self._apply_theme)
        self.text.tag_lower("current_function")

        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<KeyRelease>", self._on_key_release)
        self.text.bind("<Tab>", self._on_tab)
        self.text.bind("<Return>", self._on_return)
        self.text.bind("<Escape>", lambda e: self._close_popup())
        self.text.bind("<Down>", self._on_down)
        self.text.bind("<Up>", self._on_up)
        self.text.bind("<Control-space>", lambda e: (self._show_completions(force=True), "break")[1])
        self.text.bind("<ButtonRelease-1>", lambda e: (self._close_popup(), self._show_signature()))
        self.text.bind("<Configure>", lambda e: self._schedule_highlight())

    def _apply_theme(self) -> None:
        dark = theme.mode() == "dark"
        text_bg, gutter_bg, self._gutter_fg, cursor, error, warning, current = SURFACES["dark" if dark else "light"]
        self.text.configure(background=text_bg, foreground=theme.color("fg"), insertbackground=cursor,
                            selectbackground=theme.color("accent_bg"), selectforeground=theme.color("fg"))
        self._lines.configure(background=gutter_bg)
        for tag, color in (DARK_COLORS if dark else COLORS).items():
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_configure("error", underline=True, background=error)
        self.text.tag_configure("warning", underline=True, background=warning)
        self.text.tag_configure("current_function", background=current)
        self._redraw_lines()

    # -- public API --------------------------------------------------------
    def get(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set(self, source: str) -> None:
        self._suppress_change = True
        self.text.delete("1.0", "end")
        self.text.insert("1.0", source)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self._suppress_change = False
        self._highlight_all()
        self._redraw_lines()

    def goto_line(self, line: int, *, select: bool = False) -> None:
        index = f"{max(1, line)}.0"
        self.text.mark_set("insert", index)
        self.text.see(index)
        self.text.see(f"{line + 15}.0")
        self.text.see(index)
        if select:
            self.text.tag_remove("sel", "1.0", "end")
            self.text.tag_add("sel", index, f"{line}.end")
        self.text.focus_set()
        self._redraw_lines()

    def cursor_line(self) -> int:
        return int(self.text.index("insert").split(".")[0])

    def insert_at_cursor(self, text: str) -> None:
        self.text.insert("insert", text)
        self.text.focus_set()

    def replace_lines(self, first: int, last: int, new_lines: list[str]) -> None:
        """Replace lines first..last (1-based, inclusive) - last < first inserts before first."""
        start = f"{first}.0"
        end = f"{last + 1}.0" if last >= first else start
        self.text.edit_separator()
        self.text.delete(start, end)
        self.text.insert(start, "".join(line + "\n" for line in new_lines))
        self.text.edit_separator()
        self._schedule_highlight()

    def mark_diagnostics(self, diagnostics: list) -> None:
        self.text.tag_remove("error", "1.0", "end")
        self.text.tag_remove("warning", "1.0", "end")
        for d in diagnostics:
            if d.line <= 0:
                continue
            tag = "error" if d.severity == "error" else "warning"
            self.text.tag_add(tag, f"{d.line}.0", f"{d.line}.end")

    def highlight_function(self, first: int, last: int) -> None:
        self.text.tag_remove("current_function", "1.0", "end")
        if first > 0:
            self.text.tag_add("current_function", f"{first}.0", f"{last + 1}.0")

    def refresh_highlighting(self) -> None:
        self._highlight_all()

    # -- line numbers -------------------------------------------------------
    def _yview(self, *args):
        self.text.yview(*args)
        self._redraw_lines()
        self._schedule_highlight()

    def _redraw_lines(self) -> None:
        self._lines.delete("all")
        index = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(index)
            if info is None:
                break
            y = info[1]
            line = index.split(".")[0]
            self._lines.create_text(40, y, anchor="ne", text=line, font=self._font, fill=self._gutter_fg)
            nxt = self.text.index(f"{index}+1line")
            if nxt == index:
                break
            index = nxt

    # -- highlighting ---------------------------------------------------------
    def _schedule_highlight(self) -> None:
        if self._highlight_job is not None:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(150, self._highlight_visible)

    def _highlight_all(self) -> None:
        self._highlight_range("1.0", "end")

    def _highlight_visible(self) -> None:
        self._highlight_job = None
        first = int(self.text.index("@0,0").split(".")[0])
        last = int(self.text.index(f"@0,{self.text.winfo_height()}").split(".")[0])
        self._highlight_range(f"{max(1, first - 5)}.0", f"{last + 5}.end")

    def _highlight_range(self, start: str, end: str) -> None:
        start = self.text.index(f"{start} linestart")
        end = self.text.index(f"{end} lineend")
        for tag in COLORS:
            self.text.tag_remove(tag, start, end)
        chunk = self.text.get(start, end)
        for m in _TOKEN_RE.finditer(chunk):
            kind = m.lastgroup
            if kind == "call" and m.group() not in KEYWORDS and not self._is_known_call(m.group()):
                kind = "call_unknown"
            if kind == "call" and m.group() in KEYWORDS:
                kind = "keyword"
            self.text.tag_add(kind, f"{start}+{m.start()}c", f"{start}+{m.end()}c")

    # -- events -------------------------------------------------------------
    def _on_modified(self, _event=None) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._redraw_lines()
        if not self._suppress_change:
            self._on_change()

    def _on_key_release(self, event) -> None:
        self._schedule_highlight()
        self._redraw_lines()
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape"):
            return
        if event.char and (event.char.isalnum() or event.char == "_"):
            self._show_completions()
        else:
            self._close_popup()
        if event.char in ("(", ",") or event.keysym in ("Left", "Right", "BackSpace"):
            self._show_signature()

    def _on_tab(self, _event):
        if self._popup is not None:
            self._accept_completion()
            return "break"
        self.text.insert("insert", "    ")
        return "break"

    def _on_return(self, _event):
        if self._popup is not None:
            self._accept_completion()
            return "break"
        line = self.text.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", line).group()
        if line.rstrip().endswith(":"):
            indent += "    "
        self.text.insert("insert", "\n" + indent)
        self.text.see("insert")
        return "break"

    def _on_down(self, _event):
        if self._popup_list is None:
            return None
        self._move_selection(1)
        return "break"

    def _on_up(self, _event):
        if self._popup_list is None:
            return None
        self._move_selection(-1)
        return "break"

    # -- completion ---------------------------------------------------------
    def _current_word(self) -> str:
        m = _WORD_BEFORE.search(self.text.get("insert linestart", "insert"))
        return m.group() if m else ""

    def _show_completions(self, force: bool = False) -> None:
        word = self._current_word()
        if len(word) < (1 if force else 2):
            self._close_popup()
            return
        items = self._completions(word)[:40]
        if not items or (len(items) == 1 and items[0] == word):
            self._close_popup()
            return
        if self._popup is None:
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            self._popup_list = tk.Listbox(self._popup, height=8, width=36, font=self._font, exportselection=False)
            self._popup_list.pack(fill="both", expand=True)
            self._popup_list.bind("<Double-Button-1>", lambda e: self._accept_completion())
        self._popup_list.delete(0, "end")
        for item in items:
            self._popup_list.insert("end", item)
        self._popup_list.selection_set(0)
        bbox = self.text.bbox("insert")
        if bbox:
            x = self.text.winfo_rootx() + bbox[0]
            y = self.text.winfo_rooty() + bbox[1] + bbox[3] + 2
            self._popup.wm_geometry(f"+{x}+{y}")
        self._popup.lift()

    def _move_selection(self, delta: int) -> None:
        sel = self._popup_list.curselection()
        index = (sel[0] if sel else 0) + delta
        index = max(0, min(self._popup_list.size() - 1, index))
        self._popup_list.selection_clear(0, "end")
        self._popup_list.selection_set(index)
        self._popup_list.see(index)

    def _accept_completion(self) -> None:
        if self._popup_list is None:
            return
        sel = self._popup_list.curselection()
        if sel:
            choice = self._popup_list.get(sel[0])
            word = self._current_word()
            self.text.delete(f"insert-{len(word)}c", "insert")
            self.text.insert("insert", choice)
        self._close_popup()
        self._schedule_highlight()
        self._show_signature()

    def _close_popup(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
        self._popup = None
        self._popup_list = None

    def _show_signature(self) -> None:
        """Show the signature of the call the cursor is inside, if any."""
        before = self.text.get("insert linestart", "insert")
        depth = 0
        for i in range(len(before) - 1, -1, -1):
            ch = before[i]
            if ch == ")":
                depth += 1
            elif ch == "(":
                if depth == 0:
                    m = _WORD_BEFORE.search(before[:i].rstrip())
                    if m:
                        sig = self._signature(m.group())
                        if sig:
                            self._on_status(sig)
                            return
                    break
                depth -= 1
        self._on_status("")
