"""Audit local FE9 resources and render reproducible screenshot checkpoints.

Usage: python App/tools/verify_conversations.py EXTRACTED --output OUTPUT
Game assets and rendered images are never written into the extracted directory.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fe_modding.formats import message
from fe_modding.formats.fe9_conversation import InitialContext, tokenize, build_timeline
from fe_modding.formats.fe9_conversation_assets import ConversationAssets
from fe_modding.formats.fe9_conversation_render import ConversationRenderer

# User-provided screenshots in G:/ROM/conversationimages. A wait page is
# selected by its text, so this remains reproducible if timing is refined.
CHECKPOINTS = (
    ("c01", "MS_01_OP_01", "Nn...", "prologue-mist", ()),
    ("c01", "MS_01_OP_02", "I like your resolve", "prologue-greil", ()),
    ("c02", "MS_02_OP_01", "Sorry. I'll get up earlier", "barracks", ()),
    ("c02", "MS_02_OP_01_02", "I'll take your word", "boyd", ()),
    ("c02", "MS_02_EV_00", "Ah! My sword.", "weapon-triangle", ()),
    ("c25", "MS_25_TK_01", "Shut up!", "bastian", (("IKE", "IKE2"),)),
    ("c29", "MS_29_BT_MIST", "you took my brother", "mist-black-knight", ()),
    ("c31", "MS_31_EV_NASIR_02", "Are you crazy?", "nasir", ()),
    ("c07", "MS_07_ED_01_A", "Father and I will catch", "escape", ()),
    ("c17", "MS_17_ED_06", "Remember the genocide", "serenes", ()),
)


def verify(extracted: Path, output: Path):
    assets = ConversationAssets(extracted)
    renderer = ConversationRenderer(assets)
    output.mkdir(parents=True, exist_ok=True)
    references = {}
    failures = []
    for path in sorted((assets.files / "Mess").glob("*.m")):
        for entry in message.read_messages_path(path):
            for token in tokenize(entry.text):
                name = token.arg if token.code == "FC" else token.arg[1:] if token.code == "c" else ""
                if name:
                    references.setdefault("FID_" + name, []).append(f"{path.name}:{entry.speaker}:{token.offset}")
    for fid in references:
        if fid in ("FID_ME", "FID_LME"):
            continue
        try:
            face = assets.face(fid)
            for mouth in (0, 1):
                for eye in (0, 1, 2):
                    face.compose(mouth_variant=mouth, left_eye_frame=eye, right_eye_frame=eye)
        except (ValueError, OSError, IndexError) as error:
            failures.append({"face": fid, "error": str(error), "sources": references[fid]})
    scenes = []
    for chapter, mid, snippet, label, aliases in CHECKPOINTS:
        entry = next(m for m in message.read_messages_path(assets.files / f"Mess/{chapter}.m") if m.speaker == mid)
        timeline = build_timeline(entry.text, context=InitialContext(aliases=aliases), measure=renderer.measure)
        candidates = [e for e in timeline.events if e.wait and any(snippet in b.text for b in e.state.boxes)]
        if not candidates:
            scenes.append({"message": mid, "error": f"Checkpoint not found: {snippet}"})
            continue
        event = candidates[0]
        result = renderer.render(event)
        result.image.save(output / f"{label}.png")
        scenes.append({"message_file": f"Mess/{chapter}.m", "message": mid, "image": f"{label}.png",
                       "event": event.index, "time_ms": event.time_ms, "source_offset": event.source_offset,
                       "page": sum(e.wait for e in timeline.events[:event.index+1]), "aliases": dict(aliases),
                       "text": [b.text for b in event.state.boxes],
                       "diagnostics": [d.description for d in (*timeline.diagnostics, *result.diagnostics)]})
    report = {"native_size": [608, 448], "distinct_faces": len(references), "failures": failures,
              "context_requirements": {f: references[f] for f in ("FID_ME", "FID_LME") if f in references},
              "checkpoints": scenes}
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"faces": len(references), "failures": len(failures), "scenes": scenes}, ensure_ascii=True, indent=2))
    return bool(failures or any("error" in s for s in scenes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(verify(args.extracted, args.output))
