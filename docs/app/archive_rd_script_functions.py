"""Print the Tellius Archive 'rd-script-functions' article from externs_fe10.json.

Usage: python archive_rd_script_functions.py > article.js, then replace the
"rd-script-functions" entry of docs/tellius_archive.html with the output.
"""
import html
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
cat = json.load(open(ROOT / "App/fe_modding/formats/cmb/externs_fe10.json", encoding="utf-8"))["externs"]

GROUPS = OrderedDict([
    ("native_externcalls", ("General", "Camera focus, flags, conversations, message arguments, images (rectangles), the world map, "
                            "portraits outside conversations, fades, music, sound, voices, special terrain, deployment, "
                            "script threads and version switches.")),
    ("map_scene", ("Map scenes", "Moving, turning and animating units on the map, deployment groups, doors, roofs, torches "
                   "and other map objects, light, weather, effects, cameras and full-screen post effects.")),
    ("unit_and_battlemap", ("Units and the battle map", "Reading and changing units, their items, skills, teams and AI flags, "
                            "the per-army convoys, and battle-map values such as the turn, the score and the objective lines.")),
    ("bmap_scene", ("Battle-map scenes and tutorials", "Tutorial overlays and scripts, cursor holding and the tutorial settings.")),
    ("chapter_objective", ("Chapter results", "Bonus experience lines and the defeat and escape checks of a chapter.")),
    ("event_arrow", ("Event arrows", "Arrows drawn on the map during events.")),
    ("script_movie", ("Scripted 3D scenes", "In-engine movie scenes built from model and animation files, and the text speed.")),
    ("epilogue", ("Ending", "The epilogue, staff roll, war record and unit ranking screens.")),
    ("tfx_signal_handler", ("Conversation signals", "A flag a conversation raises for the script.")),
])


def esc(text):
    return html.escape(text, quote=False)


def entry(name, sig):
    note = sig["note"]
    match = re.match(r"\(([^)]*)\):\s*", note)
    if match:
        args, text = match.group(1), note[match.end():]
    else:
        names = [a["name"] or f"arg{i}" for i, a in enumerate(sig["args"])]
        args, text = ", ".join(names), note
    text = text[:1].upper() + text[1:]
    return f'<p><code>{esc(name)}({esc(args)})</code> — {esc(text)}</p>'


natives = {n: s for n, s in cat.items() if s["source"] == "native"}
helpers = sum(1 for s in cat.values() if s["source"] == "script")
parts = [
    '<p>Every native function Radiant Dawn\'s event scripts can call, grouped by the part of the game that registers it, '
    f'with what it does in the US game. There are {len(natives)} natives; <code>startup.cmb</code> adds {helpers} helper functions written '
    'in script. ${badge("confirmed","engine")}</p>',
    '<div class="callout"><p class="callout-t">Conventions</p>'
    '<p><strong>Units</strong> are numeric handles (the unit\'s slot + 1); 0 means no unit. '
    '<strong>Forces</strong> 0-10. <strong>Difficulty</strong>: 0 Normal, 1 Hard, 2 Maniac, 3 Easy. '
    '<strong>Skipping</strong>: while the player skips an event, calls that animate apply their end state at once and sound calls are ignored. '
    'A call that suspends the script resumes it when its process ends. Descriptions of functions that Path of Radiance '
    f'also has follow {"${wl(\"script-functions\")}"} where the two games behave the same.</p></div>',
]
for key, (title, intro) in GROUPS.items():
    names = sorted((n for n, s in natives.items() if s["group"] == key), key=str.lower)
    if not names:
        continue
    parts.append(f"<h2>{esc(title)} ({len(names)})</h2>")
    parts.append(f"<p>{esc(intro)}</p>")
    parts.extend(entry(n, natives[n]) for n in names)
unregistered = sorted(n for n, s in cat.items() if s["source"] == "unregistered")
parts.append("<h2>Called but not registered</h2>")
parts.append("<p>Vanilla scripts call " + ", ".join(f"<code>{esc(n)}</code>" for n in unregistered)
             + ", which no part of the game registers: such a call does nothing and gives 0.</p>")

text = "\n  ".join(parts)
text = text.replace("\\", "\\\\").replace("`", "\\`")
article = ('"rd-script-functions": {\n'
           '  ns:"system", title:"Script Functions (Radiant Dawn)", dek:"Every native function a Radiant Dawn event script can call",\n'
           '  infobox:{ type:"Reference", status:"confirmed", fields:[\n'
           f'    ["Natives","{len(natives)}, from 9 registration functions"],["Helpers","{helpers} in startup.cmb"],\n'
           '    ["Related",`${wl("rd-event-scripts")}, ${wl("script-functions")}`]\n'
           '  ]},\n'
           '  categories:["Structure","Radiant Dawn"],\n'
           '  body:`\n  ' + text + '\n  `\n},\n')
sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.write(article)
