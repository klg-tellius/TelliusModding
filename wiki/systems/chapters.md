---
id: "chapters"
title: "Chapters"
description: "How a story chapter is actually assembled from four independent files, and how the game moves from one to the next"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/chapters"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/chapters.md"
---
# Chapters

*How a story chapter is actually assembled from four independent files, and how the game moves from one to the next*

A story chapter is not one file — it is four independent files that happen to share the same two-digit number, each owned by a different system:

!!! info "Mental model: one chapter number, four cooperating systems"
    The number is the rendezvous point. Dialogue supplies words, the event script supplies decisions and timing, deployment supplies actors and inventories, and the map supplies physical space. The playable chapter emerges only when the engine loads these parts together.

<div class="table-wrap">
<table><thead><tr><th>File</th><th>Holds</th></tr></thead><tbody>
    <tr><td><a class="wl" href="../../formats/message-format/"><code>Mess/cNN.m</code></a></td><td>Every line of dialogue and narration for the chapter</td></tr>
    <tr><td><a class="wl" href="../../formats/event-script/"><code>Scripts/CNN.cmb</code></a></td><td>The compiled logic that sets the chapter up, fires cutscenes, and checks win/lose conditions</td></tr>
    <tr><td><a class="wl" href="../../formats/dispo-format/"><code>zmap/bmapNN/dispos.cmp</code></a></td><td>Which units spawn, as what class, carrying what, with what AI — separately for each difficulty</td></tr>
    <tr><td><a class="wl" href="../../formats/map-format/"><code>zmap/bmapNN/map.cmp</code></a></td><td>The terrain those units spawn onto, plus every placed 3D prop</td></tr>
  </tbody></table>
</div>

## The chapter record

  A table in [FE8Data.bin](../formats/fe8data.md) (`ChapterData`) ties the four files together: one record per chapter, found by its chapter number. The record names the map folder (`bmap01`, loaded as `zmap/bmap01`), the script (`Scripts/C01.cmb`) and the message file (`mess/C01.m`). <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>The record also holds</th><th>Used for</th></tr></thead><tbody>
    <tr><td>The map music</td><td>Played with the map</td></tr>
    <tr><td>Four objective texts, with Hard and Maniac replacements</td><td>The goal and defeat lines of the <a class="wl" href="../objectives/">objective window</a></td></tr>
    <tr><td>Two background images</td><td>The preparation screens and the default conversation background</td></tr>
    <tr><td>A scene map and sky</td><td>The class-change scene</td></tr>
    <tr><td>Four bonus levels, one per difficulty</td><td>Added to the level of auto-levelled enemies (0, 0, 2 and 2 on story chapters, capped at 20)</td></tr>
    <tr><td>Twelve grade limits</td><td>Trial maps only: turns, losses and kills for grades A&amp;ndash;D</td></tr>
  </tbody></table>
</div>

  The table holds 44 records: the 32 story chapters, three alternate early chapters, three tutorials and six trial maps. Its title key (`MCT01`&hellip;) is the chapter title the game prints. <span class="confidence confidence--confirmed">engine</span>

!!! info "The chapter number in these filenames is not the number shown to the player"
    File-slot numbering runs exactly one behind the in-game display: slot `01` holds the Prologue. Its saved roster is Ike, Mist, Boyd, and Greil, while displayed Chapter 1 uses slot `02`, Chapter 2 uses slot `03`, and so on. <span class="confidence confidence--confirmed">confirmed</span>

!!! info "Progression lives entirely in the executable, not in any chapter's own data"
    No script or table names the next chapter. The game keeps one byte, the current chapter number; when a chapter is won it adds 1 to it, and the new number selects its chapter record. <span class="confidence confidence--confirmed">engine</span>

## How a chapter runs

  A fixed sequence in the executable runs every chapter. The chapter's event script only supplies functions with agreed names, and a missing function simply skips its step: <span class="confidence confidence--confirmed">engine</span>

1. **Load.** The record for the current number is found; its map, script and message file load. A number with no record crashes the game.
2. **Setup.** The objective texts are copied from the record, the victory and defeat flags are cleared, and the script's `Startup` function places the first units and registers the chapter's flags.
3. **Intro.** `Opening0` plays the opening scenes.
4. **Base**, only if the script has `Opening1`. From Chapter 9 on, a report of the previous chapter comes first; then the base menu; then `Opening1`.
5. **Preparations**, only if the script has `Opening2`: the preparations screen, then `Opening2`.
6. **Battle**, until the script sets the victory flag `gf_complete` or the defeat flag `gf_gameover`.
7. **After a victory.** The clear record is shown, the chapter's turn count and play time are logged, the number goes up by 1 and the save menu opens. Then step 1 runs again.

  This is why the Prologue and Chapters 1&ndash;2 have neither base nor preparations (their scripts only define `Opening0`), Chapters 3&ndash;7 have preparations but no base, and later chapters have both.

