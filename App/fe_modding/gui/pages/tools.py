"""Tools: the workspace's utilities - the Battle Simulator, the save editor and
Game Code patches. Each opens its own page; they are not game files."""

from __future__ import annotations

from tkinter import ttk

from ..shell import Page
from ..widgets import Card, CardGrid, ScrollFrame

#: (title, icon, description, route), in hub order.
TOOLS = [
    ("Battle Simulator", "⚔", "Two units, their weapons and skills: forecast and a random or fixed fight", ("asset", "battle_sim")),
    ("Saves", "◫", "Open a .gci save and edit its units, convoy, forges and flags", ("saves",)),
    ("Check", "✓", "Find broken references and missing files before the game does", ("check",)),
    ("Game Code", "⌘", "Patches and tunable constants written into sys/main.dol", ("code",)),
]


class ToolsHub(Page):
    kind = "tools"

    def __init__(self, shell):
        super().__init__(shell)
        scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        scroll.pack(fill="both", expand=True)
        ttk.Label(scroll.body, text="Tools", style="Title.TLabel").pack(anchor="w")
        ttk.Label(scroll.body, text="Utilities that work on the game rather than hold its files.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 16))
        grid = CardGrid(scroll.body, card_width=280)
        grid.pack(fill="x")
        for title, icon, description, route in TOOLS:
            grid.add(title, Card(grid, title=title, subtitle=description, icon=icon, width=280,
                                 on_click=lambda r=route: shell.navigate(r)))
        grid.done()

    def crumbs(self, route):
        return [("Tools", None)]
