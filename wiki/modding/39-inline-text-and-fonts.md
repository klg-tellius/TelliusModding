---
id: "modding-inline-text-and-fonts"
title: "Control dialogue text, timing, icons, and fonts"
description: "A practical guide to line and page control, pauses, typing sounds, colours, icons, text effects, scale, font switches, Tellius script, and glyph failures"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Dialogue", "Fonts", "Inline codes"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/39-inline-text-and-fonts.md"
tutorial_kind: "task"
tutorial_track: "dialogue-and-text"
tutorial_stage: "draft"
prerequisites: ["modding-dialogue-editor"]
verification: ["source-reviewed", "unknown"]
---
# Control dialogue text, timing, icons, and fonts

**Route:** Chapter → Dialogue → line text and Actions

## What you will make

You will turn one plain two-line dialogue page into a controlled typography test:

- a natural pause with mouth motion stopped around an ellipsis;
- an explicit line break and page/button wait;
- one coloured phrase that returns to the previous colour;
- one inline A-button icon;
- one ancient-language phrase in the Tellius alphabet with its matching typing sound;
- a final ordinary line that proves font, sound, colour, and scale did not leak.

You will compare the result at Slow, Normal, Fast, and Max message speeds and verify it through the real script caller. The purpose is to understand state and scope, not to decorate every line.

## Before you begin

Complete [Author and connect a dialogue scene](37-dialogue-editor.md). Duplicate a short message that already parses, previews, and plays. Preserve an unformatted copy of every spoken line.

Choose source characters that the current dialogue font already renders. For the first exercise, use ASCII letters, digits, and known punctuation. A TrueType font installed on your computer does not expand the game's text encoding or current bitmap font.

Record the baseline at Normal message speed:

- number of visible lines/pages;
- speaker and box;
- where button input is required;
- typing sound;
- final scene state.

Do not combine this lesson with a font-file import. Lesson 42 changes the glyph assets themselves; this lesson changes which existing font/effect draws a part of a message.

## How the editor fits together

Ordinary characters and inline commands coexist inside each dialogue line. Scene actions control boxes, portraits, and messages; inline codes control text rendering and cadence. In the readable editor, toolbar/actions are shown as highlighted `<...>` tokens, while font/colour/timing markup is represented by the underlying message codes and described in the action editor/tooltips.

The relevant scopes differ:

- font switches, scale, italic, and many text effects last to reset or line end;
- colour can be explicitly restored with the previous-colour code;
- typing sound persists according to scene/message commands until changed;
- page and box operations alter dialogue flow rather than glyph appearance;
- each new dialogue line begins in the normal talk font unless a switch is repeated.

The game draws from five bitmap fonts:

| Index | Name | Typical use |
| ---: | --- | --- |
| 0 | system | menus and UI |
| 1 | fe_font | Tellius ancient alphabet mapped to ASCII |
| 2 | talk | ordinary dialogue default |
| 3 | bigkana | title/file-menu serif |
| 4 | alpha | condensed staff-roll font |

The editor's font operation wraps each selected line separately and returns non-talk choices to font 2. Tellius font also pairs its opening with typing sound 2 and closes with talk font plus dialogue sound 1, matching the vanilla convention.

## Guided walkthrough

### 1. Establish a plain control page

Open the duplicated message. Keep one speaker and one box active. Use these four plain phrases or equivalents:

1. `Wait for it...`
2. `Press A to continue.`
3. `The old words awaken.`
4. `This line is ordinary again.`

Preview at Normal speed. Confirm every character renders, the box fits, and no notation error is shown. Save a screenshot or written timing/layout note for comparison.

### 2. Make the ellipsis natural

Wrap the ellipsis with the supported mouth-still operation: the message representation uses `$MC...$MD`. Insert it through **Actions...**/the documented inline action rather than typing unknown bytes. The speaker's mouth should stop during the dots and resume afterward.

Add a pause after the ellipsis. Pause power `n` waits `2^n` frames: power 4 is 16 frames, power 5 is 32. Start with power 4. At Max message speed, ordinary characters appear immediately but the authored pause remains a separate cadence event.

Test the line with Auto-advance off and on. Mouth control affects animation; pause affects time. Neither creates a button wait by itself.

### 3. Separate line break from page/input wait

Insert a **new line** where you want the next text row in the same box. In raw message terms this is `$N`. It does not necessarily clear the box or wait for input.

Use the editor's **Clear**/new-page operation when the following text should replace the page, and preserve the working message's `$K` button-wait behavior at the intended page boundary. `$K` waits for player input while keeping text visible; pressing A can reveal the rest of a current page before advancing.

Step through the preview and state exactly which action causes:

- a second row;
- a button wait;
- the previous text to clear.

If you cannot distinguish them, restore the baseline and introduce one operation at a time.

### 4. Colour one phrase and restore it