## How bonus experience is awarded

  At victory the engine enumerates the chapter script's scenario-complete events (event type 12). A qualifying event function calls `AchieveSet(label, amount)`; a nonzero return makes that event one successful report line, while a failed condition contributes neither a line nor EXP. The engine stores each successful label and adjusted amount, sums the lines, adds the result to the party's existing Bonus Exp pool, and saves the chapter's sum for Soren's next report. Maniac halves each line; Easy adds half, with integer fractions discarded; Normal and Hard leave it unchanged. The optional detailed **Bonus Exp Display** popup only controls whether these lines are shown—the calculation and award still occur when it is hidden. <span class="confidence confidence--confirmed">engine + scripts</span>

  Turn awards are ordinary script formulas: a chapter starts with its own maximum, subtracts a fixed penalty for each turn after its grace limit, and calls `AchieveSet` only if the result remains positive. Chapter 17 accumulates its four parts, and Chapter 27 combines both maps. Other requirements call chapter-specific counters before setting a line:

<div class="table-wrap">
<table class="tight"><thead><tr><th>Chapter</th><th>Special requirement and raw award</th></tr></thead><tbody><tr><td>6</td><td>10 per ally escaped; a carrier and carried unit both count</td></tr><tr><td>8</td><td>50 per unused deployment slot</td></tr><tr><td>10</td><td>700 for remaining undetected, plus 10 per ally escaped; the script doubles the stealth value on Maniac before the universal halving</td></tr><tr><td>11</td><td>50 per surviving vigilante</td></tr><tr><td>13</td><td>50 per unused deployment slot</td></tr><tr><td>15</td><td>40 per surviving enemy laguz, plus 300 if all survive</td></tr><tr><td>19</td><td>30 per raven that escapes</td></tr><tr><td>22</td><td>20 per surviving priest</td></tr></tbody></table>
</div>

  From Chapter 9 onward, Normal and Easy also receive a flat clear line that rises from 50 to 700; Hard and Maniac do not. Easy's normal 1.5 multiplier is then applied to that line too.

## How Soren's battle report is generated

  Before each base from Chapter 9 onward, Soren reports counters collected during the battle just completed. This screen is separate from both the detailed Bonus Exp achievement popup and the ending War Record. **Earned** and **Spent** are the positive and negative changes recorded whenever party gold is set; **Current** reads the present gold balance. **Combat Exp** is ordinary experience gained, while **Bonus Exp** is the summed successful achievement lines described above.

  For **MVP**, the game scans player-side units and chooses the unit with the greatest map kill count. Comparison is strictly greater, so the first unit encountered wins a tie, and nobody is shown when every count is zero. **New Ally** and **Fallen** come from per-unit joined-this-chapter and death-recorded status bits. Once the report is prepared, its chapter counters and flags are cleared for the next battle. <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Special case</th><th>What happens</th></tr></thead><tbody>
    <tr><td>Chapter 27</td><td>Two numbers (slots 28 and 29) for one chapter on two maps. Clearing 28 is a continued part: the army isn't sorted out (units that joined keep their army), the war record entry is flagged as carrying on and is merged with 29's, there is no save menu, and support points are not counted again at the start of 29. The second half's script only has an intro.</td></tr>
    <tr><td>Chapter 17</td><td>One number, four battles. The script ends each of the first three with <code>Complete18(part)</code> instead of a victory: the number stays the same, the save menu opens, and <code>Opening18_2</code>, <code>_3</code> or <code>_4</code> sets up the next battle, loading another map when needed. <code>Complete18</code> works in any chapter, but only chapter 18's later parts skip the support pass: elsewhere support points are counted again at the start of each part.</td></tr>
    <tr><td>After the Endgame</td><td>Number 32 means the game is cleared: the Endgame map is reloaded for the final scene, the ending plays, the clear is recorded per difficulty in the system data, and the title screen returns.</td></tr>
    <tr><td>Starting directly</td><td>The development chapter select starts any chapter record with an empty army, keeping the difficulty (see <a class="wl" href="../developer-debug-tools/">Developer &amp; Debug Tools</a>).</td></tr>
    <tr><td>Saves</td><td>A save stores the chapter number and a resume point: the base, preparations, the start of the chapter (the save made after a victory), part 2&amp;ndash;4 of Chapter 17, or a suspended battle (see <a class="wl" href="../../formats/save-format/">GameCube Save (.gci)</a>).</td></tr>
  </tbody></table>
</div>

