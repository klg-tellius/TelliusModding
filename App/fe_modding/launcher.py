"""Shared source/frozen entry point and noninteractive release smoke check."""
import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .smoke_check import run
        raise SystemExit(run(sys.argv[2]))
    from .gui.app import main as gui_main
    gui_main()