Select a short phrase such as `Press A` and insert a documented palette colour (`#Cxx`) through the supported Markup/action workflow. Immediately restore the previous colour with `#c` after the phrase.

Preview the following words and the next line. If they remain coloured, the restore is missing or placed after the wrong byte position. Colour is not a replacement for font: both can apply simultaneously.

Use a colour already present in a vanilla message with the same type of box. Arbitrary palette indices may be unreadable against a particular background.

### 5. Insert an inline button icon

At the `A` in `Press A to continue`, replace the literal letter with the A-button icon selected through Markup/action help. The known code is icon cell `#P027`; it draws a 24×24 cell from `window/icon.tpl` and advances the line by 24 pixels.

The B button is `#P028`; weapon/category icons occupy other documented cells. Icon codes use hexadecimal cell identifiers and are not Unicode emoji. Check vertical alignment and remaining line width at all message speeds.

### 6. Apply the Tellius alphabet correctly

Select only `The old words awaken.` and apply **Tellius alphabet (ancient language)**. The editor wraps the selection per line with the font-1 opening and the closing return to talk. It also changes typing sound to ancient-language sound 2, then returns to dialogue sound 1.

Preview the glyphs. `fe_font` maps ordinary ASCII letters to invented Tellius symbols; it does not translate English into another language. The underlying text remains the characters you typed.

If the selected phrase spans two lines, inspect both lines: font switches reset at line boundaries, so the editor repeats the opening on each non-empty line. This is expected.

### 7. Prove state restoration

Keep `This line is ordinary again.` after the ancient phrase. Verify it renders in talk font, ordinary dialogue typing sound, default colour, default scale, and no italic/effect.

If state leaks, use the editor's font application/strip controls and explicit documented reset rather than inserting an arbitrary collection of raw codes. `#D` resets default colour, size, and slant and disables shadow/outline, but it is not always identical to the normal dialogue box's desired shadow/outline state. Prefer the precise paired closing produced by the editor.

### 8. Compare message speeds and input

Run the complete page at:

- Slow: 10 frames per ordinary character;
- Normal: 4 frames per character;
- Fast: 1 frame per character;
- Max: page text appears at once.

Authored `$w` pauses, waits, page operations, and transitions still define event boundaries. Press A during partially typed text to reveal the page, then press again at the wait. Press Z at a wait to inspect the text log and confirm narration/speaker capture.

### 9. Save and test through the caller

Save Chapter, reopen the message, and verify all highlighted actions/markup remain intact. Run the script caller from a clean state and test normal viewing plus skip. Check that the next message/scene begins with the expected font, sound, box, and colour.

Finish in Dolphin. Typing cadence, button input, mouth movement, text-log capture, and glyph rasterization are runtime behavior that a static frame cannot fully prove.

## Understand every control

### Wait, Pause, New line, Clear, and advance

- **Pause power** inserts `$wN`, waiting `2^N` frames.
- **Wait** inserts the selected scene wait behavior; inspect its exact action help.
- `$N` starts another row in the current text flow.
- **Clear** uses the layout/dialect's box clear/new-page operation.
- `$K` waits for button input with text visible.
- `$Y` advances without a button wait, useful for an interrupted speaker.
- `$H` hands control back to the event script so the message can resume later.
- `$UB`/`$Ub` lets a waiting event script run again and is paired with `$H` in vanilla patterns.

Copy `$H`/resume patterns from a working event; they coordinate two interpreters and are not ordinary page breaks.

### Mouth and typing sound

`$MC` stops mouth motion and `$MD` restarts it. Use the paired ellipsis/dash helper so the restart cannot be forgotten.

`$O0` is silent, 1 dialogue, 2 ancient language, 3 world-map narration, and 4 tutorial. Typing sound is independent of font even though the editor pairs sensible values for Tellius text.

### Font selection

Applying a font to a selection removes conflicting font switches inside that selection, wraps each non-empty line, and returns non-talk fonts to talk. An empty selection inserts opening/closing at the cursor. **Strip fonts** removes font codes from the selection—or the whole line/text scope used by the control when there is no selection.

### Colour and restore

`#Cxx` selects a palette colour; `#c` restores the previous colour. Per-channel `#Rxx/#Gxx/#Bxx/#Axx` controls are lower-level RGBA changes and should be used only in isolated experiments because vanilla dialogue does not rely on them.

### Icons

`#Pnnn` selects a hex-numbered 24×24 icon cell. It remains 24 pixels even when text is scaled, so scaling nearby text can produce uneven alignment.

### Scale, italic, shadow, and outline

- `#Sxx` scales both axes by `xx/64`; `#Xxx` and `#Yxx` scale one axis.
- `#s/#x/#y` reset the corresponding scales.
- `#Ixx` slants text; `#i` ends italic.
- `#E/#e` enable/disable drop shadow.
- `#O/#o` enable/disable outline.
- `#D` resets colour, size, and slant and disables shadow/outline.

