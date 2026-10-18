"""Regenerate original explanatory SVGs used by the modding tutorials.

Edit tutorial prose directly in wiki/modding. These figures are diagrams,
not application screenshots. Run from any working directory.
"""
from pathlib import Path
import html
import textwrap

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / 'wiki/assets/images/tutorials'

# Each diagram explains a distinct relationship; labels are intentionally not a
# pretend screenshot. Text is repeated in page prose for accessible reading.
FIGURES = {
'project': ('From source disc to a playable mod', [
('1 · SOURCE DISC', 'Your original image', 'Choose disc image… → Extract', 'Keep this file for patch comparison.'),
('2 · PROJECT FILES', 'The editable working copy', 'Edit → commit field → named Save', 'Reopen the record to prove it saved.'),
('3 · BUILD OUTPUT', 'A newly packed game image', 'Build disc / Build and play in Dolphin', 'Launch this output and test the change.')], 'Saving an editor does not rebuild an older disc image.'),
'workspace': ('Find the owner before changing a value', [
('1 · CHAPTER-LOCAL', 'Chapters → your chapter', 'Map, deployment, script, dialogue', 'Check part/phase and difficulty first.'),
('2 · SHARED RECORDS', 'Characters / Game Data', 'Character → class → item / skill', 'A shared record can affect many units.'),
('3 · RESOURCES & TESTS', 'Assets / Tools', 'Models and media / Check and simulation', 'Follow IDs to the resource they name.')], 'Ctrl+K finds records; Back returns along your navigation path.'),
'chapter': ('A chapter works when its references agree', [
('1 · CHAPTER IDENTITY', 'Slot + part + difficulty', 'Overview names the resources', 'Example: slot 01 is the Prologue.'),
('2 · CONNECTED FILES', 'Map + deployment + script + messages', 'Script loads groups and calls messages', 'Match IDs and section names exactly.'),
('3 · STORY BOUNDARY', 'Current chapter → next chapter', 'Win → transition → save → reload', 'Test the boundary through normal play.')], 'Copying one resource does not copy a complete chapter.'),
'character': ('A character record is only one link', [
('1 · CREATE IDENTITY', 'Example: PID_TUTORIAL_GUARD', 'Unique PID + name key + class JID', 'Save FE8Data.bin after record edits.'),
('2 · PLACE THE UNIT', 'Deployment → intended section', 'Reference the new PID and equipment', 'Choose difficulty, tile, and army.'),
('3 · CHECK THE RESULT', 'Build → Play…', 'Inspect name, stats, model, inventory', 'A new record does not auto-deploy.')], 'Text, portraits, models, and placement each have their own references.'),
'assets': ('A file must be connected to its consumer', [
('1 · RESOURCE', 'Image, model, audio, or video', 'Export a reference → import your edit', 'Check scale, dimensions, and preview.'),
('2 · IDENTITY / TABLE', 'FID_ / RID_ / BGM_ / model slot', 'Save the owning resource or table', 'Keep new identities distinct from shared ones.'),
('3 · CONSUMER', 'Character, scene, chapter, or script', 'Assign or call the exact identity', 'Test from the place that actually uses it.')], 'A successful asset preview does not prove the game reaches that asset.'),
'tables': ('Separate shared rules from local assignments', [
('1 · DEFINITION', 'Game Data: class / item / terrain', 'Copy supported records or edit a slot', 'Inspect shared users and fixed-table limits.'),
('2 · ASSIGNMENT', 'Character or chapter placement', 'Reference JID / IID / terrain type', 'Save both the definition and its owner.'),
('3 · COMPARISON', 'Same test, one changed variable', 'Before → after → unrelated control', 'Check another user of any shared record.')], 'Renaming a record does not replace an effect implemented in game code.'),
'terrain': ('Visible scenery and walking rules are separate', [
('1 · WHAT YOU SEE', 'A house prop on the map', 'Place / rotate the visible model', 'The model alone does not block movement.'),
('2 · WHERE YOU WALK', 'Terrain tiles under the house', 'Paint the intended blocked footprint', 'Movement costs depend on unit movement type.'),
('3 · WHERE YOU STAND', 'Tile corner heights', 'Match playable panels to the surface', 'Walk across edges in both directions.')], 'Test the same footprint with more than one movement type.'),
'deployment': ('One wave needs data, a trigger, and a guard', [
('1 · WHO / WHERE', 'Deployment section: your exact name', 'Units + army + start / arrival tiles', 'Create it in each intended difficulty file.'),
('2 · WHEN', 'Script trigger → Dispos* call', 'Use that same section name', 'Check turn, phase, and occupied arrival tiles.'),
('3 · ONLY ONCE', 'Chapter flag: not yet → done', 'Check before loading; set after success', 'Advance to another eligible phase to verify.')], 'A section defines units; it does not schedule its own arrival.'),
'events': ('Build an event as four explicit decisions', [
('1 · TRIGGER + GUARD', 'When can this event run?', 'Talk / phase / location + flag check', 'Confirm the trigger is actually reached.'),
('2 · ACTION', 'What should happen?', 'Show message / Join / load group / reward', 'Resolve every referenced ID and argument.'),
('3 · COMPLETION', 'What prevents another run?', 'Set the correct flag after success', 'Test the action and the repeat attempt.')], 'Chapter flags remember locally; campaign flags carry state across chapters.'),
'dialogue': ('From written dialogue to an in-game scene', [
('1 · SCENE SETUP', 'Layout → background → portraits', 'Choose seats, speaker, and textbox', 'Inspect inherited starting context.'),
('2 · TEXT & TIMING', 'Line → wait → transition', 'Preview from the beginning, then save', 'Check glyphs, page breaks, and continuity.'),
('3 · SCRIPT CALL', 'Trigger → exact Message ID', 'Compile caller → play the trigger', 'A saved message needs a reachable call.')], 'Preview checks the scene; playing the trigger checks its integration.'),
'ai': ('Trace the policy that produces an AI action', [
('1 · DEPLOYMENT', 'The acting unit’s AI assignments', 'Attack / Move / Heal policies', 'Copy shared scripts before changing a role.'),
('2 · CANDIDATES', 'Eligible actions in this board state', 'Range, HP, equipment, terrain, counters', 'Later script actions can replace earlier ones.'),
('3 · DECISION', 'Play → how the target was chosen', 'Compare candidates and the chosen action', 'Repeat with targets inside and outside range.')], 'A stationary boss needs a movement policy as well as an attack policy.'),
'media': ('Test media at the boundaries, not just the start', [
('1 · IMPORT & PREVIEW', 'Source → encoded game resource', 'Listen / watch the imported result', 'Preserve a reference export for comparison.'),
('2 · CONNECT', 'Cue or path → chapter / script', 'Use BGM_ / SFX_ / Movie path as appropriate', 'Save changed data and compile changed calls.'),
('3 · FULL PLAYBACK', 'Start → loop or tail → next event', 'Also test skipping where supported', 'Inspect build size after large media changes.')], 'Local preview omits some engine behavior; finish in the built game.'),
'model': ('Prove a small model round trip first', [
('1 · EXPORT EXACT SET', 'Keep an untouched reference', 'Preserve coordinates, rig, materials', 'Start with one small visible geometry change.'),
('2 · IMPORT REVIEW', 'Geometry + textures + bones + events', 'Inspect warnings before writing', 'Check attachments and several animations.'),
('3 · CONTEXT TEST', 'Render fight → built game', 'Near / far cameras, hit / miss / recovery', 'Rigged imports still need Dolphin confirmation.')], 'A correct idle pose does not prove attack timing or weapon attachment.'),
'testing': ('Three checks answer three different questions', [
('1 · CHECK PROJECT', 'Are references and files valid?', 'Save editors → Tools → Check → Run check', 'Compare warnings against your untouched baseline.'),
('2 · SIMULATE', 'Does the scenario behave as intended?', 'Play / Battle Simulator / Render fight', 'Inspect logs, flags, decisions, and timing.'),
('3 · BUILT GAME', 'Does it work in the game engine?', 'Build → Dolphin → controlled save state', 'Exercise the edited feature and its boundaries.')], 'Passing an earlier check does not replace the next one.'),
'release': ('A release is tested from the recipient’s starting point', [
('1 · RELEASE CANDIDATE', 'Saved, checked, tested project', 'Mod details + version + base revision', 'Remove temporary debug changes.'),
('2 · PATCH', 'Create patch… → .tpatch', 'Keep the matching source disc available', 'Review changed assets and release notes.'),
('3 · CLEAN APPLICATION', 'Unmodified matching disc + patch', 'Apply patch to a disc… → separate output', 'Launch that result and repeat a smoke test.')], 'Test patch application separately from your existing working build.'),
'campaign': ('A three-chapter exercise with observable checkpoints', [
('1 · RECRUIT', 'Chapter 1: talk → Join', 'Guard locally; record persistent state', 'Win, save, reload: is the recruit retained?'),
('2 · REINFORCE', 'Chapter 2: phase → wave', 'Load the named section only once', 'Win, save, reload: does state still agree?'),
('3 · RESOLVE', 'Chapter 3: objective → ending', 'Test boss, defeat, and finale branches', 'Repeat the complete route in Dolphin.')], 'Test every chapter independently, then every transition in sequence.'),
}

