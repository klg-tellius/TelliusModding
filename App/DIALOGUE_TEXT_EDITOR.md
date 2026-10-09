# Dialogue text editor

The Dialogue tab edits one selected message as continuous text. The right-hand
Path of Radiance seat panel and existing playback controls remain available.
The highlighted text/action follows playback without moving the editing cursor.

- Type dialogue normally; wrapping does not add game line breaks.
- Use the toolbar buttons for speaker/seat, portrait, waits, pauses and clearing
  the box. **Actions…** opens a palette of buttons for the remaining actions.
- Actions appear inside individual frames. Type them directly or double-click
  a frame to edit its contents. Names and arguments are separated with a colon.
- Click an occupied seat to insert its speaker selection at the cursor. Click
  an empty seat to choose a portrait. The seat panel follows the cursor or playback.
- Undo/redo, find/replace, selection and copy/paste work on text and actions.
- Import/export reads and writes the current message as UTF-8 `.txt`. Import can
  replace the message or insert at the cursor/selection and can be undone.
- Invalid actions stay in the editor as drafts, including when switching message
  IDs. The error identifies a line and column. Preview uses the last valid text;
  chapter saving requires fixing all invalid drafts. Drafts can be exported.

Path of Radiance example:

```text
<Show speaker:0IKE>Hello, Soren.<Wait>
<Show speaker:1SOREN>We should leave.<Pause power:4><Wait>
```

Radiant Dawn example:

```text
<Cast:IKE|SOREN><Speaker:04>Hello, Soren.<Wait>
<Speaker:14>We should leave.<Wait>
```

`Pause power:n` retains the game's timing of 2^n frames. `Transition ms` controls
fade duration, not a dialogue pause. The available actions follow each game's
existing command catalogue; the same message text is not interchangeable between
games.

For literal `<` or `>`, use `<Bytes:3C>` or `<Bytes:3E>`. Within action arguments,
use `&lt;`, `&gt;` and `&amp;`. Undecoded bytes are preserved with `<Bytes:HEX>`;
unknown named actions are retained as invalid drafts rather than discarded.
The on-disc message format and IDs do not change.

Validation: `python -m unittest discover -s App/tests -p test_dialogue_editor.py -v`.
The regression suite covers both dialects, multibyte characters, action/source
mapping, seat insertion, playback selection preservation, import/export, drafts,
and undo/redo. Disc-asset integration tests require the existing FE9/FE10 extracted
asset environment variables.
