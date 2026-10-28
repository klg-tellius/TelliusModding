"""Print the Tellius Archive 'script-functions' article from the reviewed reference.

Usage: python archive_script_functions.py > article.js, then replace the
"script-functions" entry of docs/tellius_archive.html with the output.
"""
import html
import json
import re
import sys
from collections import OrderedDict

from pathlib import Path as _P
ROOT = str(_P(__file__).resolve().parents[2])
sys.path.insert(0, ROOT + '/docs/app')
from script_reference_details import DETAILS

cat = json.load(open(ROOT + '/App/fe_modding/formats/cmb/externs_fe9.json', encoding='utf-8'))['externs']

CLEAN = [
    (' This loads a compiled game resource, not a .fe9s editor file.', ''),
    ('global is a .fe9s keyword: call it as extern("global", "name"). ', ''),
]

GROUPS = OrderedDict([
    ('music', ('Music and sound', 'Four music channels (0 is the map music), the ambient-sound level and one-shot sound effects. Every millisecond duration is converted to 60 Hz frames.')),
    ('screen', ('Screen transitions, images and captions', 'Fades, wipes and flashes, full-screen images (RID_ rectangles), world-map views, location captions and highlight frames.')),
    ('camera', ('Camera', 'The map camera keeps a point it looks at plus a yaw, a pitch (both in degrees) and a distance in tiles. The event camera plays a path of keyframes.')),
    ('talk', ('Conversations, dialogs and movies', 'Message windows, choice dialogs, cutscene movies and the ending screens.')),
    ('units', ('Units', 'A unit is addressed by a small numeric handle (from UnitGetByPID and similar lookups); 0 means no unit. The *ByPID helpers of startup.cmb look the unit up first.')),
    ('items', ('Inventory, skills and AI', 'Eight inventory slots per unit: 0–3 weapons, 4–7 items. Skills by SID_, AI scripts by SEQ_ and MTYPE_ names.')),
    ('deploy', ('Deployment and preparations', 'Placing deployment groups from the chapter\'s dispos file, the preparation screen and whole-army save/restore.')),
    ('map', ('Map objects and terrain', 'Doors, roofs, chests, villages and props (their state is kept in saves), special terrain such as ballistae, rocks and pits, and map loading.')),
    ('battle', ('Scripted battles and effects', 'Battles with forced results, map effects, event arrows and screen shakes.')),
    ('state', ('Chapter state, flags and difficulty', 'Turn, phase, money, difficulty, named flags, chapter results and the event system\'s own state.')),
    ('flow', ('Waiting, skipping and script control', 'Waits, the player\'s event skip, engine processes and script files.')),
    ('tutorial', ('Tutorials', 'The tutorial player: freezing the game, scripted controller input, tutorial dialogs and settings.')),
    ('debug', ('Debug and leftovers', 'Developer output and functions that do nothing in the retail game.')),
])


def group_of(name):
    n = name
    if n in ('NormalOnly', 'Easy'):
        return 'state'
    if re.match(r'(BGM|Bgm|SFX|ENV|Sound|LocalDieTalkWithBgm)', n):
        return 'music'
    if re.match(r'(Fade|Wipe|Flash|isFading|isWipe|isFlash|Rect|Timei|GMap|CreateNotice|DeleteNotice|Tut3SArrow|HidePrim2D|SetWhiteBackdrop|RemoveBackdrop|SetSepia|JyokyoMap|GetFukiPos|Tutorial_Fade|TutShowKari|TutShow$)', n):
        return 'screen'
    if re.search(r'(Camera|Focus)', n) and not n.startswith('Unit'):
        return 'camera'
    if re.match(r'(UnitFocus|InstantUnitFocus)', n):
        return 'camera'
    if re.match(r'(Talk|Dialog|MoviePlay|ChapterMoviePlay|DefaultDieTalk|DefaultEscapeTalk|WarRecord|IndividualWarRecord|StaffRoll|BeginFinale|EndFinale|Check$|WaitPressAnyKey)', n):
        return 'talk'
    if re.match(r'(Dispos|InstantDispos|Sally|Join|TrialAddUnit|SelectAuxiliary|UnitForcedSally|UnitDontMoveSally|Units|AllPush|AllPop|AllUnit|UnitDispReload|Disp(Pre)?Load|DispFree|ForceGet|ForceCheck|SysGetRound)', n):
        return 'deploy'
    if re.match(r'(Unit.*(Item|Equip|Skill|Weapon|AccAway|Warehouse|Cp|Valuation)|UnitPutToWarehouse|UnitReplaceItem|UnitCanUseIt|UnitQueryEquip|UnitGetEquip|ItemGetIndex|CpClrNoMoveFlag|MindGetItem|MindGetMoney|_gi$)', n):
        return 'items'
    if re.match(r'(Unit|InstantUnit|Person|PIDisAlive|Enemy|Player|GetDiedPlayerCount|CheckAttackable|MindGet)', n):
        return 'units'
    if re.match(r'(Door|InstantDoor|Roof|InstantRoof|TBox|Visit|Build|SetTerrain|SetShooter|SetRock|SetPit|SetFragile|AddTT|TTPM|ShooterBullet|Map|_mf|ShowMapCursor|HideMapCursor|BeginMapHoldCursor|EndMapHoldCursor|SetGrid|SetCircle|SetOutLink|SetFog|SetSight|SetWeather|SetAmbient|SetDiffuse|SetRoofEnable|GetMapHeight|SetCamSuspend|SetOnBtFocus|SetPullCursor|RegistLocationTT|EventGet)', n):
        return 'map'
    if re.match(r'(Netuzo|SetEventBattle|Effect|EventArrow|EventQuake|GetBattleType|intplGetValue|FRAME2MSEC|MSEC2FRAME)', n):
        return 'battle'
    if re.match(r'(BM|regist|global|get|set|clr|RegistGlobalFlags|Normal|Hard|Maniac|GetRank|GetLanguage|GCST|AchieveSet|Complete18|GetRnd|MCResult|_intr|IsE3Version|SallyGetSurplus|GetTutorial)', n):
        return 'state'
    if re.match(r'(Tut|Tutorial|Config_Tut|_pa|_tt|_tr|td$|tde$|taikitk|turntk|turnatk|_seqini|_bmsini|_cmb_mess_load|GameBind|GameUnbind|QueryLesson|ComebackFunc|Comeback|PadSetMask|PadResetMask|Config_Tutorial)', n):
        return 'tutorial'
    if re.match(r'(Wait|EnableSkip|DisableSkip|Proc|Cm|SuspendEvent|ResumeEvent|ArcLoad|ArcFree|PreLoad|_pldone|ENVNoisyOn_When|ENVSilentOff_When|RectPreLoad)', n):
        return 'flow'
    if re.match(r'(report|dump|ArenaDump|printf)', n):
        return 'debug'
    return None