def text(x, y, value, size=20, color='#243c48', weight='400'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{html.escape(value)}</text>'

def figure(key, title, cards, note):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 680" role="img" aria-labelledby="title desc">',
           f'<title id="title">{html.escape(title)}</title>',
           f'<desc id="desc">{html.escape(". ".join(". ".join(c) for c in cards) + ". " + note)}</desc>',
           '<rect width="920" height="680" rx="18" fill="#f4f3ec"/>',
           '<g font-family="Segoe UI, Arial, sans-serif">',
           text(32,36,'TELLIUS MODDING · EXPLANATORY DIAGRAM',14,'#456575','600')]
    for i,line in enumerate(textwrap.wrap(title, width=58)):
        out.append(text(32,72+i*30,line,27,'#123c50','700'))
    for i,(label,heading,action,check) in enumerate(cards):
        y=126+i*158
        out.extend([f'<rect x="32" y="{y}" width="856" height="134" rx="10" fill="#ffffff" stroke="#c7d3ce"/>',
                    f'<rect x="32" y="{y}" width="7" height="134" rx="3" fill="#26728a"/>',
                    text(55,y+26,label,14,'#26728a','700'),text(55,y+57,heading,23,'#123c50','600'),
                    text(55,y+87,action,19),text(55,y+114,check,18,'#496557')])
        if i<2:
            out.append(f'<path d="M460 {y+139} v12 m-5 -5 l5 5 5 -5" fill="none" stroke="#26728a" stroke-width="2"/>')
    for i,line in enumerate(textwrap.wrap(note,80)):
        out.append(text(32,626+i*23,line,18,'#123c50','600'))
    out.append('</g></svg>')
    (IMAGES/f'{key}.svg').write_text('\n'.join(out)+'\n',encoding='utf-8')

def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    for key, (title, cards, note) in FIGURES.items():
        figure(key, title, cards, note)
    print(f'Generated {len(FIGURES)} tutorial diagrams.')

if __name__ == '__main__':
    main()
