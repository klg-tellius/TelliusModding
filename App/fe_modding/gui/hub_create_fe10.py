"""Radiant Dawn's Create hub (Chapters › Create hub…): an added chapter (05NN) copied from a template, the
avatar alone in it (:mod:`hub_creation_fe10`), then its Build tab's Hub tool."""

from __future__ import annotations

from tkinter import messagebox

from .. import chapters, chapters_fe10, hub, hub_creation_fe10, hub_fe10
from ..game_code.story_flow import open_story_flow
from .hub_dialog import CreateHubDialog


def create_hub(page) -> None:
    """Run Create hub from the Chapters overview ``page``."""
    session = page.shell.session
    if not session.available:
        messagebox.showerror("Create hub", "This project has no FE10Data.cms.", parent=page)
        return
    flow, why = open_story_flow(page.project)
    if flow is None:
        messagebox.showerror("Create hub", f"Story flow is unavailable: {why}", parent=page)
        return
    fe10 = session.data
    free = chapters_fe10.free_chapters(page.project, fe10)
    if not free:
        messagebox.showerror("Create hub", "No free added-chapter number (0501-0524).", parent=page)
        return
    titles = chapters.chapter_titles(page.project)

    def usable(cid):
        paths = chapters.chapter_paths(page.project, cid)
        return (len(chapters.chapter_phases(page.project, cid)) == 1 and paths.map is not None
                and paths.deployment is not None and paths.script is not None
                and hub_creation_fe10.player_start(page.project, cid) is not None)

    templates = {f"{chapters.chapter_display_title(cid, titles)} ({cid})": cid
                 for cid in sorted(chapters_fe10.templates(page.project, fe10), key=lambda c: c == "0000")
                 if usable(cid)}
    if not templates:
        messagebox.showerror("Create hub", "No one-map chapter has map, deployment and script files.",
                             parent=page)
        return
    names = {pid: info.name for pid, info in getattr(page.shell.index, "by_pid", {}).items() if info.name}
    avatars = {f"{names.get(pid, pid)} ({pid})": pid for pid, _jid in sorted(
        hub_fe10.avatar_candidates(page.project, fe10), key=lambda c: c[0] not in names)}
    if not avatars:
        messagebox.showerror("Create hub", "No character is free for the hub's avatar. Create a character "
                             "that no chapter deploys first (Game Data › Characters).", parent=page)
        return
    activations = {f"{chapters.chapter_display_title(page, titles)} ({page})": n
                   for n, page in hub_fe10.activation_candidates(page.project, -1, fe10).items()}
    dialog = CreateHubDialog(page, free=free, templates=templates, avatars=avatars, activations=activations,
                             avatar_help=(
                                 "The character the player walks around the hub with. It must not be deployed "
                                 "in any other chapter: create one in Game Data › Characters first if none is "
                                 "listed. It takes the template's first player unit's tile (the middle of a "
                                 "blank map when that tile is outside it)."))
    page.wait_window(dialog)
    if dialog.result is None:
        return
    chapter, title, source_id, keep_map, size, avatar_pid, activation = dialog.result[:7]
    ground_color, ground_image, tile_ground_image = dialog.result[7:10]
    if session.dirty and not messagebox.askyesno(
            "Save FE10Data.cms?", "Creating a hub saves FE10Data.cms, including its unsaved edits. Continue?",
            parent=page):
        return
    try:
        plan = hub_creation_fe10.create_chapter(
            page.project, fe10, source_id, chapter, title, avatar_pid,
            blank_size=None if keep_map else size, ground_color=ground_color, ground_image=ground_image,
            tile_ground_image=tile_ground_image)
        session.data = plan.fe10data
        session.changed(page)
        session.save()
        hub.save_draft(page.project, {"chapter": plan.number, "activation_chapter": activation,
                                      "avatar_pid": avatar_pid, "destinations": []})
    except Exception as exc:  # noqa: BLE001 - show validation and codec failures together
        messagebox.showerror("Could not create hub", str(exc), parent=page)
        return
    page.shell.changelog.append(f"Chapter {chapter}", f"Created hub chapter from {source_id}")
    page.shell.rebuild_index()
    page._build()
    chapter_page = page.shell.existing_page("chapter")
    if chapter_page is not None:
        chapter_page.refresh_chapter_lists()
    page.shell.navigate(("chapter", chapter, "build", "hub"))