def esc(text):
    for a, b in CLEAN:
        text = text.replace(a, b)
    return html.escape(text, quote=False)


groups = {k: [] for k in GROUPS}
missing = []
for name in sorted(DETAILS, key=str.lower):
    g = group_of(name)
    if g is None:
        missing.append(name)
        continue
    groups[g].append(name)
if missing:
    print('UNGROUPED', missing)

natives = sum(1 for n in DETAILS if cat[n]['source'] == 'native')
helpers = sum(1 for n in DETAILS if cat[n]['source'] == 'script')
parts = []
parts.append(
    '<p>Every <code>externCall</code> target the game\'s event scripts can use, with what it does in the US game. '
    f'There are {natives} <strong>native</strong> functions, built into <code>main.dol</code>, and {helpers} <strong>helper</strong> functions '
    'written in script inside <code>startup.cmb</code>, which every chapter can call; helpers are marked <em>startup.cmb</em>. '
    '${badge("confirmed","confirmed")}</p>')
parts.append(
    '<div class="callout"><p class="callout-t">Rules shared by every function</p>'
    '<p><strong>Arguments are positional</strong> and each function always takes exactly its listed number. '
    '<strong>Units</strong> are numeric handles, not character IDs; 0 means no unit. '
    '<strong>Forces</strong>: 0 player, 1 enemy, 2 allied (orderable), 3 other (green), 4 free pool, 5 player reserve, 6 dead/inactive, 7 special. '
    '<strong>Tiles</strong> count from the map\'s border. <strong>Durations</strong> named <em>ms</em> are milliseconds, converted to 60 Hz frames. '
    '<strong>Skipping</strong>: while the player skips an event, calls that would animate or wait apply their end state at once (and usually return 0), and music and sound calls are ignored. '
    'A call that shows something the event must wait for (a conversation, a movement, a door, a movie) pauses the script by itself unless its description says it does not wait.</p></div>')
for key, (title, intro) in GROUPS.items():
    names = groups[key]
    if not names:
        continue
    parts.append(f'<h2>{esc(title)}</h2>')
    parts.append(f'<p>{esc(intro)}</p>')
    for name in names:
        d = DETAILS[name]
        args = ', '.join(a[0] for a in d['args'])
        tag = ' <em>(startup.cmb)</em>' if cat[name]['source'] == 'script' else (' <em>(not registered)</em>' if cat[name]['source'] == 'unregistered' else '')
        body = [f'<p><code>{esc(name)}({esc(args)})</code>{tag} — {esc(d["behavior"])}</p>']
        items = [f'<li><code>{esc(a)}</code>: {esc(m)}</li>' for a, m in d['args']]
        items.append(f'<li><em>Returns</em>: {esc(d["returns"])}</li>')
        if d['notes']:
            items.append(f'<li>{esc(d["notes"])}</li>')
        if d.get('example'):
            pass
        body.append('<ul class="fn-detail">' + ''.join(items) + '</ul>')
        parts.append(''.join(body))

text = '\n  '.join(parts)
# The archive stores article bodies in JS template literals.
text = text.replace('\\', '\\\\').replace('`', '\\`')
text = text.replace('${badge(&quot;confirmed&quot;,&quot;confirmed&quot;)}', '${badge("confirmed","confirmed")}')
assert text.count('${') == 1, text.count('${')
article = ('"script-functions": {\n'
           '  ns:"system", title:"Script Functions", dek:"Every function an event script can call — what it does, its arguments and what it returns",\n'
           '  infobox:{ type:"Reference", status:"confirmed", fields:[\n'
           f'    ["Natives","{natives} built into main.dol"],["Helpers","{helpers} in startup.cmb"],["Called through","<code>externCall</code>"],\n'
           '    ["Related",`${wl("events-scripting")}, ${wl("event-script")}, ${wl("event-flags")}`]\n'
           '  ]},\n'
           '  categories:["Structure"],\n'
           '  body:`\n  ' + text + '\n  `\n},\n')
sys.stdout.reconfigure(encoding='utf-8')
sys.stdout.write(article)