Scale grows right/down from line origin and does not increase line spacing. Oversized text can overlap other rows or leave the box even though parsing succeeds.

## Interactions and precedence

- Each line starts in talk font; multi-line special text needs a switch on every line.
- The editor's font wrapper handles paired return-to-talk and Tellius typing-sound restoration.
- Message speed controls ordinary character reveal; authored pauses/waits remain distinct.
- A press of A first reveals the rest of a typing page, then advances at the appropriate wait.
- Colour and font are independent; restore both when both change.
- Icons do not scale with text and consume fixed width.
- Scale/effects reset at line boundaries or explicit reset according to their code; do not assume page boundaries fix malformed state.
- Missing glyph fallback depends on the chosen font: dialogue fonts can show a white star, smaller fonts may fall back to space.
- Valid text encoding is required before glyph lookup. A glyph asset cannot make an unencodable Unicode character valid.
- Preview speed/context settings are not saved into the message.

## Test matrix

| Test | Setup | Pass condition |
| --- | --- | --- |
| Plain control | no markup | original text fits and renders |
| Mouth pause | wrapped ellipsis + pause 4 | mouth stops for dots; 16-frame pause is observable |
| Line break | `$N`/editor action | next row without unintended page clear |
| Page/input | clear + working wait | player input and old-text removal occur at intended points |
| Colour | coloured phrase + restore | only selected phrase changes |
| Icon | A-button cell | correct 24×24 icon, no overflow |
| Tellius | selected phrase | font 1 glyphs + sound 2; next line returns to talk/sound 1 |
| Four speeds | Slow/Normal/Fast/Max | ordinary reveal changes; authored boundaries remain |
| Text log | open at wait | intended speaker/narration text recorded |
| Runtime/skip | real caller | next scene state is identical after normal and skipped viewing |

## Troubleshooting

### A character becomes a star or disappears

The chosen font lacks that CP932 code/glyph. Test the same character in talk and system fonts, inspect the font viewer, and use a supported character or import a glyph through lesson 42. Unicode availability on the host is irrelevant.

### The next line remains in Tellius script

The line was hand-coded without a return to talk, or line boundaries/actions were malformed. Reapply the Tellius font through the editor so it generates a paired wrapper, then inspect every line.

### The next words remain coloured

Insert the previous-colour restore immediately after the selected phrase. Check byte/action position, not just where the cursor visually appears around an icon.

### Max speed removes the intended dramatic timing

Ordinary typing delay vanishes at Max. Add a documented authored pause or scene wait at the dramatic boundary; do not rely on character count.

### Text overlaps or leaves the box

Remove scale/italic first, then shorten the line or choose a suitable layout. Scaling does not increase line height, and icons retain fixed size.

### Dialogue hangs after handoff

An `$H`/`$UB` script-resume sequence is incomplete or mismatched with the caller. Restore the exact working message/script pair and modify only after tracing both sides.

## Save, build, and revert

Save Chapter, reopen the message, then Check/save the caller if its event flow changed. Build after previewing all speeds and reset/inherited context.

To revert, restore the unformatted line or the backed-up chapter message file. Removing visible words alone may leave invisible font/effect/wait codes, so use the editor's strip/remove actions or replace the complete affected line from the control copy.

## Limits and confidence

Font identities, inline code meanings, timing rates, fallback behavior, line scope, icons, scale/effect behavior, and editor font wrapping are source-reviewed. Some low-level colour/effect codes are supported by the engine but absent from retail dialogue; treat them as experimental and verify contrast/accessibility.

Preview approximates runtime input, audio, mouth animation, and logs. Dolphin is required for final cadence, controller behavior, skip/handoff, and rasterization.

## Things to try

- Put pause powers 1–6 in one test page and time their doubling pattern.
- Compare the same ASCII phrase in all five fonts without changing the underlying text.
- Place an icon beside 50%, 100%, and 200% text to observe fixed icon size.
- Toggle shadow/outline on a high-contrast test phrase, then restore the vanilla box look.
- Use horizontal scale 91% on a deliberately long line and compare fit/readability.
- Open the text log after ancient text and verify what characters/speaker name it stores.

## Related tutorials and references

- [Author and connect a dialogue scene](37-dialogue-editor.md)
- [Create and display dialogue backgrounds](38-backgrounds.md)
- [Import a translation font](42-font-translation.md)
- [Message format](../formats/message-format.md)
- [Font format](../formats/font-format.md)
- [Dialogue engine](../systems/dialogue-engine.md)

---

[← Previous: Create and display dialogue backgrounds](38-backgrounds.md) · [All tutorials](index.md) · [Next: Edit base conversations and narration →](40-base-and-world-map-text.md)
