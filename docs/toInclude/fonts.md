# Fonts

Path of Radiance (US) draws all text from five bitmap fonts. Font numbers are what the `#Fxx` message code and the engine's font-select calls use.

| # | Name | File | Glyphs | Look |
|---|---|---|---|---|
| 0 | system | `Fonts/system.cms` (LZ10) | 3988 | General UI; full CP932 set |
| 1 | fe_font | `Fonts/fe_font.gcf` | 95 | The invented Tellius alphabet, mapped onto ASCII 0x20-0x7E |
| 2 | talk | `Fonts/talk.gcf` | 4005 | Dialogue; same set as system, taller |
| 3 | bigkana | `Fonts/bigkana.gcf` | 95 | Large Latin serif |
| 4 | alpha | `Fonts/alpha.gcf` | 77 | Large condensed sans |

- Fonts 1-4 are read from the copies bundled in `system.cmp` (identical to the loose files). The system font comes from `system.cms`; the loose `Fonts/system.gcf` is never loaded.
- File: 0x30-byte header (ascent/descent at +8/+10, widest glyph +0xC, sheet size +0x14, texture format +0x18 = I4, sheet count +0x1A, sheet width/height +0x1E/+0x20, table offset +0x22, sheet data offset +0x24, sheet data size +0x28), then 16-byte glyph records sorted by code (code, sheet, U, V, width, height, bearing X, bearing Y, advance), then the I4 sheets.
- Lookup is a binary search by CP932 code. A missing character falls back to 0x8199 (☆), then to the first record (space). So a missing character shows as ☆ in the system and talk fonts and disappears in the three small ones.
- A glyph is drawn at x + bearing X, y + ascent - bearing Y; x then moves by the advance.

## Which font is used where

- System: every menu, status, forecast, shop and list screen; tutorial windows; speaker names in the backlog.
- Talk: dialogue textbox lines and backlog lines.
- fe_font (Tellius alphabet): ancient-language lines (heron galdr, Leanne and Reyson, the endgame), switched on with `#F01` and back with `#F02`, in 31 messages.
- Bigkana: title-menu and file-menu labels (each label is prefixed with `#F03`).
- Alpha: staff-roll names (format `#F04%s`).
- A separate built-in 8x8 ASCII font (not a GCF file) draws debug overlays.

A `#F` switch lasts until the end of the textbox line: each line is drawn as its own text primitive, so vanilla text repeats `#F01` at the start of every ancient-language line.

`$O<n>` in message text picks the text-typing sound `SFX_SYS_MSG<n>` (0 silent; 1 dialogue, 2 ancient language, 3 world-map narration, 4 tutorial). It does not change the font.

## Replacing a font

- Fonts are loaded into heap memory sized from the file, so a replacement may be larger than the original; there is no fixed font buffer.
- Glyph placement on the sheets is free: the engine only reads each record's sheet, U, V, width and height. Keep records sorted by code, keep ascent/descent to keep text on its lines, and write fonts 1-4 to both the loose file and `system.cmp`.
- Only characters with a CP932 code can appear in game text, so accented Latin letters need a free code of their own.
- The Tellius Modding app does this under Assets › Fonts (TrueType/OpenType import), and its dialogue step editor has a Font menu that writes the `#F` codes.

Open: whether chapter title cards, map names and damage numbers are font text or pre-rendered art, and how the drop shadow is drawn.
