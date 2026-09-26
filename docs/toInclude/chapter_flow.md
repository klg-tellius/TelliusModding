# How chapters start, end and follow each other

Summary for the documentation: what the game does between "New Game" and the ending, and what that means for adding chapters. Code path and addresses: `research/MAIN_DOL_NOTES.md`, "Chapter progression mechanism" and "Game flow process scripts"; chapter files and the modding routes: `research/CHAPTER_DATA_NOTES.md`, "How a chapter starts and ends".

## One number decides the chapter

The game keeps a single byte, the current chapter number. Everything about a chapter is looked up from it: the `ChapterData` table in `FE8Data.bin` has one record per number, naming the map, the event script, the message file, the music, the objective texts and the backgrounds. Nothing on the disc says which chapter comes next: when a chapter is won, the game adds 1 to the number.

| Numbers | Use |
|---|---|
| 0–31 | the story: the Prologue is 1 (`bmap01`, `C01`), the Endgame 31 |
| 32 | the game has been cleared: the ending plays |
| 51, 52, 58 | alternate versions of three early chapters |
| 80–82 | tutorials |
| 91–96 | trial maps |

## The steps of a chapter

1. **Loading.** The record for the number is found and its map, script and messages load.
2. **Setup.** The objective texts are copied, and the script's `Startup` function places the first units and registers the chapter's flags.
3. **Intro.** The script's `Opening0` function plays the opening scenes.
4. **Base** (only if the script has an `Opening1` function). From Chapter 9 (number 10) on, a report of the previous chapter comes first; then the base menu; then `Opening1`.
5. **Preparations** (only if the script has an `Opening2` function). The preparations screen, then `Opening2`.
6. **Battle.** Turns alternate until the script sets `gf_complete` (victory) or `gf_gameover`.
7. **After a victory.** The clear record is shown, the chapter's turn count and play time are logged, the number goes up by 1, and the save menu opens. Then step 1 runs for the next number.

So the Prologue and Chapters 1–2 have neither base nor preparations (their scripts only have `Opening0`), Chapters 3–7 have preparations but no base, and later chapters have both.

## Special cases

- **Chapter 27** is two maps with numbers 28 and 29. Between them there is no save menu, and the second half's script only has an intro.
- **Chapter 17** is one number with four battles. Its script ends each of the first three with `Complete18(part)` instead of a victory: the number does not change, the save menu opens, and the script's `Opening18_2`, `Opening18_3` or `Opening18_4` sets up the next battle, loading another map if needed.
- **The ending.** When the number reaches 32, the Endgame's map is reloaded for the final scene, the ending script plays, the clear is recorded in the system data (by difficulty), and the game returns to the title screen.
- **Saves** record the chapter number and a resume point: "start of chapter" for the save made after a victory, "part 2–4" for Chapter 17, or a point in the middle of a map.

## What this means for new chapters

- A number without a record crashes the game, and the story only moves by +1, so a new chapter cannot just be appended after the Endgame: 32 already means "ending", and the save code treats every number from 32 up as a trial map.
- **Replacing** a chapter needs data changes only: point its record at new files, or edit the files.
- **Adding battles inside a chapter** can use the Chapter 17 mechanism (`Complete18` and `Opening18_2`–`Opening18_4`) in any chapter's script, up to three extra battles per chapter. This follows from the code but has not been tried outside Chapter 17.
- **Inserting a new chapter number** means renumbering the later records and changing the executable wherever it tests a chapter number (the Chapter 27 pair, the ending, the save limit, the report from Chapter 9 on, the convoy unlock, the music, the shops).