Support points are added once per battle map, at its start; the two exceptions above (29, and the parts of chapter 18) are the engine's only ways of keeping a chapter's later maps from counting again. <span class="confidence confidence--confirmed">engine</span>

## Adding chapters

  Slots 0&ndash;31 are all used by the story, 32 means &ldquo;game cleared&rdquo;, and the save code treats every number from 32 up as a trial map, so a new story chapter cannot simply be appended after the Endgame. The chapter number is also the number in the chapter's file names (record 1 names `bmap01`, `C01`, `c01`). <span class="confidence confidence--confirmed">engine</span>

- **Replacing** a chapter needs data only: point its record at other files, or edit the files it names.
- **Adding battles inside a chapter** can reuse the Chapter 17 mechanism in any chapter's script, up to three extra battles per number. A Prologue whose script ends its battle this way opens the save menu and plays a second battle on the Chapter 1 map before Chapter 1 begins, and a save made in that menu reloads into the second battle. Likewise, giving the Prologue an `Opening2` function makes its preparations screen appear. <span class="confidence confidence--confirmed">in game</span>
- **Chapter name pictures.** A chapter's name appears twice as a picture, never as text: the title card when the chapter starts (`window/chapter/chap<N>.cms`, 480&times;160) and the strip in each save slot of the file menu (`window/chapter2/chap<N>.cms`, 312&times;32). The file menu finds its strip through a fixed 40-entry table in the executable that pairs a chapter number with a file name: chapters 1&ndash;31 (29, the second half of Chapter 27, shows Chapter 28's picture), "no data" (99), the tutorial (999), the epilogue (32) and the six trial maps (91&ndash;96). A chapter number missing from the table shows an empty box, so a chapter added on a free number needs a table entry as well as its two pictures. <span class="confidence confidence--confirmed">engine</span>
- **Inserting a new number** means renumbering every later record and changing the executable wherever it tests a chapter number: the Chapter 27 pair, the ending, the save limit, the report from Chapter 9 on, the convoy unlock, the phase music and the per-chapter shops.
- **Using a free number** avoids the renumbering. Numbers 33&ndash;89 are tested by nothing in the executable except the save limit, so a chapter can take one with its own record, files, shop sections and title, and be reached by changing two things: the &ldquo;add 1 after a victory&rdquo; step, made to read the next number from a small per-chapter table (both of its call sites), and the save limit, made to accept a number that is in that table. Everything else (the Chapter 27 pair, the ending at 32, the trial maps at 90 and up) keeps its own handling. <span class="confidence confidence--strong">static</span>

  Within one chapter the four files are largely independent in content but coordinated in effect: the script's [phase and turn triggers](./events-scripting.md) decide when dialogue plays and which units act, dispo's deployment records decide who is actually on the field for the script to act on, and the map file's terrain and [grid](./map-grid.md) decide where any of that can physically happen. A chapter with more than one battle-map phase — a mid-chapter reinforcement wave, for instance — gets its own suffixed map, `bmap06` then `bmap06_2`, sharing the same script and dialogue file as the primary phase.

## Worked example: a turn-three reinforcement

  The event script owns the “turn 3, enemy phase” condition. When it fires, it refers to units that the chapter's deployment data defines, places them at tactical-grid coordinates valid for the current map, and may display lines stored in the chapter message file. Editing only the dialogue changes what is said; editing only deployment changes who appears and what they carry; editing only the trigger changes when the same reinforcement sequence runs.

## What a chapter does not own

  Character base definitions, class capabilities, item definitions, and skill definitions remain global in [FE8Data.bin](../formats/fe8data.md). A chapter selects and overrides those definitions; it does not duplicate them. Campaign progression is also not a fifth chapter-data file: native code advances the current chapter number after completion.

## Playthrough number

  A new game records how many different games have already been cleared on the memory card, plus one. On the first playthrough the 17 class rings marked in deployment records (such as Oscar's Knight Ring and Hibuchi's Thief Ring) are not given; from the second on they appear and drop. From the second playthrough, holding A also speeds up map unit movement. Each game gets an id when it starts, and a clear is recorded once per id, so clearing again from a later save of the same game doesn't count twice. Scripts read the same number with `SysGetRound`. <span class="confidence confidence--confirmed">confirmed</span>

## Difficulty

  One difficulty setting — Easy, Normal, Hard, or Maniac, defaulting to Hard — is chosen once at the start of a playthrough and persists across every chapter transition rather than being stored or re-derived per chapter. Difficulty-indexed lookups spread throughout the game read this same value by name: it selects among the [EXP, growth, and critical-bonus constants](./combat-mechanics.md) used in combat, which per-chapter shop stock is available, and a handful of map-only effects only active on the harder settings.
